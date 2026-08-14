"""One OpenAI-compatible client for the whole AI stack, configured from the
admin settings row. Everything above this module must tolerate AIDisabled."""

import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import crypto, local_embedding
from app.auth.service import get_default_tenant
from app.models import AISettings

logger = logging.getLogger("roundtable.ai")


class AIDisabled(Exception):
    pass


class AIError(Exception):
    pass


async def get_ai_settings(db: AsyncSession) -> AISettings:
    row = (await db.execute(select(AISettings))).scalars().first()
    if row is None:
        tenant = await get_default_tenant(db)
        row = AISettings(tenant_id=tenant.id, enabled=False)
        db.add(row)
        await db.flush()
    # A key written before the encryption salt was renamed still opens, but
    # under the old salt. Rewrite it here rather than leaving every read to
    # fall through the legacy path forever, and so that an operator never has
    # to know this happened.
    if row.api_key_enc and crypto.needs_reseal(row.api_key_enc):
        resealed = crypto.reseal(row.api_key_enc)
        if resealed:
            row.api_key_enc = resealed
            await db.flush()
            logger.info("re-encrypted the stored AI key under the current salt")
    return row


async def require_ai(db: AsyncSession) -> AISettings:
    settings = await get_ai_settings(db)
    if not settings.enabled:
        raise AIDisabled("AI features are turned off in admin settings")
    return settings


class AIKeyUnreadable(AIError):
    """A key is stored but this instance cannot decrypt it."""


def _headers(settings: AISettings) -> dict[str, str]:
    """Authorization for the configured endpoint.

    A stored key that will not decrypt is its own failure and says so. The
    old behaviour sent a placeholder instead, the provider answered 401, and
    the person saw "chat endpoint returned 401" with no hint that the cause
    was on this side. The key is sealed with a value derived from
    RT_SECRET_KEY, so it stops being readable if that changes or if an
    ai_settings row is copied between instances.

    No key at all is not an error: a local LM Studio or Ollama takes any
    bearer token, which is why the placeholder exists.
    """
    if not settings.api_key_enc:
        return {"Authorization": "Bearer roundtable"}
    key = crypto.decrypt(settings.api_key_enc)
    if key is None:
        raise AIKeyUnreadable(
            "the stored AI key cannot be decrypted on this instance, most likely "
            "because RT_SECRET_KEY changed or the settings came from elsewhere. "
            "Enter the key again under Admin, AI settings."
        )
    return {"Authorization": f"Bearer {key}"}


async def embed_texts(db: AsyncSession, texts: list[str]) -> list[list[float]]:
    """Vectors for the recommendation engine.

    Uses the configured embedding endpoint when there is one, and the local
    encoder otherwise, so recommendations never depend on an external
    service being reachable."""
    settings = await require_ai(db)
    if local_embedding.is_local(settings.embed_model) or not settings.base_url:
        return local_embedding.encode_many(texts)

    url = f"{settings.base_url.rstrip('/')}/embeddings"
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                json={"model": settings.embed_model, "input": texts},
                headers=_headers(settings),
            )
    except httpx.HTTPError as exc:
        logger.warning("embeddings endpoint unreachable (%s), using the local encoder", exc)
        return local_embedding.encode_many(texts)
    if resp.status_code != 200:
        # A missing or unsupported embeddings endpoint must not take the
        # whole engine down: fall back to the local encoder.
        logger.warning("embeddings endpoint returned %s, using the local encoder", resp.status_code)
        return local_embedding.encode_many(texts)
    data = resp.json()
    logger.info("embedded %d texts in %.1fs", len(texts), time.monotonic() - started)
    ordered = sorted(data["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in ordered]


async def chat_json(
    db: AsyncSession, system: str, user: str, max_tokens: int = 800
) -> dict[str, Any]:
    """One-shot chat completion that must return a JSON object."""
    settings = await require_ai(db)
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    started = time.monotonic()
    body = {
        "model": settings.chat_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        **_provider_extras(settings),
    }
    # Same retry as chat_text, and for the same reason: a free router lands
    # on a different model each call, and some of them answer with content
    # set to null. _text_from handles that rather than letting .strip()
    # raise an AttributeError that surfaces as an unexplained 502.
    last: Exception | None = None
    content = ""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=_headers(settings))
            if resp.status_code != 200:
                raise AIError(f"chat endpoint returned {resp.status_code}")
            content = _text_from(resp.json())
            break
        except AIKeyUnreadable:
            raise
        except (AIError, httpx.HTTPError) as exc:
            last = exc
            logger.info("chat_json attempt %s failed: %s", attempt + 1, exc)
    else:
        raise AIError(str(last) if last else "the model did not answer")

    logger.info("chat call took %.1fs", time.monotonic() - started)
    parsed = _parse_json_reply(content)
    if parsed is None:
        raise AIError("model did not return valid JSON")
    return parsed


def _parse_json_reply(content: str) -> dict[str, Any] | None:
    """Get an object out of a reply, however the model chose to wrap it.

    response_format is a request, not a guarantee. A router like
    openrouter/free sends each call to whichever free model is up, and
    plenty of them ignore it and answer with prose, or with the JSON
    introduced by a sentence, or fenced. Failing the whole feature because
    a model was chatty is the wrong trade when the object is right there."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        loaded = json.loads(cleaned)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        pass

    # Prose around the object: start at the first brace and try again.
    start = cleaned.find("{")
    if start > 0:
        cleaned = cleaned[start:]
        try:
            loaded = json.loads(cleaned)
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            pass
    if not cleaned.startswith("{"):
        return None

    salvaged = _salvage_json(cleaned)
    if salvaged is not None:
        logger.info("recovered a partial JSON reply")
    return salvaged


def _provider_extras(settings: Any) -> dict[str, Any]:
    """Per provider request options.

    OpenRouter routes a request to whichever model is up, and the free pool
    is full of reasoning models. Those emit their chain of thought into
    `content`, burn the whole token budget on it, and finish with
    `length` before writing a single character of the answer. Asking
    OpenRouter to exclude reasoning fixes it at the source, which raising
    max_tokens does not: the thinking simply expands to fill whatever it is
    given.

    Sent only to OpenRouter, because a stricter API may reject a field it
    does not recognise."""
    if "openrouter" in (settings.base_url or "").lower():
        return {"reasoning": {"exclude": True}}
    return {}


def _salvage_json(text: str) -> dict[str, Any] | None:
    """Rescue a reply that ran out of tokens mid-structure.

    Small models hit the limit part way through an object. Rather than lose
    the whole answer, drop the incomplete tail and close what is open: the
    complete entries before the cut are still good."""
    if not text.startswith("{"):
        return None
    # Walk back to the last point that could end a complete element.
    for cut in range(len(text) - 1, 0, -1):
        if text[cut] not in '}]"':
            continue
        candidate = text[: cut + 1]
        # Close whatever is still open, innermost first.
        stack: list[str] = []
        in_string = False
        escaped = False
        for char in candidate:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"':
                in_string = not in_string
            elif not in_string and char in "{[":
                stack.append(char)
            elif not in_string and char in "}]" and stack:
                stack.pop()
        if in_string:
            continue
        repaired = candidate.rstrip().rstrip(",")
        repaired += "".join("}" if opener == "{" else "]" for opener in reversed(stack))
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


def _text_from(payload: dict) -> str:
    """Pull the reply out of a chat completion.

    Not every provider fills `content`. A router like openrouter/free sends
    the request to whichever free model is up, and some of them answer with
    content set to null and the text in `reasoning` instead. Reaching
    straight for content and calling .strip() on it turns that into an
    AttributeError, which surfaces as a 502 and the useless message "the
    assistant did not answer"."""
    choices = payload.get("choices") or []
    if not choices:
        raise AIError("the model returned no choices")
    message = choices[0].get("message") or {}
    for field in ("content", "reasoning"):
        value = message.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Some providers stream the text as a list of content parts.
    parts = message.get("content")
    if isinstance(parts, list):
        joined = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if joined:
            return joined
    reason = choices[0].get("finish_reason") or "unknown"
    raise AIError(f"the model returned an empty reply (finish reason: {reason})")


async def chat_text(db: AsyncSession, system: str, user: str, max_tokens: int = 300) -> str:
    settings = await require_ai(db)
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    body = {
        "model": settings.chat_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        **_provider_extras(settings),
    }
    last: Exception | None = None
    # A free router lands on a different model each call, so one empty reply
    # says nothing about the next. Two attempts, then give up honestly.
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=_headers(settings))
            if resp.status_code != 200:
                raise AIError(f"chat endpoint returned {resp.status_code}")
            return _text_from(resp.json())
        except AIKeyUnreadable:
            raise
        except (AIError, httpx.HTTPError) as exc:
            last = exc
            logger.info("chat attempt %s failed: %s", attempt + 1, exc)
    raise AIError(str(last) if last else "the model did not answer")


async def chat_tools(
    db: AsyncSession,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int = 1200,
    tool_choice: str | None = None,
) -> dict[str, Any]:
    """One round of a tool-calling conversation.

    Returns the assistant message as the provider sent it: either it has
    `tool_calls` for the caller to execute, or `content` with the final
    answer. The loop around this lives in app.ai.agent; this function only
    knows how to make one request survive a flaky router.

    Models that cannot call tools answer this request with a 404 or a
    complaint about the `tools` field. That is reported as its own error
    rather than a generic failure, because the fix is an admin picking a
    tool-capable model, not retrying.
    """
    settings = await require_ai(db)
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    body = {
        "model": settings.chat_model,
        "messages": messages,
        "tools": tools,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        **_provider_extras(settings),
    }
    if tool_choice is not None:
        # "none" forces a text answer: used when the tool budget is spent,
        # because a model that may still call tools will keep calling them.
        body["tool_choice"] = tool_choice
    last: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=180) as http:
                resp = await http.post(url, json=body, headers=_headers(settings))
            if resp.status_code != 200:
                text_body = resp.text[:400]
                if "tool" in text_body.lower() or "function" in text_body.lower():
                    raise AIError(
                        "the configured model does not support tool calling. "
                        "Pick a tool-capable model under Admin, AI settings."
                    )
                raise AIError(f"chat endpoint returned {resp.status_code}")
            payload = resp.json()
            choices = payload.get("choices") or []
            if not choices:
                raise AIError("the model returned no choices")
            message = choices[0].get("message") or {}
            if message.get("tool_calls") or (
                isinstance(message.get("content"), str) and message["content"].strip()
            ):
                return message
            raise AIError("the model answered with neither text nor a tool call")
        except AIKeyUnreadable:
            raise
        except (AIError, httpx.HTTPError) as exc:
            last = exc
            logger.info("chat_tools attempt %s failed: %s", attempt + 1, exc)
    raise AIError(str(last) if last else "the model did not answer")
