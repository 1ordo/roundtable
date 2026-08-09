"""Every action the code emits reads as a sentence, not a dotted string."""

import re
from pathlib import Path

from app.models import AuditLog
from app.routers.admin import ACTION_TEXT, _describe

APP = Path(__file__).resolve().parents[1] / "app"


def emitted_actions() -> set[str]:
    """Scrape the action strings actually passed to audit() and equivalents."""
    found: set[str] = set()
    pattern = re.compile(r'audit\(\s*db,\s*\n?\s*"([a-z_]+\.[a-z_]+)"', re.MULTILINE)
    for path in APP.rglob("*.py"):
        text = path.read_text()
        found.update(pattern.findall(text))
        # Some call sites pass the action on its own line.
        for match in re.finditer(r'^\s+"([a-z_]+\.[a-z_]+)",\s*$', text, re.MULTILINE):
            name = match.group(1)
            if name.split(".")[1] in {"desc", "gte", "asc"}:
                continue  # TMDB sort parameters, not audit actions
            found.add(name)
    return found


def test_every_emitted_action_has_readable_text():
    missing = sorted(emitted_actions() - set(ACTION_TEXT))
    assert not missing, f"audit actions with no readable text: {missing}"


def test_unknown_actions_still_produce_a_sentence():
    row = AuditLog(action="something.brand_new", detail=None)
    summary, category = _describe(row, "Lordo")
    assert summary == "Lordo something brand_new"
    assert category == "other"


def test_a_failed_sign_in_names_the_attempted_user_not_someone():
    row = AuditLog(action="auth.failed", detail={"reason": "bad_credentials", "username": "ghost"})
    summary, category = _describe(row, None)
    assert summary == "ghost failed to sign in (wrong username or password)"
    assert category == "auth"


def test_details_are_folded_into_the_sentence():
    assert (
        _describe(AuditLog(action="list.bulk_add", detail={"added": 8}), "Lordo")[0]
        == "Lordo saved a whole franchise: 8 saved"
    )
    assert (
        _describe(
            AuditLog(action="settings.auth_update", detail={"oidc": False, "password": True}),
            "Lordo",
        )[0]
        == "Lordo changed the sign-in methods: password enabled"
    )
    assert (
        _describe(
            AuditLog(action="settings.auth_update", detail={"oidc": False, "password": False}),
            "Lordo",
        )[0]
        == "Lordo changed the sign-in methods: nothing enabled"
    )
