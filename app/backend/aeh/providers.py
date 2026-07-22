"""Pluggable model-provider seam.

The agentic workflow here is deterministic by design (offline demo), but a Forward-Deployed
Engineer at a Google Cloud / Gemini partner ships against a *real* model backend. This module
is that seam: the orchestrator holds a Provider, and the provider is swappable.

- MockDeterministicProvider (default): the offline, byte-reproducible stand-in used
  throughout this demo. No network, no keys.
- GeminiVertexProvider: a thin adapter that maps a step to the REAL Vertex AI
  ``generateContent`` request/response contract (model ``gemini-2.5-pro``). ``build_request``
  is a PURE function you can unit-test with no network; ``generate`` deliberately RAISES
  offline — it is a wiring demonstration, not a live call, so the demo stays deterministic
  and key-free. Set ``AEH_PROVIDER=gemini`` (+ GOOGLE_CLOUD_PROJECT) to surface the request shape.
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable


class ProviderNotConfigured(RuntimeError):
    """Raised when a real provider is selected but cannot run offline (by design)."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def generate(self, system: str, prompt: str) -> str: ...

    def describe(self) -> dict: ...


class MockDeterministicProvider:
    """Offline, deterministic stand-in — same (system, prompt) -> same text, always."""

    name = "mock:deterministic-v1"

    def generate(self, system: str, prompt: str) -> str:
        h = hashlib.sha256((system + "\x00" + prompt).encode("utf-8")).hexdigest()[:12]
        return f"[mock-deterministic:{h}] " + prompt.strip()[:120]

    def describe(self) -> dict:
        return {
            "name": self.name,
            "backend": "offline-mock",
            "live": False,
            "note": "Deterministic offline stand-in; no network, no API keys.",
        }


class GeminiVertexProvider:
    """Adapter for Google Vertex AI Gemini ``generateContent`` — offline wiring demo."""

    name = "vertex:gemini-2.5-pro"

    def __init__(
        self, project: str | None = None, location: str = "us-central1", model: str = "gemini-2.5-pro"
    ) -> None:
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.model = model

    def endpoint(self) -> str:
        proj = self.project or "PROJECT_ID"
        return (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/{proj}/"
            f"locations/{self.location}/publishers/google/models/{self.model}:generateContent"
        )

    def build_request(self, system: str, prompt: str) -> dict:
        """PURE: build the exact Vertex generateContent request body. No network, no keys."""
        return {
            "systemInstruction": {"role": "system", "parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 1024,
                "responseMimeType": "text/plain",
            },
        }

    def generate(self, system: str, prompt: str) -> str:
        # Offline by design: prove the wiring (build_request/endpoint) without ever calling
        # out. A live deployment would POST build_request() to endpoint() with a bearer token;
        # here we refuse rather than fabricate a response.
        raise ProviderNotConfigured(
            "GeminiVertexProvider runs offline in this demo: build_request()/endpoint() show the real "
            "Vertex contract, but no network call is made. Wire an authenticated client to go live."
        )

    def describe(self) -> dict:
        return {
            "name": self.name,
            "backend": "google-vertex-ai",
            "model": self.model,
            "location": self.location,
            "live": False,
            "endpoint": self.endpoint(),
            "note": "Vertex/Gemini adapter present; offline by default (no keys, no network).",
        }


def select_provider(env: dict | None = None) -> Provider:
    """Pick a provider from AEH_PROVIDER (default 'mock'). 'gemini'/'vertex' -> Gemini adapter."""
    env = env if env is not None else os.environ
    choice = (env.get("AEH_PROVIDER") or "mock").strip().lower()
    if choice in ("gemini", "vertex", "vertex-gemini"):
        return GeminiVertexProvider()
    return MockDeterministicProvider()
