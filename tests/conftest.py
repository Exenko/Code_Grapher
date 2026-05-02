import pytest
from CodeGrapher.schema import Node, Edge, NodeType, EdgeRelation, file_id, symbol_id, type_id
from CodeGrapher.graph import CodeGraph


@pytest.fixture
def feature():
    return "test_feature"


@pytest.fixture
def empty_graph():
    return CodeGraph("test_feature")


@pytest.fixture
def file_node(feature):
    def _factory():
        return Node(
            type=NodeType.FILE,
            id=file_id(feature, "foo.py"),
            label="foo.py",
            file="foo.py",
            line=None,
        )
    return _factory


@pytest.fixture
def symbol_node(feature):
    def _factory():
        return Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "my_func"),
            label="my_func",
            file="foo.py",
            line=1,
        )
    return _factory


@pytest.fixture
def type_node(feature):
    def _factory():
        return Node(
            type=NodeType.TYPE,
            id=type_id(feature, "foo", "MyClass"),
            label="MyClass",
            file="foo.py",
            line=5,
        )
    return _factory


@pytest.fixture
def calls_edge(feature):
    return Edge(
        from_id=symbol_id(feature, "foo.py", "caller"),
        to_id=symbol_id(feature, "bar.py", "callee"),
        relation=EdgeRelation.CALLS,
        unresolved=True,
    )
