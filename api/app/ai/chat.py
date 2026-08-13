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
{"reply": "<your message naming each pick>", "titles": ["<exact candidate name>", ...],
 "list_name": "<a short name, or null>"}
The titles array repeats the ones you named, in your order, and is empty
only when you recommended nothing.

list_name is only for when the person asked for a set worth keeping: a
franchise in order, everything by one director, a themed run. Two or three
picks for tonight are not a list. Name it as they would ("Marvel, in order",
"Studio Ghibli"), never "Recommendations". Use null when in doubt: the
person is offered a button, and offering it for two films is noise."""


def _tidy(text: str) -> str:
    """House style: models reach for em and en dashes, this app does not."""
    return (
        text.replace(" — ", ", ").replace(" – ", ", ").replace("—", ", ").replace("–", ", ").strip()
    )


# A franchise named as a comparison, or as a qualifier on a single pick,
# rather than as the subject. "Like Harry Potter" wants something that
# resembles it; "a marvel film for tonight" wants one film. Answering either
# with the whole franchise is the wrong answer to the question asked.
_NOT_THE_FRANCHISE = re.compile(
    r"\b(like|similar to|similar|resembl\w*|reminds? me|instead of|other than"
    r"|besides|tonight|any good|worth (it|watching|a watch)|recommend\w*"
    r"|suggest\w*)\b",
    re.IGNORECASE,
)


# Framing to strip before what is left can be used as a franchise name.
# "harry potter in order" has to become "harry potter" or nothing matches,
# and so does "where and where to watch harry potter".
#
# Not "who" or "it": Doctor Who and It are real titles, and a strip that
# eats the name it was meant to find is worse than one that leaves noise.
_FRAMING = re.compile(
    r"\b(i\s*(wanna|want to|would like to)|make me|give me|show me|can you|please"
    r"|watch|watching|start|starting|see|list|ordered|order|all|every|whole|entire"
    r"|the|films?|movies?|shows?|series|marathon|a to z|chronological|so i can"
    r"|where|how|when|to|do|does|did|should|could|can|i|available|stream|streaming"
    r"|online|find|there|platform|service|app|has|have|had|got|get|want|wants"
    r"|wanted|looking|need|what|is|are|of|from|in|on|me|my|for|and|with)\b",
    re.IGNORECASE,
)


# Words that are never part of a franchise name. Without dropping these,
# "something good" survives the strip and gets looked up as though it were
# a title, and the collection search obliges with whatever it finds.
_GENERIC = frozenset(
    {
        "something", "anything", "everything", "stuff", "thing", "things",
        "some", "any", "more", "other", "else", "good", "great", "nice",
        "fun", "funny", "cool", "interesting", "best", "now", "today",
        "please", "thanks", "this", "that", "these", "those", "next",
        "new", "newest", "latest", "old",
        # A service is where you watch, never what you watch. Not "max":
        # dropping it would turn "mad max" into "mad".
        "netflix", "hulu", "hbo", "peacock", "prime", "showtime", "starz",
        "shahid", "osn", "crunchyroll", "disney+",
    }
)  # fmt: skip

# A franchise name is short. A long tail of words left over means the strip
# never found a name and the question was about something else.
_MOST_NAME_WORDS = 4


def _franchise_query(question: str) -> str:
    """What is left of a question once the asking is removed."""
    text = _FRAMING.sub(" ", question)
    text = re.sub(r"[^\w\s'-]+", " ", text)
    return " ".join(w for w in text.split() if w.lower() not in _GENERIC)


def _franchise_intent(question: str) -> str | None:
    """The franchise this question is about, or None.

    Naming one is enough, however the question is phrased. The first version
    of this demanded a phrase like "in order" or "all the", so "where can i
    watch harry potter" fell through to the shortlist, and the shortlist
    ranked KanColle, Gundam and Attack on Titan above Harry Potter because
    the encoder matched "where" and "watch" rather than the subject. A
    question that names a franchise is about that franchise whether or not
    the person spelled out that they wanted the set.

    Two ways in. A universe in the registry is recognised by name, because
    the MCU is not a TMDB collection and only the registry knows what it is.
    Anything else hands the leftover words to the resolver, which answers
    None when they do not name a franchise, and the caller falls back.

    The exception is a franchise named as a comparison or as a qualifier on
    one pick: something like a Marvel film wants one recommendation, not
    thirty-nine.
    """
    from app.catalog import universes

    if _NOT_THE_FRANCHISE.search(question):
        return None
    universe = universes.find(question)
    if universe is not None:
        return universe.name
    leftover = _franchise_query(question)
    # Two characters of noise is not a franchise name, and neither is a
    # sentence the strip failed to reduce.
    if len(leftover) < 3 or len(leftover.split()) > _MOST_NAME_WORDS:
        return None
    return leftover


# Asking where something streams, rather than what to watch.
_ASKS_WHERE = re.compile(
    r"\b(where|which (service|platform|app)|what (service|platform|app)"
    r"|streaming|stream(ed)? on|available|watch it on)\b",
    re.IGNORECASE,
)


async def _where_to_watch(db: AsyncSession, user: User, titles: list[Title]) -> str:
    """Which services carry this set, in the countries this person watches in.

    Named by how much of the set each one covers, because "all eight are on
    HBO Max" and "one of them is on HBO Max" are different answers and a
    bare list of every provider that appears anywhere cannot tell them
    apart.
    """
    from collections import Counter

    from app.config import get_settings
    from app.countries import for_user as countries_for
    from app.models import Availability

    if not titles:
        return ""
    # Their own countries, not the instance's: "where can I watch it" is a
    # question about where they are.
    countries = countries_for(user) or [get_settings().default_country]
    rows = (
        (
            await db.execute(
                select(Availability).where(
                    Availability.title_id.in_([t.id for t in titles]),
                    Availability.country.in_(countries),
                    Availability.kind == "stream",
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "None of them are streaming where you are, going by what the catalog has."

    # One title counts once per provider however many countries carry it.
    per_provider: dict[str, set[Any]] = {}
    for row in rows:
        per_provider.setdefault(row.provider_name, set()).add(row.title_id)
    ranked = Counter({name: len(ids) for name, ids in per_provider.items()})

    total = len(titles)
    parts = []
    for name, count in ranked.most_common(3):
        parts.append(f"{name} has {'all' if count == total else count} of them")
    return "Streaming: " + ", ".join(parts) + "."


async def _franchise_answer(db: AsyncSession, user: User, question: str) -> dict[str, Any] | None:
    """Answer a franchise question from the catalog, not from the model.

    This exists because the alternative was measurably wrong. Asked for the
    Marvel films in order, the shortlist path offered Where's Waldo, The
    Mexican and Lord of the Rings, then recommended a DC film, because the
    default encoder matches shared words and "marvel movies" shares none
    with anything useful.

    It also lifts the ceiling that shortlist had: the resolver reads TMDB, so
    it returns the whole franchise whether or not those films are in the
    local catalog yet. Anything new is ingested so it has a poster and a page
    to open, which is the difference between naming a film and offering it.
    """
    from app.catalog import ingest, tmdb, watch_order

    try:
        # The extracted name, because a collection lookup on a whole
        # sentence matches nothing. universes.find still sees the original.
        from app.catalog import universes as universe_registry

        named = universe_registry.find(question)
        lookup = question if named is not None else _franchise_query(question)
        found = await watch_order.resolve(db, query=lookup, user=user)
    except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
        return None
    if found is None or not found.titles:
        return None

    # Bring anything missing into the catalog so it renders as a real card
    # rather than a name. Capped: a first ask should not sit through sixty
    # sequential TMDB calls.
    resolved: list[Title] = []
    fetched = 0
    for entry in found.titles:
        row = (
            await db.execute(
                select(Title).where(Title.tmdb_id == entry.tmdb_id, Title.type == entry.type)
            )
        ).scalar_one_or_none()
        if row is None and fetched < 24:
            try:
                row = await ingest.ensure_title(db, entry.type, entry.tmdb_id)
                fetched += 1
            except (tmdb.TmdbNotConfigured, tmdb.TmdbError):
                row = None
        if row is not None:
            resolved.append(row)

    if not resolved:
        return None

    seen = sum(1 for t in found.titles if t.watched)
    left = len(found.titles) - seen
    bits = [f"{found.name} in release order, {len(found.titles)} of them."]
    if seen:
        bits.append(f"You have seen {seen}, so {left} to go.")
    first = next((t for t in found.titles if not t.watched), None)
    if first is not None:
        bits.append(f"Start with {first.name} ({first.year or 'year unknown'}).")
    # They asked where, so say where. A list of eight films is not an answer
    # to "where can I watch Harry Potter", and the availability is already
    # sitting in the table next to the titles.
    if _ASKS_WHERE.search(question):
        where = await _where_to_watch(db, user, resolved)
        if where:
            bits.append(where)
    if found.note:
        bits.append(found.note)

    return {
        "reply": " ".join(bits),
        "titles": resolved,
        "proposal": {
            "name": found.name,
            "titles": [
                {"tmdb_id": t.tmdb_id, "type": t.type, "name": t.name} for t in found.titles
            ],
        },
        "franchise": found,
    }


def _proposal(list_name: str | None, resolved: list[Title]) -> dict | None:
    """A named, ordered set the person can save with one press.

    Only offered from three titles up. Two picks for tonight are not a list,
    and a button under every answer stops being an offer and becomes noise.
    The contents are the titles the server already resolved, in the order it
    resolved them, so the model never decides what gets saved.
    """
    if not list_name or len(resolved) < 3:
        return None
    return {
        "name": list_name,
        "titles": [{"tmdb_id": t.tmdb_id, "type": t.type, "name": t.name} for t in resolved],
    }


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


# Someone describing a film they cannot name, rather than asking for a
# recommendation. Cheap to test and it decides whether the full-text leg is
# worth a query: "what should I watch tonight" gains nothing from it.
_RECALL = re.compile(
    r"\b(what(?:'s| is| was)? (?:the |that )?(?:film|movie|show|series|one)\b"
    r"|the one (?:where|with|about)|remember|forgot|forgotten|can't recall"
    r"|cannot recall|name of the|called\?|trying to (?:think|remember)"
    r"|there(?:'s| is| was) (?:a|this) (?:film|movie|show|series))",
    re.IGNORECASE,
)


def _sounds_like_recall(question: str) -> bool:
    return bool(_RECALL.search(question))


def _people(title: Title) -> tuple[str | None, list[str]]:
    """Director and top billing, out of the payload already on the row.

    raw_tmdb carries the whole TMDB detail response, credits included, and
    none of it ever reached the model. Asked who directed something, it had
    to guess from a row that contained the answer.
    """
    raw = title.raw_tmdb or {}
    credits = raw.get("credits") or {}
    director = None
    for person in credits.get("crew") or []:
        if person.get("job") == "Director":
            director = person.get("name")
            break
    if director is None and title.type == "tv":
        creators = raw.get("created_by") or []
        if creators:
            director = creators[0].get("name")
    cast = [p.get("name") for p in (credits.get("cast") or [])[:4] if p.get("name")]
    return director, cast


def _describe(title: Title) -> str:
    """One catalog line for the prompt.

    Deliberately dense. Everything here is already on the row, and every
    field left out is a question the model has to either dodge or invent an
    answer to. The overview is the expensive part, so it is last and
    truncated; the cheap identifying facts come first.
    """
    genres = ", ".join(g.get("name", "") for g in (title.genres or []))
    kind = "series" if title.type == "tv" else "film"
    bits = [f"{title.name} ({title.year or 'year unknown'}, {kind})"]
    if genres:
        bits.append(genres)
    if title.runtime:
        bits.append(f"{title.runtime} min")
    if title.original_language:
        bits.append(title.original_language)
    if title.imdb_rating:
        bits.append(f"IMDb {title.imdb_rating}")

    director, cast = _people(title)
    if director:
        bits.append(f"dir. {director}")
    if cast:
        bits.append("with " + ", ".join(cast))
    # Franchise membership answers a whole class of question on its own,
    # and it is one column.
    if title.collection_name:
        bits.append(f"part of {title.collection_name}")
    if title.keywords:
        bits.append("themes: " + ", ".join(title.keywords[:8]))

    line = " | ".join(bits)
    if title.overview:
        line += f" | {title.overview[:260]}"
    return line


async def _candidates(db: AsyncSession, user: User, question: str) -> list[Title]:
    """Shortlist for the model: what this person would plausibly be told
    about, chosen by embedding similarity to the question and to them.

    Two legs, because they fail in opposite directions. The vector leg is
    good at "more like this" and hopeless at "the one where a guy relives
    the same day", which the default lexical encoder scores below random.
    The full-text leg over TMDB keywords is the reverse: it finds the time
    loop film immediately and knows nothing about taste. Whichever produced
    the better answer, it is in the list the model sees.
    """
    from app.catalog import plotsearch

    plot_hits: list[Title] = []
    if _sounds_like_recall(question):
        try:
            plot_hits = await plotsearch.find(db, question, limit=12)
        except Exception:
            logger.info("plot search unavailable; falling back to the vector leg alone")

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

    # Plot hits go first: when someone is describing a half-remembered film,
    # the thing they are describing is the answer, and the taste-blended
    # neighbours are context around it.
    out: list[Title] = []
    seen: set = set()
    for title in [*plot_hits, *rows]:
        if title.id in seen:
            continue
        seen.add(title.id)
        out.append(title)
    return out[:CANDIDATES]


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

    # A franchise question is not answered the same way as "what should I
    # watch", so it must not be narrated as though it were. The trace is a
    # report of what happened; describing a shortlist search that never ran
    # would make it a decoration.
    franchise = _franchise_intent(question)
    if franchise:
        yield {
            "type": "step",
            "key": "read",
            "label": "Reading your question",
            "detail": f"a franchise: {franchise}",
        }
        yield {
            "type": "step",
            "key": "resolve",
            "label": "Resolving it from the catalog",
            "detail": "release order, not the model's guess",
        }
        answer_out = await _franchise_answer(db, user, question)
        if answer_out is not None:
            found = answer_out["franchise"]
            fresh = len(found.titles) - len([t for t in found.titles if t.watched])
            yield {
                "type": "step",
                "key": "order",
                "label": "Putting them in order",
                "detail": f"{len(found.titles)} titles, {fresh} you have not seen",
            }
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
                    for t in answer_out["titles"][:12]
                ],
            }
            yield {
                "type": "step",
                "key": "fetch",
                "label": "Fetching the ones you do not have",
                "detail": f"{len(answer_out['titles'])} ready to open",
            }
            await db.commit()
            yield {
                "type": "done",
                "reply": answer_out["reply"],
                "titles": answer_out["titles"],
                "proposal": answer_out["proposal"],
            }
            return
        yield {
            "type": "step",
            "key": "resolve-miss",
            "label": "Could not resolve that franchise",
            "detail": "falling back to searching the catalog",
        }

    recall = _sounds_like_recall(question)
    yield {
        "type": "step",
        "key": "read",
        "label": "Reading your question",
        "detail": (
            f"{len(question.split())} words, sounds like you are trying to place a title"
            if recall
            else f"{len(question.split())} words"
        ),
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
        "label": "Searching what it is about" if recall else "Searching the catalog",
        "detail": (
            f"{len(candidates)} of {indexed}, by plot and by similarity"
            if recall
            else f"{len(candidates)} closest of {indexed} indexed"
        ),
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
            "proposal": None,
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
    yield {
        "type": "done",
        "reply": result["reply"],
        "titles": result["titles"],
        "proposal": result.get("proposal"),
    }


async def answer(
    db: AsyncSession, user: User, question: str, history: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    # Same franchise short circuit as the narrated path. Two code paths that
    # answer the same question differently is a bug waiting for whichever one
    # is less used.
    if _franchise_intent(question):
        from_catalog = await _franchise_answer(db, user, question)
        if from_catalog is not None:
            return {
                "reply": from_catalog["reply"],
                "titles": from_catalog["titles"],
                "proposal": from_catalog["proposal"],
            }

    candidates = await _candidates(db, user, question)
    if not candidates:
        return {
            "reply": "The catalog is empty, so there is nothing for me to suggest yet.",
            "titles": [],
            "proposal": None,
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
    # A name for the set, when the model judged it worth keeping. The server
    # decides what is actually in it; this is the only new thing the model
    # gets to say, and it is a label.
    list_name = payload.get("list_name")
    list_name = " ".join(str(list_name).split())[:120] if list_name else None

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

    return {
        "reply": reply or "I am not sure about that one.",
        "titles": resolved,
        "proposal": _proposal(list_name, resolved),
    }


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
    # A name for the set, when the model judged it worth keeping. The server
    # decides what is actually in it; this is the only new thing the model
    # gets to say, and it is a label.
    list_name = payload.get("list_name")
    list_name = " ".join(str(list_name).split())[:120] if list_name else None

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
        "proposal": _proposal(list_name, resolved),
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
