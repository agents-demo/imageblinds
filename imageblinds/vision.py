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
    "Write two or three sentences. No JSON, no markdown, no preamble."
)

QUESTION_PROMPT = (
    "You are an image analyst. Look at the image and answer the user's "
    "question about it directly and concisely. Reply with only the answer "
    "to the question: do not re-describe the whole image and do not repeat "
    "the question. One to three sentences. No JSON, no markdown, no preamble."
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


def build_vision_agent(workspace: str | None = None) -> Any:
    """Build the multimodal vision DeepAgent (reads images via ``read_file``).

    The SysOperationRail mounts ``read_file`` and the other filesystem tools;
    without it the agent has no way to read the uploaded image (same wiring as
    taketwo's vision builder).
    """
    from openjiuwen.harness import create_deep_agent
    from openjiuwen.harness.rails import SysOperationRail

    return create_deep_agent(
        model=build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        rails=[SysOperationRail()],
        enable_task_loop=False,
        max_iterations=4,
        workspace=workspace,
        enable_read_image_multimodal=True,
    )
