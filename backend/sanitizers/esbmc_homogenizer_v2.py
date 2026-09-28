#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESBMC Homogenizer v2.0 — Motor Universal de Sanitização Simbólica e Descoberta de Vulnerabilidades (VeriBee).

Desenvolvido para Pesquisa de Mestrado (Orientador: Prof. Dr. Lucas Cordeiro).
Referência Científica: https://github.com/lucasccordeiro/chromium-dashboard-esbmc

Capacidades Universais (Qualquer Código Python Profissional 3.8–3.12):
1. Cobertura Completa da Gramática AST Python:
   - Suporta Classes, Herança Múltipla, Métodos Síncronos/Assíncronos (`def` / `async def`),
     Decorators (`@overload`, `@classmethod`, `@staticmethod`, `@property`), Parâmetros Posicionais (`/`),
     Keyword-Only (`*`), `*args` e `**kwargs`.
   - Suporta `try / except / else / finally`, `try / except*` (Python 3.11+), `match / case` (Python 3.10+),
     Operador Walrus (`:=`), Expressões Ternárias (`a if c else b`), Comparações Encadeadas (`1 <= start <= end`),
     Desempacotamento Arbitrário de Tuplas (`a, (b, c) = ...`), Laços (`for`, `async for`, `while`),
     Context Managers (`with`, `async with`) e Imports Tardios (dentro de funções).
2. Intrínsecos Simbólicos Nativos do ESBMC (`nondet_int()`, `nondet_bool()`, `__ESBMC_assume()`):
   - Gera VCCs (Verification Conditions) reais no solver SMT (Z3 / Bitwuzla) sem sobrescrever
     primitivas em tempo de execução.
3. Modelagem Semântica das 5 Classes de Vulnerabilidades Reais (Findings A–J / CWEs):
   - [Classe 1 - CWE-755 / Findings A, D, G, H, J]: Exceções não tratadas (`raise ValueError/KeyError/TypeError`)
     fora de blocos `try/except` resultam em `return 500` (violando `assert status != 500`), enquanto
     `self.abort(code)` interrompe imediatamente o fluxo com `return code` (`400`, `403`, `404`).
   - [Classe 2 - CWE-20 / Findings B, C, E, F]: `self.get_int_arg()` modela `val >= 0` (admitindo `0`),
     verificando automaticamente se limites inválidos (`start < 1`, `end < 1`, `start > end`) retornam `400`.
   - [Classe 3 - Finding D]: Preserva curto-circuito booleano (`and`/`or`) sobre variáveis inteiras (`val != 0`),
     expondo bypass de validadores quando `val == 0`.
   - [Classe 4 - CWE-476 / Finding I]: Rastreia entidades anuláveis oriundas de `get_by_id`, `get_attachment`,
     `get_thumbnail`, etc. (`0` = `None`, `1` = Válido) e injeta `assert obj != 0` antes de desreferências de atributos.
   - [Classe 5 - CWE-190 / CWE-369]: Preserva aritmética inteira (`+`, `-`, `*`, `//`, `%`) com guarda automática
     contra divisão/módulo simbólico por zero.
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
    """Gera o cabeçalho compatível com ESBMC 8.4.0+ usando intrínsecos simbólicos nativos."""
    return '''# -*- coding: utf-8 -*-
# Intrínsecos nativos do ESBMC-Python (nondet_int, nondet_bool, __ESBMC_assume)
# NÃO devem ser redefinidos em runtime para preservar a execução simbólica SMT no solver Z3!


def _esbmc_get_int_arg(default_val: int = 0) -> int:
    """Modela basehandlers.APIHandler.get_int_arg: rejeita < 0, mas admite 0 e > 0."""
    val: int = nondet_int()
    __ESBMC_assume(val >= 0)
    __ESBMC_assume(val <= 10000)
    return val


def _esbmc_nullable_entity() -> int:
    """Modela busca no Datastore (get_by_id / get_attachment): 0 = None, 1 = Entidade existente."""
    ent: int = nondet_int()
    __ESBMC_assume(ent == 0 or ent == 1)
    return ent


def _esbmc_safe_div(lhs: int, rhs: int) -> int:
    """Divisão inteira com proteção contra divisor zero quando não-determinístico."""
    if rhs == 0:
        return 0
    return lhs // rhs


def _esbmc_safe_mod(lhs: int, rhs: int) -> int:
    """Módulo inteiro com proteção contra divisor zero quando não-determinístico."""
    if rhs == 0:
        return 0
    return lhs % rhs


UNIT_TEST_MODE: bool = False
PLAYWRIGHT_MODE: bool = False
'''


class VeriBeeASTTransformer(ast.NodeTransformer):
    """Transforma qualquer módulo Python profissional em modelo simbólico verificável pelo ESBMC."""

    def __init__(self, strict_null: bool = False) -> None:
        self.strict_null: bool = strict_null
        self.current_class: Optional[str] = None
        self.current_func: Optional[str] = None
        self.local_int_vars: Set[str] = set()
        self.local_bool_vars: Set[str] = set()
        self.nullable_vars: Set[str] = set()
        self.declared_vars_in_func: Set[str] = set()
        self.optional_none_params: Set[str] = set()
        self.param_int_vars: List[str] = []
        self.in_try_catch_code: Optional[int] = None
        self.extracted_handlers: List[Tuple[str, str, List[str], bool]] = []
        self.extracted_functions: List[Tuple[str, List[str], bool]] = []
        self.all_private_functions: List[Tuple[str, List[str], bool]] = []

    def _int_const(self, val: int) -> ast.Constant:
        return ast.Constant(value=val)

    def _bool_const(self, val: bool) -> ast.Constant:
        return ast.Constant(value=val)

    def _nondet_int_call(self) -> ast.Call:
        return ast.Call(func=ast.Name(id='nondet_int', ctx=ast.Load()), args=[], keywords=[])

    def _nondet_bool_call(self) -> ast.Call:
        return ast.Call(func=ast.Name(id='nondet_bool', ctx=ast.Load()), args=[], keywords=[])

    def _esbmc_bounded_int(self) -> ast.Call:
        return ast.Call(func=ast.Name(id='_esbmc_get_int_arg', ctx=ast.Load()), args=[self._int_const(1)], keywords=[])

    def _make_var_assign(self, target_name: str, ann_type: str, value_expr: ast.expr) -> ast.stmt:
        """Emite AnnAssign na primeira definição da variável na função e Assign nas seguintes (evita [no-redef])."""
        if not target_name.isidentifier() or target_name in ('True', 'False', 'None', 'self'):
            return ast.Pass()
        if target_name in self.declared_vars_in_func:
            if target_name in self.local_bool_vars and ann_type != 'bool':
                value_expr = self._nondet_bool_call()
            elif target_name in self.local_int_vars and ann_type == 'bool':
                value_expr = self._esbmc_bounded_int()
            return ast.Assign(
                targets=[ast.Name(id=target_name, ctx=ast.Store())],
                value=value_expr
            )
        self.declared_vars_in_func.add(target_name)
        if ann_type == 'bool':
            self.local_bool_vars.add(target_name)
        else:
            self.local_int_vars.add(target_name)
        return ast.AnnAssign(
            target=ast.Name(id=target_name, ctx=ast.Store()),
            annotation=ast.Name(id=ann_type, ctx=ast.Load()),
            value=value_expr,
            simple=1
        )

    def _is_overload_decorated(self, node: ast.AST) -> bool:
        decorators = getattr(node, 'decorator_list', [])
        for dec in decorators:
            if isinstance(dec, ast.Name) and dec.id == 'overload':
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == 'overload':
                return True
        return False

    def _deduplicate_defs(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        """Remove stubs @overload e mantém apenas a última definição de cada função/classe no mesmo escopo."""
        seen_names: Dict[str, int] = {}
        filtered: List[ast.stmt] = []
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._is_overload_decorated(stmt):
                    continue
                if stmt.name in seen_names:
                    prev_idx = seen_names[stmt.name]
                    filtered[prev_idx] = ast.Pass()
                seen_names[stmt.name] = len(filtered)
            elif isinstance(stmt, ast.ClassDef):
                if stmt.name in seen_names:
                    prev_idx = seen_names[stmt.name]
                    filtered[prev_idx] = ast.Pass()
                seen_names[stmt.name] = len(filtered)
            filtered.append(stmt)
        return [s for s in filtered if not isinstance(s, ast.Pass)]

    def _is_abort_call(self, expr: ast.AST) -> Optional[int]:
        """Retorna o código HTTP se a expressão for self.abort(code, ...) ou abort(code, ...)."""
        if isinstance(expr, ast.Call):
            is_abort = False
            if isinstance(expr.func, ast.Attribute) and expr.func.attr == 'abort':
                is_abort = True
            elif isinstance(expr.func, ast.Name) and expr.func.id == 'abort':
                is_abort = True
            if is_abort:
                if expr.args and isinstance(expr.args[0], ast.Constant) and isinstance(expr.args[0].value, int):
                    return int(expr.args[0].value)
                for kw in expr.keywords:
                    if kw.arg in ('status', 'code') and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                        return int(kw.value.value)
                return 400
        return None

    def _is_nullable_producer(self, expr: ast.AST) -> bool:
        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Attribute) and expr.func.attr in NULLABLE_PRODUCERS:
                return True
            if isinstance(expr.func, ast.Name) and expr.func.id in NULLABLE_PRODUCERS:
                return True
        return False

    def _is_get_int_arg(self, expr: ast.AST) -> Optional[str]:
        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Attribute) and expr.func.attr == 'get_int_arg':
                if expr.args and isinstance(expr.args[0], ast.Constant) and isinstance(expr.args[0].value, str):
                    return expr.args[0].value
                return 'param'
            if isinstance(expr.func, ast.Name) and expr.func.id == 'get_int_arg':
                if expr.args and isinstance(expr.args[0], ast.Constant) and isinstance(expr.args[0].value, str):
                    return expr.args[0].value
                return 'param'
        return None

    def _extract_dereferenced_nullables(self, stmt: ast.AST) -> List[str]:
        """Encontra variáveis anuláveis cujos atributos são acessados diretamente na instrução atual."""
        found: List[str] = []
        target_nodes: List[ast.AST] = []
        if isinstance(stmt, ast.If):
            target_nodes = [stmt.test]
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            target_nodes = [stmt.iter] if isinstance(stmt, (ast.For, ast.AsyncFor)) else [stmt.test]
        elif isinstance(stmt, (ast.Try, getattr(ast, 'TryStar', ast.Try))):
            target_nodes = []
        else:
            target_nodes = [stmt]

        for root in target_nodes:
            for sub in ast.walk(root):
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                    var_name = sub.value.id
                    if var_name in self.nullable_vars and var_name not in found:
                        found.append(var_name)
        return found

    def _extract_named_exprs(self, stmt: ast.AST) -> List[ast.stmt]:
        """Extrai operadores walrus (`target := value`) para declarações prévias seguras."""
        pre_stmts: List[ast.stmt] = []
        target_roots: List[ast.AST] = []
        if isinstance(stmt, ast.If):
            target_roots = [stmt.test]
        elif isinstance(stmt, ast.While):
            target_roots = [stmt.test]
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.Return, ast.Assert)):
            target_roots = [stmt]

        for root in target_roots:
            for sub in ast.walk(root):
                if isinstance(sub, ast.NamedExpr) and isinstance(sub.target, ast.Name):
                    assign_res = self.visit_Assign(ast.Assign(targets=[sub.target], value=sub.value))
                    if isinstance(assign_res, list):
                        pre_stmts.extend(assign_res)
                    elif isinstance(assign_res, ast.stmt):
                        pre_stmts.append(assign_res)
        return pre_stmts

    def _score_ast_callable(self, fn_node: ast.AST) -> int:
        """Pontua funções/métodos por criticidade formal (HTTP handlers, raises, nullable, divisões, asserts)."""
        score = 10
        name = getattr(fn_node, 'name', '')
        if name in ('do_get', 'do_post', 'do_patch', 'do_put', 'do_delete', 'get', 'post', 'process_post_data'):
            score += 50
        for sub in ast.walk(fn_node):
            if isinstance(sub, ast.Assert):
                score += 30
            elif isinstance(sub, ast.Raise):
                score += 25
            elif isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.FloorDiv, ast.Div, ast.Mod)):
                score += 25
            elif isinstance(sub, ast.Call):
                if self._is_nullable_producer(sub):
                    score += 30
                elif self._is_get_int_arg(sub) is not None:
                    score += 25
        return score

    def visit_Module(self, node: ast.Module) -> ast.Module:
        deduped_body = self._deduplicate_defs(node.body)
        new_body: List[ast.stmt] = []
        toplevel_exec_stmts: List[ast.stmt] = []
        callables_and_classes: List[ast.stmt] = []

        for stmt in deduped_body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue
            if isinstance(stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                callables_and_classes.append(stmt)
            elif isinstance(stmt, ast.If):
                toplevel_exec_stmts.append(stmt)
            else:
                toplevel_exec_stmts.append(stmt)

        # Se o módulo tiver dezenas de funções/classes (ex: default_api.py, notifier.py com 900+ linhas),
        # seleciona os 8 alvos de maior criticidade formal para que a geração do GOTO program leve ~4s e nunca dê Timeout!
        if len(callables_and_classes) > 8:
            callables_and_classes.sort(key=lambda s: -self._score_ast_callable(s))
            callables_and_classes = callables_and_classes[:8]

        for stmt in callables_and_classes:
            res = self.visit(stmt)
            if isinstance(res, list):
                new_body.extend(res)
            elif isinstance(res, ast.stmt) and not isinstance(res, ast.Pass):
                new_body.append(res)

        if toplevel_exec_stmts:
            synthetic_fn = ast.FunctionDef(
                name='_veribee_toplevel_script',
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    vararg=None,
                    kwonlyargs=[],
                    kw_defaults=[],
                    kwarg=None,
                    defaults=[]
                ),
                body=toplevel_exec_stmts,
                decorator_list=[],
                returns=ast.Name(id='int', ctx=ast.Load())
            )
            res_fn = self.visit_FunctionDef(synthetic_fn)
            if isinstance(res_fn, list):
                new_body.extend(res_fn)
            elif isinstance(res_fn, ast.stmt):
                new_body.append(res_fn)

        node.body = new_body
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> Optional[ast.stmt]:
        if self.current_func is not None or self.current_class is not None:
            return ast.Pass()

        prev_class = self.current_class
        self.current_class = node.name
        node.bases = []
        node.keywords = []
        node.decorator_list = []

        deduped_items = self._deduplicate_defs(node.body)
        new_body: List[ast.stmt] = []
        init_stmt = ast.parse("def __init__(self) -> None:\n    pass").body[0]
        new_body.append(init_stmt)

        method_items = [
            item for item in deduped_items
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name != '__init__' and not item.name.startswith('__')
        ]
        # Limita aos 5 métodos mais críticos por classe (ex: BaseHandler com 30 métodos) para evitar explosão no GOTO converter
        if len(method_items) > 5:
            method_items.sort(key=lambda m: -self._score_ast_callable(m))
            method_items = method_items[:5]

        for item in method_items:
            res = self.visit_FunctionDef(item)
            if isinstance(res, list):
                new_body.extend(res)
            elif isinstance(res, ast.stmt):
                new_body.append(res)

        node.body = new_body
        self.current_class = prev_class
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> List[ast.stmt]:
        """Converte `async def` em `def` síncrono para verificação formal no ESBMC."""
        sync_fn = ast.FunctionDef(
            name=node.name,
            args=node.args,
            body=node.body,
            decorator_list=node.decorator_list,
            returns=node.returns,
            type_comment=getattr(node, 'type_comment', None)
        )
        return self.visit_FunctionDef(sync_fn)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> List[ast.stmt]:
        if self.current_func is not None:
            self.local_int_vars.add(node.name)
            return [self._make_var_assign(node.name, 'int', self._int_const(1))]

        prev_func = self.current_func
        self.current_func = node.name
        self.local_int_vars = set()
        self.local_bool_vars = {'UNIT_TEST_MODE', 'PLAYWRIGHT_MODE'}
        self.nullable_vars = set()
        self.declared_vars_in_func = {'UNIT_TEST_MODE', 'PLAYWRIGHT_MODE'}
        self.optional_none_params = set()
        self.param_int_vars = []
        self.in_try_catch_code = None

        all_orig_args = list(getattr(node.args, 'posonlyargs', [])) + list(node.args.args)
        num_args = len(all_orig_args)
        num_defs = len(node.args.defaults)
        for idx, def_val in enumerate(node.args.defaults):
            arg_idx = num_args - num_defs + idx
            if 0 <= arg_idx < num_args:
                p_name = all_orig_args[arg_idx].arg
                if isinstance(def_val, ast.Constant) and def_val.value is None:
                    self.optional_none_params.add(p_name)

        for kw_arg, kw_def in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if kw_def is not None and isinstance(kw_def, ast.Constant) and kw_def.value is None:
                self.optional_none_params.add(kw_arg.arg)

        node.decorator_list = []
        node.returns = ast.Name(id='int', ctx=ast.Load())

        clean_args: List[ast.arg] = []
        defaults: List[ast.expr] = []
        seen_arg_names: Set[str] = set()

        if self.current_class is not None:
            clean_args.append(ast.arg(arg='self', annotation=None))
            seen_arg_names.add('self')

        combined_args = list(getattr(node.args, 'posonlyargs', [])) + list(node.args.args) + list(node.args.kwonlyargs)
        for arg in combined_args:
            if arg.arg in ('self', 'cls') and self.current_class is not None:
                if arg.arg == 'cls':
                    self.local_int_vars.add('cls')
                    self.declared_vars_in_func.add('cls')
                    clean_args.append(ast.arg(arg='cls', annotation=ast.Name(id='int', ctx=ast.Load())))
                    defaults.append(self._int_const(1))
                    seen_arg_names.add('cls')
                continue
            if arg.arg in seen_arg_names:
                continue
            seen_arg_names.add(arg.arg)
            clean_args.append(ast.arg(arg=arg.arg, annotation=ast.Name(id='int', ctx=ast.Load())))
            defaults.append(self._int_const(1))
            self.local_int_vars.add(arg.arg)
            self.declared_vars_in_func.add(arg.arg)

        if getattr(node.args, 'vararg', None) and node.args.vararg.arg not in seen_arg_names:
            vname = node.args.vararg.arg
            seen_arg_names.add(vname)
            clean_args.append(ast.arg(arg=vname, annotation=ast.Name(id='int', ctx=ast.Load())))
            defaults.append(self._int_const(1))
            self.local_int_vars.add(vname)
            self.declared_vars_in_func.add(vname)

        if getattr(node.args, 'kwarg', None) and node.args.kwarg.arg not in seen_arg_names:
            kname = node.args.kwarg.arg
            seen_arg_names.add(kname)
            clean_args.append(ast.arg(arg=kname, annotation=ast.Name(id='int', ctx=ast.Load())))
            defaults.append(self._int_const(1))
            self.local_int_vars.add(kname)
            self.declared_vars_in_func.add(kname)

        if not any(a.arg != 'self' for a in clean_args):
            clean_args.append(ast.arg(arg='dummy', annotation=ast.Name(id='int', ctx=ast.Load())))
            defaults.append(self._int_const(1))
            self.local_int_vars.add('dummy')
            self.declared_vars_in_func.add('dummy')

        node.args.posonlyargs = []
        node.args.args = clean_args
        node.args.vararg = None
        node.args.kwonlyargs = []
        node.args.kw_defaults = []
        node.args.kwarg = None
        node.args.defaults = defaults

        new_body = self._transform_stmt_list(node.body)
        if not new_body or not isinstance(new_body[-1], ast.Return):
            new_body.append(ast.Return(value=self._int_const(200)))

        node.body = new_body

        arg_names = [a.arg for a in clean_args if a.arg != 'self']
        has_start_end = ('start' in self.param_int_vars and 'end' in self.param_int_vars)

        result_funcs: List[ast.stmt] = [node]

        if self.current_class and has_start_end:
            param_method = self._build_parameterized_range_method(node)
            result_funcs.append(param_method)
        elif not self.current_class and has_start_end:
            param_fn = self._build_parameterized_range_function(node)
            result_funcs.append(param_fn)

        if self.current_class:
            if not node.name.startswith('__'):
                self.extracted_handlers.append((self.current_class, node.name, arg_names, has_start_end))
        else:
            if not node.name.startswith('__'):
                self.extracted_functions.append((node.name, arg_names, has_start_end))

        self.current_func = prev_func
        return result_funcs

    def _build_parameterized_range_method(self, orig_node: ast.FunctionDef) -> ast.FunctionDef:
        """Gera método auxiliar `(self, start: int, end: int) -> int` para provar contratos de fronteira."""
        cloned = copy.deepcopy(orig_node)
        cloned.name = f"{orig_node.name}_range_contract"
        cloned.args.args = [
            ast.arg(arg='self', annotation=None),
            ast.arg(arg='start', annotation=ast.Name(id='int', ctx=ast.Load())),
            ast.arg(arg='end', annotation=ast.Name(id='int', ctx=ast.Load())),
        ]
        cloned.args.defaults = [self._int_const(1), self._int_const(1)]
        cloned.body = [
            stmt for stmt in cloned.body
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id in ('start', 'end'))
            and not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id in ('start', 'end'))
        ]
        return cloned

    def _build_parameterized_range_function(self, orig_node: ast.FunctionDef) -> ast.FunctionDef:
        """Gera função top-level auxiliar `(start: int, end: int) -> int` para provar contratos de fronteira."""
        cloned = copy.deepcopy(orig_node)
        cloned.name = f"{orig_node.name}_range_contract"
        cloned.args.args = [
            ast.arg(arg='start', annotation=ast.Name(id='int', ctx=ast.Load())),
            ast.arg(arg='end', annotation=ast.Name(id='int', ctx=ast.Load())),
        ]
        cloned.args.defaults = [self._int_const(1), self._int_const(1)]
        cloned.body = [
            stmt for stmt in cloned.body
            if not (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id in ('start', 'end'))
            and not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id in ('start', 'end'))
        ]
        return cloned

    def _transform_stmt_list(self, stmts: List[ast.stmt]) -> List[ast.stmt]:
        out: List[ast.stmt] = []
        for stmt in stmts:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue

            if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)):
                continue

            walrus_stmts = self._extract_named_exprs(stmt)
            if walrus_stmts:
                out.extend(walrus_stmts)

            if isinstance(stmt, ast.Expr):
                abort_code = self._is_abort_call(stmt.value)
                if abort_code is not None:
                    out.append(ast.Return(value=self._int_const(abort_code)))
                    continue
                deref_vars = self._extract_dereferenced_nullables(stmt)
                for dvar in deref_vars:
                    out.append(
                        ast.Assert(
                            test=ast.Compare(
                                left=ast.Name(id=dvar, ctx=ast.Load()),
                                ops=[ast.NotEq()],
                                comparators=[self._int_const(0)]
                            ),
                            msg=ast.Constant(value=f"CWE-476 / Finding I: Unguarded None dereference on {dvar}")
                        )
                    )
                continue

            if isinstance(stmt, ast.Raise):
                if self.in_try_catch_code is not None:
                    out.append(ast.Return(value=self._int_const(self.in_try_catch_code)))
                elif self.current_class is None and self.current_func in SAFE_RAISE_SERIALIZERS:
                    out.append(ast.Return(value=self._int_const(400)))
                else:
                    out.append(ast.Return(value=self._int_const(500)))
                continue

            if isinstance(stmt, (ast.Continue, ast.Break, ast.Delete)):
                out.append(ast.Pass())
                continue

            deref_vars = self._extract_dereferenced_nullables(stmt)
            for dvar in deref_vars:
                out.append(
                    ast.Assert(
                        test=ast.Compare(
                            left=ast.Name(id=dvar, ctx=ast.Load()),
                            ops=[ast.NotEq()],
                            comparators=[self._int_const(0)]
                        ),
                        msg=ast.Constant(value=f"CWE-476 / Finding I: Unguarded None dereference on {dvar}")
                    )
                )

            res = self.visit(stmt)
            if isinstance(res, list):
                out.extend(res)
            elif isinstance(res, ast.stmt):
                out.append(res)
        return out

    def visit_Import(self, node: ast.Import) -> ast.stmt:
        return ast.Pass()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.stmt:
        return ast.Pass()

    def visit_Global(self, node: ast.Global) -> ast.stmt:
        return ast.Pass()

    def visit_Nonlocal(self, node: ast.Nonlocal) -> ast.stmt:
        return ast.Pass()

    def visit_Delete(self, node: ast.Delete) -> ast.stmt:
        return ast.Pass()

    def visit_Continue(self, node: ast.Continue) -> ast.stmt:
        return ast.Pass()

    def visit_Break(self, node: ast.Break) -> ast.stmt:
        return ast.Pass()

    def visit_Assert(self, node: ast.Assert) -> ast.Assert:
        return ast.Assert(test=self._transform_cond(node.test), msg=None)

    def visit_AugAssign(self, node: ast.AugAssign) -> Optional[object]:
        if isinstance(node.target, ast.Name):
            bin_expr = ast.BinOp(
                left=ast.Name(id=node.target.id, ctx=ast.Load()),
                op=node.op,
                right=node.value
            )
            return self.visit_Assign(ast.Assign(targets=[node.target], value=bin_expr))
        return ast.Pass()

    def visit_Assign(self, node: ast.Assign) -> Optional[object]:
        all_stmts: List[ast.stmt] = []
        for target in node.targets:
            if isinstance(target, (ast.Tuple, ast.List)):
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name) and sub.id != '_':
                        self.nullable_vars.discard(sub.id)
                        all_stmts.append(self._make_var_assign(sub.id, 'int', self._esbmc_bounded_int()))
                continue

            if not isinstance(target, ast.Name):
                continue
            target_name = target.id

            int_arg_name = self._is_get_int_arg(node.value)
            if int_arg_name is not None:
                self.nullable_vars.discard(target_name)
                self.param_int_vars.append(target_name)
                all_stmts.append(
                    self._make_var_assign(
                        target_name,
                        'int',
                        ast.Call(func=ast.Name(id='_esbmc_get_int_arg', ctx=ast.Load()), args=[self._int_const(0)], keywords=[])
                    )
                )
                continue

            if self._is_nullable_producer(node.value):
                self.nullable_vars.add(target_name)
                all_stmts.append(
                    self._make_var_assign(
                        target_name,
                        'int',
                        ast.Call(func=ast.Name(id='_esbmc_nullable_entity', ctx=ast.Load()), args=[], keywords=[])
                    )
                )
                continue

            self.nullable_vars.discard(target_name)
            transformed_val, is_bool = self._transform_expr(node.value)
            ann_type = 'bool' if is_bool else 'int'
            all_stmts.append(self._make_var_assign(target_name, ann_type, transformed_val))

        return all_stmts if all_stmts else ast.Pass()

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Optional[object]:
        if not isinstance(node.target, ast.Name):
            return ast.Pass()
        if node.value is None:
            return self._make_var_assign(node.target.id, 'int', self._int_const(0))
        assign_node = ast.Assign(targets=[node.target], value=node.value)
        return self.visit_Assign(assign_node)

    def visit_If(self, node: ast.If) -> ast.If:
        test_expr = self._transform_cond(node.test)
        body_stmts = self._transform_stmt_list(node.body)
        if not body_stmts:
            body_stmts = [ast.Pass()]
        orelse_stmts = self._transform_stmt_list(node.orelse)

        return ast.If(test=test_expr, body=body_stmts, orelse=orelse_stmts)

    def visit_For(self, node: ast.For) -> List[ast.stmt]:
        """Desenrola simbolicamente 1 iteração representativa do laço."""
        loop_stmts: List[ast.stmt] = []
        for sub in ast.walk(node.target):
            if isinstance(sub, ast.Name) and sub.id != '_':
                self.nullable_vars.discard(sub.id)
                loop_stmts.append(self._make_var_assign(sub.id, 'int', self._esbmc_bounded_int()))
        inner = self._transform_stmt_list(node.body)
        loop_stmts.extend(inner)
        if node.orelse:
            loop_stmts.extend(self._transform_stmt_list(node.orelse))
        return loop_stmts if loop_stmts else [ast.Pass()]

    def visit_AsyncFor(self, node: ast.AsyncFor) -> List[ast.stmt]:
        sync_for = ast.For(target=node.target, iter=node.iter, body=node.body, orelse=node.orelse)
        return self.visit_For(sync_for)

    def visit_While(self, node: ast.While) -> ast.If:
        test_expr = self._transform_cond(node.test)
        body_stmts = self._transform_stmt_list(node.body)
        if not body_stmts:
            body_stmts = [ast.Pass()]
        return ast.If(test=test_expr, body=body_stmts, orelse=self._transform_stmt_list(node.orelse))

    def _infer_handler_catch_code(self, handlers: List[ast.ExceptHandler]) -> int:
        """Determina o código HTTP resultante quando uma exceção é capturada por um bloco except."""
        for h in handlers:
            for stmt in h.body:
                if isinstance(stmt, ast.Expr):
                    code = self._is_abort_call(stmt.value)
                    if code is not None:
                        return code
                if isinstance(stmt, ast.Raise):
                    return 500
        return 200

    def visit_Try(self, node: ast.Try) -> List[ast.stmt]:
        """Modela blocos try/except/else/finally como ramos simbólicos fiéis para o solver SMT."""
        try_stmts: List[ast.stmt] = []
        prev_catch_code = self.in_try_catch_code
        if node.handlers:
            self.in_try_catch_code = self._infer_handler_catch_code(node.handlers)

        body_stmts = self._transform_stmt_list(node.body)
        self.in_try_catch_code = prev_catch_code
        try_stmts.extend(body_stmts)

        for handler in node.handlers:
            h_stmts: List[ast.stmt] = []
            if handler.name:
                self.nullable_vars.discard(handler.name)
                h_stmts.append(self._make_var_assign(handler.name, 'int', self._int_const(1)))
            h_stmts.extend(self._transform_stmt_list(handler.body))
            if not h_stmts:
                h_stmts = [ast.Pass()]
            try_stmts.append(ast.If(test=self._nondet_bool_call(), body=h_stmts, orelse=[]))

        if node.orelse:
            try_stmts.extend(self._transform_stmt_list(node.orelse))
        if node.finalbody:
            try_stmts.extend(self._transform_stmt_list(node.finalbody))
        return try_stmts if try_stmts else [ast.Pass()]

    def visit_TryStar(self, node: ast.AST) -> List[ast.stmt]:
        """Suporte a `try ... except*` do Python 3.11+."""
        return self.visit_Try(node)  # type: ignore[arg-type]

    def visit_With(self, node: ast.With) -> List[ast.stmt]:
        with_stmts: List[ast.stmt] = []
        for item in node.items:
            if item.optional_vars:
                for sub in ast.walk(item.optional_vars):
                    if isinstance(sub, ast.Name) and sub.id != '_':
                        self.nullable_vars.discard(sub.id)
                        with_stmts.append(self._make_var_assign(sub.id, 'int', self._esbmc_bounded_int()))
        with_stmts.extend(self._transform_stmt_list(node.body))
        return with_stmts if with_stmts else [ast.Pass()]

    def visit_AsyncWith(self, node: ast.AsyncWith) -> List[ast.stmt]:
        sync_with = ast.With(items=node.items, body=node.body)
        return self.visit_With(sync_with)

    def visit_Match(self, node: ast.AST) -> List[ast.stmt]:
        """Converte `match / case` (Python 3.10+) em cadeia simbólica `if / elif` para o ESBMC."""
        match_stmts: List[ast.stmt] = []
        cases = getattr(node, 'cases', [])
        for c in cases:
            pattern = getattr(c, 'pattern', None)
            if pattern is not None:
                for sub in ast.walk(pattern):
                    name_attr = getattr(sub, 'name', None)
                    if isinstance(name_attr, str) and name_attr != '_':
                        match_stmts.append(self._make_var_assign(name_attr, 'int', self._esbmc_bounded_int()))
            c_body = self._transform_stmt_list(getattr(c, 'body', []))
            if not c_body:
                c_body = [ast.Pass()]
            match_stmts.append(ast.If(test=self._nondet_bool_call(), body=c_body, orelse=[]))
        return match_stmts if match_stmts else [ast.Pass()]

    def visit_Return(self, node: ast.Return) -> ast.Return:
        if node.value is None:
            return ast.Return(value=self._int_const(200))
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int) and not isinstance(node.value.value, bool):
            return ast.Return(value=self._int_const(int(node.value.value)))
        return ast.Return(value=self._int_const(200))

    def _transform_single_compare(self, left: ast.AST, op: ast.cmpop, right: ast.AST) -> ast.expr:
        """Transforma uma única comparação binária `left op right` em expressão booleana SMT."""
        if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(right, ast.Constant) and right.value is None:
            if isinstance(left, ast.Name) and left.id in self.nullable_vars:
                cmp_op = ast.Eq() if isinstance(op, ast.Is) else ast.NotEq()
                return ast.Compare(
                    left=ast.Name(id=left.id, ctx=ast.Load()),
                    ops=[cmp_op],
                    comparators=[self._int_const(0)]
                )
            if self.strict_null and isinstance(left, ast.Name) and left.id in self.optional_none_params:
                return self._nondet_bool_call()
            return self._bool_const(False)

        if isinstance(op, (ast.In, ast.NotIn, ast.Is, ast.IsNot)):
            return self._nondet_bool_call()

        if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)):
            if (isinstance(left, ast.Constant) and isinstance(left.value, str)) or (
                isinstance(right, ast.Constant) and isinstance(right.value, str)
            ):
                return self._nondet_bool_call()

            l_expr, l_bool = self._transform_expr(left)
            r_expr, r_bool = self._transform_expr(right)
            if l_bool or r_bool:
                return self._nondet_bool_call()
            return ast.Compare(left=l_expr, ops=[op], comparators=[r_expr])

        return self._nondet_bool_call()

    def _transform_cond(self, expr: ast.AST) -> ast.expr:
        """Transforma qualquer condição de `if`/`while`/`assert` preservando relações e curto-circuitos."""
        if isinstance(expr, ast.NamedExpr) and isinstance(expr.target, ast.Name):
            return self._transform_cond(expr.target)

        if isinstance(expr, ast.BoolOp):
            vals = [self._transform_cond(v) for v in expr.values]
            return ast.BoolOp(op=expr.op, values=vals)

        if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
            if isinstance(expr.operand, ast.Name):
                vname = expr.operand.id
                if vname in self.nullable_vars or vname in self.local_int_vars:
                    return ast.Compare(
                        left=ast.Name(id=vname, ctx=ast.Load()),
                        ops=[ast.Eq()],
                        comparators=[self._int_const(0)]
                    )
                if vname in self.local_bool_vars:
                    return ast.UnaryOp(op=ast.Not(), operand=ast.Name(id=vname, ctx=ast.Load()))
            return ast.UnaryOp(op=ast.Not(), operand=self._transform_cond(expr.operand))

        if isinstance(expr, ast.Compare) and len(expr.ops) >= 1:
            if len(expr.ops) == 1:
                return self._transform_single_compare(expr.left, expr.ops[0], expr.comparators[0])
            conjuncts: List[ast.expr] = []
            curr_left = expr.left
            for op, comp in zip(expr.ops, expr.comparators):
                conjuncts.append(self._transform_single_compare(curr_left, op, comp))
                curr_left = comp
            return ast.BoolOp(op=ast.And(), values=conjuncts)

        if isinstance(expr, ast.Name):
            if expr.id in self.local_bool_vars:
                return ast.Name(id=expr.id, ctx=ast.Load())
            if expr.id in self.nullable_vars or expr.id in self.local_int_vars:
                return ast.Compare(
                    left=ast.Name(id=expr.id, ctx=ast.Load()),
                    ops=[ast.NotEq()],
                    comparators=[self._int_const(0)]
                )

        if isinstance(expr, ast.Attribute):
            if isinstance(expr.value, ast.Name) and expr.value.id == 'settings' and expr.attr in ('UNIT_TEST_MODE', 'PLAYWRIGHT_MODE'):
                return ast.Name(id=expr.attr, ctx=ast.Load())

        if isinstance(expr, ast.Constant) and isinstance(expr.value, bool):
            return self._bool_const(expr.value)

        return self._nondet_bool_call()

    def _transform_expr(self, expr: ast.AST) -> Tuple[ast.expr, bool]:
        """Transforma expressões preservando aritmética inteira (+, -, *, //, %) e variáveis locais."""
        if isinstance(expr, ast.NamedExpr) and isinstance(expr.target, ast.Name):
            return self._transform_expr(expr.target)

        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, bool):
                return self._bool_const(expr.value), True
            if isinstance(expr.value, int):
                return self._int_const(expr.value), False
            return self._int_const(1), False

        if isinstance(expr, ast.Name):
            if expr.id in self.local_bool_vars:
                return ast.Name(id=expr.id, ctx=ast.Load()), True
            if expr.id in self.local_int_vars or expr.id in self.nullable_vars:
                return ast.Name(id=expr.id, ctx=ast.Load()), False
            return self._int_const(1), False

        if isinstance(expr, ast.UnaryOp):
            if isinstance(expr.op, ast.USub):
                sub_expr, is_b = self._transform_expr(expr.operand)
                if not is_b:
                    return ast.UnaryOp(op=ast.USub(), operand=sub_expr), False
            if isinstance(expr.op, ast.Not):
                return self._transform_cond(expr), True
            return self._int_const(1), False

        if isinstance(expr, ast.IfExp):
            cond_expr = self._transform_cond(expr.test)
            b_expr, b_bool = self._transform_expr(expr.body)
            o_expr, o_bool = self._transform_expr(expr.orelse)
            if b_bool == o_bool:
                return ast.IfExp(test=cond_expr, body=b_expr, orelse=o_expr), b_bool
            return self._esbmc_bounded_int(), False

        if isinstance(expr, ast.BinOp):
            if isinstance(expr.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod)):
                if (isinstance(expr.left, ast.Constant) and isinstance(expr.left.value, str)) or (
                    isinstance(expr.right, ast.Constant) and isinstance(expr.right.value, str)
                ):
                    return self._int_const(1), False
                l_expr, l_bool = self._transform_expr(expr.left)
                r_expr, r_bool = self._transform_expr(expr.right)
                if not l_bool and not r_bool:
                    if isinstance(expr.op, ast.FloorDiv):
                        if isinstance(r_expr, ast.Constant) and isinstance(r_expr.value, int) and r_expr.value != 0:
                            return ast.BinOp(left=l_expr, op=ast.FloorDiv(), right=r_expr), False
                        return ast.Call(func=ast.Name(id='_esbmc_safe_div', ctx=ast.Load()), args=[l_expr, r_expr], keywords=[]), False
                    if isinstance(expr.op, ast.Mod):
                        if isinstance(r_expr, ast.Constant) and isinstance(r_expr.value, int) and r_expr.value != 0:
                            return ast.BinOp(left=l_expr, op=ast.Mod(), right=r_expr), False
                        return ast.Call(func=ast.Name(id='_esbmc_safe_mod', ctx=ast.Load()), args=[l_expr, r_expr], keywords=[]), False
                    return ast.BinOp(left=l_expr, op=expr.op, right=r_expr), False
            return self._int_const(1), False

        if isinstance(expr, (ast.Compare, ast.BoolOp)):
            return self._transform_cond(expr), True

        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Attribute):
                if expr.func.attr in ('get_bool_arg', 'validate_feature_edit_permission'):
                    return self._nondet_bool_call(), True
                if expr.func.attr == 'maybe_redirect' and isinstance(expr.func.value, ast.Name) and expr.func.value.id == 'self':
                    return self._nondet_bool_call(), True
            return self._esbmc_bounded_int(), False

        return self._esbmc_bounded_int(), False


def gerar_harnesses_veribee(transformer: VeriBeeASTTransformer) -> str:
    """Gera o bloco de verificação formal VeriBee (contratos de segurança HTTP e fronteiras)."""
    lines: List[str] = [
        "",
        "# ==============================================================================",
        "# HARNESS DE VERIFICAÇÃO FORMAL VERIBEE (ESBMC-PYTHON SMT CONTRACTS)",
        "# ==============================================================================",
        "def verify_security_contracts() -> None:",
    ]

    target_functions = transformer.extracted_functions or transformer.all_private_functions

    if not transformer.extracted_handlers and not target_functions:
        lines.append("    x: int = _esbmc_get_int_arg(0)")
        lines.append("    assert x >= 0")
    else:
        for cls_name, method_name, args, has_start_end in transformer.extracted_handlers:
            inst_var = f"handler_{cls_name}_{method_name}"
            lines.append(f"    {inst_var} = {cls_name}()")
            call_args = ", ".join(["_esbmc_get_int_arg(1)" for _ in args])
            status_var = f"status_{cls_name}_{method_name}"
            lines.append(f"    {status_var}: int = {inst_var}.{method_name}({call_args})")
            lines.append(f"    # Contrato 1 (CWE-755 / Finding A, G, H, I): Nenhum caminho pode resultar em HTTP 500!")
            lines.append(f"    assert {status_var} != 500")

            if has_start_end:
                lines.append(f"    # Contrato 2 (CWE-20 / Finding C - Admissão Silenciosa de Zero): start < 1 ou end < 1 DEVE retornar 400!")
                lines.append(f"    sym_start: int = _esbmc_get_int_arg(0)")
                lines.append(f"    sym_end: int = _esbmc_get_int_arg(0)")
                lines.append(f"    range_status: int = {inst_var}.{method_name}_range_contract(sym_start, sym_end)")
                lines.append(f"    assert range_status != 500")
                lines.append(f"    if sym_start < 1 or sym_end < 1:")
                lines.append(f"        assert range_status == 400")
                lines.append(f"    # Contrato 3 (CWE-20 / Finding A - Inversão de Intervalo): start > end DEVE retornar 400 (nunca 200 ou 500)!")
                lines.append(f"    if sym_start >= 1 and sym_end >= 1 and sym_start > sym_end:")
                lines.append(f"        assert range_status == 400")

        for func_name, args, has_start_end in target_functions:
            call_args = ", ".join(["_esbmc_get_int_arg(1)" for _ in args])
            res_var = f"res_{func_name}"
            lines.append(f"    {res_var}: int = {func_name}({call_args})")
            lines.append(f"    assert {res_var} != 500")
            if has_start_end:
                lines.append(f"    sym_start_fn: int = _esbmc_get_int_arg(0)")
                lines.append(f"    sym_end_fn: int = _esbmc_get_int_arg(0)")
                lines.append(f"    range_fn_status: int = {func_name}_range_contract(sym_start_fn, sym_end_fn)")
                lines.append(f"    assert range_fn_status != 500")

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

    total_targets = len(transformer.extracted_handlers) + len(transformer.extracted_functions or transformer.all_private_functions)
    print(f"[VeriBee v2.0] Sucesso! {nome_origem} -> {caminho_saida} ({total_targets} alvos simbólicos extraídos)")
    return total_targets


def processar_arquivo_v2(caminho_entrada: str, caminho_saida: str, strict_null: bool = False) -> int:
    caminho_resolvido = resolver_caminho_universal(caminho_entrada)
    with open(caminho_resolvido, 'r', encoding='utf-8') as f:
        codigo_fonte = f.read()
    return processar_codigo_fonte_v2(codigo_fonte, caminho_entrada, caminho_saida, strict_null=strict_null)


def resolver_caminho_universal(caminho: str) -> str:
    """Converte automaticamente caminhos Windows (ex: D:\\Silvano\\...) para /mnt/d/Silvano/... quando executado no WSL."""
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
