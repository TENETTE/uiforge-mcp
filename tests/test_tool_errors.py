"""Errors that reach the model must say what went wrong and how to recover, never an empty message."""
import pytest

from uiforge_mcp import server as s


def _wrapped(fn):
    s.tool(fn)
    return s.mcp._tool_manager.get_tool(fn.__name__).fn if hasattr(s.mcp, "_tool_manager") else None


def test_errors_carry_tool_name_and_a_recovery_hint():
    def probe_value():
        raise ValueError("width must be > 0")

    def probe_bug():
        return 1 / 0

    def probe_key():
        return {}["radius"]

    for fn, needles in ((probe_value, ["probe_value", "width must be > 0", "call probe_value again"]),
                        (probe_bug, ["unexpected ZeroDivisionError", "likely a uiforge-mcp bug", "Do not repeat"]),
                        (probe_key, ["missing key 'radius'"])):
        wrapper = _wrapped(fn)
        if wrapper is None:
            pytest.skip("this MCP SDK does not expose registered tools")
        with pytest.raises(s.ToolError) as info:
            wrapper()
        for needle in needles:
            assert needle in str(info.value)


def test_missing_image_tells_to_use_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="absolute path"):
        s.view_image(str(tmp_path / "nope.png"))


def test_look_only_tools_are_marked_read_only_and_deletes_destructive():
    import asyncio
    tools = {t.name: t for t in asyncio.run(s.mcp.list_tools())}
    if tools["preview"].annotations is None:
        pytest.skip("this MCP SDK has no tool annotations")
    hint = {n: tools[n].annotations.model_dump(by_alias=True) for n in ("preview", "review_canvas", "add_rect",
                                                                        "delete_canvas", "undo")}
    assert hint["preview"]["readOnlyHint"] and hint["review_canvas"]["readOnlyHint"]
    assert not hint["add_rect"]["readOnlyHint"]
    assert hint["delete_canvas"]["destructiveHint"] and not hint["undo"]["destructiveHint"]


def test_every_public_tool_is_registered_and_no_helper_leaks():
    import asyncio
    names = {t.name for t in asyncio.run(s.mcp.list_tools())}
    assert {"export_theme", "export_pdf", "vectorize_image", "guide", "restyle", "path_ops"} <= names
    assert not any(n.startswith("_") for n in names)
