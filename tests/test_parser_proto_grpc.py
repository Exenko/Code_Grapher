"""
Tests for gRPC service and rpc method extraction in proto parser.

Coverage:
  1. Service block creates SYMBOL node with correct id
  2. DEFINES edge from file to service
  3. RPC method creates SYMBOL node with label "ServiceName.RpcName"
  4. CONTAINS edge from service to RPC method
  5. DEFINES edge from file to RPC method
  6. USES_TYPE edge from RPC to request message type (resolved)
  7. USES_TYPE edge from RPC to response message type (resolved)
  8. stream keyword stripped during type resolution
  9. Unresolved request/response type creates unresolved USES_TYPE edge
  10. Multiple RPCs in one service extracted correctly
  11. Services alongside messages extracted correctly
  12. Proto file with no services emits no service nodes
"""

from pathlib import Path
import tempfile
import pytest
from CodeGrapher.parser_proto import parse_file, _ProtoFileParser
from CodeGrapher.schema import (
    Node, NodeType, EdgeRelation, symbol_id, type_id, file_id
)


@pytest.fixture
def tmp_proto_dir():
    """Create a temporary directory for proto test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_service_creates_symbol_node(tmp_proto_dir):
    """Test that service block creates a SYMBOL node with correct id."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc Foo(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    # Find service node
    service_nodes = [n for n in graph.nodes if n.label == "MyService"]
    assert len(service_nodes) == 1
    service = service_nodes[0]

    # Check node properties
    assert service.type == NodeType.SYMBOL
    assert service.language == "proto"
    assert service.id == symbol_id("test_feature", "test.proto", "MyService")


def test_file_to_service_defines_edge(tmp_proto_dir):
    """Test DEFINES edge from file node to service node."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc Foo(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    file_id_val = file_id("test_feature", "test.proto")
    service_id = symbol_id("test_feature", "test.proto", "MyService")

    # Check for DEFINES edge
    defines_edges = [e for e in graph.edges
                     if e.from_id == file_id_val and e.to_id == service_id
                     and e.relation == EdgeRelation.DEFINES]
    assert len(defines_edges) == 1


def test_rpc_creates_symbol_node_with_service_prefix(tmp_proto_dir):
    """Test that rpc method creates SYMBOL node with label 'ServiceName.RpcName'."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    # Find rpc node
    rpc_nodes = [n for n in graph.nodes if n.label == "MyService.MyMethod"]
    assert len(rpc_nodes) == 1
    rpc = rpc_nodes[0]

    # Check node properties
    assert rpc.type == NodeType.SYMBOL
    assert rpc.language == "proto"
    assert rpc.id == symbol_id("test_feature", "test.proto", "MyService.MyMethod")


def test_service_contains_rpc_edge(tmp_proto_dir):
    """Test CONTAINS edge from service node to RPC node."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    service_id = symbol_id("test_feature", "test.proto", "MyService")
    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")

    # Check for CONTAINS edge
    contains_edges = [e for e in graph.edges
                      if e.from_id == service_id and e.to_id == rpc_id
                      and e.relation == EdgeRelation.CONTAINS]
    assert len(contains_edges) == 1


def test_file_to_rpc_defines_edge(tmp_proto_dir):
    """Test DEFINES edge from file node to RPC node."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    file_id_val = file_id("test_feature", "test.proto")
    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")

    # Check for DEFINES edge
    defines_edges = [e for e in graph.edges
                     if e.from_id == file_id_val and e.to_id == rpc_id
                     and e.relation == EdgeRelation.DEFINES]
    assert len(defines_edges) == 1


def test_rpc_uses_type_request_resolved(tmp_proto_dir):
    """Test USES_TYPE edge from RPC node to request message type (resolved)."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")
    request_type_id = type_id("test_feature", "test", "Request")

    # Check for USES_TYPE edge to request type
    uses_edges = [e for e in graph.edges
                  if e.from_id == rpc_id and e.to_id == request_type_id
                  and e.relation == EdgeRelation.USES_TYPE]
    assert len(uses_edges) == 1
    assert uses_edges[0].unresolved is False


def test_rpc_uses_type_response_resolved(tmp_proto_dir):
    """Test USES_TYPE edge from RPC node to response message type (resolved)."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")
    response_type_id = type_id("test_feature", "test", "Response")

    # Check for USES_TYPE edge to response type
    uses_edges = [e for e in graph.edges
                  if e.from_id == rpc_id and e.to_id == response_type_id
                  and e.relation == EdgeRelation.USES_TYPE]
    assert len(uses_edges) == 1
    assert uses_edges[0].unresolved is False


def test_stream_keyword_stripped_in_request(tmp_proto_dir):
    """Test that 'stream Foo' is resolved to 'Foo' type."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(stream Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")
    request_type_id = type_id("test_feature", "test", "Request")

    # Should still resolve to Request type (stream stripped)
    uses_edges = [e for e in graph.edges
                  if e.from_id == rpc_id and e.to_id == request_type_id
                  and e.relation == EdgeRelation.USES_TYPE]
    assert len(uses_edges) == 1
    assert uses_edges[0].unresolved is False


def test_stream_keyword_stripped_in_response(tmp_proto_dir):
    """Test that 'stream Foo' in response is resolved to 'Foo' type."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (stream Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")
    response_type_id = type_id("test_feature", "test", "Response")

    # Should still resolve to Response type (stream stripped)
    uses_edges = [e for e in graph.edges
                  if e.from_id == rpc_id and e.to_id == response_type_id
                  and e.relation == EdgeRelation.USES_TYPE]
    assert len(uses_edges) == 1
    assert uses_edges[0].unresolved is False


def test_unresolved_request_type(tmp_proto_dir):
    """Test unresolved request type creates unresolved USES_TYPE edge."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(UnknownRequest) returns (Response);
}

message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")

    # Check for unresolved USES_TYPE edge
    unresolved_edges = [e for e in graph.edges
                        if e.from_id == rpc_id and e.to_id == "unresolved::UnknownRequest"
                        and e.relation == EdgeRelation.USES_TYPE]
    assert len(unresolved_edges) == 1
    assert unresolved_edges[0].unresolved is True


def test_unresolved_response_type(tmp_proto_dir):
    """Test unresolved response type creates unresolved USES_TYPE edge."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc MyMethod(Request) returns (UnknownResponse);
}

message Request {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")

    # Check for unresolved USES_TYPE edge
    unresolved_edges = [e for e in graph.edges
                        if e.from_id == rpc_id and e.to_id == "unresolved::UnknownResponse"
                        and e.relation == EdgeRelation.USES_TYPE]
    assert len(unresolved_edges) == 1
    assert unresolved_edges[0].unresolved is True


def test_multiple_rpcs_in_service(tmp_proto_dir):
    """Test multiple RPCs in one service are all extracted."""
    proto_content = """
syntax = "proto3";
package test;

service MyService {
    rpc Method1(Request) returns (Response);
    rpc Method2(Request) returns (Response);
    rpc Method3(Request) returns (Response);
}

message Request {}
message Response {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    # Check for all three RPC nodes
    rpc_nodes = [n for n in graph.nodes if n.type == NodeType.SYMBOL and "MyService." in n.label]
    assert len(rpc_nodes) == 3

    labels = {n.label for n in rpc_nodes}
    assert labels == {"MyService.Method1", "MyService.Method2", "MyService.Method3"}


def test_service_alongside_messages(tmp_proto_dir):
    """Test services and messages are both extracted correctly."""
    proto_content = """
syntax = "proto3";
package test;

message MessageA {}
message MessageB {}

service MyService {
    rpc Method1(MessageA) returns (MessageB);
}

message MessageC {}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    # Check for all message type nodes
    type_nodes = [n for n in graph.nodes if n.type == NodeType.TYPE]
    type_labels = {n.label for n in type_nodes}
    assert type_labels == {"MessageA", "MessageB", "MessageC"}

    # Check for service and rpc symbol nodes
    symbol_nodes = [n for n in graph.nodes if n.type == NodeType.SYMBOL]
    symbol_labels = {n.label for n in symbol_nodes}
    assert symbol_labels == {"MyService", "MyService.Method1"}


def test_no_services_in_file(tmp_proto_dir):
    """Test proto file with no services emits no service nodes."""
    proto_content = """
syntax = "proto3";
package test;

message MessageA {}
message MessageB {}

enum MyEnum {
    OPTION_1 = 0;
}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    # Check for no service symbol nodes
    service_nodes = [n for n in graph.nodes
                     if n.type == NodeType.SYMBOL and "." not in n.label]
    assert len(service_nodes) == 0

    # Only type nodes should exist (messages and enum)
    type_nodes = [n for n in graph.nodes if n.type == NodeType.TYPE]
    assert len(type_nodes) == 3


def test_rpc_with_qualified_type_names(tmp_proto_dir):
    """Test RPC with package-qualified type names."""
    proto_content = """
syntax = "proto3";
package mypackage;

service MyService {
    rpc MyMethod(otherpackage.Request) returns (otherpackage.Response);
}
"""
    proto_file = tmp_proto_dir / "test.proto"
    proto_file.write_text(proto_content)

    graph = parse_file("test_feature", tmp_proto_dir, proto_file)

    rpc_id = symbol_id("test_feature", "test.proto", "MyService.MyMethod")

    # Should have unresolved edges for qualified names
    unresolved_edges = [e for e in graph.edges
                        if e.from_id == rpc_id
                        and e.relation == EdgeRelation.USES_TYPE
                        and e.unresolved]
    assert len(unresolved_edges) == 2
    edge_targets = {e.to_id for e in unresolved_edges}
    assert edge_targets == {"unresolved::otherpackage.Request", "unresolved::otherpackage.Response"}
