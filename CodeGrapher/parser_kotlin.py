"""
parser_kotlin.py — Regex-based Kotlin file parser for CodeGrapher.

Handles: .kt  .kts

Extracts nodes and edges from a single .kt file:
  - imports       (file → external package or local file)
  - defines       (file → class / interface / object / enum / data class / sealed class)
  - contains      (class → method / function)
  - uses_type     (class → supertype it inherits from or implements)
  - produces      (function → declared return type, non-primitive)
  - consumes      (function → typed parameter, non-mutable)
  - modifies      (function → Collection/mutable typed parameter — heuristic)
  - calls         (function → called symbol, best-effort resolution)

Kotlin-specific constructs handled:
  - data class, sealed class, open class, abstract class, enum class
  - object declarations (singletons) and companion objects
  - Extension functions (fun TypeName.methodName)
  - Nullable types (String? → String)
  - suspend fun, override fun, inline fun
  - Property delegation (val x: T by lazy { ... })
  - when expressions (calls extracted from branches)
  - Anonymous object expressions: object : Interface { }
  - Trailing lambdas (calls extracted)

Pass 1: parse_file() — builds all nodes + locally-resolvable edges.
         Unresolvable calls marked unresolved=True.
Pass 2: resolve_calls() — upgrades unresolved calls using cross-file registry.

Reusable across any Kotlin/Android project.
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from schema import (
    Node, Edge,
    NodeType, EdgeRelation,
    file_id, symbol_id, type_id,
)
from graph import CodeGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel(root: Path, filepath: Path) -> str:
    try:
        return str(filepath.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(filepath).replace("\\", "/")


def _module_name(rel_path: str) -> str:
    return rel_path.replace("/", ".").replace("\\", ".").rsplit(".", 1)[0]


# ---------------------------------------------------------------------------
# Kotlin primitive / stdlib type sets
# ---------------------------------------------------------------------------

_PRIMITIVE_TYPES: frozenset = frozenset({
    "Unit", "Nothing", "Any", "Boolean", "Byte", "Short", "Int", "Long",
    "Float", "Double", "Char", "String", "Number",
    "BooleanArray", "ByteArray", "ShortArray", "IntArray", "LongArray",
    "FloatArray", "DoubleArray", "CharArray",
    "Array", "List", "MutableList", "Set", "MutableSet", "Map", "MutableMap",
    "Collection", "MutableCollection", "Iterable", "MutableIterable",
    "Sequence", "Pair", "Triple",
    "Exception", "RuntimeException", "Throwable", "Error",
    "Function", "Lazy", "Comparator",
    # Android/common
    "Application", "Context", "Intent", "Bundle", "Activity", "Fragment",
    "View", "ViewModel", "LiveData", "Flow", "StateFlow",
})

_STDLIB_RECEIVERS: frozenset = frozenset({
    "println", "print", "TODO", "error", "check", "require",
    "Math", "System", "Thread",
    "listOf", "mutableListOf", "setOf", "mutableSetOf",
    "mapOf", "mutableMapOf", "emptyList", "emptyMap", "emptySet",
    "arrayOf", "arrayListOf",
})

_MUTABLE_TYPE_HINTS: frozenset = frozenset({
    "MutableList", "MutableSet", "MutableMap", "MutableCollection",
    "ArrayList", "HashMap", "HashSet", "LinkedHashMap",
})


def _is_primitive(name: str) -> bool:
    return name in _PRIMITIVE_TYPES or name.startswith("kotlin.") or name.startswith("java.")


def _strip_nullable(type_str: str) -> str:
    """Remove trailing ? from nullable types: String? → String."""
    return type_str.rstrip("?").strip()


def _strip_generics(type_str: str) -> str:
    return re.sub(r'<[^<>]*>', '', type_str).strip()


def _clean_type(type_str: str) -> str:
    t = _strip_nullable(type_str.strip())
    t = _strip_generics(t)
    return t.strip()


# ---------------------------------------------------------------------------
# Comment stripper
# ---------------------------------------------------------------------------

def _strip_comments(source: str) -> str:
    result = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), source, flags=re.DOTALL)
    result = re.sub(r'//[^\n]*', '', result)
    return result


# ---------------------------------------------------------------------------
# Brace-matching body extractor (same as Java parser)
# ---------------------------------------------------------------------------

def _find_body(source: str, open_brace_pos: int) -> Tuple[int, int]:
    depth = 0
    i = open_brace_pos
    while i < len(source):
        c = source[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return open_brace_pos + 1, i
        i += 1
    return open_brace_pos + 1, len(source)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Package declaration
_RE_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)', re.MULTILINE)

# Import statements
_RE_IMPORT = re.compile(r'^\s*import\s+([\w.]+(?:\.\*)?)', re.MULTILINE)

# Type declarations: class, data class, sealed class, open class, abstract class,
# object, companion object, enum class, interface
_RE_TYPE_DECL = re.compile(
    r'(?:^|\n)\s*'
    r'(?:(?:public|private|protected|internal|open|abstract|sealed|data|inner|inline|value|annotation|external|actual|expect)\s+)*'
    r'(class|interface|object|enum\s+class|data\s+class|sealed\s+class|sealed\s+interface|'
    r'abstract\s+class|open\s+class|data\s+object|enum\s+interface)\s+'
    r'(\w+)'
    r'(?:\s*<[^>]*>)?'                           # optional type params
    r'(?:\s*\([^)]*\))?'                         # optional primary constructor params
    r'(?:\s*:\s*([\w<>()\s,?.]+?))?'             # optional supertypes
    r'\s*(?:\{|$)',
    re.MULTILINE,
)

# companion object (no name, or named)
_RE_COMPANION = re.compile(
    r'(?:^|\n)\s*companion\s+object(?:\s+(\w+))?\s*\{',
    re.MULTILINE,
)

# Function declarations:
# [modifiers] fun [<T>] [ReceiverType.]name(params): ReturnType [= expr | { body }]
_RE_FUN = re.compile(
    r'(?:^|\n)\s*'
    r'(?:(?:public|private|protected|internal|open|override|abstract|final|'
    r'suspend|inline|noinline|crossinline|operator|infix|tailrec|external|'
    r'actual|expect)\s+)*'
    r'fun\s+'
    r'(?:<[^>]*>\s+)?'                          # optional generic type params
    r'(?:([\w.<>?]+)\.)?' 		                # optional receiver type (extension fun)
    r'(\w+)\s*'
    r'\(([^)]*)\)'                              # parameter list
    r'(?:\s*:\s*([\w<>\[\]?.]+))?'             # optional return type
    r'\s*(?:[={]|$)',
    re.MULTILINE,
)

# Property declarations (val/var) — for field type tracking
_RE_PROPERTY = re.compile(
    r'(?:^|\n)\s*'
    r'(?:(?:private|protected|public|internal|open|override|abstract|'
    r'lateinit|const|val|var)\s+)*'
    r'(?:val|var)\s+'
    r'(\w+)\s*'
    r'(?::\s*([\w<>?.]+))?'                    # optional type annotation
    r'\s*(?:=|by|$)',
    re.MULTILINE,
)

# Method calls: name(), obj.name(), this.name(), super.name()
_RE_CALL = re.compile(r'(?<!\w)((?:\w+\.)*\w+)\s*\(')

# Object construction: ClassName(...) — in Kotlin, no 'new' keyword
# Heuristic: UpperCamelCase followed by '('
_RE_CONSTRUCT = re.compile(r'(?<!\w)([A-Z]\w+)\s*\(')

# 'object : TypeName' anonymous object expressions
_RE_ANON_OBJECT = re.compile(r'\bobject\s*:\s*([\w.<>, ]+?)\s*\{')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(feature: str, root: Path, filepath: Path,
               known_symbol_ids: Optional[Set[str]] = None,
               known_return_types: Optional[Dict[str, str]] = None,
               known_file_ids: Optional[Dict[str, str]] = None,
               filter_stdlib: bool = False) -> CodeGraph:
    """Parse a single Kotlin file and return a CodeGraph."""
    rel_path = _rel(root, filepath)
    try:
        raw_source = filepath.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return CodeGraph(feature)

    source = _strip_comments(raw_source)
    g = CodeGraph(feature)

    parser = _FileParser(
        feature=feature,
        rel_path=rel_path,
        source=source,
        known_symbol_ids=known_symbol_ids or set(),
        known_file_ids=known_file_ids or {},
        filter_stdlib=filter_stdlib,
        g=g,
    )
    parser.parse()
    return g


def resolve_calls(graph: CodeGraph, known_symbol_ids: Set[str]) -> None:
    """Pass 2 in-place: upgrade unresolved calls where target is now known."""
    for edge in graph.edges:
        if edge.relation == EdgeRelation.CALLS and edge.unresolved:
            if edge.to_id in known_symbol_ids:
                edge.unresolved = False


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

class _FileParser:
    def __init__(self, feature: str, rel_path: str, source: str,
                 known_symbol_ids: Set[str], known_file_ids: Dict[str, str],
                 filter_stdlib: bool, g: CodeGraph):
        self.feature = feature
        self.rel_path = rel_path
        self.source = source
        self.known = known_symbol_ids
        self.known_file_ids = known_file_ids
        self.filter_stdlib = filter_stdlib
        self.g = g

        self.file_node_id = file_id(feature, rel_path)
        self.package_name: str = ""

        # class_name → type_id
        self.class_ids: Dict[str, str] = {}
        # qualified_name → symbol_id
        self.fun_ids: Dict[str, str] = {}
        # class_name → {prop_name: type_name}
        self.prop_types: Dict[str, Dict[str, str]] = {}
        # class_name → list of direct supertype names (for super.method() resolution)
        self.class_supertypes: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------

    def parse(self) -> None:
        source = self.source

        fnode = Node(
            id=self.file_node_id,
            type=NodeType.FILE,
            label=self.rel_path.split("/")[-1],
            file=self.rel_path,
            line=1,
            language="kotlin",
        )
        self.g.add_node(fnode)

        pkg_m = _RE_PACKAGE.search(source)
        self.package_name = pkg_m.group(1) if pkg_m else ""

        self._parse_imports(source)
        self._parse_type_declarations(source)
        # Top-level functions (outside any class)
        self._parse_top_level_functions(source)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _parse_imports(self, source: str) -> None:
        for m in _RE_IMPORT.finditer(source):
            fqn = m.group(1)
            simple = fqn.split(".")[-1]
            if simple == "*":
                pkg = fqn[:-2]
                self.g.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=f"stdlib::{pkg}",
                    relation=EdgeRelation.IMPORTS,
                    unresolved=True,
                ))
                continue
            local_id = self.known_file_ids.get(simple)
            if local_id:
                self.g.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=local_id,
                    relation=EdgeRelation.IMPORTS,
                ))
            else:
                self.g.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=f"stdlib::{fqn}",
                    relation=EdgeRelation.IMPORTS,
                    unresolved=True,
                ))

    # ------------------------------------------------------------------
    # Type declarations
    # ------------------------------------------------------------------

    def _parse_type_declarations(self, source: str) -> None:
        for m in _RE_TYPE_DECL.finditer(source):
            kind_raw = m.group(1).strip()       # "class", "data class", "object", etc.
            class_name = m.group(2).strip()
            supertypes_str = m.group(3) or ""

            line_no = source[:m.start()].count('\n') + 1

            module = self.package_name or _module_name(self.rel_path)
            tid = type_id(self.feature, module, class_name)
            self.class_ids[class_name] = tid

            is_enum = "enum" in kind_raw
            is_object = kind_raw in ("object", "data object")

            tnode = Node(
                id=tid,
                type=NodeType.TYPE,
                label=class_name,
                file=self.rel_path,
                line=line_no,
                language="kotlin",
                is_dataclass=("data" in kind_raw or is_enum),
            )
            self.g.add_node(tnode)

            self.g.add_edge(Edge(
                from_id=self.file_node_id,
                to_id=tid,
                relation=EdgeRelation.DEFINES,
            ))

            # Supertypes → uses_type
            if supertypes_str.strip():
                self._emit_supertypes(tid, class_name, supertypes_str)

            # Find class body
            brace_search_start = m.start()
            brace_pos = source.find('{', brace_search_start)
            if brace_pos == -1:
                continue
            body_start, body_end = _find_body(source, brace_pos)
            body = source[body_start:body_end]
            body_offset = body_start

            # Companion object inside class body
            for cm in _RE_COMPANION.finditer(body):
                companion_name = cm.group(1) or "Companion"
                comp_line = source[:body_offset + cm.start()].count('\n') + 1
                comp_qual = f"{class_name}.{companion_name}"
                comp_sid = symbol_id(self.feature, self.rel_path, comp_qual)
                comp_node = Node(
                    id=comp_sid,
                    type=NodeType.SYMBOL,
                    label=comp_qual,
                    file=self.rel_path,
                    line=comp_line,
                    language="kotlin",
                )
                self.g.add_node(comp_node)
                self.g.add_edge(Edge(from_id=tid, to_id=comp_sid, relation=EdgeRelation.CONTAINS))
                self.g.add_edge(Edge(from_id=self.file_node_id, to_id=comp_sid, relation=EdgeRelation.DEFINES))
                self.fun_ids[comp_qual] = comp_sid

                # Parse companion body
                comp_brace = body.find('{', cm.start())
                if comp_brace != -1:
                    cb_start, cb_end = _find_body(body, comp_brace)
                    comp_body = body[cb_start:cb_end]
                    self._parse_funs_in_body(comp_body, body_offset + cb_start, class_name, tid)

            # Properties (for receiver type tracking)
            prop_map: Dict[str, str] = {}
            for pm in _RE_PROPERTY.finditer(body):
                pname = pm.group(1)
                ptype_raw = pm.group(2) or ""
                ptype = _clean_type(ptype_raw)
                if ptype and not _is_primitive(ptype) and pname not in ("val", "var"):
                    prop_map[pname] = ptype
            self.prop_types[class_name] = prop_map

            # Functions inside class body
            self._parse_funs_in_body(body, body_offset, class_name, tid)

    # ------------------------------------------------------------------
    # Top-level functions
    # ------------------------------------------------------------------

    def _parse_top_level_functions(self, source: str) -> None:
        """Parse functions not inside any class body."""
        # We approximate by scanning for fun declarations that appear before
        # any class opening brace or after all class closing braces.
        # Simpler: scan all fun matches and skip those inside class bodies.
        class_ranges: List[Tuple[int, int]] = []
        for m in _RE_TYPE_DECL.finditer(source):
            bp = source.find('{', m.start())
            if bp != -1:
                bs, be = _find_body(source, bp)
                class_ranges.append((bp, be))

        def _in_class(pos: int) -> bool:
            return any(s <= pos <= e for s, e in class_ranges)

        for m in _RE_FUN.finditer(source):
            if _in_class(m.start()):
                continue
            receiver = m.group(1)    # extension receiver, or None
            fun_name = m.group(2)
            params_raw = m.group(3) or ""
            ret_type_raw = m.group(4) or ""

            if fun_name in ("main",):
                pass  # keep

            line_no = source[:m.start()].count('\n') + 1
            qual = f"{receiver}.{fun_name}" if receiver else fun_name
            sid = symbol_id(self.feature, self.rel_path, qual)
            self.fun_ids[qual] = sid

            is_main = fun_name == "main"
            snode = Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=qual,
                file=self.rel_path,
                line=line_no,
                language="kotlin",
                entry_point=is_main,
            )
            self.g.add_node(snode)
            self.g.add_edge(Edge(from_id=self.file_node_id, to_id=sid, relation=EdgeRelation.DEFINES))

            self._emit_return_type(sid, ret_type_raw)
            self._emit_params(sid, params_raw, None)

            # Body
            brace_pos = source.find('{', m.start())
            if brace_pos != -1 and not _in_class(brace_pos) and brace_pos < m.start() + 200:
                fb_start, fb_end = _find_body(source, brace_pos)
                fun_body = source[fb_start:fb_end]
                self._parse_calls_in_body(fun_body, sid, receiver or "", {})

    # ------------------------------------------------------------------
    # Functions inside a class body
    # ------------------------------------------------------------------

    def _parse_funs_in_body(self, body: str, body_offset: int,
                             class_name: str, class_tid: str) -> None:
        prop_map = self.prop_types.get(class_name, {})
        seen: Dict[str, int] = {}

        for m in _RE_FUN.finditer(body):
            receiver = m.group(1)
            fun_name = m.group(2)
            params_raw = m.group(3) or ""
            ret_type_raw = m.group(4) or ""

            if fun_name in ("if", "for", "while", "when", "catch", "try"):
                continue

            qual = f"{class_name}.{fun_name}"
            count = seen.get(qual, 0)
            seen[qual] = count + 1
            sym_name = f"{qual}_{count}" if count > 0 else qual

            line_no = self.source[:body_offset + m.start()].count('\n') + 1
            sid = symbol_id(self.feature, self.rel_path, sym_name)
            self.fun_ids[qual] = sid  # map unqualified qual → first overload

            is_main = fun_name == "main"
            is_constructor = fun_name == "constructor" or fun_name == class_name

            snode = Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=sym_name,
                file=self.rel_path,
                line=line_no,
                language="kotlin",
                entry_point=is_main,
            )
            self.g.add_node(snode)
            self.g.add_edge(Edge(from_id=class_tid, to_id=sid, relation=EdgeRelation.CONTAINS))
            self.g.add_edge(Edge(from_id=self.file_node_id, to_id=sid, relation=EdgeRelation.DEFINES))

            self._emit_return_type(sid, ret_type_raw)
            self._emit_params(sid, params_raw, class_name)

            # Function body
            brace_pos = body.find('{', m.start())
            if brace_pos == -1 or brace_pos > m.end() + 10:
                # expression body (= expr) — scan short slice for calls
                expr_slice = body[m.start():min(m.start() + 200, len(body))]
                self._parse_calls_in_body(expr_slice, sid, class_name, prop_map)
                continue

            fb_start, fb_end = _find_body(body, brace_pos)
            fun_body = body[fb_start:fb_end]
            self._parse_calls_in_body(fun_body, sid, class_name, prop_map)

    # ------------------------------------------------------------------
    # Return type → produces
    # ------------------------------------------------------------------

    def _emit_return_type(self, sid: str, ret_raw: str) -> None:
        if not ret_raw:
            return
        ret = _clean_type(ret_raw)
        if not ret or _is_primitive(ret):
            return
        ret_id = self._resolve_type(ret)
        self.g.add_edge(Edge(
            from_id=sid,
            to_id=ret_id,
            relation=EdgeRelation.PRODUCES,
            unresolved=(ret_id not in self.known),
        ))

    # ------------------------------------------------------------------
    # Parameters → consumes / modifies
    # ------------------------------------------------------------------

    def _emit_params(self, sid: str, params_raw: str, class_name: Optional[str]) -> None:
        params = _split_params(params_raw)
        for param in params:
            param = param.strip()
            if not param:
                continue
            # Remove modifiers: vararg, crossinline, noinline
            param = re.sub(r'\b(?:vararg|crossinline|noinline|val|var)\b\s*', '', param)
            # Kotlin param: name: Type [= default]
            # Remove default value
            param = re.sub(r'\s*=\s*.*$', '', param).strip()
            if ':' not in param:
                continue
            parts = param.split(':', 1)
            param_name = parts[0].strip()
            param_type_raw = parts[1].strip()
            param_type = _clean_type(param_type_raw)
            if not param_type or _is_primitive(param_type):
                continue

            param_tid = self._resolve_type(param_type)
            unresolved = param_tid not in self.known

            relation = (EdgeRelation.MODIFIES
                        if param_type in _MUTABLE_TYPE_HINTS
                        else EdgeRelation.CONSUMES)
            self.g.add_edge(Edge(
                from_id=sid,
                to_id=param_tid,
                relation=relation,
                unresolved=unresolved,
            ))

    # ------------------------------------------------------------------
    # Supertypes → uses_type
    # ------------------------------------------------------------------

    def _emit_supertypes(self, class_tid: str, class_name: str, supertypes_str: str) -> None:
        # Split on commas but respect parentheses (constructor calls in supertypes)
        supertypes = _split_supertypes(supertypes_str)
        supertype_names: List[str] = []
        for raw in supertypes:
            # Remove constructor call: Bar(args) → Bar
            name = re.sub(r'\(.*?\)', '', raw).strip()
            name = _clean_type(name)
            if not name or _is_primitive(name):
                continue
            supertype_names.append(name)
            parent_id = self._resolve_type(name)
            self.g.add_edge(Edge(
                from_id=class_tid,
                to_id=parent_id,
                relation=EdgeRelation.USES_TYPE,
                unresolved=(parent_id not in self.known and parent_id not in self.class_ids.values()),
            ))
        if supertype_names:
            self.class_supertypes[class_name] = supertype_names

    # ------------------------------------------------------------------
    # Call extraction
    # ------------------------------------------------------------------

    def _parse_calls_in_body(self, body: str, caller_sid: str,
                              class_name: str, prop_map: Dict[str, str]) -> None:
        seen: Set[str] = set()

        # Anonymous object supertypes → uses_type on caller (approximation)
        for am in _RE_ANON_OBJECT.finditer(body):
            type_list = am.group(1)
            for raw in type_list.split(","):
                name = _clean_type(raw.strip())
                if name and not _is_primitive(name):
                    tid = self._resolve_type(name)
                    if tid not in seen:
                        seen.add(tid)
                        self.g.add_edge(Edge(
                            from_id=caller_sid,
                            to_id=tid,
                            relation=EdgeRelation.USES_TYPE,
                            unresolved=(tid not in self.known),
                        ))

        # UpperCamelCase(... ) → constructor-like call
        for cm in _RE_CONSTRUCT.finditer(body):
            name = cm.group(1)
            if _is_primitive(name) or name in ("if", "when", "for", "while",
                                                "try", "catch", "object", "fun"):
                continue
            target_id = self._resolve_constructor(name)
            if target_id and target_id not in seen:
                seen.add(target_id)
                self.g.add_edge(Edge(
                    from_id=caller_sid,
                    to_id=target_id,
                    relation=EdgeRelation.CALLS,
                    unresolved=(target_id not in self.known),
                ))

        # Regular calls
        for m in _RE_CALL.finditer(body):
            raw = m.group(1)
            parts = raw.split(".")
            fun_called = parts[-1]
            receiver = parts[-2] if len(parts) >= 2 else None

            if fun_called in ("if", "for", "while", "when", "catch", "try", "return",
                               "throw", "is", "as", "in", "!in", "object", "fun",
                               "class", "interface", "it", "this", "super", "null"):
                continue

            if self.filter_stdlib and receiver and receiver in _STDLIB_RECEIVERS:
                continue
            if fun_called in _STDLIB_RECEIVERS:
                continue

            target_id = self._resolve_call(raw, receiver, fun_called, class_name, prop_map)
            if target_id and target_id not in seen:
                seen.add(target_id)
                self.g.add_edge(Edge(
                    from_id=caller_sid,
                    to_id=target_id,
                    relation=EdgeRelation.CALLS,
                    unresolved=(target_id not in self.known),
                ))

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _resolve_type(self, name: str) -> str:
        if name in self.class_ids:
            return self.class_ids[name]
        suffix = f"::{name}"
        for kid in self.known:
            if kid.endswith(suffix):
                return kid
        module = self.package_name or _module_name(self.rel_path)
        return type_id(self.feature, module, name)

    def _resolve_constructor(self, class_name: str) -> Optional[str]:
        # In Kotlin, ClassName() calls the constructor — represented as ClassName.constructor
        # First try known registry
        suffix = f"::{class_name}.constructor"
        for kid in self.known:
            if kid.endswith(suffix):
                return kid
        # Try local classes — speculative
        if class_name in self.class_ids:
            return symbol_id(self.feature, self.rel_path, f"{class_name}.constructor")
        # Fully speculative
        module = self.package_name or _module_name(self.rel_path)
        tid = type_id(self.feature, module, class_name)
        return f"{tid}.constructor"

    def _resolve_call(self, raw: str, receiver: Optional[str],
                      fun_name: str, class_name: str,
                      prop_map: Dict[str, str]) -> Optional[str]:
        parts = raw.split(".")
        fun_called = parts[-1]
        receiver = parts[-2] if len(parts) >= 2 else None

        # 1a. super.method → try each known supertype first, then fall back to same class
        if receiver == "super":
            for stype in self.class_supertypes.get(class_name, []):
                qual = f"{stype}.{fun_called}"
                if qual in self.fun_ids:
                    return self.fun_ids[qual]
                suffix = f"::{qual}"
                for kid in self.known:
                    if kid.endswith(suffix):
                        return kid

        # 1b. this / super / unqualified → same class
        if receiver is None or receiver in ("this", "super"):
            qual = f"{class_name}.{fun_called}"
            if qual in self.fun_ids:
                return self.fun_ids[qual]
            suffix = f"::{qual}"
            for kid in self.known:
                if kid.endswith(suffix):
                    return kid

        # 2. receiver is a known property → use property type
        if receiver and receiver in prop_map:
            prop_type = prop_map[receiver]
            qual = f"{prop_type}.{fun_called}"
            if qual in self.fun_ids:
                return self.fun_ids[qual]
            suffix = f"::{qual}"
            for kid in self.known:
                if kid.endswith(suffix):
                    return kid

        # 3. receiver is a class or object name
        if receiver:
            qual = f"{receiver}.{fun_called}"
            if qual in self.fun_ids:
                return self.fun_ids[qual]
            suffix = f"::{qual}"
            for kid in self.known:
                if kid.endswith(suffix):
                    return kid

        # 4. bare function name scan
        suffix = f"::{fun_called}"
        candidates = [kid for kid in self.known if kid.endswith(suffix)]
        if len(candidates) == 1:
            return candidates[0]

        # 5. Speculative
        if receiver and receiver[0].isupper():
            return symbol_id(self.feature, self.rel_path, f"{receiver}.{fun_called}")

        return symbol_id(self.feature, self.rel_path, f"_unresolved_.{fun_called}")


# ---------------------------------------------------------------------------
# Param and supertype splitters
# ---------------------------------------------------------------------------

def _split_params(params_raw: str) -> List[str]:
    """Split parameter list respecting angle brackets and parentheses."""
    result = []
    depth_angle = 0
    depth_paren = 0
    current: List[str] = []
    for ch in params_raw:
        if ch == '<':
            depth_angle += 1
            current.append(ch)
        elif ch == '>':
            depth_angle -= 1
            current.append(ch)
        elif ch == '(':
            depth_paren += 1
            current.append(ch)
        elif ch == ')':
            depth_paren -= 1
            current.append(ch)
        elif ch == ',' and depth_angle == 0 and depth_paren == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        result.append("".join(current))
    return result


def _split_supertypes(supertypes_str: str) -> List[str]:
    """Split 'Bar(args), Baz' respecting parentheses."""
    result = []
    depth = 0
    current: List[str] = []
    for ch in supertypes_str:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        result.append("".join(current))
    return result
