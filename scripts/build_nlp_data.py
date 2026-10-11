#!/usr/bin/env python3
"""
Build high-precision NLP resources for Pedantix:
1. french_lemmas.json.gz (Comprehensive French lemmatization & inflection mapping from Grammalecte)
2. french_embeddings.bin.gz (Compact, quantized Word2Vec embeddings from frWaC)
"""

import gzip
import io
import json
import os
import re
import unicodedata
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "data")
os.makedirs(DATA_DIR, exist_ok=True)

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return stripped.replace("œ", "oe").replace("æ", "ae")

NOUN_VERB_HOMOGRAPHS = {
    "lit": "lit",
    "lits": "lit",
    "souris": "souris",
    "bois": "bois",
    "cours": "cours",
    "sens": "sens",
    "talent": "talent",
    "talents": "talent",
    "talon": "talon",
    "talons": "talon",
    "parent": "parent",
    "parents": "parent",
    "vol": "vol",
    "vols": "vol",
    "tour": "tour",
    "tours": "tour",
    "part": "part",
    "parts": "part",
    "fond": "fond",
    "fonds": "fond",
    "vers": "vers",
    "pas": "pas",
    "point": "point",
    "points": "point",
    "fait": "fait",
    "faits": "fait",
    "vue": "vue",
    "vues": "vue",
    "mort": "mort",
    "morts": "mort",
    "prix": "prix",
    "prise": "prise",
    "prises": "prise",
    "mise": "mise",
    "mises": "mise",
    "pause": "pause",
    "pauses": "pause",
    "conte": "conte",
    "contes": "conte",
    "banc": "banc",
    "bancs": "banc",
    "pont": "pont",
    "ponts": "pont",
    "port": "port",
    "ports": "port",
    "porte": "porte",
    "portes": "porte",
}

IRREGULAR_PLURALS = {
    "yeux": "oeil",
    "cieux": "ciel",
    "aieux": "aieul",
    "travaux": "travail",
    "baux": "bail",
    "coraux": "corail",
    "emaux": "email",
    "soupiraux": "soupirail",
    "vitraux": "vitrail",
    "chevaux": "cheval",
    "journaux": "journal",
    "bijoux": "bijou",
    "cailloux": "caillou",
    "choux": "chou",
    "genoux": "genou",
    "hiboux": "hibou",
    "joujoux": "joujou",
    "poux": "pou",
    "messieurs": "monsieur",
    "mesdames": "madame",
    "mesdemoiselles": "mademoiselle",
}


def build_lemmas(grammalecte_path: str, out_path: str):
    print(f"Building {out_path} from {grammalecte_path}...")
    flexion_to_lemmas = {}

    with open(grammalecte_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) < 5:
                continue
            flex = normalize_text(parts[2])
            lem = normalize_text(parts[3])
            tags = parts[4]

            if not flex or not lem or len(flex) <= 1 or len(lem) <= 1:
                continue

            if flex in NOUN_VERB_HOMOGRAPHS:
                flexion_to_lemmas.setdefault(flex, set()).add(NOUN_VERB_HOMOGRAPHS[flex])
                continue

            flexion_to_lemmas.setdefault(flex, set()).add(lem)

    for pl, sg in IRREGULAR_PLURALS.items():
        pln = normalize_text(pl)
        sgn = normalize_text(sg)
        flexion_to_lemmas.setdefault(pln, set()).add(sgn)
        flexion_to_lemmas.setdefault(sgn, set()).add(sgn)

    # Save lean representation
    lean_map = {}
    for k, v in flexion_to_lemmas.items():
        if v != {k}:
            lean_map[k] = sorted(list(v))

    print(f"Saving {len(lean_map)} lemma mappings...")
    with gzip.open(out_path, "wt", encoding="utf-8") as gz:
        json.dump(lean_map, gz, ensure_ascii=False, separators=(",", ":"))
    print(f"Finished {out_path} ({os.path.getsize(out_path) / 1024 / 1024:.2f} MB)")


def build_embeddings(frwac_path: str, out_path: str):
    print(f"Building {out_path} from {frwac_path}...")

    # Collect curated article vocabulary
    curated_words = set()
    curated_json = os.path.join(os.path.dirname(__file__), "..", "app", "curated_articles.json")
    if os.path.exists(curated_json):
        with open(curated_json) as f:
            articles = json.load(f)
        for title, data in articles.items():
            text = data.get("title", "") + " " + " ".join(data.get("paragraphs", []))
            tokens = re.findall(r"[a-zA-Zàâäéèêëîïôöùûüçœæ]+", text)
            for tok in tokens:
                w = normalize_text(tok)
                if len(w) >= 2:
                    curated_words.add(w)

    syn_json = os.path.join(DATA_DIR, "synonyms.json.gz")
    syn_words = set()
    if os.path.exists(syn_json):
        with gzip.open(syn_json, "rt") as f:
            syn_words = set(json.load(f).keys())

    fw_path = os.path.join(DATA_DIR, "french_words.txt.gz")
    fw = set()
    if os.path.exists(fw_path):
        with gzip.open(fw_path, "rt", encoding="utf-8") as f:
            for line in f:
                w = normalize_text(line.strip())
                if w:
                    fw.add(w)

    words_to_keep = []
    vecs_to_keep = []
    seen = set()

    with open(frwac_path, "rb") as f:
        header = f.readline().decode("utf-8").strip()
        vocab_size, dim = map(int, header.split())
        print(f"frWaC contains {vocab_size} words in {dim} dimensions")

        for i in range(vocab_size):
            w = []
            while True:
                c = f.read(1)
                if c == b" ":
                    break
                w.append(c)
            word = b"".join(w).decode("utf-8", errors="ignore")
            vec = np.frombuffer(f.read(dim * 4), dtype=np.float32)
            sep = f.read(1)

            wn = normalize_text(word)
            if len(wn) >= 2 and wn not in seen and not any(ch.isdigit() for ch in wn):
                if i < 65000 or wn in curated_words or wn in syn_words or wn in fw:
                    seen.add(wn)
                    vnorm = np.linalg.norm(vec)
                    if vnorm > 0:
                        words_to_keep.append(wn)
                        vecs_to_keep.append(vec / vnorm)

    print(f"Selected {len(words_to_keep)} vectors. Quantizing to int8...")
    X = np.array(vecs_to_keep, dtype=np.float32)
    X_i8 = np.clip(np.round(X * 127.0), -127, 127).astype(np.int8)

    vocab_count = len(words_to_keep)
    print(f"Saving {vocab_count} words to {out_path}...")
    with gzip.open(out_path, "wb", compresslevel=6) as gz:
        gz.write(f"{vocab_count} {dim}\n".encode("utf-8"))
        gz.write("\n".join(words_to_keep).encode("utf-8") + b"\n---VECTORS---\n")
        gz.write(X_i8.tobytes())

    print(f"Finished {out_path} ({os.path.getsize(out_path) / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    grammalecte_file = "/tmp/grammalecte.txt"
    frwac_file = "/tmp/frwac.bin"
    lemmas_out = os.path.join(DATA_DIR, "french_lemmas.json.gz")
    embeddings_out = os.path.join(DATA_DIR, "french_embeddings.bin.gz")

    if os.path.exists(grammalecte_file):
        build_lemmas(grammalecte_file, lemmas_out)
    else:
        print(f"Missing {grammalecte_file}")

    if os.path.exists(frwac_file):
        build_embeddings(frwac_file, embeddings_out)
    else:
        print(f"Missing {frwac_file}")
