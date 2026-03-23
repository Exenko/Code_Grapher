"""
parser_cpp.py — Regex-based C/C++ file parser.

Extracts nodes and edges from .h and .cc files:
  - .h files:   structs, enums, typedefs, function declarations, field types
  - .cc files:  function definitions, function calls, includes, return types

Produces:
  - TYPE nodes for structs, enums, typedefs
  - SYMBOL nodes for functions (both declarations and definitions)
  - SYMBOL nodes for struct fields
  - TYPEDEF_OF edges for type aliases (with ptr_depth for pointer indirection)
  - CONTAINS edges (struct → field)
  - USES_TYPE edges (field → type)
  - DEFINES/CALLS/PRODUCES/CONSUMES edges (file/function-level)
  - DEPENDS_ON edges for #include directives

Relay rule: if file path contains "relay" or "broker" in directory name,
           set relay=True on all produces edges from that file's symbols.

Role:control rule: if parameter type matches *Config/*Table/*Policy/*Options/*Settings,
                   set role="control" on the consumes edge.

Reusable across any C/C++ project.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Optional, Set, Dict, Tuple

from schema import (
    Node, Edge, NodeType, EdgeRelation,
    file_id, symbol_id, type_id, is_test_file,
)
from graph import CodeGraph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(feature: str, root: Path, filepath: Path,
               known_symbol_ids: Set[str] | None = None) -> CodeGraph:
    """
    Parse a single C/C++ file (.h or .cc) and return a CodeGraph.

    Args:
        feature:          Feature name (e.g. "broker")
        root:             Project root Path (for computing relative paths)
        filepath:         Absolute path to the .h or .cc file
        known_symbol_ids: Set of all symbol/type IDs known across the feature
                         (used to resolve type references).
                         If None, all type references are unresolved.
    """
    rel_path = _rel(root, filepath)
    source = filepath.read_text(encoding="utf-8", errors="replace")

    is_header = filepath.suffix.lower() in {".h", ".hpp", ".hxx"}
    is_implementation = filepath.suffix.lower() in {".cc", ".cpp", ".cxx", ".c"}

    # Extract member variable types from corresponding header (if parsing implementation)
    member_var_types: Dict[str, str] = {}
    class_bases: Dict[str, List[str]] = {}
    if is_implementation:
        # Pre-pass: find corresponding header and extract member variable types
        for ext in ('.h', '.hpp'):
            candidate = filepath.with_suffix(ext)
            if candidate.exists():
                header_source = candidate.read_text(encoding='utf-8', errors='replace')
                header_rel = _rel(root, candidate)
                _hparser = _HeaderParser(
                    feature=feature,
                    rel_path=header_rel,
                    module_name=_module_name(header_rel),
                    is_test=is_test_file(header_rel),
                    known_symbol_ids=known_symbol_ids or set(),
                )
                _hparser.parse(header_source)
                member_var_types = _hparser._member_var_types
                class_bases = _hparser._class_bases
                break

    if is_header:
        parser = _HeaderParser(
            feature=feature,
            rel_path=rel_path,
            module_name=_module_name(rel_path),
            is_test=is_test_file(rel_path),
            known_symbol_ids=known_symbol_ids or set(),
            member_var_types=member_var_types,
        )
    elif is_implementation:
        parser = _ImplementationParser(
            feature=feature,
            rel_path=rel_path,
            module_name=_module_name(rel_path),
            is_test=is_test_file(rel_path),
            known_symbol_ids=known_symbol_ids or set(),
            member_var_types=member_var_types,
            class_bases=class_bases,
        )
    else:
        # Fallback: treat as header
        parser = _HeaderParser(
            feature=feature,
            rel_path=rel_path,
            module_name=_module_name(rel_path),
            is_test=is_test_file(rel_path),
            known_symbol_ids=known_symbol_ids or set(),
            member_var_types=member_var_types,
        )

    parser.parse(source)
    return parser.graph


# ---------------------------------------------------------------------------
# Helper function for multi-line parameter parsing
# ---------------------------------------------------------------------------

def _find_matching_paren(source: str, open_pos: int) -> Tuple[str, int]:
    """
    Starting at open_pos (which must be the index of '(' in source),
    scan forward to find the matching ')'.

    Returns (params_str, close_pos) where:
      - params_str is the content between the parens (may span multiple lines)
      - close_pos is the index of the closing ')'

    If no matching paren is found, returns ("", open_pos).
    """
    if open_pos >= len(source) or source[open_pos] != '(':
        return "", open_pos
    depth = 1
    pos = open_pos + 1
    while pos < len(source) and depth > 0:
        ch = source[pos]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        pos += 1
    if depth != 0:
        return "", open_pos
    close_pos = pos - 1  # index of the matching ')'
    params_str = source[open_pos + 1:close_pos]
    return params_str, close_pos


# ---------------------------------------------------------------------------
# Base parser class
# ---------------------------------------------------------------------------

class _BaseParser:
    """Shared functionality for header and implementation parsers."""

    def __init__(self, feature: str, rel_path: str, module_name: str,
                 is_test: bool, known_symbol_ids: Set[str],
                 member_var_types: Dict[str, str] | None = None,
                 class_bases: Dict[str, List[str]] | None = None):
        self.feature = feature
        self.rel_path = rel_path
        self.module_name = module_name
        self.is_test = is_test
        self.known = known_symbol_ids
        self.graph = CodeGraph(feature)

        # Local cache: type name -> type_id
        self.known_types: Dict[str, str] = {}

        # Cross-file member variable type map: var_name -> type_name
        # Populated by header parser from class member declarations.
        # Used by implementation parser to resolve obj.method() calls.
        self._member_var_types: Dict[str, str] = member_var_types if member_var_types is not None else {}

        # Inheritance map: class_name -> [base_class_name, ...]
        # Seeded from header pre-parse, extended by _extract_classes.
        self._class_bases: Dict[str, List[str]] = dict(class_bases) if class_bases else {}

        # Check if this file should have relay=True on produces edges
        rel_dir = str(rel_path).replace("\\", "/").split("/")[0] if "/" in rel_path else ""
        self.should_relay = "relay" in rel_path.lower() or "broker" in rel_path.lower()

        # File node
        self._file_node_id = file_id(feature, rel_path)
        self.graph.add_node(Node(
            id=self._file_node_id,
            type=NodeType.FILE,
            label=Path(rel_path).name,
            file=rel_path,
            line=None,
            language="cpp",
            is_test=is_test,
        ))

    def _resolve_type(self, name: str) -> Optional[str]:
        """
        Find a known type node matching this name.

        Priority:
          1. Local known_types cache (built during parsing)
          2. Same-module type in known_symbol_ids
          3. Any type in known_symbol_ids with matching label
        """
        # Check local cache first
        if name in self.known_types:
            return self.known_types[name]

        # Try known_symbol_ids
        same_module = []
        any_match = []

        for nid in self.known:
            label = nid.split("::")[-1]
            if label != name:
                continue
            if f"::{self.module_name}::" in nid:
                same_module.append(nid)
            else:
                any_match.append(nid)

        if same_module:
            result = same_module[0]
        elif any_match:
            result = any_match[0]
        else:
            return None

        # Cache it
        self.known_types[name] = result
        return result

    def _is_control_type(self, name: str) -> bool:
        """Return True if type name suggests a config/settings/policy input."""
        control_hints = {"Config", "Table", "Policy", "Options", "Settings"}
        if name in control_hints:
            return True
        return any(hint in name for hint in control_hints)


# ---------------------------------------------------------------------------
# Header parser (.h files)
# ---------------------------------------------------------------------------

class _HeaderParser(_BaseParser):
    """Parse .h files: structs, enums, typedefs, function declarations."""

    def parse(self, source: str) -> None:
        """Parse header source and populate graph."""
        self._extract_classes(source)
        self._extract_structs(source)
        self._extract_enums(source)
        self._extract_typedefs(source)
        self._extract_function_declarations(source)

    def _extract_classes(self, source: str) -> None:
        """Extract class definitions and their method declarations."""
        # Match: class ClassName [: public Base, ...] {
        # Capture the inheritance clause (group 2) so we can extract base class names.
        pattern = r'\bclass\s+(\w+)\s*(?::([^{]*))?\{'
        for match in re.finditer(pattern, source):
            class_name = match.group(1)
            inheritance_clause = match.group(2) or ""
            class_start = match.start()

            # Parse base class names from inheritance clause.
            # e.g. ": public Base, protected Mixin" -> ["Base", "Mixin"]
            bases: List[str] = []
            if inheritance_clause:
                for part in inheritance_clause.split(','):
                    tokens = part.strip().split()
                    # Strip access specifiers and 'virtual'
                    base_name = next(
                        (t for t in tokens
                         if t not in ('public', 'private', 'protected', 'virtual')
                         and t.isidentifier()),
                        None
                    )
                    if base_name:
                        bases.append(base_name)
            self._class_bases[class_name] = bases

            # Find the closing brace
            brace_count = 1
            pos = match.end()
            while pos < len(source) and brace_count > 0:
                if source[pos] == '{':
                    brace_count += 1
                elif source[pos] == '}':
                    brace_count -= 1
                pos += 1
            class_end = pos - 1

            class_body = source[match.end():class_end]

            # Create TYPE node for class
            tid = type_id(self.feature, self.module_name, class_name)
            self.known_types[class_name] = tid

            self.graph.add_node(Node(
                id=tid,
                type=NodeType.TYPE,
                label=class_name,
                file=self.rel_path,
                line=source[:class_start].count('\n') + 1,
                language="cpp",
                is_test=self.is_test,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=tid,
                relation=EdgeRelation.DEFINES,
            ))

            # Extract method declarations from class body
            self._extract_class_methods(class_body, class_name, tid,
                                        source[:class_start].count('\n') + 1)

            # Extract member variable declarations
            self._extract_member_variables(class_body, class_name)

    def _extract_class_methods(self, class_body: str, class_name: str,
                               class_type_id: str, base_line: int) -> None:
        """Extract method declarations from a class body."""
        # Match method signatures up to the opening paren.
        # Params extracted separately so multi-line signatures are handled.
        pattern = re.compile(
            r'^\s*(?:(?:virtual|static|explicit|inline|override)\s+)*'
            r'(\w[\w\s\*&:<>]*?)\s+'   # return type (group 1)
            r'(\w+)\s*'                 # method name (group 2)
            r'\(',                       # opening paren
            re.MULTILINE
        )

        for match in pattern.finditer(class_body):
            return_type = match.group(1).strip()
            method_name = match.group(2)

            if _is_likely_builtin_cpp(method_name):
                continue
            if method_name in ('public', 'private', 'protected', 'class', 'struct',
                               'return', 'if', 'for', 'while', 'switch'):
                continue

            # Find matching close paren
            open_paren_pos = match.end() - 1
            params_str, close_paren_pos = _find_matching_paren(class_body, open_paren_pos)
            if close_paren_pos == open_paren_pos:
                continue

            # After ')': expect optional const/override then ; or {
            after_close = class_body[close_paren_pos + 1:]
            stripped = after_close.lstrip(' \t\r\n')
            # Strip const/override qualifiers
            qualifier_re = re.compile(r'^(?:const\s+|override\s+)*')
            q_match = qualifier_re.match(stripped)
            rest = stripped[q_match.end():] if q_match else stripped
            if not rest or rest[0] not in (';', '{'):
                continue

            qualified_name = f"{class_name}.{method_name}"
            sid = symbol_id(self.feature, self.rel_path, qualified_name)
            line_num = base_line + class_body[:match.start()].count('\n')

            self.graph.add_node(Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=qualified_name,
                file=self.rel_path,
                line=line_num,
                language="cpp",
                is_test=self.is_test,
            ))
            self.graph.add_edge(Edge(
                from_id=class_type_id,
                to_id=sid,
                relation=EdgeRelation.CONTAINS,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=sid,
                relation=EdgeRelation.DEFINES,
            ))

            params_normalized = ' '.join(params_str.split())
            self._process_function_signature(qualified_name, return_type, params_normalized, sid)

    def _extract_member_variables(self, class_body: str, class_name: str) -> None:
        """Extract member variable declarations from a class body.

        Handles:
          TypeName varName;
          TypeName* varName;
          TypeName varName = ...;
          std::unique_ptr<TypeName> varName;

        Skips: primitives, juce:: types, std::function, bool/float/int/double/void
        """
        # Pattern 1: std::unique_ptr<TypeName> varName  or  TypeName* varName  or  TypeName varName
        # We extract the inner type name (stripping ptr/ref/template wrappers)
        lines = class_body.split('\n')
        for line in lines:
            line = line.strip()
            # Skip access specifiers, macros, method declarations, comments
            if not line or line.startswith('//') or line.startswith('*') or line.startswith('#'):
                continue
            if any(kw in line for kw in ('virtual', 'static', 'explicit', 'inline', 'override',
                                          'JUCE_', '(', 'operator', 'return', 'friend')):
                continue
            if not line.endswith(';'):
                continue

            # Try unique_ptr<T> varName[...];
            m = re.match(r'std::unique_ptr\s*<\s*([\w:]+)\s*>\s+(\w+)', line)
            if m:
                type_name = m.group(1).split('::')[-1]
                var_name = m.group(2)
                if not _is_builtin_cpp_type(type_name) and not _is_likely_builtin_cpp(type_name):
                    self._member_var_types[var_name] = type_name
                continue

            # Try plain: TypeName[*] varName[...];   (no template, no std::)
            # Must start with a capital letter (project types) or known type
            m = re.match(r'^([A-Z]\w*)\s*\*?\s+(\w+)\s*(?:[={].*)?;', line)
            if m:
                type_name = m.group(1)
                var_name = m.group(2)
                if not _is_builtin_cpp_type(type_name) and not _is_likely_builtin_cpp(type_name):
                    self._member_var_types[var_name] = type_name
                continue

    def _extract_structs(self, source: str) -> None:
        """Extract struct definitions and their fields."""
        # Match: struct StructName {
        pattern = r'\bstruct\s+(\w+)\s*\{'
        for match in re.finditer(pattern, source):
            struct_name = match.group(1)
            struct_start = match.start()

            # Find the closing brace
            brace_count = 1
            pos = match.end()
            struct_end = pos
            while pos < len(source) and brace_count > 0:
                if source[pos] == '{':
                    brace_count += 1
                elif source[pos] == '}':
                    brace_count -= 1
                pos += 1
            struct_end = pos - 1

            struct_body = source[match.end():struct_end]

            # Create TYPE node for struct
            tid = type_id(self.feature, self.module_name, struct_name)
            self.known_types[struct_name] = tid

            self.graph.add_node(Node(
                id=tid,
                type=NodeType.TYPE,
                label=struct_name,
                file=self.rel_path,
                line=source[:struct_start].count('\n') + 1,
                language="cpp",
                is_test=self.is_test,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=tid,
                relation=EdgeRelation.DEFINES,
            ))

            # Extract field declarations
            self._extract_struct_fields(struct_body, struct_name, tid)

    def _extract_struct_fields(self, struct_body: str, struct_name: str,
                              struct_type_id: str) -> None:
        """Extract fields from struct body and emit CONTAINS and USES_TYPE edges."""
        # Match field declarations: type field_name;
        # Simple pattern: word(s) followed by identifier(s) and semicolon
        pattern = r'(\w[\w\s\*&]*?)\s+(\w+)\s*;'

        for match in re.finditer(pattern, struct_body):
            field_type = match.group(1).strip()
            field_name = match.group(2)

            # Create SYMBOL node for field
            qualified_name = f"{struct_name}.{field_name}"
            sid = symbol_id(self.feature, self.rel_path, qualified_name)

            self.graph.add_node(Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=qualified_name,
                file=self.rel_path,
                line=None,
                language="cpp",
                is_test=self.is_test,
                annotation=field_type,
            ))

            # CONTAINS edge: struct -> field
            self.graph.add_edge(Edge(
                from_id=struct_type_id,
                to_id=sid,
                relation=EdgeRelation.CONTAINS,
            ))

            # Extract base type name (strip pointer/reference markers)
            base_type = re.sub(r'[\*&\s]', '', field_type)

            # USES_TYPE edge: field -> referenced type
            if base_type and not _is_builtin_cpp_type(base_type):
                target_id = self._resolve_type(base_type)
                if target_id:
                    self.graph.add_edge(Edge(
                        from_id=sid,
                        to_id=target_id,
                        relation=EdgeRelation.USES_TYPE,
                    ))

    def _extract_enums(self, source: str) -> None:
        """Extract enum definitions."""
        pattern = r'\benum\s+(?:class\s+)?(\w+)\s*\{'
        for match in re.finditer(pattern, source):
            enum_name = match.group(1)

            # Create TYPE node for enum
            tid = type_id(self.feature, self.module_name, enum_name)
            self.known_types[enum_name] = tid

            self.graph.add_node(Node(
                id=tid,
                type=NodeType.TYPE,
                label=enum_name,
                file=self.rel_path,
                line=source[:match.start()].count('\n') + 1,
                language="cpp",
                is_test=self.is_test,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=tid,
                relation=EdgeRelation.DEFINES,
            ))

    def _extract_typedefs(self, source: str) -> None:
        """Extract typedef declarations and create TYPEDEF_OF edges."""
        # Match: typedef ExistingType[*] NewName;
        pattern = r'\btypedef\s+([\w\s\*&]+?)\s+(\w+)\s*;'

        # First pass: collect all typedefs
        typedefs = []
        for match in re.finditer(pattern, source):
            old_type_str = match.group(1).strip()
            new_name = match.group(2)
            local_ptr_stars = old_type_str.count('*')
            base_type = re.sub(r'[\*&\s]', '', old_type_str)
            typedefs.append((new_name, base_type, local_ptr_stars, match.start()))

        # Build cumulative ptr_depth map: name -> cumulative depth from original base
        # Start with known types having depth 0
        cumulative_depth: Dict[str, int] = {}
        for type_id_val in self.known_types.values():
            label = type_id_val.split("::")[-1]
            cumulative_depth[label] = 0

        # Walk the typedef chain to compute cumulative depths
        for new_name, base_type, local_ptr_stars, _ in typedefs:
            base_depth = cumulative_depth.get(base_type, 0)
            cumulative_depth[new_name] = base_depth + local_ptr_stars

        # Second pass: create nodes and edges with cumulative ptr_depth
        for new_name, base_type, local_ptr_stars, match_start in typedefs:
            # Create TYPE node for the new alias
            new_tid = type_id(self.feature, self.module_name, new_name)
            self.known_types[new_name] = new_tid

            self.graph.add_node(Node(
                id=new_tid,
                type=NodeType.TYPE,
                label=new_name,
                file=self.rel_path,
                line=source[:match_start].count('\n') + 1,
                language="cpp",
                is_test=self.is_test,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=new_tid,
                relation=EdgeRelation.DEFINES,
            ))

            # Get cumulative ptr_depth for this typedef
            ptr_depth = cumulative_depth[new_name]

            # Find or resolve the base type
            base_tid = self._resolve_type(base_type)
            if base_tid:
                # TYPEDEF_OF edge: new_name -> base_type with cumulative ptr_depth
                self.graph.add_edge(Edge(
                    from_id=new_tid,
                    to_id=base_tid,
                    relation=EdgeRelation.TYPEDEF_OF,
                    ptr_depth=ptr_depth,
                ))
            else:
                # Unresolved base type
                unresolved_id = f"unresolved::{base_type}"
                self.graph.add_edge(Edge(
                    from_id=new_tid,
                    to_id=unresolved_id,
                    relation=EdgeRelation.TYPEDEF_OF,
                    ptr_depth=ptr_depth,
                    unresolved=True,
                ))

    def _extract_function_declarations(self, source: str) -> None:
        """Extract function declarations (signatures without implementations)."""
        # Match up to opening paren; extract params via _find_matching_paren
        # so multi-line signatures are handled correctly.
        pattern = re.compile(
            r'^(\w[\w\s\*]*?)\s+'  # return type (group 1)
            r'(\w+)\s*'             # function name (group 2)
            r'\(',                   # opening paren
            re.MULTILINE
        )

        for match in pattern.finditer(source):
            return_type = match.group(1).strip()
            func_name = match.group(2)

            if _is_likely_builtin_cpp(func_name):
                continue

            # Find matching close paren
            open_paren_pos = match.end() - 1
            params_str, close_paren_pos = _find_matching_paren(source, open_paren_pos)
            if close_paren_pos == open_paren_pos:
                continue

            # After ')': must end with ; (declaration, not definition)
            after_close = source[close_paren_pos + 1:]
            stripped = after_close.lstrip(' \t\r\n')
            qualifier_re = re.compile(r'^(?:const\s+|override\s+)*')
            q_match = qualifier_re.match(stripped)
            rest = stripped[q_match.end():] if q_match else stripped
            if not rest or rest[0] != ';':
                continue

            sid = symbol_id(self.feature, self.rel_path, func_name)
            line_num = source[:match.start()].count('\n') + 1

            self.graph.add_node(Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=func_name,
                file=self.rel_path,
                line=line_num,
                language="cpp",
                is_test=self.is_test,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=sid,
                relation=EdgeRelation.DEFINES,
            ))

            params_normalized = ' '.join(params_str.split())
            self._process_function_signature(func_name, return_type, params_normalized, sid)

    def _process_function_signature(self, func_name: str, return_type: str,
                                   params_str: str, func_id: str) -> None:
        """Process return type and parameters for produces/consumes edges."""
        return_type = return_type.strip()

        # PRODUCES: return type (if non-void, non-primitive)
        if return_type and return_type != "void" and not _is_builtin_cpp_type(return_type):
            base_type = re.sub(r'[\*&\s]', '', return_type)
            target_id = self._resolve_type(base_type)
            if target_id:
                self.graph.add_edge(Edge(
                    from_id=func_id,
                    to_id=target_id,
                    relation=EdgeRelation.PRODUCES,
                    via="return_value",
                    relay=True if self.should_relay else None,
                ))

        # CONSUMES: parameters (with role detection)
        if params_str:
            self._process_function_params(func_id, params_str)

    def _process_function_params(self, func_id: str, params_str: str) -> None:
        """Extract parameters and emit CONSUMES or MODIFIES edges."""
        # Split params by comma (naive — doesn't handle nested templates perfectly)
        params = [p.strip() for p in params_str.split(',') if p.strip()]

        for param in params:
            if param == "void" or param == "":
                continue

            # Extract type: everything except the last identifier (parameter name)
            parts = param.split()
            if len(parts) < 1:
                continue

            # Type is all but the last identifier
            param_name = parts[-1].lstrip('*&')
            param_type_str = " ".join(parts[:-1])

            # Classify the parameter passing style:
            #   T*           (non-const pointer)  → modifies
            #   T&           (non-const reference) → modifies
            #   const T*     (const pointer)        → consumes
            #   const T&     (const reference)      → consumes
            #   T            (value)                → consumes
            is_ptr = "*" in param_type_str
            is_const_ptr = "const" in param_type_str and "*" in param_type_str
            is_non_const_ref = "&" in param_type_str and "const" not in param_type_str
            is_modifying = (is_ptr and not is_const_ptr) or is_non_const_ref

            # Extract base type: remove qualifiers (const, volatile, static, etc.)
            # and pointer/reference markers (*, &, []), keeping only the type name
            base_type = re.sub(r'\b(?:const|volatile|static|extern|register)\b', '', param_type_str)
            base_type = re.sub(r'[\*&\[\]]', ' ', base_type)
            base_type = base_type.split()[0] if base_type.split() else ""

            if not base_type or _is_builtin_cpp_type(base_type):
                continue

            resolved_id = self._resolve_type(base_type)
            unresolved = resolved_id is None
            target_id: str = resolved_id if resolved_id else f"unresolved::{base_type}"

            role = "control" if self._is_control_type(base_type) else "data"

            if is_modifying:
                # Non-const pointer or non-const reference → the function modifies
                # this value in place.  Emit modifies instead of consumes.
                self.graph.add_edge(Edge(
                    from_id=func_id,
                    to_id=target_id,
                    relation=EdgeRelation.MODIFIES,
                    relay=True if self.should_relay else None,
                    unresolved=unresolved,
                ))
            else:
                # Const pointer/reference or value parameter → read-only input.
                self.graph.add_edge(Edge(
                    from_id=func_id,
                    to_id=target_id,
                    relation=EdgeRelation.CONSUMES,
                    role=role,
                    unresolved=unresolved,
                ))


# ---------------------------------------------------------------------------
# Implementation parser (.cc files)
# ---------------------------------------------------------------------------

class _ImplementationParser(_BaseParser):
    """Parse .cc files: function definitions, calls, includes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Maps variable/field name → declared type name, built before body parsing.
        self.var_types: Dict[str, str] = {}

    def parse(self, source: str) -> None:
        """Parse implementation source and populate graph."""
        self._extract_includes(source)
        self._extract_variable_declarations(source)
        self._extract_function_definitions(source)

    def _extract_variable_declarations(self, source: str) -> None:
        """Build a variable-name → type-name table from global/static declarations.

        Handles patterns like:
            static EventBus g_bus;
            EventBus g_bus;
            static EventBus* g_ptr;
        """
        # Match file-scope variable declarations (outside function bodies).
        # Simple heuristic: lines matching  [static] TypeName[*] varname;
        # that are NOT inside a block (we strip function bodies first).
        pattern = r'^\s*(?:static\s+)?([A-Z]\w+)\s*\*?\s+(\w+)\s*;'
        for match in re.finditer(pattern, source, re.MULTILINE):
            type_name = match.group(1)
            var_name = match.group(2)
            if not _is_builtin_cpp_type(type_name) and not _is_likely_builtin_cpp(type_name):
                self.var_types[var_name] = type_name

    def _extract_includes(self, source: str) -> None:
        """Extract #include directives and create DEPENDS_ON edges."""
        pattern = r'#include\s+"([^"]+)"'

        for match in re.finditer(pattern, source):
            included_file = match.group(1)
            # Normalize path
            included_rel = included_file.replace("\\", "/")

            # Create or reference the included file node
            include_file_id = file_id(self.feature, included_rel)

            # We don't know if it exists yet, but we can create an edge
            # The node might be added later or marked as unresolved
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=include_file_id,
                relation=EdgeRelation.DEPENDS_ON,
            ))

    def _extract_function_definitions(self, source: str) -> None:
        """Extract function definitions with bodies."""
        # Match C++ function definition signatures up to the opening paren.
        # Params are extracted separately via _find_matching_paren so that
        # multi-line parameter lists are handled correctly.
        # Pattern: ReturnType [ClassName::]FunctionName(
        pattern = re.compile(
            r'^([\w][\w\s\*&:<>]*?)\s+'  # return type (group 1)
            r'(?:(\w+)::)?'               # optional class qualifier (group 2)
            r'(\w+)\s*'                   # function name (group 3)
            r'\(',                         # opening paren (not captured)
            re.MULTILINE
        )

        seen_names = set()

        for match in pattern.finditer(source):
            return_type = match.group(1).strip()
            class_qualifier = match.group(2)
            func_name = match.group(3)

            if _is_likely_builtin_cpp(func_name):
                continue
            if func_name in ('public', 'private', 'protected', 'class', 'struct',
                             'return', 'if', 'for', 'while', 'switch', 'namespace'):
                continue

            # Find matching close paren (handles multi-line params)
            open_paren_pos = match.end() - 1  # position of '('
            params_str, close_paren_pos = _find_matching_paren(source, open_paren_pos)
            if close_paren_pos == open_paren_pos:
                continue  # unmatched paren, skip

            # Scan after ')' for optional qualifiers then '{'
            # Skip: const, override, noexcept, whitespace, newlines
            after_close = source[close_paren_pos + 1:]
            # Strip trailing qualifiers before brace
            qualifier_pattern = re.compile(r'^[\s\n]*(const\s+|override\s+|noexcept\s*(?:\([^)]*\))?\s+)*')
            q_match = qualifier_pattern.match(after_close)
            skip = q_match.end() if q_match else 0
            rest = after_close[skip:]

            # Next non-whitespace must be '{'
            stripped = rest.lstrip(' \t\r\n')
            if not stripped or stripped[0] != '{':
                continue

            brace_pos = close_paren_pos + 1 + skip + (len(rest) - len(stripped))

            # Use qualified name if class qualifier present
            if class_qualifier:
                qualified_name = f"{class_qualifier}.{func_name}"
            else:
                qualified_name = func_name

            # Deduplicate
            if qualified_name in seen_names:
                continue
            seen_names.add(qualified_name)

            # Find the matching closing brace
            brace_count = 1
            pos = brace_pos + 1
            while pos < len(source) and brace_count > 0:
                if source[pos] == '{':
                    brace_count += 1
                elif source[pos] == '}':
                    brace_count -= 1
                pos += 1
            func_end = pos - 1
            func_body = source[brace_pos + 1:func_end]

            # Create SYMBOL node
            func_start = match.start()
            sid = symbol_id(self.feature, self.rel_path, qualified_name)
            line_num = source[:func_start].count('\n') + 1

            self.graph.add_node(Node(
                id=sid,
                type=NodeType.SYMBOL,
                label=qualified_name,
                file=self.rel_path,
                line=line_num,
                language="cpp",
                is_test=self.is_test or func_name.startswith("test_"),
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=sid,
                relation=EdgeRelation.DEFINES,
            ))

            # Normalize multi-line params to single line for processing
            params_normalized = ' '.join(params_str.split())
            self._process_function_signature(qualified_name, return_type, params_normalized, sid)
            self._process_function_body(func_body, sid, params_normalized, class_qualifier or "")

    def _process_function_signature(self, func_name: str, return_type: str,
                                   params_str: str, func_id: str) -> None:
        """Process return type and parameters for produces/consumes edges."""
        return_type = return_type.strip()

        # PRODUCES: return type (if non-void, non-primitive)
        if return_type and return_type != "void" and not _is_builtin_cpp_type(return_type):
            base_type = re.sub(r'[\*&\s]', '', return_type)
            target_id = self._resolve_type(base_type)
            if target_id:
                self.graph.add_edge(Edge(
                    from_id=func_id,
                    to_id=target_id,
                    relation=EdgeRelation.PRODUCES,
                    via="return_value",
                    relay=True if self.should_relay else None,
                ))

        # CONSUMES: parameters
        if params_str:
            self._process_function_params(func_id, params_str)

    def _process_function_params(self, func_id: str, params_str: str) -> None:
        """Extract parameters and emit CONSUMES or MODIFIES edges."""
        params = [p.strip() for p in params_str.split(',') if p.strip()]

        for param in params:
            if param == "void" or param == "":
                continue

            # Extract parameter name (last identifier)
            parts = param.split()
            if len(parts) < 1:
                continue

            param_type_str = " ".join(parts[:-1])

            # Classify the parameter passing style:
            #   T*           (non-const pointer)   → modifies
            #   T&           (non-const reference)  → modifies
            #   const T*     (const pointer)         → consumes
            #   const T&     (const reference)       → consumes
            #   T            (value)                 → consumes
            is_ptr = "*" in param_type_str
            is_const_ptr = "const" in param_type_str and "*" in param_type_str
            is_non_const_ref = "&" in param_type_str and "const" not in param_type_str
            is_modifying = (is_ptr and not is_const_ptr) or is_non_const_ref

            # Extract base type: remove qualifiers and pointer/reference markers
            base_type = re.sub(r'\b(?:const|volatile|static|extern|register)\b', '', param_type_str)
            base_type = re.sub(r'[\*&\[\]]', ' ', base_type)
            base_type = base_type.split()[0] if base_type.split() else ""

            if not base_type or _is_builtin_cpp_type(base_type):
                continue

            resolved_id = self._resolve_type(base_type)
            unresolved = resolved_id is None
            target_id: str = resolved_id if resolved_id else f"unresolved::{base_type}"

            role = "control" if self._is_control_type(base_type) else "data"

            if is_modifying:
                # Non-const pointer or non-const reference → modifies
                self.graph.add_edge(Edge(
                    from_id=func_id,
                    to_id=target_id,
                    relation=EdgeRelation.MODIFIES,
                    relay=True if self.should_relay else None,
                    unresolved=unresolved,
                ))
            else:
                # Const or value parameter → consumes
                self.graph.add_edge(Edge(
                    from_id=func_id,
                    to_id=target_id,
                    relation=EdgeRelation.CONSUMES,
                    role=role,
                    unresolved=unresolved,
                ))

    def _process_function_body(self, body: str, func_id: str, params_str: str = "",
                               class_name: str = "") -> None:
        """Scan function body for calls and emit CALLS edges."""
        # Track which call locations we've already processed to avoid duplicates
        processed_positions = set()
        call_seq = 0

        # ------------------------------------------------------------------
        # Build parameter type map from function signature.
        # Pattern: TypeName[*] paramname
        # ------------------------------------------------------------------
        param_var_types: Dict[str, str] = {}
        if params_str:
            params = [p.strip() for p in params_str.split(',') if p.strip()]
            for param in params:
                if param == "void" or param == "":
                    continue
                # Extract parameter name (last identifier) and type (all but last)
                parts = param.split()
                if len(parts) < 1:
                    continue
                param_name = parts[-1].lstrip('*&')
                param_type_str = " ".join(parts[:-1])
                # Extract base type: remove qualifiers and pointer/reference markers
                base_type = re.sub(r'\b(?:const|volatile|static|extern|register)\b', '', param_type_str)
                base_type = re.sub(r'[\*&\[\]]', ' ', base_type)
                base_type = base_type.split()[0] if base_type.split() else ""
                if base_type and not _is_builtin_cpp_type(base_type) and not _is_likely_builtin_cpp(base_type):
                    param_var_types[param_name] = base_type

        # ------------------------------------------------------------------
        # Gap 3: Build a local variable type map from explicit declarations
        # inside this function body.  Pattern: TypeName[*] varname = / ( / ;
        # Augments the file-scope var_types with function-local variables so
        # that  obj->method()  can be resolved when obj is a local pointer.
        # Only tracks types starting with an uppercase letter (user types).
        # ------------------------------------------------------------------
        local_var_types: Dict[str, str] = {}
        local_decl_pattern = r'\b([A-Z]\w+)\s*\*?\s+(\w+)\s*[=({;]'
        for m in re.finditer(local_decl_pattern, body):
            type_name = m.group(1)
            var_name = m.group(2)
            if not _is_builtin_cpp_type(type_name) and not _is_likely_builtin_cpp(type_name):
                local_var_types[var_name] = type_name

        # Merge member variable types from headers, parameter types, file-scope, and local type maps;
        # local declarations take precedence
        effective_var_types: Dict[str, str] = {**self._member_var_types, **self.var_types, **param_var_types, **local_var_types}

        # Find simple function calls: identifier(
        simple_pattern = r'\b([A-Za-z_]\w*)\s*\('
        for match in re.finditer(simple_pattern, body):
            pos = match.start()
            if pos in processed_positions:
                continue

            call_name = match.group(1)
            call_seq += 1

            # Check if this is part of a scoped call (e.g., Foo::bar() or obj->bar())
            # by looking for :: or -> before the call name
            if pos > 0:
                back_search = body[max(0, pos - 20):pos]
                if "::" in back_search or "->" in back_search or "." in back_search:
                    processed_positions.add(pos)
                    continue

            if _is_likely_builtin_cpp(call_name):
                continue

            # Try to resolve the call target
            resolved = self._resolve_call_target(call_name)
            # Inheritance fallback: try Base.method for each base class of the
            # enclosing class. Only fires when class_name is known (impl files).
            if resolved is None and class_name:
                for base in self._class_bases.get(class_name, []):
                    resolved = self._resolve_call_target(f"{base}.{call_name}")
                    if resolved is not None:
                        break
            if resolved is None:
                final_target: str = f"unresolved::{call_name}"
                unresolved = True
            else:
                final_target = resolved
                unresolved = False

            self.graph.add_edge(Edge(
                from_id=func_id,
                to_id=final_target,
                relation=EdgeRelation.CALLS,
                unresolved=unresolved,
                seq=call_seq,
            ))
            processed_positions.add(pos)

        # Find scoped method calls: Namespace::method( or obj->method( or obj.method(
        scoped_pattern = r'(?:(\w+)\s*(?:::|->|\.)\s*)?(\w+)\s*\('
        for match in re.finditer(scoped_pattern, body):
            pos = match.start()
            if pos in processed_positions:
                continue

            namespace_or_obj = match.group(1)
            method_name = match.group(2)

            # Only process if we found a namespace/object prefix
            if namespace_or_obj is None:
                continue

            call_seq += 1

            if _is_likely_builtin_cpp(method_name):
                continue

            # Try to resolve the call target.
            # Use effective_var_types (file-scope + local) for type-guided resolution.
            resolved2: Optional[str] = None
            declared_type = effective_var_types.get(namespace_or_obj)
            if declared_type:
                # 1. Try TypeName.method (most specific — matches label format)
                resolved2 = self._resolve_call_target(f"{declared_type}.{method_name}")
                if resolved2 is None:
                    resolved2 = self._resolve_call_target(method_name)

            # 2. Try the method name alone
            if resolved2 is None:
                resolved2 = self._resolve_call_target(method_name)

            # 3. Try the qualified form (namespace.method — matches label format)
            if resolved2 is None:
                resolved2 = self._resolve_call_target(f"{namespace_or_obj}.{method_name}")

            if resolved2 is not None:
                final_target2: str = resolved2
                unresolved2 = False
            else:
                # Before giving up: if variable type is known, try resolving to
                # the type node itself (e.g. g_bus.publish() → EventBus type node).
                # This gives convergence: multiple dispatch_event symbols → 1 shared type node.
                unresolved2 = True
                if declared_type:
                    type_node_id = self._resolve_type(declared_type)
                    if type_node_id is not None:
                        final_target2 = type_node_id
                        unresolved2 = False
                    else:
                        final_target2 = f"unresolved::{declared_type}::{method_name}"
                else:
                    final_target2 = f"unresolved::{namespace_or_obj}::{method_name}"

            self.graph.add_edge(Edge(
                from_id=func_id,
                to_id=final_target2,
                relation=EdgeRelation.CALLS,
                unresolved=unresolved2,
                seq=call_seq,
            ))
            processed_positions.add(pos)

    def _resolve_call_target(self, name: str) -> Optional[str]:
        """Try to find a known symbol matching this call name.

        Priority (in order):
          1. Same file
          2. Same directory (same parent dir)
          3. Same module, prefer .cc/.cpp/.c over .h/.hpp/.hxx
          4. Any match, prefer .cc/.cpp/.c over .h/.hpp/.hxx
        """
        # Search known_symbol_ids for a match
        file_prefix = f"{self.feature}::{self.rel_path}::"

        same_file = []
        same_dir = []
        same_module = []
        any_match = []

        # Compute the parent directory prefix for same-directory matching
        rel_dir = str(self.rel_path).replace("\\", "/").rsplit("/", 1)[0] if "/" in str(self.rel_path).replace("\\", "/") else ""
        dir_prefix = f"{self.feature}::{rel_dir}/" if rel_dir else ""

        for nid in self.known:
            label = nid.split("::")[-1]
            if label != name:
                continue

            if nid.startswith(file_prefix):
                same_file.append(nid)
            elif dir_prefix and nid.startswith(dir_prefix):
                same_dir.append(nid)
            elif f"::{self.module_name}::" in nid:
                same_module.append(nid)
            elif label == name:
                any_match.append(nid)

        # Helper: prefer .cc/.cpp/.c over .h/.hpp/.hxx
        def _prefer_implementation_over_declaration(candidates: list) -> Optional[str]:
            """From a list of candidates, prefer implementation files."""
            if not candidates:
                return None

            # Separate by file extension type
            impl_files = []  # .cc, .cpp, .cxx, .c
            decl_files = []  # .h, .hpp, .hxx
            other_files = []

            for cand in candidates:
                # Extract file path from candidate ID
                # Format: feature::rel/path/file.ext::SymbolName
                parts = cand.split("::")
                if len(parts) >= 2:
                    filepath = parts[1]  # rel/path/file.ext
                    lower_ext = filepath.lower()

                    if lower_ext.endswith(('.cc', '.cpp', '.cxx', '.c')):
                        impl_files.append(cand)
                    elif lower_ext.endswith(('.h', '.hpp', '.hxx')):
                        decl_files.append(cand)
                    else:
                        other_files.append(cand)
                else:
                    other_files.append(cand)

            # Return in priority order: implementation > declaration > other
            if impl_files:
                return impl_files[0]
            if decl_files:
                return decl_files[0]
            if other_files:
                return other_files[0]
            return None

        if same_file:
            return _prefer_implementation_over_declaration(same_file)
        if same_dir:
            return _prefer_implementation_over_declaration(same_dir)
        if same_module:
            return _prefer_implementation_over_declaration(same_module)
        if any_match:
            return _prefer_implementation_over_declaration(any_match)
        return None


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _rel(root: Path, filepath: Path) -> str:
    """Compute relative path from root, normalized to forward slashes."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        rel = filepath
    return str(rel).replace("\\", "/")


def _module_name(rel_path: str) -> str:
    """Convert a relative file path to a module name (file stem without extension)."""
    # e.g. broker/router.h → router
    name = rel_path.replace("\\", "/").split("/")[-1]
    # Remove extension
    if "." in name:
        name = name[:name.rfind(".")]
    return name


_BUILTIN_CPP_TYPES = frozenset({
    "void", "bool", "char", "short", "int", "long", "float", "double",
    "signed", "unsigned", "auto",
    "size_t", "int8_t", "int16_t", "int32_t", "int64_t",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
})

_BUILTIN_CPP_FUNCS = frozenset({
    "printf", "scanf", "malloc", "free", "memset", "memcpy",
    "strlen", "strcpy", "strcmp",
    "cout", "cin", "endl",
    "std", "vector", "map", "set", "queue", "stack",
    # C/C++ keywords that look like calls due to parentheses
    "sizeof", "alignof", "typeof", "decltype",
    "if", "for", "while", "switch", "return", "static_assert",
    "new", "delete", "throw", "catch",
})


def _is_builtin_cpp_type(name: str) -> bool:
    """Return True if this is a built-in C++ type."""
    return name in _BUILTIN_CPP_TYPES


def _is_likely_builtin_cpp(name: str) -> bool:
    """Return True if this name is likely a built-in function or type."""
    return name in _BUILTIN_CPP_FUNCS or name in _BUILTIN_CPP_TYPES
