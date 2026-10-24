"""Entry harness for C/C++ modules without main: calls each function with nondet arguments."""
import re
import subprocess

_TIPOS_BASICOS = {'int', 'long', 'short', 'char', 'signed', 'unsigned',
                  'float', 'double', 'bool', '_Bool'}
_TAMANHO_BUFFER = 16


def _tipo(decl: str, padrao: str) -> str:
    tokens = decl.split()
    if (len(tokens) > 1 and tokens[-1] not in _TIPOS_BASICOS
            and tokens[-2] not in ('struct', 'union', 'enum', 'class')):
        tokens = tokens[:-1]
    tipo = ' '.join(tokens)
    return padrao if tipo in ('', 'void', 'auto') else tipo


def declarar_argumento(decl: str, nome: str) -> list:
    """Declare an unconstrained harness argument for parameter `decl`.

    Arguments are left uninitialised, which ESBMC treats as nondet (#39). Pointers get a buffer
    with nondet contents; plain char buffers are null-terminated so string calls stay in bounds.
    """
    decl = re.sub(r'\b(?:const|volatile|register)\b', '', re.sub(r'=.*$', '', decl)).strip()
    if '*' in decl or '[' in decl:
        tipo = _tipo(re.sub(r'[\*\[].*', '', decl).strip(), 'unsigned char')
        linhas = [f"    {tipo} {nome}[{_TAMANHO_BUFFER}];"]
        if tipo == 'char':
            linhas.append(f"    {nome}[{_TAMANHO_BUFFER - 1}] = 0;")
        return linhas
    return [f"    {_tipo(re.sub(r'&.*', '', decl).strip(), 'int')} {nome};"]


def _chamada(idx: int, fn_name: str, params: list) -> list:
    args = [f"_sym_arg_{idx}_{p_idx}" for p_idx in range(len(params))]
    linhas = [linha for decl, nome in zip(params, args) for linha in declarar_argumento(decl, nome)]
    return linhas + [f"    {fn_name}({', '.join(args)});"]


def _linhas_com_erro(origem: str, caminho: str, comando: list) -> set:
    """Lines of `origem` that clang blames for an error, following instantiation notes into it.

    Empty when clang also rejects user code on its own: its headers then differ from ESBMC's
    models, so the harness is left for ESBMC to judge.
    """
    try:
        proc = subprocess.run(comando + [caminho], capture_output=True, text=True,
                              timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return set()
    padrao = re.compile(r'^(.*?):(\d+):\d+: (fatal error|error|warning|note):', re.MULTILINE)
    linhas, pendente = set(), False
    for m in padrao.finditer(proc.stderr):
        no_harness = m.group(1) == origem
        if m.group(3) != 'note':
            if pendente:
                return set()
            pendente = m.group(3) != 'warning' and not no_harness
        if no_harness and (m.group(3) != 'note' or pendente):
            linhas.add(int(m.group(2)))
            pendente = False
    return set() if pendente else linhas


def _escrever(caminho: str, prefixo: str, cabecalho: list, funcoes, ignoradas: list) -> list:
    """Write the module with its harness; returns the function owning each harness line."""
    linhas, donos = list(cabecalho), [None] * len(cabecalho)
    for idx, (fn_name, params) in enumerate(funcoes):
        if fn_name not in ignoradas:
            bloco = _chamada(idx, fn_name, params)
            linhas += bloco
            donos += [fn_name] * len(bloco)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(prefixo + '\n'.join(linhas + ['    return 0;', '}']) + '\n')
    return donos


def montar_harness(caminho: str, codigo: str, funcoes, abertura: list, comando_clang: list):
    """Write `codigo` plus a harness to `caminho`, dropping calls that do not compile.

    Returns the names of the functions left unexercised.
    """
    # A file name of its own keeps harness locations apart from any #line in the user's code.
    origem = caminho + '.harness'
    cabecalho = [f'#line 1 "{origem}"'] + list(abertura)
    prefixo = codigo.rstrip('\n') + '\n\n'
    ignoradas = []
    while True:
        donos = _escrever(caminho, prefixo, cabecalho, funcoes, ignoradas)
        ruins = {donos[n] for n in _linhas_com_erro(origem, caminho, comando_clang)
                 if n < len(donos) and donos[n]}
        if not ruins:
            return ignoradas
        ignoradas += sorted(ruins)
