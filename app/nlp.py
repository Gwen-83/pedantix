from __future__ import annotations
import unicodedata
import re
import os
import math
import gzip
import json
from typing import Set, Dict, Optional, List, Tuple, Any
from rapidfuzz import fuzz

try:
    import enchant
    ENCHANT_DICT = enchant.Dict("fr_FR")
except Exception:
    ENCHANT_DICT = None

def normalize_text(text: str) -> str:
    """Lowercases and removes diacritics (accents) and extra spaces."""
    if not text:
        return ""
    text = text.lower().strip()
    # Normalize unicode to decomposed form (NFD) and remove combining marks
    nfkd = unicodedata.normalize('NFD', text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != 'Mn')
    # Replace ligatures
    stripped = stripped.replace("œ", "oe").replace("æ", "ae")
    return stripped


def normalize_letter(c: str) -> str:
    """Normalizes a character to lowercase ASCII a-z without accents (e.g. 'é' -> 'e', 'œ' -> 'oe')."""
    if not c:
        return ""
    norm = normalize_text(c)
    letters = [ch for ch in norm if "a" <= ch <= "z"]
    return "".join(letters)


def is_letter_revealed(c: str, revealed_letters) -> bool:
    """Returns True if character c is revealed under revealed_letters (or is non-alpha)."""
    if not c.isalpha():
        return True
    norm = normalize_letter(c)
    if not norm:
        return True
    return any(l in revealed_letters for l in norm)

from app.synonyms_dict import (
    GENERIC_BRIDGE_WORDS,
    EXPANDED_STOPWORDS,
    HARDCODED_SYNONYMS_RAW,
    EXPANDED_ETYMOLOGICAL_FAMILIES,
    FRENCH_PROPER_NOUNS,
)
from app.synonym_api import SYNONYM_API


# Rich irregular and 3rd-group French verbs mapping to lemma
FRENCH_VERB_LEMMAS: Dict[str, str] = {}
FRENCH_VERB_LEMMA_CANDIDATES: Dict[str, Set[str]] = {}

def _register_verb(lemma: str, forms: list):
    for f in forms:
        fn = normalize_text(f)
        if fn:
            FRENCH_VERB_LEMMAS.setdefault(fn, lemma)
            FRENCH_VERB_LEMMA_CANDIDATES.setdefault(fn, set()).add(lemma)

_register_verb("etre", [
    "etre", "suis", "es", "est", "sommes", "etes", "sont",
    "ete", "etee", "etes", "etees", "etais", "etait", "etions", "etiez", "etaient",
    "fus", "fut", "fumes", "futes", "furent",
    "serai", "seras", "sera", "serons", "serez", "seront",
    "serais", "serait", "serions", "seriez", "seraient",
    "sois", "soit", "soyons", "soyez", "soient",
    "fusse", "fusses", "fussions", "fussiez", "fussent", "etant"
])

_register_verb("avoir", [
    "avoir", "ai", "as", "avons", "avez", "ont",
    "eu", "eue", "eus", "eues", "avais", "avait", "avions", "aviez", "avaient",
    "aurai", "auras", "aura", "aurons", "aurez", "auront",
    "aurais", "aurait", "aurions", "auriez", "auraient",
    "aie", "aies", "ait", "ayons", "ayez", "aient",
    "eusse", "eusses", "eut", "eussions", "eussiez", "eussent", "ayant"
])

_register_verb("faire", [
    "faire", "fais", "fait", "faisons", "faites", "font",
    "faisais", "faisait", "faisions", "faisiez", "faisaient",
    "fis", "fit", "fimes", "fites", "firent",
    "ferai", "feras", "fera", "ferons", "ferez", "feront",
    "ferais", "ferait", "ferions", "feriez", "feraient",
    "fasse", "fasses", "fassions", "fassiez", "fassent",
    "faisant", "faite", "faits", "faites", "refaire", "defaire"
])

_register_verb("aller", [
    "aller", "vais", "vas", "va", "allons", "allez", "vont",
    "allais", "allait", "allions", "alliez", "allaient",
    "allai", "allas", "alla", "allames", "allates", "allerent",
    "irai", "iras", "ira", "irons", "irez", "iront",
    "irais", "irait", "irions", "iriez", "iraient",
    "aille", "ailles", "aillons", "aillez", "aillent",
    "alle", "allee", "alles", "allees", "allant"
])

_register_verb("pouvoir", [
    "pouvoir", "peux", "puis", "peut", "pouvons", "pouvez", "peuvent",
    "pouvais", "pouvait", "pouvions", "pouviez", "pouvaient",
    "pus", "put", "pumes", "putes", "purent",
    "pourrai", "pourras", "pourra", "pourrons", "pourrez", "pourront",
    "pourrais", "pourrait", "pourrions", "pourriez", "pourraient",
    "puisse", "puisses", "puissions", "puissiez", "puissent",
    "pu", "pue", "pus", "pues", "pouvant"
])

_register_verb("vouloir", [
    "vouloir", "veux", "veut", "voulons", "voulez", "veulent",
    "voulais", "voulait", "voulions", "vouliez", "voulaient",
    "voulus", "voulut", "voulumes", "voulutes", "voulurent",
    "voudrai", "voudras", "voudra", "voudrons", "voudrez", "voudront",
    "voudrais", "voudrait", "voudrions", "voudriez", "voudraient",
    "veuille", "veuilles", "veillent", "voulu", "voulue", "voulus", "voulues", "voulant"
])

_register_verb("devoir", [
    "devoir", "dois", "doit", "devons", "devez", "doivent",
    "devais", "devait", "devions", "deviez", "devaient",
    "dus", "dut", "dumes", "dutes", "durent",
    "devrai", "devras", "devra", "devrons", "devrez", "devront",
    "devrais", "devrait", "devrions", "devriez", "devraient",
    "doive", "doives", "du", "due", "dus", "dues", "devant"
])

_register_verb("savoir", [
    "savoir", "sais", "sait", "savons", "savez", "savent",
    "savais", "savait", "savions", "saviez", "savaient",
    "sus", "sut", "sumes", "sutes", "surent",
    "saurai", "sauras", "saura", "saurons", "saurez", "sauront",
    "saurais", "saurait", "saurions", "sauriez", "sauraient",
    "sache", "saches", "sachions", "sachiez", "sachent",
    "su", "sue", "sus", "sues", "sachant"
])

_register_verb("voir", [
    "voir", "vois", "voit", "voyons", "voyez", "voient",
    "voyais", "voyait", "voyions", "voyiez", "voyaient",
    "vis", "vit", "vimes", "vites", "virent",
    "verrai", "verras", "verra", "verrons", "verrez", "verront",
    "verrais", "verrait", "verrions", "verriez", "verraient",
    "voie", "voies", "vu", "vue", "vus", "vues", "voyant", "revoir", "prevoir"
])

_register_verb("falloir", ["falloir", "faut", "fallait", "fallut", "faudra", "faudrait", "faille", "fallu"])
_register_verb("valoir", ["valoir", "vaux", "vaut", "valons", "valez", "valent", "valais", "valait", "valus", "valut", "vaudra", "vaudrait", "vaille", "valu"])

_register_verb("mourir", [
    "mourir", "meurs", "meurt", "mourons", "mourez", "meurent",
    "mourais", "mourait", "mourions", "mouriez", "mouraient",
    "mourus", "mourut", "mourumes", "mourutes", "moururent",
    "mourra", "mourras", "mourrai", "mourrons", "mourront", "mourrait",
    "meure", "meures", "mourant",
    "mort", "morte", "morts", "mortes"
])

_register_verb("naitre", [
    "naitre", "nais", "nait", "naissons", "naissez", "naissent",
    "naissais", "naissait", "naissions", "naissiez", "naissaient",
    "naquit", "naquirent", "naquis",
    "naitra", "naitrai", "naitront", "naitrait",
    "naisse", "naisses", "naissant",
    "nee", "nes", "nees"
])

_register_verb("vivre", [
    "vivre", "vis", "vit", "vivons", "vivez", "vivent",
    "vivais", "vivait", "vivions", "viviez", "vivaient",
    "vecus", "vecut", "vecumes", "vecutes", "vecurent",
    "vivra", "vivrai", "vivront", "vivrait",
    "vive", "vives", "vivant",
    "vecu", "vecue", "vecus", "vecues", "survivre", "revivre"
])

_register_verb("dire", [
    "dire", "dis", "dit", "disons", "dites", "disent",
    "disais", "disait", "disions", "disiez", "disaient",
    "dira", "diras", "dirai", "dirons", "diront", "dirais", "dirait",
    "dise", "dises", "disant",
    "dite", "dits"
])

_register_verb("lire", [
    "lire", "lis", "lit", "lisons", "lisez", "lisent",
    "lisais", "lisait", "lisions", "lisiez", "lisaient",
    "lut", "lurent", "lus",
    "lira", "liras", "lirai", "liront", "lirait",
    "lise", "lisant",
    "lu", "lue", "lues"
])

_register_verb("ecrire", [
    "ecrire", "ecris", "ecrit", "ecrivons", "ecrivez", "ecrivent",
    "ecrivais", "ecrivait", "ecrivions", "ecriviez", "ecrivaient",
    "ecrivit", "ecrivirent", "ecrivis",
    "ecrira", "ecrirai", "ecriront", "ecrirait",
    "ecrive", "ecrivant",
    "ecrite", "ecrits", "ecrites", "decrire", "inscrire", "prescrire"
])

_register_verb("prendre", [
    "prendre", "prends", "prend", "prenons", "prenez", "prennent",
    "prenais", "prenait", "prenions", "preniez", "prenaient",
    "pris", "prit", "primes", "prites", "prirent",
    "prendrai", "prendras", "prendra", "prendrons", "prendrez", "prendront", "prendrais", "prendrait",
    "prenne", "prennes", "prenant",
    "prise", "prises"
])

_register_verb("apprendre", [
    "apprendre", "apprends", "apprend", "apprenons", "apprenez", "apprennent",
    "apprenais", "apprenait", "appris", "apprit", "apprendrai", "apprenne",
    "apprise", "apprises", "apprenant"
])

_register_verb("comprendre", [
    "comprendre", "comprends", "comprend", "comprenons", "comprenez", "comprennent",
    "comprenais", "comprenait", "compris", "comprit", "comprendrai", "comprenne",
    "comprise", "comprises", "comprenant"
])

_register_verb("mettre", [
    "mettre", "mets", "met", "mettons", "mettez", "mettent",
    "mettais", "mettait", "mettions", "mettiez", "mettaient",
    "mis", "mit", "mimes", "mites", "mirent",
    "mettrai", "mettras", "mettra", "mettrons", "mettront", "mettrait",
    "mette", "mettes", "mettant",
    "mise", "mises"
])

_register_verb("permettre", [
    "permettre", "permets", "permet", "permettons", "permettez", "permettent",
    "permettait", "permis", "permit", "permettra", "permette", "permise", "permises", "permettant"
])

_register_verb("promettre", [
    "promettre", "promets", "promet", "promettons", "promettez", "promettent",
    "promettait", "promis", "promit", "promettra", "promette", "promise", "promises", "promettant"
])

_register_verb("venir", [
    "venir", "viens", "vient", "venons", "venez", "viennent",
    "venais", "venait", "venions", "veniez", "venaient",
    "vins", "vint", "vinmes", "vintes", "vinrent",
    "viendrai", "viendras", "viendra", "viendrons", "viendront", "viendrait",
    "vienne", "viennes", "venant",
    "venu", "venue", "venus", "venues"
])

_register_verb("devenir", [
    "devenir", "deviens", "devient", "devenons", "devenez", "deviennent",
    "devenais", "devenait", "devins", "devint", "deviendra", "devienne",
    "devenu", "devenue", "devenus", "devenues", "devenant"
])

_register_verb("revenir", [
    "revenir", "reviens", "revient", "revenons", "revenez", "reviennent",
    "revenais", "revenait", "revins", "revint", "reviendra", "revienne",
    "revenu", "revenue", "revenus", "revenues", "revenant"
])

_register_verb("tenir", [
    "tenir", "tiens", "tient", "tenons", "tenez", "tiennent",
    "tenais", "tenait", "tenions", "teniez", "tenaient",
    "tins", "tint", "tinmes", "tintes", "tinrent",
    "tiendrai", "tiendras", "tiendra", "tiendrons", "tiendront", "tiendrait",
    "tienne", "tiennes", "tenant",
    "tenu", "tenue", "tenus", "tenues"
])

_register_verb("maintenir", [
    "maintenir", "maintiens", "maintient", "maintenons", "maintenez", "maintiennent",
    "maintenait", "maintins", "maintint", "maintiendra", "maintenu", "maintenue", "maintenus", "maintenues", "maintenant"
])

_register_verb("obtenir", [
    "obtenir", "obtiens", "obtient", "obtenons", "obtenez", "obtiennent",
    "obtenait", "obtins", "obtint", "obtiendra", "obtenu", "obtenue", "obtenus", "obtenues", "obtenant"
])

_register_verb("connaitre", [
    "connaitre", "connais", "connait", "connaissons", "connaissez", "connaissent",
    "connaissais", "connaissait", "connaissions", "connaissiez", "connaissaient",
    "connut", "connurent", "connus",
    "connaitra", "connaitrai", "connaitront", "connaitrait",
    "connaisse", "connaissant",
    "connu", "connue", "connues", "reconnaitre"
])

_register_verb("paraitre", [
    "paraitre", "parais", "parait", "paraissons", "paraissez", "paraissent",
    "paraissais", "paraissait", "paraissions", "paraissiez", "paraissaient",
    "parut", "parurent", "parus",
    "paraitra", "paraitrai", "paraitront", "paraitrait",
    "paraisse", "paraissant",
    "paru", "parue", "parues", "apparaitre", "disparaitre"
])

_register_verb("ouvrir", [
    "ouvrir", "ouvre", "ouvres", "ouvrons", "ouvrez", "ouvrent",
    "ouvrais", "ouvrait", "ouvrant", "ouvert", "ouverte", "ouverts", "ouvertes", "ouvrit", "ouvrira"
])

_register_verb("couvrir", [
    "couvrir", "couvre", "couvres", "couvrons", "couvrez", "couvrent",
    "couvrais", "couvrait", "couvrant", "couvert", "couverte", "couverts", "couvertes", "couvrit", "couvrira"
])

_register_verb("decouvrir", [
    "decouvrir", "decouvre", "decouvres", "decouvrons", "decouvrez", "decouvrent",
    "decouvrais", "decouvrait", "decouvrant", "decouvert", "decouverte", "decouverts", "decouvertes", "decouvrit", "decouvrira"
])

_register_verb("construire", [
    "construire", "construis", "construit", "construisons", "construisez", "construisent",
    "construisais", "construisait", "construisant", "construite", "construits", "construites", "construira"
])

_register_verb("produire", [
    "produire", "produis", "produit", "produisons", "produisez", "produisent",
    "produisais", "produisait", "produisant", "produite", "produits", "produites", "produira"
])

_register_verb("peindre", [
    "peindre", "peins", "peint", "peignons", "peignez", "peignent",
    "peignais", "peignait", "peignant", "peinte", "peints", "peintes", "peignit", "peindra"
])

_register_verb("croire", [
    "croire", "crois", "croit", "croyons", "croyez", "croient",
    "croyais", "croyait", "croyant", "cru", "crue", "crus", "crues", "croira", "croie"
])

_register_verb("boire", [
    "boire", "bois", "boit", "buvons", "buvez", "boivent",
    "buvais", "buvait", "buvant", "bu", "bue", "bus", "bues", "boira", "boive"
])

# Alias for backward compatibility
FRENCH_IRREGULAR_VERBS = FRENCH_VERB_LEMMAS

# French irregular family clusters (words sharing same core etymological stem)
FRENCH_IRREGULAR_FAMILIES = {
    "roi": "fam_roi", "reine": "fam_roi", "royaume": "fam_roi", "royal": "fam_roi", "royale": "fam_roi", "royaux": "fam_roi", "royaute": "fam_roi",
    "empereur": "fam_empire", "imperatrice": "fam_empire", "empire": "fam_empire", "imperial": "fam_empire", "imperiale": "fam_empire", "imperiaux": "fam_empire",
    "homme": "fam_humain", "humain": "fam_humain", "humaine": "fam_humain", "humanite": "fam_humain",
    "ville": "fam_ville", "urbain": "fam_ville", "urbaine": "fam_ville", "urbanisme": "fam_ville",
    "mer": "fam_mer", "marin": "fam_mer", "marine": "fam_mer", "maritime": "fam_mer", "maritimes": "fam_mer",
    "terre": "fam_terre", "terrestre": "fam_terre", "territoire": "fam_terre", "territoires": "fam_terre",
    "soleil": "fam_soleil", "solaire": "fam_soleil", "solaires": "fam_soleil",
    "lune": "fam_lune", "lunaire": "fam_lune", "lunaires": "fam_lune",
    "espace": "fam_espace", "spatial": "fam_espace", "spatiale": "fam_espace", "spatiaux": "fam_espace",
    "france": "fam_france", "francais": "fam_france", "francaise": "fam_france", "francaises": "fam_france",
    "paris": "fam_paris", "parisien": "fam_paris", "parisienne": "fam_paris", "parisiens": "fam_paris",
    "medecine": "fam_medecine", "medecin": "fam_medecine", "medecins": "fam_medecine", "medical": "fam_medecine", "medicale": "fam_medecine",
    "peinture": "fam_peintre", "peintre": "fam_peintre", "peintres": "fam_peintre", "peindre": "fam_peintre",
    "sculpture": "fam_sculpteur", "sculpteur": "fam_sculpteur", "sculpteurs": "fam_sculpteur", "sculpter": "fam_sculpteur",
    "musique": "fam_musique", "musicien": "fam_musique", "musiciens": "fam_musique", "musical": "fam_musique", "musicale": "fam_musique",
    "guerre": "fam_guerre", "guerrier": "fam_guerre", "guerriers": "fam_guerre", "guerriere": "fam_guerre",
    "livre": "fam_livre", "litterature": "fam_livre", "litteraire": "fam_livre", "litteraires": "fam_livre",
    "loi": "fam_loi", "legal": "fam_loi", "legale": "fam_loi", "legislation": "fam_loi", "legislatif": "fam_loi",
    "dieu": "fam_dieu", "deesse": "fam_dieu", "divin": "fam_dieu", "divine": "fam_dieu", "divinite": "fam_dieu",
    "siecle": "fam_siecle", "seculaire": "fam_siecle",
}

FRENCH_IRREGULAR_FAMILIES.update({
    "nation": "fam_nation", "national": "fam_nation", "nationale": "fam_nation",
    "nationalite": "fam_nation", "nationaliser": "fam_nation", "international": "fam_nation",
    "cite": "fam_civique", "citoyen": "fam_civique", "citoyenne": "fam_civique",
    "civique": "fam_civique", "civil": "fam_civique", "civile": "fam_civique",
    "civilite": "fam_civique", "civilisation": "fam_civique", "civiliser": "fam_civique",
    "culture": "fam_culture", "cultiver": "fam_culture", "cultivateur": "fam_culture",
    "culturel": "fam_culture", "culturelle": "fam_culture", "agriculture": "fam_culture",
    "horticulture": "fam_culture",
    "education": "fam_education", "eduquer": "fam_education", "educateur": "fam_education",
    "educatrice": "fam_education", "educatif": "fam_education", "educative": "fam_education",
    "medecine": "fam_medecine", "medecin": "fam_medecine", "medical": "fam_medecine",
    "medicale": "fam_medecine", "medicament": "fam_medecine", "medication": "fam_medecine",
    "audition": "fam_audition", "audible": "fam_audition", "auditeur": "fam_audition",
    "auditrice": "fam_audition", "audio": "fam_audition", "audiovisuel": "fam_audition",
    "inaudible": "fam_audition",
    "spectacle": "fam_spectacle", "spectateur": "fam_spectacle",
    "spectatrice": "fam_spectacle", "spectaculaire": "fam_spectacle",
    "nationaux": "fam_nation", "nationales": "fam_nation",
})

PREFIX_LIST = (
    "anti", "auto", "bio", "micro", "macro", "neuro", "psycho", "socio",
    "geo", "tele", "astro", "retro", "inter", "intra", "sous", "sur",
    "hyper", "hypo", "multi", "omni", "poly", "pseudo", "super", "ultra",
    "contre", "extra", "infra", "trans", "para", "peri", "meso", "quasi",
    "mal", "non", "pro", "ex", "avant", "arriere", "pre", "post",
    "co", "re", "de", "in", "im", "dis"
)

def strip_prefix(w: str) -> str:
    """Strips common Greek/Latin and grammatical prefixes for root comparison."""
    for p in PREFIX_LIST:
        if len(w) > len(p) + 3 and w.startswith(p):
            return w[len(p):]
    return w

def clean_guess(word: str) -> str:
    """Cleans a guess word, removing quotes and trailing elision apostrophes."""
    if not word:
        return ""
    w = word.strip().strip('"«»“”')
    if w.endswith(("'", "’")):
        w = w[:-1]
    return w.strip()

STOPWORDS_EXACT: Set[str] = {
    # Articles
    "le", "la", "les", "l",
    "un", "une", "des",
    "du", "de", "d",
    # Demonstratives
    "ce", "cet", "cette", "ces",
    # Possessives
    "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses",
    "notre", "votre", "nos", "vos", "leur", "leurs",
    # Personal pronouns & particles
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "te", "se", "ne", "en", "y",
    "lui", "eux", "moi", "toi", "soi",
    # Relative pronouns
    "qui", "que", "quoi", "dont", "ou",
    # Conjunctions
    "et", "ou", "ni", "mais", "donc", "or", "car",
    # Prepositions
    "a", "au", "aux",
    "dans", "par", "pour", "sur", "sous", "avec", "sans", "chez",
    # Negations & adverbs
    "pas", "plus", "non", "si", "comme", "quand", "lorsque", "puisque", "quoique"
}
STOPWORDS_EXACT.update(EXPANDED_STOPWORDS)

NON_FLEXIBLE_WORDS: Set[str] = {
    "paris", "mois", "fois", "mais", "vers", "corps", "temps", "cours",
    "souris", "avis", "devis", "palais", "poids", "puits", "tapis", "pays",
    "heros", "repas", "succes", "proces", "progres", "acces", "deces", "os", "fils",
    "bois", "choix", "voix", "prix", "croix", "paix", "faux", "nez", "gaz", "pas",
    "univers", "virus", "cactus", "sphinx", "lynx", "corpus", "cursus", "sinus",
    "processus", "rebus", "humus", "tennis", "cannabis", "thorax"
}

IRREGULAR_PLURALS: Dict[str, str] = {
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

REGULAR_VERB_SUFFIXES = (
    "assions", "assiez", "assent",
    "issaient", "issions", "issiez",
    "issantes", "issants",
    "iraient", "irions", "iriez",
    "eraient", "erions", "eriez",
    "issais", "issait", "issons", "issez", "issent", "issant", "issante",
    "eaient", "eassent",
    "erais", "erait", "erons", "erez", "eront",
    "irais", "irait", "irons", "irez", "iront",
    "asse", "asses", "ames", "ates", "erent", "eons", "eait", "eant",
    "erai", "eras", "irai", "iras", "isse", "isses",
    "ions", "iez", "ient", "imes", "ites", "irent",
    "ais", "ait", "ant", "ons", "ent", "ira", "era", "ees", "ies",
    "er", "ir", "ez", "ai", "as", "es", "is", "it", "ee", "ie",
    "e", "i"
)

def get_singular_forms(w: str) -> Set[str]:
    """Generates normalized singular candidates from plural forms."""
    forms = {w}
    if w in NON_FLEXIBLE_WORDS or w in STOPWORDS_EXACT:
        return forms
    if w in IRREGULAR_PLURALS:
        forms.add(IRREGULAR_PLURALS[w])
    if w.endswith("eaux") and len(w) > 4:
        forms.add(w[:-1])
    elif w.endswith("aux") and len(w) > 3:
        forms.add(w[:-3] + "al")
        forms.add(w[:-3] + "ail")
    elif w.endswith("eux") and len(w) > 3:
        forms.add(w[:-1])
    elif w.endswith("oux") and len(w) > 3:
        forms.add(w[:-1])
    elif w.endswith("s") and len(w) > 3:
        forms.add(w[:-1])
    elif w.endswith("x") and len(w) > 3:
        forms.add(w[:-1])
    return forms

def get_verb_stems(w: str) -> Set[str]:
    """Extracts candidate regular verb stems for inflection matching."""
    stems = set()
    if w in NON_FLEXIBLE_WORDS or w in STOPWORDS_EXACT or len(w) <= 2:
        return stems
    for suffix in REGULAR_VERB_SUFFIXES:
        if w.endswith(suffix):
            stem = w[:-len(suffix)]
            if len(stem) >= 2:
                stems.add(stem)
    return stems

def check_match(guess: str, target: str) -> bool:
    """Checks if a player guess matches the target word under Pédantix rules.
    Matches exact words, verb conjugations, and singular/plural forms."""
    g_clean = clean_guess(guess)
    g_norm = normalize_text(g_clean)
    t_norm = normalize_text(target)

    if not g_norm or not t_norm:
        return False

    # 1. Exact match
    if g_norm == t_norm:
        return True

    # 2. Stopwords safeguard (never cross-match short functional words)
    if g_norm in STOPWORDS_EXACT or t_norm in STOPWORDS_EXACT:
        return False

    # 3. Verb lemma match (for irregular / 3rd group verbs)
    g_lemmas = FRENCH_VERB_LEMMA_CANDIDATES.get(g_norm, set())
    t_lemmas = FRENCH_VERB_LEMMA_CANDIDATES.get(t_norm, set())
    if g_lemmas & t_lemmas:
        return True

    # 4. Singular <-> Plural match
    g_sings = get_singular_forms(g_norm)
    t_sings = get_singular_forms(t_norm)
    if g_sings & t_sings:
        return True

    # 5. Regular verb stem match (covers -er and -ir conjugations)
    g_stems = get_verb_stems(g_norm)
    t_stems = get_verb_stems(t_norm)
    if g_stems and t_stems and (g_stems & t_stems):
        return True

    return False

def stem_french(word: str) -> str:
    """Stems a normalized French word using rich morphological rules."""
    w = normalize_text(word)
    if not w or len(w) <= 2:
        return w

    if w in FRENCH_IRREGULAR_VERBS:
        return FRENCH_IRREGULAR_VERBS[w]
    if w in FRENCH_IRREGULAR_FAMILIES:
        return FRENCH_IRREGULAR_FAMILIES[w]

    # Plural transforms
    if w.endswith("eaux") and len(w) > 4:
        return w[:-1]
    if w.endswith("aux") and len(w) > 4:
        return w[:-3] + "al"
    if w.endswith("eux") and len(w) > 4:
        return w
    if len(w) > 3 and w[-1] in ("s", "x"):
        w = w[:-1]

    # French suffixes transformation to common canonical stem
    suffixes = (
        ("logiques", "log"), ("logique", "log"), ("logiste", "log"), ("logie", "log"),
        ("ifiques", "ifi"), ("ifique", "ifi"), ("ification", "ifi"), ("ifiquement", "ifi"),
        ("istiques", "ist"), ("istique", "ist"), ("istes", "ist"), ("iste", "ist"), ("ismes", "ist"), ("isme", "ist"),
        ("ateurs", "at"), ("ateur", "at"), ("atrices", "at"), ("atrice", "at"), ("ations", "at"), ("ation", "at"),
        ("teurs", "t"), ("teur", "t"), ("trices", "t"), ("trice", "t"), ("tions", "t"), ("tion", "t"), ("sions", "t"), ("sion", "t"),
        ("iciennes", ""), ("icienne", ""), ("iciens", ""), ("icien", ""),
        ("iennes", ""), ("ienne", ""), ("iens", ""), ("ien", ""),
        ("iques", ""), ("ique", ""),
        ("aires", ""), ("aire", ""),
        ("euses", "eur"), ("euse", "eur"), ("eurs", "eur"),
        ("ieres", "ier"), ("iere", "ier"), ("iers", "ier"),
        ("ements", ""), ("ement", ""),
        ("ables", ""), ("able", ""), ("ibles", ""), ("ible", ""),
        ("ites", ""), ("ite", ""),
        ("elles", "el"), ("elle", "el"), ("els", "el"),
        ("ales", "al"), ("ale", "al"),
        ("ines", ""), ("ine", ""),
        ("ees", ""), ("ee", ""), ("er", ""), ("ir", ""), ("ant", ""),
        ("erions", ""), ("eriez", ""), ("eront", ""), ("erait", ""), ("erais", ""),
        ("aient", ""), ("ait", ""), ("ais", ""), ("ent", "")
    )
    for sfx, rep in suffixes:
        if len(w) > len(sfx) + 2 and w.endswith(sfx):
            w = w[:-len(sfx)] + rep
            break

    # Feminine forms of adjectives for long roots (e.g. grande/grand, petite/petit, lourde/lourd)
    # Avoid stripping single "e" from short nouns (e.g. ponte vs pont, porte vs port, conte, corde, etc.)
    if len(w) >= 6 and (w.endswith("de") or w.endswith("te") or w.endswith("le") or w.endswith("se")):
        w = w[:-1]

    return w


# High-affinity bidirectional semantic word associations (scores 78-88)
WORD_ASSOCIATIONS: Dict[str, Dict[str, int]] = {
    "science": {
        "chercheur": 86, "chercheurs": 86, "chercheuse": 86, "chercheuses": 86, "recherche": 86, "recherches": 86,
        "laboratoire": 85, "laboratoires": 85,
        "physique": 84, "physicien": 84, "physicienne": 84, "physiciens": 84, "physiciennes": 84,
        "chimie": 83, "chimiste": 83, "chimistes": 83, "chimique": 83, "chimiques": 83,
        "biologie": 83, "biologiste": 83, "biologistes": 83, "biologique": 83, "biologiques": 83,
        "theorie": 82, "theories": 82, "theoricien": 82,
        "mathematiques": 82, "mathematique": 82, "mathematicien": 82, "mathematicienne": 82,
        "decouverte": 82, "decouvertes": 82, "astronomie": 80, "astronome": 80, "experience": 80,
        "savant": 82, "savants": 82, "academie": 78, "universite": 76,
        "methode": 78, "technologie": 78, "savoir": 80, "connaissance": 80,
        "loi": 68, "formule": 72, "docteur": 72, "professeur": 74
    },
    "recherche": {
        "chercheur": 92, "chercheurs": 92, "science": 86, "laboratoire": 86,
        "decouverte": 84, "etude": 82, "theorie": 80, "institut": 78, "universite": 78
    },
    "histoire": {
        "siecle": 86, "siecles": 86, "epoque": 85, "epoques": 85,
        "historien": 92, "historiens": 92, "guerre": 78, "guerres": 78,
        "bataille": 76, "revolution": 78, "empire": 78, "roi": 76, "reine": 76,
        "regne": 78, "passe": 80, "antiquite": 82, "civilisation": 80,
        "archives": 78, "dynastie": 80, "chronologie": 82, "periode": 82
    },
    "guerre": {
        "bataille": 88, "armee": 88, "militaire": 88, "soldat": 86, "soldats": 86,
        "conflit": 86, "combat": 84, "paix": 80, "victoire": 82, "defaite": 82,
        "traite": 80, "invasion": 82, "ennemi": 80, "arme": 82, "troupes": 85
    },
    "roi": {
        "reine": 94, "royaume": 92, "royal": 92, "monarchie": 88, "prince": 86,
        "couronne": 84, "trone": 84, "empereur": 82, "regne": 86, "dynastie": 84, "chateau": 76
    },
    "ville": {
        "capitale": 88, "commune": 88, "habitant": 84, "habitants": 84,
        "population": 84, "quartier": 80, "maire": 82, "region": 78,
        "pays": 76, "urbain": 85, "rue": 76, "centre": 78, "monument": 75
    },
    "pays": {
        "nation": 88, "etat": 88, "territoire": 86, "capitale": 84,
        "frontiere": 84, "gouvernement": 80, "peuple": 80, "president": 78, "republique": 80
    },
    "peinture": {
        "peintre": 94, "tableau": 88, "tableaux": 88, "toile": 86, "toiles": 86,
        "dessin": 84, "artiste": 86, "art": 86, "musee": 84, "sculpture": 80,
        "exposition": 80, "galerie": 82, "couleur": 76, "portrait": 82
    },
    "musique": {
        "chanson": 88, "chansons": 88, "chanteur": 88, "chanteuse": 88,
        "compositeur": 88, "orchestre": 86, "concert": 86, "album": 84,
        "instrument": 84, "symphonie": 82, "opera": 82, "melodie": 82, "groupe": 78
    },
    "cinema": {
        "film": 90, "films": 90, "realisateur": 88, "acteur": 88, "actrice": 88,
        "tournage": 84, "scenario": 82, "festival": 80, "ecran": 78, "comedie": 78
    },
    "livre": {
        "roman": 88, "romans": 88, "auteur": 88, "ecrivain": 88, "litterature": 86,
        "texte": 82, "page": 80, "edition": 80, "publication": 80, "poeme": 78
    },
    "chateau": {
        "palais": 88, "forteresse": 88, "tour": 80, "rempart": 82,
        "domaine": 78, "residence": 78, "roi": 78, "seigneur": 78
    },
    "monument": {
        "edifice": 86, "cathedrale": 84, "tour": 82, "statue": 82,
        "historique": 82, "patrimoine": 82, "symbole": 78, "visiteur": 76
    },
    "espace": {
        "cosmos": 90, "etoile": 84, "etoiles": 84, "planete": 84, "planetes": 84,
        "univers": 84, "telescope": 82, "orbite": 82, "satellite": 82,
        "astronomie": 85, "soleil": 80, "lune": 80, "terre": 78
    },
    "mer": {
        "ocean": 90, "marin": 88, "maritime": 88, "cote": 82,
        "plage": 80, "port": 82, "bateau": 80, "navire": 80, "eau": 80, "ile": 80
    },
    "animal": {
        "espece": 85, "faune": 85, "sauvage": 82, "mammifere": 84,
        "oiseau": 82, "nature": 78, "poisson": 78, "corps": 74
    },
    "france": {
        "francais": 95, "paris": 88, "republique": 82, "europe": 82, "nation": 80, "pays": 80
    },
    "paris": {
        "capitale": 88, "france": 88, "seine": 82, "eiffel": 84, "louvre": 82, "ville": 80
    },
    "nature": {
        "environnement": 86, "ecologie": 84, "arbre": 82, "plante": 82,
        "foret": 82, "animal": 80, "terre": 78
    }
}

for _word, _associations in {
    "education": {
        "ecole": 90, "eleve": 88, "enseignement": 90, "apprentissage": 88,
        "professeur": 86, "enseignant": 86, "universite": 84, "formation": 84,
        "diplome": 82, "pedagogie": 82, "scolarite": 82, "etudiant": 84,
    },
    "economie": {
        "finance": 90, "marche": 86, "entreprise": 86, "commerce": 86,
        "industrie": 84, "monnaie": 84, "banque": 84, "capital": 82,
        "croissance": 82, "inflation": 82, "emploi": 80, "production": 80,
    },
    "politique": {
        "gouvernement": 90, "etat": 88, "election": 88, "democratie": 86,
        "parlement": 86, "president": 84, "ministre": 82, "constitution": 82,
        "parti": 80, "citoyen": 80, "republique": 84, "diplomatie": 82,
    },
    "religion": {
        "dieu": 90, "foi": 88, "culte": 88, "eglise": 86, "religieux": 86,
        "theologie": 84, "priere": 84, "temple": 82, "sacre": 82,
        "christianisme": 82, "islam": 82, "judaisme": 82,
    },
    "sante": {
        "medecine": 90, "maladie": 88, "medecin": 86, "hopital": 86,
        "patient": 84, "soin": 84, "traitement": 84, "diagnostic": 82,
        "chirurgie": 82, "prevention": 80, "medicament": 84,
    },
    "transport": {
        "vehicule": 90, "transport": 90, "route": 84, "train": 84,
        "automobile": 84, "avion": 84, "chemin": 80, "gare": 82,
        "voyage": 82, "circulation": 82, "navire": 80,
    },
    "alimentation": {
        "nourriture": 90, "aliment": 90, "cuisine": 86, "repas": 86,
        "boisson": 84, "ingredient": 82, "gastronomie": 82, "fruit": 80,
        "legume": 80, "nutrition": 84,
    },
    "architecture": {
        "batiment": 90, "architecte": 88, "construction": 88, "edifice": 86,
        "monument": 84, "maison": 82, "urbanisme": 82, "structure": 80,
        "architecture": 90, "patrimoine": 80,
    },
    "informatique": {
        "ordinateur": 90, "logiciel": 88, "programmation": 88, "donnee": 84,
        "reseau": 84, "internet": 84, "systeme": 82, "algorithme": 82,
        "numerique": 82, "materiel": 80,
    },
    "langue": {
        "langage": 90, "linguistique": 88, "mot": 86, "grammaire": 86,
        "vocabulaire": 84, "dialecte": 82, "parole": 82, "ecriture": 80,
        "francais": 80, "traduction": 82,
    },
    "climat": {
        "temperature": 88, "meteorologie": 88, "atmosphere": 86, "saison": 84,
        "precipitation": 82, "rechauffement": 82, "environnement": 80,
        "climatique": 88, "secheresse": 80, "pluie": 80,
    },
    "agriculture": {
        "culture": 86, "ferme": 84, "agriculteur": 88, "elevage": 86,
        "recolte": 84, "champ": 82, "cereale": 82, "rural": 80,
        "exploitation": 80, "cultiver": 82,
    },
    "sport": {
        "athlete": 88, "competition": 86, "equipe": 86, "championnat": 84,
        "entrainement": 82, "jeu": 80, "football": 84, "olympique": 82,
        "performance": 80, "stade": 80,
    },
    "justice": {
        "droit": 90, "tribunal": 88, "juge": 86, "loi": 86,
        "justice": 90, "avocat": 84, "juridique": 84, "proces": 82,
        "jurisprudence": 82, "peine": 80,
    },
    "communication": {
        "information": 88, "media": 88, "journal": 86, "presse": 86,
        "television": 84, "radio": 84, "message": 82, "internet": 82,
        "journaliste": 82, "publication": 80,
    },
    "energie": {
        "electricite": 90, "energie": 90, "centrale": 86, "nucleaire": 84,
        "renouvelable": 84, "petrole": 82, "gaz": 82, "charbon": 80,
        "production": 80, "consommation": 80,
    },
    "matiere": {
        "substance": 88, "materiau": 88, "atome": 86, "molecule": 84,
        "solide": 82, "liquide": 82, "gaz": 82, "chimie": 82,
        "physique": 80, "element": 80,
    },
}.items():
    WORD_ASSOCIATIONS.setdefault(_word, {}).update(_associations)


# Comprehensive French semantic clusters
THEMATIC_CLUSTERS = {
    "sciences_fondamentales": {
        "science", "scientifique", "scientifiques", "chercheur", "chercheurs", "recherche", "recherches",
        "laboratoire", "laboratoires", "decouverte", "decouvertes", "theorie", "theories",
        "formule", "formules", "loi", "lois", "methode", "methodes", "experience", "experiences",
        "savant", "savants", "academie", "institut", "universite", "nobel", "publication", "revue",
        "observation", "analyse", "resultat", "donnees", "savoir", "connaissance", "docteur", "professeur",
        "technologie", "technologique"
    },
    "sciences_physique_chimie": {
        "physique", "physicien", "physiciens", "atome", "atomes", "atomique", "particule", "particules",
        "molecule", "molecules", "moleculaire", "energie", "masse", "force", "gravitation", "vitesse",
        "lumiere", "onde", "ondes", "quantum", "quantique", "mecanique", "matiere", "noyau",
        "electron", "electrons", "proton", "protons", "neutron", "neutrons", "chimie", "chimiste",
        "chimique", "element", "elements", "reaction", "reactions", "acide", "base", "metal",
        "carbone", "oxygene", "hydrogene", "azote", "gaz", "liquide", "solide", "solution"
    },
    "sciences_biologie_medecine": {
        "biologie", "biologiste", "biologique", "cellule", "cellules", "cellulaire", "adn", "gene",
        "genes", "genetique", "genome", "organisme", "organismes", "espece", "especes", "vivant",
        "corps", "organe", "organes", "cerveau", "sang", "medecine", "medical", "medicale",
        "medecin", "medecins", "sante", "maladie", "maladies", "traitement", "virus", "bacterie",
        "vaccin", "immunite", "anatomie", "physiologie", "docteur", "hopital", "clinique"
    },
    "sciences_mathematiques": {
        "mathematique", "mathematiques", "mathematicien", "mathematiciens", "calcul", "calculer",
        "nombre", "nombres", "chiffre", "chiffres", "geometrie", "geometrique", "algebre",
        "theoreme", "theoremes", "equation", "equations", "fonction", "fonctions", "dimension",
        "infini", "logique", "probabilite", "statistique", "espace", "vecteur"
    },
    "espace_astronomie": {
        "astronomie", "astronome", "astronomes", "astronomique", "espace", "spatial", "spatiale",
        "cosmos", "cosmique", "galaxie", "galaxies", "etoile", "etoiles", "soleil", "solaire",
        "lune", "lunaire", "planete", "planetes", "orbite", "telescope", "univers", "terre",
        "mars", "jupiter", "saturne", "comete", "asteroide", "fusee", "satellite", "satellites"
    },
    "histoire_epoques": {
        "histoire", "historique", "historiques", "historien", "historiens", "siecle", "siecles",
        "annee", "annees", "epoque", "epoques", "periode", "periodes", "date", "dates",
        "chronologie", "ere", "temps", "passe", "antiquite", "moyen", "age", "renaissance",
        "moderne", "contemporain", "archives", "memoire", "dynastie", "regne", "civilisation"
    },
    "histoire_guerre_militaire": {
        "guerre", "guerres", "bataille", "batailles", "conflit", "conflits", "combat", "combats",
        "armee", "armees", "militaire", "militaires", "soldat", "soldats", "troupe", "troupes",
        "officier", "general", "marechal", "arme", "armes", "canon", "fusil", "char", "defense",
        "attaque", "siege", "invasion", "victoire", "defaite", "paix", "traite", "alliance", "ennemi"
    },
    "politique_pouvoir_etat": {
        "politique", "politiques", "gouvernement", "etat", "etats", "republique", "royaume",
        "empire", "empires", "monarchie", "roi", "reine", "prince", "princesse", "empereur",
        "president", "ministre", "parlement", "assemblee", "senat", "depute", "pouvoir", "regime",
        "souverain", "election", "vote", "democratie", "constitution", "loi", "parti"
    },
    "geographie_lieux": {
        "pays", "nation", "territoire", "frontiere", "frontieres", "capitale", "ville", "villes",
        "commune", "communes", "village", "quartier", "centre", "departement", "region", "regions",
        "continent", "europe", "asie", "afrique", "amerique", "oceanie", "monde", "population",
        "habitant", "habitants", "superficie", "nord", "sud", "est", "ouest"
    },
    "geographie_nature": {
        "montagne", "montagnes", "sommet", "colline", "vallee", "plaine", "volcan", "desert",
        "foret", "forets", "fleuve", "fleuves", "riviere", "rivieres", "eau", "mer", "mers",
        "ocean", "oceans", "lac", "lacs", "ile", "iles", "cote", "plage", "climat"
    },
    "arts_peinture_sculpture": {
        "art", "arts", "artiste", "artistes", "peinture", "peintures", "peintre", "peintres",
        "tableau", "tableaux", "toile", "toiles", "dessin", "sculpture", "sculpteur", "statue",
        "monument", "oeuvre", "oeuvres", "musee", "galerie", "salon", "exposition", "collection",
        "atelier", "style", "portrait", "paysage", "couleur"
    },
    "musique_spectacle": {
        "musique", "musical", "musicale", "musicien", "musiciens", "compositeur", "chanson",
        "chansons", "chant", "chanteur", "chanteuse", "voix", "orchestre", "concert", "opera",
        "symphonie", "album", "disque", "instrument", "piano", "violon", "guitare", "melodie"
    },
    "cinema_theatre": {
        "cinema", "film", "films", "tournage", "realisateur", "acteur", "actrice", "comedien",
        "role", "scenario", "festival", "cannes", "oscar", "theatre", "piece", "scene", "comedie", "drame"
    },
    "litterature_ecriture": {
        "litterature", "litteraire", "livre", "livres", "roman", "romans", "ecrivain", "ecrivains",
        "auteur", "auteurs", "poete", "poesie", "poeme", "texte", "page", "chapitre", "ecriture",
        "lecture", "edition", "publication", "essai", "goncourt"
    },
    "nature_animaux": {
        "animal", "animaux", "espece", "especes", "faune", "sauvage", "mammifere", "mammiferes",
        "oiseau", "oiseaux", "poisson", "poissons", "reptile", "insecte", "insectes", "nature",
        "cheval", "chien", "chat", "lion", "loup", "ours"
    },
    "nature_plantes": {
        "plante", "plantes", "arbre", "arbres", "fleur", "fleurs", "feuille", "feuilles", "foret",
        "forets", "bois", "vegetal", "vegetaux", "vegetation", "environnement", "ecologie", "racine"
    },
    "architecture_monuments": {
        "monument", "monuments", "batiment", "batiments", "edifice", "construction", "architecte",
        "architecture", "pierre", "fer", "acier", "tour", "eiffel", "cathedrale", "eglise",
        "chateau", "palais", "forteresse", "dome", "arche", "patrimoine"
    },
    "biographie_vie": {
        "naissance", "naitre", "ne", "nee", "mort", "morte", "deces", "mourir", "vie", "vivant",
        "enfance", "jeunesse", "famille", "pere", "mere", "fils", "fille", "enfant", "enfants",
        "frere", "soeur", "mariage", "epoux", "epouse", "tombe", "sepulture", "figure", "personnage"
    },
    "sports_competitions": {
        "sport", "sportif", "sportifs", "olympique", "olympiques", "athlete", "champion", "championnat",
        "equipe", "equipes", "match", "joueur", "joueurs", "tournoi", "stade", "coupe", "medaille",
        "football", "rugby", "tennis", "course"
    },
    "religion_philosophie": {
        "religion", "religieux", "foi", "dieu", "eglise", "chretien", "catholique", "islam", "musulman",
        "judaisme", "juif", "pape", "saint", "sainte", "temple", "priere", "philosophie", "philosophe",
        "pensee", "idee", "concept", "raison", "verite", "morale", "ethique", "conscience"
    }
}

THEMATIC_CLUSTERS.update({
    "economie_finance": {
        "economie", "economique", "economiste", "finance", "financier", "banque", "bancaire",
        "monnaie", "marche", "entreprise", "industrie", "commerce", "capital", "croissance",
        "inflation", "emploi", "production", "consommation", "revenu", "impot", "dette",
    },
    "education_ecole": {
        "education", "ecole", "scolarite", "enseignement", "enseignant", "professeur", "eleve",
        "etudiant", "universite", "faculte", "formation", "apprentissage", "pedagogie", "classe",
        "cours", "diplome", "examen", "college", "lycee", "instituteur",
    },
    "sante_medecine": {
        "sante", "medecine", "medical", "medecin", "maladie", "patient", "hopital", "clinique",
        "soin", "traitement", "diagnostic", "chirurgie", "medicament", "prevention", "vaccin",
        "infirmier", "urgence", "therapie", "guerison",
    },
    "transport_deplacements": {
        "transport", "vehicule", "automobile", "voiture", "route", "train", "rail", "gare",
        "avion", "aeroport", "navire", "bateau", "port", "voyage", "circulation", "metro",
        "bus", "camion", "moteur", "mobilite",
    },
    "alimentation_cuisine": {
        "alimentation", "aliment", "nourriture", "repas", "cuisine", "gastronomie", "nutrition",
        "ingredient", "recette", "fruit", "legume", "viande", "poisson", "pain", "fromage",
        "boisson", "restaurant", "agriculture", "cereale",
    },
    "technologie_informatique": {
        "technologie", "technique", "informatique", "ordinateur", "logiciel", "programmation",
        "reseau", "internet", "numerique", "donnee", "algorithme", "systeme", "robot", "machine",
        "innovation", "electronique", "materiel", "serveur", "intelligence", "artificiel",
    },
    "climat_environnement": {
        "climat", "climatique", "temperature", "meteorologie", "atmosphere", "saison", "pluie",
        "neige", "vent", "secheresse", "rechauffement", "environnement", "ecologie", "pollution",
        "carbone", "emission", "biodiversite", "foret", "ocean", "energie",
    },
    "agriculture_elevage": {
        "agriculture", "agriculteur", "ferme", "exploitation", "champ", "culture", "cultiver",
        "recolte", "cereale", "elevage", "bovin", "ovin", "rural", "tracteur", "agronomie",
        "semence", "sol", "irrigation", "recolter",
    },
    "droit_justice": {
        "droit", "juridique", "justice", "loi", "tribunal", "juge", "avocat", "proces", "peine",
        "jurisprudence", "juriste", "magistrat", "justice", "legal", "constitution", "decret",
        "code", "legislation", "condamnation",
    },
    "communication_medias": {
        "communication", "information", "media", "journal", "journalisme", "presse", "journaliste",
        "television", "radio", "internet", "message", "publication", "reportage", "emission",
        "audiovisuel", "communication", "publicite", "reseau", "information",
    },
    "energie_ressources": {
        "energie", "electricite", "centrale", "nucleaire", "renouvelable", "petrole", "gaz",
        "charbon", "solaire", "eolien", "hydraulique", "production", "consommation", "ressource",
        "combustible", "puissance", "thermique", "uranium", "barrage",
    },
    "architecture_urbanisme": {
        "architecture", "architecte", "batiment", "edifice", "construction", "monument", "maison",
        "urbanisme", "ville", "structure", "patrimoine", "monumental", "materiau", "chantier",
        "immeuble", "logement", "habitat", "restauration", "plan",
    },
    "langue_linguistique": {
        "langue", "langage", "linguistique", "linguiste", "grammaire", "vocabulaire", "mot",
        "parole", "ecriture", "dialecte", "idiome", "traduction", "syntaxe", "phonologie",
        "lexique", "francais", "anglais", "espagnol", "litterature",
    },
    "psychologie_esprit": {
        "psychologie", "psychologique", "psychologue", "psychiatrie", "psychiatre", "esprit",
        "pensee", "conscience", "memoire", "emotion", "comportement", "cerveau", "mental",
        "personnalite", "perception", "raisonnement", "intelligence", "sentiment",
    },
    "religions_croyances": {
        "religion", "dieu", "foi", "culte", "eglise", "temple", "priere", "theologie", "sacre",
        "christianisme", "islam", "judaisme", "bouddhisme", "hindouisme", "croyance", "rituel",
        "spiritualite", "religieux", "philosophie",
    },
    "tourisme_voyage": {
        "tourisme", "touriste", "voyage", "voyager", "voyageur", "visite", "visiter", "monument",
        "patrimoine", "hotel", "hebergement", "destination", "guide", "sejour", "vacances",
        "paysage", "culture", "transport", "decouverte",
    },
    "arts_visuels": {
        "art", "artiste", "peinture", "peintre", "sculpture", "sculpteur", "dessin", "tableau",
        "oeuvre", "musee", "galerie", "exposition", "photographie", "portrait", "paysage",
        "installation", "creation", "esthetique", "collection",
    },
})


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FRENCH_WORDS_PATH = os.path.join(DATA_DIR, "french_words.txt.gz")
SYNONYMS_PATH = os.path.join(DATA_DIR, "synonyms.json.gz")
VERB_LEMMAS_PATH = os.path.join(DATA_DIR, "verb_lemmas.json.gz")

FRENCH_DICTIONARY: Set[str] = set()
if os.path.exists(FRENCH_WORDS_PATH):
    try:
        with gzip.open(FRENCH_WORDS_PATH, "rt", encoding="utf-8") as _f:
            for _line in _f:
                _w = _line.strip()
                if _w:
                    FRENCH_DICTIONARY.add(normalize_text(_w))
    except Exception:
        pass

# Keep the curated proper-name list available even when a general spell-check
# lexicon omits names, demonyms, and uncommon French spellings.
FRENCH_DICTIONARY.update(normalize_text(word) for word in FRENCH_PROPER_NOUNS)
FRENCH_DICTIONARY.update(
    token
    for proper_name in FRENCH_PROPER_NOUNS
    for token in re.findall(r"[\w]+", normalize_text(proper_name), flags=re.UNICODE)
)

PROPER_NOUNS_PATH = os.path.join(DATA_DIR, "proper_nouns.txt.gz")
PROPER_NOUNS: Set[str] = set()
if os.path.exists(PROPER_NOUNS_PATH):
    try:
        with gzip.open(PROPER_NOUNS_PATH, "rt", encoding="utf-8") as _f:
            for _line in _f:
                _w = _line.strip()
                if _w:
                    PROPER_NOUNS.add(normalize_text(_w))
    except Exception:
        pass
FRENCH_DICTIONARY.update(PROPER_NOUNS)

_verb_index = {}
if os.path.exists(VERB_LEMMAS_PATH):
    try:
        with gzip.open(VERB_LEMMAS_PATH, "rt", encoding="utf-8") as _f:
            _verb_index = json.load(_f)
    except Exception:
        _verb_index = {}
for _form, _lemmas in _verb_index.items():
    _form_norm = normalize_text(_form)
    if not _form_norm:
        continue
    _candidate_lemmas = FRENCH_VERB_LEMMA_CANDIDATES.setdefault(_form_norm, set())
    for _lemma in _lemmas:
        _lemma_norm = normalize_text(_lemma)
        if _lemma_norm:
            _candidate_lemmas.add(_lemma_norm)
            FRENCH_VERB_LEMMAS.setdefault(_form_norm, _lemma_norm)

FRENCH_SYNONYMS: Dict[str, Set[str]] = {}
if os.path.exists(SYNONYMS_PATH):
    try:
        with gzip.open(SYNONYMS_PATH, "rt", encoding="utf-8") as _f:
            _raw_syns = json.load(_f)
            for _k, _v in _raw_syns.items():
                FRENCH_SYNONYMS[_k] = set(_v)
    except Exception:
        pass

# Build high-precision normalized bidirectional hardcoded synonyms dictionary
HARDCODED_SYNONYMS: Dict[str, Set[str]] = {}
for _k, _syns in HARDCODED_SYNONYMS_RAW.items():
    _kn = normalize_text(_k)
    if _kn not in HARDCODED_SYNONYMS:
        HARDCODED_SYNONYMS[_kn] = set()
    for _s in _syns:
        _sn = normalize_text(_s)
        if _sn and _sn != _kn:
            HARDCODED_SYNONYMS[_kn].add(_sn)
            if _sn not in HARDCODED_SYNONYMS:
                HARDCODED_SYNONYMS[_sn] = set()
            HARDCODED_SYNONYMS[_sn].add(_kn)

# Merge hardcoded curated synonyms into FRENCH_SYNONYMS
for _k, _syn_set in HARDCODED_SYNONYMS.items():
    if _k not in FRENCH_SYNONYMS:
        FRENCH_SYNONYMS[_k] = set()
    FRENCH_SYNONYMS[_k].update(_syn_set)

# Merge persisted API cached synonyms into FRENCH_SYNONYMS
for _k, _syn_list in SYNONYM_API._cache.items():
    _kn = normalize_text(_k)
    if _kn not in FRENCH_SYNONYMS:
        FRENCH_SYNONYMS[_kn] = set()
    for _s in _syn_list:
        _sn = normalize_text(_s)
        if _sn and _sn != _kn:
            FRENCH_SYNONYMS[_kn].add(_sn)

ETYMOLOGICAL_FAMILIES: Dict[str, Set[str]] = {
    "aqua_hydro": {"eau", "aquatique", "aquarium", "aqueduc", "aquarelle", "aqueux", "aquaculture", "hydrogene", "hydraulique", "hydratation", "hydrocarbure", "hydrographie", "hydrofuge"},
    "bio_vie": {"vie", "vivant", "vivante", "vital", "vitalite", "survivre", "survie", "revivre", "vitamine", "biologie", "biologique", "biologiste", "biographie", "biotope", "biosphere", "antibiotique", "biodiversite"},
    "chrono_temps": {"temps", "chronologie", "chronologique", "chronique", "chronometre", "anachronique", "synchroniser", "synchrone", "temporel", "temporaire", "intemporel", "contemporain"},
    "geo_terre": {"terre", "terrestre", "territoire", "territoires", "atterrir", "enterre", "geographie", "geographique", "geologie", "geologique", "geometrie", "geometrique", "geothermie", "geophysique", "geopolitique"},
    "tele_loin": {"loin", "television", "telephone", "telegraphe", "telescope", "telepathie", "telematique", "telecommande"},
    "astro_cosmos": {"astre", "etoile", "etoiles", "astronomie", "astronome", "astronomique", "astronaute", "astrophysique", "asteroide", "astrologie", "cosmos", "cosmique", "spatial", "spatiale", "espace"},
    "thermo_calor": {"chaleur", "chaud", "thermique", "thermometre", "thermostat", "thermonucleaire", "thermodynamique", "calorie", "calorique"},
    "demo_peuple": {"peuple", "population", "democratie", "democratique", "demographie", "demographique", "epidemie", "pandemie"},
    "psycho_esprit": {"esprit", "ame", "pensee", "psychologie", "psychologique", "psychiatrie", "psychiatre", "psychanalyse", "psychisme", "psychopathe"},
    "socio_societe": {"societe", "sociologie", "sociologique", "sociologue", "social", "socialisme", "socialiste", "sociable", "association"},
    "poli_cite": {"ville", "citoyen", "citoyenne", "politique", "politologue", "metropole", "metropolitain", "megapole", "police", "policier"},
    "milit_bell": {"guerre", "militaire", "militaires", "milice", "militariser", "militant", "belliqueux", "belligerant", "rebellion", "rebelle", "bataille", "combat", "armee", "soldat"},
    "jur_leg": {"loi", "droit", "juridique", "jurisprudence", "juriste", "juge", "justice", "legal", "legalite", "legitime", "legislation", "legislatif", "legislature", "privilege"},
    "mort_nec": {"mort", "morte", "mortel", "mortalite", "immortel", "immortalite", "necropole", "morbide", "funebre", "funerailles", "deces", "trepas"},
    "reg_roy": {"roi", "reine", "royal", "royale", "royaux", "royaume", "royaute", "regir", "regent", "regime", "regner", "regne", "monarque", "monarchie", "souverain", "souverainete"},
    "capit_chef": {"chef", "tete", "capitale", "decapiter", "capitaine", "capitulation", "capituler", "precipiter"},
    "urb_ville": {"ville", "urbain", "urbaine", "urbanisme", "urbaniste", "urbanite", "suburbain"},
    "rur_campagne": {"campagne", "rural", "rurale", "rusticite", "rustique"},
    "mar_nav": {"mer", "marin", "marine", "maritime", "navire", "navigation", "naval", "navigateur", "sous-marin", "nautique", "ocean", "oceanique"},
    "sol_heli": {"soleil", "solaire", "solaires", "heliocentrique", "insolation", "heliotherapie"},
    "lun_sel": {"lune", "lunaire", "lunaires", "lunatique", "clair-de-lune"},
    "noct_nuit": {"nuit", "nocturne", "noctambule"},
    "journ_diurn": {"jour", "journal", "journaliste", "journalisme", "journee", "diurne", "quotidien", "quotidienne"},
    "ocul_opt": {"oeil", "yeux", "oculaire", "oculiste", "optique", "opticien", "monocle", "binoculaire", "vision", "visible", "vue", "visuel"},
    "aer_aviat": {"air", "aerien", "aerienne", "aeroport", "aerodrome", "avion", "aviation", "aviateur", "aeronautique"},
    "ling_glot": {"langue", "linguistique", "linguiste", "polyglotte", "langage", "idiome", "dialecte"},
    "num_mon": {"argent", "monnaie", "monetaire", "finance", "financier", "numeraire", "banque", "bancaire"},
    "the_div": {"dieu", "deesse", "divin", "divine", "divinite", "religion", "religieux", "theologie", "atheisme", "pantheon", "culte"},
    "phil_amour": {"amour", "amitie", "philosophe", "philosophie", "philosophique", "philanthropie", "philologie"},
    "anthro_homo": {"homme", "humain", "humaine", "humanite", "anthropologie", "misanthrope", "philanthrope"},
    "morph_forme": {"forme", "morphologie", "metamorphose", "amorphe", "isomorphe"},
    "scrip_graph": {"ecrire", "ecriture", "ecrivain", "graphique", "graphisme", "biographie", "calligraphie", "orthographe", "manuscrit", "inscription", "description", "prescrire", "texte"},
    "phon_son": {"son", "voix", "telephone", "phonetique", "symphonie", "sonore", "acoustique", "resonance", "microphone"},
    "vid_vis": {"voir", "vue", "visible", "visuel", "vision", "television", "prevoir", "prevision", "revoir", "revue", "clairvoyant"},
    "aud_ecoute": {"entendre", "ecoute", "audio", "audience", "auditeur", "audible", "auditif", "auditorium"},
    "man_main": {"main", "manuel", "manuelle", "manuscrit", "manipuler", "manipulation", "manutention"},
    "equi_caval": {"cheval", "chevaux", "equestre", "equitation", "cavalier", "cavalerie"},
    "flor_fleur": {"fleur", "fleurs", "floral", "florale", "fleuriste", "floraison", "flore"},
    "arbor_silv": {"arbre", "arbres", "foret", "forets", "arboriculture", "arborescent", "sylvestre", "boise", "bois"},
    "carn_chair": {"chair", "viande", "carnivore", "carnage", "carnassier", "incarnation"},
    "herb_plante": {"herbe", "herbivore", "herbier", "herbeux", "herbeuse", "plante", "vegetal"},
    "igne_pyro": {"feu", "flamme", "ignifuge", "pyrotechnie", "incendie", "pyromane"},
    "frig_cryo": {"froid", "frigorifique", "refrigerateur", "cryogenie", "glacial", "glace"},
    "luc_lum": {"lumiere", "lucide", "lumineux", "lumineuse", "luminosite", "illuminer", "luciole"},
    "pater_pere": {"pere", "paternel", "paternelle", "paternite", "patrimoine", "patriarche", "patrie"},
    "mater_mere": {"mere", "maternel", "maternelle", "maternite", "matrice", "matriarche"},
    "frater_frere": {"frere", "fraternel", "fraternelle", "fraternite"},
    "scien_savoir": {"science", "scientifique", "scientifiques", "savoir", "connaissance", "chercheur", "recherche", "theorie"},
    "art_crea": {"art", "artiste", "artistique", "artisan", "artisanat", "oeuvre", "creation"},
    "litt_roman": {"livre", "lettre", "litterature", "litteraire", "auteur", "roman", "romans", "ecrit", "poesie"},
    "peintre_tableau": {"peinture", "peintre", "peindre", "tableau", "tableaux", "toile", "toiles"},
    "musique_orchestre": {"musique", "musicien", "musical", "musicale", "compositeur", "symphonie", "orchestre", "concert", "chanson", "chanteur"},
    "cinema_film": {"cinema", "film", "films", "cinematographique", "cineaste", "tournage", "realisateur", "acteur", "actrice"},
    "theatre_scene": {"theatre", "theatral", "dramatique", "dramaturge", "comedie", "comedien", "acteur", "actrice", "scene", "piece"},
    "medecine_soin": {"medecine", "medical", "medicale", "medecin", "soin", "soigner", "hopital", "clinique", "docteur", "sante", "therapie", "maladie"},
    "sport_jeu": {"sport", "sportif", "sportive", "athletisme", "athlete", "competition", "champion", "championnat", "stade", "match", "equipe", "joueur"},
    "architec_monu": {"architecture", "architecte", "architectural", "edifice", "batiment", "construction", "construire", "monument", "tour", "cathedrale", "palais", "chateau"},
}

# Merge expanded etymological families into ETYMOLOGICAL_FAMILIES
for _fid, _words in EXPANDED_ETYMOLOGICAL_FAMILIES.items():
    if _fid not in ETYMOLOGICAL_FAMILIES:
        ETYMOLOGICAL_FAMILIES[_fid] = set()
    ETYMOLOGICAL_FAMILIES[_fid].update(_words)

ETYMOLOGICAL_INDEX: Dict[str, str] = {}
for _fid, _words in ETYMOLOGICAL_FAMILIES.items():
    for _w in _words:
        _wn = normalize_text(_w)
        if _wn:
            ETYMOLOGICAL_INDEX[_wn] = _fid


def is_valid_french_word(word: str, article_words: Optional[Set[str]] = None) -> bool:
    """Verifies whether a word is valid French, exists in dictionaries, is numeric, or is in the article."""
    if not word:
        return False
    w_clean = clean_guess(word)
    if not w_clean:
        return False
    w_norm = normalize_text(w_clean)
    if not w_norm:
        return False

    # 1. Digits and numbers (e.g. 1945, 1889, 42)
    if w_norm.isdigit():
        return True

    # 2. Roman numerals (e.g. xix, xiv, vii)
    if len(w_norm) <= 6 and re.fullmatch(r"[ivxlcdm]+", w_norm):
        return True

    # 3. Essential stopwords
    if w_norm in STOPWORDS_EXACT:
        return True

    # 4. Context words in target article (permits proper names, places, foreign terms present in text)
    if article_words:
        if w_norm in article_words or w_clean.lower() in article_words:
            return True

    # 5. Full French words dictionary + 80,000+ proper nouns
    if w_norm in FRENCH_DICTIONARY or w_clean.lower() in FRENCH_DICTIONARY:
        return True

    # 6. Proper nouns index (cities, countries, persons, historical entities)
    if w_norm in PROPER_NOUNS or w_clean.lower() in PROPER_NOUNS:
        return True

    # 7. Capitalized proper noun candidate (e.g. Einstein, Picasso, Zidane, Churchill...)
    if len(w_clean) >= 2 and w_clean[0].isupper() and all(c.isalpha() or c in "'- " for c in w_clean):
        return True

    # 8. Conjugated / irregular verbs & lemma
    if w_norm in FRENCH_VERB_LEMMAS:
        return True

    # 9. Etymological and irregular families
    if w_norm in ETYMOLOGICAL_INDEX or w_norm in FRENCH_IRREGULAR_FAMILIES:
        return True

    # 10. Synonyms index
    if w_norm in FRENCH_SYNONYMS:
        return True

    # 11. Morphological stem found in dictionary
    stem = stem_french(w_norm)
    if stem and (stem in FRENCH_DICTIONARY or stem in FRENCH_SYNONYMS or stem in PROPER_NOUNS):
        return True

    return False


# Precomputed stems for WORD_ASSOCIATIONS
ASSOCIATION_STEMS: Dict[str, Dict[str, int]] = {}
for _w, _assocs in WORD_ASSOCIATIONS.items():
    _w_stem = stem_french(_w)
    if _w_stem not in ASSOCIATION_STEMS:
        ASSOCIATION_STEMS[_w_stem] = {}
    for _a_word, _score in _assocs.items():
        _a_stem = stem_french(_a_word)
        ASSOCIATION_STEMS[_w_stem][_a_stem] = max(ASSOCIATION_STEMS[_w_stem].get(_a_stem, 0), _score)

# Known false homographs and coincidental stems that must NEVER match
FALSE_HOMOGRAPHS = {
    ("banc", "banque"), ("banque", "banc"),
    ("banc", "bancaire"), ("bancaire", "banc"),
    ("banc", "banquier"), ("banquier", "banc"),
    ("conte", "continuer"), ("continuer", "conte"),
    ("paner", "panique"), ("panique", "paner"),
    ("mer", "mere"), ("mere", "mer"),
    ("pere", "perdre"), ("perdre", "pere"),
    ("mort", "morceau"), ("morceau", "mort"),
    ("port", "porte"), ("porte", "port"),
    ("pont", "ponte"), ("ponte", "pont"),
    ("car", "carte"), ("carte", "car"),
    ("vol", "volee"), ("volee", "vol"),
}

# Rich conceptual domain taxonomy with core & extended semantic relations
CONCEPT_DOMAINS = [
    # Sports & Games
    {
        "core": {"football", "foot", "ballon", "match", "joueur", "stade", "equipe", "but", "gardien", "arbitre"},
        "extended": {"championnat", "coupe", "ligue", "tournoi", "penalty", "prolongation", "mi-temps", "pelouse", "buteur", "entraineur", "club"},
        "base_score": 82.0
    },
    {
        "core": {"tennis", "raquette", "balle", "court", "filet", "service", "set", "tournoi"},
        "extended": {"grand-chelem", "roland-garros", "wimbledon", "arbitre", "joueur", "match"},
        "base_score": 82.0
    },
    {
        "core": {"sport", "athlete", "competition", "championnat", "champion", "medaille", "olympique", "jeu", "stade", "entrainement"},
        "extended": {"football", "rugby", "basket", "tennis", "natation", "cyclisme", "athletisme", "course", "equipe", "match"},
        "base_score": 75.0
    },
    # Furniture & Home
    {
        "core": {"table", "chaise", "meuble", "fauteuil", "tabouret", "bureau", "buffet", "armoire", "commode", "tiroir"},
        "extended": {"salon", "salle", "cuisine", "mobilier", "bois", "siege", "etagere"},
        "base_score": 83.0
    },
    {
        "core": {"lit", "matelas", "sommier", "oreiller", "couverture", "draps", "chambre", "coucher", "dormir", "sommeil"},
        "extended": {"meuble", "nuit", "reve", "reveil", "couette"},
        "base_score": 83.0
    },
    # Food, Bakery & Agriculture
    {
        "core": {"pain", "boulangerie", "boulanger", "baguette", "farine", "four", "ble", "pate", "croissant", "patisserie"},
        "extended": {"levure", "mie", "croute", "fournil", "brioche", "biscuit", "gateau", "artisan", "nourriture"},
        "base_score": 84.0
    },
    {
        "core": {"viande", "boucherie", "boucher", "boeuf", "porc", "veau", "agneau", "volaille", "poulet", "charcuterie"},
        "extended": {"abattoir", "nourriture", "steak", "cotelette", "jambon", "saucisse"},
        "base_score": 82.0
    },
    {
        "core": {"pomme", "poire", "fruit", "orange", "banane", "fraise", "raisin", "cerise", "peche", "abricot", "citron"},
        "extended": {"verger", "arbre", "jus", "sucre", "vitamine", "cueillette", "panier", "legume"},
        "base_score": 83.0
    },
    {
        "core": {"fromage", "lait", "beurre", "creme", "vache", "chevre", "brebis", "laiterie", "fromagerie"},
        "extended": {"ferme", "elevage", "traite", "pasteurise", "yaourt", "pate"},
        "base_score": 83.0
    },
    {
        "core": {"cafe", "the", "tasse", "boisson", "sucre", "lait", "grain", "expresso", "percolateur", "chocolat"},
        "extended": {"matin", "petit-dejeuner", "bistro", "pause", "serveur", "bar"},
        "base_score": 83.0
    },
    # Health & Medicine
    {
        "core": {"medecin", "docteur", "hopital", "clinique", "patient", "maladie", "soin", "soigner", "traitement", "medicament", "ordonnance", "infirmier", "infirmiere", "chirurgien"},
        "extended": {"sante", "diagnostic", "guerison", "urgence", "chambre", "visite", "therapie", "consultation", "blessure", "fievre", "virus", "bacterie", "vaccin"},
        "base_score": 84.0
    },
    # Transportation & Vehicles
    {
        "core": {"voiture", "automobile", "auto", "vehicule", "moteur", "roue", "pneu", "volant", "conducteur", "chauffeur", "route", "autoroute"},
        "extended": {"frein", "vitesse", "carburant", "essence", "diesel", "garage", "mecanique", "carrosserie", "permis", "circulation", "traffic"},
        "base_score": 83.0
    },
    {
        "core": {"train", "gare", "rail", "chemin", "locomotive", "wagon", "voie", "conducteur", "voyageur", "quai", "ligne", "tgv"},
        "extended": {"sncf", "reseau", "billet", "trajet", "vitesse", "electrique", "transport"},
        "base_score": 84.0
    },
    {
        "core": {"avion", "aeroport", "vol", "pilote", "aviation", "voler", "piste", "aile", "aerien", "passager", "compagnie"},
        "extended": {"reacteur", "cockpit", "terminal", "voyage", "altitude", "atterrissage", "decollage", "cie"},
        "base_score": 84.0
    },
    {
        "core": {"bateau", "navire", "port", "marin", "mer", "ocean", "voilier", "capitaine", "equipage", "navigation", "naviguer"},
        "extended": {"coque", "voile", "mouille", "ancre", "flotte", "maritime", "peche", "pecheur", "babord", "tribord"},
        "base_score": 83.0
    },
    # Clothing & Body
    {
        "core": {"chaussure", "pied", "chaussette", "soulier", "bottes", "lacet", "semelle", "talon", "pantoufle"},
        "extended": {"marche", "chausser", "cuir", "pointure", "vetement"},
        "base_score": 83.0
    },
    {
        "core": {"vetement", "habit", "chemise", "pantalon", "robe", "jupe", "manteau", "veste", "tissu", "costume"},
        "extended": {"mode", "couture", "taille", "soie", "coton", "laine", "bouton", "manche"},
        "base_score": 82.0
    },
    # Nature & Astronomy
    {
        "core": {"arbre", "foret", "bois", "tronc", "branche", "feuille", "racine", "chene", "sapin", "pin", "vegetal"},
        "extended": {"nature", "ecorce", "forets", "clairiere", "faune", "flore", "sylvestre"},
        "base_score": 85.0
    },
    {
        "core": {"fleur", "plante", "petale", "jardin", "rose", "tulipe", "tige", "feuille", "parfum", "botanique"},
        "extended": {"bouquet", "jardinier", "bourgeon", "nature", "herbe", "semence", "graine"},
        "base_score": 84.0
    },
    {
        "core": {"soleil", "lune", "etoile", "ciel", "terre", "planete", "lumiere", "espace", "univers", "cosmos", "galaxie", "orbite", "satellite"},
        "extended": {"astronomie", "astronome", "telescope", "jour", "nuit", "rayon", "chaleur", "gravite", "etoiles", "planetes"},
        "base_score": 82.0
    },
    {
        "core": {"pluie", "nuage", "orage", "eau", "averse", "tempete", "vent", "eclair", "tonnerre", "meteo", "temps", "parapluie"},
        "extended": {"goutte", "ciel", "precipitation", "inondation", "humide", "brume", "brouillard"},
        "base_score": 84.0
    },
    {
        "core": {"neige", "hiver", "glace", "froid", "flocon", "gel", "givre", "glacier", "avalanche", "ski"},
        "extended": {"temperature", "saison", "blizzard", "montagne", "piste", "patinage"},
        "base_score": 84.0
    },
    # Science & Matter
    {
        "core": {"atome", "molecule", "electron", "proton", "neutron", "noyau", "matiere", "particule", "charge", "physique", "chimie"},
        "extended": {"liaison", "quantique", "element", "masse", "energie", "rayonnement", "orbital"},
        "base_score": 85.0
    },
    {
        "core": {"cellule", "organisme", "adn", "gene", "chromosome", "genome", "proteine", "membrane", "biologie"},
        "extended": {"tissu", "organe", "noyau", "division", "mutations", "genetique", "vivant"},
        "base_score": 85.0
    },
    # Education
    {
        "core": {"ecole", "professeur", "eleve", "classe", "cours", "enseignant", "enseignement", "scolaire", "etudiant", "college", "lycee", "universite"},
        "extended": {"tableau", "cahier", "livre", "examen", "note", "diplome", "apprentissage", "etude", "scolarite", "recre", "directeur"},
        "base_score": 84.0
    },
    # Animals
    {
        "core": {"chien", "chat", "chiot", "chaton", "canin", "felin", "aboiement", "miaulement", "animal", "compagnie", "maitre"},
        "extended": {"veterinaire", "laisse", "croquette", "poil", "fourrure", "pattes", "queue"},
        "base_score": 83.0
    },
    # Arts & Music
    {
        "core": {"peintre", "peinture", "tableau", "toile", "pinceau", "artiste", "musee", "galerie", "portrait", "paysage", "couleur", "exposition"},
        "extended": {"art", "dessin", "sculpteur", "sculpture", "chef-d-oeuvre", "atelier", "beaux-arts"},
        "base_score": 85.0
    },
    {
        "core": {"musique", "musicien", "chanson", "chanteur", "chanteuse", "album", "concert", "instrument", "piano", "guitare", "violon", "orchestre", "symphonie", "compositeur", "corde", "touche", "clavier"},
        "extended": {"partition", "son", "rythme", "melodie", "groupe", "opera", "harmonie", "note", "voix", "archet", "manche"},
        "base_score": 85.0
    },
    # Literature
    {
        "core": {"livre", "roman", "auteur", "ecrivain", "litterature", "page", "chapitre", "texte", "poesie", "poeme", "editeur", "edition", "bibliotheque"},
        "extended": {"histoire", "recit", "personnage", "tome", "volume", "lecture", "lecteur", "plume"},
        "base_score": 85.0
    },
    # Politics & History
    {
        "core": {"president", "republique", "gouvernement", "ministre", "premier-ministre", "election", "elysee", "etat", "politique", "vote", "loi", "parlement", "assemblee", "senat"},
        "extended": {"mandat", "constitution", "democratie", "campagne", "pouvoir", "citoyen", "depute", "senateur", "regime"},
        "base_score": 84.0
    },
    {
        "core": {"roi", "reine", "royaume", "monarchie", "couronne", "trone", "prince", "princesse", "dynastie", "regne", "souverain", "chateau", "palais"},
        "extended": {"royal", "noble", "noblesse", "cour", "heritier", "succession", "empire", "empereur"},
        "base_score": 86.0
    },
    {
        "core": {"guerre", "paix", "bataille", "armee", "soldat", "militaire", "combat", "conflit", "victoire", "defaite", "traite", "arme", "troupes"},
        "extended": {"invasion", "ennemi", "front", "attaque", "defense", "tranchee", "colonel", "general", "capitaine", "guerrier"},
        "base_score": 84.0
    },
    {
        "core": {"revolution", "bastille", "monarchie", "republique", "guillotine", "peuple", "insurrection", "revolte", "1789"},
        "extended": {"liberte", "egalite", "fraternite", "sans-culottes", "convention", "terreur", "paris", "citoyen"},
        "base_score": 84.0
    }
]

# Fast reverse index for concept domains
CONCEPT_LOOKUP: Dict[str, List[Tuple[dict, str]]] = {}
for cd in CONCEPT_DOMAINS:
    for w in cd["core"]:
        wn = normalize_text(w)
        CONCEPT_LOOKUP.setdefault(wn, []).append((cd, "core"))
    for w in cd["extended"]:
        wn = normalize_text(w)
        CONCEPT_LOOKUP.setdefault(wn, []).append((cd, "extended"))


def calculate_numeric_proximity(g_val: int, t_val: int) -> float:
    """
    Calculates proximity between two numbers (specifically years/dates).
    Returns a score between 48.0 and 99.0 if within 100 units of each other,
    or 0.0 if too far.
    """
    diff = abs(g_val - t_val)
    if diff == 0:
        return 100.0

    # Year comparison:
    # Applies if both numbers are in the historical year range (>= 100 and <= 2500)
    # or both are 4-digit numbers (1000 to 9999).
    is_year_range = (
        (100 <= g_val <= 2500 and 100 <= t_val <= 2500) or
        (1000 <= g_val <= 9999 and 1000 <= t_val <= 9999)
    )

    if is_year_range:
        MAX_DIFF = 100
        if diff <= MAX_DIFF:
            score = 99.0 - (diff - 1) * (99.0 - 48.0) / (MAX_DIFF - 1)
            return round(score, 1)
        return 0.0

    return 0.0


def calculate_proximity(guess: str, target: str, context_words: Optional[Set[str]] = None) -> float:
    """
    Calculates a continuous, organic semantic and morphological proximity score between 0.0 and 100.0.
    100.0 = exact match
    94-98 = curated high-confidence direct synonym / lexical equivalent
    90-94 = standard thesaurus synonym or direct morphological family
    82-92 = high-affinity domain association (e.g. football/ballon, table/chaise, medecin/hopital)
    60-82 = shared 2nd-degree semantic overlap (Adamic-Adar specificity weighted)
    < 48  = unrelated (returns 0.0)
    """
    g_clean = clean_guess(guess)
    g_norm = normalize_text(g_clean)
    t_norm = normalize_text(target)

    if not g_norm or not t_norm:
        return 0.0

    if check_match(g_norm, t_norm):
        return 100.0

    # Number / date proximity handling:
    if g_norm.isdigit() and t_norm.isdigit():
        return calculate_numeric_proximity(int(g_norm), int(t_norm))
    if g_norm.isdigit() or t_norm.isdigit():
        return 0.0

    # 0. Stopword safeguard: grammatical words & prepositions never produce semantic heat
    if g_norm in STOPWORDS_EXACT or t_norm in STOPWORDS_EXACT:
        return 0.0

    # False homographs safety protection (e.g. banc vs banque, mer vs mere)
    if (g_norm, t_norm) in FALSE_HOMOGRAPHS or (t_norm, g_norm) in FALSE_HOMOGRAPHS:
        return 0.0

    t_forms = {t_norm} | get_singular_forms(t_norm)
    g_forms = {g_norm} | get_singular_forms(g_norm)

    # 1. Curated Hardcoded Synonyms (highest fidelity, continuous scoring)
    g_hard = HARDCODED_SYNONYMS.get(g_norm, set())
    t_hard = HARDCODED_SYNONYMS.get(t_norm, set())
    is_hard_mutual = any(tf in g_hard for tf in t_forms) and any(gf in t_hard for gf in g_forms)
    is_hard_one_way = any(tf in g_hard for tf in t_forms) or any(gf in t_hard for gf in g_forms)

    if is_hard_mutual:
        len_ratio = min(len(g_norm), len(t_norm)) / max(len(g_norm), len(t_norm))
        return round(94.0 + 3.5 * len_ratio, 1)
    if is_hard_one_way:
        len_ratio = min(len(g_norm), len(t_norm)) / max(len(g_norm), len(t_norm))
        return round(90.0 + 3.5 * len_ratio, 1)

    # 2. General French Thesaurus Synonyms
    g_syns = FRENCH_SYNONYMS.get(g_norm, set())
    t_syns = FRENCH_SYNONYMS.get(t_norm, set())
    is_syn_mutual = any(tf in g_syns for tf in t_forms) and any(gf in t_syns for gf in g_forms)
    is_syn_one_way = any(tf in g_syns for tf in t_forms) or any(gf in t_syns for gf in g_forms)

    if is_syn_mutual:
        len_ratio = min(len(g_norm), len(t_norm)) / max(len(g_norm), len(t_norm))
        return round(91.0 + 3.0 * len_ratio, 1)
    if is_syn_one_way:
        len_ratio = min(len(g_norm), len(t_norm)) / max(len(g_norm), len(t_norm))
        return round(86.0 + 3.5 * len_ratio, 1)

    # 3. High-Affinity Concept Domain Associations (sports, objects, trades, health, science, etc.)
    g_concepts = CONCEPT_LOOKUP.get(g_norm, [])
    t_concepts = CONCEPT_LOOKUP.get(t_norm, [])
    best_concept_score = 0.0

    for cd_g, role_g in g_concepts:
        for cd_t, role_t in t_concepts:
            if cd_g is cd_t:
                base = cd_g["base_score"]
                if role_g == "core" and role_t == "core":
                    len_ratio = min(len(g_norm), len(t_norm)) / max(len(g_norm), len(t_norm))
                    score = base + 4.0 + 3.0 * len_ratio
                elif role_g == "core" or role_t == "core":
                    score = base - 2.0
                else:
                    score = base - 8.0
                if score > best_concept_score:
                    best_concept_score = score

    if best_concept_score >= 60.0:
        return round(best_concept_score, 1)

    # 4. Curated Word Associations (direct)
    if g_norm in WORD_ASSOCIATIONS and t_norm in WORD_ASSOCIATIONS[g_norm]:
        return float(WORD_ASSOCIATIONS[g_norm][t_norm])
    if t_norm in WORD_ASSOCIATIONS and g_norm in WORD_ASSOCIATIONS[t_norm]:
        return float(WORD_ASSOCIATIONS[t_norm][g_norm])

    # 5. Morphological family / Stem analysis with homograph safety
    g_stem = stem_french(g_norm)
    t_stem = stem_french(t_norm)

    if g_stem == t_stem and len(g_stem) >= 4:
        len_ratio = min(len(g_norm), len(t_norm)) / max(len(g_norm), len(t_norm))
        return round(91.0 + 4.0 * len_ratio, 1)
    elif g_stem == t_stem and len(g_stem) == 3:
        if g_norm[:3] == t_norm[:3] and not ((g_norm, t_norm) in FALSE_HOMOGRAPHS or (t_norm, g_norm) in FALSE_HOMOGRAPHS):
            return 91.0

    # Etymological Root Families (curated Greek/Latin root clusters)
    g_etym = ETYMOLOGICAL_INDEX.get(g_norm)
    t_etym = ETYMOLOGICAL_INDEX.get(t_norm)
    if g_etym and t_etym and g_etym == t_etym:
        return 88.0

    # Prefix stripping check (e.g. astrophysique vs physique, neuroscience vs science)
    g_nopre = strip_prefix(g_norm)
    t_nopre = strip_prefix(t_norm)
    if g_nopre != g_norm or t_nopre != t_norm:
        if stem_french(g_nopre) == stem_french(t_nopre) and len(g_nopre) >= 4 and len(t_nopre) >= 4:
            return 89.5

        g_etym_nopre = ETYMOLOGICAL_INDEX.get(g_nopre)
        t_etym_nopre = ETYMOLOGICAL_INDEX.get(t_nopre)
        if g_etym_nopre and t_etym_nopre and g_etym_nopre == t_etym_nopre:
            return 86.0

    # 6. Shared 2nd-degree synonyms with Adamic-Adar specificity weighting
    if g_syns and t_syns:
        meaningful_shared = (g_syns & t_syns) - GENERIC_BRIDGE_WORDS
        if len(meaningful_shared) >= 1:
            total_weight = 0.0
            for shared_w in meaningful_shared:
                deg = len(FRENCH_SYNONYMS.get(shared_w, set()))
                weight = 1.0 / math.log2(max(deg, 2))
                total_weight += weight

            if total_weight >= 0.35:
                score = 58.0 + 24.0 * min(total_weight / 2.5, 1.0)
                return round(score, 1)

    # 7. Direct Thematic Cluster membership (exact word verification, no loose stem collision)
    for cluster in THEMATIC_CLUSTERS.values():
        if g_norm in cluster and t_norm in cluster:
            return 64.0

    return 0.0
