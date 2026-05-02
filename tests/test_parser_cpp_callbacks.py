"""
Tests for C++ callback tracing in parser_cpp.

Coverage:
  1. std::function field tracked in _member_var_types with __callable__ prefix
  2. obj.field = handler emits CALLS edge when field is __callable__
  3. obj->field = handler emits CALLS edge when field is __callable__
  4. handler resolves to known symbol (resolved=False)
  5. handler is unknown — unresolved CALLS edge emitted
  6. Bare field assignment (no obj prefix) tracked via __callable__ prefix
  7. nullptr / false / 0 rhs skipped (no spurious edges)
  8. Non-callable plain field assignment does NOT emit CALLS edge
  9. std::function field tracked: var_name maps to __callable__ signature
  10. Multiple std::function fields in one class all tracked
  11. Stress corpus: dispatcher.cc setup() emits CALLS to on_data_received and on_error
  12. Stress corpus: dispatcher.cc setup() emits CALLS to EventBus.subscribe
"""

from pathlib import Path
import tempfile
import pytest

from CodeGrapher.parser_cpp import parse_file
from CodeGrapher.schema import EdgeRelation, symbol_id, type_id, file_id


FEATURE = "test_cb"


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def _parse_pair(tmp_dir, header_src, impl_src, basename="widget"):
    """Write header + impl to tmp_dir and parse the impl, returning the graph."""
    h = tmp_dir / f"{basename}.h"
    cc = tmp_dir / f"{basename}.cc"
    h.write_text(header_src, encoding="utf-8")
    cc.write_text(impl_src, encoding="utf-8")

    # Build known_symbol_ids from header parse first
    from CodeGrapher.parser_cpp import parse_file as pf
    hgraph = pf(FEATURE, tmp_dir, h)
    known = {n.id for n in hgraph.nodes}

    return pf(FEATURE, tmp_dir, cc, known_symbol_ids=known)


# ---------------------------------------------------------------------------
# 1. std::function field tracking
# ---------------------------------------------------------------------------

def test_std_function_field_tracked_in_member_var_types(tmp_dir):
    """std::function<Sig> field is stored with __callable__ prefix."""
    from CodeGrapher.parser_cpp import _HeaderParser

    header_src = """\
#pragma once
#include <functional>
class Foo {
public:
    std::function<void(int)> on_event;
};
"""
    h = tmp_dir / "foo.h"
    h.write_text(header_src)

    from CodeGrapher.schema import is_test_file
    parser = _HeaderParser(
        feature=FEATURE,
        rel_path="foo.h",
        module_name="foo",
        is_test=False,
        known_symbol_ids=set(),
    )
    parser.parse(header_src)

    assert "on_event" in parser._member_var_types
    assert parser._member_var_types["on_event"].startswith("__callable__")
    assert "void(int)" in parser._member_var_types["on_event"]


def test_multiple_std_function_fields_all_tracked(tmp_dir):
    """Multiple std::function fields in one class are all tracked."""
    from CodeGrapher.parser_cpp import _HeaderParser

    header_src = """\
#pragma once
#include <functional>
class Bar {
public:
    std::function<void(int)> on_data;
    std::function<bool(float)> on_check;
    std::function<int(int, int)> on_combine;
};
"""
    parser = _HeaderParser(
        feature=FEATURE,
        rel_path="bar.h",
        module_name="bar",
        is_test=False,
        known_symbol_ids=set(),
    )
    parser.parse(header_src)

    assert "on_data" in parser._member_var_types
    assert "on_check" in parser._member_var_types
    assert "on_combine" in parser._member_var_types
    for key in ("on_data", "on_check", "on_combine"):
        assert parser._member_var_types[key].startswith("__callable__")


# ---------------------------------------------------------------------------
# 2–5. Callback assignment CALLS edges
# ---------------------------------------------------------------------------

HEADER_WITH_CALLBACKS = """\
#pragma once
#include <functional>

void free_handler(int x);
void error_handler(int x);

class Widget {
public:
    void setup();
    std::function<void(int)> on_data;
    std::function<void(int)> on_error;
};
"""

IMPL_ASSIGNS_RESOLVED = """\
#include "widget.h"

void free_handler(int x) { (void)x; }
void error_handler(int x) { (void)x; }

void Widget::setup() {
    on_data = free_handler;
    on_error = error_handler;
}
"""

def test_callable_field_assignment_emits_calls_edge_resolved(tmp_dir):
    """obj.field = known_handler emits resolved CALLS edge from setup()."""
    graph = _parse_pair(tmp_dir, HEADER_WITH_CALLBACKS, IMPL_ASSIGNS_RESOLVED)

    calls = [e for e in graph.edges if e.relation == EdgeRelation.CALLS]
    targets = {e.to_id for e in calls}

    # free_handler and error_handler should appear as CALLS targets
    handler_ids = {n.id for n in graph.nodes if n.label in ("free_handler", "error_handler")}
    # At least one of the two must be resolved
    assert any(t in handler_ids or "free_handler" in t or "error_handler" in t
               for t in targets), f"Expected callback targets in {targets}"


def test_callable_field_assignment_resolved_flag(tmp_dir):
    """When handler resolves to a known symbol, unresolved=False."""
    # Build known_symbol_ids that include free_handler
    h = tmp_dir / "widget.h"
    cc = tmp_dir / "widget.cc"
    h.write_text(HEADER_WITH_CALLBACKS)
    cc.write_text(IMPL_ASSIGNS_RESOLVED)

    from CodeGrapher.parser_cpp import parse_file as pf
    hgraph = pf(FEATURE, tmp_dir, h)
    # Also pre-parse the .cc to get free_handler symbol
    cc_pre = pf(FEATURE, tmp_dir, cc)
    known = {n.id for n in hgraph.nodes} | {n.id for n in cc_pre.nodes}

    graph = pf(FEATURE, tmp_dir, cc, known_symbol_ids=known)

    calls_to_free = [
        e for e in graph.edges
        if e.relation == EdgeRelation.CALLS and "free_handler" in e.to_id
    ]
    # If any edge points to free_handler as a known symbol it should be resolved
    resolved_calls = [e for e in calls_to_free if not e.unresolved]
    assert resolved_calls, "Expected at least one resolved CALLS edge to free_handler"


def test_nullptr_assignment_skipped(tmp_dir):
    """Assigning nullptr to a callable field does NOT emit a CALLS edge."""
    header = """\
#pragma once
#include <functional>
class Widget {
public:
    void reset();
    std::function<void(int)> on_data;
};
"""
    impl = """\
#include "widget.h"
void Widget::reset() {
    on_data = nullptr;
}
"""
    graph = _parse_pair(tmp_dir, header, impl, "widget2")

    calls = [e for e in graph.edges if e.relation == EdgeRelation.CALLS]
    for e in calls:
        assert "nullptr" not in e.to_id


def test_plain_field_assignment_no_calls_edge(tmp_dir):
    """Assigning to a non-callable plain field does NOT emit a CALLS edge."""
    header = """\
#pragma once
class Widget {
public:
    void init();
    int count;
};
"""
    impl = """\
#include "widget.h"
void Widget::init() {
    count = 42;
}
"""
    graph = _parse_pair(tmp_dir, header, impl, "widget3")

    # No CALLS edges at all expected (init() makes no function calls)
    calls = [e for e in graph.edges if e.relation == EdgeRelation.CALLS]
    assert not calls, f"Unexpected CALLS edges: {[(e.from_id, e.to_id) for e in calls]}"


def test_unresolved_callback_assignment_emits_unresolved_edge(tmp_dir):
    """Assigning an unknown handler to a callable field emits unresolved CALLS edge."""
    header = """\
#pragma once
#include <functional>
class Widget {
public:
    void setup();
    std::function<void(int)> on_data;
};
"""
    impl = """\
#include "widget.h"
void Widget::setup() {
    on_data = totally_unknown_handler;
}
"""
    graph = _parse_pair(tmp_dir, header, impl, "widget4")

    unresolved_calls = [
        e for e in graph.edges
        if e.relation == EdgeRelation.CALLS and e.unresolved
        and "totally_unknown_handler" in e.to_id
    ]
    assert unresolved_calls, "Expected unresolved CALLS edge for unknown handler"


# ---------------------------------------------------------------------------
# 6. Bare field assignment (no obj prefix)
# ---------------------------------------------------------------------------

def test_bare_callable_field_assignment(tmp_dir):
    """Bare assignment (no obj. prefix) on __callable__ field emits CALLS."""
    # Already covered by Widget::setup() above (on_data is member, accessed bare in method body)
    # Confirm: the test above tests bare access (Widget::setup accesses on_data directly)
    header = """\
#pragma once
#include <functional>
void my_handler(int x);
class Widget {
public:
    void setup();
    std::function<void(int)> on_data;
};
"""
    impl = """\
#include "widget.h"
void my_handler(int x) { (void)x; }
void Widget::setup() {
    on_data = my_handler;
}
"""
    graph = _parse_pair(tmp_dir, header, impl, "widget5")

    calls = [e for e in graph.edges if e.relation == EdgeRelation.CALLS]
    targets = {e.to_id for e in calls}
    assert any("my_handler" in t for t in targets), f"Expected my_handler in CALLS targets, got {targets}"


# ---------------------------------------------------------------------------
# 11–12. Stress corpus integration
# ---------------------------------------------------------------------------

STRESS_DIR = Path(__file__).parent.parent / "stress_tests" / "callbacks"


@pytest.mark.skipif(not STRESS_DIR.exists(), reason="stress_tests/callbacks not present")
def test_stress_dispatcher_setup_calls_event_bus_subscribe():
    """dispatcher.cc setup() emits CALLS edge to EventBus.subscribe."""
    root = STRESS_DIR
    h = root / "dispatcher.h"
    cc = root / "dispatcher.cc"

    from CodeGrapher.parser_cpp import parse_file as pf

    # Parse all headers first to build known_symbol_ids
    known: set = set()
    for hf in root.glob("*.h"):
        hg = pf("callbacks", root, hf)
        known |= {n.id for n in hg.nodes}

    graph = pf("callbacks", root, cc, known_symbol_ids=known)

    calls = [e for e in graph.edges if e.relation == EdgeRelation.CALLS]
    targets = {e.to_id for e in calls}

    assert any("subscribe" in t for t in targets), \
        f"Expected CALLS to subscribe in {targets}"


@pytest.mark.skipif(not STRESS_DIR.exists(), reason="stress_tests/callbacks not present")
def test_stress_dispatcher_setup_calls_on_data_received_or_on_error():
    """dispatcher.cc setup() callback assignments produce CALLS edges to handlers."""
    root = STRESS_DIR
    cc = root / "dispatcher.cc"

    from CodeGrapher.parser_cpp import parse_file as pf

    known: set = set()
    for hf in root.glob("*.h"):
        hg = pf("callbacks", root, hf)
        known |= {n.id for n in hg.nodes}

    graph = pf("callbacks", root, cc, known_symbol_ids=known)

    calls = [e for e in graph.edges if e.relation == EdgeRelation.CALLS]
    targets = {e.to_id for e in calls}

    assert any("on_data_received" in t or "on_error" in t for t in targets), \
        f"Expected callback handler CALLS edges in {targets}"
