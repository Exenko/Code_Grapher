"""
serve.py — CodeGrapher LOD Server

Serves the graph viewer + graph JSON files with an /api/neighbors endpoint
for progressive level-of-detail loading.

Usage:
    py CodeGrapher/serve.py --graphs CodeGrapher/graphs --port 5000
"""

import argparse
import json
import mimetypes
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse, parse_qs, unquote

# Import analyze module functions
sys.path.insert(0, os.path.dirname(__file__))
from analyze import flow_trace, type_expander


# Module-level JSON cache: abs_path_str -> parsed dict
_cache: Dict = {}
_graphs_dir: Path = Path("graphs")
_viewer_dir: Path = Path(__file__).parent / "viewer"


def _load_json(path: Path) -> Optional[Dict]:
    """Load and cache a JSON file. Returns None if file not found."""
    key = str(path.resolve())
    if key not in _cache:
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            _cache[key] = json.load(f)
    return _cache[key]


def _safe_resolve(base: Path, rel: str) -> Optional[Path]:
    """Resolve rel path under base, return None if it escapes base."""
    try:
        resolved = (base / rel).resolve()
        if resolved.is_relative_to(base.resolve()):
            return resolved
        return None
    except Exception:
        return None


def _neighbors_response(node_id: str) -> Tuple[int, Dict]:
    """
    Parse node_id, load appropriate graph file, find node + neighbors.
    Returns (status_code, response_dict).
    """
    parts = node_id.split("::")

    if len(parts) < 2:
        return 400, {"error": "invalid node id", "id": node_id}

    second = parts[1]

    if second == "dir":
        graph_file = _graphs_dir / "tier_directory.json"
    elif second == "repo":
        graph_file = _graphs_dir / "tier_repo.json"
    elif len(parts) == 2:
        # file node
        graph_file = _graphs_dir / "tier_file.json"
    elif len(parts) == 3:
        # symbol node — find sub-graph via toc.json
        file_path = parts[1]
        toc = _load_json(_graphs_dir / "toc.json")
        slug = None
        if toc:
            for ep in toc.get("entry_points", []):
                if ep.get("file") == file_path:
                    slug = ep.get("slug")
                    break
        if slug:
            graph_file = _graphs_dir / "sub" / f"{slug}.json"
        else:
            graph_file = _graphs_dir / "tier_file.json"
    else:
        graph_file = _graphs_dir / "tier_symbol.json"

    data = _load_json(graph_file)
    if data is None:
        return 404, {"error": "graph file not found", "file": str(graph_file)}

    nodes_by_id = {n["id"]: n for n in data.get("nodes", [])}
    node = nodes_by_id.get(node_id)
    if node is None:
        return 404, {"error": "node not found", "id": node_id}

    matching_edges = [
        e for e in data.get("edges", [])
        if e.get("from") == node_id or e.get("to") == node_id
    ]

    neighbor_ids = set()
    for e in matching_edges:
        if e.get("from") == node_id:
            neighbor_ids.add(e["to"])
        else:
            neighbor_ids.add(e["from"])

    neighbors = [nodes_by_id[nid] for nid in neighbor_ids if nid in nodes_by_id]

    return 200, {
        "node": node,
        "neighbors": neighbors,
        "edges": matching_edges,
    }


class _Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):  # noqa: A002
        # Suppress default per-request logging; errors still visible
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/" or path == "/index.html":
            self._serve_file(_viewer_dir / "index.html")

        elif path.startswith("/viewer/"):
            rel = unquote(path[len("/viewer/"):])
            target = _safe_resolve(_viewer_dir, rel)
            if target is None:
                self._send_error(403, "Forbidden")
            else:
                self._serve_file(target)

        elif path.startswith("/graphs/"):
            rel = unquote(path[len("/graphs/"):])
            target = _safe_resolve(_graphs_dir, rel)
            if target is None:
                self._send_error(403, "Forbidden")
            else:
                self._serve_file(target)

        elif path == "/api/neighbors":
            qs = parse_qs(parsed.query)
            ids = qs.get("id", [])
            if not ids:
                self._send_json(400, {"error": "missing ?id= parameter"})
            else:
                status, body = _neighbors_response(ids[0])
                self._send_json(status, body)

        elif path == "/api/diagram/flow":
            qs = parse_qs(parsed.query)
            graph = qs.get("graph", [None])[0]
            entry = qs.get("entry", [None])[0]
            symbol = qs.get("symbol", [None])[0]

            if not entry:
                self._send_json(400, {"error": "missing ?entry= parameter"})
                return

            # Default to tier_symbol.json if graph not provided
            if graph is None:
                graph_path = str(_graphs_dir / "tier_symbol.json")
            else:
                resolved = _safe_resolve(_graphs_dir, graph)
                if resolved is None:
                    self._send_json(403, {"error": "Forbidden"})
                    return
                graph_path = str(resolved)

            try:
                mermaid_output = flow_trace.trace(graph_path, entry, output="mermaid", symbol_name=symbol)
                self._send_json(200, {"mermaid": mermaid_output, "entry": entry})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif path == "/api/diagram/type":
            qs = parse_qs(parsed.query)
            graph = qs.get("graph", [None])[0]
            type_name = qs.get("type", [None])[0]
            fmt = qs.get("format", ["mermaid"])[0]

            if not type_name:
                self._send_json(400, {"error": "missing ?type= parameter"})
                return

            # Default to tier_symbol.json if graph not provided
            if graph is None:
                graph_path = str(_graphs_dir / "tier_symbol.json")
            else:
                resolved = _safe_resolve(_graphs_dir, graph)
                if resolved is None:
                    self._send_json(403, {"error": "Forbidden"})
                    return
                graph_path = str(resolved)

            try:
                output = type_expander.expand(graph_path, type_name, output=fmt)
                self._send_json(200, {"output": output, "format": fmt})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif path == "/api/diagram/types":
            qs = parse_qs(parsed.query)
            graph = qs.get("graph", [None])[0]

            # Default to tier_symbol.json if graph not provided
            if graph is None:
                graph_path = str(_graphs_dir / "tier_symbol.json")
            else:
                resolved = _safe_resolve(_graphs_dir, graph)
                if resolved is None:
                    self._send_json(403, {"error": "Forbidden"})
                    return
                graph_path = str(resolved)

            try:
                types = type_expander.list_types(graph_path)
                self._send_json(200, {"types": types})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        else:
            # Fallback: try serving the path as a viewer static asset.
            # Handles relative asset references in index.html (styles.css, d3.min.js, graph.js).
            rel = unquote(path.lstrip("/"))
            if rel:
                target = _safe_resolve(_viewer_dir, rel)
                if target is not None and target.is_file():
                    self._serve_file(target)
                    return
            self._send_error(404, "Not Found")

    def _serve_file(self, path: Path):
        if not path.exists() or not path.is_file():
            self._send_error(404, f"File not found: {path.name}")
            return
        mime, _ = mimetypes.guess_type(str(path))
        if mime is None:
            ext = path.suffix.lower()
            mime = {
                ".json": "application/json",
                ".js": "application/javascript",
                ".html": "text/html",
                ".css": "text/css",
            }.get(ext, "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (ConnectionAbortedError, BrokenPipeError):
            pass  # browser closed the connection early — not an error

    def _send_json(self, status: int, body: dict):
        data = json.dumps(body, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (ConnectionAbortedError, BrokenPipeError):
            pass  # browser closed the connection early — not an error

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": message})


def main():
    global _graphs_dir

    parser = argparse.ArgumentParser(description="CodeGrapher LOD Server")
    parser.add_argument("--graphs", default="graphs",
                        help="Path to graphs directory (default: graphs)")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port to serve on (default: 5000)")
    args = parser.parse_args()

    _graphs_dir = Path(args.graphs).resolve()

    if not _graphs_dir.exists():
        print(f"Error: graphs directory not found: {_graphs_dir}")
        raise SystemExit(1)

    url = f"http://localhost:{args.port}"
    print(f"Serving CodeGrapher at {url}  (graphs: {_graphs_dir})")

    server = HTTPServer(("localhost", args.port), _Handler)

    # Open browser after a short delay so server is ready
    def _open():
        import time
        time.sleep(0.5)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
