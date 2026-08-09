"""Getting an object out of a reply, however the model wrapped it.

response_format is a request, not a guarantee. openrouter/free sends each
call to whichever free model is up and plenty of them ignore it, which is
what made Ask fail with "model did not return valid JSON"."""

from app.ai.client import _parse_json_reply


def test_plain_json():
    assert _parse_json_reply('{"reply": "hi", "titles": []}') == {"reply": "hi", "titles": []}


def test_fenced_json():
    assert _parse_json_reply('```json\n{"reply": "hi"}\n```') == {"reply": "hi"}


def test_prose_before_the_object():
    """The common failure: a model that ignores JSON mode introduces it."""
    reply = (
        "Sure! Here is the JSON you asked for:\n\n"
        '{"reply": "Try Chernobyl", "titles": ["Chernobyl"]}'
    )
    assert _parse_json_reply(reply) == {"reply": "Try Chernobyl", "titles": ["Chernobyl"]}


def test_prose_before_and_after():
    reply = 'Here you go:\n{"reply": "ok"}\nLet me know if you need more.'
    # The trailing prose makes it invalid, so this falls through to salvage,
    # which closes at the last complete element.
    assert _parse_json_reply(reply) == {"reply": "ok"}


def test_truncated_object_is_salvaged():
    reply = '{"quotes": [{"text": "one", "character": "A"}, {"text": "two", "char'
    out = _parse_json_reply(reply)
    assert out is not None
    assert out["quotes"][0]["text"] == "one"


def test_a_bare_array_is_not_an_object():
    """The callers all index by key, so a list is not a usable answer."""
    assert _parse_json_reply('["a", "b"]') is None


def test_pure_prose_gives_up():
    assert _parse_json_reply("I am not sure what you mean by that.") is None


def test_empty_gives_up():
    assert _parse_json_reply("") is None
    assert _parse_json_reply("   ") is None
