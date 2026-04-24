"""
parser_python.py — AST-based Python file parser.

Extracts nodes and edges from a single .py file:
  - imports       (file → module)
  - defines       (file → class/function)
  - contains      (class → method)
  - produces      (function → type it emits via return or mutation)
  - consumes      (function → type it takes as read-only input)
  - modifies      (function → typed parameter it mutates in-place)
  - uses_type     (function → type annotation, undirected fallback)
  - calls         (function → called symbol, best-effort name resolution)

Pass 1: parse_file() — emits all nodes + all edges it can resolve locally.
         Unresolvable `calls` edges are marked unresolved=True.
         Body walking detects mutation patterns and confirms relay via return analysis.
Pass 2: resolve_calls() — re-walks call edges, upgrades unresolved ones
         using a cross-file symbol registry built from Pass 1 results.

Reusable across any Python project.
"""

import ast
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple, Union

from schema import (
    Node, Edge, NodeType, EdgeRelation,
    file_id, symbol_id, type_id, stdlib_module_id, is_test_file,
)
from graph import CodeGraph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(feature: str, root: Path, filepath: Path,
               known_symbol_ids: Optional[Set[str]] = None,
               known_return_types: Optional[Dict[str, str]] = None,
               known_file_ids: Optional[Dict[str, str]] = None,
               filter_stdlib: bool = False) -> CodeGraph:
    """
    Parse a single Python file and return a CodeGraph.

    Args:
        feature:            Feature name (e.g. "autofill")
        root:               Project root Path (for computing relative paths)
        filepath:           Absolute path to the .py file
        known_symbol_ids:   Set of all symbol/type IDs known across the feature
                            (used to resolve `calls` edges cross-file).
                            If None, all call targets are marked unresolved.
        known_return_types: Dict mapping function label → return type class name,
                            built from Pass 1 across all files.  Used to resolve
                            instance method calls like db.execute() when db was
                            assigned from a typed factory function.
        known_file_ids:     Dict mapping module name/stem → file_id, for detecting
                            local project imports and distinguishing them from stdlib.
    """
    rel_path = _rel(root, filepath)
    source = filepath.read_text(encoding="utf-8", errors="replace")

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        # Return empty graph for unparseable files rather than crashing
        return CodeGraph(feature)

    visitor = _FileVisitor(
        feature=feature,
        rel_path=rel_path,
        module_name=_module_name(rel_path),
        is_test=is_test_file(rel_path),
        known_symbol_ids=known_symbol_ids or set(),
        known_return_types=known_return_types or {},
        known_file_ids=known_file_ids or {},
        filter_stdlib=filter_stdlib,
    )
    visitor.visit(tree)
    return visitor.graph


def resolve_calls(graph: CodeGraph, known_symbol_ids: Set[str]) -> None:
    """
    In-place pass 2: upgrade unresolved `calls` edges where the target
    can now be found in known_symbol_ids.
    """
    to_upgrade = [
        e for e in graph.edges
        if e.relation == EdgeRelation.CALLS and e.unresolved
    ]
    for edge in to_upgrade:
        if edge.to_id in known_symbol_ids:
            edge.unresolved = False


# ---------------------------------------------------------------------------
# Internal AST visitor
# ---------------------------------------------------------------------------

class _FileVisitor(ast.NodeVisitor):
    def __init__(self, feature: str, rel_path: str, module_name: str,
                 is_test: bool, known_symbol_ids: Set[str],
                 known_return_types: Optional[Dict[str, str]] = None,
                 known_file_ids: Optional[Dict[str, str]] = None,
                 filter_stdlib: bool = False):
        self.feature = feature
        self.rel_path = rel_path
        self.module_name = module_name
        self.is_test = is_test
        self.known = known_symbol_ids
        self.graph = CodeGraph(feature)
        self._filter_stdlib = filter_stdlib

        # State for tracking current class context
        self._current_class: Optional[str] = None      # class name
        self._current_class_id: Optional[str] = None   # full type_id
        self._current_func: Optional[str] = None       # symbol name (qualified)
        self._current_func_id: Optional[str] = None    # full symbol_id
        self._call_seq: int = 0                         # sequence counter for calls within a function

        # Names brought into scope by "from x import y [as z]".
        # Maps local_name -> True for every explicitly imported symbol.
        # Used to skip same-file resolution bias for imported bare names.
        self._import_names: Set[str] = set()

        # Cross-file function label → return type class name (from Pass 1).
        # Used to resolve instance method calls like db.execute() where db was
        # assigned from a typed factory function in another file.
        self._known_return_types: Dict[str, str] = known_return_types or {}

        # Same-file function label → return type class name (built during this pass).
        self._return_types: Dict[str, str] = {}

        # Per-function scope: variable/parameter name → type class name.
        # Seeded from annotated parameters; extended by assignment tracking.
        self._local_var_types: Dict[str, str] = {}

        # Per-function: set of parameter arg names that were mutated in the body.
        # Used after body-walk to decide consumes vs. modifies per annotated param.
        self._mutated_params: Set[str] = set()

        # Mapping: module name/stem → file_id, for local file import detection.
        # Distinguishes local imports from stdlib (e.g. barcode_database from logging).
        self._known_file_ids: Dict[str, str] = known_file_ids or {}

        # Maps local alias → module name for unresolved call annotation.
        # e.g. "import numpy as np" → {"np": "numpy"}
        # e.g. "import logging" → {"logging": "logging"}
        # e.g. "from os import path" → {"path": "os"}
        self._import_module_of: Dict[str, str] = {}

        # Per-class: self.attr_name → type class name, built from __init__ body.
        # Populated by: self.x = ClassName() and annotated __init__ params assigned to self.x
        self._instance_attr_types: Dict[str, str] = {}

        # File node
        self._file_node_id = file_id(feature, rel_path)
        self.graph.add_node(Node(
            id=self._file_node_id,
            type=NodeType.FILE,
            label=Path(rel_path).name,
            file=rel_path,
            line=None,
            is_test=is_test,
        ))

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _resolve_module_id(self, module_name: str) -> str:
        """
        Resolve a module name to its file_id or stdlib_module_id.

        For a module name like "barcode_database" or "household_inventory.src.barcode_database":
        - Check full dotted path match in known_file_ids
        - Also check stem-only match (last component after splitting by ".")
        - If either matches, return the corresponding file_id
        - Otherwise fall through to stdlib_module_id (for true stdlib modules)
        """
        # Try full dotted path match
        if module_name in self._known_file_ids:
            return self._known_file_ids[module_name]

        # Try stem-only match (last component)
        stem = module_name.split(".")[-1]
        if stem in self._known_file_ids:
            return self._known_file_ids[stem]

        # Not a known local file, fall back to stdlib
        return stdlib_module_id(module_name)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            # Check if this is a local file import (in known_file_ids)
            mod_id = self._resolve_module_id(alias.name)
            self.graph.add_node(Node(
                id=mod_id,
                type=NodeType.FILE,
                label=alias.name,
                file=None,
                line=node.lineno,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=mod_id,
                relation=EdgeRelation.IMPORTS,
            ))
            # Track alias → module name for via_module annotation on unresolved calls
            local_name = alias.asname if alias.asname else alias.name.split(".")[0]
            self._import_module_of[local_name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            # Check if this is a local file import (in known_file_ids)
            mod_id = self._resolve_module_id(node.module)
            self.graph.add_node(Node(
                id=mod_id,
                type=NodeType.FILE,
                label=node.module,
                file=None,
                line=node.lineno,
            ))
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=mod_id,
                relation=EdgeRelation.IMPORTS,
            ))
        # Record each imported name (or its alias) so call resolution can
        # skip same-file bias for bare names that came from another module.
        for alias in node.names:
            local_name = alias.asname if alias.asname else alias.name
            # Only record the simple name portion (e.g. "get_theme_manager" not "module.fn")
            simple = local_name.split(".")[-1]
            self._import_names.add(simple)
            # Track alias → module name for via_module annotation on unresolved calls
            if node.module:
                self._import_module_of[simple] = node.module
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Class definitions → type nodes
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_dc = _has_decorator(node, "dataclass")
        tid = type_id(self.feature, self.module_name, node.name)

        self.graph.add_node(Node(
            id=tid,
            type=NodeType.TYPE,
            label=node.name,
            file=self.rel_path,
            line=node.lineno,
            is_dataclass=is_dc,
            is_test=self.is_test,
        ))
        self.graph.add_edge(Edge(
            from_id=self._file_node_id,
            to_id=tid,
            relation=EdgeRelation.DEFINES,
        ))

        # Visit methods inside the class with context set
        prev_class = self._current_class
        prev_class_id = self._current_class_id
        self._current_class = node.name
        self._current_class_id = tid

        for child in node.body:
            self.visit(child)

        self._instance_attr_types = {}
        self._current_class = prev_class
        self._current_class_id = prev_class_id

    # ------------------------------------------------------------------
    # Annotated class fields (dataclass fields, typed attributes)
    # ------------------------------------------------------------------

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # Only process class-level annotations (not function-local ones)
        if self._current_class is None or self._current_class_id is None or self._current_func is not None:
            return
        # Only named targets (skip subscript/tuple targets)
        if not isinstance(node.target, ast.Name):
            return

        field_name = node.target.id
        qualified_name = f"{self._current_class}.{field_name}"
        sid = symbol_id(self.feature, self.rel_path, qualified_name)

        # Produce a human-readable annotation string (e.g. "List[Tuple[str, str]]")
        try:
            annot_str: Optional[str] = ast.unparse(node.annotation)
        except Exception:
            annot_str = None

        self.graph.add_node(Node(
            id=sid,
            type=NodeType.SYMBOL,
            label=qualified_name,
            file=self.rel_path,
            line=node.lineno,
            is_test=self.is_test,
            annotation=annot_str,
        ))
        self.graph.add_edge(Edge(
            from_id=self._current_class_id,
            to_id=sid,
            relation=EdgeRelation.CONTAINS,
        ))

        # Emit uses_type for the field's annotation
        for tname in _annotation_names(node.annotation):
            if _is_builtin_type(tname):
                continue
            target_id = self._resolve_type(tname)
            if target_id:
                self.graph.add_edge(Edge(
                    from_id=sid,
                    to_id=target_id,
                    relation=EdgeRelation.USES_TYPE,
                ))

        # Seed instance attribute type map so self.field.method() calls in other
        # methods can resolve against the declared type (e.g. conn: DatabaseConnection).
        for tname in _annotation_names(node.annotation):
            if not _is_builtin_type(tname):
                self._instance_attr_types[field_name] = tname
                break

    # ------------------------------------------------------------------
    # Function / method definitions → symbol nodes
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)

    def visit_If(self, node: ast.If) -> None:
        """
        Detect if __name__ == "__main__": blocks at module level.
        When found, mark the called function (if any) as an entry point.

        Handles two patterns:
          1. Bare-name call: main()
          2. Instance-construction: app = MyClass(); app.run()
        """
        # Only process top-level if statements (not nested inside functions/classes)
        if self._current_func is not None or self._current_class is not None:
            self.generic_visit(node)
            return

        if not _is_main_check(node.test):
            self.generic_visit(node)
            return

        # Map: local_var_name → class_name for assignments like `app = MyClass()`
        instance_vars: Dict[str, str] = {}

        # First pass: collect instance assignments (var = ClassName())
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Call)
                    and isinstance(stmt.value.func, ast.Name)):
                var_name = stmt.targets[0].id
                class_name = stmt.value.func.id
                instance_vars[var_name] = class_name

        # Second pass: mark entry points from calls in the __main__ body
        for stmt in node.body:
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
                continue
            call_func = stmt.value.func

            # Pattern 1: bare-name call — main(), run(), etc.
            if isinstance(call_func, ast.Name):
                call_name = call_func.id
                if call_name:
                    target_id = self._resolve_call_target(call_name, skip_same_file=False)
                    if target_id:
                        for n in self.graph.nodes:
                            if n.id == target_id:
                                n.entry_point = True
                                break

            # Pattern 2: instance method call — app.run_interactive_mode()
            elif (isinstance(call_func, ast.Attribute)
                    and isinstance(call_func.value, ast.Name)):
                receiver_name = call_func.value.id
                method_name = call_func.attr
                class_name = instance_vars.get(receiver_name)
                if class_name:
                    # Try to resolve ClassName.method_name
                    qualified = f"{class_name}.{method_name}"
                    target_id = self._resolve_call_target(qualified, skip_same_file=False)
                    if target_id is None:
                        target_id = self._resolve_call_target(method_name, skip_same_file=False)
                    if target_id:
                        for n in self.graph.nodes:
                            if n.id == target_id:
                                n.entry_point = True
                                break

        self.generic_visit(node)

    def _handle_function(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> None:
        if self._current_class:
            qualified_name = f"{self._current_class}.{node.name}"
        else:
            qualified_name = node.name

        sid = symbol_id(self.feature, self.rel_path, qualified_name)
        is_route = _is_route_handler(node)

        self.graph.add_node(Node(
            id=sid,
            type=NodeType.SYMBOL,
            label=qualified_name,
            file=self.rel_path,
            line=node.lineno,
            is_test=self.is_test or node.name.startswith("test_"),
            entry_point=is_route,
        ))

        if self._current_class_id:
            # method → contains edge from class
            self.graph.add_edge(Edge(
                from_id=self._current_class_id,
                to_id=sid,
                relation=EdgeRelation.CONTAINS,
            ))
        else:
            # module-level function → defines edge from file
            self.graph.add_edge(Edge(
                from_id=self._file_node_id,
                to_id=sid,
                relation=EdgeRelation.DEFINES,
            ))

        # Build annotated_params: arg_name → type_class_name (first non-builtin
        # type extracted from the parameter's annotation).
        all_args = (
            node.args.args
            + node.args.posonlyargs
            + node.args.kwonlyargs
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        )
        annotated_params: Dict[str, str] = {}
        for arg in all_args:
            if arg.arg in ("self", "cls"):
                continue
            if arg.annotation:
                for tname in _annotation_names(arg.annotation):
                    if not _is_builtin_type(tname):
                        annotated_params[arg.arg] = tname
                        break

        # Emit produces edge for annotated return type.
        # Pass param type names for relay detection (return type = param type → relay).
        param_type_names = list(annotated_params.values())
        self._extract_return_type_edges(node, sid, param_type_names)

        # Store this function's return type for same-file instance-method resolution.
        # Gap 1: later functions in this file can track  x = this_func() → x: ReturnType.
        if node.returns:
            for tname in _annotation_names(node.returns):
                if not _is_builtin_type(tname):
                    self._return_types[qualified_name] = tname
                    # Also store the bare method name so callers inside the same
                    # file can look it up without knowing the class prefix.
                    if "." in qualified_name:
                        self._return_types[node.name] = tname
                    break

        # Collect param arg names (excluding self/cls) for mutation + relay detection.
        param_arg_names = {
            arg.arg for arg in all_args if arg.arg not in ("self", "cls")
        }

        # Save/restore per-function state (supports nested function defs).
        prev_func = self._current_func
        prev_func_id = self._current_func_id
        prev_local_var_types = self._local_var_types
        prev_mutated_params = self._mutated_params

        self._current_func = qualified_name
        self._current_func_id = sid
        self._call_seq = 0
        # Seed local type map with annotated parameters.
        self._local_var_types = dict(annotated_params)
        self._mutated_params = set()

        # For __init__, seed instance attr types from annotated parameters.
        # Pattern B: def __init__(self, db: DatabaseManager) → self.db_manager = db
        # We can't track which param maps to which self.attr statically without
        # reading the body, so we scan the body for `self.x = param_name` assignments
        # where param_name is in annotated_params.
        if node.name == "__init__" and self._current_class:
            for stmt in ast.walk(node):
                if (isinstance(stmt, ast.Assign)
                        and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Attribute)
                        and isinstance(stmt.targets[0].value, ast.Name)
                        and stmt.targets[0].value.id == "self"):
                    attr_name = stmt.targets[0].attr
                    val = stmt.value
                    # Pattern C: self.x = factory_func(...) where factory_func has
                    # a known annotated return type (checked before Pattern A so that
                    # factory function names don't get recorded as the type).
                    if (isinstance(val, ast.Call)
                            and isinstance(val.func, ast.Name)):
                        call_name = val.func.id
                        ret_type = (self._known_return_types.get(call_name)
                                    or self._return_types.get(call_name))
                        if ret_type:
                            self._instance_attr_types[attr_name] = ret_type
                        else:
                            # Pattern A: self.x = ClassName(...)
                            self._instance_attr_types[attr_name] = call_name
                    # Pattern A (attribute): self.x = module.ClassName(...)
                    elif (isinstance(val, ast.Call)
                            and isinstance(val.func, ast.Attribute)):
                        call_name = val.func.attr
                        ret_type = (self._known_return_types.get(call_name)
                                    or self._return_types.get(call_name))
                        self._instance_attr_types[attr_name] = ret_type if ret_type else call_name
                    # Pattern B: self.x = param_name where param_name has annotation
                    elif (isinstance(val, ast.Name)
                            and val.id in annotated_params):
                        self._instance_attr_types[attr_name] = annotated_params[val.id]

        self._walk_body(node.body, param_arg_names, sid)
        self._detect_relay_from_return(node, param_arg_names, sid)

        # Emit consumes or modifies for each annotated parameter.
        # After body-walk we know which params were mutated.
        for arg_name, type_name in annotated_params.items():
            if _is_builtin_type(type_name):
                continue
            target_id = self._resolve_type(type_name)
            if not target_id:
                continue

            role = "control" if _is_control_type(type_name) else "data"
            if arg_name in self._mutated_params:
                # Parameter was mutated → modifies edge
                self.graph.add_edge(Edge(
                    from_id=sid,
                    to_id=target_id,
                    relation=EdgeRelation.MODIFIES,
                ))
            else:
                # Parameter was only read → consumes edge
                self.graph.add_edge(Edge(
                    from_id=sid,
                    to_id=target_id,
                    relation=EdgeRelation.CONSUMES,
                    role=role,
                ))

            # Mutable containers always get an additional produces(param_mutation)
            # regardless of whether they were explicitly mutated.
            if _is_mutable_container(type_name):
                self.graph.add_edge(Edge(
                    from_id=sid,
                    to_id=target_id,
                    relation=EdgeRelation.PRODUCES,
                    via="param_mutation",
                ))

        self._current_func = prev_func
        self._current_func_id = prev_func_id
        self._local_var_types = prev_local_var_types
        self._mutated_params = prev_mutated_params

    # ------------------------------------------------------------------
    # Call expressions → calls edges
    # ------------------------------------------------------------------

    def _handle_call(self, node: ast.Call) -> None:
        if self._current_func_id is None:
            return

        # Drop super() calls — super().__init__() would resolve to the current
        # class's own __init__ (same-file priority), producing a spurious self-loop.
        # We have no MRO tracking, so super() calls to external parents must be dropped.
        if _is_super_call(node.func):
            return

        name = _extract_call_name(node.func)
        if name is None:
            return

        # Drop bare self()/cls() calls — PyTorch modules call self(inputs) to invoke
        # __call__. We have no way to resolve this and it produces unresolved::self noise.
        if name in ("self", "cls") and isinstance(node.func, ast.Name):
            return

        receiver, chain_depth = _extract_call_receiver(node.func)

        if self._filter_stdlib and receiver in _STDLIB_RECEIVERS:
            return

        # ------------------------------------------------------------------
        # Instance attribute method call: self.attr.method()
        # receiver == "self" or "cls", chain_depth == 2, name is method
        # Look up self.attr type from _instance_attr_types
        if (receiver in ("self", "cls")
                and chain_depth == 2
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)):
            attr_name = node.func.value.attr
            type_name = self._instance_attr_types.get(attr_name)
            if type_name:
                qualified = f"{type_name}.{name}"
                resolved = self._resolve_call_target(qualified, skip_same_file=True)
                if resolved is None:
                    resolved = self._resolve_call_target(name, skip_same_file=True)
                if resolved is None:
                    if _is_likely_builtin(name):
                        return
                    final_target_ia: str = f"unresolved::{type_name}::{name}"
                    unresolved_ia = True
                else:
                    final_target_ia = resolved
                    unresolved_ia = False
                self._call_seq += 1
                self.graph.add_edge(Edge(
                    from_id=self._current_func_id,
                    to_id=final_target_ia,
                    relation=EdgeRelation.CALLS,
                    unresolved=unresolved_ia,
                    seq=self._call_seq,
                ))
                return

        # ------------------------------------------------------------------
        # Gap 1: Instance method resolution via local variable type map.
        #
        # When the call receiver is a variable with a known type (either from
        # an annotated parameter or from a typed assignment x = some_func()),
        # resolve TypeName.method instead of doing generic name matching.
        # This correctly handles patterns like:
        #   db = get_database()   # get_database() -> PostgresDatabaseUtility
        #   db.execute(query)     # → PostgresDatabaseUtility.execute
        # ------------------------------------------------------------------
        if (receiver is not None
                and receiver not in ("self", "cls")
                and receiver in self._local_var_types):
            type_name = self._local_var_types[receiver]
            # Try the fully qualified form TypeName.method first,
            # then fall back to the bare method name with skip_same_file.
            qualified = f"{type_name}.{name}"
            resolved = self._resolve_call_target(qualified, skip_same_file=True)
            if resolved is None:
                resolved = self._resolve_call_target(name, skip_same_file=True)
            if resolved is None:
                if _is_likely_builtin(name):
                    return
                final_target: str = f"unresolved::{type_name}::{name}"
                unresolved = True
                _via_module: Optional[str] = self._import_module_of.get(receiver)
            else:
                final_target = resolved
                unresolved = False
                _via_module = None
            self._call_seq += 1
            self.graph.add_edge(Edge(
                from_id=self._current_func_id,
                to_id=final_target,
                relation=EdgeRelation.CALLS,
                unresolved=unresolved,
                seq=self._call_seq,
                via_module=_via_module if unresolved else None,
            ))
            return

        # ------------------------------------------------------------------
        # Existing generic call resolution
        # ------------------------------------------------------------------

        # Try to resolve against known symbols in this feature.
        # Skip same-file bias when:
        #   (a) the name was explicitly imported from another module, OR
        #   (b) the call is a chained attribute call with depth >= 2,
        #       e.g. self._attr.method() — the method belongs to the attr's type,
        #       not to the enclosing class.
        is_imported_name = receiver is None and name in self._import_names
        is_chained_attr = chain_depth >= 2
        is_external_obj = receiver is not None and receiver not in ("self", "cls")
        skip_same_file = is_imported_name or is_chained_attr or is_external_obj
        resolved = self._resolve_call_target(name, skip_same_file=skip_same_file)
        if resolved is None:
            # Don't clutter the graph with unresolved builtins/stdlib calls
            if _is_likely_builtin(name):
                return
            final_target2: str = f"unresolved::{name}"
            unresolved = True
            # Annotate with originating module when the name is a known import alias
            _via_module2: Optional[str] = (
                self._import_module_of.get(receiver)
                if receiver is not None
                else self._import_module_of.get(name)
            )
        else:
            final_target2 = resolved
            unresolved = False
            _via_module2 = None

        self._call_seq += 1
        self.graph.add_edge(Edge(
            from_id=self._current_func_id,
            to_id=final_target2,
            relation=EdgeRelation.CALLS,
            unresolved=unresolved,
            seq=self._call_seq,
            via_module=_via_module2 if unresolved else None,
        ))

    def _walk_body(
        self,
        stmts: List,
        param_names: Set[str],
        func_id: str,
    ) -> None:
        """Walk function body statements in order for calls and mutation detection."""
        for stmt in stmts:
            # Process only expression-level calls from this statement — NOT calls
            # inside nested block bodies (if/try/for bodies).  Block bodies are
            # handled by the recursion below so that assignment tracking (e.g.
            # db = get_database()) fires before sibling calls (db.execute()) in
            # the same nested scope, enabling Gap 1 instance-method resolution.
            for node in _direct_call_nodes(stmt):
                self._handle_call(node)

            # Gap 1: Track local variable type from typed assignment.
            # Pattern: x = some_func() where some_func has a known return type.
            # This populates _local_var_types so subsequent x.method() calls
            # can resolve to the concrete type.
            if isinstance(stmt, ast.Assign):
                if (len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and isinstance(stmt.value, ast.Call)):
                    var_name = stmt.targets[0].id
                    call_name = _extract_call_name(stmt.value.func)
                    if call_name:
                        ret_type = (self._return_types.get(call_name)
                                    or self._known_return_types.get(call_name))
                        if ret_type:
                            self._local_var_types[var_name] = ret_type
                # Gap 1b: Track local variable type from instance attribute assignment.
                # Pattern: x = self.attr or x = cls.attr where attr is in _instance_attr_types.
                # This enables resolution of x.method() calls when x is assigned from an instance attribute.
                elif (len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and isinstance(stmt.value, ast.Attribute)
                        and isinstance(stmt.value.value, ast.Name)
                        and stmt.value.value.id in ("self", "cls")):
                    var_name = stmt.targets[0].id
                    attr_name = stmt.value.attr
                    if attr_name in self._instance_attr_types:
                        self._local_var_types[var_name] = self._instance_attr_types[attr_name]

            # Attribute mutation: obj.field = x  or  obj.field += x
            if isinstance(stmt, (ast.Assign, ast.AugAssign)):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    if isinstance(target, ast.Attribute):
                        root = _root_name(target)
                        if root and root in param_names:
                            if root in self._local_var_types:
                                # Annotated param: record mutation for modifies detection
                                self._mutated_params.add(root)
                            else:
                                # Unannotated param: keep existing unresolved produces
                                self._emit_param_mutation(root, func_id)

            # Mutating method calls: obj.append(...), obj.update(...), etc.
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if isinstance(call.func, ast.Attribute):
                    if call.func.attr in _MUTATING_METHODS:
                        root = _root_name(call.func)
                        if root and root in param_names:
                            if root in self._local_var_types:
                                self._mutated_params.add(root)
                            else:
                                self._emit_param_mutation(root, func_id)

            # Recurse into control flow blocks to preserve statement order
            for child_stmts in _child_statement_lists(stmt):
                self._walk_body(child_stmts, param_names, func_id)

    def _emit_param_mutation(self, param_name: str, func_id: str) -> None:
        """Emit produces(via:param_mutation) for an unannotated mutated parameter."""
        # Only emit if there's no annotation-based edge already — check by seeing
        # if we already have a produces edge for this func. Since we don't track
        # by param name here, we use uses_type as the fallback instead.
        # Emit uses_type so the graph at least captures the connection.
        # A future mypy enrichment pass can upgrade this to produces/consumes.
        # For now, mark it unresolved so the viewer can show it distinctly.
        target_id = f"unresolved::mutated_param::{param_name}"
        self.graph.add_edge(Edge(
            from_id=func_id,
            to_id=target_id,
            relation=EdgeRelation.PRODUCES,
            via="param_mutation",
            unresolved=True,
        ))

    def _detect_relay_from_return(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        param_names: Set[str],
        func_id: str,
    ) -> None:
        """Upgrade relay=True on produces edges where return value is a param name."""
        # Find all return statements that return a bare name matching a param
        returned_params: Set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value:
                name = _bare_name(child.value)
                if name and name in param_names:
                    returned_params.add(name)

        if not returned_params:
            return

        # Upgrade any produces(via:return_value) edges from this func to relay=True
        for edge in self.graph.edges:
            if (edge.from_id == func_id
                    and edge.relation == EdgeRelation.PRODUCES
                    and edge.via == "return_value"
                    and edge.relay is None):
                edge.relay = True

    # ------------------------------------------------------------------
    # Return type annotation → produces edge
    # ------------------------------------------------------------------

    def _extract_return_type_edges(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        from_id: str,
        param_type_names: List[str],
    ) -> None:
        """Emit produces(via:return_value) edge for the function's return annotation.

        param_type_names: list of type class names from parameter annotations,
        used for relay detection (return type == param type → relay=True).
        """
        if not node.returns:
            return
        for tname in _annotation_names(node.returns):
            if _is_builtin_type(tname):
                continue
            target_id = self._resolve_type(tname)
            if target_id:
                is_relay = tname in param_type_names
                self.graph.add_edge(Edge(
                    from_id=from_id,
                    to_id=target_id,
                    relation=EdgeRelation.PRODUCES,
                    via="return_value",
                    relay=True if is_relay else None,
                ))

    def _resolve_call_target(self, name: str, skip_same_file: bool = False) -> Optional[str]:
        """
        Try to find a known symbol/type ID matching this call name.

        Priority order (most specific to least):
          1. Same-file symbol — nid starts with feature::rel_path:: and label matches
             (skipped when skip_same_file=True, e.g. for obj.method() where obj != self)
          2. Same-module type symbol — nid contains module_name:: and label matches
          3. Any symbol in the registry with matching label (last resort, cross-file)

        skip_same_file should be True when the call receiver is a typed attribute
        (e.g. self._foo.bar()) rather than a bare name or self.bar(). This prevents
        resolving obj.method() to a same-name method on the enclosing class.

        Returns the best match or None.
        """
        # Build the file-scoped ID prefix for same-file priority
        file_prefix = f"{self.feature}::{self.rel_path}::"

        same_file = []
        same_module = []
        any_match = []

        for nid in self.known:
            label = nid.split("::")[-1]
            exact = label == name
            suffix = label.endswith(f".{name}")
            if not exact and not suffix:
                continue

            if nid.startswith(file_prefix):
                same_file.append(nid)
            elif f"::{self.module_name}::" in nid:
                same_module.append(nid)
            elif exact:
                # Cross-file: only accept exact label matches.
                # Suffix matches (ClassName.method) cross-file are unreliable —
                # a bare call to run() should not resolve to IngredientConsolidator.run()
                # in a completely unrelated file.
                any_match.append(nid)

        # Return best match by priority
        if same_file and not skip_same_file:
            return same_file[0]
        if same_module:
            return same_module[0]
        if any_match:
            return any_match[0]
        # When skip_same_file is False, fall back to same-file as last resort.
        # When skip_same_file is True (chained attr / imported name), do NOT fall back —
        # returning None (unresolved) is more honest than returning the wrong same-file symbol.
        if same_file and not skip_same_file:
            return same_file[0]
        return None

    # ------------------------------------------------------------------
    # Type resolution helpers
    # ------------------------------------------------------------------

    def _resolve_type(self, name: str) -> Optional[str]:
        """
        Find a known type node matching this name.

        Priority:
          1. Same-file type (file matches self.rel_path)
          2. Same-module type (module_name in nid)
          3. Any type in registry with matching label
        """
        file_prefix = f"{self.feature}::{self.rel_path}::"

        same_file = []
        same_module = []
        any_match = []

        for nid in self.known:
            label = nid.split("::")[-1]
            if label != name:
                continue
            if nid.startswith(file_prefix):
                same_file.append(nid)
            elif f"::{self.module_name}::" in nid:
                same_module.append(nid)
            else:
                any_match.append(nid)

        if same_file:
            return same_file[0]
        if same_module:
            return same_module[0]
        if any_match:
            return any_match[0]
        return None


# ---------------------------------------------------------------------------
# AST helper utilities
# ---------------------------------------------------------------------------

def _rel(root: Path, filepath: Path) -> str:
    """Compute relative path from root, normalized to forward slashes."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        rel = filepath
    return str(rel).replace("\\", "/")


def _module_name(rel_path: str) -> str:
    """Convert a relative file path to a dotted module name."""
    # e.g. Client_Side/utils/autofill_engine.py → autofill_engine
    name = rel_path.replace("\\", "/").split("/")[-1]
    if name.endswith(".py"):
        name = name[:-3]
    return name


def _has_decorator(node: Union[ast.ClassDef, ast.FunctionDef], name: str) -> bool:
    """Check if a class or function has a specific decorator by name."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == name:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == name:
            return True
    return False


def _is_main_check(node: ast.expr) -> bool:
    """Return True if node is: __name__ == "__main__" or "__main__" == __name__."""
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
        return False
    left = node.left
    right = node.comparators[0] if node.comparators else None
    if not right:
        return False
    if (isinstance(left, ast.Name) and left.id == "__name__"
            and isinstance(right, ast.Constant) and right.value == "__main__"):
        return True
    if (isinstance(left, ast.Constant) and left.value == "__main__"
            and isinstance(right, ast.Name) and right.id == "__name__"):
        return True
    return False


def _is_route_handler(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
    """Return True if the function has a web-framework route decorator.

    Detects Flask (@app.route), FastAPI/aiohttp (@router.get, @app.post, etc.),
    and WebSocket handlers.
    """
    route_attrs = {"route", "get", "post", "put", "delete", "patch", "websocket"}
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in route_attrs:
            return True
        elif isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Attribute) and func.attr in route_attrs:
                return True
            if isinstance(func, ast.Name) and func.id in route_attrs:
                return True
        elif isinstance(dec, ast.Attribute) and dec.attr in route_attrs:
            return True
    return False


def _extract_call_name(node: ast.expr) -> Optional[str]:
    """Extract a simple name from a call expression's func node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_call_receiver(node: ast.expr) -> Tuple[Optional[str], int]:
    """
    Extract the receiver name and chain depth from an attribute call expression.
    Returns (root_name, depth) where depth is the number of attribute hops.

    Examples:
      self.method()       -> ("self", 1)   — direct self call
      self.attr.method()  -> ("self", 2)   — chained: receiver is a typed attribute
      obj.method()        -> ("obj", 1)
      func()              -> (None, 0)     — bare call, no receiver
    """
    if isinstance(node, ast.Attribute):
        root = node.value
        depth = 1
        while isinstance(root, ast.Attribute):
            root = root.value
            depth += 1
        if isinstance(root, ast.Name):
            return root.id, depth
    return None, 0


def _is_super_call(node: ast.expr) -> bool:
    """
    Return True if this call expression is a super().__x__() call.
    Detects: super().__init__(), super().method(), super(A, self).__init__()
    """
    if not isinstance(node, ast.Attribute):
        return False
    val = node.value
    # super().__init__ — val is a Call whose func is Name("super")
    if isinstance(val, ast.Call):
        func = val.func
        if isinstance(func, ast.Name) and func.id == "super":
            return True
    return False


def _annotation_names(node: ast.expr) -> List[str]:
    """Extract type names from an annotation AST node."""
    names = []
    if isinstance(node, ast.Name):
        names.append(node.id)
    elif isinstance(node, ast.Attribute):
        names.append(node.attr)
    elif isinstance(node, ast.Subscript):
        # e.g. List[X], Optional[X], Dict[K, V]
        names.extend(_annotation_names(node.value))
        names.extend(_annotation_names(node.slice))
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            names.extend(_annotation_names(elt))
    elif isinstance(node, ast.BinOp):
        # Python 3.10+ union syntax: X | Y
        names.extend(_annotation_names(node.left))
        names.extend(_annotation_names(node.right))
    return names


# Stdlib module/namespace receivers — when filter_stdlib is on, method calls
# whose receiver matches one of these are suppressed entirely (no edge emitted).
_STDLIB_RECEIVERS: frozenset = frozenset({
    "logging", "logger", "log",
    "os", "sys", "re", "io", "abc",
    "json", "csv", "xml", "html", "urllib", "http",
    "math", "random", "statistics",
    "time", "datetime", "calendar",
    "pathlib", "shutil", "glob", "tempfile",
    "collections", "itertools", "functools", "operator",
    "threading", "multiprocessing", "subprocess", "socket",
    "hashlib", "hmac", "base64", "struct", "codecs",
    "unittest", "pytest", "mock",
    "traceback", "warnings", "gc", "inspect",
    "pickle", "shelve", "sqlite3",
    "copy", "pprint", "textwrap",
    "argparse", "configparser", "enum",
    "typing",
})

_BUILTIN_TYPES = frozenset({
    "int", "str", "float", "bool", "bytes", "None", "NoneType",
    "list", "dict", "set", "tuple", "type", "object",
    "List", "Dict", "Set", "Tuple", "Optional", "Union", "Any",
    "Callable", "Iterator", "Generator", "Iterable", "Sequence",
    "Type", "ClassVar", "Final", "Literal",
    "T", "K", "V",  # common TypeVar names
})

_BUILTIN_FUNCS = frozenset({
    "print", "len", "range", "enumerate", "zip", "map", "filter",
    "sorted", "reversed", "list", "dict", "set", "tuple", "str", "int",
    "float", "bool", "isinstance", "issubclass", "hasattr", "getattr",
    "setattr", "delattr", "super", "type", "object", "vars", "dir",
    "repr", "id", "hash", "abs", "max", "min", "sum", "round", "pow",
    "divmod", "open", "input", "format", "iter", "next", "any", "all",
    "callable", "staticmethod", "classmethod", "property",
    # container mutators
    "append", "extend", "update", "get", "items", "keys", "values",
    "pop", "popitem", "remove", "discard", "add", "clear", "insert",
    # string methods
    "join", "split", "strip", "lstrip", "rstrip", "replace", "encode",
    "decode", "lower", "upper", "title", "capitalize", "casefold",
    "startswith", "endswith", "find", "rfind", "index", "rindex",
    "count", "zfill", "ljust", "rjust", "center", "expandtabs",
    "splitlines", "partition", "rpartition", "isdigit", "isalpha",
    "isalnum", "isspace", "isupper", "islower", "istitle",
    # misc builtins
    "copy", "deepcopy", "format",
})


# Names that suggest a config/settings/policy type — consumes with role:control
_CONTROL_TYPE_HINTS = frozenset({
    "Config", "Settings", "Options", "Params", "Cfg", "Configuration",
    "Preferences", "Policy", "Context", "Ctx",
})

_MUTABLE_CONTAINER_TYPES = frozenset({
    "dict", "list", "Dict", "List", "MutableMapping", "MutableSequence",
    "DefaultDict", "OrderedDict", "Counter", "Deque",
})


def _is_control_type(name: str) -> bool:
    """Return True if type name suggests a config/settings/policy input."""
    if name in _CONTROL_TYPE_HINTS:
        return True
    return any(hint in name for hint in _CONTROL_TYPE_HINTS)


def _is_mutable_container(name: str) -> bool:
    """Return True if type is a mutable container (Python's equivalent of non-const pointer)."""
    return name in _MUTABLE_CONTAINER_TYPES


_MUTATING_METHODS = frozenset({
    "append", "extend", "insert", "remove", "pop", "clear", "reverse", "sort",
    "update", "setdefault", "add", "discard", "difference_update",
    "intersection_update", "symmetric_difference_update",
})


def _root_name(node: ast.expr) -> Optional[str]:
    """Extract the root variable name from an attribute chain. e.g. a.b.c -> 'a'"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return None


def _bare_name(node: ast.expr) -> Optional[str]:
    """Return the name if node is a simple Name node, else None."""
    if isinstance(node, ast.Name):
        return node.id
    return None


def _child_statement_lists(stmt: ast.stmt) -> List[List]:
    """Return all nested statement lists from a compound statement."""
    result = []
    for _, value in ast.iter_fields(stmt):
        if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
            result.append(value)
    return result


def _direct_call_nodes(stmt: ast.stmt):
    """Yield Call nodes from expression-level parts of stmt only.

    Unlike ast.walk(stmt), this does NOT descend into nested block bodies
    (if/for/while/try/with bodies).  Block bodies are handled by the
    _child_statement_lists recursion in _walk_body, which ensures assignment
    tracking fires before any call inside the same nested scope.

    Only yields calls that sit directly in the statement's value/test/iter
    expressions, where ordering relative to assignments is determined by the
    statement type, not by block-level nesting.
    """
    if isinstance(stmt, ast.Expr):
        yield from (n for n in ast.walk(stmt.value) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.Assign):
        for t in stmt.targets:
            yield from (n for n in ast.walk(t) if isinstance(n, ast.Call))
        yield from (n for n in ast.walk(stmt.value) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.AugAssign):
        yield from (n for n in ast.walk(stmt.value) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.AnnAssign):
        if stmt.value:
            yield from (n for n in ast.walk(stmt.value) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.Return):
        if stmt.value:
            yield from (n for n in ast.walk(stmt.value) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.If):
        # Only the test expression (e.g. if func(): ...) — not the body/orelse
        yield from (n for n in ast.walk(stmt.test) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.For):
        yield from (n for n in ast.walk(stmt.iter) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.While):
        yield from (n for n in ast.walk(stmt.test) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.With):
        for item in stmt.items:
            yield from (n for n in ast.walk(item.context_expr) if isinstance(n, ast.Call))
    elif isinstance(stmt, ast.Raise):
        if stmt.exc:
            yield from (n for n in ast.walk(stmt.exc) if isinstance(n, ast.Call))
    # ast.Try / ast.TryStar have no direct expression parts — only block bodies


def _is_builtin_type(name: str) -> bool:
    return name in _BUILTIN_TYPES


def _is_likely_builtin(name: str) -> bool:
    return name in _BUILTIN_FUNCS or name in _BUILTIN_TYPES
