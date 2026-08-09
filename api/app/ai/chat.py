"""The conversational assistant.

The model talks; the catalog decides. Every title the assistant mentions is
resolved against the local catalog and ranked by the same embedding maths as
the rest of the app, so it can describe and explain but never invent a film
that does not exist or claim something is streaming when it is not.
"""

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.ai import client, taste
from app.models import Interaction, ListItem, Title, User, WatchEvent
from app.models import List as ListModel

logger = logging.getLogger("roundtable.chat")

MAX_HISTORY_TURNS = 12
CANDIDATES = 40

SYSTEM = """You are the assistant inside Roundtable, a private film and series app.

You help one person decide what to watch. You are warm, brief, and specific.

Rules you must follow:
- Only ever discuss titles from the CANDIDATES list you are given. Never
  invent a title, a year, or a streaming service.
- Recommend at most four titles, and say in one short clause why each fits
  this person, using their history and stated tastes.
- If the candidates do not answer the question, say so plainly and suggest
  how to widen the search.
- Never claim to know where something streams unless the candidate says so.
- Reply in the language the person wrote their message in, including darija
  or mixed Arabic. Their profile language preferences are about the films
  they like to watch, not about what to answer them in: someone who enjoys
  Arabic cinema and asks in English gets an English answer.
- No emojis. No em dashes.

- Always write each title's exact name inside your reply. Never say "two
  titles" without naming them.

Return JSON only, shaped exactly:
{"reply": "<your message naming each pick>", "titles": ["<exact candidate name>", ...]}
The titles array repeats the ones you named, in your order, and is empty
only when you recommended nothing."""


def _tidy(text: str) -> str:
    """House style: models reach for em and en dashes, this app does not."""
    return (
        text.replace(" — ", ", ").replace(" – ", ", ").replace("—", ", ").replace("–", ", ").strip()
    )


async def _profile_block(db: AsyncSession, user: User) -> str:
    """What the assistant knows about this person, in plain text."""
    lines: list[str] = []
    prefs = user.prefs or {}
    if user.country_code:
        lines.append(f"Watches from: {user.country_code}")
    if prefs.get("languages"):
        lines.append("Prefers these languages: " + ", ".join(prefs["languages"]))

    watched = (
        (
            await db.execute(
                select(WatchEvent)
                .options(joinedload(WatchEvent.title))
                .where(WatchEvent.user_id == user.id)
                .order_by(WatchEvent.watched_at.desc())
                .limit(25)
            )
        )
        .scalars()
        .all()
    )
    if watched:
        parts = []
        for event in watched:
            bits = event.title.name
            if event.rating_10 is not None:
                bits += f" ({event.rating_10}/10)"
            if event.loved:
                bits += " loved"
            parts.append(bits)
        lines.append("Recently watched: " + "; ".join(parts))

    liked = (
        (
            await db.execute(
                select(Title.name)
                .join(Interaction, Interaction.title_id == Title.id)
                .where(Interaction.user_id == user.id, Interaction.kind == "like")
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    if liked:
        lines.append("Liked: " + ", ".join(liked))

    disliked = (
        (
            await db.execute(
                select(Title.name)
                .join(Interaction, Interaction.title_id == Title.id)
                .where(Interaction.user_id == user.id, Interaction.kind == "dislike")
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    if disliked:
        lines.append("Not for them: " + ", ".join(disliked))

    # Scoped to the person asking. Lists belong to a user, and a list with no
    # owner is the household shared one, which everybody here may see; without
    # the predicate this returned the first 25 rows in the whole install.
    saved = (
        (
            await db.execute(
                select(Title.name)
                .join(ListItem, ListItem.title_id == Title.id)
                .join(ListModel, ListModel.id == ListItem.list_id)
                .where(
                    or_(
                        ListModel.user_id == user.id,
                        ListModel.kind == "shared",
                    )
                )
                .limit(25)
            )
        )
        .scalars()
        .all()
    )
    if saved:
        lines.append("On their lists: " + ", ".join(saved))

    return "\n".join(lines) or "No history yet; this person is new here."


def _describe(title: Title) -> str:
    genres = ", ".join(g.get("name", "") for g in (title.genres or []))
    bits = [f"{title.name} ({title.year or 'year unknown'})"]
    if genres:
        bits.append(genres)
    if title.runtime:
        bits.append(f"{title.runtime} min")
    if title.original_language:
        bits.append(title.original_language)
    if title.imdb_rating:
        bits.append(f"IMDb {title.imdb_rating}")
    line = " | ".join(bits)
    if title.overview:
        line += f" | {title.overview[:220]}"
    return line


async def _candidates(db: AsyncSession, user: User, question: str) -> list[Title]:
    """Shortlist for the model: what this person would plausibly be told
    about, chosen by embedding similarity to the question and to them."""
    settings = await client.require_ai(db)
    question_vector = np.array((await client.embed_texts(db, [question]))[0])

    my_taste = await taste.get_taste(db, user)
    if my_taste is not None:
        # Bias toward the person without drowning out the question.
        blended = 0.7 * question_vector + 0.3 * my_taste
        norm = np.linalg.norm(blended)
        if norm:
            question_vector = blended / norm

    from app.models import TitleEmbedding

    rows = (
        await db.execute(
            select(Title)
            .join(TitleEmbedding, TitleEmbedding.title_id == Title.id)
            .where(TitleEmbedding.model == settings.embed_model)
            .order_by(TitleEmbedding.embedding.cosine_distance(question_vector.tolist()))
            .limit(CANDIDATES)
        )
    ).scalars()
    return list(rows)


async def answer_steps(
    db: AsyncSession, user: User, question: str, history: list[dict[str, str]] | None = None
) -> AsyncIterator[dict[str, Any]]:
    """The same answer, narrated.

    Every step is emitted after the work it describes has actually happened,
    so the trace is a report and not a loading animation dressed up as one.
    That matters most for the last step: it says how many titles the model
    named and how many survived checking against the catalog, which is the
    one number that tells you whether it was making things up."""
    from sqlalchemy import func

    from app.models import TitleEmbedding

    indexed = (await db.execute(select(func.count(TitleEmbedding.title_id)))).scalar_one()

    yield {
        "type": "step",
        "key": "read",
        "label": "Reading your question",
        "detail": f"{len(question.split())} words",
    }

    my_taste = await taste.get_taste(db, user)
    yield {
        "type": "step",
        "key": "taste",
        "label": "Weighing it against your taste",
        "detail": (
            "blended 70 to 30 with your history"
            if my_taste is not None
            else "no history yet, going on the question alone"
        ),
    }

    candidates = await _candidates(db, user, question)
    yield {
        "type": "step",
        "key": "search",
        "label": "Searching the catalog",
        "detail": f"{len(candidates)} closest of {indexed} indexed",
    }
    if candidates:
        yield {
            "type": "candidates",
            "titles": [
                {
                    "tmdb_id": t.tmdb_id,
                    "type": t.type,
                    "name": t.name,
                    "year": t.year,
                    "poster_path": t.poster_path,
                }
                for t in candidates[:12]
            ],
        }

    if not candidates:
        yield {
            "type": "done",
            "reply": "The catalog is empty, so there is nothing for me to suggest yet.",
            "titles": [],
        }
        return

    # Deliberately unnamed. Which model answers is an operator setting that
    # changes without notice, and naming it invites people to judge the
    # answer by the label. Admins can see it in Admin, AI settings.
    yield {
        "type": "step",
        "key": "ask",
        "label": "Asking the assistant",
        "detail": "it may only name titles from the shortlist",
    }

    result = await _finish(db, user, question, history, candidates)
    yield {
        "type": "step",
        "key": "check",
        "label": "Checking every title it named",
        "detail": result["check"],
    }
    yield {"type": "done", "reply": result["reply"], "titles": result["titles"]}


async def answer(
    db: AsyncSession, user: User, question: str, history: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    candidates = await _candidates(db, user, question)
    if not candidates:
        return {
            "reply": "The catalog is empty, so there is nothing for me to suggest yet.",
            "titles": [],
        }

    by_name = {t.name.lower(): t for t in candidates}
    catalog_block = "\n".join(f"- {_describe(t)}" for t in candidates)
    profile_block = await _profile_block(db, user)

    conversation = ""
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = "Person" if turn.get("role") == "user" else "You"
        conversation += f"{role}: {turn.get('content', '')}\n"

    prompt = (
        f"ABOUT THIS PERSON:\n{profile_block}\n\n"
        f"CANDIDATES (the only titles you may name):\n{catalog_block}\n\n"
        f"{'CONVERSATION SO FAR:' + chr(10) + conversation + chr(10) if conversation else ''}"
        f"THEIR MESSAGE:\n{question}"
    )

    payload = await client.chat_json(db, SYSTEM, prompt, max_tokens=900)
    reply = _tidy(str(payload.get("reply") or ""))
    named = payload.get("titles") or []

    # Resolve to real rows, dropping anything the model made up.
    resolved: list[Title] = []
    for name in named:
        match = by_name.get(str(name).strip().lower())
        if match is not None and match not in resolved:
            resolved.append(match)
    if len(named) != len(resolved):
        logger.info("dropped %d unmatched title(s) from the reply", len(named) - len(resolved))

    if not resolved and reply:
        resolved = _titles_named_in(reply, candidates)

    if not resolved and _sounds_like_a_recommendation(reply):
        # The model said it had picks but never named one. Rather than show
        # an answer with nothing behind it, answer from the ranking, which
        # is what actually decides the order anyway.
        resolved = candidates[:3]
        reply = "Here is what fits best from your catalog: " + ", ".join(
            f"{t.name} ({t.year})" if t.year else t.name for t in resolved
        )

    return {"reply": reply or "I am not sure about that one.", "titles": resolved}


async def _finish(
    db: AsyncSession,
    user: User,
    question: str,
    history: list[dict[str, str]] | None,
    candidates: list[Title],
) -> dict[str, Any]:
    """The model call and the verification, shared by both entry points."""
    by_name = {t.name.lower(): t for t in candidates}
    catalog_block = "\n".join(f"- {_describe(t)}" for t in candidates)
    profile_block = await _profile_block(db, user)

    conversation = ""
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = "Person" if turn.get("role") == "user" else "You"
        conversation += f"{role}: {turn.get('content', '')}\n"

    prompt = (
        f"ABOUT THIS PERSON:\n{profile_block}\n\n"
        f"CANDIDATES (the only titles you may name):\n{catalog_block}\n\n"
        f"{'CONVERSATION SO FAR:' + chr(10) + conversation + chr(10) if conversation else ''}"
        f"THEIR MESSAGE:\n{question}"
    )

    payload = await client.chat_json(db, SYSTEM, prompt, max_tokens=900)
    reply = _tidy(str(payload.get("reply") or ""))
    named = payload.get("titles") or []

    resolved: list[Title] = []
    for name in named:
        match = by_name.get(str(name).strip().lower())
        if match is not None and match not in resolved:
            resolved.append(match)
    dropped = len(named) - len(resolved)

    if not resolved and reply:
        resolved = _titles_named_in(reply, candidates)

    fell_back = False
    if not resolved and _sounds_like_a_recommendation(reply):
        resolved = candidates[:3]
        fell_back = True
        reply = "Here is what fits best from your catalog: " + ", ".join(
            f"{t.name} ({t.year})" if t.year else t.name for t in resolved
        )

    if fell_back:
        check = "it named none, so these come straight from the ranking"
    elif dropped > 0:
        check = f"{len(resolved)} found, {dropped} dropped as not in your catalog"
    else:
        check = f"all {len(resolved)} are in your catalog"

    return {
        "reply": reply or "I am not sure about that one.",
        "titles": resolved,
        "check": check,
    }


RECOMMENDING = ("recommend", "suggest", "you might", "found", "here are", "try ", "watch")


def _sounds_like_a_recommendation(reply: str) -> bool:
    lowered = reply.lower()
    return any(phrase in lowered for phrase in RECOMMENDING)


def _titles_named_in(reply: str, candidates: list[Title]) -> list[Title]:
    """Recover picks from prose when the model skips the array.

    Matching is on whole words, so a short title like "Her" is not found
    inside "other" or "there"."""
    lowered = reply.lower()
    found: list[tuple[int, Title]] = []
    # Longest first so "Dune: Part Two" wins over "Dune".
    for candidate in sorted(candidates, key=lambda t: -len(t.name)):
        pattern = re.compile(rf"(?<!\w){re.escape(candidate.name.lower())}(?!\w)")
        match = pattern.search(lowered)
        if match and all(candidate is not existing for _, existing in found):
            found.append((match.start(), candidate))
        if len(found) == 4:
            break
    found.sort(key=lambda pair: pair[0])
    return [title for _, title in found]
