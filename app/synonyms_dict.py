"""
Comprehensive hardcoded French synonyms, etymological root families,
generic polysemy filters, and stopword isolation for Pédantix.
"""

from typing import Dict, Set

# Ubiquitous polysemic words that appear in hundreds of dictionary entries.
# These MUST NOT be used to bridge 2nd-degree synonyms (they cause false positives like sur -> net, pur -> blanc).
GENERIC_BRIDGE_WORDS: Set[str] = {
    "net", "pur", "fort", "fin", "delicat", "calme", "ferme", "force", "brillant",
    "trouble", "aise", "mesure", "accord", "juste", "attaque", "dur", "charge",
    "fatigue", "eclat", "regle", "extraordinaire", "casser", "annonce", "manifeste",
    "arranger", "montrer", "attaquer", "epreuve", "battre", "couper", "ouverture",
    "reunion", "assure", "grand", "petit", "bon", "beau", "clair", "vrai", "doux",
    "chose", "point", "etat", "forme", "piece", "effet", "fond", "ordre", "part",
    "terme", "maniere", "facade", "faible", "haut", "bas", "plein", "vide", "simple",
    "grave", "leger", "court", "long", "large", "droit", "franc", "froid", "chaud",
    "vif", "sombre", "libre", "secret", "fixer", "porter", "tenir", "passer", "mettre",
    "prendre", "tirer", "toucher", "traiter", "poser", "pousser", "rendre", "laisser",
    "garder", "donner", "servir", "action", "mouvement", "marche", "sens", "vue",
    "ligne", "cote", "bout", "face", "plan", "tour", "air", "esprit", "matiere"
}

# Exhaustive French stop words, prepositions, conjunctions, determiners, pronouns,
# and grammatical particles that must NEVER have semantic proximity with lexical words.
EXPANDED_STOPWORDS: Set[str] = {
    # Articles
    "le", "la", "les", "l",
    "un", "une", "des",
    "du", "de", "d",
    # Demonstratives
    "ce", "cet", "cette", "ces", "ceci", "cela", "ca",
    # Possessives
    "mon", "ton", "son", "ma", "ta", "sa", "mes", "tes", "ses",
    "notre", "votre", "nos", "vos", "leur", "leurs",
    # Personal pronouns & particles
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "te", "se", "ne", "en", "y",
    "lui", "eux", "moi", "toi", "soi",
    # Relative & interrogative pronouns
    "qui", "que", "quoi", "dont", "ou", "lequel", "laquelle", "lesquels", "lesquelles",
    "auquel", "auxquels", "auxquelles", "duquel", "desquels", "desquelles",
    # Conjunctions
    "et", "ou", "ni", "mais", "donc", "or", "car", "soit", "sinon",
    # Prepositions
    "a", "au", "aux",
    "dans", "par", "pour", "sur", "sous", "avec", "sans", "chez",
    "vers", "entre", "jusque", "jusqu", "hors", "selon", "malgre",
    "pendant", "depuis", "contre", "envers", "parmi", "outre", "devant", "derriere",
    # Grammatical adverbs & quantifiers
    "pas", "plus", "non", "si", "comme", "quand", "lorsque", "puisque", "quoique",
    "tres", "trop", "peu", "bien", "aussi", "encore", "deja", "meme", "memes",
    "tout", "tous", "toute", "toutes", "autre", "autres", "ici", "la",
    "alors", "ainsi", "tant", "tel", "telle", "tels", "telles",
    "assez", "beaucoup", "combien", "comment", "pourquoi", "toujours", "jamais"
}

# Massive, curated hardcoded French synonyms and direct semantic relations.
# Mapped bidirectionally during registration.
HARDCODED_SYNONYMS_RAW: Dict[str, Set[str]] = {
    # --- Montagnes, Relief & Géographie alpine ---
    "mont": {
        "montagne", "sommet", "pic", "cime", "creme", "aiguille", "massif", "alpes",
        "pyrenees", "colline", "hauteur", "elevation", "monticule", "relief", "altitude",
        "versant", "crete", "butte", "morne", "puy", "orographie"
    },
    "montagne": {
        "mont", "sommet", "pic", "cime", "chaine", "massif", "alpes", "pyrenees",
        "himalaya", "relief", "cordillere", "alpinisme", "altitude", "hauteur",
        "roche", "vallee", "glacier", "versant", "aiguille", "crevasse"
    },
    "sommet": {
        "mont", "montagne", "pic", "cime", "faite", "zenith", "apex", "apogee",
        "pointe", "aiguille", "hauteur", "altitude", "crete", "haut", "pinnacle"
    },
    "pic": {
        "mont", "montagne", "sommet", "cime", "aiguille", "pointe", "dent", "arete", "creme"
    },
    "cime": {
        "mont", "montagne", "sommet", "pic", "aiguille", "faite", "pointe", "hauteur"
    },
    "colline": {
        "mont", "montagne", "monticule", "coteau", "butte", "eminence", "tertre", "vallon"
    },
    "vallee": {
        "montagne", "gorge", "ravin", "vallon", "combe", "plaine", "canyon", "bassin", "val"
    },
    "glacier": {
        "glace", "neige", "crevasse", "serac", "moraine", "banquise", "montagne", "inlandsis",
        "calotte", "alpes", "froid", "glacial", "neve"
    },
    "alpes": {
        "montagne", "mont", "massif", "chaine", "sommet", "alpin", "alpine", "alpinisme",
        "glacier", "mont-blanc", "suisse", "france", "italie", "autriche"
    },
    "pyrenees": {
        "montagne", "mont", "massif", "chaine", "sommet", "espagne", "france"
    },
    "himalaya": {
        "montagne", "mont", "massif", "chaine", "sommet", "everest", "tibet", "nepal"
    },
    "alpinisme": {
        "montagne", "escalade", "ascension", "grimpe", "alpiniste", "varappe", "sommet", "cordee"
    },
    "volcan": {
        "cratere", "lave", "magma", "eruption", "seisme", "pyroclaste", "cendres", "montagne"
    },

    # --- Couleurs & Nuances ---
    "blanc": {
        "neige", "neigeux", "immacule", "ivoire", "blancheur", "blanchatre", "craie",
        "albatre", "argente", "pale", "eburneen", "lacte", "laiteux", "crayeux"
    },
    "neige": {
        "blanc", "blancheur", "glace", "flocon", "glacier", "hiver", "poudreuse",
        "avalanche", "neigeux", "givre", "blizzard", "neve", "igloo"
    },
    "glace": {
        "glacier", "neige", "froid", "glacial", "gel", "banquise", "givre", "verglas",
        "glacon", "igloo", "congeler"
    },
    "noir": {
        "sombre", "obscur", "ebene", "tenebres", "noirceur", "noircir", "charbon", "opaque", "encre"
    },
    "rouge": {
        "vermeil", "ecarlate", "pourpre", "carmin", "rubis", "grenat", "roussatre", "rougi", "sang"
    },
    "bleu": {
        "azur", "azurite", "cyan", "indigo", "saphir", "outremer", "bleute", "ciel", "marine"
    },
    "vert": {
        "emeraude", "olive", "verdoyant", "verdi", "chlorophylle", "verdoiement", "menthe"
    },
    "jaune": {
        "dore", "or", "ambre", "citron", "ocre", "blond", "blonde", "safran"
    },
    "gris": {
        "argente", "cendre", "plomb", "ardoise", "grisant", "grise"
    },
    "or": {
        "dore", "jaune", "orfevre", "metallique", "lingot", "pepite", "richesse"
    },
    "argent": {
        "argente", "gris", "metal", "monnaie", "finance", "lingot"
    },

    # --- Eau, Mers, Rivières & Nature liquide ---
    "mer": {
        "ocean", "onde", "eau", "flot", "large", "marine", "maree", "abysse",
        "cote", "littoral", "plage", "rivage", "maritime", "golfe", "baie"
    },
    "ocean": {
        "mer", "abysse", "large", "flot", "eau", "atlantique", "pacifique", "indien",
        "arctique", "antarctique", "maritime", "oceanique"
    },
    "eau": {
        "onde", "liquide", "source", "flot", "mer", "fleuve", "riviere", "lac", "pluie", "boisson", "aquatique"
    },
    "fleuve": {
        "riviere", "cours-d-eau", "affluent", "estuaire", "delta", "flot", "ruisseau", "embouchure", "seine", "rhone", "loire", "rhin"
    },
    "riviere": {
        "fleuve", "ruisseau", "cours-d-eau", "affluent", "torrent", "berge", "rive"
    },
    "lac": {
        "etang", "bassin", "lagune", "marais", "reservoir", "plan-d-eau", "nappe"
    },
    "ile": {
        "archipel", "ilot", "atoll", "insulaire", "terre", "recif"
    },
    "foret": {
        "bois", "jungle", "bocage", "futaie", "bosquet", "boisement", "arbre", "vegetation", "selve"
    },
    "arbre": {
        "foret", "bois", "plante", "tronc", "branche", "feuille", "racine", "arbuste", "chene", "sapin", "pin"
    },
    "plante": {
        "vegetal", "flore", "herbe", "fleur", "arbre", "arbuste", "botanique"
    },
    "fleur": {
        "plante", "floraison", "bouquet", "petale", "rose", "tulipe", "orchidee", "floral"
    },
    "desert": {
        "sable", "dune", "erg", "oasis", "aride", "sahara", "secheresse"
    },

    # --- Espace, Ciel & Astronomie ---
    "espace": {
        "cosmos", "univers", "galaxie", "spatial", "etoile", "planete", "orbite", "vide", "astronomie"
    },
    "cosmos": {
        "espace", "univers", "etoile", "galaxie", "cosmique", "astronomie", "infini"
    },
    "univers": {
        "cosmos", "espace", "monde", "creation", "infini", "astrophysique"
    },
    "soleil": {
        "astre", "etoile", "lumiere", "rayon", "aurore", "sol", "helio", "chaleur", "solaire"
    },
    "lune": {
        "satellite", "astre", "croissant", "pleine-lune", "lunaire", "selene", "orbite"
    },
    "etoile": {
        "astre", "constellation", "etoilement", "galaxie", "supernova", "nebuleuse", "stellaire", "soleil"
    },
    "planete": {
        "astre", "orbite", "satellite", "terre", "mars", "jupiter", "saturne", "mercure", "venus"
    },
    "terre": {
        "globe", "planete", "monde", "sol", "terroir", "argile", "tellure", "terrestre", "humanite"
    },
    "ciel": {
        "azur", "voute", "firmament", "espace", "cosmos", "atmosphere", "cieux", "nuage"
    },
    "nuage": {
        "brume", "brouillard", "cumulus", "stratus", "nimbus", "pluie", "ciel", "vapeur"
    },
    "vent": {
        "brise", "souffle", "bourrasque", "tempete", "rafale", "cyclone", "ouragan", "eolien", "air"
    },
    "pluie": {
        "averse", "precipitations", "orage", "ondée", "deluge", "goutte", "bruine", "eau"
    },
    "orage": {
        "eclair", "foudre", "tonnerre", "tempete", "averse", "bourrasque", "electricite"
    },
    "feu": {
        "flamme", "braise", "incendie", "brasier", "foyer", "combustion", "cendre", "chaleur"
    },

    # --- Humains, Corps, Famille & Société ---
    "homme": {
        "humain", "individu", "personne", "mortel", "genre", "masculin", "homme-politique"
    },
    "femme": {
        "dame", "feminin", "epouse", "feminite", "matrone", "mere", "fille"
    },
    "enfant": {
        "gosse", "bambin", "mome", "fils", "fille", "jeune", "mineur", "enfance", "bebe"
    },
    "pere": {
        "papa", "parent", "paternel", "patriarche", "famille", "geniteur"
    },
    "mere": {
        "maman", "parente", "maternelle", "matriarche", "famille", "genitrice"
    },
    "famille": {
        "parents", "enfants", "fratrie", "foyer", "lignee", "clan", "descendance", "ancetres"
    },
    "corps": {
        "organisme", "anatomie", "physique", "corporel", "chair", "membre"
    },
    "tete": {
        "crane", "visage", "face", "chef", "cerveau", "esprit"
    },
    "coeur": {
        "cardiaque", "organe", "centre", "sentiment", "amour", "pouls", "poitrine"
    },
    "yeux": {
        "oeil", "regard", "vision", "vue", "oculaire", "prunelle"
    },
    "main": {
        "doigt", "paume", "manuel", "poing", "geste", "toucher"
    },
    "cerveau": {
        "esprit", "pensee", "neurone", "cerebral", "intellect", "tete", "matiere-grise"
    },

    # --- Pouvoir, Histoire & Politique ---
    "roi": {
        "reine", "monarque", "souverain", "prince", "regnant", "couronne", "empereur", "tsar", "trone", "royaume", "royal"
    },
    "reine": {
        "roi", "souveraine", "monarque", "princesse", "imperatrice", "couronne", "royaume", "royale"
    },
    "prince": {
        "princesse", "roi", "reine", "heritier", "monarque", "seigneur", "duc", "royaute"
    },
    "empereur": {
        "imperatrice", "empire", "imperial", "souverain", "monarque", "cesar", "tsar", "napoleon"
    },
    "president": {
        "republique", "chef", "dirigeant", "gouvernement", "etat", "ministre", "elysee"
    },
    "gouvernement": {
        "etat", "ministere", "pouvoir", "regime", "administration", "cabinet", "politique"
    },
    "pays": {
        "nation", "etat", "patrie", "territoire", "terre", "royaume", "republique", "frontiere"
    },
    "ville": {
        "cite", "metropole", "commune", "capitale", "bourg", "agglomeration", "urbain", "quartier"
    },
    "capitale": {
        "metropole", "ville", "siege", "centre", "paris", "gouvernement"
    },
    "guerre": {
        "conflit", "bataille", "combat", "hostilites", "lutte", "affrontement", "armee", "militaire", "soldat"
    },
    "paix": {
        "concorde", "armistice", "calme", "serenite", "traite", "treve", "reconciliation"
    },
    "armee": {
        "troupes", "forces", "soldats", "militaire", "regiment", "bataillon", "legion", "defense"
    },
    "soldat": {
        "guerrier", "combattant", "militaire", "troupe", "fantassin", "officier", "armee"
    },
    "bataille": {
        "combat", "affrontement", "guerre", "engagement", "choc", "victoire", "defaite"
    },
    "loi": {
        "regle", "norme", "decret", "ordonnance", "constitution", "droit", "statut", "principe", "legal"
    },
    "justice": {
        "equite", "droit", "tribunal", "juge", "juridiction", "legalite", "magistrature", "loi"
    },

    # --- Sciences, Technologie & Recherche ---
    "science": {
        "discipline", "savoir", "connaissance", "erudition", "recherche", "technologie", "scientifique", "theorie"
    },
    "physique": {
        "mecanique", "matiere", "energie", "optique", "thermodynamique", "quantique", "atomique", "atome"
    },
    "chimie": {
        "alchimie", "biochimie", "synthese", "reaction", "element", "matiere", "formule", "molecule"
    },
    "biologie": {
        "vie", "genetique", "zoologie", "botanique", "physiologie", "ecologie", "anatomie", "cellule"
    },
    "mathematiques": {
        "calcul", "geometrie", "algebre", "arithmetique", "analyse", "statistique", "logique", "nombre"
    },
    "recherche": {
        "chercheur", "laboratoire", "decouverte", "science", "investigation", "etude", "experience"
    },
    "laboratoire": {
        "recherche", "chercheur", "science", "experience", "institut", "analyse"
    },
    "medecine": {
        "medical", "medecin", "soin", "soigner", "hopital", "sante", "maladie", "docteur", "chirurgie"
    },
    "docteur": {
        "medecin", "praticien", "therapeute", "soignant", "professeur", "chercheur"
    },
    "hopital": {
        "clinique", "soin", "medecine", "urgence", "patient", "infirmier", "chambres"
    },

    # --- Arts, Littérature, Musique & Cinéma ---
    "musique": {
        "melodie", "harmonie", "chant", "sonate", "symphonie", "partition", "composition", "rythme", "chanson", "musical"
    },
    "chanson": {
        "musique", "chant", "chanteur", "chanteuse", "air", "tube", "refrain", "melodie"
    },
    "peinture": {
        "tableau", "toile", "fresque", "aquarelle", "gouache", "peintre", "portrait", "couleur", "art"
    },
    "peintre": {
        "artiste", "peinture", "tableau", "toile", "dessinateur", "atelier"
    },
    "cinema": {
        "film", "septieme-art", "cinematographe", "pellicule", "audiovisuel", "long-metrage", "acteur", "realisateur"
    },
    "film": {
        "cinema", "long-metrage", "court-metrage", "tournage", "scenario", "movie", "video"
    },
    "livre": {
        "roman", "ouvrage", "tome", "volume", "recueil", "manuscrit", "oeuvre", "bouquin", "auteur", "page"
    },
    "roman": {
        "livre", "fiction", "recit", "histoire", "romancier", "auteur", "nouvelle"
    },
    "auteur": {
        "ecrivain", "romancier", "poete", "createur", "dramaturge", "litterature"
    },
    "theatre": {
        "comedie", "tragedie", "dramaturgie", "scene", "piece", "representation", "spectacle", "acteur"
    },
    "chateau": {
        "palais", "forteresse", "bastion", "citadelle", "donjon", "manoir", "residence", "roi"
    },
    "eglise": {
        "cathedrale", "basilique", "chapelle", "temple", "sanctuaire", "paroisse", "clocher"
    },

    # --- Verbes & Concepts universels ---
    "construire": {
        "edifier", "batir", "fonder", "eriger", "creer", "construction", "batiment", "architecte"
    },
    "detruire": {
        "demolir", "abattre", "raser", "aneantir", "ruiner", "destruction", "ruine"
    },
    "vivre": {
        "exister", "resider", "habiter", "subsister", "vie", "vivant", "survivre"
    },
    "mourir": {
        "deceder", "trepasser", "expirer", "perir", "mort", "deces", "funebre"
    },
    "manger": {
        "nourrir", "consommer", "dejeuner", "diner", "souper", "aliment", "nourriture", "repas"
    },
    "boire": {
        "desalterer", "avaler", "siroter", "boisson", "eau", "vin"
    },
    "dormir": {
        "sommeiller", "reposer", "sommeil", "reve", "coucher", "lit"
    },
    "voyager": {
        "parcourir", "visiter", "voyage", "voyageur", "trajet", "expedition", "traverser"
    },
    "voler": {
        "planer", "s-envoler", "vol", "aviation", "avion", "oiseau", "aile"
    },
    "rouler": {
        "circuler", "conduire", "vehicule", "voiture", "automobile", "route", "roue"
    }
}

# Expanded etymological families covering Greek/Latin roots and French morphological networks.
EXPANDED_ETYMOLOGICAL_FAMILIES: Dict[str, Set[str]] = {
    "mont_orog": {
        "mont", "montagne", "monticule", "montant", "surmonter", "orographie", "orogenese",
        "oronyme", "alpes", "pic", "sommet", "cime", "alpin", "alpinisme", "pyrenees", "massif"
    },
    "alb_blanc": {
        "blanc", "blanche", "blancheur", "blanchir", "albatre", "albumine", "albinos",
        "albedo", "craie", "immacule", "neige", "neigeux"
    },
    "glac_cryo": {
        "glace", "glacier", "glaciation", "glacial", "glacon", "glaciere", "gel", "degel",
        "degeler", "geler", "cryogenie", "cryotherapie", "cryosphere", "inlandsis",
        "serac", "banquise", "verglas", "moraine", "froid"
    },
    "aqua_hydro": {
        "eau", "aquatique", "aquarium", "aqueduc", "aquarelle", "aqueux", "aquaculture",
        "hydrogene", "hydraulique", "hydratation", "hydrocarbure", "hydrographie", "hydrofuge",
        "hydrolienne", "hydrophile"
    },
    "geo_tellur": {
        "terre", "terrestre", "territoire", "territoires", "atterrir", "enterre", "geographie",
        "geographique", "geologie", "geologique", "geometrie", "geometrique", "geothermie",
        "geophysique", "geopolitique", "tellurique", "tellure", "globe"
    },
    "ign_pyro": {
        "feu", "flamme", "ignifuge", "pyrotechnie", "incendie", "pyromane", "ignition",
        "combustion", "embrasement", "foyer", "braise"
    },
    "vent_anemo": {
        "vent", "venteux", "ventilation", "ventilateur", "anemometre", "anemophile", "brise",
        "bourrasque", "tempete", "eole", "eolien", "eolienne", "souffle"
    },
    "fluv_potamo": {
        "fleuve", "fluvial", "fluviale", "riviere", "affluent", "potamologie", "ruisseau",
        "estuaire", "cours-d-eau"
    },
    "mar_thalasso": {
        "mer", "marin", "marine", "maritime", "navire", "navigation", "naval", "navigateur",
        "thalassotherapie", "thalassocratie", "nautique", "ocean", "oceanique", "sous-marin"
    },
    "ast_cosm": {
        "astre", "etoile", "etoiles", "astronomie", "astronome", "astronomique", "astronaute",
        "astrophysique", "asteroide", "astrologie", "cosmos", "cosmique", "spatial",
        "spatiale", "espace", "cosmonaute"
    },
    "luc_phot": {
        "lumiere", "lucide", "lumineux", "lumineuse", "luminosite", "illuminer", "luciole",
        "photon", "photographie", "photometrie", "photosynthese"
    },
    "chron_temp": {
        "temps", "chronologie", "chronologique", "chronique", "chronometre", "anachronique",
        "synchroniser", "synchrone", "temporel", "temporaire", "intemporel", "contemporain", "temporalite"
    },
    "anthro_hum": {
        "homme", "humain", "humaine", "humanite", "anthropologie", "misanthrope", "philanthrope",
        "anthropomorphisme", "humanitaire"
    },
    "graph_script": {
        "ecrire", "ecriture", "ecrivain", "graphique", "graphisme", "biographie", "calligraphie",
        "orthographe", "manuscrit", "inscription", "description", "prescrire", "texte",
        "typographie", "epigraphie"
    },
    "phon_son": {
        "son", "voix", "telephone", "phonetique", "symphonie", "sonore", "acoustique",
        "resonance", "microphone", "polyphonie", "francophone", "cacophonie"
    },
    "vid_opt": {
        "voir", "vue", "visible", "visuel", "vision", "television", "prevoir", "prevision",
        "revoir", "revue", "clairvoyant", "optique", "opticien", "oculaire", "ophtalmologie", "panoramique"
    },
    "scien_epist": {
        "science", "scientifique", "scientifiques", "epistemologie", "epistemon", "savoir",
        "connaissance", "erudition", "chercheur", "recherche", "laboratoire", "theorie"
    },
    "polit_civ": {
        "cite", "citoyen", "citoyenne", "politique", "civique", "civil", "civilisation",
        "metropole", "megapole", "police", "politologue"
    },
    "bell_milit": {
        "guerre", "guerrier", "belliqueux", "belligerant", "rebellion", "militaire", "militaires",
        "armee", "arme", "soldat", "bataille", "combat", "combattant"
    },
    "jur_droit": {
        "droit", "justice", "juridique", "jurisprudence", "juriste", "juge", "loi",
        "legal", "legalite", "legitime", "legislation", "legislatif", "magistrat", "juridiction"
    },
    "viv_bio": {
        "vie", "vivant", "vivante", "vital", "vitalite", "survivre", "survie", "revivre",
        "vitamine", "biologie", "biologique", "biologiste", "biographie", "biotope",
        "biosphere", "antibiotique", "biodiversite"
    },
    "san_sante": {
        "sante", "sain", "assainir", "sanitaire", "salubre", "guerir", "guerison",
        "medecine", "medical", "hopital", "soin", "soigner", "clinique", "docteur"
    },
    "aero_vol": {
        "air", "aerien", "aerienne", "aeroport", "avion", "aviation", "aviateur",
        "aeronautique", "vol", "voler", "aeronef", "aerodynamique"
    },
    "thermo_calor": {
        "chaud", "chaleur", "thermique", "thermometre", "thermostat", "thermonucleaire",
        "thermodynamique", "calorie", "calorifique"
    },
    "morph_forme": {
        "forme", "morphologie", "metamorphose", "amorphe", "isomorphe", "polymorphe", "difforme"
    },
    "psych_ment": {
        "esprit", "ame", "psychologie", "psychologique", "psychiatrie", "psychique",
        "mental", "mentalite", "pensee", "conscience"
    },
    "demo_pop": {
        "peuple", "population", "democratie", "demographie", "demographique", "epidemie",
        "pandemie", "populaire"
    },
    "num_pecun": {
        "argent", "monnaie", "monetaire", "finance", "financier", "fiscal", "pecuniaire",
        "economie", "economique", "banque", "bancaire"
    },
    "the_divin": {
        "dieu", "deesse", "divin", "divinite", "theologie", "theisme", "pantheon", "culte",
        "religion", "religieux", "sacre", "saint"
    },
    "urbs_polis": {
        "ville", "urbain", "urbanisme", "urbaniste", "suburbain", "metropole", "megapole", "megalopole"
    },
    "arbor_dendro": {
        "arbre", "foret", "boise", "bois", "arboriculture", "arborescent", "sylvestre", "dendrologie"
    },
    "equ_hipp": {
        "cheval", "chevaux", "equestre", "equitation", "cavalier", "cavalerie", "hippique", "hippodrome"
    }
}

# Curated French and world proper nouns (prénoms, noms de famille, écrivains, artistes, figures historiques, géographie)
FRENCH_PROPER_NOUNS: Set[str] = {
    # Prénoms masculins & féminins
    "marcel", "pierre", "jean", "paul", "michel", "alain", "philippe", "louis", "nicolas",
    "christophe", "patrick", "christian", "daniel", "laurent", "bernard", "eric", "stephane",
    "david", "luc", "julien", "alexandre", "antoine", "thomas", "vincent", "sebastien",
    "olivier", "guillaume", "francois", "georges", "andre", "jacques", "claude", "rene",
    "robert", "maurice", "charles", "henri", "guy", "gerard", "albert", "edouard", "eugene",
    "leon", "maxime", "theodore", "auguste", "benjamin", "clement", "etienne", "gabriel",
    "leonard", "mathieu", "raphael", "simon", "valentin", "xavier", "arthur", "camille",
    "emile", "felix", "gaston", "gustave", "victor", "achille", "adrien", "alban", "alexis",
    "anatole", "anthony", "armand", "arnaud", "baptiste", "basile", "bastien", "benoit",
    "blaise", "boris", "brice", "cedric", "cesar", "cyril", "damien", "dorian", "eloi",
    "emmanuel", "fabien", "fabrice", "florent", "florian", "franck", "gaspard", "gaetan",
    "gregoire", "hugo", "jocelyn", "joel", "jules", "justin", "kevin", "lambert", "lazare",
    "leo", "loic", "ludovic", "marius", "martial", "mathis", "maximilien", "mickael", "milo",
    "nathan", "noe", "octave", "pascal", "quentin", "raymond", "remi", "rodolphe", "roger",
    "roland", "romain", "sacha", "serge", "sylvain", "tanguy", "theo", "thibault", "timothee",
    "tristan", "wilfried", "yann", "yannick", "yoan", "gwenael",
    "marie", "nathalie", "isabelle", "sylvie", "catherine", "francoise", "monique", "christine",
    "sandrine", "stephanie", "celine", "sophie", "valerie", "aurelie", "emilie", "julie",
    "charlotte", "claire", "emma", "jeanne", "lea", "louise", "manon", "sarah", "alice",
    "juliette", "lucie", "margaux", "pauline", "clara", "mathilde", "oceane", "romane",
    "helene", "suzanne", "simone", "georgette", "marcelle", "colette", "yvonne", "odette",
    "paulette", "therese", "micheline", "jacqueline", "germaine", "renee", "lucette", "denise",
    "marianne", "brigitte", "chantal", "martine", "dominique", "veronique", "caroline",
    "florence", "beatrice", "laurence", "agnes", "corinne", "pascale", "patricia", "genevieve",
    "adele", "adeline", "agathe", "alexandra", "alicia", "aline", "amandine", "ambre", "amelie",
    "anais", "angelique", "annick", "apolline", "astrid", "audrey", "bernadette", "capucine",
    "cecile", "chloe", "christelle", "claudine", "clemence", "coline", "constance", "coralie",
    "delphine", "diane", "dorothee", "elena", "eleonore", "elisa", "elisabeth", "elodie",
    "estelle", "eugenie", "eva", "fanny", "faustine", "flavie", "fleur", "gaelle", "gwenaelle",
    "hortense", "ines", "iris", "jade", "jessica", "josephine", "laetitia", "lara", "laure",
    "lena", "leonie", "lola", "lorene", "lou", "louna", "lucille", "ludivine", "magali",
    "marina", "marine", "marion", "marlene", "melanie", "melissa", "meline", "myriam", "nadine",
    "noemie", "olivia", "ophelie", "oriane", "perrine", "roxane", "sabine", "sabrina", "salome",
    "severine", "solene", "sonia", "tiffany", "tiphaine", "victoire", "virginie", "zoe",

    # Écrivains, dramaturges, philosophes & artistes
    "pagnol", "hugo", "zola", "proust", "moliere", "voltaire", "rousseau", "balzac", "flaubert",
    "baudelaire", "verlaine", "rimbaud", "dumas", "camus", "sartre", "beauvoir", "sand",
    "stendhal", "montaigne", "rabelais", "corneille", "racine", "lafontaine", "chateaubriand",
    "maupassant", "verne", "apollinaire", "prevert", "elouard", "aragon", "cocteau", "gide",
    "malraux", "vian", "cesaire", "senghor", "duras", "modiano", "houellebecq", "tournier",
    "perec", "queneau", "simenon", "anouilh", "beckett", "ionesco", "genet", "rostand",
    "musset", "vigny", "lamartine", "merimee", "gautier", "daudet", "renard", "radiguet",
    "bernanos", "giono", "barjavel", "claudel", "valery",
    "monet", "renoir", "rodin", "picasso", "cezanne", "degas", "manet", "gauguin", "matisse",
    "chagall", "dali", "courbet", "delacroix", "ingres", "david", "braque", "seurat",
    "modigliani", "kandinsky", "miro", "warhol", "rembrandt", "vermeer", "vinci", "michel-ange",
    "caravage", "rubens", "velasquez", "goya", "turner", "klimt", "munch", "botticelli",
    "chopin", "debussy", "ravel", "berlioz", "bizet", "faure", "saint-saens", "bach",
    "mozart", "beethoven", "vivaldi", "brahms", "schubert", "tchaikovski", "verdi", "wagner",
    "handel", "haydn", "liszt", "mahler", "puccini", "rossini", "mendelssohn", "strauss",
    "truffaut", "godard", "rohmer", "chabrol", "resnais", "malle", "tati", "bresson",
    "clouzot", "melville", "lelouch", "audiard", "besson", "jeunet", "hitchcock", "spielberg",
    "kubrick", "scorsese", "tarantino", "chaplin", "fellini", "bergman", "kurosawa",

    # Figures historiques, scientifiques & politiques
    "napoleon", "bonaparte", "charlemagne", "clovis", "de gaulle", "clemenceau", "jaures",
    "macron", "mitterrand", "chirac", "hollande", "sarkozy", "pompidou", "giscard", "thiers",
    "gambetta", "robespierre", "danton", "marat", "curie", "pasteur", "descartes", "pascal",
    "fermat", "poincare", "einstein", "newton", "galilee", "darwin", "lavoisier", "ampere",
    "foucault", "becquerel", "laplace", "buffon", "lamarck", "cuvier", "turing", "copernic",
    "kepler", "hawking", "mendeleiev", "planck", "bohr", "feynman", "tesla", "edison", "bell",
    "aristote", "platon", "socrate", "cesar", "auguste", "alexandre", "homere", "ciceron",
    "seneque", "spinoza", "kant", "hegel", "nietzsche", "marx", "engels", "freud", "jung", "locke",
    "hume", "hobbes", "machiavel", "oppenheimer", "colbert", "richelieu", "mazarin", "talleyrand",
    "poutine", "zelensky", "trump", "biden", "obama", "bush", "clinton", "reagan", "nixon", "kennedy",
    "roosevelt", "lincoln", "washington", "churchill", "thatcher", "staline", "lenine", "trotski",
    "gorbatchev", "mao", "mandela", "gandhi", "castro", "guevara", "che", "bolivar", "merkel",
    "hitler", "mussolini", "franco", "ataturk", "nasser",

    # Cinéma, Théâtre & Acteurs
    "belmondo", "delon", "deneuve", "bardot", "depardieu", "gabin", "ventura", "funes", "de funes",
    "bourvil", "fernandel", "coluche", "desproges", "devos", "marceau", "binoche", "cotillard",
    "adjani", "hitchcock", "kubrick", "spielberg", "scorsese", "tarantino", "coppola", "nolan",
    "cameron", "lucas", "chaplin", "keaton", "monroe", "bogart", "brando", "pacino", "de niro",
    "streep", "hepburn", "marivaux", "beaumarchais", "diderot", "montesquieu",

    # Musique & Chanson
    "brassens", "brel", "ferrat", "ferre", "piaf", "gainsbourg", "aznavour", "hallyday", "goldman",
    "cabrel", "souchon", "renaud", "bashung", "balavoine", "berger", "gall", "hardy", "sanson",
    "mitchell", "nougaro", "montand", "trenet", "dassin", "salvador", "satie",

    # Sport
    "zidane", "mbappe", "platini", "henry", "griezmann", "benzema", "kopa", "fontaine", "pele",
    "maradona", "messi", "ronaldo", "cruyff", "beckham", "nadal", "federer", "djokovic", "noah",
    "prost", "senna", "schumacher", "hamilton", "verstappen", "jordan", "lebron", "kobe", "curry",
    "bolt", "phelps", "fourcade", "riner", "marchand", "dupont",

    # Auteurs internationaux majeurs
    "tolstoi", "dostoievski", "tchekhov", "gogol", "pouchkine", "kafka", "goethe", "schiller",
    "thomas mann", "mann", "brecht", "dante", "petrarque", "boccace", "cervantes", "shakespeare",
    "milton", "swift", "dickens", "woolf", "joyce", "wilde", "orwell", "huxley", "poe", "twain",
    "hemingway", "fitzgerald", "faulkner", "steinbeck", "kerouac", "borges", "marquez", "neruda",
    "calvino", "eco", "kundera", "nothomb", "ernaux",

    # Géographie : Villes, Régions, Pays & Rivières
    "paris", "marseille", "lyon", "toulouse", "nice", "nantes", "strasbourg", "montpellier",
    "bordeaux", "lille", "rennes", "reims", "toulon", "saint-etienne", "le havre", "grenoble",
    "dijon", "angers", "nimes", "villeurbanne", "clermont-ferrand", "le mans", "aix-en-provence",
    "brest", "tours", "amiens", "limoges", "perpignan", "metz", "besancon", "orleans", "rouen",
    "mulhouse", "caen", "nancy", "avignon", "poitiers", "versailles", "aubagne", "cannes",
    "antibes", "calais", "dunkerque", "cherbourg", "biarritz", "bayonne", "pau", "tarbes",
    "valence", "chambery", "annecy", "colmar", "belfort", "bourges", "chartres", "blois",
    "ajaccio", "bastia", "londres", "madrid", "rome", "berlin", "bruxelles", "amsterdam",
    "vienne", "berne", "geneve", "zurich", "lisbonne", "athenes", "varsovie", "prague",
    "budapest", "bucarest", "moscou", "kiev", "oslo", "stockholm", "helsinki", "copenhague",
    "dublin", "washington", "new york", "chicago", "los angeles", "san francisco", "tokyo",
    "pekin", "shanghai", "hong kong", "seoul", "bangkok", "singapour", "delhi", "mumbai",
    "le caire", "tunis", "alger", "rabat", "casablanca", "dakar", "pretoria", "sydney",
    "melbourne", "ottawa", "montreal", "toronto", "mexico", "buenos aires", "rio de janeiro",
    "sao paulo", "bogota", "lima", "santiago",
    "france", "belgique", "suisse", "italie", "espagne", "allemagne", "angleterre", "portugal",
    "grece", "irlande", "ecosse", "pays-bas", "autriche", "suede", "norvege", "danemark",
    "finlande", "pologne", "russie", "ukraine", "canada", "bresil", "argentine", "chine",
    "japon", "inde", "australie", "egypte", "maroc", "algerie", "tunisie", "senegal", "madagascar",
    "mexique", "chili", "perou", "colombie", "islande", "turquie", "liban", "israel", "iran",
    "provence", "bretagne", "normandie", "alsace", "lorraine", "bourgogne", "aquitaine",
    "occitanie", "corse", "savoie", "auvergne", "picardie", "champagne", "touraine",
    "seine", "rhone", "loire", "garonne", "rhin", "meuse", "tamise", "danube", "nil", "amazone",
    "alpes", "pyrenees", "vosges", "jura", "himalaya", "andes", "oural", "caucase", "atlas",
    "everest", "mont-blanc"
}

GENERIC_BRIDGE_WORDS.update({
    "accepter", "accorder", "accompagner", "ajouter", "amener", "apporter", "arriver",
    "atteindre", "augmenter", "changer", "commencer", "conduire", "conserver", "continuer",
    "convenir", "devenir", "entrer", "envoyer", "exister", "expliquer", "former", "gagner",
    "importer", "inclure", "indiquer", "jouer", "lancer", "marquer", "offrir", "ouvrir",
    "parler", "placer", "produire", "proposer", "rester", "retourner", "suivre", "terminer",
    "utiliser", "venir", "vivre", "reponse", "rapport", "niveau", "lieu", "milieu",
    "partie", "public", "personne", "ensemble", "groupe", "centre", "cause", "fin",
})

EXPANDED_STOPWORDS.update({
    "aucun", "aucune", "aucuns", "aucunes", "chaque", "chacun", "chacune", "certain",
    "certaine", "certains", "certaines", "plusieurs", "quelque", "quelques", "quelqu'un",
    "quelqu'une", "quiconque", "mien", "mienne", "miens", "miennes", "tien", "tienne",
    "tiens", "tiennes",
    "sien", "sienne", "siens", "siennes", "notre", "votre", "nôtre", "vôtre",
    "ceux", "celles", "celui", "celle", "ceci", "cela", "voici", "voila", "voilà",
    "dont", "aupres", "auprès", "ici", "quelquefois", "parfois", "maintenant",
    "ensuite", "enfin", "cependant", "pourtant", "néanmoins", "donc", "car", "or",
    "quoique", "quoiqu", "puisqu", "lorsqu", "jusqu", "dès", "des", "parmi", "quant",
    "soi-même", "lui-même", "elle-même", "eux-mêmes", "elles-mêmes",
})

for _word, _synonyms in {
    "habitation": {"logement", "demeure", "résidence", "maison"},
    "logement": {"habitation", "demeure", "résidence"},
    "demeure": {"habitation", "logement", "résidence"},
    "automobile": {"voiture", "auto"},
    "voiture": {"automobile", "auto"},
    "bateau": {"navire", "embarcation"},
    "navire": {"bateau", "vaisseau"},
    "embarcation": {"bateau", "canot"},
    "véhicule": {"engin", "automobile", "moyen de transport"},
    "futaie": {"forêt"},
    "ruisseau": {"ru", "rigole"},
    "ru": {"ruisseau"},
    "rivage": {"rive", "bord"},
    "rive": {"rivage", "berge"},
    "ouvrage": {"œuvre", "travail"},
    "œuvre": {"ouvrage", "création"},
    "auteur": {"écrivain", "écrivaine"},
    "écrivain": {"auteur", "écrivaine"},
    "médecin": {"docteur", "praticien"},
    "praticien": {"médecin", "professionnel"},
    "enseignant": {"professeur", "instituteur"},
    "professeur": {"enseignant", "prof"},
    "élève": {"écolier", "apprenant"},
    "écolier": {"élève"},
    "commune": {"municipalité"},
    "municipalité": {"commune"},
    "début": {"commencement", "origine"},
    "commencement": {"début", "origine"},
    "fin": {"terme", "conclusion"},
    "terme": {"fin", "aboutissement"},
    "bâtiment": {"édifice", "construction"},
    "édifice": {"bâtiment"},
    "boutique": {"magasin", "commerce"},
    "magasin": {"boutique"},
    "commerce": {"négoce"},
    "négoce": {"commerce"},
    "nourriture": {"aliment", "denrée"},
    "aliment": {"nourriture", "denrée"},
    "boisson": {"breuvage"},
    "breuvage": {"boisson"},
    "boisement": {"forêt"},
    "colline": {"coteau", "monticule"},
    "monticule": {"colline", "butte"},
    "coteau": {"colline"},
    "rocher": {"roc"},
    "roc": {"rocher"},
    "prison": {"geôle", "maison d'arrêt"},
    "geôle": {"prison"},
    "célébrité": {"personnalité"},
    "personnalité": {"célébrité", "figure"},
    "chanteur": {"vocaliste"},
    "vocaliste": {"chanteur"},
    "comédien": {"acteur", "interprète"},
    "acteur": {"comédien", "interprète"},
    "réalisateur": {"metteur en scène"},
    "metteur en scène": {"réalisateur"},
    "vérité": {"véracité", "exactitude"},
    "véracité": {"vérité"},
    "courage": {"bravoure", "vaillance"},
    "bravoure": {"courage", "vaillance"},
    "peur": {"crainte", "frayeur"},
    "crainte": {"peur", "appréhension"},
    "joie": {"allégresse", "gaieté"},
    "allégresse": {"joie"},
    "colère": {"courroux", "ire"},
    "courroux": {"colère"},
    "rapide": {"prompt", "véloce"},
    "prompt": {"rapide", "véloce"},
    "lent": {"lambin"},
    "lambin": {"lent"},
    "ancien": {"antique", "vieux"},
    "antique": {"ancien"},
    "commencer": {"débuter", "entamer"},
    "débuter": {"commencer", "entamer"},
    "terminer": {"achever", "finir"},
    "achever": {"terminer", "finir"},
    "construire": {"bâtir", "édifier"},
    "bâtir": {"construire", "édifier"},
    "détruire": {"démolir", "anéantir"},
    "démolir": {"détruire", "raser"},
    "regarder": {"observer", "contempler"},
    "observer": {"regarder", "examiner"},
    "aider": {"assister", "secourir"},
    "secourir": {"aider", "assister"},
    "choisir": {"sélectionner", "opter"},
    "sélectionner": {"choisir"},
    "acheter": {"acquérir"},
    "acquérir": {"acheter"},
    "vendre": {"céder"},
    "céder": {"vendre"},
    "mourir": {"décéder", "trépasser"},
    "décéder": {"mourir", "trépasser"},
    "naître": {"venir au monde"},
    "habiter": {"résider", "demeurer"},
    "résider": {"habiter", "demeurer"},
    "parler": {"s'exprimer"},
    "s'exprimer": {"parler"},
}.items():
    HARDCODED_SYNONYMS_RAW.setdefault(_word, set()).update(_synonyms)

EXPANDED_ETYMOLOGICAL_FAMILIES.update({
    "nation_natal": {
        "nation", "national", "nationale", "nationalité", "nationaliser", "international",
        "internationalité", "nationalisme", "nationaliste",
    },
    "civ_cite": {
        "cité", "citoyen", "citoyenne", "civique", "civil", "civile", "civilité",
        "civilisation", "civiliser",
    },
    "cult_culture": {
        "culture", "cultiver", "cultivateur", "cultivé", "cultural", "culturel",
        "culturisme", "agriculture", "horticulture",
    },
    "educ_duc": {
        "éducation", "éduquer", "éducateur", "éducatrice", "éducatif", "éducative",
    },
    "aud_audio": {
        "audition", "audible", "auditeur", "auditrice", "audio", "audiovisuel",
        "audience", "inaudible",
    },
    "port_transport": {
        "porter", "porteur", "porteuse", "transport", "transporter", "transporteur",
        "portable", "importer", "exporter", "supporter",
    },
    "scrib_ecrire": {
        "écrire", "écriture", "écrivain", "écrivaine", "script", "scribe", "transcrire",
        "inscrire", "inscription", "descriptif", "description",
    },
    "med_medic": {
        "médecine", "médecin", "médical", "médicale", "médicament", "médicamenter",
        "médication", "médicamentation",
    },
    "manu_main": {
        "main", "manuel", "manuelle", "manipuler", "manipulation", "manipulateur",
        "manuscrit", "manufacture", "manufacturier",
    },
    "spec_spectacle": {
        "spectacle", "spectateur", "spectatrice", "spectaculaire", "spectacle vivant",
        "spectacularité",
    },
    "form_formation": {
        "forme", "former", "formation", "formateur", "formatrice", "formel", "formelle",
        "conformer", "déformer", "transformer",
    },
    "labor_travail": {
        "labeur", "laborieux", "laborieuse", "laboratoire", "collaborer", "collaboration",
        "collaborateur", "élaborer",
    },
    "phil_amour_savoir": {
        "philosophie", "philosophe", "philanthrope", "philanthropie", "philologie",
        "philologue", "bibliophile", "francophile", "anglophile",
    },
    "phob_crainte": {
        "phobie", "phobique", "claustrophobie", "agoraphobie", "arachnophobie",
        "xénophobie", "hydrophobie",
    },
    "dem_peuple": {
        "démocratie", "démocratique", "démocratiquement", "démocratisation",
        "démocratiser", "démocrate", "démographie", "démographique",
    },
    "eco_maison": {
        "écologie", "écologique", "écosystème", "écologue", "écocide",
    },
    "chron_temps_etude": {
        "chronologie", "chronologique", "chronique", "chroniqueur", "chronomètre",
        "chronométrer", "anachronisme", "synchroniser", "synchronisation",
    },
    "therm_chaleur": {
        "thermique", "thermomètre", "thermostat", "thermodynamique", "thermographie",
        "thermique", "thermicien", "thermogenèse",
    },
    "graph_ecriture": {
        "graphie", "graphique", "graphisme", "graphiste", "graphologie", "typographie",
        "calligraphie", "géographie", "orthographe", "photographie",
    },
})

FRENCH_PROPER_NOUNS.update({
    "afghanistan", "afrique", "albanie", "algérie", "allemagne", "andorre", "angola",
    "arabie", "arabie saoudite", "arménie", "asie", "autriche", "azerbaïdjan", "bahamas",
    "bahreïn", "bangladesh", "barbade", "belgique", "bénin", "bhoutan", "biélorussie",
    "birmanie", "bolivie", "bosnie", "botswana", "brésil", "bulgarie", "burkina faso",
    "burundi", "cambodge", "cameroun", "canada", "cap-vert", "chili", "chine", "chypre",
    "colombie", "comores", "congo", "corée", "croatie", "cuba", "danemark", "djibouti",
    "dominique", "égypte", "équateur", "érythrée", "espagne", "estonie", "états-unis",
    "éthiopie", "europe", "finlande", "france", "gabon", "gambie", "géorgie", "ghana",
    "grèce", "guatemala", "guinée", "haïti", "honduras", "hongrie", "inde", "indonésie",
    "irak", "iran", "irlande", "islande", "israël", "italie", "jamaïque", "japon", "jordanie",
    "kazakhstan", "kenya", "kirghizistan", "kosovo", "koweït", "laos", "lettonie", "liban",
    "libéria", "libye", "lituanie", "luxembourg", "madagascar", "malaisie", "mali", "malte",
    "maroc", "mauritanie", "maurice", "mexique", "monaco", "mongolie", "monténégro",
    "mozambique", "namibie", "népal", "nicaragua", "niger", "nigeria", "norvège", "nouvelle-zélande",
    "oman", "ouganda", "ouzbekistan", "pakistan", "panama", "paraguay", "pays-bas", "pérou",
    "philippines", "pologne", "portugal", "qatar", "roumanie", "royaume-uni", "russie",
    "rwanda", "sénégal", "serbie", "singapour", "slovaquie", "slovénie", "somalie", "soudan",
    "sri lanka", "suède", "suisse", "syrie", "tadjikistan", "taïwan", "tanzanie", "tchad",
    "tchéquie", "thaïlande", "togo", "tunisie", "turquie", "ukraine", "uruguay", "vatican",
    "venezuela", "vietnam", "yémen", "zambie", "zimbabwe",
    "amsterdam", "athènes", "bangkok", "barcelone", "berlin", "bogota", "bruxelles", "budapest",
    "buenos aires", "casablanca", "dakar", "delhi", "dubai", "istanbul", "jérusalem", "kinshasa",
    "lisbonne", "londres", "los angeles", "madrid", "mexico", "montréal", "moscou", "nairobi",
    "new york", "oslo", "ottawa", "pékin", "prague", "rio de janeiro", "rome", "séoul",
    "sydney", "tokyo", "toronto", "tunis", "varsovie", "vienne", "zurich",
    "albert camus", "emile zola", "george sand", "jules verne", "victor hugo", "simone de beauvoir",
    "marie curie", "louis pasteur", "charles de gaulle", "jeanne d'arc", "françois mitterrand",
    "léonard de vinci", "vincent van gogh", "claude monet", "auguste rodin", "pablo picasso",
    "wolfgang amadeus mozart", "ludwig van beethoven", "charles darwin", "isaac newton",
    "albert einstein", "aristote", "socrate", "platon", "confucius", "mahomet", "bouddha",
})
