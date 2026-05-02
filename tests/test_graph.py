import pytest
from CodeGrapher.schema import Node, Edge, NodeType, EdgeRelation, file_id, symbol_id, type_id
from CodeGrapher.graph import CodeGraph


class TestMerge:
    def test_merge_disjoint_graphs_combines_nodes(self, feature):
        g1 = CodeGraph(feature)
        g2 = CodeGraph(feature)

        node1 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func1"),
            label="func1",
            file="foo.py",
            line=1,
        )
        node2 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "bar.py", "func2"),
            label="func2",
            file="bar.py",
            line=2,
        )

        g1.add_node(node1)
        g2.add_node(node2)

        g1.merge(g2)

        assert g1.node_count() == 2
        assert g1.has_node(node1.id)
        assert g1.has_node(node2.id)

    def test_merge_graphs_with_same_node_id_deduplicates(self, feature):
        g1 = CodeGraph(feature)
        g2 = CodeGraph(feature)

        node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func"),
            label="func",
            file="foo.py",
            line=1,
        )

        g1.add_node(node)
        g2.add_node(node)

        g1.merge(g2)

        assert g1.node_count() == 1

    def test_merge_graphs_with_same_edge_deduplicates(self, feature):
        g1 = CodeGraph(feature)
        g2 = CodeGraph(feature)

        edge = Edge(
            from_id=symbol_id(feature, "foo.py", "caller"),
            to_id=symbol_id(feature, "bar.py", "callee"),
            relation=EdgeRelation.CALLS,
        )

        g1.add_edge(edge)
        g2.add_edge(edge)

        g1.merge(g2)

        assert g1.edge_count() == 1


class TestDedupTypeNodesByLabel:
    def test_two_type_nodes_with_same_label_deduplicates_to_one(self, feature):
        g = CodeGraph(feature)

        type1 = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module1", "MyClass"),
            label="MyClass",
            file="module1.py",
            line=1,
        )
        type2 = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module2", "MyClass"),
            label="MyClass",
            file="module2.py",
            line=5,
        )

        g.add_node(type1)
        g.add_node(type2)

        assert g.node_count() == 2

        g.dedup_type_nodes_by_label()

        assert g.node_count() == 1
        assert g.has_node(type1.id)
        assert not g.has_node(type2.id)

    def test_edges_pointing_to_deleted_duplicate_get_rewritten(self, feature):
        g = CodeGraph(feature)

        type1 = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module1", "MyClass"),
            label="MyClass",
            file="module1.py",
            line=1,
        )
        type2 = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module2", "MyClass"),
            label="MyClass",
            file="module2.py",
            line=5,
        )
        consumer = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "consumer.py", "use_class"),
            label="use_class",
            file="consumer.py",
            line=10,
        )

        g.add_node(type1)
        g.add_node(type2)
        g.add_node(consumer)

        edge_to_type2 = Edge(
            from_id=consumer.id,
            to_id=type2.id,
            relation=EdgeRelation.USES_TYPE,
        )
        g.add_edge(edge_to_type2)

        assert g.edge_count() == 1
        assert g.get_node(type2.id) is not None

        g.dedup_type_nodes_by_label()

        assert g.edge_count() == 1
        edges = g.edges
        assert len(edges) == 1
        assert edges[0].to_id == type1.id
        assert not g.has_node(type2.id)

    def test_non_type_nodes_with_same_label_unaffected(self, feature):
        g = CodeGraph(feature)

        symbol1 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "helper"),
            label="helper",
            file="foo.py",
            line=1,
        )
        symbol2 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "bar.py", "helper"),
            label="helper",
            file="bar.py",
            line=2,
        )

        g.add_node(symbol1)
        g.add_node(symbol2)

        assert g.node_count() == 2

        g.dedup_type_nodes_by_label()

        assert g.node_count() == 2
        assert g.has_node(symbol1.id)
        assert g.has_node(symbol2.id)

    def test_type_node_with_contains_edge_not_deduplicated(self, feature):
        g = CodeGraph(feature)

        type_with_contains = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module1", "MyClass"),
            label="MyClass",
            file="module1.py",
            line=1,
        )
        type_forward_decl = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module2", "MyClass"),
            label="MyClass",
            file="module2.py",
            line=5,
        )
        field = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "module1.py", "field"),
            label="field",
            file="module1.py",
            line=2,
        )

        g.add_node(type_with_contains)
        g.add_node(type_forward_decl)
        g.add_node(field)

        contains_edge = Edge(
            from_id=type_with_contains.id,
            to_id=field.id,
            relation=EdgeRelation.CONTAINS,
        )
        g.add_edge(contains_edge)

        assert g.node_count() == 3

        g.dedup_type_nodes_by_label()

        assert g.node_count() == 2
        assert g.has_node(type_with_contains.id)
        assert not g.has_node(type_forward_decl.id)


class TestDropGhostNodes:
    def test_node_with_unresolved_prefix_dropped(self, feature):
        g = CodeGraph(feature)

        normal_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func"),
            label="func",
            file="foo.py",
            line=1,
        )

        edge = Edge(
            from_id=normal_node.id,
            to_id="unresolved::UnknownClass.method",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )

        g.add_node(normal_node)
        g.add_edge(edge)

        assert g.edge_count() == 1

        dropped = g.drop_ghost_nodes()

        assert dropped == 1
        assert g.edge_count() == 0
        assert g.has_node(normal_node.id)

    def test_node_with_unresolved_dot_prefix_dropped(self, feature):
        g = CodeGraph(feature)

        normal_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func"),
            label="func",
            file="foo.py",
            line=1,
        )

        ghost_id = symbol_id(feature, "bar.py", "_unresolved_.method")
        edge = Edge(
            from_id=normal_node.id,
            to_id=ghost_id,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )

        g.add_node(normal_node)
        g.add_edge(edge)

        assert g.edge_count() == 1

        dropped = g.drop_ghost_nodes()

        assert dropped == 1
        assert g.edge_count() == 0
        assert g.has_node(normal_node.id)

    def test_normal_nodes_not_dropped(self, feature):
        g = CodeGraph(feature)

        node1 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func1"),
            label="func1",
            file="foo.py",
            line=1,
        )
        node2 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "bar.py", "func2"),
            label="func2",
            file="bar.py",
            line=2,
        )

        edge = Edge(
            from_id=node1.id,
            to_id=node2.id,
            relation=EdgeRelation.CALLS,
        )

        g.add_node(node1)
        g.add_node(node2)
        g.add_edge(edge)

        assert g.node_count() == 2
        assert g.edge_count() == 1

        dropped = g.drop_ghost_nodes()

        assert dropped == 0
        assert g.node_count() == 2
        assert g.edge_count() == 1

    def test_edges_referencing_dropped_ghost_nodes_removed(self, feature):
        g = CodeGraph(feature)

        normal1 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "caller"),
            label="caller",
            file="foo.py",
            line=1,
        )
        normal2 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "bar.py", "normal_callee"),
            label="normal_callee",
            file="bar.py",
            line=2,
        )

        g.add_node(normal1)
        g.add_node(normal2)

        ghost_from_edge = Edge(
            from_id="unresolved::GhostClass",
            to_id=normal2.id,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        ghost_to_edge = Edge(
            from_id=normal1.id,
            to_id="unresolved::UnknownFunc",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        normal_edge = Edge(
            from_id=normal1.id,
            to_id=normal2.id,
            relation=EdgeRelation.CALLS,
        )

        g.add_edge(ghost_from_edge)
        g.add_edge(ghost_to_edge)
        g.add_edge(normal_edge)

        assert g.edge_count() == 3

        dropped = g.drop_ghost_nodes()

        assert dropped == 2
        assert g.edge_count() == 1
        edges = g.edges
        assert edges[0].from_id == normal1.id
        assert edges[0].to_id == normal2.id


class TestSerializationRoundTrip:
    def test_to_dict_from_dict_preserves_nodes_and_edges(self, feature):
        g1 = CodeGraph(feature)

        node1 = Node(
            type=NodeType.FILE,
            id=file_id(feature, "foo.py"),
            label="foo.py",
            file="foo.py",
            line=None,
        )
        node2 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "my_func"),
            label="my_func",
            file="foo.py",
            line=10,
        )

        g1.add_node(node1)
        g1.add_node(node2)

        edge = Edge(
            from_id=file_id(feature, "foo.py"),
            to_id=symbol_id(feature, "foo.py", "my_func"),
            relation=EdgeRelation.DEFINES,
        )
        g1.add_edge(edge)

        data = g1.to_dict()

        assert data["feature"] == feature
        assert data["stats"]["nodes"] == 2
        assert data["stats"]["edges"] == 1
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

    def test_round_trip_preserves_structure(self, feature, tmp_path):
        g1 = CodeGraph(feature)

        node1 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func1"),
            label="func1",
            file="foo.py",
            line=5,
            is_test=True,
        )
        node2 = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module", "MyClass"),
            label="MyClass",
            file="module.py",
            line=20,
            is_dataclass=True,
        )

        g1.add_node(node1)
        g1.add_node(node2)

        edge = Edge(
            from_id=node1.id,
            to_id=node2.id,
            relation=EdgeRelation.USES_TYPE,
            count=3,
        )
        g1.add_edge(edge)

        graph_file = tmp_path / "test_graph.json"
        g1.save(graph_file)
        g2 = CodeGraph.load(graph_file)

        assert g2.feature == g1.feature
        assert g2.node_count() == g1.node_count()
        assert g2.edge_count() == g1.edge_count()

        node1_loaded = g2.get_node(node1.id)
        assert node1_loaded is not None
        assert node1_loaded.label == "func1"
        assert node1_loaded.is_test is True
        assert node1_loaded.file == "foo.py"
        assert node1_loaded.line == 5

        node2_loaded = g2.get_node(node2.id)
        assert node2_loaded is not None
        assert node2_loaded.label == "MyClass"
        assert node2_loaded.is_dataclass is True

        edges = g2.edges
        assert len(edges) == 1
        assert edges[0].relation == EdgeRelation.USES_TYPE


class TestAllSymbolIds:
    def test_returns_only_symbol_and_type_node_ids(self, feature):
        g = CodeGraph(feature)

        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, "foo.py"),
            label="foo.py",
            file="foo.py",
            line=None,
        )
        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, "foo.py", "func"),
            label="func",
            file="foo.py",
            line=1,
        )
        type_node = Node(
            type=NodeType.TYPE,
            id=type_id(feature, "module", "MyClass"),
            label="MyClass",
            file="module.py",
            line=5,
        )
        dir_node = Node(
            type=NodeType.DIRECTORY,
            id="test_feature::dir::src",
            label="src",
            file=None,
            line=None,
        )

        g.add_node(file_node)
        g.add_node(symbol_node)
        g.add_node(type_node)
        g.add_node(dir_node)

        symbol_ids = g.all_symbol_ids()

        assert symbol_node.id in symbol_ids
        assert type_node.id in symbol_ids
        assert file_node.id not in symbol_ids
        assert dir_node.id not in symbol_ids
        assert len(symbol_ids) == 2

    def test_returns_empty_set_when_no_symbols_or_types(self, feature):
        g = CodeGraph(feature)

        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, "foo.py"),
            label="foo.py",
            file="foo.py",
            line=None,
        )

        g.add_node(file_node)

        symbol_ids = g.all_symbol_ids()

        assert len(symbol_ids) == 0
