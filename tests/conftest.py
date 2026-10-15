"""Shared fixtures: a stub vision agent and workspace isolation."""

from __future__ import annotations

from typing import Any

import pytest

from imageblinds import service


class StubAgent:
    """Stands in for the openjiuwen DeepAgent in offline tests."""

    def __init__(self) -> None:
        self.last_query: str | None = None


@pytest.fixture
def stub_agent() -> StubAgent:
    return StubAgent()


@pytest.fixture
def stub_pipeline(monkeypatch, stub_agent):
    """Route the agent build + run through stubs; record the query used."""

    async def fake_run_agent(agent: Any, query: str) -> Any:
        agent.last_query = query
        return {"output": "This image shows a chair."}

    monkeypatch.setattr(service, "_build_agent", lambda lang="en": stub_agent)
    monkeypatch.setattr(service, "run_agent", fake_run_agent)
    return stub_agent
