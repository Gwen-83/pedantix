import gzip
import json
import math
import os
import re
from typing import Dict, Set, Tuple, List

def normalize_text(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    text = text.lower().strip()
    nfkd = unicodedata.normalize('NFD', text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != 'Mn')
    stripped = stripped.replace("œ", "oe").replace("æ", "ae")
    return stripped

with gzip.open('app/data/synonyms.json.gz', 'rt') as f:
    FRENCH_SYNONYMS = {k: set(v) for k, v in json.load(f).items()}

from app.nlp import (
    HARDCODED_SYNONYMS,
    WORD_ASSOCIATIONS,
    GENERIC_BRIDGE_WORDS,
    STOPWORDS_EXACT,
    check_match,
    stem_french,
    strip_prefix,
    get_singular_forms,
    calculate_numeric_proximity
)

# Known false homographs and coincidental stems
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
    # Food & Bakery
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
    # Transportation
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
    # Clothing & Accessories
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

CONCEPT_LOOKUP: Dict[str, List[Tuple[dict, str]]] = {}
for cd in CONCEPT_DOMAINS:
    for w in cd["core"]:
        wn = normalize_text(w)
        CONCEPT_LOOKUP.setdefault(wn, []).append((cd, "core"))
    for w in cd["extended"]:
        wn = normalize_text(w)
        CONCEPT_LOOKUP.setdefault(wn, []).append((cd, "extended"))

def new_calculate_proximity(guess: str, target: str) -> float:
    g_norm = normalize_text(guess)
    t_norm = normalize_text(target)

    if not g_norm or not t_norm:
        return 0.0

    if check_match(g_norm, t_norm):
        return 100.0

    if g_norm.isdigit() and t_norm.isdigit():
        return calculate_numeric_proximity(int(g_norm), int(t_norm))
    if g_norm.isdigit() or t_norm.isdigit():
        return 0.0

    if g_norm in STOPWORDS_EXACT or t_norm in STOPWORDS_EXACT:
        return 0.0

    if (g_norm, t_norm) in FALSE_HOMOGRAPHS or (t_norm, g_norm) in FALSE_HOMOGRAPHS:
        return 0.0

    t_forms = {t_norm} | get_singular_forms(t_norm)
    g_forms = {g_norm} | get_singular_forms(g_norm)

    # 1. Curated Hardcoded Synonyms (highest fidelity)
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

    # 3. Enhanced Concept Domain Associations
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

    # Prefix stripping check
    g_nopre = strip_prefix(g_norm)
    t_nopre = strip_prefix(t_norm)
    if g_nopre != g_norm or t_nopre != t_norm:
        if stem_french(g_nopre) == stem_french(t_nopre) and len(g_nopre) >= 4 and len(t_nopre) >= 4:
            return 89.5

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

    return 0.0

if __name__ == "__main__":
    pairs = [
        ('electron', 'atome'),
        ('cellule', 'adn'),
        ('etoile', 'galaxie'),
        ('revolution', 'bastille'),
        ('pomme', 'fruit'),
        ('fromage', 'vache'),
        ('cafe', 'tasse'),
        ('chaussure', 'pied'),
        ('pluie', 'parapluie'),
        ('guitare', 'corde'),
        ('piano', 'touche'),
        ('football', 'ballon'),
        ('table', 'chaise'),
        ('pain', 'boulangerie'),
        ('banc', 'banque'),
    ]
    for w1, w2 in pairs:
        print(f'{w1} vs {w2}: {new_calculate_proximity(w1, w2)}%')
