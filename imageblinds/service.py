"""Run the vision agent on an uploaded image and extract its textual answer.

Copies taketwo's agent-reply contract: run the built agent, then best-effort
extract the text from whatever the runner returned. When the agent reply is an
unexecuted DSML tool call (some DeepSeek V4 models emit tool calls as markup in
``content`` instead of native ``tool_calls``), the file read is executed here
and the image is sent to the model directly as a multimodal message.
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import re
import urllib.parse
from pathlib import Path
from typing import Any

from imageblinds import dsml, settings, vision

RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"
WORKSPACE_DIR = RUNTIME_DIR / "workspace"
UPLOAD_DIR = WORKSPACE_DIR / "uploads"


def ensure_workspace() -> Path:
    """Create and return the runtime workspace (images live here for ``read_file``)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_DIR


def _build_agent(lang: str = "en") -> Any:
    """Build a fresh vision agent for one request.

    The openjiuwen filesystem service (SQLite + rwlocks) is tied to the
    agent's session lifecycle. Reusing a single agent across requests reopens
    a closed database and stale locks ("Cannot operate on a closed database",
    "Cannot release a lock ... that is not held by this task"), so a new
    agent is built per analysis.
    """
    return vision.build_vision_agent(str(ensure_workspace()), lang=lang)


async def run_agent(agent: Any, query: str) -> Any:
    """Run the agent on the global Runner (starts it if needed)."""
    from openjiuwen.core.runner import Runner

    try:
        await Runner.start()
    except Exception:
        pass
    return await Runner.run_agent(agent, {"query": query})


def reply_text(result: Any) -> str:
    """Best-effort text extraction from whatever the backend runner returned."""
    if result is None:
        return ""
    if isinstance(result, dict):
        for key in ("output", "content", "answer", "result"):
            value = result.get(key)
            if isinstance(value, str):
                return value
        return ""
    return getattr(result, "content", None) or str(result)


def _data_url(image_path: str) -> str | None:
    """Base64 ``data:`` URL for an image file, or ``None`` when not readable."""
    path = Path(image_path)
    if not path.is_file():
        return None
    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    if not mime.startswith("image/"):
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


async def _ask_model_directly(image_path: str, lang: str = "en") -> str:
    """Send the image bytes straight to the model as a multimodal message."""
    data_url = _data_url(image_path)
    if data_url is None:
        return ""
    model = vision.build_model()
    reply = await model.invoke(
        [
            {"role": "system", "content": vision.system_prompt(lang)},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": vision.direct_describe_text(lang),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
    )
    content = getattr(reply, "content", None)
    return content.strip() if isinstance(content, str) else ""


async def answer_question(image_path: str | Path, question: str, lang: str = "en") -> str:
    """Answer a follow-up question about ``image_path`` with the vision model.

    The image is sent to the model directly as a multimodal message together
    with the user's question. Raises on timeout so the server can surface a
    proper error.
    """
    data_url = _data_url(str(image_path))
    if data_url is None:
        raise ValueError("The image is not readable.")
    model = vision.build_model()
    reply = await asyncio.wait_for(
        model.invoke(
            [
                {"role": "system", "content": vision.question_prompt(lang)},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ]
        ),
        timeout=float(settings.llm_timeout()),
    )
    content = getattr(reply, "content", None)
    return content.strip() if isinstance(content, str) else ""


_COMMAND_ACTION_RE = re.compile(r"ACTION:\s*([a-zA-Z]+)")
_COMMAND_LANGUAGE_RE = re.compile(r"LANGUAGE:\s*([a-zA-Z-]+)")
_COMMAND_URL_RE = re.compile(r"URL:\s*([^\n]+)")

_SPEECH_ARTIFACTS = (
    (re.compile(r"(?<![a-zA-Z])dot(?![a-zA-Z])"), "."),
    (re.compile(r"(?<![a-zA-Z])slash(?![a-zA-Z])"), "/"),
    (re.compile(r"(?<![a-zA-Z])colon(?![a-zA-Z])"), ":"),
    (re.compile(r"(?<![a-zA-Z])dash(?![a-zA-Z])"), "-"),
    (re.compile(r"(?<![a-zA-Z])at(?![a-zA-Z])"), "@"),
    (re.compile(r"(?<![a-zA-Z])plus(?![a-zA-Z])"), "+"),
)


def _normalize_url(raw: str) -> str | None:
    """Clean a spoken URL: fix speech artifacts, add https:// when missing."""
    url = raw.strip()
    for pattern, replacement in _SPEECH_ARTIFACTS:
        url = pattern.sub(replacement, url)
    url = re.sub(r"\s+", "", url).strip(".,;:()[]{}'\"")
    if not url:
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        if not url.lower().startswith(("http://", "https://")):
            return None
    else:
        if ":" in url:
            return None
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return url


def _parse_command(text: str) -> dict[str, Any]:
    """Parse the model's fixed-format command reply into an action dict."""
    action_match = _COMMAND_ACTION_RE.search(text)
    if not action_match:
        return {"action": "unknown"}
    action = action_match.group(1).lower()
    if action == "describe":
        return {"action": "describe"}
    if action == "language":
        language_match = _COMMAND_LANGUAGE_RE.search(text)
        target = language_match.group(1).lower() if language_match else ""
        if not vision.is_lang(target):
            return {"action": "unknown"}
        return {"action": "language", "language": target}
    if action == "open":
        url_match = _COMMAND_URL_RE.search(text)
        url = _normalize_url(url_match.group(1)) if url_match else None
        if not url:
            return {"action": "unknown"}
        return {"action": "open", "url": url}
    return {"action": "unknown"}


_LANGUAGE_KEYWORD_RE = re.compile(
    r"language|english|chinese|中文|英文|英语|语言|切换", re.IGNORECASE
)
_DESCRIBE_KEYWORD_RE = re.compile(
    r"describe|analy[sz]e|read|snap|capture|picture|photo|image|scene"
    r"|描述|图片|照片|图像|场景|看看|读|介绍|识别",
    re.IGNORECASE,
)
_ZH_LANGUAGE_RE = re.compile(r"中文|chinese", re.IGNORECASE)
_EN_LANGUAGE_RE = re.compile(r"english|英文|英语", re.IGNORECASE)


def _keyword_command(command: str, lang: str = "en") -> dict[str, Any] | None:
    """Forgiving keyword fallback for natural phrasings the model missed."""
    if _LANGUAGE_KEYWORD_RE.search(command):
        if _ZH_LANGUAGE_RE.search(command):
            return {"action": "language", "language": "zh"}
        if _EN_LANGUAGE_RE.search(command):
            return {"action": "language", "language": "en"}
        return {"action": "language", "language": "zh" if lang == "en" else "en"}
    if _DESCRIBE_KEYWORD_RE.search(command):
        return {"action": "describe"}
    return None


async def interpret_command(command: str, lang: str = "en") -> dict[str, Any]:
    """Classify a spoken voice command into an action dict (text-only call).

    Returns one of ``{"action": "describe"}``,
    ``{"action": "language", "language": "en"|"zh"}``,
    ``{"action": "open", "url": ...}`` or ``{"action": "unknown"}``. When the
    model fails or cannot classify the command, a forgiving keyword fallback
    covers common phrasings ("describe the scene", "tell me about the image",
    "switch language"), so natural speech keeps working.
    """
    model = vision.build_model()
    try:
        reply = await asyncio.wait_for(
            model.invoke(
                [
                    {"role": "system", "content": vision.COMMAND_PROMPT},
                    {
                        "role": "user",
                        "content": f"Current app language: {lang}\nSpoken command: {command}",
                    },
                ]
            ),
            timeout=float(settings.llm_timeout()),
        )
    except Exception:  # noqa: BLE001 - the keyword fallback takes over
        reply = None
    content = getattr(reply, "content", None) if reply is not None else None
    text = content.strip() if isinstance(content, str) else ""
    result = _parse_command(text)
    if result["action"] != "unknown":
        return result
    return _keyword_command(command, lang) or result


def _dsml_target(text: str) -> str | None:
    """The first existing image path named in an unexecuted DSML tool call."""
    for call in dsml.parse_invokes(text):
        file_path = call["params"].get("file_path")
        if file_path and Path(file_path).is_file():
            return file_path
    return None


_UNABLE_TO_READ_RE = re.compile(
    r"can'?t read|cannot read|unable to read|unable to describe"
    r"|no (?:actual )?visual data|not available|don'?t have access|no access"
    r"|without completion|read_file.{0,60}fail|infrastructure errors"
    r"|无法读取|无法描述|无法查看|读取失败|描述失败|没有访问权限|无法访问"
    r"|看不到图像|图片.{0,20}失败",
    re.IGNORECASE,
)

AGENT_TIMEOUT_SECONDS = 120.0


def _looks_like_read_failure(text: str) -> bool:
    return _UNABLE_TO_READ_RE.search(text) is not None


async def describe_image(image_path: str | Path, lang: str = "en") -> str:
    """Ask the vision agent what is in ``image_path`` and return its answer.

    If the agent run times out, errors, or replies with an unexecuted tool
    call / read-failure message, the image is sent to the model directly as a
    multimodal message.
    """
    path = str(image_path)
    agent = _build_agent(lang=lang)
    query = vision.agent_query(path, lang)
    try:
        result = await asyncio.wait_for(run_agent(agent, query), timeout=AGENT_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - the direct path is the fallback
        result = None
    text = reply_text(result).strip()
    run_failed = result is None

    target = _dsml_target(text)
    if run_failed or target is not None or _looks_like_read_failure(text):
        try:
            direct = await _ask_model_directly(target or path, lang=lang)
        except Exception:  # noqa: BLE001 - the agent path already failed to read
            direct = ""
        if direct:
            return direct

    cleaned = dsml.strip_markup(text)
    return cleaned or text
