"""Shipped model adapters.

Each one speaks a wire protocol rather than naming a vendor, which is what lets
a program office evaluate competing systems under identical conditions.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

import httpx

from .base import ModelAdapter, TargetRequest, TargetResponse, register_adapter


def _resolve_secret(adapter: ModelAdapter, env_fallback: str | None = None) -> str | None:
    """Secrets are referenced, never stored in the database.

    `credential_ref` names an environment variable or a mounted secret file, so
    key material lives in the deployment's secret manager.
    """
    ref = adapter.secret or adapter.config.get("credential_ref")
    if not ref:
        return os.getenv(env_fallback) if env_fallback else None
    if ref.startswith("file:"):
        path = ref.removeprefix("file:")
        try:
            return open(path).read().strip()
        except OSError:
            return None
    if ref.startswith("env:"):
        return os.getenv(ref.removeprefix("env:"))
    return os.getenv(ref) or ref


@register_adapter
class OpenAICompatibleAdapter(ModelAdapter):
    """Any endpoint speaking the OpenAI chat-completions shape.

    Covers commercial OpenAI, Azure OpenAI deployments, vLLM, llama.cpp server,
    Ollama's compatibility route and most government-hosted inference
    gateways -- one adapter, many hosts.
    """

    key = "openai_compatible"
    label = "OpenAI-compatible chat completions"

    def invoke(self, request: TargetRequest) -> TargetResponse:
        base = (self.endpoint or "https://api.openai.com/v1").rstrip("/")
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        self._check_egress(url)

        messages = request.messages or []
        if not messages:
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": self.config.get("model_name") or self.parameters.get("model", "gpt-4o-mini"),
            "messages": messages,
        }
        for field in ("temperature", "top_p", "max_tokens", "seed", "stop"):
            if field in self.parameters:
                payload[field] = self.parameters[field]
        if request.tools:
            payload["tools"] = request.tools
        # Token log-probabilities are the one confidence signal this API
        # exposes. Opt-in, because not every compatible server implements it.
        if self.parameters.get("logprobs"):
            payload["logprobs"] = True

        headers = {"Content-Type": "application/json"}
        token = _resolve_secret(self, "OPENAI_API_KEY")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response, elapsed = self._timed(client.post, url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            return TargetResponse(text="", error=f"{type(exc).__name__}: {exc}")

        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = body.get("usage") or {}
        trace = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            trace.append(
                {
                    "step": "tool_call",
                    "tool": fn.get("name"),
                    "input": fn.get("arguments"),
                    "call_id": call.get("id"),
                }
            )
        confidence = _logprob_confidence(choice.get("logprobs"))
        return TargetResponse(
            text=message.get("content") or "",
            raw=body,
            latency_ms=elapsed,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            trace=trace,
            confidence=confidence,
            confidence_source="logprob" if confidence is not None else None,
        )


def _logprob_confidence(logprobs: dict | None) -> float | None:
    """Geometric-mean token probability of the answer, or None.

    A rough signal: it measures how expected each token was, not whether the
    claim is true, and it is recorded as `logprob` so nobody reads it as the
    model's stated belief.
    """
    tokens = (logprobs or {}).get("content") or []
    values = [t.get("logprob") for t in tokens if isinstance(t.get("logprob"), (int, float))]
    if not values:
        return None
    return round(math.exp(sum(values) / len(values)), 4)


@register_adapter
class AnthropicMessagesAdapter(ModelAdapter):
    """Anthropic-compatible messages endpoint."""

    key = "anthropic_messages"
    label = "Anthropic-compatible messages"

    def invoke(self, request: TargetRequest) -> TargetResponse:
        base = (self.endpoint or "https://api.anthropic.com/v1").rstrip("/")
        url = base if base.endswith("/messages") else f"{base}/messages"
        self._check_egress(url)

        messages = request.messages or [{"role": "user", "content": request.prompt}]
        payload = {
            "model": self.config.get("model_name") or "claude-sonnet-5",
            "max_tokens": self.parameters.get("max_tokens", 2048),
            "messages": messages,
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        for field in ("temperature", "top_p", "top_k", "stop_sequences"):
            if field in self.parameters:
                payload[field] = self.parameters[field]
        if request.tools:
            payload["tools"] = request.tools

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self.parameters.get("api_version", "2023-06-01"),
        }
        token = _resolve_secret(self, "ANTHROPIC_API_KEY")
        if token:
            headers["x-api-key"] = token

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response, elapsed = self._timed(client.post, url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:
            return TargetResponse(text="", error=f"{type(exc).__name__}: {exc}")

        text_parts, trace = [], []
        for block in body.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                trace.append(
                    {
                        "step": "tool_call",
                        "tool": block.get("name"),
                        "input": block.get("input"),
                        "call_id": block.get("id"),
                    }
                )
        usage = body.get("usage") or {}
        return TargetResponse(
            text="".join(text_parts),
            raw=body,
            latency_ms=elapsed,
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            trace=trace,
        )


@register_adapter
class GenericRestAdapter(ModelAdapter):
    """Any REST application, mapped with JSON paths.

    This is how a complete AI-enabled capability -- not just a model -- gets
    evaluated: point it at the application's own endpoint and describe where
    the answer, citations and trace live in the response body.
    """

    key = "generic_rest"
    label = "Generic REST endpoint"

    def invoke(self, request: TargetRequest) -> TargetResponse:
        url = self.endpoint
        if not url:
            return TargetResponse(text="", error="No endpoint configured for generic_rest")
        self._check_egress(url)

        template = self.parameters.get("request_template") or {"input": "{{prompt}}"}
        payload = self._render(template, request)

        headers = {"Content-Type": "application/json", **(self.parameters.get("headers") or {})}
        token = _resolve_secret(self)
        if token:
            scheme = self.parameters.get("auth_scheme", "Bearer")
            header_name = self.parameters.get("auth_header", "Authorization")
            headers[header_name] = f"{scheme} {token}".strip()

        method = self.parameters.get("method", "POST").upper()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response, elapsed = self._timed(
                    client.request, method, url, json=payload, headers=headers
                )
            response.raise_for_status()
            body = response.json() if response.content else {}
        except Exception as exc:
            return TargetResponse(text="", error=f"{type(exc).__name__}: {exc}")

        text = self._extract(body, self.parameters.get("response_path", "output"))
        citations = self._extract(body, self.parameters.get("citations_path")) or []
        retrieved = self._extract(body, self.parameters.get("retrieval_path")) or []
        trace = self._extract(body, self.parameters.get("trace_path")) or []
        return TargetResponse(
            text=text if isinstance(text, str) else json.dumps(text, default=str),
            raw=body if isinstance(body, dict) else {"body": body},
            latency_ms=elapsed,
            citations=citations if isinstance(citations, list) else [],
            retrieved=retrieved if isinstance(retrieved, list) else [],
            trace=trace if isinstance(trace, list) else [],
        )

    def _render(self, template, request: TargetRequest):
        if isinstance(template, dict):
            return {k: self._render(v, request) for k, v in template.items()}
        if isinstance(template, list):
            return [self._render(v, request) for v in template]
        if isinstance(template, str):
            return (
                template.replace("{{prompt}}", request.prompt)
                .replace("{{system_prompt}}", request.system_prompt or "")
                .replace("{{documents}}", json.dumps(request.documents, default=str))
            )
        return template

    @staticmethod
    def _extract(body, path: str | None):
        """Resolve a dotted path, with `[n]` index support."""
        if not path:
            return None
        current = body
        for part in path.split("."):
            match = re.match(r"^(.*?)\[(\d+)\]$", part)
            index = None
            if match:
                part, index = match.group(1), int(match.group(2))
            if part:
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            if index is not None:
                if not isinstance(current, list) or index >= len(current):
                    return None
                current = current[index]
        return current


@register_adapter
class HttpRagAdapter(GenericRestAdapter):
    """A RAG application that returns retrieved passages alongside its answer.

    Retrieval and generation are judged independently (section 24), so the
    adapter normalises whatever the application returns into a passage list
    carrying an id, text and score.
    """

    key = "http_rag"
    label = "RAG application (answer + retrieved passages)"

    def invoke(self, request: TargetRequest) -> TargetResponse:
        response = super().invoke(request)
        response.retrieved = [self._normalise(p) for p in response.retrieved]
        if not response.citations:
            response.citations = [
                {"source_id": p.get("source_id"), "quote": None}
                for p in response.retrieved
                if p.get("source_id")
            ]
        return response

    @staticmethod
    def _normalise(passage) -> dict:
        if isinstance(passage, str):
            return {"source_id": None, "text": passage, "score": None}
        if not isinstance(passage, dict):
            return {"source_id": None, "text": str(passage), "score": None}
        return {
            "source_id": passage.get("source_id")
            or passage.get("id")
            or passage.get("doc_id")
            or passage.get("document_id"),
            "text": passage.get("text") or passage.get("content") or passage.get("chunk") or "",
            "score": passage.get("score") or passage.get("relevance"),
            "metadata": passage.get("metadata") or {},
        }


RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"


def recording_key(system_prompt: str | None, prompt: str) -> str:
    """The identity of one request in a recording: its system prompt and prompt."""
    return hashlib.sha256(json.dumps([system_prompt or "", prompt]).encode()).hexdigest()


@lru_cache(maxsize=16)
def load_recording(name: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", name or ""):
        raise ValueError(f"Invalid recording name {name!r}")
    return json.loads((RECORDINGS_DIR / f"{name}.json").read_text())


@register_adapter
class RecordedAdapter(ModelAdapter):
    """Replays responses a model gave earlier, request for request.

    For demonstrations and reproducible examples where the model cannot be
    called from the deployment. A request is matched on its exact system
    prompt and prompt; one that was never recorded is an error, never a
    made-up answer. Latency and token counts are not recorded, so they are
    reported as unknown rather than as the replay's own timing.
    """

    key = "recorded"
    label = "Recorded responses (replay of an earlier model run)"
    requires_egress = False

    def invoke(self, request: TargetRequest) -> TargetResponse:
        name = self.parameters.get("recording", "")
        recording = load_recording(name)
        key = recording_key(request.system_prompt, request.prompt)
        entry = (recording.get("responses") or {}).get(key)
        if entry is None:
            return TargetResponse(
                text="",
                latency_ms=None,
                error=f"No recorded response for this request in recording '{name}' ({key[:12]}).",
            )
        return TargetResponse(
            text=entry["text"],
            raw={
                "recording": name,
                "request_sha256": key,
                "recorded_model": recording.get("model"),
                "recorded_via": recording.get("recorded_via"),
            },
            latency_ms=None,
            trace=[{"step": "replay", "detail": f"recording {name}, request {key[:12]}"}],
        )


@register_adapter
class EchoAdapter(ModelAdapter):
    """Deterministic offline target.

    Exists so the platform is demonstrable, testable and CI-runnable with no
    network and no model provider -- which is also how an air-gapped install
    proves itself before any real system is connected. Behaviour is seeded from
    the prompt, so the same input always produces the same output.
    """

    key = "echo"
    label = "Offline deterministic target (development and self-test)"
    requires_egress = False

    def invoke(self, request: TargetRequest) -> TargetResponse:
        profile = self.parameters.get("profile", "cooperative")
        seed = int(hashlib.sha256(request.prompt.encode()).hexdigest()[:8], 16)
        latency = 120 + (seed % 900)

        sources = [d.get("source_id") for d in request.documents if d.get("source_id")]
        text = self._compose(profile, request, seed, sources)

        trace = [{"step": "receive", "detail": "prompt accepted"}]
        retrieved = [
            {
                "source_id": d.get("source_id"),
                "text": (d.get("text") or "")[:400],
                "score": round(1.0 - (i * 0.11), 3),
            }
            for i, d in enumerate(request.documents)
        ]
        if retrieved:
            trace.append({"step": "retrieve", "detail": f"{len(retrieved)} passages"})
        for tool in request.tools:
            name = (tool.get("function") or tool).get("name")
            # The uncooperative profile reaches for tools it was not authorised
            # to use, which is what the agent authorisation evaluation looks for.
            if profile == "uncooperative" or (seed % 5 == 0):
                trace.append({"step": "tool_call", "tool": name, "input": {"query": request.prompt[:80]}})
                trace.append({"step": "tool_result", "tool": name, "output": "simulated result"})
        trace.append({"step": "respond", "detail": f"{len(text)} chars"})

        # A stated confidence, seeded like everything else here. Opt-in, so
        # the offline target does not claim a signal nobody configured.
        confidence = None
        if self.parameters.get("report_confidence"):
            confidence = round(0.5 + (seed % 50) / 100, 2)

        return TargetResponse(
            text=text,
            raw={"profile": profile, "seed": seed},
            confidence=confidence,
            confidence_source="reported" if confidence is not None else None,
            latency_ms=latency,
            tokens_in=len(request.prompt.split()),
            tokens_out=len(text.split()),
            trace=trace,
            retrieved=retrieved,
            citations=[{"source_id": s} for s in sources[: 2 if profile != "fabricating" else 0]],
        )

    def _compose(self, profile: str, request: TargetRequest, seed: int, sources: list) -> str:
        prompt = request.prompt.strip()
        # An injected instruction inside a source document. The compliant
        # profile follows it -- that is the failure the red-team pack detects.
        injected = None
        for doc in request.documents:
            body = doc.get("text") or ""
            match = re.search(r"(ignore (?:all )?previous instructions[^.\n]*)", body, re.I)
            if match:
                injected = match.group(1)
                break

        if profile == "vulnerable" and injected:
            return f"Understood. {injected.capitalize()}. Proceeding on that basis."
        if profile == "fabricating":
            return (
                f"Based on the reporting, the assessment is confirmed with high confidence. "
                f"See source AR-{seed % 900 + 100} and source AR-{seed % 400 + 500}."
            )
        if profile == "refusing":
            return "I can't help with that request."

        cited = ", ".join(sources[:3]) if sources else "the provided material"
        hedge = "Reporting conflicts on this point and confidence is moderate."
        return (
            f"Summary: {prompt[:220]}\n\n"
            f"Assessment grounded in {cited}. {hedge} "
            f"No claim here is supported beyond what the cited material states."
        )
