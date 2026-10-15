#!/usr/bin/env python3
"""Build the bundled Undercover lexicon from the project's French NLP data."""

import itertools
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.nlp import (
    FRENCH_WORDNET_SYNSETS,
    WORD_EMBEDDING_INDEX,
    WORD_EMBEDDING_NORMS,
    WORD_EMBEDDINGS,
)


OUTPUT = ROOT / "app" / "data" / "undercover_word_pairs.json"
MIN_SIMILARITY = 0.25
MAX_SIMILARITY = 0.95
PAIR_COUNT = 12_000


def build_pairs() -> list[list[str]]:
    synsets: dict[str, set[str]] = defaultdict(set)
    for word, synset_ids in FRENCH_WORDNET_SYNSETS.items():
        if (
            re.fullmatch(r"[a-z]{3,18}", word)
            and word in WORD_EMBEDDING_INDEX
            and WORD_EMBEDDING_INDEX[word] < 60_000
        ):
            for synset_id in synset_ids:
                synsets[synset_id].add(word)

    pairs: set[tuple[str, str]] = set()
    for words in synsets.values():
        for first, second in itertools.combinations(sorted(words), 2):
            if first.rstrip("s") == second.rstrip("s"):
                continue
            first_index = WORD_EMBEDDING_INDEX[first]
            second_index = WORD_EMBEDDING_INDEX[second]
            similarity = float(
                np.dot(
                    WORD_EMBEDDINGS[first_index].astype(np.float32),
                    WORD_EMBEDDINGS[second_index].astype(np.float32),
                )
                / (WORD_EMBEDDING_NORMS[first_index] * WORD_EMBEDDING_NORMS[second_index])
            )
            if MIN_SIMILARITY <= similarity <= MAX_SIMILARITY:
                pairs.add((first, second))

    if len(pairs) < PAIR_COUNT:
        raise ValueError(
            f"Expected at least {PAIR_COUNT} distinct word pairs, found {len(pairs)}."
        )
    selected = sorted(pairs)
    random.Random(20261015).shuffle(selected)
    return [list(pair) for pair in selected[:PAIR_COUNT]]


if __name__ == "__main__":
    OUTPUT.write_text(
        json.dumps(build_pairs(), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {PAIR_COUNT:,} word pairs to {OUTPUT}")
