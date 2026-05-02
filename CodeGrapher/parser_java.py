"""
parser_java.py — Regex-based Java file parser for CodeGrapher.

Extracts nodes and edges from a single .java file:
  - imports       (file → external package or local file)
  - defines       (file → class / interface / enum)
  - contains      (class → method / constructor)
  - uses_type     (class → superclass / interface it extends or implements)
  - produces      (method → declared return type, non-void, non-primitive)
  - consumes      (method → non-mutating typed parameter)
  - modifies      (method → Collection/mutable typed parameter — heuristic)
  - calls         (method → called symbol, best-effort resolution)

Pass 1: parse_file() — builds all nodes + edges resolvable locally.
         Unresolvable calls are marked unresolved=True.
Pass 2: resolve_calls() — upgrades unresolved calls using cross-file registry.

Reusable across any Java project — no project-specific logic here.
"""

from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .schema import (
    Node, Edge,
    NodeType, EdgeRelation,
    file_id, symbol_id, type_id,
)
from .graph import CodeGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel(root: Path, filepath: Path) -> str:
    try:
        return str(filepath.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(filepath).replace("\\", "/")


def _stem(filepath: Path) -> str:
    return filepath.stem


def _module_name(rel_path: str) -> str:
    """Derive a module-like name from relative path (no extension, slashes→dots)."""
    return rel_path.replace("/", ".").replace("\\", ".").rsplit(".", 1)[0]


# ---------------------------------------------------------------------------
# Java primitive / stdlib type sets
# ---------------------------------------------------------------------------

_PRIMITIVE_TYPES: frozenset = frozenset({
    "void", "int", "long", "short", "byte", "char", "float", "double", "boolean",
    "String", "Object", "Integer", "Long", "Short", "Byte", "Character",
    "Float", "Double", "Boolean", "Number", "Math",
    "StringBuilder", "StringBuffer", "CharSequence",
})

_STDLIB_GENERICS: frozenset = frozenset({
    "List", "ArrayList", "LinkedList", "Set", "HashSet", "TreeSet", "Map",
    "HashMap", "TreeMap", "LinkedHashMap", "Collection", "Iterable",
    "Iterator", "Optional", "Stream", "Comparator", "Callable", "Runnable",
    "Thread", "Exception", "RuntimeException", "Throwable", "Error",
    "Class", "Enum", "Record",
})

_SKIP_TYPES: frozenset = _PRIMITIVE_TYPES | _STDLIB_GENERICS

# Heuristic: parameter types that suggest mutation (the method modifies the object)
_MUTABLE_TYPE_HINTS: frozenset = frozenset({
    "List", "ArrayList", "LinkedList", "Set", "HashSet", "Map", "HashMap",
    "Collection", "Queue", "Deque", "Stack",
})

# Java stdlib receiver prefixes to suppress as unresolved calls
_STDLIB_RECEIVERS: frozenset = frozenset({
    "System", "Math", "Arrays", "Collections", "Objects", "Optional",
    "String", "Integer", "Long", "Double", "Boolean", "Character",
    "Thread", "Runtime", "Class", "Object",
})


def _is_primitive(name: str) -> bool:
    return name in _SKIP_TYPES or name.startswith("java.")


def _strip_generics(type_str: str) -> str:
    """Remove generic parameters: 'List<String>' -> 'List'."""
    return re.sub(r'<[^>]*>', '', type_str).strip()


def _strip_array(type_str: str) -> str:
    """Remove array brackets: 'String[]' -> 'String'."""
    return type_str.replace("[]", "").strip()


def _clean_type(type_str: str) -> str:
    return _strip_generics(_strip_array(type_str.strip()))


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Package declaration
_RE_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)

# Import statements
_RE_IMPORT = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;', re.MULTILINE)

# Class/interface/enum declaration (top-level and nested)
_RE_TYPE_DECL = re.compile(
    r'(?:^|\n)\s*'
    r'(?:(?:public|private|protected|static|final|abstract|sealed|non-sealed)\s+)*'
    r'(class|interface|enum|@interface|record)\s+'
    r'(\w+)'
    r'(?:\s*<[^{]*?>)?'                              # optional generic params
    r'(?:\s+extends\s+([\w.<>, \n]+?))?'             # optional extends
    r'(?:\s+implements\s+([\w.<>, \n]+?))?'          # optional implements
    r'\s*\{',
    re.MULTILINE,
)

# Method/constructor declaration inside a class body
# Matches: [modifiers] [return_type] name(params) [throws ...] {
_RE_METHOD = re.compile(
    r'(?:^|(?<=\n))\s*'
    r'(?:(?:@\w+(?:\([^)]*\))?\s+)*)'               # annotations
    r'(?:(?:public|private|protected|static|final|abstract|synchronized|native|default|override)\s+)*'
    r'(?:<[^>]*>\s+)?'                               # generic method type params
    r'([\w<>\[\]?.]+)\s+'                            # return type (or constructor name part)
    r'(\w+)\s*'
    r'\(([^)]*)\)'                                   # parameter list
    r'(?:\s+throws\s+[\w,\s]+)?'                     # optional throws
    r'\s*(?:\{|;)',
    re.MULTILINE,
)

# Method call patterns: name(), obj.name(), this.name(), super.name()
_RE_CALL = re.compile(
    r'(?<!\w)((?:\w+\.)*\w+)\s*\(',
)

# new ClassName(...) — constructor calls
_RE_NEW = re.compile(r'\bnew\s+([\w.<>]+)\s*\(')

# Field/variable type assignment (simple): Type varName = ...
_RE_VAR_DECL = re.compile(
    r'(?:^|(?<=\n))\s*'
    r'(?:(?:private|protected|public|static|final|volatile|transient)\s+)*'
    r'([\w<>\[\]]+)\s+'
    r'(\w+)\s*[=;,]',
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Comment stripper (block + line)
# ---------------------------------------------------------------------------

def _strip_comments(source: str) -> str:
    """Remove Java block comments and line comments, preserving line structure."""
    # Block comments /* ... */
    result = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), source, flags=re.DOTALL)
    # Line comments //
    result = re.sub(r'//[^\n]*', '', result)
    return result


# ---------------------------------------------------------------------------
# Class body extractor
# ---------------------------------------------------------------------------

def _find_class_body(source: str, open_brace_pos: int) -> Tuple[int, int]:
    """
    Given position of the opening '{' of a class, find the matching '}'.
    Returns (start, end) indices of the body content (exclusive of braces).
    """
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
# Public API
# ---------------------------------------------------------------------------

def parse_file(feature: str, root: Path, filepath: Path,
               known_symbol_ids: Set[str] | None = None,
               known_return_types: Dict[str, str] | None = None,
               known_file_ids: Dict[str, str] | None = None,
               filter_stdlib: bool = False) -> CodeGraph:
    """
    Parse a single Java file and return a CodeGraph.

    Args:
        feature:            Feature name
        root:               Project root Path
        filepath:           Absolute path to the .java file
        known_symbol_ids:   Cross-file symbol registry (Pass 2 only)
        known_return_types: function_label → return type (unused in Java — types
                            are always explicit; kept for API parity)
        known_file_ids:     class_name → file_id mapping for local class resolution
        filter_stdlib:      If True, suppress calls to stdlib receivers
    """
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
        raw_source=raw_source,
        known_symbol_ids=known_symbol_ids or set(),
        known_file_ids=known_file_ids or {},
        filter_stdlib=filter_stdlib,
        g=g,
    )
    parser.parse()
    return g


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

class _FileParser:
    def __init__(self, feature: str, rel_path: str, source: str, raw_source: str,
                 known_symbol_ids: Set[str], known_file_ids: Dict[str, str],
                 filter_stdlib: bool, g: CodeGraph):
        self.feature = feature
        self.rel_path = rel_path
        self.source = source
        self.raw_source = raw_source
        self.known = known_symbol_ids
        self.known_file_ids = known_file_ids
        self.filter_stdlib = filter_stdlib
        self.g = g

        self.file_node_id = file_id(feature, rel_path)
        self.package_name: str = ""

        # class_name → type_id (for building contains/uses_type edges)
        self.class_ids: Dict[str, str] = {}
        # method qualified name → symbol_id
        self.method_ids: Dict[str, str] = {}
        # class_name → set of field variable types (for call resolution)
        self.field_types: Dict[str, Dict[str, str]] = {}  # class → {varname: type}
        # class_name → list of direct supertype names (for super.method() resolution)
        self.class_supertypes: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # Top-level parse
    # ------------------------------------------------------------------

    def parse(self) -> None:
        source = self.source

        # File node
        fnode = Node(
            id=self.file_node_id,
            type=NodeType.FILE,
            label=self.rel_path.split("/")[-1],
            file=self.rel_path,
            line=1,
            language="java",
        )
        self.g.add_node(fnode)

        # Package
        pkg_m = _RE_PACKAGE.search(source)
        self.package_name = pkg_m.group(1) if pkg_m else ""

        # Imports
        self._parse_imports(source)

        # Type declarations (class / interface / enum)
        self._parse_type_declarations(source)

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _parse_imports(self, source: str) -> None:
        for m in _RE_IMPORT.finditer(source):
            fqn = m.group(1)
            # Determine target: local file or stdlib
            # Simple name (last segment)
            simple = fqn.split(".")[-1]
            if simple == "*":
                # Wildcard import — point to package as stdlib-like node
                pkg = fqn[:-2]  # strip ".*"
                target_id = f"stdlib::{pkg}"
                self.g.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=target_id,
                    relation=EdgeRelation.IMPORTS,
                    unresolved=True,
                ))
                continue

            # Try to resolve as a local class
            local_id = self._resolve_local_class(simple)
            if local_id:
                self.g.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=local_id,
                    relation=EdgeRelation.IMPORTS,
                ))
            else:
                # External/stdlib import
                target_id = f"stdlib::{fqn}"
                self.g.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=target_id,
                    relation=EdgeRelation.IMPORTS,
                    unresolved=True,
                ))

    # ------------------------------------------------------------------
    # Type declarations
    # ------------------------------------------------------------------

    def _parse_type_declarations(self, source: str) -> None:
        for m in _RE_TYPE_DECL.finditer(source):
            kind = m.group(1)          # class / interface / enum / record
            class_name = m.group(2)
            extends_str = m.group(3) or ""
            implements_str = m.group(4) or ""

            line_no = source[:m.start()].count('\n') + 1

            # type_id uses package as module context
            module = self.package_name or _module_name(self.rel_path)
            tid = type_id(self.feature, module, class_name)
            self.class_ids[class_name] = tid

            is_interface = kind in ("interface", "@interface")
            is_enum = (kind == "enum")

            tnode = Node(
                id=tid,
                type=NodeType.TYPE,
                label=class_name,
                file=self.rel_path,
                line=line_no,
                language="java",
                is_dataclass=is_enum,
            )
            self.g.add_node(tnode)

            # file defines type
            self.g.add_edge(Edge(
                from_id=self.file_node_id,
                to_id=tid,
                relation=EdgeRelation.DEFINES,
            ))

            # extends / implements → uses_type edges
            supertypes_for_class: List[str] = []
            for parent_str in [extends_str, implements_str]:
                if not parent_str.strip():
                    continue
                for raw_type in parent_str.split(","):
                    parent_name = _clean_type(raw_type.strip())
                    if not parent_name or _is_primitive(parent_name):
                        continue
                    supertypes_for_class.append(parent_name)
                    parent_id = self._resolve_type(parent_name)
                    self.g.add_edge(Edge(
                        from_id=tid,
                        to_id=parent_id,
                        relation=EdgeRelation.USES_TYPE,
                        unresolved=(parent_id not in self.known and parent_id not in self.class_ids.values()),
                    ))
            if supertypes_for_class:
                self.class_supertypes[class_name] = supertypes_for_class

            # Find class body
            brace_pos = source.index('{', m.start())
            body_start, body_end = _find_class_body(source, brace_pos)
            body = source[body_start:body_end]
            body_offset = body_start

            # Field declarations (for call resolution via instance types)
            field_map: Dict[str, str] = {}
            for vm in _RE_VAR_DECL.finditer(body):
                vtype = _clean_type(vm.group(1))
                vname = vm.group(2)
                if vtype and not _is_primitive(vtype) and vname not in ("return", "if", "for", "while"):
                    field_map[vname] = vtype
            self.field_types[class_name] = field_map

            # Methods and constructors
            self._parse_methods(body, body_offset, class_name, tid, kind)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _parse_methods(self, body: str, body_offset: int,
                       class_name: str, class_type_id: str, class_kind: str) -> None:
        seen_names: Dict[str, int] = {}

        for m in _RE_METHOD.finditer(body):
            ret_type_raw = m.group(1).strip()
            method_name = m.group(2).strip()
            params_raw = m.group(3).strip()

            # Skip keywords that match the pattern accidentally
            if method_name in ("if", "for", "while", "switch", "catch", "return",
                                "new", "class", "interface", "enum"):
                continue
            # Skip inner class/interface declarations caught by method regex
            if ret_type_raw in ("class", "interface", "enum", "public", "private",
                                 "protected", "static", "final", "abstract"):
                continue

            # Detect constructor: return type matches class name
            is_constructor = (ret_type_raw == class_name)
            qualified_name = f"{class_name}.{method_name}" if not is_constructor else f"{class_name}.constructor"

            # Disambiguate overloads
            count = seen_names.get(qualified_name, 0)
            seen_names[qualified_name] = count + 1
            if count > 0:
                sym_name = f"{qualified_name}_{count}"
            else:
                sym_name = qualified_name

            line_no = self.source[:body_offset + m.start()].count('\n') + 1

            sid = symbol_id(self.feature, self.rel_path, sym_name)
            self.method_ids[qualified_name] = sid

            snode = Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=sym_name,
                file=self.rel_path,
                line=line_no,
                language="java",
                entry_point=(method_name == "main" and ret_type_raw == "void"),
            )
            self.g.add_node(snode)

            # class contains method
            self.g.add_edge(Edge(
                from_id=class_type_id,
                to_id=sid,
                relation=EdgeRelation.CONTAINS,
            ))

            # file defines method
            self.g.add_edge(Edge(
                from_id=self.file_node_id,
                to_id=sid,
                relation=EdgeRelation.DEFINES,
            ))

            # Return type → produces edge
            if not is_constructor:
                ret_clean = _clean_type(ret_type_raw)
                if ret_clean and not _is_primitive(ret_clean):
                    ret_id = self._resolve_type(ret_clean)
                    self.g.add_edge(Edge(
                        from_id=sid,
                        to_id=ret_id,
                        relation=EdgeRelation.PRODUCES,
                        unresolved=(ret_id not in self.known),
                    ))

            # Parameters → consumes / modifies edges
            if params_raw:
                self._parse_params(params_raw, sid, class_name)

            # Parse method body for calls
            # Find method body via brace matching
            brace_pos_in_body = body.find('{', m.start())
            if brace_pos_in_body == -1 or brace_pos_in_body > m.end() + 5:
                continue
            mbody_start, mbody_end = _find_class_body(body, brace_pos_in_body)
            method_body = body[mbody_start:mbody_end]

            self._parse_calls(method_body, sid, class_name)

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _parse_params(self, params_raw: str, method_sid: str, class_name: str) -> None:
        # Split params: "Type name, Type2 name2, ..."
        # Handle generics by counting < >
        params = _split_params(params_raw)
        for param in params:
            param = param.strip()
            if not param:
                continue
            # Remove varargs, final, annotations
            param = re.sub(r'\.\.\.|@\w+\s*|final\s+', '', param).strip()
            parts = param.split()
            if len(parts) < 2:
                continue
            param_type_raw = " ".join(parts[:-1])
            param_name = parts[-1]
            param_type = _clean_type(param_type_raw)
            if not param_type or _is_primitive(param_type):
                continue

            param_tid = self._resolve_type(param_type)
            unresolved = param_tid not in self.known

            if param_type in _MUTABLE_TYPE_HINTS:
                self.g.add_edge(Edge(
                    from_id=method_sid,
                    to_id=param_tid,
                    relation=EdgeRelation.MODIFIES,
                    unresolved=unresolved,
                ))
            else:
                self.g.add_edge(Edge(
                    from_id=method_sid,
                    to_id=param_tid,
                    relation=EdgeRelation.CONSUMES,
                    unresolved=unresolved,
                ))

    # ------------------------------------------------------------------
    # Call extraction
    # ------------------------------------------------------------------

    def _parse_calls(self, method_body: str, caller_sid: str, class_name: str) -> None:
        field_map = self.field_types.get(class_name, {})
        seen_calls: Set[str] = set()

        # new ClassName(...) → constructor call
        for m in _RE_NEW.finditer(method_body):
            raw = _clean_type(m.group(1))
            if not raw or _is_primitive(raw):
                continue
            target_id = self._resolve_constructor(raw)
            if target_id and target_id not in seen_calls:
                seen_calls.add(target_id)
                self.g.add_edge(Edge(
                    from_id=caller_sid,
                    to_id=target_id,
                    relation=EdgeRelation.CALLS,
                    unresolved=(target_id not in self.known),
                ))

        # Regular calls: name(), obj.method(), this.method(), super.method()
        for m in _RE_CALL.finditer(method_body):
            raw = m.group(1)

            # Skip language keywords
            if raw.split(".")[-1] in ("if", "for", "while", "switch", "catch",
                                       "return", "new", "class", "throw", "assert",
                                       "instanceof", "super", "this"):
                continue

            # Parse receiver chain
            parts = raw.split(".")
            method_called = parts[-1]
            receiver = parts[-2] if len(parts) >= 2 else None

            # Suppress stdlib receivers
            if self.filter_stdlib and receiver and receiver in _STDLIB_RECEIVERS:
                continue
            if receiver and receiver in _STDLIB_RECEIVERS:
                # Still suppress common stdlib even without filter (they're unresolvable noise)
                pass

            target_id = self._resolve_call(raw, receiver, method_called, class_name, field_map)
            if target_id and target_id not in seen_calls:
                seen_calls.add(target_id)
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
        """Resolve a type name to a type_id. First checks local classes, then registry."""
        # Local class in same file
        if name in self.class_ids:
            return self.class_ids[name]
        # Registry hit (any feature-scoped type node)
        suffix = f"::{name}"
        for kid in self.known:
            if kid.endswith(suffix):
                return kid
        # Build a speculative type_id using package context
        module = self.package_name or _module_name(self.rel_path)
        return type_id(self.feature, module, name)

    def _resolve_constructor(self, class_name: str) -> Optional[str]:
        """Resolve new ClassName() to the constructor symbol_id."""
        # Try ClassName.constructor suffix in known registry
        constructor_suffix = f"::{class_name}.constructor"
        for kid in self.known:
            if kid.endswith(constructor_suffix):
                return kid
        # Try local class_ids → build speculative
        if class_name in self.class_ids:
            # Build speculative constructor symbol_id
            return symbol_id(self.feature, self.rel_path, f"{class_name}.constructor")
        # Unresolved — build speculative with package
        module = self.package_name or _module_name(self.rel_path)
        tid = type_id(self.feature, module, class_name)
        # Return speculative constructor id based on type_id pattern
        return f"{tid}.constructor"

    def _resolve_local_class(self, simple_name: str) -> Optional[str]:
        """Try to find a known file_id for a simple class name via known_file_ids."""
        # known_file_ids maps stem/class name → file_id
        if simple_name in self.known_file_ids:
            return self.known_file_ids[simple_name]
        return None

    def _resolve_call(self, raw: str, receiver: Optional[str],
                      method_name: str, class_name: str,
                      field_map: Dict[str, str]) -> Optional[str]:
        """
        Best-effort resolution of a method call to a symbol_id.

        Resolution order:
        1a. super.method → supertype first, then same class (inherited override)
        1b. this.method / unqualified → same class method
        2. receiver is a local variable with known type → FieldType.method
        3. receiver is a class name (static call) → ClassName.method
        4. ClassName.method suffix scan in known registry
        5. Bare method name suffix scan in registry
        """
        parts = raw.split(".")
        method_called = parts[-1]
        receiver = parts[-2] if len(parts) >= 2 else None

        # 1a. super.method → try each known supertype first, then fall back to same class
        if receiver == "super":
            for stype in self.class_supertypes.get(class_name, []):
                qualified = f"{stype}.{method_called}"
                if qualified in self.method_ids:
                    return self.method_ids[qualified]
                suffix = f"::{qualified}"
                for kid in self.known:
                    if kid.endswith(suffix):
                        return kid

        # 1b. this.method or unqualified → look up in same class methods
        if receiver is None or receiver in ("this", "super"):
            qualified = f"{class_name}.{method_called}"
            if qualified in self.method_ids:
                return self.method_ids[qualified]
            # Scan registry for same-class qualified name
            suffix = f"::{qualified}"
            for kid in self.known:
                if kid.endswith(suffix):
                    return kid

        # 2. Receiver is a known local field → resolve via field type
        if receiver and receiver in field_map:
            field_type = field_map[receiver]
            qualified = f"{field_type}.{method_called}"
            if qualified in self.method_ids:
                return self.method_ids[qualified]
            suffix = f"::{qualified}"
            for kid in self.known:
                if kid.endswith(suffix):
                    return kid

        # 3. Receiver is a class name (static call or enum call)
        if receiver:
            qualified = f"{receiver}.{method_called}"
            if qualified in self.method_ids:
                return self.method_ids[qualified]
            suffix = f"::{qualified}"
            for kid in self.known:
                if kid.endswith(suffix):
                    return kid

        # 4. Bare method name scan
        suffix = f"::{method_called}"
        candidates = [kid for kid in self.known if kid.endswith(suffix)]
        if len(candidates) == 1:
            return candidates[0]

        # Unresolved — emit speculative id
        if receiver and receiver[0].isupper():
            # Looks like a class reference
            module = self.package_name or _module_name(self.rel_path)
            return symbol_id(self.feature, self.rel_path, f"{receiver}.{method_called}")

        # Can't resolve
        return symbol_id(self.feature, self.rel_path, f"_unresolved_.{method_called}")


# ---------------------------------------------------------------------------
# Param splitter (respects generics angle brackets)
# ---------------------------------------------------------------------------

def _split_params(params_raw: str) -> List[str]:
    """Split 'Type<A,B> name, Type2 name2' respecting generic brackets."""
    result = []
    depth = 0
    current = []
    for ch in params_raw:
        if ch == '<':
            depth += 1
            current.append(ch)
        elif ch == '>':
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
