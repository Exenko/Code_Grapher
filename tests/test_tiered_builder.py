import tempfile
from pathlib import Path
import pytest
from CodeGrapher.schema import Node, Edge, NodeType, EdgeRelation, file_id, symbol_id
from CodeGrapher.graph import CodeGraph
from CodeGrapher.tiered_builder import _detect_entry_points, _make_slug


class TestMakeSlug:
    def test_simple_filename(self):
        assert _make_slug("main.py") == "main_main"

    def test_path_with_subdirectory(self):
        assert _make_slug("Client_Side/utils/autofill_engine.py") == "main_Client_Side_utils_autofill_engine"

    def test_windows_path_normalization(self):
        assert _make_slug("Client_Side\\utils\\autofill_engine.py") == "main_Client_Side_utils_autofill_engine"

    def test_file_without_extension(self):
        assert _make_slug("main") == "main_main"

    def test_nested_directory_structure(self):
        assert _make_slug("src/module/submodule/handler.py") == "main_src_module_submodule_handler"

    def test_single_directory(self):
        assert _make_slug("utils/helper.py") == "main_utils_helper"

    def test_preserves_underscores_in_name(self):
        assert _make_slug("my_app_file.py") == "main_my_app_file"


class TestDetectEntryPointsWithMainBlock:
    def test_main_block_detected(self, tmp_path, feature):
        main_file = tmp_path / "main.py"
        main_file.write_text("if __name__ == '__main__':\n    print('hello')")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(main_file)),
            label="main.py",
            file=str(main_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["file"] == str(main_file)
        assert result[0]["reason"] == "contains if __name__ == '__main__' block"
        assert result[0]["slug"].startswith("main_")

    def test_main_block_but_script_file_excluded(self, tmp_path, feature):
        setup_file = tmp_path / "setup_database.py"
        setup_file.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(setup_file)),
            label="setup_database.py",
            file=str(setup_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_main_block_in_test_file_excluded(self, tmp_path, feature):
        test_file = tmp_path / "test_main.py"
        test_file.write_text("if __name__ == '__main__':\n    pytest.main()")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(test_file)),
            label="test_main.py",
            file=str(test_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_main_block_in_tests_directory_excluded(self, tmp_path, feature):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_script = tests_dir / "runner.py"
        test_script.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(test_script)),
            label="runner.py",
            file=str(test_script),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_main_block_in_scripts_directory_excluded(self, tmp_path, feature):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        script = scripts_dir / "runner.py"
        script.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(script)),
            label="runner.py",
            file=str(script),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_main_block_in_utils_directory_excluded(self, tmp_path, feature):
        utils_dir = tmp_path / "utils"
        utils_dir.mkdir()
        util = utils_dir / "handler.py"
        util.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(util)),
            label="handler.py",
            file=str(util),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0


class TestDetectEntryPointsWithScriptPatterns:
    def test_migrate_file_excluded(self, tmp_path, feature):
        migrate_file = tmp_path / "migrate_schema.py"
        migrate_file.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(migrate_file)),
            label="migrate_schema.py",
            file=str(migrate_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_populate_file_excluded(self, tmp_path, feature):
        populate_file = tmp_path / "populate_cache.py"
        populate_file.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(populate_file)),
            label="populate_cache.py",
            file=str(populate_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_autocomplete_file_excluded(self, tmp_path, feature):
        autocomplete_file = tmp_path / "autocomplete_engine.py"
        autocomplete_file.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(autocomplete_file)),
            label="autocomplete_engine.py",
            file=str(autocomplete_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0


class TestDetectEntryPointsWithInitFiles:
    def test_init_py_with_exports(self, tmp_path, feature):
        init_file = tmp_path / "__init__.py"
        init_file.write_text("")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(init_file)),
            label="__init__.py",
            file=str(init_file),
            line=None,
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(init_file), "exported_func"),
            label="exported_func",
            file=str(init_file),
            line=1,
        )
        graph.add_node(symbol_node)

        edge = Edge(
            from_id=file_id(feature, str(init_file)),
            to_id=symbol_id(feature, str(init_file), "exported_func"),
            relation=EdgeRelation.DEFINES,
        )
        graph.add_edge(edge)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["file"] == str(init_file)
        assert result[0]["reason"] == "package surface with exports (__init__.py)"

    def test_init_py_without_exports(self, tmp_path, feature):
        init_file = tmp_path / "__init__.py"
        init_file.write_text("")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(init_file)),
            label="__init__.py",
            file=str(init_file),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0

    def test_init_py_with_contains_edge(self, tmp_path, feature):
        init_file = tmp_path / "__init__.py"
        init_file.write_text("")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(init_file)),
            label="__init__.py",
            file=str(init_file),
            line=None,
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(init_file), "Class"),
            label="Class",
            file=str(init_file),
            line=1,
        )
        graph.add_node(symbol_node)

        edge = Edge(
            from_id=file_id(feature, str(init_file)),
            to_id=symbol_id(feature, str(init_file), "Class"),
            relation=EdgeRelation.CONTAINS,
        )
        graph.add_edge(edge)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["reason"] == "package surface with exports (__init__.py)"


class TestDetectEntryPointsWithCppMain:
    def test_cpp_main_function_detected(self, tmp_path, feature):
        cpp_file = tmp_path / "server.cc"
        cpp_file.write_text("int main() { return 0; }")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(cpp_file)),
            label="server.cc",
            file=str(cpp_file),
            line=None,
            language="cpp",
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(cpp_file), "main"),
            label="main",
            file=str(cpp_file),
            line=1,
            language="cpp",
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["file"] == str(cpp_file)
        assert result[0]["reason"] == "C++ main() function"

    def test_cpp_main_cpp_extension(self, tmp_path, feature):
        cpp_file = tmp_path / "app.cpp"
        cpp_file.write_text("int main() { return 0; }")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(cpp_file)),
            label="app.cpp",
            file=str(cpp_file),
            line=None,
            language="cpp",
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(cpp_file), "main"),
            label="main",
            file=str(cpp_file),
            line=1,
            language="cpp",
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["reason"] == "C++ main() function"

    def test_cpp_main_c_extension(self, tmp_path, feature):
        c_file = tmp_path / "program.c"
        c_file.write_text("int main() { return 0; }")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(c_file)),
            label="program.c",
            file=str(c_file),
            line=None,
            language="c",
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(c_file), "main"),
            label="main",
            file=str(c_file),
            line=1,
            language="c",
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1

    def test_python_main_not_cpp_style(self, tmp_path, feature):
        py_file = tmp_path / "main.py"
        py_file.write_text("def main():\n    pass\n\nif __name__ == '__main__':\n    main()")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(py_file)),
            label="main.py",
            file=str(py_file),
            line=None,
            language="python",
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(py_file), "main"),
            label="main",
            file=str(py_file),
            line=1,
            language="python",
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["reason"] == "contains if __name__ == '__main__' block"


class TestDetectEntryPointsSymbolMarked:
    def test_symbol_with_entry_point_flag(self, tmp_path, feature):
        py_file = tmp_path / "handlers.py"
        py_file.write_text("")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(py_file)),
            label="handlers.py",
            file=str(py_file),
            line=None,
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(py_file), "route_handler"),
            label="route_handler",
            file=str(py_file),
            line=10,
            entry_point=True,
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["file"] == str(py_file)
        assert result[0]["reason"] == "contains entry point: route_handler"

    def test_multiple_symbols_marked_entry_point_same_file(self, tmp_path, feature):
        py_file = tmp_path / "handlers.py"
        py_file.write_text("")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(py_file)),
            label="handlers.py",
            file=str(py_file),
            line=None,
        )
        graph.add_node(file_node)

        symbol1 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(py_file), "handler1"),
            label="handler1",
            file=str(py_file),
            line=10,
            entry_point=True,
        )
        graph.add_node(symbol1)

        symbol2 = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(py_file), "handler2"),
            label="handler2",
            file=str(py_file),
            line=20,
            entry_point=True,
        )
        graph.add_node(symbol2)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["file"] == str(py_file)
        assert result[0]["reason"] == "contains entry point: handler1"


class TestDetectEntryPointsMultiple:
    def test_multiple_entry_points_different_files(self, tmp_path, feature):
        main_file = tmp_path / "main.py"
        main_file.write_text("if __name__ == '__main__':\n    pass")

        cpp_file = tmp_path / "server.cc"
        cpp_file.write_text("int main() { }")

        graph = CodeGraph(feature)
        main_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(main_file)),
            label="main.py",
            file=str(main_file),
            line=None,
        )
        graph.add_node(main_node)

        cpp_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(cpp_file)),
            label="server.cc",
            file=str(cpp_file),
            line=None,
            language="cpp",
        )
        graph.add_node(cpp_node)

        cpp_symbol = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(cpp_file), "main"),
            label="main",
            file=str(cpp_file),
            line=1,
            language="cpp",
        )
        graph.add_node(cpp_symbol)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 2
        files = {r["file"] for r in result}
        assert str(main_file) in files
        assert str(cpp_file) in files

    def test_no_duplicate_entry_points_from_same_file(self, tmp_path, feature):
        main_file = tmp_path / "main.py"
        main_file.write_text("if __name__ == '__main__':\n    pass")

        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(main_file)),
            label="main.py",
            file=str(main_file),
            line=None,
        )
        graph.add_node(file_node)

        symbol_node = Node(
            type=NodeType.SYMBOL,
            id=symbol_id(feature, str(main_file), "main"),
            label="main",
            file=str(main_file),
            line=1,
            entry_point=True,
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 1
        assert result[0]["reason"] == "contains if __name__ == '__main__' block"


class TestDetectEntryPointsEmpty:
    def test_empty_graph(self, feature):
        graph = CodeGraph(feature)
        result = _detect_entry_points(graph, feature)
        assert result == []

    def test_graph_with_no_files(self, feature):
        graph = CodeGraph(feature)
        symbol_node = Node(
            type=NodeType.SYMBOL,
            id="test_feature::some_symbol",
            label="some_symbol",
            file=None,
            line=None,
        )
        graph.add_node(symbol_node)

        result = _detect_entry_points(graph, feature)
        assert result == []

    def test_file_node_without_file_path(self, feature):
        graph = CodeGraph(feature)
        file_node = Node(
            type=NodeType.FILE,
            id=file_id(feature, "orphan.py"),
            label="orphan.py",
            file=None,
            line=None,
        )
        graph.add_node(file_node)

        result = _detect_entry_points(graph, feature)
        assert result == []


class TestDetectEntryPointsConftest:
    def test_conftest_py_excluded(self, tmp_path, feature):
        conftest = tmp_path / "conftest.py"
        conftest.write_text("def pytest_configure():\n    pass")

        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, str(conftest)),
            label="conftest.py",
            file=str(conftest),
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0


class TestDetectEntryPointsNonexistentFile:
    def test_nonexistent_file_with_main_block_check(self, feature):
        fake_path = "/nonexistent/file.py"
        graph = CodeGraph(feature)
        node = Node(
            type=NodeType.FILE,
            id=file_id(feature, fake_path),
            label="file.py",
            file=fake_path,
            line=None,
        )
        graph.add_node(node)

        result = _detect_entry_points(graph, feature)
        assert len(result) == 0
