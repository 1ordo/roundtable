"""Content advisories may say what is present, never what is absent."""

from app.ai import advisories


def test_categories_are_fixed_and_complete():
    cleaned = advisories._clean({"categories": [], "summary": "x"})
    keys = [c["key"] for c in cleaned["categories"]]
    assert keys == [key for key, _ in advisories.CATEGORIES]
    assert all(c["severity"] == "none-reported" for c in cleaned["categories"])


def test_absence_is_never_asserted():
    """A model that tries to say "no nudity" must not get it published."""
    cleaned = advisories._clean(
        {
            "categories": [
                {"key": "sex_nudity", "severity": "none-reported", "note": "No nudity at all."},
                {"key": "violence", "severity": "moderate", "note": "Frequent fist fights."},
            ],
            "summary": "An action film.",
        }
    )
    by_key = {c["key"]: c for c in cleaned["categories"]}
    assert by_key["sex_nudity"]["note"] == "", "a claim of absence is dropped"
    assert by_key["violence"]["note"] == "Frequent fist fights.", "presence is kept"


def test_unknown_severities_fall_back_safely():
    cleaned = advisories._clean(
        {"categories": [{"key": "violence", "severity": "extreme", "note": "n"}], "summary": ""}
    )
    violence = next(c for c in cleaned["categories"] if c["key"] == "violence")
    assert violence["severity"] == "none-reported"
    assert violence["note"] == ""


def test_unknown_categories_are_ignored():
    cleaned = advisories._clean(
        {
            "categories": [
                {"key": "politics", "severity": "severe", "note": "made up"},
                {"key": "language", "severity": "mild", "note": "Some swearing."},
            ],
            "summary": "",
        }
    )
    keys = {c["key"] for c in cleaned["categories"]}
    assert "politics" not in keys
    assert next(c for c in cleaned["categories"] if c["key"] == "language")["note"]


def test_notes_and_summary_are_bounded():
    cleaned = advisories._clean(
        {
            "categories": [{"key": "violence", "severity": "mild", "note": "x" * 900}],
            "summary": "y" * 900,
        }
    )
    assert len(next(c for c in cleaned["categories"] if c["key"] == "violence")["note"]) <= 400
    assert len(cleaned["summary"]) <= 400


def test_prompt_carries_the_real_evidence():
    class FakeTitle:
        name = "Sicario"
        year = 2015
        type = "movie"
        genres = [{"id": 28, "name": "Action"}, {"id": 53, "name": "Thriller"}]
        certifications = {"US": "R", "GB": "15"}
        keywords = ["cartel", "border"]
        overview = "An idealistic agent joins a task force."

    prompt = advisories._prompt(FakeTitle())
    assert "Sicario" in prompt
    assert "US: R" in prompt, "the official rating is the strongest evidence"
    assert "Action, Thriller" in prompt
    assert "cartel" in prompt


async def test_advisory_endpoint_needs_ai(client, fake_idp, fake_tmdb_http):
    from tests.util import LORDO, do_login

    await do_login(client, fake_idp, LORDO)
    resp = await client.get("/api/titles/movie/354912/advisory")
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ai_disabled"


async def test_advisory_is_generated_once_then_reused(
    client, fake_idp, fake_tmdb_http, db_session, ai_enabled, monkeypatch
):
    from tests.util import LORDO, do_login

    calls = {"n": 0}

    async def fake_chat_json(db, system, user, max_tokens=800):
        calls["n"] += 1
        return {
            "categories": [
                {"key": "violence", "severity": "moderate", "note": "Cartoon peril."},
            ],
            "summary": "A family film with mild peril.",
        }

    monkeypatch.setattr(advisories.client, "chat_json", fake_chat_json)

    await do_login(client, fake_idp, LORDO)
    first = await client.get("/api/titles/movie/354912/advisory")
    assert first.status_code == 200
    body = first.json()
    assert body["summary"].startswith("A family film")
    assert next(c for c in body["categories"] if c["key"] == "violence")["severity"] == "moderate"

    second = await client.get("/api/titles/movie/354912/advisory")
    assert second.status_code == 200
    assert second.json() == body
    assert calls["n"] == 1, "the answer is cached, not paid for twice"


def test_truncated_model_output_is_salvaged():
    """Small models run out of tokens mid-object; keep what completed."""
    from app.ai.client import _salvage_json

    truncated = (
        '{"categories": [{"key": "violence", "severity": "moderate", "note": "Fights."}, '
        '{"key": "language", "severity": "mi'
    )
    out = _salvage_json(truncated)
    assert out is not None
    assert out["categories"][0]["note"] == "Fights."

    assert _salvage_json("not json at all") is None
    assert _salvage_json('{"a": 1}') == {"a": 1}
