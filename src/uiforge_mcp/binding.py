"""Safe reactive data binding: canvas variables and expressions driving element properties.

A canvas can hold default ``data`` (e.g. {"hp": 75, "max_hp": 100, "name": "Aria"}) and ``bindings``
([{"target": "hp_bar", "property": "width", "expr": "clamp(hp / max_hp, 0, 1) * 240"}]).
Expressions are validated against a strict AST whitelist (arithmetic, comparisons and pure helpers only).
"""

from __future__ import annotations

import ast
import copy
import math
from functools import lru_cache
from typing import Any

MAX_EXPR = 400
_NODES = (
    ast.Expression, ast.Name, ast.Load, ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Call, ast.IfExp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq,
)

FUNCS: dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": lambda x: math.sqrt(max(0.0, float(x))),
    "clamp": lambda v, lo=0.0, hi=1.0: max(float(lo), min(float(hi), float(v))),
    "mix": lambda a, b, t: float(a) + (float(b) - float(a)) * float(t),
    "lerp": lambda a, b, t: float(a) + (float(b) - float(a)) * float(t),
    "where": lambda cond, a, b: a if cond else b,
    "int": int,
    "float": float,
    "str": str,
    "pct": lambda v, hi=100.0: f"{round(100.0 * float(v) / max(1e-9, float(hi)))}%",
}


@lru_cache(maxsize=256)
def compile_expr(expr: str):
    """Validate and compile a binding expression. Rejects attributes, subscripts, imports and loops."""
    text = str(expr or "").strip()
    if not text:
        raise ValueError("binding expr must be a non-empty expression like 'clamp(hp / max_hp, 0, 1) * 240'")
    if len(text) > MAX_EXPR:
        raise ValueError(f"binding expr is over {MAX_EXPR} characters")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"binding expr syntax error: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _NODES):
            raise ValueError(f"binding expr: '{type(node).__name__}' is not allowed - use plain variables, "
                             "arithmetic, comparisons and helpers like clamp(), where(), round(), pct()")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("binding expr: names cannot start with '_'")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
                raise ValueError(f"binding expr: unknown function. Available: {', '.join(sorted(FUNCS))}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str, bool)):
            raise ValueError("binding expr: only numbers, strings and booleans are allowed")
    return compile(tree, "<binding>", "eval")


def eval_expr(expr: str, data: dict[str, Any]) -> Any:
    """Evaluate a validated binding expression against ``data``."""
    code = compile_expr(expr)
    ns: dict[str, Any] = {"__builtins__": {}}
    ns.update(FUNCS)
    for k, v in (data or {}).items():
        if isinstance(k, str) and k.isidentifier() and not k.startswith("_") and k not in FUNCS:
            ns[k] = v
    try:
        return eval(code, ns)
    except Exception as exc:
        raise ValueError(f"binding expr '{expr}' failed: {exc}") from exc


def _set_nested(el: dict, prop: str, value: Any) -> None:
    parts = prop.split(".")
    node = el
    for i, key in enumerate(parts[:-1]):
        cur = node.get(key)
        if key == "style" and i == 0 and isinstance(cur, str):
            cur = {"use": cur}
        elif not isinstance(cur, dict):
            cur = {"color": cur} if isinstance(cur, str) else {}
        else:
            cur = dict(cur)
        node[key] = cur
        node = cur
    node[parts[-1]] = value


def apply_bindings(canvas: dict, extra_data: dict[str, Any] | None = None) -> dict:
    """Return a copy of ``canvas`` with all data bindings applied (or the same dict if none exist)."""
    bindings = canvas.get("bindings") or []
    base_data = canvas.get("data") or {}
    if not bindings and not extra_data:
        return canvas
    merged = {**base_data, **(extra_data or {})}
    out = copy.deepcopy(canvas)
    if merged:
        out["data"] = merged
    if not bindings:
        return out
    by_id = {e["id"]: e for e in out.get("elements", [])}
    for rule in bindings:
        el = by_id.get(rule.get("target"))
        if el is None:
            continue
        prop = str(rule.get("property", ""))
        expr = str(rule.get("expr", ""))
        if not prop or not expr:
            continue
        val = eval_expr(expr, merged)
        if prop == "opacity":
            _set_nested(el, "style.opacity", max(0.0, min(1.0, float(val))))
        elif prop == "visible":
            el["visible"] = bool(val)
        elif prop == "text":
            el["text"] = str(val)
        elif prop in ("width", "height"):
            el[prop] = max(0.0, float(val))
        else:
            _set_nested(el, prop, val)
    return out


def js_expr(expr: str) -> str:
    """Translate a validated binding expression to a safe JavaScript expression for web/React runtime."""
    tree = ast.parse(str(expr).strip(), mode="eval")

    def emit(n: ast.AST) -> str:
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool):
                return "true" if n.value else "false"
            if isinstance(n.value, str):
                return repr(n.value)
            return repr(float(n.value)) if isinstance(n.value, float) else str(n.value)
        if isinstance(n, ast.Name):
            return f"d[{n.id!r}]"
        if isinstance(n, ast.UnaryOp):
            inner = emit(n.operand)
            if isinstance(n.op, ast.USub):
                return f"(-({inner}))"
            if isinstance(n.op, ast.UAdd):
                return f"(+({inner}))"
            if isinstance(n.op, ast.Not):
                return f"(!({inner}))"
        if isinstance(n, ast.BoolOp):
            op = " && " if isinstance(n.op, ast.And) else " || "
            return "(" + op.join(emit(v) for v in n.values) + ")"
        if isinstance(n, ast.BinOp):
            l, r = emit(n.left), emit(n.right)
            if isinstance(n.op, ast.Pow):
                return f"Math.pow({l},{r})"
            if isinstance(n.op, ast.FloorDiv):
                return f"Math.floor(({l})/({r}))"
            ops = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
            return f"(({l}){ops[type(n.op)]}({r}))"
        if isinstance(n, ast.Compare):
            ops = {ast.Lt: "<", ast.Gt: ">", ast.LtE: "<=", ast.GtE: ">=", ast.Eq: "===", ast.NotEq: "!=="}
            parts = []
            left = emit(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = emit(comp)
                parts.append(f"(({left}){ops[type(op)]}({right}))")
                left = right
            return "(" + " && ".join(parts) + ")"
        if isinstance(n, ast.IfExp):
            return f"(({emit(n.test)})?({emit(n.body)}):({emit(n.orelse)}))"
        if isinstance(n, ast.Call):
            fn = n.func.id
            a = [emit(arg) for arg in n.args]
            if fn in ("min", "max", "abs", "round", "floor", "ceil", "sqrt"):
                return f"Math.{fn}({','.join(a)})"
            if fn == "clamp":
                lo = a[1] if len(a) > 1 else "0"
                hi = a[2] if len(a) > 2 else "1"
                return f"Math.max({lo},Math.min({hi},{a[0]}))"
            if fn in ("mix", "lerp"):
                return f"(({a[0]})+(({a[1]})-({a[0]}))*({a[2]}))"
            if fn == "where":
                return f"(({a[0]})?({a[1]}):({a[2]}))"
            if fn == "int":
                return f"Math.trunc({a[0]})"
            if fn == "float":
                return f"Number({a[0]})"
            if fn == "str":
                return f"String({a[0]})"
            if fn == "pct":
                hi = a[1] if len(a) > 1 else "100"
                return f"(Math.round(100*Number({a[0]})/Math.max(1e-9,Number({hi})))+'%')"
        raise ValueError(f"cannot translate binding expr: {expr}")

    return emit(tree.body)
