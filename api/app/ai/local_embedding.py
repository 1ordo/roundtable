"""A local, deterministic text encoder.

Not every deployment has an embedding endpoint: OpenRouter's free tier has no
embeddings, and the LM Studio box is not always up. Rather than disable the
recommendation engine in those cases, this encodes text here.

It is a hashed n-gram model: word unigrams and bigrams plus character
4-grams, hashed into a fixed 768-dimension space with sub-linear term
weighting and L2 normalisation. Character n-grams are what make it work
across Arabic, French and English without a tokenizer per language.

The result is a real vector space: similar plots and casts land near each
other, cosine similarity is meaningful, and everything downstream (taste
centroids, pgvector search, diversified ranking) is unchanged. It is weaker
than a trained transformer at paraphrase, and stronger than nothing at all.
"""

import hashlib
import math
import re
import unicodedata

DIM = 768
MODEL_NAME = "roundtable-local-hashed-ngrams-v1"
# What this encoder was called before the project was renamed. Rows in
# title_embeddings are keyed by this string, and ai_settings.embed_model
# stores it, so an instance that predates the rename still has the old value
# in its database. The migration rewrites both, and this stays so that a
# database that somehow missed it is still recognised as local rather than
# sent to an embedding endpoint that does not exist.
LEGACY_MODEL_NAMES = ("watchdeck-local-hashed-ngrams-v1",)


def is_local(model: str | None) -> bool:
    """Whether this model name means the bundled encoder."""
    return model == MODEL_NAME or model in LEGACY_MODEL_NAMES


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    # Strip Arabic diacritics and the tatweel so spellings collapse together.
    text = re.sub(r"[ً-ْـ]", "", text)
    return text


def _bucket(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % DIM


def _sign(token: str) -> float:
    # A second hash decides the sign, so unrelated collisions cancel out
    # instead of always reinforcing each other.
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4, person=b"sign").digest()
    return 1.0 if digest[0] & 1 else -1.0


def features(text: str) -> dict[str, float]:
    text = _normalize(text)
    counts: dict[str, float] = {}

    words = _TOKEN_RE.findall(text)
    for word in words:
        counts[f"w:{word}"] = counts.get(f"w:{word}", 0.0) + 1.0
    for first, second in zip(words, words[1:], strict=False):
        key = f"b:{first}_{second}"
        # Bigrams carry more meaning than single words, so weight them up.
        counts[key] = counts.get(key, 0.0) + 1.5

    compact = re.sub(r"\s+", " ", text)
    for size in (4,):
        for index in range(len(compact) - size + 1):
            gram = compact[index : index + size]
            if gram.strip():
                counts[f"c:{gram}"] = counts.get(f"c:{gram}", 0.0) + 0.5
    return counts


def encode(text: str) -> list[float]:
    vector = [0.0] * DIM
    for token, count in features(text).items():
        # Sub-linear scaling: the tenth mention of a word says little more
        # than the third.
        weight = (1.0 + math.log(count)) * _sign(token)
        vector[_bucket(token)] += weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        # Never hand back a zero vector: cosine distance is undefined.
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


def encode_many(texts: list[str]) -> list[list[float]]:
    return [encode(text) for text in texts]
