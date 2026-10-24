"""Entry harness for C/C++ modules without main: calls each root function with nondet arguments."""
import re
import subprocess
from dataclasses import dataclass, field

_TIPOS_BASICOS = {'int', 'long', 'short', 'char', 'signed', 'unsigned',
                  'float', 'double', 'bool', '_Bool'}
_TAMANHO_BUFFER = 16
_ESCOLHA_NULL = 'nondet_harness_null'


def _tipo(decl: str, padrao: str) -> str:
    tokens = decl.split()
    if (len(tokens) > 1 and tokens[-1] not in _TIPOS_BASICOS
            and tokens[-2] not in ('struct', 'union', 'enum', 'class')):
        tokens = tokens[:-1]
    tipo = ' '.join(tokens)
    return padrao if tipo in ('', 'void', 'auto') else tipo


def declarar_argumento(decl: str, nome: str) -> list:
    """Declare an unconstrained harness argument for parameter `decl`.

    Arguments are left uninitialised, which ESBMC treats as nondet (#39). A pointer is NULL or a
    buffer with nondet contents (#46); plain char buffers are null-terminated so string calls stay
    in bounds. A raw nondet pointer would be non-null and invalid, failing guarded code.
    `T a[static N]` must point to N elements (C11 6.7.6.3p7), so it is never NULL.
    """
    decl = re.sub(r'\b(?:const|volatile|register)\b', '', re.sub(r'=.*$', '', decl)).strip()
    if '*' in decl or '[' in decl:
        tipo = _tipo(re.sub(r'[\*\[].*', '', decl).strip(), 'unsigned char')
        buf = f"{nome}_buf"
        linhas = [f"    {tipo} {buf}[{_TAMANHO_BUFFER}];"]
        if tipo == 'char':
            linhas.append(f"    {buf}[{_TAMANHO_BUFFER - 1}] = 0;")
        if re.search(r'\[\s*static\b', decl):
            return linhas + [f"    {tipo} *{nome} = {buf};"]
        return linhas + [f"    {tipo} *{nome} = {_ESCOLHA_NULL}() ? 0 : {buf};"]
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


_NAO_AVALIADOS = {'sizeof', 'alignof', '_Alignof', '__alignof__', 'noexcept', 'decltype',
                  'typeid', 'typeof', '__typeof__', '_Generic', '__builtin_choose_expr',
                  '__builtin_constant_p'}


@dataclass
class GrafoDeChamadas:
    """Direct calls between the module's free functions, read from clang's AST (#46).

    An edge needs a call that resolves to one of the module's own definitions and is evaluated
    whenever the caller's body runs. A function referenced any other way (address taken, called
    in a lambda, local class, default argument, unevaluated operand or discarded `if constexpr`
    branch, or defined more than once) is a forced root, because its calling context is unknown.
    """

    chama: dict = field(default_factory=dict)
    forcadas: set = field(default_factory=set)
    estaticas: set = field(default_factory=set)

    @classmethod
    def ler(cls, caminho: str, codigo: str, args: list, nomes: list):  # pylint: disable=too-many-locals
        """Build the graph; without libclang or an AST every function is a root."""
        grafo = cls()
        try:
            from clang import cindex  # pylint: disable=import-outside-toplevel
            tu = cindex.Index.create().parse(caminho, args=args, unsaved_files=[(caminho, codigo)])
        except Exception:  # pylint: disable=broad-exception-caught
            grafo.forcadas = set(nomes)
            return grafo
        k = cindex.CursorKind
        funcoes = (k.FUNCTION_DECL, k.FUNCTION_TEMPLATE)
        escopos_proprios = (k.LAMBDA_EXPR, k.STRUCT_DECL, k.CLASS_DECL, k.UNION_DECL,
                            k.CLASS_TEMPLATE, k.CXX_METHOD, k.CONSTRUCTOR, k.DESTRUCTOR,
                            k.CXX_UNARY_EXPR, k.GENERIC_SELECTION_EXPR, k.CXX_TYPEID_EXPR)
        do_modulo = list(_declaracoes_do_arquivo(tu.cursor, caminho, k))
        definicoes = [c for c in do_modulo if c.kind in funcoes and c.is_definition()]
        proprias = {c.hash for c in definicoes}
        tokens = _tokens_do_arquivo(tu, caminho)
        nao_avaliado = _trechos_nao_avaliados(tokens)

        def proprio(ref):
            definicao = ref.get_definition() if ref is not None and ref.kind in funcoes else None
            return definicao is not None and definicao.hash in proprias

        def visitar(no, dono, chamadas):
            if dono and (no.kind in escopos_proprios or _if_constexpr(no, tokens, k)
                         or any(a <= no.extent.start.offset < b for a, b in nao_avaliado)):
                dono = None
            if no.kind == k.CALL_EXPR and proprio(no.referenced):
                alvo = next(no.get_children(), None)
                if alvo is not None:
                    chamadas.update(r.hash for r in _refs_do_callee(alvo, k))
                if dono:
                    grafo.chama.setdefault(dono, set()).add(no.referenced.spelling)
                else:
                    grafo.forcadas.add(no.referenced.spelling)
            if no.kind == k.DECL_REF_EXPR and no.hash not in chamadas and proprio(no.referenced):
                grafo.forcadas.add(no.referenced.spelling)
            for filho in no.get_children():
                visitar(filho, dono, chamadas)

        for c in do_modulo:
            if c.hash in proprias:
                if c.storage_class == cindex.StorageClass.STATIC:
                    grafo.estaticas.add(c.spelling)
                for filho in c.get_children():
                    visitar(filho, c.spelling if filho.kind == k.COMPOUND_STMT else None, set())
            else:
                visitar(c, None, set())
        contagem = {}
        for c in definicoes:
            contagem[c.spelling] = contagem.get(c.spelling, 0) + 1
        grafo.forcadas |= {n for n, total in contagem.items() if total > 1}
        return grafo


def _declaracoes_do_arquivo(no, caminho, k):
    for filho in no.get_children():
        if filho.location.file is None or filho.location.file.name != caminho:
            continue
        if filho.kind in (k.NAMESPACE, k.LINKAGE_SPEC, k.UNEXPOSED_DECL):
            yield from _declaracoes_do_arquivo(filho, caminho, k)
        else:
            yield filho


def _tokens_do_arquivo(tu, caminho):
    return [(t.extent.start.offset, t.spelling) for t in tu.get_tokens(extent=tu.cursor.extent)
            if t.location.file is not None and t.location.file.name == caminho]


def _trechos_nao_avaliados(tokens):
    """Offset ranges of operands that are never evaluated (C11 6.5.3.4p2, C++ [expr.context])."""
    trechos = []
    for i, (inicio, texto) in enumerate(tokens):
        if texto not in _NAO_AVALIADOS:
            continue
        nivel, fim = 0, None
        for deslocamento, t in tokens[i + 1:]:
            if t == '(':
                nivel += 1
            elif t == ')':
                nivel -= 1
            elif t == ';' and nivel <= 0:
                fim = deslocamento
            if (t == ')' and nivel == 0) or fim is not None:
                fim = deslocamento
                break
        trechos.append((inicio, fim if fim is not None else float('inf')))
    return trechos


def _refs_do_callee(no, k):
    if no.kind == k.DECL_REF_EXPR:
        return [no]
    if no.kind in (k.UNEXPOSED_EXPR, k.PAREN_EXPR):
        return [r for filho in no.get_children() for r in _refs_do_callee(filho, k)]
    return []


def _if_constexpr(no, tokens, k):
    if no.kind != k.IF_STMT:
        return False
    seguintes = [t for deslocamento, t in tokens if deslocamento > no.extent.start.offset][:1]
    return seguintes == ['constexpr']


def escolher_raizes(nomes: list, grafo: GrafoDeChamadas, excluidas=()):
    """Functions the harness calls directly, and those it leaves unexercised.

    A function called by another one is checked only through its callers, which constrain its
    inputs as the code does (#46). Roots are uncalled non-static functions, forced roots, and
    entry-less call cycles; unreachable static functions are dead code and left out.
    """
    chamados = set().union(*grafo.chama.values()) if grafo.chama else set()
    alcancados = set()

    def alcancar(raiz):
        pendentes = [raiz]
        while pendentes:
            n = pendentes.pop()
            if n not in alcancados:
                alcancados.add(n)
                pendentes.extend(grafo.chama.get(n, ()))

    raizes = []
    for n in nomes:
        livre = n not in chamados and n not in grafo.estaticas
        if n not in excluidas and (n in grafo.forcadas or livre):
            raizes.append(n)
            alcancar(n)
    for n in nomes:
        if n not in alcancados and n not in excluidas and n not in grafo.estaticas:
            raizes.append(n)
            alcancar(n)
    return raizes, [n for n in nomes if n not in alcancados]


def _escrever(caminho: str, prefixo: str, cabecalho: list, funcoes, raizes: list) -> list:
    """Write the module with its harness; returns the function owning each harness line."""
    linhas, donos = list(cabecalho), [None] * len(cabecalho)
    for idx, (fn_name, params) in enumerate(funcoes):
        if fn_name in raizes:
            bloco = _chamada(idx, fn_name, params)
            linhas += bloco
            donos += [fn_name] * len(bloco)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(prefixo + '\n'.join(linhas + ['    return 0;', '}']) + '\n')
    return donos


def montar_harness(caminho: str, codigo: str, funcoes, abertura: list, comando_clang: list) -> dict:
    """Write `codigo` plus a harness to `caminho`, dropping root calls that do not compile.

    Returns the roots called and the functions left unexercised.
    """
    # A file name of its own keeps harness locations apart from any #line in the user's code.
    origem = caminho + '.harness'
    cabecalho = [f'#line 1 "{origem}"', f'int {_ESCOLHA_NULL}(void);'] + list(abertura)
    prefixo = codigo.rstrip('\n') + '\n\n'
    nomes = list(dict.fromkeys(n for n, _ in funcoes))
    grafo = GrafoDeChamadas.ler(caminho, codigo, comando_clang[2:], nomes)
    excluidas = set()
    while True:
        raizes, nao_exercitadas = escolher_raizes(nomes, grafo, excluidas)
        donos = _escrever(caminho, prefixo, cabecalho, funcoes, raizes)
        ruins = {donos[n] for n in _linhas_com_erro(origem, caminho, comando_clang)
                 if n < len(donos) and donos[n]}
        if not ruins:
            return {'raizes': raizes, 'nao_exercitadas': nao_exercitadas}
        excluidas |= ruins
