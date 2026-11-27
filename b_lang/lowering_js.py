"""Independent JavaScript (Node.js) lowering backend consuming checked BIR.

Demonstrates that B's BIR is genuinely backend-neutral and not a thin Python
code generator. Lowers pure B programs (functions, records, units/currencies,
cases, summarize, ordered history counts, list comprehensions, contracts, and
direct `js:` imports) to standalone executable JavaScript with matching B semantics.
"""
from __future__ import annotations

import json
import keyword
from .history import order_comparison
from .ir import ExprIR, ProgramIR, StmtIR
from .types import BError, FLOAT, INT, is_dim_float


_JS_RESERVED = frozenset({
    "break", "case", "catch", "class", "const", "continue", "debugger", "default",
    "delete", "do", "else", "enum", "export", "extends", "false", "finally", "for",
    "function", "if", "import", "in", "instanceof", "let", "new", "null", "return",
    "super", "switch", "this", "throw", "true", "try", "typeof", "var", "void",
    "while", "with", "yield", "await", "arguments", "eval",
})

_JS_RUNTIME = """\
'use strict';
const fs = require('node:fs');
function _b_mod(a, b) {
  if (b === 0) throw new Error('ZeroDivisionError: division by zero');
  return ((a % b) + b) % b;
}
function _b_div(a, b) {
  if (b === 0) throw new Error('ZeroDivisionError: division by zero');
  return a / b;
}
function _b_add(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) return a.concat(b);
  return a + b;
}
function _b_eq(a, b) {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((v, i) => _b_eq(v, b[i]));
  }
  if (Array.isArray(a) || Array.isArray(b)) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && _b_eq(a[k], b[k]));
}
function _b_cmp(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const c = _b_cmp(a[i], b[i]);
      if (c !== 0) return c;
    }
    return a.length - b.length;
  }
  return a < b ? -1 : a > b ? 1 : 0;
}
function _b_b_len(x) {
  if (typeof x === 'string') return Array.from(x).length;
  if (Array.isArray(x)) return x.length;
  if (x && typeof x === 'object') return Object.keys(x).length;
  throw new Error('len: unsupported type');
}
function _b_b_abs(x) { return Math.abs(x); }
function _b_b_min(a, b) { return a <= b ? a : b; }
function _b_b_max(a, b) { return a >= b ? a : b; }
function _b_b_round_even(x) {
  if (!Number.isFinite(x)) throw new Error('Non-finite Float');
  const f = Math.floor(x);
  const diff = x - f;
  if (diff < 0.5) return f;
  if (diff > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}
function _b_b_round_away(x) {
  if (!Number.isFinite(x)) throw new Error('Non-finite Float');
  return x >= 0 ? Math.floor(x + 0.5) : Math.ceil(x - 0.5);
}
function _b_b_div_euclid(a, b) {
  if (b === 0) throw new Error('ZeroDivisionError');
  let q = Math.floor(a / b);
  const r = a - q * b;
  if (r < 0) q += (b < 0 ? 1 : -1);
  return q;
}
function _b_b_rem_euclid(a, b) { return a - _b_b_div_euclid(a, b) * b; }
function _b_b_rem_trunc(a, b) {
  if (b === 0) throw new Error('ZeroDivisionError');
  return a % b === 0 ? 0 : a % b;
}
function _b_b_scalar(x) { return x; }
function _b_b_to_text(x) {
  if (x === null) return 'none';
  if (typeof x === 'boolean') return x ? 'true' : 'false';
  return String(x);
}
function _b_b_to_float(x) {
  const f = Number(x);
  if (!Number.isFinite(f)) throw new Error('Non-finite Float');
  return f;
}
function _b_b_to_int(x) { return Math.trunc(x); }
function _b_b_stdin_text() { return fs.readFileSync(0, 'utf8'); }
function _b_b_json_encode(x) { return JSON.stringify(x); }
function _b_b_from_json(text) { return JSON.parse(text); }
function _b_b_str_contains(s, sub) { return s.includes(sub); }
function _b_b_str_starts(s, p) { return s.startsWith(p); }
function _b_b_str_ends(s, p) { return s.endsWith(p); }
function _b_b_str_lower(s) { return s.toLowerCase(); }
function _b_b_str_upper(s) { return s.toUpperCase(); }
function _b_b_str_trim(s) { return s.trim(); }
function _b_b_str_split(s, sep) { return s.split(sep); }
function _b_b_str_join(xs, sep) { return xs.join(sep); }
function _b_b_str_replace(s, oldS, newS) { return s.split(oldS).join(newS); }
function _b_print(x) {
  if (x === null) console.log('None');
  else if (typeof x === 'boolean') console.log(x ? 'True' : 'False');
  else if (typeof x === 'string') console.log(x);
  else console.log(JSON.stringify(x));
}
function _b_assert(cond, msg) { if (!cond) throw new Error(msg); }
function _b_guard(val, _t) { return val; }
function _b_record_with(rec, updates) { return Object.assign({}, rec, updates); }
"""


def _js_name(name: str) -> str:
    if name in _JS_RESERVED or keyword.iskeyword(name):
        return "_b_name_" + name
    return name


class JavaScriptLowerer:
    def __init__(self):
        self._tmp = 0

    def _fresh(self, prefix: str) -> str:
        self._tmp += 1
        return f"_b_{prefix}_{self._tmp}"

    def expr(self, e: ExprIR) -> str:
        op, ch, data = e.op, e.operands, e.data
        if op == "literal":
            return json.dumps(data)
        if op == "name":
            return _js_name(data)
        if op == "let_expr":
            b = _js_name(data)
            return f"((({b}) => ({self.expr(ch[1])}))({self.expr(ch[0])}))"
        if op == "list_comp":
            b = _js_name(data)
            src = self.expr(ch[0])
            elt = self.expr(ch[1])
            if len(ch) == 3:
                return f"({src}).filter(({b}) => ({self.expr(ch[2])})).map(({b}) => ({elt}))"
            return f"({src}).map(({b}) => ({elt}))"
        if op == "record_make":
            pairs = ", ".join(f"{json.dumps(f)}: {self.expr(c)}" for f, c in zip(data["fields"], ch))
            return f"({{{pairs}}})"
        if op == "record_field":
            return f"({self.expr(ch[0])})[{json.dumps(data)}]"
        if op == "record_with":
            pairs = ", ".join(f"{json.dumps(f)}: {self.expr(c)}" for f, c in zip(data, ch[1:]))
            return f"_b_record_with({self.expr(ch[0])}, {{{pairs}}})"
        if op == "builtin":
            args = ", ".join(self.expr(c) for c in ch)
            return f"_b_b_{data}({args})"
        if op == "builtin_from_json":
            return f"_b_b_from_json({self.expr(ch[0])})"
        if op == "list":
            return "[" + ", ".join(self.expr(c) for c in ch) + "]"
        if op == "dict":
            items = ", ".join(f"[{self.expr(ch[i])}]: {self.expr(ch[i + 1])}" for i in range(0, len(ch), 2))
            return f"({{{items}}})"
        if op == "lookup":
            obj = self._fresh("obj")
            key = self._fresh("key")
            return f"((({obj}, {key}) => Object.prototype.hasOwnProperty.call({obj}, {key}) ? {obj}[{key}] : null)({self.expr(ch[0])}, {self.expr(ch[1])}))"
        if op == "attr":
            return f"({self.expr(ch[0])})[{json.dumps(data)}]"
        if op == "call":
            fn = self.expr(ch[0])
            args = ", ".join(self.expr(c) for c in ch[1:])
            return f"({fn})({args})"
        if op == "guard":
            return f"_b_guard({self.expr(ch[0])}, {json.dumps(str(e.typ))})"
        if op == "conditional":
            return f"(({self.expr(ch[0])}) ? ({self.expr(ch[1])}) : ({self.expr(ch[2])}))"
        if op == "coalesce":
            tmp = self._fresh("coal")
            return f"((({tmp}) => ({tmp} !== null && {tmp} !== undefined ? {tmp} : ({self.expr(ch[1])})))({self.expr(ch[0])}))"
        if op == "add":
            return f"_b_add({self.expr(ch[0])}, {self.expr(ch[1])})"
        if op == "sub":
            return f"(({self.expr(ch[0])}) - ({self.expr(ch[1])}))"
        if op == "mul":
            return f"(({self.expr(ch[0])}) * ({self.expr(ch[1])}))"
        if op == "div":
            return f"_b_div({self.expr(ch[0])}, {self.expr(ch[1])})"
        if op == "mod":
            return f"_b_mod({self.expr(ch[0])}, {self.expr(ch[1])})"
        if op == "cmp":
            a, b = self.expr(ch[0]), self.expr(ch[1])
            if data == "==":
                return f"_b_eq({a}, {b})"
            if data == "!=":
                return f"(!_b_eq({a}, {b}))"
            return f"(_b_cmp({a}, {b}) {data} 0)"
        if op == "and":
            return f"(({self.expr(ch[0])}) && ({self.expr(ch[1])}))"
        if op == "or":
            return f"(({self.expr(ch[0])}) || ({self.expr(ch[1])}))"
        if op == "not":
            return f"(!({self.expr(ch[0])}))"
        if op == "neg":
            return f"(-({self.expr(ch[0])}))"
        if op == "summarize":
            return self._summarize(e)
        if op == "history_count":
            return self._history_count(e)
        raise BError("E_BACKEND", f"JS backend does not support BIR op: {op}")

    def _summarize(self, e: ExprIR) -> str:
        binder = _js_name(e.data["binder"])
        src = self._fresh("src")
        lines = [f"const {src} = ({self.expr(e.operands[0])}).slice();"]
        loop_lines = []
        result_entries = []
        for idx, (label, reducer, val_idx, guard_idx, default) in enumerate(e.data["fields"]):
            acc = f"_b_acc_{idx}"
            if reducer == "count" and guard_idx is None:
                result_entries.append(f"{json.dumps(label)}: {src}.length")
                continue
            if reducer in ("count", "sum"):
                lines.append(f"let {acc} = 0;")
                term = "1" if reducer == "count" else self.expr(e.operands[val_idx])
                upd = f"{acc} += ({term});"
                result_entries.append(f"{json.dumps(label)}: {acc}")
            elif reducer in ("min", "max"):
                lines.append(f"let {acc} = null;")
                cand = self._fresh("cand")
                cmp_op = "<" if reducer == "min" else ">"
                upd = f"const {cand} = ({self.expr(e.operands[val_idx])}); if ({acc} === null || {cand} {cmp_op} {acc}) {acc} = {cand};"
                result_entries.append(f"{json.dumps(label)}: ({acc} === null ? {json.dumps(default)} : {acc})")
            else:
                raise BError("E_BACKEND", f"Unknown reducer {reducer}")
            if guard_idx is None:
                loop_lines.append(upd)
            else:
                loop_lines.append(f"if ({self.expr(e.operands[guard_idx])}) {{ {upd} }}")
        if loop_lines:
            lines.append(f"for (const {binder} of {src}) {{ " + " ".join(loop_lines) + " }")
        lines.append("return {" + ", ".join(result_entries) + "};")
        return "(() => { " + " ".join(lines) + " })()"

    def _history_count(self, e: ExprIR) -> str:
        src = self._fresh("src")
        hits = self._fresh("hits")
        past = _js_name(e.data["past"])
        cur = _js_name(e.data["current"])
        mode = e.data["mode"]
        pred = self.expr(e.operands[1])
        if mode == "adjacent":
            return (
                f"(() => {{ const {src} = {self.expr(e.operands[0])}; let {hits} = 0; "
                f"for (let _i = 1; _i < {src}.length; _i++) {{ const {past} = {src}[_i - 1]; const {cur} = {src}[_i]; "
                f"if ({pred}) {hits}++; }} return {hits}; }})()"
            )
        return (
            f"(() => {{ const {src} = {self.expr(e.operands[0])}; let {hits} = 0; "
            f"for (let _i = 1; _i < {src}.length; _i++) {{ const {cur} = {src}[_i]; "
            f"for (let _j = 0; _j < _i; _j++) {{ const {past} = {src}[_j]; if ({pred}) {{ {hits}++; break; }} }} }} "
            f"return {hits}; }})()"
        )

    def lower(self, program: ProgramIR) -> str:
        lines = [_JS_RUNTIME]
        for s in program.statements:
            if s.op in ("permit", "foreign", "unit", "currency", "record", "probe", "expect"):
                continue
            if s.op == "import":
                if s.backend != "js":
                    raise BError("E_BACKEND", f"JS backend supports pure B and js: imports directly (got {s.backend}:)")
                lines.append(f"const {_js_name(s.name)} = require({json.dumps(s.target)});")
            elif s.op == "let":
                lines.append(f"const {_js_name(s.name)} = {self.expr(s.expr)};")
            elif s.op == "fn":
                params = ", ".join(_js_name(n) for n, _ in s.params)
                fn_lines = [f"function {_js_name(s.name)}({params}) {{"]
                if s.requires is not None:
                    fn_lines.append(f"  _b_assert({self.expr(s.requires)}, {json.dumps(f'Precondition of {s.name} failed')});")
                fn_lines.append(f"  const result = {self.expr(s.expr)};")
                if s.ensures is not None:
                    fn_lines.append(f"  _b_assert({self.expr(s.ensures)}, {json.dumps(f'Postcondition of {s.name} failed')});")
                fn_lines.append("  return result;")
                fn_lines.append("}")
                lines.append("\n".join(fn_lines))
            elif s.op == "print":
                lines.append(f"_b_print({self.expr(s.expr)});")
            elif s.op == "assert":
                lines.append(f"_b_assert({self.expr(s.expr)}, 'B assertion failed');")
            else:
                raise BError("E_BACKEND", f"JS backend does not support statement: {s.op}")
        return "\n".join(lines) + "\n"
