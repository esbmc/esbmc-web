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
  { id: 'E2E-03', lang: 'c', expect: 'NOT_SUCCESSFUL', banner: /ESBMC ERROR/, note: 'parse error must not be shown as success',
    code: 'int main( { return 0 }\n' },
  { id: 'E2E-04', lang: 'c', expect: 'NOT_SUCCESSFUL', banner: /TIMED OUT/, note: 'timeout must not be shown as success',
    timeout: '3', unwind: '5000001', code: SLOW_C },
  { id: 'E2E-05', lang: 'c', expect: 'NOT_SUCCESSFUL', banner: /CANCELLED/, note: 'cancelled run must not be shown as success',
    cancelAfterMs: 3000, unwind: '5000001', code: SLOW_C },
  { id: 'E2E-11', lang: 'c', expect: 'NOT_SUCCESSFUL', banner: /LOOP BOUND REACHED/,
    note: 'a safe loop longer than the default bound is shown as bound reached, not as a failure',
    code: '#include <assert.h>\nint main(){int s=0; for(int i=0;i<10;i++) s++; assert(s==10); return 0;}\n' },
];

const ROW = (file, status, extra = {}) => ({
  index: 1, grau: 0, nome_grau: 'Auxiliary', lang: 'C', directory: 'src', file, score: 10, reasons: '-',
  fused_deps: 0, fused_names: '-', goto_time: '0.1s', ssa_assigns: 0, vccs: 0, wall_time: '0.1s', mode: 'Native C',
  phase: 'Phase 1', esbmc_cli: 'esbmc', z3_witness: '', violations: 0, status, expected_verdict: '-',
  test_status: 'COMPLETED', test_status_code: 'COMPLETED', is_harness: false, homogenized_code: '', ...extra,
});

// Stubbed scenarios replace the backend with a canned /status payload to pin rendering decisions.
SCENARIOS.push(
  { id: 'E2E-06', lang: 'c', expect: 'NOT_SUCCESSFUL', banner: /INCONCLUSIVE — ESBMC REPORTED NO VERDICT/, code: 'int main(){return 0;}\n',
    note: 'oracle suite banner must not override an inconclusive repository verdict',
    stub: { status: 'completed', logs: '', progresso: null, resultado: {
      verdict: 'UNKNOWN', verificacao_sucesso: false, dashboard_data: [], codigo_analisado: '// stub',
      repo_exploration_summary: [
        ROW('src/a.c', 'BOUNDED SAFE (k=1)', { expected_verdict: 'VERIFICATION SUCCESSFUL', test_status: '🟢 PASS (Proved Safe)', test_status_code: 'PASS_SOUND' }),
        ROW('src/b.c', 'ERROR (NO VERDICT)', { index: 2 }),
      ] } } },
  { id: 'E2E-07', lang: 'c', expect: 'FAILED', code: 'int main(){return 0;}\n',
    note: 'partial results with violations must show FAILED, not an error',
    stub: { status: 'error', logs: '', resultado: null, progresso: {
      current: 1, total: 2, violation_count: 1,
      partial_summary: [ROW('src/bug.c', 'VIOLATION [NATIVE BUG] (k=1)', { violations: 1 })] } } },
  { id: 'E2E-08', lang: 'c', expect: 'FAILED', code: 'int main(){return 0;}\n',
    note: 'completed repository run with a violation and no oracles must show FAILED',
    stub: { status: 'completed', logs: '', progresso: null, resultado: {
      verdict: 'FAILED', verificacao_sucesso: false, codigo_analisado: '// stub',
      dashboard_data: [{ status: 'violation', steps: [{ type: 'violation', message: 'assertion 0', file: 'src/bug.c', line: 3, function: 'main', cwe: 'CWE-617', severity: 'High' }] }],
      repo_exploration_summary: [ROW('src/bug.c', 'VIOLATION [NATIVE BUG] (k=1)', { violations: 1, test_status: '❌ VIOLATION', test_status_code: 'VIOLATION' })] } } },
  { id: 'E2E-09', lang: 'c', expect: 'BANNER', banner: /TEST SUITE PASSED: 1 BUG/, code: 'int main(){return 0;}\n',
    note: 'a real oracle suite whose expected bug was found still shows the approved-suite banner',
    stub: { status: 'completed', logs: '', progresso: null, resultado: {
      verdict: 'FAILED', verificacao_sucesso: false, codigo_analisado: '// stub',
      dashboard_data: [{ status: 'violation', steps: [{ type: 'violation', message: 'assertion 0', file: 'src/bug.c', line: 3, function: 'main', cwe: 'CWE-617', severity: 'High' }] }],
      repo_exploration_summary: [ROW('src/bug.c', 'VIOLATION [NATIVE BUG] (k=1)', { violations: 1, expected_verdict: 'VERIFICATION FAILED', test_status: '🟢 PASS (Bug Found)', test_status_code: 'PASS_BUG_FOUND' })] } } },
  { id: 'E2E-10', lang: 'c', expect: 'BANNER', banner: /TEST SUITE INCONCLUSIVE/, code: 'int main(){return 0;}\n',
    note: 'an oracle module without a verdict keeps the suite from showing as approved',
    stub: { status: 'completed', logs: '', progresso: null, resultado: {
      verdict: 'FAILED', verificacao_sucesso: false, codigo_analisado: '// stub',
      dashboard_data: [{ status: 'violation', steps: [{ type: 'violation', message: 'assertion 0', file: 'src/bug.c', line: 3, function: 'main', cwe: 'CWE-617', severity: 'High' }] }],
      repo_exploration_summary: [
        ROW('src/bug.c', 'VIOLATION [NATIVE BUG] (k=1)', { violations: 1, expected_verdict: 'VERIFICATION FAILED', test_status: '🟢 PASS (Bug Found)', test_status_code: 'PASS_BUG_FOUND' }),
        ROW('src/slow.c', 'TIMEOUT (NO VERDICT)', { index: 2, expected_verdict: 'VERIFICATION SUCCESSFUL', test_status: '⚠ INCONCLUSIVE (No Verdict)', test_status_code: 'INCONCLUSIVE' }),
      ] } } },
);

const probe = (id) => `<img id=${id} src=x>`;
const PROBES = ['p_msg', 'p_vfile', 'p_func', 'p_row', 'p_dir', 'p_w', 'p_mode', 'p_cli', 'p_fused', 'p_exp'];
SCENARIOS.push({
  id: 'E2E-12', lang: 'c', expect: 'BANNER', banner: /./, forbid: PROBES, code: 'int main(){return 0;}\n',
  note: 'values from ESBMC, the analysed code or a repository are shown as text, never parsed as HTML',
  stub: { status: 'completed', logs: '', progresso: null, resultado: {
    verdict: 'FAILED', verificacao_sucesso: false, codigo_analisado: '// stub',
    dashboard_data: [{ status: 'violation', steps: [{ type: 'violation', message: `assertion ${probe('p_msg')}`,
      file: `${probe('p_vfile')}.c`, line: 3, function: probe('p_func'), cwe: 'CWE-617', severity: 'High' }] }],
    repo_exploration_summary: [ROW(`${probe('p_row')}.c`, 'VIOLATION [NATIVE BUG] (k=1)', {
      violations: 1, directory: probe('p_dir'), z3_witness: probe('p_w'), mode: probe('p_mode'),
      esbmc_cli: probe('p_cli'), fused_names: probe('p_fused'), expected_verdict: probe('p_exp'),
      test_status: '🟢 PASS (Bug Found)', test_status_code: 'PASS_BUG_FOUND' })] } },
});

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
  const send = (method, params = {}) => new Promise((r, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP ${method} timed out`)); }, 30000);
    pending.set(id, (msg) => { clearTimeout(timer); r(msg); });
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
  if (s.stub) {
    await evaluate(`(() => {
      const stub = ${JSON.stringify(s.stub)};
      const json = (body) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
      const realFetch = window.fetch.bind(window);
      window.fetch = (url, opts) => {
        if (String(url).endsWith('/analisar')) return Promise.resolve(json({ task_id: 'stub' }));
        if (String(url).endsWith('/status/stub')) return Promise.resolve(json(stub));
        return realFetch(url, opts);
      };
      return true;
    })()`);
  }
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
  else if (s.expect === 'NOT_SUCCESSFUL') pass &&= !showsSuccess;
  if (s.banner) pass &&= s.banner.test(banner);
  if (s.forbid) {
    const injected = await evaluate(`${JSON.stringify(s.forbid)}.filter(id => document.getElementById(id))`);
    if (injected.length) console.log(`${s.id} injected elements: ${injected.join(', ')}`);
    pass &&= injected.length === 0;
  }
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
  const only = process.env.E2E_ONLY ? process.env.E2E_ONLY.split(',') : null;
  for (const s of SCENARIOS.filter((x) => !only || only.includes(x.id))) {
    const r = await runScenario(page, s);
    if (r.result === 'FAIL' || r.result === 'XPASS') failures++;
    console.log(JSON.stringify(r));
  }
  page.close();
} finally {
  const exited = new Promise((r) => (chrome.exitCode === null ? chrome.once('exit', r) : r()));
  chrome.kill();
  await exited;
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
process.exit(failures ? 1 : 0);
