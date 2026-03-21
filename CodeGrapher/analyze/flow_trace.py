"""
flow_trace.py — Trace execution flow from an entry point and emit a Mermaid stateDiagram-v2.

Reads a tier_symbol.json graph produced by CodeGrapher and walks the "calls" edges
starting from a nominated entry file, producing two levels of Mermaid output:
  - File-level flow: which files execution passes through and in what order
  - Symbol-level flow: individual function calls with seq annotations

Language-agnostic; depends only on Python stdlib.
"""

import json
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# State ID generator factory
# ---------------------------------------------------------------------------

def _make_id_generator():
    """
    Return a callable that maps arbitrary strings to short stable state IDs.
    IDs are of the form S0, S1, S2, ... assigned in first-seen order.
    A fresh generator (fresh cache) should be created per trace() call.
    """
    cache = {}
    def get_id(s: str) -> str:
        if s not in cache:
            cache[s] = f"S{len(cache)}"
        return cache[s]
    return get_id


# ---------------------------------------------------------------------------
# Graph loading and index construction
# ---------------------------------------------------------------------------

def _load_graph(graph_path: str) -> tuple[dict, dict, dict]:
    """
    Load tier_symbol.json and build lookup structures.

    Returns:
        nodes_by_id  : dict[id -> node dict]
        calls_from   : dict[symbol_id -> list of (target_id, seq)] sorted by seq
        file_of      : dict[symbol_id -> file path string]
    """
    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes_by_id: dict = {}
    for node in data.get("nodes", []):
        nodes_by_id[node["id"]] = node

    # Build file_of for symbol nodes
    file_of: dict = {}
    for node_id, node in nodes_by_id.items():
        if node.get("type") == "symbol" and node.get("file"):
            file_of[node_id] = node["file"]

    # Build calls_from: only "calls" edges, sorted by seq
    calls_from: dict = defaultdict(list)
    for edge in data.get("edges", []):
        if edge.get("relation") == "calls":
            src = edge["from"]
            tgt = edge["to"]
            seq = edge.get("seq", 0) or 0
            calls_from[src].append((tgt, seq))

    # Sort each adjacency list by seq
    for src in calls_from:
        calls_from[src].sort(key=lambda x: x[1])

    return nodes_by_id, calls_from, file_of


# ---------------------------------------------------------------------------
# Entry symbol resolution
# ---------------------------------------------------------------------------

def _find_entry_symbol(nodes_by_id: dict, file_of: dict, calls_from: dict, entry_file: str, symbol_name: str | None = None) -> str | None:
    """
    Find the best entry symbol in the given file.

    Priority:
      0. Explicit symbol name provided by caller (matched by label or method name)
      1. Symbol whose label == "main"
      2. Module-level function (no dot in label) with the most outgoing calls
      3. Any module-level function, by line number
      4. Fallback — first symbol defined in the file by line number

    Returns the node id of the chosen entry symbol, or None if not found.
    """
    # Normalise path separators for comparison
    entry_norm = entry_file.replace("\\", "/")

    # Priority 0: explicit symbol name provided by caller
    if symbol_name:
        for node_id, node in nodes_by_id.items():
            if node.get("type") != "symbol":
                continue
            node_file = (node.get("file") or "").replace("\\", "/")
            if node_file != entry_norm:
                continue
            label = node.get("label", "")
            # Match on full label or just the method name (after last dot)
            if label == symbol_name or label.split(".")[-1] == symbol_name:
                return node_id
        # If named symbol not found in this file, warn but don't fail yet
        # (fall through to other heuristics)

    candidates_main = []
    candidates_module = []  # module-level functions (no dot in label)
    candidates_any = []

    for node_id, node in nodes_by_id.items():
        if node.get("type") != "symbol":
            continue
        node_file = (node.get("file") or "").replace("\\", "/")
        if node_file != entry_norm:
            continue
        label = node.get("label", "")
        line = node.get("line") or 99999

        if label == "main":
            candidates_main.append(node_id)
        elif "." not in label:
            # Module-level function — rank by outgoing call count (desc), then line (asc)
            call_count = len(calls_from.get(node_id, []))
            candidates_module.append((-call_count, line, node_id))
        else:
            candidates_any.append((line, node_id))

    if candidates_main:
        return candidates_main[0]
    if candidates_module:
        candidates_module.sort()
        return candidates_module[0][2]
    if candidates_any:
        candidates_any.sort()
        return candidates_any[0][1]
    return None


# ---------------------------------------------------------------------------
# Directory prefix helpers (Change 2)
# ---------------------------------------------------------------------------

def _common_dir_prefix(files: list) -> str:
    """
    Given a list of forward-slash file paths, return the deepest directory
    prefix shared by all of them. Empty string if nothing is shared.
    Example: ["A/B/C/x.py", "A/B/D/y.py"] -> "A/B"
    """
    if not files:
        return ""
    dir_parts = [Path(f).parent.parts for f in files if f]
    if not dir_parts:
        return ""
    min_len = min(len(p) for p in dir_parts)
    common = []
    for i in range(min_len):
        part = dir_parts[0][i]
        if all(p[i] == part for p in dir_parts):
            common.append(part)
        else:
            break
    return "/".join(common)


def _relative_dir(file_path: str, prefix: str) -> str:
    """
    Strip the common prefix from file_path and return the first remaining
    directory component. This becomes the boundary group label.
    Example: file="A/B/C/D/x.py", prefix="A/B" -> "C"
    If no prefix or file is directly in prefix dir, return the filename.
    """
    norm = file_path.replace("\\", "/")
    if prefix and norm.startswith(prefix + "/"):
        remainder = norm[len(prefix) + 1:]
    else:
        remainder = norm
    parts = remainder.split("/")
    if len(parts) > 1:
        return parts[0]
    return Path(file_path).name


# ---------------------------------------------------------------------------
# Callback boundary helpers (Change 3)
# ---------------------------------------------------------------------------

# Prefixes/patterns that suggest callback registration
_CALLBACK_PATTERNS = (
    "register", "subscribe", "on_", "add_listener", "add_handler",
    "connect", "bind", "attach", "listen", "hook", "emit", "dispatch",
    "set_callback", "set_handler",
)


def _is_callback_boundary(label: str) -> bool:
    """
    Return True if this symbol label looks like a callback registration,
    subscription, or event dispatch point.
    """
    low = label.lower()
    method = low.split(".")[-1]
    return any(method.startswith(p) for p in _CALLBACK_PATTERNS)


# ---------------------------------------------------------------------------
# DFS walk
# ---------------------------------------------------------------------------

def _walk(
    entry_id: str,
    calls_from: dict,
    nodes_by_id: dict,
    file_of: dict,
    max_depth: int = 6,
) -> list[dict]:
    """
    Walk the call graph via DFS from entry_id, collecting steps.

    Each step dict:
        from_symbol  : label of calling symbol
        from_file    : file of caller
        to_symbol    : label of called symbol
        to_file      : file of callee
        seq          : seq value on the edge
        depth        : recursion depth (0 = direct call from entry)
        crosses_file : True if from_file != to_file

    Max depth is enforced to prevent run-away traversal.
    Visited symbol ids are tracked to prevent cycles.
    """
    steps: list[dict] = []
    visited: set = set()
    callback_annotated: set = set()

    def _dfs(current_id: str, depth: int) -> None:
        if depth > max_depth:
            return
        if current_id in visited:
            return
        visited.add(current_id)

        current_node = nodes_by_id.get(current_id, {})
        current_label = current_node.get("label", current_id)
        current_file = (file_of.get(current_id) or current_node.get("file") or "").replace("\\", "/")

        if _is_callback_boundary(current_label) and current_id not in callback_annotated:
            callback_annotated.add(current_id)
            steps.append({
                "from_symbol": current_label,
                "from_file":   current_file,
                "to_symbol":   "__callback_boundary__",
                "to_file":     "",
                "seq":         -1,
                "depth":       depth,
                "crosses_file": False,
                "kind":        "callback_boundary",
            })

        for target_id, seq in calls_from.get(current_id, []):
            if target_id.startswith("unresolved::") or target_id.startswith("stdlib::"):
                continue
            target_node = nodes_by_id.get(target_id, {})
            target_label = target_node.get("label", target_id)
            target_file = (file_of.get(target_id) or target_node.get("file") or "").replace("\\", "/")

            if target_id in visited:
                # Back-edge: emit a cycle step but don't recurse
                steps.append({
                    "from_symbol": current_label,
                    "from_file":   current_file,
                    "to_symbol":   target_label,
                    "to_file":     target_file,
                    "seq":         seq,
                    "depth":       depth,
                    "crosses_file": current_file != target_file,
                    "kind":        "cycle",
                })
                continue

            steps.append({
                "from_symbol": current_label,
                "from_file":   current_file,
                "to_symbol":   target_label,
                "to_file":     target_file,
                "seq":         seq,
                "depth":       depth,
                "crosses_file": current_file != target_file,
                "kind":        "call",
            })

            _dfs(target_id, depth + 1)

    _dfs(entry_id, 0)
    return steps


# ---------------------------------------------------------------------------
# Mermaid rendering — file level
# ---------------------------------------------------------------------------

def _render_file_level(steps: list[dict], entry_file: str, state_id) -> str:
    """
    Build the file-level Mermaid stateDiagram-v2 section.

    Shows which files execution visits and the order of first crossing.
    Duplicate file->file transitions are suppressed.
    Steps where to_file is empty are skipped.
    """
    lines = [
        "%% === FILE LEVEL ===",
        f"%% File-level flow from {entry_file}",
        "stateDiagram-v2",
        "",
    ]

    # Entry file is always the first state
    entry_sid = state_id(entry_file)
    lines.append(f"[*] --> {entry_sid}")
    lines.append("")

    # Collect unique file states and ordered file->file transitions
    seen_states: set = set()
    seen_transitions: set = set()
    file_transitions: list[tuple[str, str, bool]] = []  # (from_file, to_file, is_cycle)

    # Seed with entry file
    seen_states.add(entry_file)

    for step in steps:
        if not step["to_file"]:
            continue
        if step["crosses_file"]:
            is_cycle = step.get("kind") == "cycle"
            key = (step["from_file"], step["to_file"])
            if key not in seen_transitions:
                seen_transitions.add(key)
                file_transitions.append((step["from_file"], step["to_file"], is_cycle))
            seen_states.add(step["from_file"])
            seen_states.add(step["to_file"])

    # Compute common directory prefix for relative display labels
    all_files = list(seen_states)
    prefix = _common_dir_prefix(all_files)

    # State declarations
    for file_path in sorted(seen_states):
        sid = state_id(file_path)
        norm = file_path.replace("\\", "/")
        if prefix and norm.startswith(prefix + "/"):
            display = norm[len(prefix) + 1:]
        else:
            display = norm
        lines.append(f"{sid} : {display}")

    lines.append("")

    # Transitions
    if not file_transitions:
        # No cross-file calls; just show the entry file
        lines.append("%% No cross-file calls detected")
    else:
        for from_file, to_file, is_cycle in file_transitions:
            from_sid = state_id(from_file)
            to_sid = state_id(to_file)
            if is_cycle:
                lines.append(f"{from_sid} --> {to_sid} : cycle")
            else:
                norm_to = to_file.replace("\\", "/")
                if prefix and norm_to.startswith(prefix + "/"):
                    to_display = norm_to[len(prefix) + 1:]
                else:
                    to_display = norm_to
                lines.append(f"{from_sid} --> {to_sid} : {to_display}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mermaid rendering — symbol level
# ---------------------------------------------------------------------------

def _render_symbol_level(
    steps: list[dict],
    entry_id: str,
    entry_file: str,
    nodes_by_id: dict,
    state_id,
) -> str:
    """
    Build the symbol-level Mermaid stateDiagram-v2 section.

    Groups symbols by file into composite state blocks.
    Cross-file calls appear as top-level transitions between file blocks.
    Steps where to_file is empty or to_symbol starts with "unresolved::" are skipped.
    """
    lines = [
        "%% === SYMBOL LEVEL ===",
        "stateDiagram-v2",
        "",
    ]

    # Collect all symbols involved
    # symbol_id -> (label, file)
    symbols_seen: dict[str, tuple[str, str]] = {}

    # Seed with entry
    entry_node = nodes_by_id.get(entry_id, {})
    entry_label = entry_node.get("label", entry_id)
    symbols_seen[entry_id] = (entry_label, entry_file)

    # We need the original symbol ids for state IDs.
    # Build a mapping: (label, file) -> original_id for step lookup.
    # Since steps use labels, we reconstruct ids by walking nodes_by_id.
    label_file_to_id: dict[tuple[str, str], str] = {}
    for nid, node in nodes_by_id.items():
        if node.get("type") == "symbol":
            nfile = (node.get("file") or "").replace("\\", "/")
            nlabel = node.get("label", "")
            label_file_to_id[(nlabel, nfile)] = nid

    # Gather all unique symbols from steps (skip unresolved/empty targets)
    for step in steps:
        if not step["to_file"]:
            continue
        if step["to_symbol"].startswith("unresolved::"):
            continue
        from_key = (step["from_symbol"], step["from_file"])
        to_key = (step["to_symbol"], step["to_file"])
        from_id = label_file_to_id.get(from_key, f"{step['from_file']}::{step['from_symbol']}")
        to_id = label_file_to_id.get(to_key, f"{step['to_file']}::{step['to_symbol']}")
        symbols_seen[from_id] = (step["from_symbol"], step["from_file"])
        symbols_seen[to_id] = (step["to_symbol"], step["to_file"])

    # Group by file
    file_to_symbols: dict[str, list[tuple[str, str]]] = defaultdict(list)  # file -> [(symbol_id, label)]
    for sym_id, (label, file) in symbols_seen.items():
        file_to_symbols[file].append((sym_id, label))

    # Entry state
    entry_state_id = state_id(entry_id)
    lines.append(f"[*] --> {entry_state_id}")
    lines.append("")

    # Emit composite state blocks per file
    for file_path in sorted(file_to_symbols.keys()):
        fname = Path(file_path).name
        file_sid = state_id(file_path)
        lines.append(f'state "{fname}" as {file_sid}_block {{')
        for sym_id, label in file_to_symbols[file_path]:
            ssid = state_id(sym_id)
            fname_bracket = Path(file_path).name
            lines.append(f'    {ssid} : {label}() [{fname_bracket}]')
        lines.append("}")
        lines.append("")

    # Emit transitions (skip unresolved/empty targets)
    seen_sym_transitions: set = set()
    for step in steps:
        if not step["to_file"]:
            continue
        if step["to_symbol"].startswith("unresolved::"):
            continue
        from_key = (step["from_symbol"], step["from_file"])
        to_key = (step["to_symbol"], step["to_file"])
        from_nid = label_file_to_id.get(from_key, f"{step['from_file']}::{step['from_symbol']}")
        to_nid = label_file_to_id.get(to_key, f"{step['to_file']}::{step['to_symbol']}")
        from_ssid = state_id(from_nid)
        to_ssid = state_id(to_nid)
        trans_key = (from_ssid, to_ssid)
        if trans_key in seen_sym_transitions:
            continue
        seen_sym_transitions.add(trans_key)
        seq_label = f"seq={step['seq']}" if step["seq"] else "calls"
        lines.append(f"{from_ssid} --> {to_ssid} : {seq_label}")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def trace(graph_path: str, entry_file: str, output: str = "mermaid", symbol_name: str | None = None) -> str:
    """
    Given a tier_symbol.json path and an entry file path (e.g. "Client_Side/main.py"),
    find the entry symbol in that file, walk calls edges by seq, and return a Mermaid
    stateDiagram-v2 string.

    Args:
        graph_path  : Path to tier_symbol.json
        entry_file  : Relative file path of the entry point (e.g. "Client_Side/main.py")
        output      : Output format — only "mermaid" is supported currently
        symbol_name : Optional specific symbol/function name to start the trace from
                      (e.g. "health_check", "on_message"). If omitted, uses main() or
                      the first __init__, then falls back to the first symbol in the file
                      by line number.

    Returns:
        A string containing two Mermaid diagrams separated by section comments:
        file-level flow and symbol-level flow.

    Raises:
        ValueError  : If the entry symbol cannot be found or output format is unsupported
        FileNotFoundError : If graph_path does not exist
    """
    if output != "mermaid":
        raise ValueError(f"Unsupported output format: {output!r}. Only 'mermaid' is supported.")

    # Normalise entry_file path separators
    entry_file = entry_file.replace("\\", "/")

    # Load graph
    nodes_by_id, calls_from, file_of = _load_graph(graph_path)

    # Find entry symbol
    entry_id = _find_entry_symbol(nodes_by_id, file_of, calls_from, entry_file, symbol_name=symbol_name)
    if entry_id is None:
        raise ValueError(
            f"Could not find an entry symbol (main or __init__) in file: {entry_file}\n"
            f"Check that the graph contains symbol nodes for this file."
        )

    # Walk call graph
    steps = _walk(entry_id, calls_from, nodes_by_id, file_of, max_depth=6)

    # Fresh ID generator per call — ensures stable short IDs (S0, S1, ...) with no cross-call accumulation
    state_id = _make_id_generator()

    # Render both levels
    file_level = _render_file_level(steps, entry_file, state_id)
    symbol_level = _render_symbol_level(steps, entry_id, entry_file, nodes_by_id, state_id)

    return file_level + "\n" + symbol_level


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Trace execution flow and emit Mermaid diagram")
    p.add_argument("--graph",  required=True, help="Path to tier_symbol.json")
    p.add_argument("--entry",  required=True, help="Entry file path, e.g. Client_Side/main.py")
    p.add_argument("--symbol", default=None,
                   help="Specific symbol/function name to start trace from (e.g. health_check, on_message). "
                        "If omitted, uses main() or first __init__, then falls back to first symbol in file.")
    p.add_argument("--out",    default="-",   help="Output file path or - for stdout")
    args = p.parse_args()

    result = trace(args.graph, args.entry, symbol_name=args.symbol)

    if args.out == "-":
        print(result)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
