"""
type_expander.py — Recursively expand a named type/class from a CodeGrapher graph.

Reads a tier_symbol.json graph and follows "contains" and "uses_type" edges to
produce a fully resolved nested structure of a named type — including when the
same type definition is reused across multiple fields with different names.

Language-agnostic; depends only on Python stdlib.
"""

import json
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Graph loading and index construction
# ---------------------------------------------------------------------------

def _load_graph(graph_path: str) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Load tier_symbol.json and build lookup structures.

    Returns:
        nodes_by_id    : dict[id -> node dict]
        contains_from  : dict[type_id -> list of node dicts reachable via "contains"]
        uses_type_from : dict[node_id -> list of type node dicts reachable via "uses_type"]
        ptr_depth_map  : dict[(from_id, to_id) -> int] — ptr_depth on contains edges
        typedef_from   : dict[type_id -> list of type nodes where this type is "from" in typedef_of]
        typedef_to     : dict[type_id -> list of type nodes where this type is "to" in typedef_of]
    """
    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes_by_id: dict = {}
    for node in data.get("nodes", []):
        nodes_by_id[node["id"]] = node

    # contains_from: node_id -> list of target node dicts (all contains targets)
    contains_from: dict = defaultdict(list)
    # uses_type_from: node_id -> list of target type node dicts
    uses_type_from: dict = defaultdict(list)
    # ptr_depth on contains edges keyed by (from_id, to_id)
    ptr_depth_map: dict = {}
    # typedef_from: type_id -> list of type nodes aliased by this type (downward chain)
    typedef_from: dict = defaultdict(list)
    # typedef_to: type_id -> list of type nodes that alias this type (upward chain)
    typedef_to: dict = defaultdict(list)

    for edge in data.get("edges", []):
        relation = edge.get("relation", "")
        src = edge.get("from", "")
        tgt = edge.get("to", "")

        if relation == "contains":
            tgt_node = nodes_by_id.get(tgt)
            if tgt_node is not None:
                contains_from[src].append(tgt_node)
                pd = edge.get("ptr_depth", 0) or 0
                ptr_depth_map[(src, tgt)] = pd

        elif relation == "uses_type":
            tgt_node = nodes_by_id.get(tgt)
            if tgt_node is not None and tgt_node.get("type") == "type":
                uses_type_from[src].append(tgt_node)

        elif relation == "typedef_of":
            src_node = nodes_by_id.get(src)
            tgt_node = nodes_by_id.get(tgt)
            if src_node is not None and tgt_node is not None:
                if src_node.get("type") == "type" and tgt_node.get("type") == "type":
                    typedef_from[src].append(tgt_node)
                    typedef_to[tgt].append(src_node)

    return nodes_by_id, contains_from, uses_type_from, ptr_depth_map, typedef_from, typedef_to


# ---------------------------------------------------------------------------
# Type node lookup
# ---------------------------------------------------------------------------

def _find_type_node(nodes_by_id: dict, type_name: str) -> dict | None:
    """
    Find a node with type=="type" and label==type_name.

    Attempts case-sensitive match first; falls back to case-insensitive.
    Returns the node dict, or None if not found.
    """
    # Case-sensitive pass
    for node in nodes_by_id.values():
        if node.get("type") == "type" and node.get("label") == type_name:
            return node

    # Case-insensitive fallback
    lower_name = type_name.lower()
    for node in nodes_by_id.values():
        if node.get("type") == "type" and node.get("label", "").lower() == lower_name:
            return node

    return None


def list_types(graph_path: str) -> list[str]:
    """Return all type names available in the graph, sorted."""
    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    names = sorted(
        node.get("label", "")
        for node in data.get("nodes", [])
        if node.get("type") == "type" and node.get("label")
    )
    return names


# ---------------------------------------------------------------------------
# Field info extraction helpers
# ---------------------------------------------------------------------------

def _short_filename(node: dict) -> str:
    """Return 'filename.py:line' from a node dict, or empty string."""
    file_path = node.get("file", "") or ""
    line = node.get("line")
    name = Path(file_path).name if file_path else ""
    if name and line is not None:
        return f"{name}:{line}"
    return name or ""


def _field_name(symbol_node: dict) -> str:
    """
    Extract the field name from a symbol label like "ClassName.field_name".
    Returns the portion after the last dot, or the full label if no dot.
    """
    label = symbol_node.get("label", "")
    return label.split(".")[-1]


def _resolve_field_type(
    symbol_node: dict,
    uses_type_from: dict,
    nodes_by_id: dict,
) -> dict | None:
    """
    Given a field symbol node, look for a "uses_type" edge pointing to a type
    node.  Returns the target type node dict, or None if the field has no
    custom type annotation in the graph.
    """
    targets = uses_type_from.get(symbol_node["id"], [])
    # Return the first type node found (graphs typically have at most one)
    for tgt in targets:
        if tgt.get("type") == "type":
            return tgt
    return None


# ---------------------------------------------------------------------------
# Typedef chain traversal
# ---------------------------------------------------------------------------

def _expand_typedef_chain(
    type_node: dict,
    typedef_from: dict,
    typedef_to: dict,
    nodes_by_id: dict,
    ptr_depth_map: dict,
    visited: set,
    indent: int,
    lines: list,
    relations: list,
    render_mode: str,
) -> None:
    """
    Recursively expand typedef_of edges from a type node in both directions.

    Shows:
      - Downward chain: what this type aliases (typedef_from edges)
      - Upward chain: what aliases this type (typedef_to edges)
    """
    type_id = type_node["id"]
    type_label = type_node.get("label", type_id)

    # Expand downward chain (what this type aliases)
    downchain = typedef_from.get(type_id, [])
    if downchain and render_mode == "text":
        prefix = "  " * indent
        lines.append(f"{prefix}<<typedefs (aliases)>>")
        for alias_node in downchain:
            alias_label = alias_node.get("label", alias_node["id"])
            alias_loc = _short_filename(alias_node)
            prefix_child = "  " * (indent + 1)
            header = f"{prefix_child}{alias_label}"
            if alias_loc:
                header += f" ({alias_loc})"
            lines.append(header)

            # Recurse into alias
            if alias_node["id"] not in visited:
                visited.add(alias_node["id"])
                _expand_typedef_chain(
                    alias_node,
                    typedef_from,
                    typedef_to,
                    nodes_by_id,
                    ptr_depth_map,
                    visited,
                    indent + 2,
                    lines,
                    relations,
                    render_mode,
                )
                visited.discard(alias_node["id"])

    # Expand upward chain (what aliases this type)
    upchain = typedef_to.get(type_id, [])
    if upchain and render_mode == "text":
        prefix = "  " * indent
        lines.append(f"{prefix}<<aliased-by>>")
        for derived_node in upchain:
            derived_label = derived_node.get("label", derived_node["id"])
            derived_loc = _short_filename(derived_node)
            prefix_child = "  " * (indent + 1)
            header = f"{prefix_child}{derived_label}"
            if derived_loc:
                header += f" ({derived_loc})"
            lines.append(header)

            # Recurse into derived
            if derived_node["id"] not in visited:
                visited.add(derived_node["id"])
                _expand_typedef_chain(
                    derived_node,
                    typedef_from,
                    typedef_to,
                    nodes_by_id,
                    ptr_depth_map,
                    visited,
                    indent + 2,
                    lines,
                    relations,
                    render_mode,
                )
                visited.discard(derived_node["id"])

    # For mermaid: collect typedef relations
    if render_mode == "mermaid":
        for alias_node in downchain:
            alias_label = alias_node.get("label", "")
            relations.append((type_label, alias_label, "typedef", ""))


# ---------------------------------------------------------------------------
# Recursive expansion
# ---------------------------------------------------------------------------

def _collect_fields(
    type_node: dict,
    contains_from: dict,
    nodes_by_id: dict,
) -> list[dict]:
    """
    Return the direct field symbol nodes of a type node.
    Only symbol children (class fields/attributes) are returned; methods are
    included but callers can distinguish them by label (fields have a dot).
    """
    children = contains_from.get(type_node["id"], [])
    fields = []
    for child in children:
        # A symbol node whose label starts with the type name is a field
        if child.get("type") == "symbol":
            fields.append(child)
    # Sort by line number for stable output
    fields.sort(key=lambda n: n.get("line") or 0)
    return fields


def _expand_type(
    type_node: dict,
    contains_from: dict,
    uses_type_from: dict,
    nodes_by_id: dict,
    ptr_depth_map: dict,
    visited: set,
    indent: int,
    lines: list,
    relations: list,          # mermaid only: list of (from_label, to_label, field_name)
    render_mode: str,
) -> None:
    """
    Recursively expand type_node into `lines` (text) or `relations` (mermaid).

    Args:
        type_node    : The type node being expanded now
        visited      : Set of type node IDs already on the current recursion path
        indent       : Current indentation level (text mode)
        lines        : Accumulator for text lines
        relations    : Accumulator for mermaid relation tuples
        render_mode  : "text" or "mermaid"
    """
    type_id = type_node["id"]
    type_label = type_node.get("label", type_id)
    loc = _short_filename(type_node)

    if render_mode == "text":
        prefix = "  " * indent
        header = f"{prefix}{type_label}"
        if loc:
            header += f" ({loc})"
        lines.append(header)

    # Mark visited before recursing to catch cycles
    visited.add(type_id)

    # Collect field symbols for this type
    field_symbols = _collect_fields(type_node, contains_from, nodes_by_id)

    for sym in field_symbols:
        field = _field_name(sym)
        sym_id = sym["id"]

        # Find what custom type (if any) this field references
        referred_type = _resolve_field_type(sym, uses_type_from, nodes_by_id)

        # Determine ptr_depth: check the edge from type_node -> referred_type
        ptr_stars = ""
        if referred_type is not None:
            pd = ptr_depth_map.get((type_id, referred_type["id"]), 0) or 0
            ptr_stars = "*" * pd

        if render_mode == "text":
            prefix_field = "  " * (indent + 1)
            if referred_type is not None:
                type_annotation = ptr_stars + referred_type.get("label", "")
                lines.append(f"{prefix_field}{field}: {type_annotation}")
            else:
                # Primitive / builtin — show annotation text from node if available
                annot = sym.get("annotation")
                if annot:
                    lines.append(f"{prefix_field}{field}: {annot}")
                else:
                    lines.append(f"{prefix_field}{field}")

            # Recurse into the referred custom type
            if referred_type is not None:
                ref_id = referred_type["id"]
                if ref_id in visited:
                    lines.append("  " * (indent + 2) + f"<cycle: {referred_type.get('label', ref_id)}>")
                else:
                    _expand_type(
                        referred_type,
                        contains_from,
                        uses_type_from,
                        nodes_by_id,
                        ptr_depth_map,
                        visited,
                        indent + 2,
                        lines,
                        relations,
                        render_mode,
                    )

        elif render_mode == "mermaid":
            if referred_type is not None:
                ref_label = referred_type.get("label", "")
                # Record relation for later rendering
                relations.append((type_label, ref_label, field, ptr_stars))

                ref_id = referred_type["id"]
                if ref_id not in visited:
                    _expand_type(
                        referred_type,
                        contains_from,
                        uses_type_from,
                        nodes_by_id,
                        ptr_depth_map,
                        visited,
                        indent + 2,
                        lines,
                        relations,
                        render_mode,
                    )
                # Cycles in mermaid are silently skipped (diagram handles loops visually)

    # Remove from visited on the way back up so the same type can appear in
    # multiple branches (but not recursively within the same branch).
    visited.discard(type_id)


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------

def _render_text(
    root_type: dict,
    contains_from: dict,
    uses_type_from: dict,
    nodes_by_id: dict,
    ptr_depth_map: dict,
    typedef_from: dict,
    typedef_to: dict,
) -> str:
    """
    Render the fully expanded type tree as an indented text tree.
    Includes typedef chain traversal.

    Example:
        RecipeScore (autofill_engine.py:42)
          score: float
          sub_data: SubStruct
            SubStruct (sub_data.py:10)
              field_a: str
        <<typedefs (aliases)>>
          AliasName (file.py:123)
    """
    lines: list[str] = []
    _expand_type(
        root_type,
        contains_from,
        uses_type_from,
        nodes_by_id,
        ptr_depth_map,
        visited=set(),
        indent=0,
        lines=lines,
        relations=[],
        render_mode="text",
    )

    # Append typedef chain information
    lines.append("")
    lines.append("=== Typedef Chain ===")
    _expand_typedef_chain(
        root_type,
        typedef_from,
        typedef_to,
        nodes_by_id,
        ptr_depth_map,
        visited=set(),
        indent=0,
        lines=lines,
        relations=[],
        render_mode="text",
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mermaid renderer
# ---------------------------------------------------------------------------

def _render_mermaid(
    root_type: dict,
    contains_from: dict,
    uses_type_from: dict,
    nodes_by_id: dict,
    ptr_depth_map: dict,
    typedef_from: dict,
    typedef_to: dict,
) -> str:
    """
    Render the fully expanded type structure as a Mermaid classDiagram.
    Includes typedef chain relationships.

    Example:
        classDiagram
            class RecipeScore {
                +float score
                +SubStruct sub_data
            }
            RecipeScore --> SubStruct : sub_data
            RecipeScore --|> Alias : <<typedef>>
    """
    # --- Pass 1: collect all involved types and relations
    relations: list[tuple[str, str, str, str]] = []  # (from_type, to_type, field_name, ptr_stars)
    types_seen: dict[str, dict] = {}  # label -> type_node
    type_fields: dict[str, list[tuple[str, str | None]]] = defaultdict(list)

    def _collect_all(type_node: dict) -> None:
        """Recursively collect types, fields, and relations in a single pass."""
        label = type_node.get("label", type_node["id"])
        if label in types_seen:
            return
        types_seen[label] = type_node

        field_symbols = _collect_fields(type_node, contains_from, nodes_by_id)
        for sym in field_symbols:
            field = _field_name(sym)
            referred = _resolve_field_type(sym, uses_type_from, nodes_by_id)
            if referred is not None:
                pd = ptr_depth_map.get((type_node["id"], referred["id"]), 0) or 0
                ptr_stars = "*" * pd
                type_fields[label].append((field, ptr_stars + referred.get("label", "")))
                relations.append((label, referred.get("label", ""), field, ptr_stars))
                _collect_all(referred)
            else:
                type_fields[label].append((field, sym.get("annotation") or None))

        for alias_node in typedef_from.get(type_node["id"], []):
            alias_label = alias_node.get("label", "")
            relations.append((label, alias_label, "typedef", ""))
            _collect_all(alias_node)

    _collect_all(root_type)

    # --- Pass 2: emit Mermaid text
    output_lines = ["classDiagram"]

    for type_label in sorted(types_seen.keys()):
        output_lines.append(f"    class {type_label} {{")
        for field_name, type_annot in type_fields.get(type_label, []):
            if type_annot:
                output_lines.append(f"        +{type_annot} {field_name}")
            else:
                output_lines.append(f"        +{field_name}")
        output_lines.append("    }")

    # Deduplicate relations while preserving order
    seen_rels: set = set()
    for from_lbl, to_lbl, field_name, ptr_stars in relations:
        key = (from_lbl, to_lbl, field_name)
        if key not in seen_rels:
            seen_rels.add(key)
            # Special rendering for typedef relations
            if field_name == "typedef":
                output_lines.append(f"    {from_lbl} --|> {to_lbl} : <<typedef>>")
            else:
                annotation = ptr_stars + field_name if ptr_stars else field_name
                output_lines.append(f"    {from_lbl} --> {to_lbl} : {annotation}")

    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def expand(graph_path: str, type_name: str, output: str = "text") -> str:
    """
    Given a tier_symbol.json path and a type/class name (e.g. "RecipeScore"),
    recursively expand all nested types following contains, uses_type, and typedef_of edges,
    and return a formatted tree showing the fully resolved structure including typedef chain.

    Args:
        graph_path : Path to tier_symbol.json
        type_name  : Class/struct name to expand (e.g. "RecipeScore", "State")
        output     : "text" for indented tree, "mermaid" for classDiagram

    Returns:
        Formatted string showing the expanded type structure with typedef chain.

    Raises:
        ValueError        : If type_name is not found in the graph or output format
                            is unsupported.
        FileNotFoundError : If graph_path does not exist.
    """
    if output not in ("text", "mermaid"):
        raise ValueError(f"Unsupported output format: {output!r}. Choose 'text' or 'mermaid'.")

    nodes_by_id, contains_from, uses_type_from, ptr_depth_map, typedef_from, typedef_to = _load_graph(graph_path)

    root_type = _find_type_node(nodes_by_id, type_name)
    if root_type is None:
        available = list_types(graph_path)
        available_str = ", ".join(available) if available else "(none)"
        raise ValueError(
            f"Type {type_name!r} not found in graph.\n"
            f"Available types: {available_str}"
        )

    if output == "text":
        return _render_text(root_type, contains_from, uses_type_from, nodes_by_id, ptr_depth_map, typedef_from, typedef_to)
    else:
        return _render_mermaid(root_type, contains_from, uses_type_from, nodes_by_id, ptr_depth_map, typedef_from, typedef_to)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Expand a type/struct recursively from a CodeGrapher graph")
    p.add_argument("--graph", required=True, help="Path to tier_symbol.json")
    p.add_argument("--type", required=False, dest="type_name", help="Type/class name to expand")
    p.add_argument("--format", choices=["text", "mermaid"], default="text")
    p.add_argument("--list", action="store_true", help="List all available types and exit")
    p.add_argument("--out", default="-", help="Output file or - for stdout")
    args = p.parse_args()

    if args.list:
        types = list_types(args.graph)
        for t in types:
            print(t)
    else:
        result = expand(args.graph, args.type_name, output=args.format)
        if args.out == "-":
            print(result)
        else:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(result)
