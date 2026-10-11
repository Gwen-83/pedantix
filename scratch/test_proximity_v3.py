import gzip
import json
import math
import unicodedata
import functools
import numpy as np

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    nfkd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return stripped.replace("œ", "oe").replace("æ", "ae")

# 1. Load French Lemmas (Grammalecte)
with gzip.open("app/data/french_lemmas.json.gz", "rt", encoding="utf-8") as f:
    FRENCH_LEMMAS = {k: set(v) for k, v in json.load(f).items()}

# 2. Load French Embeddings (frWaC int8)
with gzip.open("app/data/french_embeddings.bin.gz", "rb") as f:
    hdr = f.readline().decode("utf-8").strip()
    v_size, dim = map(int, hdr.split())
    w_bytes = b""
    while True:
        line = f.readline()
        if line == b"---VECTORS---\n":
            break
        w_bytes += line
    words = w_bytes.decode("utf-8").splitlines()
    word_to_idx = {w: i for i, w in enumerate(words)}
    vectors = np.frombuffer(f.read(v_size * dim), dtype=np.int8).reshape((v_size, dim))
    norms = np.linalg.norm(vectors.astype(np.float32), axis=1)

print(f"Loaded {len(FRENCH_LEMMAS)} lemmas and {len(words)} embeddings.")

from app.nlp import (
    STOPWORDS_EXACT, FALSE_HOMOGRAPHS, IRREGULAR_PLURALS,
    HARDCODED_SYNONYMS, FRENCH_SYNONYMS, ETYMOLOGICAL_INDEX,
    CONCEPT_LOOKUP, WORD_ASSOCIATIONS, THEMATIC_CLUSTERS,
    GENERIC_BRIDGE_WORDS, clean_guess, get_singular_forms,
    calculate_numeric_proximity, PREFIX_LIST
)

# Extended false homographs
EXTENDED_FALSE_HOMOGRAPHS = set(FALSE_HOMOGRAPHS)
EXTENDED_FALSE_HOMOGRAPHS.update({
    ("enfant", "enfer"), ("enfer", "enfant"),
    ("parent", "parer"), ("parer", "parent"),
    ("talent", "talon"), ("talon", "talent"),
    ("talent", "talons"), ("talons", "talent"),
    ("lit", "lire"), ("lire", "lit"),
    ("souris", "sourire"), ("sourire", "souris"),
    ("bois", "boire"), ("boire", "bois"),
    ("cours", "courir"), ("courir", "cours"),
    ("vers", "verser"), ("verser", "vers"),
    ("fond", "fondre"), ("fondre", "fond"),
    ("sens", "sentir"), ("sentir", "sens"),
    ("tour", "tourner"), ("tourner", "tour"),
    ("pas", "passer"), ("passer", "pas"),
    ("plat", "plaire"), ("plaire", "plat"),
    ("vent", "vendre"), ("vendre", "vent"),
    ("pain", "peine"), ("peine", "pain"),
    ("chat", "chambre"), ("chambre", "chat"),
    ("sang", "sangle"), ("sangle", "sang"),
    ("cote", "coton"), ("coton", "cote"),
    ("point", "pointer"), ("pointer", "point"),
})

DERIVATION_SUFFIXES = (
    "ement", "ements", "ation", "ations", "ateur", "ateurs", "atrice", "atrices",
    "eux", "euse", "euses", "ique", "iques", "able", "ables", "ible", "ibles",
    "ite", "ites", "iser", "ification", "ifier", "isme", "ismes", "iste", "istes",
    "ien", "ienne", "iens", "iennes", "el", "elle", "els", "elles", "al", "ale", "ales",
    "ier", "iere", "iers", "ieres", "eur", "euse", "eurs", "euses"
)

@functools.lru_cache(maxsize=32768)
def get_lemmas(w: str) -> frozenset:
    if not w:
        return frozenset()
    lemmas = FRENCH_LEMMAS.get(w)
    if lemmas:
        return frozenset({w} | lemmas)
    if w in IRREGULAR_PLURALS:
        return frozenset({w, IRREGULAR_PLURALS[w]})
    return get_singular_forms(w)

@functools.lru_cache(maxsize=32768)
def check_match(guess: str, target: str) -> bool:
    gn = normalize_text(clean_guess(guess))
    tn = normalize_text(target)
    if not gn or not tn:
        return False
    if gn == tn:
        return True
    if gn in STOPWORDS_EXACT or tn in STOPWORDS_EXACT:
        return False
    if (gn, tn) in EXTENDED_FALSE_HOMOGRAPHS or (tn, gn) in EXTENDED_FALSE_HOMOGRAPHS:
        return False

    gl = get_lemmas(gn)
    tl = get_lemmas(tn)
    if gl and tl and (gl & tl):
        return True

    gs = get_singular_forms(gn)
    ts = get_singular_forms(tn)
    if gs & ts:
        return True
    return False

def get_word_vector(w: str):
    if w in word_to_idx:
        idx = word_to_idx[w]
        return vectors[idx], norms[idx]
    # Check lemmas
    for lem in get_lemmas(w):
        if lem in word_to_idx:
            idx = word_to_idx[lem]
            return vectors[idx], norms[idx]
    return None, None

def get_cosine_sim(w1: str, w2: str):
    v1, n1 = get_word_vector(w1)
    v2, n2 = get_word_vector(w2)
    if v1 is None or v2 is None:
        return None
    dot = int(np.dot(v1.astype(np.int32), v2.astype(np.int32)))
    return dot / (n1 * n2)

@functools.lru_cache(maxsize=65536)
def calculate_proximity(guess: str, target: str) -> float:
    gn = normalize_text(clean_guess(guess))
    tn = normalize_text(target)

    if not gn or not tn:
        return 0.0

    if check_match(gn, tn):
        return 100.0

    if gn.isdigit() and tn.isdigit():
        return calculate_numeric_proximity(int(gn), int(tn))
    if gn.isdigit() or tn.isdigit():
        return 0.0

    if gn in STOPWORDS_EXACT or tn in STOPWORDS_EXACT:
        return 0.0

    if (gn, tn) in EXTENDED_FALSE_HOMOGRAPHS or (tn, gn) in EXTENDED_FALSE_HOMOGRAPHS:
        return 0.0

    best_score = 0.0

    # 1. Direct Word Embeddings Cosine Similarity
    cos = get_cosine_sim(gn, tn)
    if cos is not None and cos >= 0.15:
        t = min(max((cos - 0.15) / 0.60, 0.0), 1.0)
        emb_score = 48.0 + 48.0 * (t ** 0.85)
        best_score = max(best_score, round(emb_score, 1))

    # 2. Hardcoded High-Confidence Synonyms
    g_forms = {gn} | get_singular_forms(gn)
    t_forms = {tn} | get_singular_forms(tn)
    g_hard = HARDCODED_SYNONYMS.get(gn, set())
    t_hard = HARDCODED_SYNONYMS.get(tn, set())
    is_hard_mutual = any(tf in g_hard for tf in t_forms) and any(gf in t_hard for gf in g_forms)
    is_hard_one_way = any(tf in g_hard for tf in t_forms) or any(gf in t_hard for gf in g_forms)
    if is_hard_mutual:
        len_ratio = min(len(gn), len(tn)) / max(len(gn), len(tn))
        best_score = max(best_score, round(94.0 + 3.5 * len_ratio, 1))
    elif is_hard_one_way:
        len_ratio = min(len(gn), len(tn)) / max(len(gn), len(tn))
        best_score = max(best_score, round(90.0 + 3.5 * len_ratio, 1))

    # 3. Thesaurus Synonyms
    g_syns = FRENCH_SYNONYMS.get(gn, set())
    t_syns = FRENCH_SYNONYMS.get(tn, set())
    is_syn_mutual = any(tf in g_syns for tf in t_forms) and any(gf in t_syns for gf in g_forms)
    is_syn_one_way = any(tf in g_syns for tf in t_forms) or any(gf in t_syns for gf in g_forms)
    if is_syn_mutual:
        len_ratio = min(len(gn), len(tn)) / max(len(gn), len(tn))
        best_score = max(best_score, round(91.0 + 3.0 * len_ratio, 1))
    elif is_syn_one_way:
        len_ratio = min(len(gn), len(tn)) / max(len(gn), len(tn))
        best_score = max(best_score, round(86.0 + 3.5 * len_ratio, 1))

    # 4. Etymological Root Families
    ge = ETYMOLOGICAL_INDEX.get(gn)
    te = ETYMOLOGICAL_INDEX.get(tn)
    if ge and te and ge == te:
        best_score = max(best_score, 88.0)

    # 5. Concept Domains
    g_concepts = CONCEPT_LOOKUP.get(gn, [])
    t_concepts = CONCEPT_LOOKUP.get(tn, [])
    for cd_g, role_g in g_concepts:
        for cd_t, role_t in t_concepts:
            if cd_g is cd_t:
                base = cd_g["base_score"]
                if role_g == "core" and role_t == "core":
                    score = base + 4.0
                elif role_g == "core" or role_t == "core":
                    score = base - 2.0
                else:
                    score = base - 8.0
                best_score = max(best_score, score)

    # 6. Word Associations
    if gn in WORD_ASSOCIATIONS and tn in WORD_ASSOCIATIONS[gn]:
        best_score = max(best_score, float(WORD_ASSOCIATIONS[gn][tn]))
    elif tn in WORD_ASSOCIATIONS and gn in WORD_ASSOCIATIONS[tn]:
        best_score = max(best_score, float(WORD_ASSOCIATIONS[tn][gn]))

    # 7. Verified Derivational Morphology
    # Only if cosine is NOT strongly negative (prevents coincidental prefix matches)
    if cos is None or cos >= 0.05:
        short_w, long_w = (gn, tn) if len(gn) < len(tn) else (tn, gn)
        if len(short_w) >= 4 and long_w.startswith(short_w):
            suffix = long_w[len(short_w):]
            if suffix in DERIVATION_SUFFIXES:
                deriv_score = 84.0 + 4.0 * (len(short_w) / len(long_w))
                best_score = max(best_score, round(deriv_score, 1))

    # 8. Shared 2nd-degree synonyms (Adamic-Adar)
    if g_syns and t_syns and (cos is None or cos >= 0.05):
        meaningful_shared = (g_syns & t_syns) - GENERIC_BRIDGE_WORDS
        if len(meaningful_shared) >= 1:
            total_weight = sum(1.0 / math.log2(max(len(FRENCH_SYNONYMS.get(sw, set())), 2)) for sw in meaningful_shared)
            if total_weight >= 0.35:
                best_score = max(best_score, round(58.0 + 24.0 * min(total_weight / 2.5, 1.0), 1))

    return round(best_score, 1) if best_score >= 48.0 else 0.0

if __name__ == "__main__":
    test_cases = [
        # (word1, word2, expected_match, min_expected_prox)
        # Exact & Grammatical inflections
        ("grand", "grande", True, 100.0),
        ("nouveau", "nouvelle", True, 100.0),
        ("beau", "belle", True, 100.0),
        ("vieux", "vieille", True, 100.0),
        ("acteur", "actrice", True, 100.0),
        ("cheval", "chevaux", True, 100.0),
        ("oeil", "yeux", True, 100.0),
        ("manger", "mangeait", True, 100.0),
        ("naquit", "naitre", True, 100.0),
        ("voulut", "vouloir", True, 100.0),

        # Semantic links
        ("avion", "atterrir", False, 85.0),
        ("avion", "decoller", False, 75.0),
        ("ordinateur", "ecran", False, 75.0),
        ("clavier", "souris", False, 85.0),
        ("chien", "aboyer", False, 80.0),
        ("chat", "miauler", False, 80.0),
        ("chanson", "paroles", False, 75.0),
        ("danger", "dangereux", False, 80.0),
        ("courage", "courageux", False, 75.0),
        ("facile", "facilite", False, 75.0),
        ("cuisine", "casserole", False, 70.0),
        ("boulanger", "baguette", False, 75.0),
        ("peintre", "toile", False, 75.0),
        ("medecin", "hopital", False, 85.0),
        ("mer", "poisson", False, 60.0),
        ("livre", "chapitre", False, 70.0),
        ("soleil", "lune", False, 85.0),
        ("roi", "royaume", False, 90.0),
        ("pluie", "parapluie", False, 70.0),
        ("guitare", "corde", False, 60.0),
        ("fromage", "vache", False, 60.0),

        # Unrelated words & False friends (MUST be 0.0)
        ("enfant", "enfer", False, 0.0),
        ("talent", "talons", False, 0.0),
        ("parent", "parer", False, 0.0),
        ("lit", "lire", False, 0.0),
        ("souris", "sourire", False, 0.0),
        ("bois", "boire", False, 0.0),
        ("banc", "banque", False, 0.0),
        ("conte", "continuer", False, 0.0),
        ("paner", "panique", False, 0.0),
        ("mer", "mere", False, 0.0),
        ("pere", "perdre", False, 0.0),
        ("mort", "morceau", False, 0.0),
        ("port", "porte", False, 0.0),
        ("pont", "ponte", False, 0.0),
        ("car", "carte", False, 0.0),
        ("vol", "volee", False, 0.0),
    ]

    print("\n--- TEST EXECUTION ---")
    all_passed = True
    for w1, w2, exp_m, min_p in test_cases:
        m = check_match(w1, w2)
        p = calculate_proximity(w1, w2)
        match_ok = (m == exp_m)
        if exp_m:
            prox_ok = (p == 100.0)
        elif min_p == 0.0:
            prox_ok = (p == 0.0)
        else:
            prox_ok = (p >= min_p)
        passed = match_ok and prox_ok
        if not passed:
            all_passed = False
        status = "PASS" if passed else "FAIL"
        print(f"{w1:12s} vs {w2:12s} | match={m} (exp:{exp_m}) | prox={p:.1f}% (target:{min_p}%) -> {status}")

    print("\nFINAL RESULT:", "ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED!")
