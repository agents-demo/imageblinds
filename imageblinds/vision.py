"""The openjiuwen integration: build the multimodal vision DeepAgent.

The only module that imports ``openjiuwen``, mirroring taketwo's
``integrations/agents/`` layer (vision builder + model builder).
"""

from __future__ import annotations

from typing import Any

from imageblinds import fix_rwlocks as _fix_rwlocks
from imageblinds import settings

# Fix openjiuwen's lock acquire/release task mismatch before any filesystem
# operation runs; without it, every release leaks the OS lock and the next
# request hangs for the full lock timeout.
_fix_rwlocks.patch()

SYSTEM_PROMPT = (
    "You are an image analyst. Read the image with read_file and return a "
    "detailed plain-text description of what is in the image: the main "
    "object(s), their color, material, shape, parts, and surroundings. "
    "Write two or three sentences. Answer in English only. "
    "No JSON, no markdown, no preamble. "
    "Comply with ASD-STE100 Simplified Technical English: use approved words, "
    "short sentences, one idea per sentence, and active voice."
)

QUESTION_PROMPT = (
    "You are an image analyst. Look at the image and answer the user's "
    "question about it directly and concisely. Reply with only the answer "
    "to the question: do not re-describe the whole image and do not repeat "
    "the question. One to three sentences. Answer in English only. "
    "No JSON, no markdown, no preamble. "
    "Comply with ASD-STE100 Simplified Technical English: use approved words, "
    "short sentences, one idea per sentence, and active voice."
)

SYSTEM_PROMPT_ZH = (
    "你是一名图像分析员。使用 read_file 工具读取图像，并用纯文本详细描述图像内容："
    "主要物体、其颜色、材质、形状、部件以及周围环境。写两到三句话。只用中文回答。"
    "不要输出 JSON、Markdown 或任何前言。"
    "使用简短句子，每句只表达一个意思，并使用主动语态。"
)

QUESTION_PROMPT_ZH = (
    "你是一名图像分析员。查看图像并直接、简洁地回答用户关于该图像的问题。"
    "只回答问题的答案：不要重新描述整幅图像，也不要重复问题。"
    "一到三句话。只用中文回答。不要输出 JSON、Markdown 或任何前言。"
    "使用简短句子，每句只表达一个意思，并使用主动语态。"
)

DIRECT_DESCRIBE_ZH = (
    "用中文详细描述图像：主要物体、其颜色、材质、形状、部件和周围环境。"
    "两到三句话。只用中文回答。"
)

AGENT_QUERY_ZH = "读取位于 {path} 的图像并描述其中的内容。"

AGENT_QUERY_EN = "Read the image at {path} and describe what is in it."

COMMAND_PROMPT = (
    "You are the voice-command interpreter of a camera app for blind users. "
    "The user spoke a command after double-tapping the screen. Classify it and "
    "reply with exactly one line in one of these formats:\n"
    "ACTION: describe\n"
    "ACTION: language LANGUAGE: en\n"
    "ACTION: language LANGUAGE: zh\n"
    "ACTION: open URL: <url>\n"
    "ACTION: unknown\n"
    'Use "describe" when the user wants the picture analyzed or described '
    "(like pressing the shutter button). Be generous: phrasings such as "
    '"describe the scene", "tell me about the image", "what do you see", '
    '"analyze the photo" or "read the picture" all mean ACTION: describe. '
    'Use "language" with the language code the user wants; when the user only '
    'says "change language" or "switch language" without naming one, pick the '
    "other language relative to the current language stated in the message. "
    'Use "open" when the user wants to visit a website: normalize the URL - '
    'add "https://" when the scheme is missing, remove spaces, and fix speech '
    'artifacts such as "dot", "slash", "colon" and "dash". '
    'Use "unknown" for anything else, for unclear commands, and for specific '
    'questions about the picture (for example "what color is the chair" or '
    '"is the milk expired") - those are not commands and will be answered as '
    "questions about the picture. "
    "Reply with the single line only: no explanation, no markdown, no preamble."
)

_LANGS = ("en", "zh")


def is_lang(lang: str) -> bool:
    """Whether ``lang`` is a supported language code."""
    return lang in _LANGS


def system_prompt(lang: str = "en") -> str:
    """The description system prompt for the requested language."""
    return SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT


def question_prompt(lang: str = "en") -> str:
    """The follow-up-question system prompt for the requested language."""
    return QUESTION_PROMPT_ZH if lang == "zh" else QUESTION_PROMPT


def agent_query(path: str, lang: str = "en") -> str:
    """The agent instruction that asks it to read and describe an image."""
    template = AGENT_QUERY_ZH if lang == "zh" else AGENT_QUERY_EN
    return template.format(path=path)


def direct_describe_text(lang: str = "en") -> str:
    """The user text attached to the image in the direct multimodal call."""
    if lang == "zh":
        return DIRECT_DESCRIBE_ZH
    return (
        "Describe the image in detail: the main object(s), "
        "their color, material, shape, parts, and surroundings. "
        "Two or three sentences. Answer in English only."
    )


def build_model() -> Any:
    """Construct an openjiuwen ``Model`` for the configured provider/endpoint."""
    from openjiuwen.core.foundation.llm import (
        Model,
        ModelClientConfig,
        ModelRequestConfig,
    )

    client = ModelClientConfig(
        client_provider=settings.model_provider(),
        api_key=settings.api_key(),
        api_base=settings.api_base(),
        timeout=int(settings.llm_timeout()),
        verify_ssl=settings.verify_ssl(),
    )
    request = ModelRequestConfig(
        model=settings.vision_model_name(),
        temperature=settings.vision_temperature(),
        top_p=0.9,
    )
    return Model(model_client_config=client, model_config=request)


def build_vision_agent(workspace: str | None = None, lang: str = "en") -> Any:
    """Build the multimodal vision DeepAgent (reads images via ``read_file``).

    The SysOperationRail mounts ``read_file`` and the other filesystem tools;
    without it the agent has no way to read the uploaded image (same wiring as
    taketwo's vision builder).
    """
    from openjiuwen.harness import create_deep_agent
    from openjiuwen.harness.rails import SysOperationRail

    return create_deep_agent(
        model=build_model(),
        system_prompt=system_prompt(lang),
        tools=[],
        rails=[SysOperationRail()],
        enable_task_loop=False,
        max_iterations=4,
        workspace=workspace,
        enable_read_image_multimodal=True,
    )
