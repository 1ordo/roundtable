"""The real parents guide: parsing, caching, and the fallback boundary."""

import pytest

from app.catalog import imdb_guide

# Captured before the suite-wide stub replaces it. Every other test file
# wants IMDb switched off; this one is testing IMDb itself.
REAL_FOR_TITLE = imdb_guide.for_title


@pytest.fixture(autouse=True)
def real_guide(monkeypatch):
    monkeypatch.setattr(imdb_guide, "for_title", REAL_FOR_TITLE)


# The shape IMDb actually returns, trimmed to two categories.
REAL_SHAPE = {
    "title": {
        "parentsGuide": {
            "categories": [
                {
                    "category": {"id": "nudity", "text": "Sex & Nudity"},
                    "severity": {"text": "None"},
                    "guideItems": {
                        "total": 9,
                        "edges": [
                            {
                                "node": {
                                    "text": {
                                        "plainText": "A man says he is naked, seen mid-torso up."
                                    },
                                    "isSpoiler": False,
                                }
                            }
                        ],
                    },
                },
                {
                    "category": {"id": "violence", "text": "Violence & Gore"},
                    "severity": {"text": "Moderate"},
                    "guideItems": {
                        "total": 12,
                        "edges": [
                            {
                                "node": {
                                    "text": {
                                        "plainText": "Characters are punched, with brief blood."
                                    },
                                    "isSpoiler": False,
                                }
                            },
                            {
                                "node": {
                                    "text": {"plainText": "A character dies near the end."},
                                    "isSpoiler": True,
                                }
                            },
                        ],
                    },
                },
                # A category the app does not model is skipped, not crashed on.
                {
                    "category": {"id": "certificates", "text": "Certificates"},
                    "severity": None,
                    "guideItems": {"total": 0, "edges": []},
                },
            ]
        }
    }
}


def test_parses_severity_items_and_totals():
    guide = imdb_guide.parse(REAL_SHAPE)
    assert guide["source"] == "imdb"
    by_key = {c["key"]: c for c in guide["categories"]}
    assert set(by_key) == {"sex_nudity", "violence"}

    nudity = by_key["sex_nudity"]
    assert nudity["label"] == "Sex and nudity"
    assert nudity["severity"] == "none-reported"
    assert nudity["total"] == 9
    assert nudity["items"][0]["spoiler"] is False

    violence = by_key["violence"]
    assert violence["severity"] == "moderate"
    assert len(violence["items"]) == 2
    assert violence["items"][1]["spoiler"] is True


def test_the_one_line_note_is_never_a_spoiler():
    """The compact view shows a note; it must not be the entry that gives
    away the ending."""
    payload = {
        "title": {
            "parentsGuide": {
                "categories": [
                    {
                        "category": {"id": "violence"},
                        "severity": {"text": "Severe"},
                        "guideItems": {
                            "total": 1,
                            "edges": [
                                {
                                    "node": {
                                        "text": {"plainText": "The hero dies."},
                                        "isSpoiler": True,
                                    }
                                }
                            ],
                        },
                    }
                ]
            }
        }
    }
    category = imdb_guide.parse(payload)["categories"][0]
    assert category["note"] == ""
    # It is still available behind the spoiler flag, just not up front.
    assert category["items"][0]["text"] == "The hero dies."


def test_every_category_imdb_sends_is_mapped():
    """IMDb sends five categories with fixed ids. A typo in the map drops a
    whole category silently, which is how "Alcohol, Drugs & Smoking" went
    missing the first time."""
    from app.catalog.imdb_guide import CATEGORY_KEYS

    real_ids = {"NUDITY", "VIOLENCE", "PROFANITY", "ALCOHOL", "FRIGHTENING"}
    missing = sorted(i for i in real_ids if i.lower() not in CATEGORY_KEYS)
    assert not missing, f"IMDb categories with no mapping: {missing}"

    payload = {
        "title": {
            "parentsGuide": {
                "categories": [
                    {
                        "category": {"id": real_id},
                        "severity": {"text": "Mild"},
                        "guideItems": {"total": 1, "edges": []},
                    }
                    for real_id in sorted(real_ids)
                ]
            }
        }
    }
    assert len(imdb_guide.parse(payload)["categories"]) == 5


def test_a_title_with_no_guide_raises_rather_than_returning_empty():
    with pytest.raises(imdb_guide.GuideUnavailable):
        imdb_guide.parse({"title": {"parentsGuide": {"categories": []}}})
    with pytest.raises(imdb_guide.GuideUnavailable):
        imdb_guide.parse({})


def test_unknown_severity_words_do_not_become_a_claim():
    payload = {
        "title": {
            "parentsGuide": {
                "categories": [
                    {
                        "category": {"id": "profanity"},
                        "severity": {"text": "Extremely Bananas"},
                        "guideItems": {"total": 1, "edges": []},
                    }
                ]
            }
        }
    }
    assert imdb_guide.parse(payload)["categories"][0]["severity"] == "none-reported"


async def test_a_title_with_no_imdb_id_is_never_fetched(db_session, monkeypatch):
    from app.models import Title

    called = False

    async def boom(imdb_id):
        nonlocal called
        called = True
        raise AssertionError("should not reach the network")

    monkeypatch.setattr(imdb_guide, "_fetch", boom)
    title = Title(tmdb_id=1, type="movie", name="No Id", genres=[], imdb_id=None)
    assert await imdb_guide.for_title(db_session, title) is None
    assert called is False


async def test_the_guide_is_fetched_once_then_served_from_cache(db_session, monkeypatch):
    from app.models import Title

    calls = []

    async def fake_fetch(imdb_id):
        calls.append(imdb_id)
        return REAL_SHAPE

    monkeypatch.setattr(imdb_guide, "_fetch", fake_fetch)
    title = Title(tmdb_id=2, type="movie", name="Cached", genres=[], imdb_id="tt0000002")
    db_session.add(title)
    await db_session.commit()

    first = await imdb_guide.for_title(db_session, title)
    second = await imdb_guide.for_title(db_session, title)
    assert first == second
    assert first is not None and first["source"] == "imdb"
    assert calls == ["tt0000002"], "the second read must come from cache"


async def test_a_missing_guide_is_cached_so_it_is_not_refetched(db_session, monkeypatch):
    from app.models import Title

    calls = []

    async def empty(imdb_id):
        calls.append(imdb_id)
        return {"title": {"parentsGuide": {"categories": []}}}

    monkeypatch.setattr(imdb_guide, "_fetch", empty)
    title = Title(tmdb_id=3, type="movie", name="No Guide", genres=[], imdb_id="tt0000003")
    db_session.add(title)
    await db_session.commit()

    assert await imdb_guide.for_title(db_session, title) is None
    assert await imdb_guide.for_title(db_session, title) is None
    assert calls == ["tt0000003"], "a known absence must not be retried every view"


async def test_a_network_failure_is_not_cached(db_session, monkeypatch):
    import httpx

    from app.models import Title

    calls = []

    async def flaky(imdb_id):
        calls.append(imdb_id)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(imdb_guide, "_fetch", flaky)
    title = Title(tmdb_id=4, type="movie", name="Flaky", genres=[], imdb_id="tt0000004")
    db_session.add(title)
    await db_session.commit()

    assert await imdb_guide.for_title(db_session, title) is None
    assert await imdb_guide.for_title(db_session, title) is None
    # Being unreachable says nothing about whether a guide exists, so the
    # next view tries again.
    assert calls == ["tt0000004", "tt0000004"]
