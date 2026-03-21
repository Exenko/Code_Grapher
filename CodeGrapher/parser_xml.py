"""
parser_xml.py — XML parser for CodeGrapher.

Handles WSDL, XSD, and configuration XML files.
Extracts port type operations, complex types, simple types (enums), and config sections.
Creates maps_to edges across language boundaries using name matching heuristics.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from schema import Node, Edge, NodeType, EdgeRelation, file_id, symbol_id, type_id


def parse_file(
    feature: str,
    root: Path,
    filepath: Path,
    known_symbol_ids: set | None = None,
) -> "CodeGraph":
    """
    Parse an XML file and extract nodes/edges.

    Args:
        feature: Feature name (e.g., "repo")
        root: Project root directory
        filepath: Absolute path to XML file
        known_symbol_ids: Set of all known symbol/type IDs from other parsers (for maps_to resolution)

    Returns:
        CodeGraph with file, symbol, and type nodes; defines/contains/maps_to edges
    """
    from graph import CodeGraph

    g = CodeGraph(feature)

    # Compute relative path
    try:
        rel_path = str(filepath.relative_to(root))
    except ValueError:
        rel_path = str(filepath)

    # Determine file type by examining content
    xml_type = _detect_xml_type(filepath)

    # Create file node
    file_node_id = file_id(feature, rel_path)
    language = "wsdl" if xml_type == "wsdl" else ("xsd" if xml_type == "xsd" else "config")
    file_node = Node(
        id=file_node_id,
        type=NodeType.FILE,
        label=filepath.name,
        file=rel_path,
        line=None,
        language=language,
    )
    g.add_node(file_node)

    # Parse based on type
    if xml_type == "wsdl":
        _parse_wsdl(g, feature, rel_path, filepath, file_node_id)
    elif xml_type == "xsd":
        _parse_xsd(g, feature, rel_path, filepath, file_node_id)
    else:  # config
        _parse_config(g, feature, rel_path, filepath, file_node_id)

    # Create maps_to edges if we have known_symbol_ids
    if known_symbol_ids:
        _create_maps_to_edges(g, known_symbol_ids)

    return g


def _detect_xml_type(filepath: Path) -> str:
    """
    Detect XML file type by examining content.

    Returns: "wsdl", "xsd", or "config"
    """
    try:
        tree = ET.parse(filepath)
        root_elem = tree.getroot()
        root_tag = _strip_ns(root_elem.tag)

        # Check root element
        if root_tag == "definitions" or "wsdl" in root_elem.tag.lower():
            return "wsdl"
        elif root_tag == "schema" or "schema" in root_elem.tag.lower():
            return "xsd"
        else:
            return "config"
    except Exception:
        # Default to config on parse error
        return "config"


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from tag name."""
    return tag.split('}')[-1] if '}' in tag else tag


def _parse_wsdl(g, feature: str, rel_path: str, filepath: Path, file_node_id: str) -> None:
    """
    Parse WSDL file and extract portType operations and message types.

    Creates:
    - SYMBOL nodes for each operation within portTypes
    - TYPE nodes for wsdl:message elements (if they reference complex types)
    - DEFINES edges from file → symbols and types
    """
    try:
        tree = ET.parse(filepath)
        root_elem = tree.getroot()
    except Exception:
        return

    # Find all portType elements
    for pt_elem in root_elem.iter():
        pt_tag = _strip_ns(pt_elem.tag)
        if pt_tag == "portType":
            pt_name = pt_elem.get("name")
            if not pt_name:
                continue

            # Extract operations from this portType
            for op_elem in pt_elem.iter():
                op_tag = _strip_ns(op_elem.tag)
                if op_tag == "operation":
                    op_name = op_elem.get("name")
                    if not op_name:
                        continue

                    # Create SYMBOL node for this operation
                    sym_name = f"{pt_name}.{op_name}"
                    sym_node_id = symbol_id(feature, rel_path, sym_name)
                    sym_node = Node(
                        id=sym_node_id,
                        type=NodeType.SYMBOL,
                        label=op_name,
                        file=rel_path,
                        line=None,
                        language="wsdl",
                    )
                    g.add_node(sym_node)

                    # DEFINES edge from file to symbol
                    g.add_edge(Edge(
                        from_id=file_node_id,
                        to_id=sym_node_id,
                        relation=EdgeRelation.DEFINES,
                    ))


def _parse_xsd(g, feature: str, rel_path: str, filepath: Path, file_node_id: str) -> None:
    """
    Parse XSD file and extract complexType, simpleType, and their nested elements.

    Creates:
    - TYPE nodes for each complexType and simpleType
    - DEFINES edges from file → types
    - CONTAINS edges from complexType → nested types
    """
    try:
        tree = ET.parse(filepath)
        root_elem = tree.getroot()
    except Exception:
        return

    # Get file stem for module name
    module_name = filepath.stem  # e.g., "legacy_types"

    # Extract primitive XSD types to ignore in field definitions
    xsd_primitives = {
        "string", "int", "integer", "long", "short", "byte",
        "float", "double", "boolean", "base64Binary", "hexBinary",
        "date", "time", "dateTime", "duration",
        "unsignedLong", "unsignedInt", "unsignedShort", "unsignedByte",
        "decimal", "token", "normalizedString", "anyURI", "QName",
    }

    # Find all complexType and simpleType elements
    for elem in root_elem.iter():
        elem_tag = _strip_ns(elem.tag)

        if elem_tag == "complexType":
            ct_name = elem.get("name")
            if not ct_name:
                continue

            # Create TYPE node for this complexType
            type_node_id = type_id(feature, module_name, ct_name)
            type_node = Node(
                id=type_node_id,
                type=NodeType.TYPE,
                label=ct_name,
                file=rel_path,
                line=None,
                language="xsd",
            )
            g.add_node(type_node)

            # DEFINES edge from file to type
            g.add_edge(Edge(
                from_id=file_node_id,
                to_id=type_node_id,
                relation=EdgeRelation.DEFINES,
            ))

            # Find nested elements (sequence)
            for field_elem in elem.iter():
                field_tag = _strip_ns(field_elem.tag)
                if field_tag == "element":
                    field_type_str = field_elem.get("type")
                    if field_type_str:
                        # Strip namespace prefix (e.g., "tns:RawBytes" → "RawBytes")
                        field_type_name = _strip_ns(field_type_str.split(':')[-1])

                        # Skip XSD primitives
                        if field_type_name not in xsd_primitives:
                            # Try to find this type in the same module
                            nested_type_id = type_id(feature, module_name, field_type_name)

                            # CONTAINS edge (even if unresolved; will be deduplicated if resolved later)
                            g.add_edge(Edge(
                                from_id=type_node_id,
                                to_id=nested_type_id,
                                relation=EdgeRelation.CONTAINS,
                                unresolved=True,  # Mark unresolved; if node doesn't exist, stays unresolved
                            ))

        elif elem_tag == "simpleType":
            st_name = elem.get("name")
            if not st_name:
                continue

            # Create TYPE node for this simpleType (enum)
            type_node_id = type_id(feature, module_name, st_name)
            type_node = Node(
                id=type_node_id,
                type=NodeType.TYPE,
                label=st_name,
                file=rel_path,
                line=None,
                language="xsd",
            )
            g.add_node(type_node)

            # DEFINES edge from file to type
            g.add_edge(Edge(
                from_id=file_node_id,
                to_id=type_node_id,
                relation=EdgeRelation.DEFINES,
            ))


def _parse_config(g, feature: str, rel_path: str, filepath: Path, file_node_id: str) -> None:
    """
    Parse configuration XML and extract top-level config sections as SYMBOL nodes.

    Creates:
    - SYMBOL nodes for each top-level child element (config section)
    - DEFINES edges from file → symbols
    """
    try:
        tree = ET.parse(filepath)
        root_elem = tree.getroot()
    except Exception:
        return

    # Each immediate child of root is a config section
    for section_elem in root_elem:
        section_tag = _strip_ns(section_elem.tag)

        # Create SYMBOL node for this section
        sym_node_id = symbol_id(feature, rel_path, section_tag)
        sym_node = Node(
            id=sym_node_id,
            type=NodeType.SYMBOL,
            label=section_tag,
            file=rel_path,
            line=None,
            language="config",
        )
        g.add_node(sym_node)

        # DEFINES edge from file to symbol
        g.add_edge(Edge(
            from_id=file_node_id,
            to_id=sym_node_id,
            relation=EdgeRelation.DEFINES,
        ))


def _create_maps_to_edges(g, known_symbol_ids: set) -> None:
    """
    Create maps_to edges across language boundaries using name matching.

    Heuristic: types with same base name (after stripping language suffixes) are mapped.
    Examples:
    - LegacyEvent (XSD) ↔ LegacyEvent_Proto (proto) ↔ LegacyEvent_CC (C++)
    """
    # Get all TYPE nodes from current graph
    type_nodes = {
        node.id: node
        for node in g.nodes
        if node.type == NodeType.TYPE
    }

    # For each type in current graph, try to find matches in known_symbol_ids
    for type_id_current, type_node in type_nodes.items():
        # Extract base name (strip language suffixes)
        base_name = _extract_base_name(type_node.label)

        # Search known_symbol_ids for types with matching base name
        candidate_ids = []
        for known_id in known_symbol_ids:
            # Parse known_id to extract symbol/type label
            # Format: feature::module::TypeName or feature::path::TypeName
            parts = known_id.split("::")
            if len(parts) >= 2:
                potential_name = parts[-1]
                potential_base = _extract_base_name(potential_name)

                if potential_base == base_name and known_id != type_id_current:
                    candidate_ids.append(known_id)

        # Create MAPS_TO edges to candidates
        for candidate_id in candidate_ids:
            g.add_edge(Edge(
                from_id=type_id_current,
                to_id=candidate_id,
                relation=EdgeRelation.MAPS_TO,
            ))


def _extract_base_name(label: str) -> str:
    """
    Extract base name by stripping language suffixes.

    Examples:
    - "LegacyEvent_Proto" → "LegacyEvent"
    - "LegacyEvent_WSDL" → "LegacyEvent"
    - "LegacyEvent_CC" → "LegacyEvent"
    - "LegacyEvent" → "LegacyEvent"
    """
    suffixes = ("_Proto", "_WSDL", "_CC")
    for suffix in suffixes:
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label
