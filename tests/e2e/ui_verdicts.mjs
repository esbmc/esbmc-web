// End-to-end check of the verdict banner shown by frontend/index.html.
// Requires: the backend on 127.0.0.1:5000, ESBMC on PATH, Google Chrome, Node >= 22.
// Usage: node tests/e2e/ui_verdicts.mjs
// Scenarios with `knownDefect` behave like strict xfail: they must fail, and an unexpected pass
// fails the run so the marker gets removed once the defect is fixed.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const CHROME = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PAGE = pathToFileURL(resolve(dirname(fileURLToPath(import.meta.url)), '../../frontend/index.html')).href;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const SLOW_C = 'unsigned nondet_uint();\nint main(){ unsigned s=0; for (unsigned i=0;i<5000000;i++){ s = s*31u + nondet_uint(); } __ESBMC_assert(s != 7u, "s"); return 0; }\n';

const SCENARIOS = [
  { id: 'E2E-01', lang: 'c', expect: 'FAILED',
    code: '#include <assert.h>\nint main(){int x=5; assert(x==6); return 0;}\n' },
  { id: 'E2E-02', lang: 'c', expect: 'SUCCESSFUL',
    code: '#include <assert.h>\nint main(){int x=5; assert(x==5); return 0;}\n' },
  { id: 'E2E-03', lang: 'c', expect: 'NOT_SUCCESSFUL', knownDefect: '#13', note: 'parse error must not be shown as success',
    code: 'int main( { return 0 }\n' },
  { id: 'E2E-04', lang: 'c', expect: 'NOT_SUCCESSFUL', knownDefect: '#13', note: 'timeout must not be shown as success',
    timeout: '3', unwind: '5000001', code: SLOW_C },
  { id: 'E2E-05', lang: 'c', expect: 'NOT_SUCCESSFUL', knownDefect: '#12/#13', note: 'cancelled run must not be shown as success',
    cancelAfterMs: 3000, unwind: '5000001', code: SLOW_C },
];

async function cdp(port) {
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = targets.find((t) => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  let seq = 0;
  const pending = new Map();
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  });
  const send = (method, params = {}) => new Promise((r) => {
    const id = ++seq;
    pending.set(id, r);
    ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async (expression) => {
    const res = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (res.result?.exceptionDetails) throw new Error(JSON.stringify(res.result.exceptionDetails));
    return res.result?.result?.value;
  };
  return { send, evaluate, close: () => ws.close() };
}

async function waitFor(evaluate, expr, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await evaluate(expr)) return true;
    await sleep(300);
  }
  return false;
}

async function runScenario(page, s) {
  const { send, evaluate } = page;
  await send('Page.navigate', { url: PAGE });
  await waitFor(evaluate, `!!document.querySelector('.CodeMirror') && !document.getElementById('analisarBtn').closest('[style*="display: none"]')`, 15000);
  await evaluate(`(() => {
    const ov = document.getElementById('server-startup-overlay'); if (ov) ov.style.display = 'none';
    document.getElementById('lang-${s.lang}').click();
    document.querySelectorAll('.esbmc-param').forEach(i => { i.value = ''; });
    ${s.timeout ? `document.querySelector('.esbmc-param[data-flag="--timeout"]').value = '${s.timeout}';` : ''}
    ${s.unwind ? `document.querySelector('.esbmc-param[data-flag="--unwind"]').value = '${s.unwind}';` : ''}
    const cm = document.querySelector('.CodeMirror').CodeMirror;
    cm.setValue(${JSON.stringify(s.code)});
    document.getElementById('status-banner').textContent = '';
    return true;
  })()`);
  await waitFor(evaluate, `!document.getElementById('analisarBtn').disabled`, 5000);
  await evaluate(`document.getElementById('analisarBtn').click()`);
  if (s.cancelAfterMs) {
    await sleep(s.cancelAfterMs);
    await evaluate(`document.getElementById('cancelarBtn').click()`);
  }
  const done = await waitFor(evaluate,
    `document.getElementById('analisarBtn').style.display !== 'none' && document.getElementById('cancelarBtn').style.display === 'none'`,
    120000);
  await sleep(500);
  const banner = await evaluate(`document.getElementById('status-banner').textContent.trim()`);
  const terminal = await evaluate(`(document.getElementById('resultado-texto') || {}).textContent || ''`);
  const showsSuccess = /VERIFICATION SUCCESSFUL/.test(banner);
  const showsFailed = /VERIFICATION FAILED/.test(banner);
  let pass = done && banner !== '';
  if (s.expect === 'SUCCESSFUL') pass &&= showsSuccess && !showsFailed;
  else if (s.expect === 'FAILED') pass &&= showsFailed;
  else pass &&= !showsSuccess;
  const lastEsbmcLine = terminal.split('\n').filter((l) => /VERIFICATION|ERROR|STOPPED/.test(l)).slice(-1)[0] || '';
  let result = pass ? 'PASS' : 'FAIL';
  if (s.knownDefect) result = pass ? 'XPASS' : 'XFAIL';
  return { id: s.id, expect: s.expect, knownDefect: s.knownDefect || '', note: s.note || '', completed: done, banner, esbmc: lastEsbmcLine.trim(), result };
}

const profile = mkdtempSync(join(tmpdir(), 'esbmc-web-e2e-'));
const chrome = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  '--no-first-run', '--allow-file-access-from-files', 'about:blank',
], { stdio: 'ignore' });

let failures = 0;
try {
  const portFile = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 50 && !existsSync(portFile); i++) await sleep(200);
  const port = readFileSync(portFile, 'utf8').split('\n')[0];
  let page;
  for (let i = 0; i < 50 && !page; i++) {
    try { page = await cdp(port); } catch { await sleep(200); }
  }
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  for (const s of SCENARIOS) {
    const r = await runScenario(page, s);
    if (r.result === 'FAIL' || r.result === 'XPASS') failures++;
    console.log(JSON.stringify(r));
  }
  page.close();
} finally {
  chrome.kill();
  rmSync(profile, { recursive: true, force: true });
}
process.exit(failures ? 1 : 0);
