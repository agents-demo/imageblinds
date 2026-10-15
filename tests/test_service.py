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

    async def fake_direct(image_path, lang="en"):
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

    async def fake_direct(image_path, lang="en"):
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

    async def fake_direct(image_path, lang="en"):
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

    async def fake_direct(image_path, lang="en"):
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

    async def fake_direct(_image_path, lang="en"):
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

    async def fake_direct(image_path, lang="en"):
        calls["image_path"] = str(image_path)
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image)

    assert text == "This image shows a chair."
    assert calls.get("image_path") == str(image)


class FakeModel:
    """Stands in for the vision model: records messages, returns a reply."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: list | None = None

    async def invoke(self, messages: list) -> SimpleNamespace:
        self.messages = messages
        return SimpleNamespace(content=self.reply)


@pytest.mark.asyncio
async def test_answer_question_returns_model_reply(monkeypatch, tmp_path):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    fake = FakeModel("It is made of wood.")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    answer = await service.answer_question(image, "What is it made of?")

    assert answer == "It is made of wood."
    assert fake.messages is not None
    assert fake.messages[0]["content"] == service.vision.QUESTION_PROMPT
    user = fake.messages[1]["content"]
    assert user[0]["text"] == "What is it made of?"
    assert user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_answer_question_empty_reply(monkeypatch, tmp_path):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel(""))

    assert await service.answer_question(image, "What is it?") == ""


@pytest.mark.asyncio
async def test_answer_question_uses_chinese_prompt(monkeypatch, tmp_path):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    fake = FakeModel("这是木制的。")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    answer = await service.answer_question(image, "它是什么做的？", lang="zh")

    assert answer == "这是木制的。"
    assert fake.messages is not None
    assert fake.messages[0]["content"] == service.vision.QUESTION_PROMPT_ZH


@pytest.mark.asyncio
async def test_describe_image_uses_chinese_query(stub_pipeline, tmp_path):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    await service.describe_image(image, lang="zh")

    assert stub_pipeline.last_query is not None
    assert "读取" in stub_pipeline.last_query
    assert str(image) in stub_pipeline.last_query


@pytest.mark.asyncio
async def test_describe_image_falls_back_on_chinese_read_failure(
    monkeypatch, stub_pipeline, tmp_path
):
    image = tmp_path / "chair.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    async def fake_run_agent(agent, query):
        return {"output": "无法读取该图像，因为 read_file 工具不可用。", "result_type": "answer"}

    calls: dict = {}

    async def fake_direct(image_path, lang="en"):
        calls["lang"] = lang
        return "This image shows a chair."

    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    monkeypatch.setattr(service, "_ask_model_directly", fake_direct)

    text = await service.describe_image(image, lang="zh")

    assert text == "This image shows a chair."
    assert calls.get("lang") == "zh"


@pytest.mark.asyncio
async def test_answer_question_rejects_unreadable_image(monkeypatch, tmp_path):
    missing = tmp_path / "nope.jpg"

    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel("x"))

    with pytest.raises(ValueError):
        await service.answer_question(missing, "What is it?")


def test_normalize_url_adds_https_and_strips_spaces():
    assert service._normalize_url("example.com") == "https://example.com"
    assert service._normalize_url(" https://example.com ") == "https://example.com"
    assert service._normalize_url("http://example.com") == "http://example.com"
    assert service._normalize_url("example.com/page") == "https://example.com/page"


def test_normalize_url_fixes_speech_artifacts():
    assert service._normalize_url("example dot com") == "https://example.com"
    assert service._normalize_url("agents-demo dot github dot io slash imageblinds") == (
        "https://agents-demo.github.io/imageblinds"
    )
    assert service._normalize_url("https colon slash slash example dot com") == (
        "https://example.com"
    )


def test_normalize_url_rejects_invalid():
    assert service._normalize_url("") is None
    assert service._normalize_url("   ") is None
    assert service._normalize_url("javascript:alert(1)") is None
    assert service._normalize_url("...") is None


@pytest.mark.asyncio
async def test_interpret_command_returns_describe(monkeypatch):
    fake = FakeModel("ACTION: describe")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    result = await service.interpret_command("describe the picture")

    assert result == {"action": "describe"}
    assert fake.messages is not None
    assert fake.messages[0]["content"] == service.vision.COMMAND_PROMPT
    assert fake.messages[1]["content"] == (
        "Current app language: en\nSpoken command: describe the picture"
    )


@pytest.mark.asyncio
async def test_interpret_command_returns_language(monkeypatch):
    fake = FakeModel("ACTION: language LANGUAGE: zh")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    result = await service.interpret_command("switch to Chinese")

    assert result == {"action": "language", "language": "zh"}


@pytest.mark.asyncio
async def test_interpret_command_rejects_unsupported_language(monkeypatch):
    fake = FakeModel("ACTION: language LANGUAGE: fr")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    result = await service.interpret_command("switch to French")

    assert result == {"action": "unknown"}


@pytest.mark.asyncio
async def test_interpret_command_returns_open(monkeypatch):
    fake = FakeModel("ACTION: open URL: https://example.com")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    result = await service.interpret_command("open example.com")

    assert result == {"action": "open", "url": "https://example.com"}


@pytest.mark.asyncio
async def test_interpret_command_normalizes_spoken_url(monkeypatch):
    fake = FakeModel("ACTION: open URL: example dot com")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    result = await service.interpret_command("open example dot com")

    assert result == {"action": "open", "url": "https://example.com"}


@pytest.mark.asyncio
async def test_interpret_command_unknown_for_garbage_reply(monkeypatch):
    fake = FakeModel("I think the user wants something but I am not sure what.")
    monkeypatch.setattr(service.vision, "build_model", lambda: fake)

    assert await service.interpret_command("do the thing") == {"action": "unknown"}


@pytest.mark.asyncio
async def test_interpret_command_unknown_for_empty_reply(monkeypatch):
    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel(""))

    assert await service.interpret_command("blah blah") == {"action": "unknown"}


@pytest.mark.asyncio
async def test_interpret_command_keyword_fallback_describe(monkeypatch):
    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel("ACTION: unknown"))

    assert await service.interpret_command("tell me about the image") == {"action": "describe"}
    assert await service.interpret_command("describe the scene") == {"action": "describe"}
    assert await service.interpret_command("描述一下场景") == {"action": "describe"}


@pytest.mark.asyncio
async def test_interpret_command_keyword_fallback_language_toggle(monkeypatch):
    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel("ACTION: unknown"))

    assert await service.interpret_command("switch language") == {
        "action": "language",
        "language": "zh",
    }
    assert await service.interpret_command("切换语言", lang="zh") == {
        "action": "language",
        "language": "en",
    }


@pytest.mark.asyncio
async def test_interpret_command_keyword_fallback_language_explicit(monkeypatch):
    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel("ACTION: unknown"))

    assert await service.interpret_command("speak Chinese") == {
        "action": "language",
        "language": "zh",
    }
    assert await service.interpret_command("说英语") == {
        "action": "language",
        "language": "en",
    }


@pytest.mark.asyncio
async def test_interpret_command_falls_back_on_model_failure(monkeypatch):
    class FailingModel:
        async def invoke(self, messages):
            raise ConnectionError("no network")

    monkeypatch.setattr(service.vision, "build_model", lambda: FailingModel())

    assert await service.interpret_command("describe the picture") == {"action": "describe"}
    assert await service.interpret_command("blah blah") == {"action": "unknown"}


def test_keyword_command_returns_none_for_unrelated_text():
    assert service._keyword_command("hello there") is None


def test_prompts_require_the_requested_language():
    assert "Answer in English only" in service.vision.SYSTEM_PROMPT
    assert "Answer in English only" in service.vision.QUESTION_PROMPT
    assert "只用中文回答" in service.vision.SYSTEM_PROMPT_ZH
    assert "只用中文回答" in service.vision.QUESTION_PROMPT_ZH
    assert "只用中文回答" in service.vision.DIRECT_DESCRIBE_ZH


def test_keyword_command_does_not_swallow_follow_up_questions():
    assert service._keyword_command("what color is the chair") is None
    assert service._keyword_command("is the milk expired") is None
    assert service._keyword_command("how many people are there") is None


@pytest.mark.asyncio
async def test_interpret_command_question_stays_unknown_for_frontend_fallback(monkeypatch):
    monkeypatch.setattr(service.vision, "build_model", lambda: FakeModel("ACTION: unknown"))

    assert await service.interpret_command("what color is the chair") == {"action": "unknown"}
    assert await service.interpret_command("is the milk expired") == {"action": "unknown"}
