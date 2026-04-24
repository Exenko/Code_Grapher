"""
TypeScript / JavaScript parser for CodeGrapher.

Handles: .ts  .tsx  .js  .jsx

V1 scope
--------
- Imports (ES module import, require())
- Class definitions + method definitions
- Interface / type alias definitions
- Top-level function definitions (function keyword + const arrow)
- React functional components (const Foo = () => <JSX>)
- Custom hooks (functions whose name starts with 'use')
- Method calls: this.method(), obj.method(), chained
- JSX component usage  →  CALLS edge to the component symbol
- Type annotations on params and return types
- Export tracking (named + default)
- Mutation detection (non-const pointer/ref params) — approximated via
  param naming conventions since TS has no pointer syntax

Out of scope for v1
-------------------
- Generic type parameters beyond the identifier
- Decorators
- Dynamic import()
- Template literal types / conditional / mapped types
"""

import re
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from schema import (
    Node, Edge,
    NodeType, EdgeRelation,
    file_id, symbol_id, type_id,
)
from graph import CodeGraph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUILTIN_TYPES: frozenset = frozenset({
    "string", "number", "boolean", "void", "null", "undefined", "never",
    "any", "unknown", "object", "symbol", "bigint",
    "Array", "Promise", "Record", "Map", "Set", "WeakMap", "WeakSet",
    "Error", "Date", "RegExp", "Function", "Object", "Number", "String",
    "Boolean", "Symbol", "Uint8Array", "Int8Array", "Float32Array",
    "Float64Array", "ArrayBuffer", "ReadonlyArray", "Partial", "Required",
    "Readonly", "NonNullable", "ReturnType", "InstanceType",
    "React", "ReactNode", "ReactElement", "FC", "useEffect", "useState",
    "useRef", "useCallback", "useMemo", "useContext", "useReducer",
    "StyleSheet", "View", "Text", "TouchableOpacity",
})

_CONTROL_SUBSTRINGS: tuple = (
    "config", "option", "setting", "param", "props", "args", "context",
    "theme", "env", "policy",
)

def _is_builtin(name: str) -> bool:
    return name in _BUILTIN_TYPES or name.startswith("__")

def _is_control_type(name: str) -> bool:
    low = name.lower()
    return any(s in low for s in _CONTROL_SUBSTRINGS)

# Raw type names (before generic stripping) that indicate the param is mutated by the callee.
# Ref<T> / MutableRefObject<T> are React refs passed for mutation; Dispatch<T> is a setState
# setter; WritableAtom / MutableAtom are Jotai/Zustand writable atoms.
_MUTABLE_REF_TYPES: frozenset = frozenset({
    "Ref", "MutableRefObject", "RefObject", "Dispatch",
    "WritableAtom", "MutableAtom", "SetStateAction",
})

def _is_mutable_ref_type(raw_annotation: str) -> bool:
    """Return True if the raw type annotation (before generic stripping) is a mutable ref."""
    base = raw_annotation.split('<')[0].strip().lstrip('?')
    return base in _MUTABLE_REF_TYPES

_MUTATING_NAME_RE = re.compile(
    r'^(?:set|update|mutate|dispatch|write|push|append|remove|delete|clear|reset|toggle)'
    r'[A-Z_]',
)

def _is_mutating_param_name(param_name: str) -> bool:
    """Return True if the param name follows a setter/mutator naming convention."""
    return bool(_MUTATING_NAME_RE.match(param_name))

_BODY_MUTATION_RE = re.compile(
    r'\b(\w+)(?:\.[\w.]+)?\s*(?:=(?!=)|\.(?:push|pop|splice|shift|unshift|delete|set|clear|add|remove|append|reset)\s*\(|\+=|-=|\*=|/=|\|=|&=)'
)

def _rel(root: str, filepath: str) -> str:
    try:
        r = os.path.relpath(filepath, root).replace("\\", "/")
        return r
    except ValueError:
        return filepath.replace("\\", "/")

def _stem(filepath: str) -> str:
    return os.path.splitext(os.path.basename(filepath))[0]

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Imports
_RE_IMPORT_FROM   = re.compile(
    r'''import\s+(?:type\s+)?(?:\*\s+as\s+(\w+)|\{([^}]*)\}|(\w+)(?:\s*,\s*\{([^}]*)\})?)\s+from\s+['"]([^'"]+)['"]''')
_RE_IMPORT_SIDE   = re.compile(r'''import\s+['"]([^'"]+)['"]''')
_RE_REQUIRE       = re.compile(r'''(?:const|let|var)\s+(?:\{([^}]*)\}|(\w+))\s*=\s*require\(['"]([^'"]+)['"]\)''')

# Class
_RE_CLASS         = re.compile(
    r'\bclass\s+(\w+)(?:\s+extends\s+([\w.<>, ]+?))?(?:\s+implements\s+[\w,\s<>]+)?\s*\{')
# Method inside class (simplified — handles public/private/protected/static/async/readonly)
_RE_METHOD        = re.compile(
    r'^\s*(?:(?:public|private|protected|static|async|readonly|override|abstract)\s+)*'
    r'(?:get\s+|set\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*([\w<>\[\]|&\s,?.]+?))?\s*(?:\{|;)',
    re.MULTILINE)
# Top-level function declaration
_RE_FUNC_DECL     = re.compile(
    r'^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([\w<>\[\]|&\s,?.]+?))?\s*\{',
    re.MULTILINE)
# Arrow / const function  (MULTILINE so ^ matches line starts)
# Params group is intentionally loose — we extract params separately via brace-aware scan
_RE_ARROW_FUNC    = re.compile(
    r'^(?:export\s+)?(?:default\s+)?(?:const|let)\s+(\w+)\s*(?::\s*(?:React\.FC|FC)\s*<[^>]*>)?\s*=\s*(?:async\s*)?',
    re.MULTILINE)
# Interface / type alias
_RE_INTERFACE     = re.compile(r'\binterface\s+(\w+)')
_RE_TYPE_ALIAS    = re.compile(r'^\s*(?:export\s+)?type\s+(\w+)\s*=', re.MULTILINE)
# Method call:  this.foo(  or  obj.foo(
_RE_METHOD_CALL   = re.compile(r'(\b\w+)\.(\w+)\s*\(')
# Bare call:  foo(  — but not flow keywords
_RE_BARE_CALL     = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
# JSX component tag:  <ComponentName  (capital letter = component)
_RE_JSX_TAG       = re.compile(r'<([A-Z]\w*)\s*[\s/>]')
# Destructured state setter:  const [state, setState] = useState(...)
_RE_USE_STATE     = re.compile(r'const\s+\[(\w+),\s*(\w+)\]\s*=\s*useState')
# Variable type annotation:  const x: MyType = ...
_RE_VAR_ANNOT     = re.compile(r'(?:const|let|var)\s+(\w+)\s*:\s*([\w<>\[\]]+)')
# new ClassName(
_RE_NEW           = re.compile(r'\bnew\s+(\w+)\s*\(')

_FLOW_KEYWORDS: frozenset = frozenset({
    "if", "for", "while", "switch", "catch", "return", "typeof", "instanceof",
    "import", "require", "from", "of", "in", "async", "await", "yield",
    "delete", "void", "throw", "new", "super", "class", "function",
    "const", "let", "var", "export", "default", "true", "false", "null",
    "undefined", "this", "arguments", "console", "Object", "Array",
    "Math", "JSON", "Promise", "setTimeout", "setInterval", "clearTimeout",
    "clearInterval", "parseInt", "parseFloat", "isNaN", "isFinite",
    "encodeURIComponent", "decodeURIComponent", "fetch", "Symbol", "Date",
    "Error", "Map", "Set", "WeakMap", "WeakSet", "Reflect", "Proxy",
    "Buffer",
    # Common prototype / stdlib method names — too generic to resolve meaningfully
    "log", "error", "warn", "info", "debug",        # console.*
    "now", "toFixed", "toString", "valueOf",         # Date.now, Number.toFixed
    "abs", "max", "min", "floor", "ceil", "round",  # Math.*
    "from", "alloc", "concat", "slice", "splice",   # Array/Buffer.*
    "indexOf", "includes", "find", "filter", "map", "reduce", "forEach",
    "push", "pop", "shift", "unshift", "join", "sort", "reverse",
    "split", "trim", "replace", "match", "test",
    "then", "catch", "finally", "resolve", "reject",  # Promise.*
    "assign", "keys", "values", "entries", "freeze",  # Object.*
    "stringify", "parse",                              # JSON.*
    "writeInt32BE", "writeUInt8", "writeUInt16BE", "readUInt8",  # Buffer.*
    "alert", "confirm", "prompt",                      # browser globals
    "create",                                          # Object.create / StyleSheet.create
})

# Stdlib receiver objects — when --no-stdlib-calls is set, method calls whose
# receiver matches one of these are suppressed entirely (no edge emitted).
# Covers JS/TS standard library namespaces that are never user-defined symbols.
_STDLIB_RECEIVERS: frozenset = frozenset({
    "console", "Math", "JSON", "Object", "Array", "Buffer", "Date", "Promise",
    "String", "Number", "Boolean", "Symbol", "Reflect", "Proxy",
    "process", "module", "exports", "require",
    "window", "document", "navigator", "location", "history",  # browser globals
    "React", "ReactDOM",
})

# ---------------------------------------------------------------------------
# Context dataclass
# ---------------------------------------------------------------------------

@dataclass
class _ParseContext:
    feature:     str
    root:        str
    filepath:    str
    rel:         str
    file_node_id: str
    graph:       CodeGraph
    known_symbol_ids: Set[str]
    known_file_ids:   Dict[str, str]
    filter_stdlib:    bool = False

    # symbol tables
    exported_names:  Set[str]               = field(default_factory=set)
    type_names:      Set[str]               = field(default_factory=set)   # interfaces + type aliases
    class_names:     Set[str]               = field(default_factory=set)
    func_names:      Set[str]               = field(default_factory=set)   # top-level functions
    # import alias → module path
    import_alias:    Dict[str, str]          = field(default_factory=dict)
    # import alias → list of named imports from that module
    named_imports:   Dict[str, List[str]]    = field(default_factory=dict)
    # var name → type name (from annotations / new / useState)
    var_types:       Dict[str, str]          = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

class _TSParser:

    def __init__(self, ctx: _ParseContext):
        self.ctx = ctx
        self._source: str = ""

    # ------------------------------------------------------------------
    # public entry
    # ------------------------------------------------------------------

    def parse(self, source: str) -> None:
        self.ctx.graph.add_node(Node(
            id=self.ctx.file_node_id,
            type=NodeType.FILE,
            label=self.ctx.rel,
            file=self.ctx.rel,
            line=0,
            language="typescript",
        ))
        self._source = source
        stripped = self._strip_comments(source)
        self._parse_imports(stripped)
        self._parse_type_defs(stripped)
        self._parse_classes(source, stripped)
        self._parse_top_level_functions(source, stripped)
        self._detect_entry_points(stripped)

    # ------------------------------------------------------------------
    # comment stripping (keep line count intact)
    # ------------------------------------------------------------------

    def _strip_comments(self, src: str) -> str:
        """Remove // and /* */ comments, preserving newlines."""
        result = []
        i = 0
        in_str_single = False
        in_str_double = False
        in_str_template = False
        n = len(src)
        while i < n:
            c = src[i]
            if in_str_single:
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < n:
                        result.append(src[i])
                elif c == "'":
                    in_str_single = False
            elif in_str_double:
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < n:
                        result.append(src[i])
                elif c == '"':
                    in_str_double = False
            elif in_str_template:
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < n:
                        result.append(src[i])
                elif c == '`':
                    in_str_template = False
            elif c == "'" and i + 1 < n and src[i+1] != "'":
                in_str_single = True
                result.append(c)
            elif c == '"' and i + 1 < n and src[i+1] != '"':
                in_str_double = True
                result.append(c)
            elif c == '`':
                in_str_template = True
                result.append(c)
            elif c == '/' and i + 1 < n:
                if src[i+1] == '/':
                    # line comment
                    while i < n and src[i] != '\n':
                        i += 1
                    continue
                elif src[i+1] == '*':
                    i += 2
                    while i < n - 1 and not (src[i] == '*' and src[i+1] == '/'):
                        if src[i] == '\n':
                            result.append('\n')
                        i += 1
                    i += 2  # skip */
                    continue
                else:
                    result.append(c)
            else:
                result.append(c)
            i += 1
        return ''.join(result)

    # ------------------------------------------------------------------
    # imports
    # ------------------------------------------------------------------

    def _parse_imports(self, src: str) -> None:
        ctx = self.ctx
        g   = ctx.graph

        for m in _RE_IMPORT_FROM.finditer(src):
            star_alias, named_block, default_name, extra_named, mod_path = m.groups()
            line = src[:m.start()].count('\n') + 1
            mod_fid = self._resolve_module(mod_path)

            if mod_fid:
                g.add_edge(Edge(
                    from_id=ctx.file_node_id, to_id=mod_fid,
                    relation=EdgeRelation.IMPORTS, unresolved=False,
                ))
            else:
                # external package — still record as unresolved
                ext_id = f"external::{mod_path.lstrip('./')}"
                g.add_edge(Edge(
                    from_id=ctx.file_node_id, to_id=ext_id,
                    relation=EdgeRelation.IMPORTS, unresolved=True,
                ))

            # track aliases for call resolution later
            if star_alias:
                ctx.import_alias[star_alias] = mod_path
            if default_name:
                ctx.import_alias[default_name] = mod_path
            if named_block:
                for raw in named_block.split(','):
                    parts = raw.strip().split()
                    name = parts[-1] if parts else ""
                    if name:
                        ctx.import_alias[name] = mod_path
                        ctx.named_imports.setdefault(mod_path, []).append(name)
            if extra_named:
                for raw in extra_named.split(','):
                    parts = raw.strip().split()
                    name = parts[-1] if parts else ""
                    if name:
                        ctx.import_alias[name] = mod_path

        for m in _RE_REQUIRE.finditer(src):
            named_block, alias, mod_path = m.groups()
            mod_fid = self._resolve_module(mod_path)
            if mod_fid:
                g.add_edge(Edge(
                    from_id=ctx.file_node_id, to_id=mod_fid,
                    relation=EdgeRelation.IMPORTS, unresolved=False,
                ))
            if alias:
                ctx.import_alias[alias] = mod_path
            if named_block:
                for raw in named_block.split(','):
                    name = raw.strip()
                    if name:
                        ctx.import_alias[name] = mod_path

    def _resolve_module(self, mod_path: str) -> Optional[str]:
        """Return file_id for local modules, None for external packages."""
        if not mod_path.startswith('.'):
            return None
        ctx = self.ctx
        # Try various extensions
        base = os.path.normpath(os.path.join(os.path.dirname(ctx.filepath), mod_path))
        for ext in (".ts", ".tsx", ".js", ".jsx", ""):
            candidate = base + ext
            crel = _rel(ctx.root, candidate)
            fid  = file_id(ctx.feature, crel)
            if fid in ctx.known_file_ids.values() or fid in {
                n.id for n in ctx.graph.nodes if n.type == NodeType.FILE
            }:
                return fid
        # fallback: try stem match in known_file_ids
        stem = os.path.basename(base)
        if stem in ctx.known_file_ids:
            return ctx.known_file_ids[stem]
        return None

    # ------------------------------------------------------------------
    # type definitions (interface / type alias)
    # ------------------------------------------------------------------

    def _parse_type_defs(self, src: str) -> None:
        ctx = self.ctx
        g   = ctx.graph
        for m in _RE_INTERFACE.finditer(src):
            name = m.group(1)
            line = src[:m.start()].count('\n') + 1
            nid  = type_id(ctx.feature, _stem(ctx.filepath), name)
            ctx.type_names.add(name)
            g.add_node(Node(
                id=nid, type=NodeType.TYPE, label=name,
                file=ctx.rel, line=line, language="typescript",
            ))
            g.add_edge(Edge(
                from_id=ctx.file_node_id, to_id=nid,
                relation=EdgeRelation.DEFINES,
            ))
        for m in _RE_TYPE_ALIAS.finditer(src):
            name = m.group(1)
            line = src[:m.start()].count('\n') + 1
            nid  = type_id(ctx.feature, _stem(ctx.filepath), name)
            ctx.type_names.add(name)
            g.add_node(Node(
                id=nid, type=NodeType.TYPE, label=name,
                file=ctx.rel, line=line, language="typescript",
            ))
            g.add_edge(Edge(
                from_id=ctx.file_node_id, to_id=nid,
                relation=EdgeRelation.DEFINES,
            ))

    # ------------------------------------------------------------------
    # classes
    # ------------------------------------------------------------------

    def _parse_classes(self, src: str, stripped: str) -> None:
        ctx = self.ctx
        g   = ctx.graph
        for m in _RE_CLASS.finditer(stripped):
            class_name = m.group(1)
            base_name  = m.group(2)
            line       = stripped[:m.start()].count('\n') + 1
            ctx.class_names.add(class_name)

            type_nid = type_id(ctx.feature, _stem(ctx.filepath), class_name)
            g.add_node(Node(
                id=type_nid, type=NodeType.TYPE, label=class_name,
                file=ctx.rel, line=line, language="typescript",
            ))
            g.add_edge(Edge(
                from_id=ctx.file_node_id, to_id=type_nid,
                relation=EdgeRelation.DEFINES,
            ))

            # Extract class body
            body_start = stripped.find('{', m.start())
            if body_start == -1:
                continue
            body, body_end = self._extract_block(stripped, body_start)

            self._parse_class_body(body, class_name, type_nid, line, src)

    def _parse_class_body(self, body: str, class_name: str, class_nid: str,
                          class_line: int, orig_src: str) -> None:
        ctx = self.ctx

        # Build local var types from constructor (for this.x = new Foo() style)
        local_var_types: Dict[str, str] = {}
        ctor_m = re.search(r'\bconstructor\s*\(', body)
        if ctor_m:
            paren_pos = body.find('(', ctor_m.start())
            params_end = self._find_matching_paren(body, paren_pos)
            brace_pos  = body.find('{', params_end)
            if brace_pos != -1:
                ctor_body, _ = self._extract_block(body, brace_pos)
                for vm in _RE_VAR_ANNOT.finditer(ctor_body):
                    local_var_types[vm.group(1)] = vm.group(2)
                for nm in _RE_NEW.finditer(ctor_body):
                    prefix = ctor_body[max(0, nm.start()-40):nm.start()]
                    assign = re.search(r'(?:this\.|const\s+|let\s+|var\s+)(\w+)\s*=\s*$', prefix)
                    if assign:
                        local_var_types[assign.group(1)] = nm.group(1)
            # Emit constructor as a symbol
            ctor_line = class_line + body[:ctor_m.start()].count('\n')
            ctor_body = ""
            if brace_pos != -1:
                ctor_body, _ = self._extract_block(body, brace_pos)
            self._emit_class_method("constructor", class_name, class_nid, "", "", ctor_line, ctor_body)
            if brace_pos != -1 and ctor_body:
                ctor_sym = symbol_id(ctx.feature, ctx.rel, f"{class_name}.constructor")
                self._parse_calls(ctor_body, ctor_sym, local_var_types.copy(), class_name)

        _SKIP_NAMES = frozenset({
            "constructor", "if", "for", "while", "switch", "return",
            "else", "try", "catch", "finally", "class", "new",
            "import", "export", "const", "let", "var", "type",
            "interface", "enum", "namespace", "module", "declare",
            "abstract", "override", "readonly", "get", "set",
        })

        seen_methods: Set[str] = set()

        # Pattern 1: traditional method syntax — methodName(params) { }
        for m in _RE_METHOD.finditer(body):
            mname = m.group(1)
            if mname in _SKIP_NAMES or mname in seen_methods:
                continue
            seen_methods.add(mname)
            params_str  = m.group(2) or ""
            return_type = (m.group(3) or "").strip()
            line = class_line + body[:m.start()].count('\n')

            brace_pos = body.find('{', m.end() - 1)
            method_body = ""
            if brace_pos != -1 and not body[m.end()-1:m.end()].strip() == ';':
                method_body, _ = self._extract_block(body, brace_pos)

            sym_nid = self._emit_class_method(
                mname, class_name, class_nid, params_str, return_type, line, method_body)

            if method_body:
                self._parse_calls(method_body, sym_nid, local_var_types.copy(), class_name)

        # Pattern 2: arrow function class fields — methodName = async (...) => { }
        _RE_ARROW_METHOD = re.compile(
            r'^\s*(?:(?:public|private|protected|static|readonly|override)\s+)*'
            r'(\w+)\s*(?::[^=]+)?\s*=\s*(?:async\s*)?\(',
            re.MULTILINE)
        for m in _RE_ARROW_METHOD.finditer(body):
            mname = m.group(1)
            if mname in _SKIP_NAMES or mname in seen_methods:
                continue
            # Ensure we're at the top level of the class body (depth 0), not
            # inside another method's body — count braces up to match start
            depth = 0
            for ch in body[:m.start()]:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            if depth != 0:
                continue
            # verify it's actually an arrow function (has => after params)
            paren_pos = body.rfind('(', m.start(), m.end())
            params_end = self._find_matching_paren(body, paren_pos)
            after = body[params_end:params_end+30].lstrip()
            # may have return type annotation before =>
            if not re.match(r'(?::\s*[\w<>\[\]|&\s,?.]+\s*)?=>', after):
                continue
            seen_methods.add(mname)
            line = class_line + body[:m.start()].count('\n')
            params_str = body[paren_pos+1:params_end-1] if params_end > paren_pos else ""

            method_body = ""
            # find the arrow body
            arrow_pos = body.find('=>', params_end)
            if arrow_pos != -1:
                after_arrow = body[arrow_pos+2:].lstrip()
                if after_arrow and after_arrow[0] == '{':
                    abs_brace = arrow_pos + 2 + (len(body[arrow_pos+2:]) - len(after_arrow))
                    method_body, _ = self._extract_block(body, abs_brace)

            sym_nid = self._emit_class_method(
                mname, class_name, class_nid, params_str, "", line, method_body)

            if method_body:
                self._parse_calls(method_body, sym_nid, local_var_types.copy(), class_name)

    def _emit_class_method(self, mname: str, class_name: str, class_nid: str,
                           params_str: str, return_type: str, line: int, body: str = "") -> str:
        ctx = self.ctx
        g   = ctx.graph
        sym_nid = symbol_id(ctx.feature, ctx.rel, f"{class_name}.{mname}")
        is_test = "test" in mname.lower() or "spec" in mname.lower() or \
                  "test" in ctx.rel.lower() or "spec" in ctx.rel.lower()
        g.add_node(Node(
            id=sym_nid, type=NodeType.SYMBOL, label=f"{class_name}.{mname}",
            file=ctx.rel, line=line, language="typescript", is_test=is_test,
        ))
        g.add_edge(Edge(from_id=class_nid, to_id=sym_nid, relation=EdgeRelation.DEFINES))
        g.add_edge(Edge(from_id=ctx.file_node_id, to_id=sym_nid, relation=EdgeRelation.CONTAINS))
        self._process_params(params_str, sym_nid, body)
        if return_type and return_type not in ("void", ""):
            clean_rt = re.sub(r'<.*?>', '', return_type).strip()
            if clean_rt and not _is_builtin(clean_rt):
                rt_nid = self._resolve_type_node(clean_rt)
                if rt_nid:
                    g.add_edge(Edge(from_id=sym_nid, to_id=rt_nid, relation=EdgeRelation.PRODUCES))
        return sym_nid

    # ------------------------------------------------------------------
    # top-level functions (function decl + arrow)
    # ------------------------------------------------------------------

    def _parse_top_level_functions(self, src: str, stripped: str) -> None:
        ctx = self.ctx
        g   = ctx.graph

        seen: Set[str] = set()

        # function declarations
        for m in _RE_FUNC_DECL.finditer(stripped):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            params_str  = m.group(2) or ""
            return_type = (m.group(3) or "").strip()
            line = stripped[:m.start()].count('\n') + 1
            ctx.func_names.add(name)

            body = ""
            brace_pos = stripped.find('{', m.end() - 1)
            if brace_pos != -1:
                body, _ = self._extract_block(stripped, brace_pos)

            sym_nid = self._emit_function(name, params_str, return_type, line, body=body)

            if body:
                local_var_types = self._extract_local_var_types(body)
                self._parse_calls(body, sym_nid, local_var_types, "")
                self._parse_jsx(body, sym_nid)

        # arrow / const functions
        # _RE_ARROW_FUNC matches up to the opening ( of params; we extract params
        # with paren-matching to handle destructured props like ({ a, b }) correctly.
        for m in _RE_ARROW_FUNC.finditer(stripped):
            name = m.group(1)
            if name in seen:
                continue

            # The regex ends just before '(' — find and extract params
            rest = stripped[m.end():]
            if not rest.lstrip().startswith('('):
                continue
            paren_abs = m.end() + (len(rest) - len(rest.lstrip()))
            params_end = self._find_matching_paren(stripped, paren_abs)
            params_str = stripped[paren_abs+1:params_end-1]

            # Optional return type annotation before =>
            after_params = stripped[params_end:params_end+60]
            return_type = ""
            rt_m = re.match(r'\s*:\s*([\w<>\[\]|&\s,?.]+?)\s*=>', after_params)
            if rt_m:
                return_type = rt_m.group(1).strip()
                arrow_pos = params_end + after_params.index('=>')
            else:
                arr = after_params.find('=>')
                if arr == -1:
                    continue
                arrow_pos = params_end + arr

            seen.add(name)
            is_component = name[0].isupper()
            line = stripped[:m.start()].count('\n') + 1
            ctx.func_names.add(name)

            # extract arrow body
            after_arrow = stripped[arrow_pos + 2:].lstrip()
            if after_arrow.startswith('{'):
                brace_abs = arrow_pos + 2 + (len(stripped[arrow_pos+2:]) - len(after_arrow))
                body, _ = self._extract_block(stripped, brace_abs)
            elif after_arrow.startswith('('):
                # expression body wrapped in parens (common in JSX returns)
                paren2_abs = arrow_pos + 2 + (len(stripped[arrow_pos+2:]) - len(after_arrow))
                end2 = self._find_matching_paren(stripped, paren2_abs)
                body = stripped[paren2_abs:end2]
            else:
                body = after_arrow[:300]

            # useCallback/useMemo unwrapping: if the outer arrow body is a single
            # hook call, extract the inner function's params and body instead so
            # the symbol gets correct type edges and call edges.
            unwrapped = self._unwrap_hook_body(body)
            if unwrapped is not None:
                inner_params, body = unwrapped
                if inner_params is not None:
                    sym_nid = self._emit_function(name, inner_params, return_type, line,
                                                  is_component=is_component, body=body)
                else:
                    sym_nid = self._emit_function(name, params_str, return_type, line,
                                                  is_component=is_component, body=body)
            else:
                sym_nid = self._emit_function(name, params_str, return_type, line,
                                              is_component=is_component, body=body)

            local_var_types = self._extract_local_var_types(body)
            self._parse_calls(body, sym_nid, local_var_types, "")
            self._parse_jsx(body, sym_nid)

    def _unwrap_hook_body(self, body: str) -> Optional[Tuple[Optional[str], str]]:  # type: ignore
        """If body is `useCallback(innerFn, deps)` or `useMemo(innerFn, deps)`,
        return (inner_params_str_or_None, inner_body_str).
        Returns None if the body is not a hook wrapper."""
        body_stripped = body.strip()
        # Check if the entire body is a hook call (common in arrow bodies that
        # are expression-only, i.e. `const x = useCallback(...)`)
        # Also handle block body: `{ return useCallback(...); }`
        candidate = body_stripped
        # Strip block wrapper: { return ...; } → inner
        block_m = re.match(r'^\{\s*return\s+([\s\S]+?)\s*;?\s*\}$', candidate)
        if block_m:
            candidate = block_m.group(1).strip()

        # Match: hookName(
        hook_m = re.match(r'^(useCallback|useMemo)\s*\(', candidate)
        if not hook_m:
            return None

        # Find the args of the hook call using paren matching on `candidate`
        outer_paren_start = candidate.index('(')
        depth = 0
        outer_paren_end = outer_paren_start
        for i, ch in enumerate(candidate[outer_paren_start:], outer_paren_start):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    outer_paren_end = i
                    break
        # First argument is the inner function; find it
        first_arg = candidate[outer_paren_start + 1:outer_paren_end].lstrip()

        # Inner function can be:
        #   (params): RetType => { body }    ← arrow with block body
        #   (params): RetType => expr         ← arrow with expression body
        #   async (params) => { body }
        inner_m = re.match(
            r'(?:async\s*)?\(([^)]*)\)(?:\s*:\s*[\w<>\[\]|&\s,?.]+?)?\s*=>\s*',
            first_arg,
        )
        if not inner_m:
            return None

        inner_params = inner_m.group(1)
        after_arrow = first_arg[inner_m.end():].lstrip()
        if after_arrow.startswith('{'):
            # block body — extract until matching }
            depth = 0
            end = 0
            for i, ch in enumerate(after_arrow):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            inner_body = after_arrow[1:end]
        else:
            # expression body — take until first comma at depth 0 (the deps array)
            depth = 0
            end = len(after_arrow)
            for i, ch in enumerate(after_arrow):
                if ch in ('(', '[', '{'):
                    depth += 1
                elif ch in (')', ']', '}'):
                    depth -= 1
                elif ch == ',' and depth == 0:
                    end = i
                    break
            inner_body = after_arrow[:end]

        return (inner_params, inner_body)

    def _detect_entry_points(self, stripped: str) -> None:
        """Mark entry point symbols for React Native and common JS patterns."""
        ctx = self.ctx
        g   = ctx.graph

        # Pattern 1: AppRegistry.registerComponent(appName, () => App)
        # The second argument is a factory that returns the root component.
        _RE_REGISTER = re.compile(
            r'AppRegistry\s*\.\s*registerComponent\s*\([^,]+,\s*\(\s*\)\s*=>\s*(\w+)\s*\)')
        for m in _RE_REGISTER.finditer(stripped):
            comp_name = m.group(1)
            # Mark the file itself as an entry point
            for n in g.nodes:
                if n.id == ctx.file_node_id:
                    n.entry_point = True
                    # Store component name in annotation so Pass 2 can mark it
                    n.annotation = f"rn_root::{comp_name}"
                    break
            # Mark the component if already present in the local graph.
            # Cross-file case (e.g. index.js → App.tsx) is handled after
            # merge in run.py via the rn_root:: annotation on the file node.
            suffix = f"::{comp_name}"
            for n in g.nodes:
                if n.type == NodeType.SYMBOL and (
                    n.label == comp_name or n.id.endswith(suffix)
                ):
                    n.entry_point = True

        # Pattern 2: export default function / export default const
        # These are the public surface of a module — treat as entry if file
        # is an index / entry file by name convention.
        entry_filenames = {"index", "main", "App", "app"}
        stem = _stem(ctx.filepath)
        if stem in entry_filenames:
            _RE_DEFAULT_EXPORT = re.compile(
                r'\bexport\s+default\s+(?:function\s+)?(\w+)')
            for m in _RE_DEFAULT_EXPORT.finditer(stripped):
                name = m.group(1)
                if name in ("function", "class", "async"):
                    continue
                suffix = f"::{name}"
                for n in g.nodes:
                    if n.type == NodeType.SYMBOL and (
                        n.label == name or n.id.endswith(suffix)
                    ):
                        n.entry_point = True

    def _emit_function(self, name: str, params_str: str, return_type: str,
                       line: int, is_component: bool = False, body: str = "") -> str:
        ctx = self.ctx
        g   = ctx.graph
        sym_nid = symbol_id(ctx.feature, ctx.rel, name)
        is_test = "test" in name.lower() or "spec" in name.lower() or \
                  "test" in ctx.rel.lower() or "spec" in ctx.rel.lower()
        g.add_node(Node(
            id=sym_nid, type=NodeType.SYMBOL, label=name,
            file=ctx.rel, line=line, language="typescript", is_test=is_test,
        ))
        g.add_edge(Edge(from_id=ctx.file_node_id, to_id=sym_nid, relation=EdgeRelation.DEFINES))
        g.add_edge(Edge(from_id=ctx.file_node_id, to_id=sym_nid, relation=EdgeRelation.CONTAINS))

        if is_component and name[0].isupper():
            type_nid = type_id(ctx.feature, _stem(ctx.filepath), name)
            g.add_node(Node(
                id=type_nid, type=NodeType.TYPE, label=name,
                file=ctx.rel, line=line, language="typescript",
            ))
            g.add_edge(Edge(from_id=ctx.file_node_id, to_id=type_nid, relation=EdgeRelation.DEFINES))

        self._process_params(params_str, sym_nid, body)

        if return_type and return_type not in ("void", ""):
            clean_rt = re.sub(r'<.*?>', '', return_type).strip()
            if clean_rt and not _is_builtin(clean_rt):
                rt_nid = self._resolve_type_node(clean_rt)
                if rt_nid:
                    g.add_edge(Edge(from_id=sym_nid, to_id=rt_nid, relation=EdgeRelation.PRODUCES))

        return sym_nid

    # ------------------------------------------------------------------
    # parameter processing
    # ------------------------------------------------------------------

    def _process_params(self, params_str: str, sym_nid: str, body: str = "") -> None:
        ctx = self.ctx
        g   = ctx.graph
        if not params_str.strip():
            return

        # Detect which params are mutated in the body (if body provided)
        mutated_params: Set[str] = set()
        if body:
            mutated_params = self._detect_body_mutations(body)

        for param in self._split_params(params_str):
            param = param.strip()
            if not param:
                continue
            # destructured: { a, b }: TypeName  or just TypeName
            type_name = None
            raw_annotation = ""
            param_name = ""
            if ':' in param:
                parts = param.split(':', 1)
                param_name = parts[0].strip().lstrip('{').strip()
                raw_annotation = parts[1].strip()
                # strip generics for simple lookup
                clean = re.sub(r'<.*?>', '', raw_annotation).strip().lstrip('?')
                clean = clean.split('[')[0].split('|')[0].strip()
                if clean and not _is_builtin(clean):
                    type_name = clean
            if type_name:
                t_nid = self._resolve_type_node(type_name)
                if t_nid:
                    # Check if mutable via annotation, naming convention, or body mutation
                    is_mutable = (
                        _is_mutable_ref_type(raw_annotation)
                        or _is_mutating_param_name(param_name)
                        or param_name in mutated_params
                    )
                    if is_mutable:
                        g.add_edge(Edge(
                            from_id=sym_nid, to_id=t_nid,
                            relation=EdgeRelation.MODIFIES,
                        ))
                    else:
                        role = "control" if _is_control_type(type_name) else None
                        g.add_edge(Edge(
                            from_id=sym_nid, to_id=t_nid,
                            relation=EdgeRelation.CONSUMES,
                            role=role,
                        ))

    def _split_params(self, params_str: str) -> List[str]:
        """Split params on commas, respecting <> and {} nesting."""
        result = []
        depth_angle = 0
        depth_brace = 0
        depth_paren = 0
        current = []
        for ch in params_str:
            if ch == '<':
                depth_angle += 1
            elif ch == '>':
                depth_angle -= 1
            elif ch == '{':
                depth_brace += 1
            elif ch == '}':
                depth_brace -= 1
            elif ch == '(':
                depth_paren += 1
            elif ch == ')':
                depth_paren -= 1
            elif ch == ',' and depth_angle == 0 and depth_brace == 0 and depth_paren == 0:
                result.append(''.join(current))
                current = []
                continue
            current.append(ch)
        if current:
            result.append(''.join(current))
        return result

    def _detect_body_mutations(self, body: str) -> Set[str]:
        """Scan body for patterns where a parameter is mutated (assigned to or mutating method called).

        Returns set of parameter names that are demonstrably mutated in the body.
        Patterns detected:
        - param.attr = value  (any assignment operator)
        - param.attr += value
        - param.push(...) / pop / splice / etc.

        The regex matches the IMMEDIATE object (before the dot), which could be a property
        of the parameter or the parameter itself. This is intentional: any mutation in the
        chain indicates the root parameter is being modified.
        """
        mutated = set()
        for m in _BODY_MUTATION_RE.finditer(body):
            obj_name = m.group(1)
            mutated.add(obj_name)
        return mutated

    # ------------------------------------------------------------------
    # call parsing
    # ------------------------------------------------------------------

    def _extract_local_var_types(self, body: str) -> Dict[str, str]:
        local: Dict[str, str] = {}
        for m in _RE_VAR_ANNOT.finditer(body):
            local[m.group(1)] = m.group(2)
        for m in _RE_NEW.finditer(body):
            # Try to find assignment: const x = new Foo()
            prefix = body[max(0, m.start()-120):m.start()]
            assign = re.search(r'(?:const|let|var)\s+(\w+)\s*=\s*$', prefix)
            if assign:
                local[assign.group(1)] = m.group(1)
        return local

    def _parse_calls(self, body: str, from_sym_id: str,
                     local_var_types: Dict[str, str],
                     class_name: str) -> None:
        ctx = self.ctx
        g   = ctx.graph

        # Augment local_var_types from body
        local_var_types.update(self._extract_local_var_types(body))

        # Collect useState setter names so calls to them don't generate unresolved edges
        local_setters: Set[str] = set()
        for m in _RE_USE_STATE.finditer(body):
            local_setters.add(m.group(2))  # e.g. setJoystickX

        # obj.method() calls
        for m in _RE_METHOD_CALL.finditer(body):
            obj    = m.group(1)
            method = m.group(2)
            if ctx.filter_stdlib and obj in _STDLIB_RECEIVERS:
                continue
            if obj == "this":
                # this.method() — resolve within class
                target_id = self._resolve_call(
                    f"{class_name}.{method}" if class_name else method,
                    from_sym_id,
                )
                g.add_edge(Edge(
                    from_id=from_sym_id, to_id=target_id[0],
                    relation=EdgeRelation.CALLS,
                    unresolved=target_id[1],
                ))
            else:
                # obj.method() — try to resolve obj's type
                obj_type = local_var_types.get(obj) or ctx.var_types.get(obj)
                if obj_type:
                    target_id = self._resolve_call(f"{obj_type}.{method}", from_sym_id)
                else:
                    target_id = self._resolve_call(method, from_sym_id)
                g.add_edge(Edge(
                    from_id=from_sym_id, to_id=target_id[0],
                    relation=EdgeRelation.CALLS,
                    unresolved=target_id[1],
                ))

        # bare calls
        for m in _RE_BARE_CALL.finditer(body):
            name = m.group(1)
            if name in _FLOW_KEYWORDS or _is_builtin(name) or name in local_setters:
                continue
            # skip if immediately preceded by . (already caught by method call)
            pos = m.start()
            if pos > 0 and body[pos-1] == '.':
                continue
            target_id = self._resolve_call(name, from_sym_id)
            g.add_edge(Edge(
                from_id=from_sym_id, to_id=target_id[0],
                relation=EdgeRelation.CALLS,
                unresolved=target_id[1],
            ))

    def _resolve_call(self, name: str, from_sym_id: str) -> Tuple[str, bool]:  # type: ignore
        """Return (target_id, unresolved)."""
        ctx = self.ctx
        # Try exact match in known symbols
        # same-file first
        same_file_id = symbol_id(ctx.feature, ctx.rel, name)
        if same_file_id in ctx.known_symbol_ids:
            return (same_file_id, False)
        # any known symbol ending with ::name
        # Prefer ClassName.constructor over bare ClassName (which may be a TYPE node)
        ctor_suffix = f"::{name}.constructor"
        for sid in ctx.known_symbol_ids:
            if sid.endswith(ctor_suffix):
                return (sid, False)
        suffix = f"::{name}"
        for sid in ctx.known_symbol_ids:
            if sid.endswith(suffix):
                return (sid, False)
        # fallback: unresolved synthetic id
        unresolved_id = f"unresolved::{name}"
        return (unresolved_id, True)

    # ------------------------------------------------------------------
    # JSX component usage
    # ------------------------------------------------------------------

    def _parse_jsx(self, body: str, from_sym_id: str) -> None:
        ctx = self.ctx
        g   = ctx.graph
        for m in _RE_JSX_TAG.finditer(body):
            comp = m.group(1)
            if comp in ("React", "Fragment"):
                continue
            target_id, unresolved = self._resolve_call(comp, from_sym_id)
            g.add_edge(Edge(
                from_id=from_sym_id, to_id=target_id,
                relation=EdgeRelation.CALLS,
                unresolved=unresolved,
            ))

    # ------------------------------------------------------------------
    # type resolution
    # ------------------------------------------------------------------

    def _resolve_type_node(self, name: str) -> Optional[str]:
        ctx = self.ctx
        if _is_builtin(name):
            return None
        # same-file type
        candidate = type_id(ctx.feature, _stem(ctx.filepath), name)
        # search all known type nodes
        for n in ctx.graph.nodes:
            if n.type == NodeType.TYPE and n.label == name:
                return n.id
        # not found yet — create a forward-declared placeholder
        if name in ctx.type_names or name in ctx.class_names:
            return candidate
        return None

    # ------------------------------------------------------------------
    # block extraction
    # ------------------------------------------------------------------

    def _extract_block(self, src: str, open_brace: int) -> Tuple[str, int]:  # type: ignore
        """Extract content between matching braces starting at open_brace."""
        depth = 0
        i = open_brace
        n = len(src)
        while i < n:
            c = src[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return src[open_brace+1:i], i
            i += 1
        return src[open_brace+1:], n - 1

    def _find_matching_paren(self, src: str, open_paren: int) -> int:
        """Return the index one past the closing ')' matching open_paren."""
        depth = 0
        i = open_paren
        n = len(src)
        while i < n:
            c = src[i]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return n


# ---------------------------------------------------------------------------
# Public API — matches the interface of parser_python.py and parser_cpp.py
# ---------------------------------------------------------------------------

def parse_file(
    feature: str,
    root: Path,
    filepath: Path,
    known_symbol_ids: Optional[Set[str]] = None,
    known_return_types: Optional[Dict[str, str]] = None,
    known_file_ids: Optional[Dict[str, str]] = None,
    filter_stdlib: bool = False,
) -> CodeGraph:
    """Parse a single TypeScript/JavaScript file and return a CodeGraph."""
    if known_symbol_ids is None:
        known_symbol_ids = set()
    if known_file_ids is None:
        known_file_ids = {}

    root_str = str(root)
    filepath_str = str(filepath)
    rel  = _rel(root_str, filepath_str)
    fid  = file_id(feature, rel)
    g    = CodeGraph(feature)

    ctx = _ParseContext(
        feature=feature,
        root=root_str,
        filepath=filepath_str,
        rel=rel,
        file_node_id=fid,
        graph=g,
        known_symbol_ids=known_symbol_ids,
        known_file_ids=known_file_ids,
        filter_stdlib=filter_stdlib,
    )

    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return g

    parser = _TSParser(ctx)
    parser.parse(source)
    return g


def resolve_calls(graph: CodeGraph, known_symbol_ids: Set[str]) -> None:
    """Upgrade unresolved CALLS edges in-place and mark RN entry points (Pass 2)."""
    for edge in graph.edges:
        if edge.relation == EdgeRelation.CALLS and edge.unresolved:
            if edge.to_id.startswith("unresolved::"):
                name = edge.to_id[len("unresolved::"):]
                suffix = f"::{name}"
                for sid in known_symbol_ids:
                    if sid.endswith(suffix):
                        edge.to_id      = sid
                        edge.unresolved = False
                        break

    # Pass 2: mark RN root components as entry_point using full symbol registry.
    # During Pass 1 we stored "rn_root::<ComponentName>" in the file node's
    # annotation field when AppRegistry.registerComponent was detected.
    for node in graph.nodes:
        if node.annotation and node.annotation.startswith("rn_root::"):
            comp_name = node.annotation[len("rn_root::"):]
            suffix = f"::{comp_name}"
            for sid in known_symbol_ids:
                if sid.endswith(suffix):
                    # Mark in this graph if present
                    for n in graph.nodes:
                        if n.id == sid:
                            n.entry_point = True
                    break
