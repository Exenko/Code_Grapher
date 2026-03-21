"""
parser_proto.py — Protocol Buffer (.proto) file parser.

Extracts nodes and edges from a single .proto file:
  - package declaration (module for type IDs)
  - message types → TYPE nodes
  - nested messages → TYPE nodes + contains edges
  - enum types → TYPE nodes
  - message fields → contains/uses_type edges for non-scalar types
  - imports → depends_on edges
  - maps_to edges for proto-to-other-language type mappings (name convention)

Uses regex-based parsing (no external proto library).
Reusable across any project with .proto files.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple

from schema import (
    Node, Edge, NodeType, EdgeRelation,
    file_id, type_id, is_test_file,
)
from graph import CodeGraph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(feature: str, root: Path, filepath: Path,
               known_symbol_ids: Set[str] | None = None) -> CodeGraph:
    """
    Parse a single Protocol Buffer (.proto) file and return a CodeGraph.

    Args:
        feature:          Feature name (e.g. "messages", "events")
        root:             Project root Path (for computing relative paths)
        filepath:         Absolute path to the .proto file
        known_symbol_ids: Set of all symbol/type IDs known across the feature
                          (used to resolve maps_to edges by naming convention).
                          If None, maps_to edges are still created but marked unresolved.
    """
    rel_path = _rel(root, filepath)
    source = filepath.read_text(encoding="utf-8", errors="replace")

    parser = _ProtoFileParser(
        feature=feature,
        rel_path=rel_path,
        source=source,
        known_symbol_ids=known_symbol_ids or set(),
    )
    return parser.parse()


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

class _ProtoFileParser:
    def __init__(self, feature: str, rel_path: str, source: str,
                 known_symbol_ids: Set[str]):
        self.feature = feature
        self.rel_path = rel_path
        self.source = source
        self.known = known_symbol_ids
        self.graph = CodeGraph(feature)

        # State: module name derived from package or file stem
        self.module_name: str = ""
        self.file_node_id: str = ""

        # Map of known proto file paths for resolving imports
        # Built from known_symbol_ids (file nodes): feature::rel/path/file.proto
        self.known_proto_files: Dict[str, str] = self._build_known_proto_files()

    def parse(self) -> CodeGraph:
        """Main entry point: parse the proto file and return populated graph."""
        # Create file node
        self.file_node_id = file_id(self.feature, self.rel_path)
        self.graph.add_node(Node(
            id=self.file_node_id,
            type=NodeType.FILE,
            label=Path(self.rel_path).name,
            file=self.rel_path,
            line=None,
            language="proto",
            is_test=is_test_file(self.rel_path),
        ))

        # Extract package (module name)
        self._extract_package()

        # Extract imports
        self._extract_imports()

        # Extract top-level messages and enums
        self._extract_top_level_types()

        # After all types are extracted, create maps_to edges by naming convention
        self._create_maps_to_edges()

        return self.graph

    # ------------------------------------------------------------------
    # Package extraction
    # ------------------------------------------------------------------

    def _build_known_proto_files(self) -> Dict[str, str]:
        """
        Extract all known .proto file nodes from known_symbol_ids.
        Returns a dict mapping basename (e.g., "messages.proto") -> full_id
        (e.g., "stress::protos/messages.proto").
        Also stores full paths for resolution via directory traversal.
        """
        proto_map: Dict[str, str] = {}
        for node_id in self.known:
            # File nodes: feature::rel/path/file.proto
            if "::" in node_id and node_id.count("::") == 1:
                parts = node_id.split("::")
                path_part = parts[1]
                if path_part.endswith(".proto"):
                    # Store by basename
                    basename = Path(path_part).name
                    proto_map[basename] = node_id
                    # Also store by full path for exact matches
                    proto_map[path_part] = node_id
        return proto_map

    def _extract_package(self) -> None:
        """Extract 'package some.package.name;' and set module_name."""
        match = re.search(r'^\s*package\s+([\w.]+)\s*;', self.source, re.MULTILINE)
        if match:
            self.module_name = match.group(1)
        else:
            # Fallback: use file stem
            self.module_name = Path(self.rel_path).stem

    # ------------------------------------------------------------------
    # Import extraction and resolution
    # ------------------------------------------------------------------

    def _resolve_imported_file(self, import_path: str) -> Optional[str]:
        """
        Resolve an import statement to a proper file node ID.

        Strategy:
          1. Try exact match in known_proto_files (full path)
          2. Try basename match in known_proto_files
          3. Try to construct path relative to current file's directory
          4. Return None if unresolved (skip edge to prevent spurious nodes)
        """
        # Strategy 1: Exact match (e.g., "protos/messages.proto")
        if import_path in self.known_proto_files:
            return self.known_proto_files[import_path]

        # Strategy 2: Basename match (e.g., "messages.proto")
        basename = Path(import_path).name
        if basename in self.known_proto_files:
            return self.known_proto_files[basename]

        # Strategy 3: Relative to current file's directory
        # (e.g., current file is "dir/current.proto", import "sibling.proto" -> "dir/sibling.proto")
        current_dir = Path(self.rel_path).parent
        relative_path = str(current_dir / import_path).replace("\\", "/")
        if relative_path in self.known_proto_files:
            return self.known_proto_files[relative_path]

        # Unresolved: return None (caller will skip edge)
        return None

    def _extract_imports(self) -> None:
        """Extract 'import "other.proto";' statements and create depends_on edges."""
        pattern = r'^\s*import\s+"([^"]+)"\s*;'
        for match in re.finditer(pattern, self.source, re.MULTILINE):
            imported_file = match.group(1)

            # Try to resolve the imported file to a proper node ID
            resolved_id = self._resolve_imported_file(imported_file)

            # Only create edge if we found a known proto file
            if resolved_id:
                self.graph.add_edge(Edge(
                    from_id=self.file_node_id,
                    to_id=resolved_id,
                    relation=EdgeRelation.DEPENDS_ON,
                ))
            # If unresolved, skip the edge entirely to avoid creating malformed nodes

    # ------------------------------------------------------------------
    # Top-level message and enum extraction
    # ------------------------------------------------------------------

    def _extract_top_level_types(self) -> None:
        """Extract all top-level (non-nested) messages and enums."""
        # Remove comments to avoid false matches in // comments
        clean_source = self._remove_comments(self.source)

        # Find all top-level messages (not indented)
        for match in re.finditer(r'^\s*message\s+(\w+)\s*\{', clean_source, re.MULTILINE):
            msg_name = match.group(1)
            msg_start = match.start()
            msg_end = self._find_closing_brace(clean_source, match.end() - 1)

            if msg_end is not None:
                msg_body = clean_source[match.end():msg_end]
                self._add_message_node(msg_name, msg_body)

                # Extract nested types (messages and enums) within this message
                self._extract_nested_types(msg_name, msg_body)

        # Find all top-level enums
        for match in re.finditer(r'^\s*enum\s+(\w+)\s*\{', clean_source, re.MULTILINE):
            enum_name = match.group(1)
            self._add_enum_node(enum_name)

    def _extract_nested_types(self, parent_msg_name: str, body: str) -> None:
        """Extract nested messages and enums within a parent message."""
        parent_id = type_id(self.feature, self.module_name, parent_msg_name)

        # Remove comments from body
        clean_body = self._remove_comments(body)

        # Find nested messages
        for match in re.finditer(r'^\s*message\s+(\w+)\s*\{', clean_body, re.MULTILINE):
            nested_name = match.group(1)
            nested_start = match.start()
            nested_end = self._find_closing_brace(clean_body, match.end() - 1)

            if nested_end is not None:
                nested_body = clean_body[match.end():nested_end]
                qualified_name = f"{parent_msg_name}.{nested_name}"
                self._add_message_node(qualified_name, nested_body)

                # Create contains edge from parent to nested
                nested_id = type_id(self.feature, self.module_name, qualified_name)
                self.graph.add_edge(Edge(
                    from_id=parent_id,
                    to_id=nested_id,
                    relation=EdgeRelation.CONTAINS,
                ))

                # Recursively extract further nesting
                self._extract_nested_types(qualified_name, nested_body)

        # Find nested enums
        for match in re.finditer(r'^\s*enum\s+(\w+)\s*\{', clean_body, re.MULTILINE):
            enum_name = match.group(1)
            qualified_name = f"{parent_msg_name}.{enum_name}"
            self._add_enum_node(qualified_name)

            # Create contains edge from parent message to nested enum
            enum_id = type_id(self.feature, self.module_name, qualified_name)
            self.graph.add_edge(Edge(
                from_id=parent_id,
                to_id=enum_id,
                relation=EdgeRelation.CONTAINS,
            ))

    # ------------------------------------------------------------------
    # Message and enum node creation
    # ------------------------------------------------------------------

    def _add_message_node(self, msg_name: str, body: str) -> None:
        """Create a TYPE node for a message and process its fields."""
        msg_id = type_id(self.feature, self.module_name, msg_name)

        self.graph.add_node(Node(
            id=msg_id,
            type=NodeType.TYPE,
            label=msg_name,
            file=self.rel_path,
            line=None,
            language="proto",
        ))

        # Create defines edge from file to message
        self.graph.add_edge(Edge(
            from_id=self.file_node_id,
            to_id=msg_id,
            relation=EdgeRelation.DEFINES,
        ))

        # Extract fields and create edges for referenced types
        self._extract_message_fields(msg_id, body)

    def _add_enum_node(self, enum_name: str) -> None:
        """Create a TYPE node for an enum."""
        enum_id = type_id(self.feature, self.module_name, enum_name)

        self.graph.add_node(Node(
            id=enum_id,
            type=NodeType.TYPE,
            label=enum_name,
            file=self.rel_path,
            line=None,
            language="proto",
        ))

        # Create defines edge from file to enum
        self.graph.add_edge(Edge(
            from_id=self.file_node_id,
            to_id=enum_id,
            relation=EdgeRelation.DEFINES,
        ))

    # ------------------------------------------------------------------
    # Message field extraction
    # ------------------------------------------------------------------

    def _extract_message_fields(self, msg_id: str, body: str) -> None:
        """Extract fields from message body and create contains/uses_type edges."""
        # Pattern: [repeated|optional|required] FieldType field_name = N [;|{...]
        # Matches lines like:
        #   string name = 1;
        #   repeated int32 ids = 2;
        #   optional Message ref = 3;
        #   map<string, int32> config = 4;
        pattern = (
            r'^\s*(?:repeated|optional|required|map)?\s*'
            r'(?:<[^>]+>)?\s*'  # for map types
            r'([\w.]+)\s+'
            r'(\w+)\s*=\s*\d+'
        )

        for match in re.finditer(pattern, body, re.MULTILINE):
            field_type = match.group(1)
            field_name = match.group(2)

            # Skip scalar types
            if self._is_scalar_type(field_type):
                continue

            # It's a message type reference
            # Try to resolve it: could be a sibling, or fully qualified
            referenced_id = self._resolve_field_type(field_type, msg_id)

            if referenced_id:
                self.graph.add_edge(Edge(
                    from_id=msg_id,
                    to_id=referenced_id,
                    relation=EdgeRelation.CONTAINS,
                ))
            else:
                # Unresolved type reference
                self.graph.add_edge(Edge(
                    from_id=msg_id,
                    to_id=f"unresolved::{field_type}",
                    relation=EdgeRelation.USES_TYPE,
                    unresolved=True,
                ))

    def _resolve_field_type(self, field_type: str, parent_msg_id: str) -> Optional[str]:
        """
        Resolve a field type to a known message/enum ID.

        Priority:
          1. Qualified name as-is (e.g., "foo.bar.Message")
          2. Sibling in same module (e.g., "Message" when parent is in same module)
          3. Nested type relative to parent (e.g., "Parent.Nested" if parent is "Parent")
        """
        # Extract parent message name from parent_msg_id
        # parent_msg_id format: feature::module::MessageName
        parts = parent_msg_id.split("::")
        parent_msg_name = parts[-1] if len(parts) >= 3 else None

        # Try direct lookup with module
        direct_id = type_id(self.feature, self.module_name, field_type)
        if self.graph.has_node(direct_id):
            return direct_id

        # Try as a nested type of the parent message
        if parent_msg_name:
            nested_qualified = f"{parent_msg_name}.{field_type}"
            nested_id = type_id(self.feature, self.module_name, nested_qualified)
            if self.graph.has_node(nested_id):
                return nested_id

        # Try without module prefix (field_type might already be fully qualified)
        # Check all known types for a matching label
        for node in self.graph.nodes:
            if node.type == NodeType.TYPE and node.label == field_type:
                return node.id

        return None

    # ------------------------------------------------------------------
    # maps_to edges — naming convention matching
    # ------------------------------------------------------------------

    def _create_maps_to_edges(self) -> None:
        """
        Create maps_to edges by matching proto types to other language types.

        Naming convention:
          - ProtoTypeName_Proto or ProtoTypeNameProto → maps to ProtoTypeName_CC, ProtoTypeName_WSDL, etc.
          - LegacyEvent_Proto specifically → matches LegacyEvent_CC, LegacyEvent_WSDL in known_symbol_ids
        """
        for node in self.graph.nodes:
            if node.type != NodeType.TYPE:
                continue

            proto_name = node.label

            # Check if name follows proto naming convention
            if proto_name.endswith("_Proto"):
                base_name = proto_name[:-6]  # Remove "_Proto"
            elif proto_name.endswith("Proto"):
                base_name = proto_name[:-5]  # Remove "Proto"
            else:
                continue

            # Look for matching types in known_symbol_ids with suffixes: _CC, _WSDL, _CPP, etc.
            suffixes = ["_CC", "_WSDL", "_CPP", "_JAVA", "_RUST"]
            for suffix in suffixes:
                target_name = f"{base_name}{suffix}"
                # Find in known_symbol_ids
                for known_id in self.known:
                    known_label = known_id.split("::")[-1]
                    if known_label == target_name:
                        # Found a match
                        self.graph.add_edge(Edge(
                            from_id=node.id,
                            to_id=known_id,
                            relation=EdgeRelation.MAPS_TO,
                        ))
                        return  # Only one maps_to per proto type

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _remove_comments(self, text: str) -> str:
        """Remove // and /* */ comments from proto source."""
        # Remove // comments (to end of line)
        text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
        # Remove /* */ comments
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        return text

    def _find_closing_brace(self, text: str, open_brace_pos: int) -> Optional[int]:
        """
        Find the position of the closing brace matching the one at open_brace_pos.
        open_brace_pos should be at the opening '{' character.
        Returns the position of the closing '}', or None if not found.
        """
        if open_brace_pos >= len(text) or text[open_brace_pos] != '{':
            return None

        depth = 1
        pos = open_brace_pos + 1
        while pos < len(text) and depth > 0:
            if text[pos] == '{':
                depth += 1
            elif text[pos] == '}':
                depth -= 1
            pos += 1

        return pos - 1 if depth == 0 else None

    def _is_scalar_type(self, field_type: str) -> bool:
        """Check if a field type is a scalar proto type (not a message/enum)."""
        scalar_types = {
            "int32", "int64", "uint32", "uint64", "sint32", "sint64",
            "fixed32", "fixed64", "sfixed32", "sfixed64",
            "float", "double",
            "bool",
            "string",
            "bytes",
        }
        # Also handle map types like "map<string, int32>"
        if field_type.startswith("map<"):
            return True
        return field_type in scalar_types


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _rel(root: Path, filepath: Path) -> str:
    """Compute relative path from root, normalized to forward slashes."""
    try:
        rel = filepath.relative_to(root)
    except ValueError:
        rel = filepath
    return str(rel).replace("\\", "/")
