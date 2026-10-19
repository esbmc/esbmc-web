#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESBMC Homogenizer v2.0 — Motor Universal de Sanitização Simbólica e Geração de Harness (VeriBee).

Desenvolvido para Pesquisa de Mestrado (Orientador: Prof. Dr. Lucas Cordeiro).
Correção de Solidez Formal (Soundness Fix - GitHub Issue #14):
1. NUNCA substitui corpos de funções de usuários por constantes dummy (ex: return 200, return 500).
2. NUNCA restringe domínios de inteiros com suposições artificiais (0 <= val <= 10000).
3. Gera harnesses que invocam as funções e métodos originais sobre entradas não-determinísticas
   totalmente irrestritas (`nondet_int()`), permitindo ao ESBMC/SMT explorar todo o espaço de busca,
   incluindo valores negativos e divisões por zero.
"""

import ast
import argparse
import copy
import os
import subprocess
import sys
from typing import Dict, List, Set, Optional, Tuple


NULLABLE_PRODUCERS = {
    'get_attachment', 'get_by_id', 'get_thumbnail', 'get_feature',
    'get_user', 'get_gate', 'get_stage', 'get_vote'
}

SAFE_RAISE_SERIALIZERS = {
    'to_dict', 'feature_entry_to_json_verbose', 'feature_entry_to_json_basic'
}


def gerar_cabecalho_veribee() -> str:
    """Gera o cabeçalho compatível com ESBMC 8.4.0+ usando intrínsecos simbólicos nativos.
    As funções auxiliares preservam argumentos simbólicos irrestritos sem forçar intervalos artificiais.
    """
    return '''# -*- coding: utf-8 -*-
# Intrínsecos nativos do ESBMC-Python (nondet_int, nondet_bool, __ESBMC_assume)
# NÃO devem ser redefinidos em runtime para preservar a execução simbólica SMT no solver Z3!


def _esbmc_get_int_arg(default_val: int = 0) -> int:
    """Entrada simbólica inteira irrestrita para compatibilidade com handlers."""
    val: int = nondet_int()
    return val


def _esbmc_bounded_int(min_val: int = -1000, max_val: int = 1000) -> int:
    """Entrada simbólica inteira irrestrita."""
    val: int = nondet_int()
    return val


def _esbmc_nullable_entity() -> int:
    """Modela busca no Datastore: 0 = None, 1 = Entidade existente."""
    ent: int = nondet_int()
    __ESBMC_assume(ent == 0 or ent == 1)
    return ent


def _esbmc_safe_div(lhs: int, rhs: int) -> int:
    """Divisão inteira natural preservando verificação de divisão por zero."""
    return lhs // rhs


def _esbmc_safe_mod(lhs: int, rhs: int) -> int:
    """Módulo inteiro natural preservando verificação de divisão por zero."""
    return lhs % rhs


UNIT_TEST_MODE: bool = False
PLAYWRIGHT_MODE: bool = False
'''


# ==============================================================================
# ANÁLISE ESTÁTICA DE INTERVALOS GUIADA POR AST (UFAM / ESBMC RANGE ANALYZER)
# Mantida para telemetria e extração de propriedades sem restringir o harness
# ==============================================================================
class VariableInterval:
    """Modela o intervalo [min_val, max_val] de uma variável com estreitamento de domínio (Domain Narrowing)."""
    def __init__(self, name: str):
        self.name: str = name
        self.min_val: Optional[int] = None
        self.max_val: Optional[int] = None
        self.discrete_set: Set[int] = set()

    def add_lower_bound(self, val: int, inclusive: bool = True):
        bound = val if inclusive else val + 1
        if self.min_val is None or bound > self.min_val:
            self.min_val = bound

    def add_upper_bound(self, val: int, inclusive: bool = True):
        bound = val if inclusive else val - 1
        if self.max_val is None or bound < self.max_val:
            self.max_val = bound

    def get_effective_bounds(self) -> Tuple[int, int]:
        low = self.min_val if self.min_val is not None else -1000
        high = self.max_val if self.max_val is not None else 1000
        if low > high:
            low, high = high, low
        return (low, high)


class ASTIntervalAnalyzer(ast.NodeVisitor):
    """Analisador Estático de Intervalos de Variáveis (Interval Analysis / Domain Narrowing)."""
    def __init__(self, target_vars: Optional[Set[str]] = None):
        self.target_vars: Optional[Set[str]] = target_vars
        self.intervals: Dict[str, VariableInterval] = {}

    def _get_var(self, name: str) -> VariableInterval:
        if name not in self.intervals:
            self.intervals[name] = VariableInterval(name)
        return self.intervals[name]

    def _extract_int_const(self, expr: ast.expr) -> Optional[int]:
        if isinstance(expr, ast.Constant) and isinstance(expr.value, int) and not isinstance(expr.value, bool):
            return expr.value
        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub) and isinstance(expr.operand, ast.Constant) and isinstance(expr.operand.value, int):
            return -expr.operand.value
        return None

    def visit_Compare(self, node: ast.Compare) -> None:
        curr_left = node.left
        for op, right in zip(node.ops, node.comparators):
            self._analyze_binary_comparison(curr_left, op, right)
            curr_left = right
        self.generic_visit(node)

    def _analyze_binary_comparison(self, left: ast.expr, op: ast.cmpop, right: ast.expr) -> None:
        left_name = left.id if isinstance(left, ast.Name) else None
        right_name = right.id if isinstance(right, ast.Name) else None
        left_val = self._extract_int_const(left)
        right_val = self._extract_int_const(right)

        if left_name and right_val is not None:
            v = self._get_var(left_name)
            if isinstance(op, ast.Gt):
                v.add_lower_bound(right_val, inclusive=False)
            elif isinstance(op, ast.GtE):
                v.add_lower_bound(right_val, inclusive=True)
            elif isinstance(op, ast.Lt):
                v.add_upper_bound(right_val, inclusive=False)
            elif isinstance(op, ast.LtE):
                v.add_upper_bound(right_val, inclusive=True)
            elif isinstance(op, ast.Eq):
                v.add_lower_bound(right_val, inclusive=True)
                v.add_upper_bound(right_val, inclusive=True)
        elif right_name and left_val is not None:
            v = self._get_var(right_name)
            if isinstance(op, ast.Lt):
                v.add_lower_bound(left_val, inclusive=False)
            elif isinstance(op, ast.LtE):
                v.add_lower_bound(left_val, inclusive=True)
            elif isinstance(op, ast.Gt):
                v.add_upper_bound(left_val, inclusive=False)
            elif isinstance(op, ast.GtE):
                v.add_upper_bound(left_val, inclusive=True)
            elif isinstance(op, ast.Eq):
                v.add_lower_bound(left_val, inclusive=True)
                v.add_upper_bound(left_val, inclusive=True)


# ==============================================================================
# TRANSFORMADOR AST UNIVERSAL COM SOLIDEZ FORMAL (SOUNDNESS)
# ==============================================================================
class VeriBeeASTTransformer(ast.NodeTransformer):
    """Transformador AST Universal com Solidez Formal (Soundness) para ESBMC-Python.

    Regra Primária (Issue #14): NUNCA substitui corpos de funções originais.
    Preserva a semântica original do código e gera harnesses com argumentos
    não-determinísticos irrestritos (unconstrained nondet_int()), sem range assumes.
    """

    def __init__(self, strict_null: bool = False) -> None:
        super().__init__()
        self.strict_null: bool = strict_null
        self.current_class: Optional[str] = None
        self.current_func: Optional[str] = None
        self.extracted_functions: List[Tuple[str, List[str]]] = []
        self.extracted_classes: List[Tuple[str, List[str], List[Tuple[str, List[str]]]]] = []
        self.all_private_functions: List[Tuple[str, List[str]]] = []
        self.extracted_handlers: List[Tuple[str, str, List[str], bool]] = []
        self.function_intervals: Dict[str, Dict[str, Tuple[int, int]]] = {}
        self.handler_intervals: Dict[Tuple[str, str], Dict[str, Tuple[int, int]]] = {}

    def visit_Module(self, node: ast.Module) -> ast.Module:
        new_body: List[ast.stmt] = []
        for stmt in node.body:
            res = self.visit(stmt)
            if isinstance(res, list):
                new_body.extend(res)
            elif isinstance(res, ast.stmt):
                new_body.append(res)
        node.body = new_body
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        # Extrai nomes de argumentos para geração de harness (excluindo self/cls)
        all_args = list(getattr(node.args, 'posonlyargs', [])) + list(node.args.args) + list(node.args.kwonlyargs)
        arg_names = [a.arg for a in all_args if a.arg not in ('self', 'cls')]

        if self.current_class is None:
            if not node.name.startswith('__'):
                self.extracted_functions.append((node.name, arg_names))
            else:
                self.all_private_functions.append((node.name, arg_names))
        else:
            if not node.name.startswith('__'):
                self.extracted_handlers.append((self.current_class, node.name, arg_names, False))

        # Soundness: PRESERVA 100% DO CORPO DA FUNÇÃO ORIGINAL (Issue #14)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.FunctionDef:
        """Converte async def para def síncrono preservando 100% do corpo original."""
        sync_fn = ast.FunctionDef(
            name=node.name,
            args=node.args,
            body=node.body,
            decorator_list=node.decorator_list,
            returns=node.returns,
            type_comment=getattr(node, 'type_comment', None)
        )
        return self.visit_FunctionDef(sync_fn)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        prev_class = self.current_class
        self.current_class = node.name

        init_args: List[str] = []
        methods: List[Tuple[str, List[str]]] = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_args = list(getattr(item.args, 'posonlyargs', [])) + list(item.args.args) + list(item.args.kwonlyargs)
                m_args = [a.arg for a in all_args if a.arg not in ('self', 'cls')]
                if item.name == '__init__':
                    init_args = m_args
                elif not item.name.startswith('__'):
                    methods.append((item.name, m_args))

        self.extracted_classes.append((node.name, init_args, methods))

        # Visita métodos da classe para converter async def se houver, preservando corpos
        new_class_body: List[ast.stmt] = []
        for item in node.body:
            res = self.visit(item)
            if isinstance(res, list):
                new_class_body.extend(res)
            elif isinstance(res, ast.stmt):
                new_class_body.append(res)
        node.body = new_class_body

        self.current_class = prev_class
        return node


def gerar_harnesses_veribee(transformer: VeriBeeASTTransformer) -> str:
    """Gera o harness de verificação formal chamando as funções e métodos originais
    com argumentos não-determinísticos irrestritos (unconstrained nondet inputs, sem range assumes),
    garantindo a solidez (soundness) da verificação de acordo com o padrão ESBMC."""
    target_functions = transformer.extracted_functions or transformer.all_private_functions
    target_classes = transformer.extracted_classes

    if not target_functions and not target_classes:
        return ""

    lines: List[str] = [
        "",
        "# ==============================================================================",
        "# HARNESS DE VERIFICAÇÃO FORMAL (UNCONSTRAINED SYMBOLIC INPUTS)",
        "# ==============================================================================",
        "def verify_security_contracts() -> None:",
    ]

    has_calls = False

    for func_name, args in target_functions:
        call_arg_names = []
        for a_name in args:
            sym_var = f"sym_{func_name}_{a_name}"
            lines.append(f"    {sym_var}: int = nondet_int()")
            call_arg_names.append(sym_var)
        call_args_str = ", ".join(call_arg_names)
        lines.append(f"    {func_name}({call_args_str})")
        has_calls = True

    for cls_name, init_args, methods in target_classes:
        inst_var = f"inst_{cls_name}"
        init_args_str = []
        for a_name in init_args:
            sym_var = f"sym_init_{cls_name}_{a_name}"
            lines.append(f"    {sym_var}: int = nondet_int()")
            init_args_str.append(sym_var)
        init_call_str = ", ".join(init_args_str)
        lines.append(f"    {inst_var} = {cls_name}({init_call_str})")
        for method_name, m_args in methods:
            call_arg_names = []
            for a_name in m_args:
                sym_var = f"sym_{cls_name}_{method_name}_{a_name}"
                lines.append(f"    {sym_var}: int = nondet_int()")
                call_arg_names.append(sym_var)
            call_args_str = ", ".join(call_arg_names)
            lines.append(f"    {inst_var}.{method_name}({call_args_str})")
            has_calls = True

    if not has_calls:
        return ""

    lines.append("")
    lines.append("verify_security_contracts()")
    lines.append("")
    return "\n".join(lines)


def processar_codigo_fonte_v2(
    codigo_fonte: str,
    nome_origem: str,
    caminho_saida: str,
    strict_null: bool = False
) -> int:
    arvore = ast.parse(codigo_fonte)
    transformer = VeriBeeASTTransformer(strict_null=strict_null)
    arvore_transformada = transformer.visit(arvore)
    ast.fix_missing_locations(arvore_transformada)

    corpo_python = ast.unparse(arvore_transformada)
    cabecalho = gerar_cabecalho_veribee()
    harness = gerar_harnesses_veribee(transformer)

    codigo_final = f"{cabecalho}\n\n{corpo_python}\n{harness}"
    ast.parse(codigo_final)

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write(codigo_final)

    total_targets = len(transformer.extracted_functions or transformer.all_private_functions) + sum(len(m[2]) for m in transformer.extracted_classes)
    print(f"[VeriBee v2.0] Sucesso! {nome_origem} -> {caminho_saida} ({total_targets} alvos simbólicos extraídos)")
    return total_targets


def processar_arquivo_v2(caminho_entrada: str, caminho_saida: str, strict_null: bool = False) -> int:
    caminho_resolvido = resolver_caminho_universal(caminho_entrada)
    with open(caminho_resolvido, 'r', encoding='utf-8') as f:
        codigo_fonte = f.read()
    return processar_codigo_fonte_v2(codigo_fonte, caminho_entrada, caminho_saida, strict_null=strict_null)


def resolver_caminho_universal(caminho: str) -> str:
    """Converte automaticamente caminhos Windows para /mnt/d/... quando executado no WSL."""
    norm = caminho.strip().strip('"').strip("'")
    if os.path.exists(norm):
        return norm
    if os.name != 'nt' and len(norm) >= 3 and norm[1] == ':' and norm[2] in ('\\', '/'):
        drive = norm[0].lower()
        rest = norm[3:].replace('\\', '/')
        wsl_path = f"/mnt/{drive}/{rest}"
        if os.path.exists(wsl_path) or '.zip' in wsl_path.lower():
            return wsl_path
    return norm.replace('\\', '/') if os.name != 'nt' else norm
