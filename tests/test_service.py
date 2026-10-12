"""Offline tests for the textual-result pipeline (no model calls).

Verifies the reply-text contract and that ``describe_image`` sends the image
path to the agent and returns the agent's textual answer.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from imageblinds import service


def test_reply_text_prefers_output_key():
    assert service.reply_text({"output": "a chair", "content": "other"}) == "a chair"


def test_reply_text_falls_back_to_content_key():
    assert service.reply_text({"content": "a fridge"}) == "a fridge"


def test_reply_text_accepts_answer_and_result_keys():
    assert service.reply_text({"answer": "x"}) == "x"
    assert service.reply_text({"result": "y"}) == "y"


def test_reply_text_from_object_content():
    assert service.reply_text(SimpleNamespace(content="a chair")) == "a chair"


def test_reply_text_from_object_without_content():
    assert service.reply_text(SimpleNamespace(value="hi")) == "namespace(value='hi')"


def test_reply_text_empty_results():
    assert service.reply_text(None) == ""
    assert service.reply_text({}) == ""


@pytest.mark.asyncio
async def test_describe_image_returns_agent_text(stub_pipeline, tmp_path):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    text = await service.describe_image(image)

    assert text == "This image shows a chair."


@pytest.mark.asyncio
async def test_describe_image_query_references_image_path(stub_pipeline, tmp_path):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    await service.describe_image(image)

    assert stub_pipeline.last_query is not None
    assert str(image) in stub_pipeline.last_query


@pytest.mark.asyncio
async def test_describe_image_falls_back_to_direct_model_on_dsml_reply(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    dsml_reply = (
        "<|DSML| calls><|DSML| invoke name=\"Read\">"
        f"<|DSML| parameter name=\"file_path\" string=\"true\">{image}</|DSML| parameter>"
        "</|DSML| invoke></|DSML| calls>"
    )

    async def fake_run_agent(agent, query):
        agent.last_query = query
        return {"output": dsml_reply, "result_type": "answer"}

    calls: dict = {}

    async def fake_direct(image_path):
        calls["image_path"] = str(image_path)
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert text == "This image shows a chair."
    assert calls.get("image_path") == str(image)


@pytest.mark.asyncio
async def test_describe_image_falls_back_on_iteration_limit(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    async def fake_run_agent(agent, query):
        return {"output": "Max iterations reached without completion", "result_type": "error"}

    async def fake_direct(image_path):
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert text == "This image shows a chair."


@pytest.mark.asyncio
async def test_describe_image_falls_back_on_fs_failure_reply(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    async def fake_run_agent(agent, query):
        return {
            "output": (
                "I'm unable to describe this image - the read_file call failed 3 times "
                "with infrastructure errors, so I have no actual visual data to report."
            ),
            "result_type": "answer",
        }

    async def fake_direct(image_path):
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert text == "This image shows a chair."


@pytest.mark.asyncio
async def test_describe_image_falls_back_when_agent_run_times_out(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    async def fake_run_agent(agent, query):
        raise TimeoutError

    async def fake_direct(image_path):
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert text == "This image shows a chair."


@pytest.mark.asyncio
async def test_describe_image_ignores_dsml_paths_that_do_not_exist(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    dsml_reply = (
        '<|DSML| invoke name="Read">'
        '<|DSML| parameter name="file_path" string="true">/does/not/exist.jpg</|DSML| parameter>'
        "</|DSML| invoke> The image shows a chair."
    )

    async def fake_run_agent(agent, query):
        return {"output": dsml_reply, "result_type": "answer"}

    async def fake_direct(_image_path):
        raise AssertionError("direct call must not run for a missing path")

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert "The image shows a chair" in text
    assert "DSML" not in text


@pytest.mark.asyncio
async def test_describe_image_falls_back_when_agent_cannot_read(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    async def fake_run_agent(agent, query):
        return {
            "output": "I can't read the image because the read_file tool isn't available.",
            "result_type": "answer",
        }

    calls: dict = {}

    async def fake_direct(image_path):
        calls["image_path"] = str(image_path)
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert text == "This image shows a chair."
    assert calls.get("image_path") == str(image)
