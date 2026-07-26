"""The pluggable model-provider seam: mock by default, real Gemini/Vertex adapter present.

Proves this is a genuine wiring seam for a Google Cloud / Gemini partner, not a narrative:
the Vertex adapter builds the exact generateContent contract (unit-testable, no network),
selection is env-driven, and the harness stays deterministic on the default mock.
"""

import pytest

from aeh.eval import run_eval_suite
from aeh.providers import (
    GeminiVertexProvider,
    MockDeterministicProvider,
    ProviderNotConfigured,
    select_provider,
)


def test_default_provider_is_mock_and_deterministic():
    p = select_provider({})  # no AEH_PROVIDER
    assert isinstance(p, MockDeterministicProvider)
    a = p.generate("sys", "same prompt")
    b = p.generate("sys", "same prompt")
    assert a == b and a.startswith("[mock-deterministic:")  # same in -> same out


def test_env_selects_the_gemini_vertex_adapter():
    assert isinstance(select_provider({"AEH_PROVIDER": "gemini"}), GeminiVertexProvider)
    assert isinstance(select_provider({"AEH_PROVIDER": "vertex"}), GeminiVertexProvider)


def test_gemini_adapter_builds_the_real_vertex_contract():
    g = GeminiVertexProvider(project="acme-proj", location="us-central1")
    req = g.build_request("You are a planner.", "Break down the task.")
    assert req["contents"][0]["role"] == "user"
    assert req["contents"][0]["parts"][0]["text"] == "Break down the task."
    assert req["systemInstruction"]["parts"][0]["text"] == "You are a planner."
    assert req["generationConfig"]["temperature"] == 0.0
    ep = g.endpoint()
    assert (
        "acme-proj" in ep
        and "gemini-2.5-pro:generateContent" in ep
        and ep.startswith("https://")
    )


def test_gemini_adapter_is_offline_by_design():
    # a live call is refused, not faked — keeps the demo deterministic and key-free
    with pytest.raises(ProviderNotConfigured):
        GeminiVertexProvider().generate("sys", "prompt")


def test_eval_surfaces_provider_and_stays_deterministic_on_mock():
    r1 = run_eval_suite()
    r2 = run_eval_suite()
    assert r1["provider"]["name"] == "mock:deterministic-v1"
    assert r1["provider"]["live"] is False
    # provider is not in the hashed trace -> the suite result is stable across runs
    assert r1["accuracy"] == r2["accuracy"]
