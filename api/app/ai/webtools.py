"""The assistant's reach beyond the catalog: search, Reddit, and pages.

These exist because a film question is not always a database question.
"which order do the Conjuring films go in" has a better answer on the open
internet than in any API, and an assistant that cannot look is reduced to
guessing confidently, which is worse than either looking or admitting it.

Two rules hold everywhere in this file.

Everything fetched is UNTRUSTED DATA. A web page or a Reddit thread can
say anything, including instructions aimed at the model reading it. The
agent's system prompt says so, the content is fenced when handed over, and
nothing here can write: every function is a read, and the only write in
the whole chat feature stays behind the person's own Save button.

And nothing here reaches into the house. Fetches are plain HTTP(S) to
public hosts; addresses that resolve to the machine itself or to private
ranges are refused, so a crafted link cannot turn the assistant into a
probe of the network it runs on.
"""

import html
import ipaddress
import json
import logging
import re
import socket
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

logger = logging.getLogger("roundtable.webtools")

# Honest about being a bot, specific enough for site operators to act on.
UA = "RoundtableAssistant/1.0 (self-hosted film tracker; +https://github.com/1ordo/roundtable)"

# How much of a page the model gets to read. Enough for an article or a
# thread; a cap because a page is unbounded and the context window is not.
PAGE_CHARS = 6000
RESULTS = 8


class WebUnavailable(Exception):
    """The internet said no. Reported to the agent as a tool result, so it
    can try something else, rather than as an exception that kills the answer."""


def _refuse_private(url: str) -> None:
    """Refuse anything that is not plain public HTTP(S).

    The assistant fetches URLs a model chose, and the model read them on
    the open internet. Without this, a page saying "now read
    http://192.168.1.1/admin" turns a film question into a network scan.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise WebUnavailable("only http and https can be fetched")
    host = parsed.hostname or ""
    if not host:
        raise WebUnavailable("that is not a fetchable address")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise WebUnavailable(f"could not resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise WebUnavailable("that address is not on the public internet")


async def _get(url: str, follow_redirects: bool = True) -> httpx.Response:
    _refuse_private(url)
    try:
        async with httpx.AsyncClient(
            timeout=15, headers={"User-Agent": UA}, follow_redirects=follow_redirects
        ) as http:
            resp = await http.get(url)
    except httpx.HTTPError as exc:
        raise WebUnavailable(f"fetch failed: {exc}") from exc
    if resp.status_code != 200:
        raise WebUnavailable(f"the site answered {resp.status_code}")
    return resp


def _strip_html(page: str) -> str:
    """A page as readable text. Scripts and styles go first, then tags,
    then the whitespace the tags were holding apart."""
    page = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    page = html.unescape(page)
    return re.sub(r"\s+", " ", page).strip()


async def search_web(query: str) -> list[dict[str, str]]:
    """Web search results: title, url, snippet.

    DuckDuckGo's HTML endpoint, because it answers without an API key and a
    self-hosted app should not require one to be useful. The links come
    wrapped in a redirect with the real address in the uddg parameter.
    """
    resp = await _get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}")
    out: list[dict[str, str]] = []
    blocks = re.findall(
        r'(?s)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
        resp.text,
    )
    for href, title_html, tail in blocks[: RESULTS * 2]:
        target = href
        if "uddg=" in href:
            wrapped = parse_qs(urlparse(href).query).get("uddg")
            if wrapped:
                target = wrapped[0]
        if target.startswith("//"):
            target = "https:" + target
        snippet_match = re.search(r'(?s)class="result__snippet"[^>]*>(.*?)</a>', tail)
        out.append(
            {
                "title": _strip_html(title_html)[:200],
                "url": target,
                "snippet": _strip_html(snippet_match.group(1))[:300] if snippet_match else "",
            }
        )
        if len(out) >= RESULTS:
            break
    if not out:
        raise WebUnavailable("the search returned nothing readable")
    return out


async def search_reddit(query: str) -> list[dict[str, str]]:
    """Reddit search: what people actually say, not what a database stores.

    The public JSON endpoint, which needs no credentials. Each hit carries
    enough to decide whether the thread is worth reading with read_page.
    """
    resp = await _get(
        f"https://www.reddit.com/search.json?q={quote_plus(query)}&limit={RESULTS}&sort=relevance"
    )
    try:
        posts = resp.json().get("data", {}).get("children", [])
    except json.JSONDecodeError as exc:
        raise WebUnavailable("reddit answered with something that is not JSON") from exc
    out = []
    for post in posts[:RESULTS]:
        data = post.get("data") or {}
        out.append(
            {
                "title": str(data.get("title") or "")[:250],
                "subreddit": str(data.get("subreddit") or ""),
                "score": str(data.get("score") or 0),
                "url": f"https://www.reddit.com{data.get('permalink', '')}",
                "text": str(data.get("selftext") or "")[:400],
            }
        )
    if not out:
        raise WebUnavailable("no reddit threads matched")
    return out


async def read_page(url: str) -> str:
    """A page, as text the model can read.

    Reddit threads are fetched through their .json form instead of their
    HTML, which yields the post and the top comments rather than a wall of
    interface. That is the difference between "reading the thread" and
    reading Reddit's navigation.
    """
    parsed = urlparse(url)
    if parsed.hostname and parsed.hostname.endswith("reddit.com"):
        return await _read_reddit_thread(url)
    resp = await _get(url)
    text = _strip_html(resp.text)
    if not text:
        raise WebUnavailable("the page had no readable text")
    return text[:PAGE_CHARS]


async def _read_reddit_thread(url: str) -> str:
    bare = url.split("?")[0].rstrip("/")
    resp = await _get(f"{bare}.json?limit=30")
    try:
        payload = resp.json()
    except json.JSONDecodeError as exc:
        raise WebUnavailable("reddit answered with something that is not JSON") from exc
    if not isinstance(payload, list) or len(payload) < 1:
        raise WebUnavailable("that does not look like a reddit thread")
    bits: list[str] = []
    post = payload[0]["data"]["children"][0]["data"]
    bits.append(f"POST: {post.get('title', '')}")
    if post.get("selftext"):
        bits.append(str(post["selftext"])[:2000])
    if len(payload) > 1:
        for child in payload[1]["data"].get("children", [])[:12]:
            data = child.get("data") or {}
            body = str(data.get("body") or "").strip()
            if body:
                bits.append(f"COMMENT ({data.get('score', 0)} points): {body[:600]}")
    return "\n\n".join(bits)[:PAGE_CHARS]
