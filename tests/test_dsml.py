"""DSML parser tests using the exact markup shape DeepSeek V4 emits."""

from __future__ import annotations

from imageblinds import dsml

REAL_REPLY = (
    "<｜DSML｜ calls><｜DSML｜ invoke name=\"Read\">"
    "<｜DSML｜ parameter name=\"file_path\" string=\"true\">"
    "/home/yoni/agents/camera/runtime/workspace/uploads/8be2826e004e4c85bdc5fd5f4c14caf4.jpg"
    "</｜DSML｜ parameter></｜DSML｜ invoke></｜DSML｜ calls>"
)


def test_parse_invokes_extracts_read_call():
    calls = dsml.parse_invokes(REAL_REPLY)
    assert calls == [
        {
            "name": "Read",
            "params": {
                "file_path": "/home/yoni/agents/camera/runtime/workspace/uploads/8be2826e004e4c85bdc5fd5f4c14caf4.jpg"
            },
        }
    ]


def test_parse_invokes_accepts_ascii_markup():
    text = '<|DSML| invoke name="Read"><|DSML| parameter name="file_path" string="true">/tmp/a.jpg</|DSML| parameter></|DSML| invoke>'
    assert dsml.parse_invokes(text) == [{"name": "Read", "params": {"file_path": "/tmp/a.jpg"}}]


def test_parse_invokes_handles_self_closing_parameter():
    text = '<|DSML| invoke name="Foo"><|DSML| parameter name="bar" value="baz"/> </|DSML| invoke>'
    calls = dsml.parse_invokes(text)
    assert calls[0]["params"].get("bar") == "baz"


def test_parse_invokes_empty_for_plain_text():
    assert dsml.parse_invokes("This image shows a chair.") == []


def test_strip_markup_removes_tags():
    cleaned = dsml.strip_markup(REAL_REPLY + " answer text")
    assert "answer text" in cleaned
    assert "DSML" not in cleaned


def test_normalize_maps_fullwidth_delimiters():
    assert dsml.normalize("＜｜DSML｜＞") == "<|DSML|>"
