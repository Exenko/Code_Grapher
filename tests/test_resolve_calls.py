import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from CodeGrapher.schema import Node, Edge, NodeType, EdgeRelation, file_id, symbol_id, type_id
from CodeGrapher.graph import CodeGraph
from CodeGrapher import parser_typescript

resolve_calls_typescript = parser_typescript.resolve_calls


def resolve_calls_via_graph(graph, known_symbol_ids):
    graph.resolve_calls(known_symbol_ids)


@pytest.fixture
def feature():
    return "test_feature"


class TestResolveCoreLogic:
    @pytest.mark.parametrize("resolve_func", [
        resolve_calls_via_graph,
    ])
    def test_unresolved_call_in_registry_becomes_resolved(self, feature, resolve_func):
        graph = CodeGraph(feature)
        callee_id = symbol_id(feature, "bar.py", "callee")
        caller_id = symbol_id(feature, "foo.py", "caller")

        edge = Edge(
            from_id=caller_id,
            to_id=callee_id,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {callee_id}
        resolve_func(graph, known_symbols)

        resolved_edge = graph.edges[0]
        assert resolved_edge.unresolved is False
        assert resolved_edge.to_id == callee_id

    @pytest.mark.parametrize("resolve_func", [
        resolve_calls_via_graph,
    ])
    def test_unresolved_call_not_in_registry_stays_unresolved(self, feature, resolve_func):
        graph = CodeGraph(feature)
        caller_id = symbol_id(feature, "foo.py", "caller")
        unknown_id = symbol_id(feature, "unknown.py", "missing_func")

        edge = Edge(
            from_id=caller_id,
            to_id=unknown_id,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {symbol_id(feature, "bar.py", "other_func")}
        resolve_func(graph, known_symbols)

        resolved_edge = graph.edges[0]
        assert resolved_edge.unresolved is True
        assert resolved_edge.to_id == unknown_id

    @pytest.mark.parametrize("resolve_func", [
        resolve_calls_via_graph,
    ])
    def test_resolved_call_unchanged_regardless_of_registry(self, feature, resolve_func):
        graph = CodeGraph(feature)
        caller_id = symbol_id(feature, "foo.py", "caller")
        callee_id = symbol_id(feature, "bar.py", "callee")

        edge = Edge(
            from_id=caller_id,
            to_id=callee_id,
            relation=EdgeRelation.CALLS,
            unresolved=False,
        )
        graph.add_edge(edge)

        known_symbols = set()
        resolve_func(graph, known_symbols)

        resolved_edge = graph.edges[0]
        assert resolved_edge.unresolved is False

    @pytest.mark.parametrize("resolve_func", [
        resolve_calls_via_graph,
    ])
    def test_non_calls_edge_unchanged(self, feature, resolve_func):
        graph = CodeGraph(feature)
        from_id = file_id(feature, "foo.py")
        to_id = symbol_id(feature, "foo.py", "my_func")

        edge = Edge(
            from_id=from_id,
            to_id=to_id,
            relation=EdgeRelation.DEFINES,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {to_id}
        resolve_func(graph, known_symbols)

        result_edge = graph.edges[0]
        assert result_edge.unresolved is True

    @pytest.mark.parametrize("resolve_func", [
        resolve_calls_via_graph,
    ])
    def test_empty_registry(self, feature, resolve_func):
        graph = CodeGraph(feature)
        caller_id = symbol_id(feature, "foo.py", "caller")
        callee_id = symbol_id(feature, "bar.py", "callee")

        edge = Edge(
            from_id=caller_id,
            to_id=callee_id,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = set()
        resolve_func(graph, known_symbols)

        assert graph.edges[0].unresolved is True

    @pytest.mark.parametrize("resolve_func", [
        resolve_calls_via_graph,
    ])
    def test_multiple_edges_selective_resolution(self, feature, resolve_func):
        graph = CodeGraph(feature)
        caller1 = symbol_id(feature, "foo.py", "caller1")
        caller2 = symbol_id(feature, "foo.py", "caller2")
        resolvable = symbol_id(feature, "bar.py", "resolvable")
        unresolvable = symbol_id(feature, "missing.py", "unknown")

        edge1 = Edge(
            from_id=caller1,
            to_id=resolvable,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        edge2 = Edge(
            from_id=caller2,
            to_id=unresolvable,
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)

        known_symbols = {resolvable}
        resolve_func(graph, known_symbols)

        edges_by_to_id = {e.to_id: e for e in graph.edges}
        assert edges_by_to_id[resolvable].unresolved is False
        assert edges_by_to_id[unresolvable].unresolved is True


class TestTypeScriptSpecific:
    def test_unresolved_prefix_rewrite_found_in_registry(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="unresolved::my_func",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {"feat::bar.ts::my_func", "feat::utils.ts::other"}
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].to_id == "feat::bar.ts::my_func"
        assert graph.edges[0].unresolved is False

    def test_unresolved_prefix_not_in_registry_unchanged(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="unresolved::missing_func",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {"feat::bar.ts::other_func"}
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].to_id == "unresolved::missing_func"
        assert graph.edges[0].unresolved is True

    def test_non_unresolved_prefix_with_ts_resolver(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="feat::bar.ts::existing_func",
            relation=EdgeRelation.CALLS,
            unresolved=False,
        )
        graph.add_edge(edge)

        known_symbols = {"feat::bar.ts::existing_func"}
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].to_id == "feat::bar.ts::existing_func"
        assert graph.edges[0].unresolved is False

    def test_multiple_matches_uses_first(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="unresolved::render",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {
            "feat::components/ComponentA.ts::render",
            "feat::components/ComponentB.ts::render",
        }
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].unresolved is False
        assert graph.edges[0].to_id in known_symbols

    def test_unresolved_prefix_exact_name_match(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="unresolved::getUserData",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        suffix = "::getUserData"
        known_symbols = {
            "feat::api/client.ts::fetchData",
            "feat::utils/helpers.ts::getUserData",
            "feat::services/auth.ts::validateUser",
        }
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].to_id == "feat::utils/helpers.ts::getUserData"
        assert graph.edges[0].unresolved is False

    def test_typescript_empty_registry_stays_unresolved(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="unresolved::mystery_func",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = set()
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].to_id == "unresolved::mystery_func"
        assert graph.edges[0].unresolved is True

    def test_typescript_partial_name_no_match(self):
        graph = CodeGraph("feat")

        edge = Edge(
            from_id="feat::foo.ts::caller",
            to_id="unresolved::getData",
            relation=EdgeRelation.CALLS,
            unresolved=True,
        )
        graph.add_edge(edge)

        known_symbols = {
            "feat::utils.ts::setData",
            "feat::utils.ts::get_other_data",
        }
        resolve_calls_typescript(graph, known_symbols)

        assert graph.edges[0].to_id == "unresolved::getData"
        assert graph.edges[0].unresolved is True


class TestEdgeCases:
    def test_multiple_unresolved_calls_mixed_resolution(self, feature):
        graph = CodeGraph(feature)

        resolvable_1 = symbol_id(feature, "a.py", "func_a")
        resolvable_2 = symbol_id(feature, "b.py", "func_b")
        unresolvable_1 = symbol_id(feature, "missing.py", "unknown_1")
        unresolvable_2 = symbol_id(feature, "missing.py", "unknown_2")
        caller = symbol_id(feature, "main.py", "main")

        edges = [
            Edge(caller, resolvable_1, EdgeRelation.CALLS, unresolved=True),
            Edge(caller, resolvable_2, EdgeRelation.CALLS, unresolved=True),
            Edge(caller, unresolvable_1, EdgeRelation.CALLS, unresolved=True),
            Edge(caller, unresolvable_2, EdgeRelation.CALLS, unresolved=True),
        ]
        for e in edges:
            graph.add_edge(e)

        known_symbols = {resolvable_1, resolvable_2}
        resolve_calls_via_graph(graph, known_symbols)

        edges_by_to = {e.to_id: e for e in graph.edges}
        assert edges_by_to[resolvable_1].unresolved is False
        assert edges_by_to[resolvable_2].unresolved is False
        assert edges_by_to[unresolvable_1].unresolved is True
        assert edges_by_to[unresolvable_2].unresolved is True

    def test_imports_edge_unchanged(self, feature):
        graph = CodeGraph(feature)

        from_id = symbol_id(feature, "foo.py", "caller")
        to_id = symbol_id(feature, "bar.py", "something")

        edge = Edge(from_id, to_id, EdgeRelation.IMPORTS, unresolved=True)
        graph.add_edge(edge)

        known_symbols = {to_id}
        resolve_calls_via_graph(graph, known_symbols)

        assert graph.edges[0].unresolved is True

    def test_uses_type_edge_unchanged(self, feature):
        graph = CodeGraph(feature)

        from_id = symbol_id(feature, "foo.py", "func")
        to_id = type_id(feature, "models", "UserType")

        edge = Edge(from_id, to_id, EdgeRelation.USES_TYPE, unresolved=True)
        graph.add_edge(edge)

        known_symbols = {to_id}
        resolve_calls_via_graph(graph, known_symbols)

        assert graph.edges[0].unresolved is True

    def test_graph_with_no_edges(self, feature):
        graph = CodeGraph(feature)
        known_symbols = {symbol_id(feature, "foo.py", "func")}

        resolve_calls_via_graph(graph, known_symbols)

        assert len(graph.edges) == 0

    def test_graph_with_only_resolved_calls(self, feature):
        graph = CodeGraph(feature)
        caller = symbol_id(feature, "foo.py", "caller")
        callee = symbol_id(feature, "bar.py", "callee")

        edge = Edge(caller, callee, EdgeRelation.CALLS, unresolved=False)
        graph.add_edge(edge)

        known_symbols = set()
        resolve_calls_via_graph(graph, known_symbols)

        assert graph.edges[0].unresolved is False

    def test_symbol_in_registry_but_no_matching_edge(self, feature):
        graph = CodeGraph(feature)
        caller = symbol_id(feature, "foo.py", "caller")
        callee = symbol_id(feature, "bar.py", "callee")

        edge = Edge(caller, callee, EdgeRelation.CALLS, unresolved=False)
        graph.add_edge(edge)

        # Put a totally different symbol in the registry — no edge points to it
        unrelated = symbol_id(feature, "other.py", "unrelated")
        resolve_calls_via_graph(graph, {unrelated})

        assert graph.edge_count() == 1
        assert graph.edges[0].unresolved is False
        assert graph.edges[0].to_id == callee
