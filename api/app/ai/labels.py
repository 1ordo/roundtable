"""Curated vibe labels for zero-shot classification. Each description is
embedded once per model; titles are tagged by cosine similarity against these
centroids. Descriptions are written to be language-agnostic anchors for a
multilingual embedding model."""

VIBE_LABELS: dict[str, str] = {
    "cozy comfort watch": "warm, gentle, low-stakes story you watch to relax and feel safe",
    "feel-good": "uplifting and optimistic, leaves you happier than it found you",
    "tearjerker": "emotionally devastating, about loss, grief, love, and letting go",
    "mind-bending": "twisty puzzle narrative that plays with time, memory, or reality",
    "edge of your seat": "relentless tension, suspense, and high stakes from start to finish",
    "dark and gritty": "bleak tone, morally grey characters, violence and consequences",
    "slow burn": "patient, atmospheric storytelling that rewards attention",
    "laugh out loud": "broad comedy whose main goal is making you laugh hard",
    "romantic": "love story at the center, longing, chemistry, and grand gestures",
    "family night": "suitable for all ages, adventure and heart the whole family enjoys",
    "visually stunning": "extraordinary cinematography, production design, or animation",
    "true story energy": "based on or inspired by real people and historical events",
    "creepy and unsettling": "horror and dread, ghosts, monsters, or psychological fear",
    "epic scale": "sweeping saga with big battles, long journeys, and huge worlds",
    "smart and talky": "dialogue-driven, witty, cerebral, more ideas than action",
    "chaotic fun": "loud, fast, silly popcorn entertainment that never slows down",
}
