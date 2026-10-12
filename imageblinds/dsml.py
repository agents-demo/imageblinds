"""Minimal parser for DeepSeek DSML tool-call markup.

Some DeepSeek V4 models emit tool invocations as DSML text inside the message
``content`` instead of native OpenAI ``tool_calls``. openjiuwen's ReAct loop
does not parse this markup, so the invocation leaks into the agent's textual
reply. This module normalizes the full-width markup and extracts the calls so
the service layer can execute them (e.g. read the image) itself.
"""

from __future__ import annotations

import re

_FULLWIDTH = str.maketrans({"＜": "<", "＞": ">", "｜": "|"})

_INVOKE_RE = re.compile(
    r"<\|DSML\|\s+invoke\s+name=\"([^\"]+)\"[^>]*>(.*?)</\|DSML\|\s+invoke\s*>",
    re.DOTALL | re.IGNORECASE,
)
_PARAM_RE = re.compile(
    r"<\|DSML\|\s+parameter\s+name=\"([^\"]+)\"[^>]*>(.*?)</\|DSML\|\s+parameter\s*>",
    re.DOTALL | re.IGNORECASE,
)
_SELF_CLOSING_PARAM_RE = re.compile(
    r"<\|DSML\|\s+parameter\s+name=\"([^\"]+)\"([^>]*?)/>",
    re.IGNORECASE,
)
_VALUE_RE = re.compile(r"value=\"([^\"]*)\"")
_TAG_RE = re.compile(r"</?\|DSML\|[^>]*>", re.IGNORECASE)


def normalize(text: str) -> str:
    """Map full-width DSML delimiters (＜ ＞ ｜) to their ASCII forms."""
    return text.translate(_FULLWIDTH) if text else text


def parse_invokes(text: str) -> list[dict]:
    """Extract ``[{name, params}]`` tool calls from a DSML text reply."""
    calls: list[dict] = []
    for name, body in _INVOKE_RE.findall(normalize(text)):
        params: dict[str, str] = {}
        for key, value in _PARAM_RE.findall(body):
            params[key.strip()] = value.strip()
        for name, attrs in _SELF_CLOSING_PARAM_RE.findall(body):
            match = _VALUE_RE.search(attrs)
            params[name.strip()] = match.group(1) if match else ""
        calls.append({"name": name.strip(), "params": params})
    return calls


def strip_markup(text: str) -> str:
    """Remove DSML tags from a reply, leaving any plain text behind."""
    return _TAG_RE.sub("", normalize(text)).strip()
