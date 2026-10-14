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
        "montagne", "sommet", "pic", "cime", "aiguille", "massif", "alpes",
        "pyrenees", "colline", "hauteur", "elevation", "monticule", "relief", "altitude",
        "versant", "crete", "butte", "morne", "puy", "orographie"
    },
    "montagne": {
        "mont", "sommet", "pic", "cime", "chaine", "massif", "alpes", "pyrenees",
        "himalaya", "relief", "cordillere", "alpinisme", "altitude", "hauteur",
        "roche", "glacier", "versant", "aiguille", "crevasse"
    },
    "sommet": {
        "mont", "montagne", "pic", "cime", "zenith", "apex", "apogee",
        "pointe", "aiguille", "hauteur", "altitude", "crete", "haut", "pinnacle"
    },
    "pic": {
        "mont", "montagne", "sommet", "cime", "aiguille", "pointe", "dent", "arete"
    },
    "cime": {
        "mont", "montagne", "sommet", "pic", "aiguille", "pointe", "hauteur"
    },
    "colline": {
        "mont", "montagne", "monticule", "coteau", "butte", "eminence", "tertre", "vallon"
    },
    "vallee": {
        "gorge", "ravin", "vallon", "combe", "plaine", "canyon", "bassin", "val"
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

CURATED_VERB_ASSOCIATIONS: Dict[str, Dict[str, int]] = {
    "aboyer": {"chien": 84, "aboiement": 82, "chenil": 76},
    "miauler": {"chat": 84, "miaulement": 82, "félin": 78},
    "rugir": {"lion": 84, "rugissement": 82, "fauve": 78},
    "hennir": {"cheval": 84, "hennissement": 82, "écurie": 76},
    "braire": {"âne": 84, "braiement": 82},
    "coasser": {"grenouille": 84, "mare": 78},
    "croasser": {"corbeau": 84, "corneille": 80},
    "bourdonner": {"abeille": 82, "insecte": 78, "ruche": 78},
    "nager": {"piscine": 84, "natation": 84, "nageur": 82, "eau": 78},
    "plonger": {"plongeon": 84, "plongeur": 82, "piscine": 78, "eau": 76},
    "naviguer": {"bateau": 84, "navigation": 84, "marin": 80, "voile": 78},
    "ramer": {"aviron": 84, "rame": 82, "barque": 78},
    "conduire": {"voiture": 84, "volant": 82, "conducteur": 82, "route": 78},
    "piloter": {"avion": 84, "pilote": 84, "cockpit": 80, "aéroport": 76},
    "rouler": {"voiture": 82, "roue": 82, "route": 80, "automobile": 78},
    "marcher": {"pied": 82, "marche": 82, "chemin": 78, "promenade": 76},
    "courir": {"course": 84, "coureur": 82, "piste": 78, "athlétisme": 78},
    "galoper": {"cheval": 84, "galop": 84, "cavalier": 80},
    "grimper": {"escalade": 84, "montagne": 82, "sommet": 78, "alpiniste": 78},
    "atterrir": {"avion": 84, "atterrissage": 84, "piste": 82, "aéroport": 80},
    "décoller": {"avion": 84, "décollage": 84, "piste": 82, "aéroport": 80},
    "construire": {"bâtiment": 84, "maison": 82, "chantier": 82, "maçon": 78},
    "bâtir": {"bâtiment": 84, "maison": 82, "chantier": 80, "maçon": 78},
    "démolir": {"bâtiment": 84, "démolition": 84, "ruine": 80, "pelleteuse": 76},
    "fabriquer": {"usine": 84, "fabrication": 84, "machine": 80, "ouvrier": 78},
    "réparer": {"panne": 82, "outil": 80, "mécanicien": 80, "garage": 78},
    "assembler": {"pièce": 82, "montage": 82, "machine": 78},
    "peindre": {"peinture": 84, "tableau": 82, "toile": 82, "peintre": 80},
    "dessiner": {"dessin": 84, "crayon": 82, "portrait": 80, "dessinateur": 80},
    "sculpter": {"sculpture": 84, "pierre": 82, "statue": 82, "sculpteur": 80},
    "photographier": {"photographie": 84, "appareil": 82, "photo": 82, "photographe": 80},
    "filmer": {"film": 84, "caméra": 82, "tournage": 82, "cinéma": 78},
    "chanter": {"chanson": 84, "chant": 84, "chanteur": 82, "voix": 78},
    "composer": {"musique": 84, "partition": 82, "compositeur": 82, "mélodie": 80},
    "danser": {"danse": 84, "danseur": 82, "musique": 80, "chorégraphie": 80},
    "écrire": {"écriture": 84, "texte": 82, "lettre": 80, "écrivain": 80},
    "rédiger": {"texte": 84, "document": 82, "article": 80, "rédaction": 80},
    "lire": {"lecture": 84, "livre": 82, "texte": 80, "lecteur": 80},
    "traduire": {"traduction": 84, "langue": 82, "traducteur": 82, "texte": 78},
    "publier": {"publication": 84, "livre": 82, "journal": 80, "éditeur": 80},
    "imprimer": {"impression": 84, "imprimerie": 82, "papier": 78, "presse": 78},
    "cuisiner": {"cuisine": 84, "recette": 82, "repas": 82, "cuisinier": 80},
    "cuire": {"cuisson": 84, "four": 82, "aliment": 78, "plat": 78},
    "manger": {"nourriture": 84, "repas": 84, "aliment": 80, "alimentation": 78},
    "boire": {"boisson": 84, "eau": 82, "verre": 78, "soif": 78},
    "pétrir": {"pâte": 84, "farine": 82, "boulanger": 80, "boulangerie": 78},
    "moudre": {"moulin": 84, "farine": 82, "grain": 80, "meule": 78},
    "cultiver": {"culture": 84, "champ": 82, "agriculteur": 82, "terre": 78},
    "semer": {"semence": 84, "graine": 82, "champ": 80, "semoir": 78},
    "planter": {"plantation": 84, "arbre": 82, "graine": 80, "jardin": 78},
    "arroser": {"arrosage": 84, "plante": 82, "jardin": 80, "eau": 78},
    "récolter": {"récolte": 84, "champ": 82, "agriculteur": 80, "moisson": 78},
    "moissonner": {"moisson": 84, "blé": 82, "récolte": 82, "paysan": 78},
    "labourer": {"labour": 84, "champ": 82, "charrue": 82, "agriculteur": 78},
    "vendre": {"vente": 84, "commerce": 82, "magasin": 80, "marchand": 78},
    "acheter": {"achat": 84, "magasin": 80, "client": 78, "marchandise": 78},
    "payer": {"paiement": 84, "argent": 82, "prix": 80, "monnaie": 78},
    "soigner": {"soin": 84, "patient": 82, "médecin": 82, "hôpital": 78},
    "guérir": {"guérison": 84, "maladie": 82, "patient": 80, "santé": 78},
    "diagnostiquer": {"diagnostic": 84, "médecin": 82, "maladie": 80, "patient": 78},
    "opérer": {"opération": 84, "chirurgien": 82, "chirurgie": 82, "hôpital": 78},
    "vacciner": {"vaccin": 84, "vaccination": 84, "médecin": 80, "maladie": 78},
    "enseigner": {"enseignement": 84, "élève": 82, "professeur": 82, "école": 80},
    "apprendre": {"apprentissage": 84, "élève": 82, "connaissance": 80, "étude": 78},
    "étudier": {"étude": 84, "étudiant": 82, "université": 80, "école": 78},
    "chercher": {"recherche": 84, "quête": 82, "enquête": 80, "chercheur": 80},
    "observer": {"observation": 84, "microscope": 80, "astronome": 78, "étudier": 76},
    "mesurer": {"mesure": 84, "règle": 82, "longueur": 80, "mètre": 80},
    "calculer": {"calcul": 84, "nombre": 82, "mathématique": 80, "mathématiques": 80},
    "découvrir": {"découverte": 84, "explorateur": 80, "science": 78, "invention": 76},
    "inventer": {"invention": 84, "inventeur": 82, "innovation": 80, "idée": 78},
    "explorer": {"exploration": 84, "explorateur": 82, "expédition": 80, "territoire": 78},
    "gouverner": {"gouvernement": 84, "pays": 82, "président": 80, "politique": 78},
    "régner": {"règne": 84, "roi": 82, "royaume": 82, "monarchie": 80},
    "voter": {"vote": 84, "élection": 82, "urne": 82, "bulletin": 78},
    "élire": {"élection": 84, "président": 82, "vote": 82, "citoyen": 78},
    "juger": {"jugement": 84, "tribunal": 82, "juge": 82, "procès": 80},
    "condamner": {"condamnation": 84, "peine": 82, "tribunal": 80, "prison": 78},
    "défendre": {"défense": 84, "avocat": 82, "droit": 80, "tribunal": 78},
    "arrêter": {"police": 82, "policier": 80, "arrestation": 80, "suspect": 78},
    "enquêter": {"enquête": 84, "enquêteur": 82, "police": 78, "inspecteur": 78},
    "combattre": {"combat": 84, "guerre": 82, "armée": 80, "bataille": 80},
    "attaquer": {"attaque": 84, "ennemi": 82, "bataille": 80, "armée": 78},
    "protéger": {"protection": 84, "défense": 82, "bouclier": 78, "sécurité": 78},
    "libérer": {"libération": 84, "prisonnier": 82, "prison": 80, "liberté": 80},
    "pondre": {"œuf": 84, "poule": 82, "oiseau": 80, "ponte": 80},
    "éclore": {"éclosion": 84, "œuf": 82, "poussin": 80, "nid": 78},
    "couver": {"couvée": 84, "œuf": 82, "oiseau": 80, "nid": 78},
    "butiner": {"fleur": 84, "abeille": 82, "nectar": 82, "pollinisation": 78},
    "polliniser": {"pollinisation": 84, "fleur": 82, "pollen": 82, "abeille": 78},
    "fleurir": {"fleur": 84, "floraison": 84, "plante": 80, "printemps": 78},
    "bourgeonner": {"bourgeon": 84, "arbre": 80, "printemps": 78, "plante": 78},
    "faner": {"fleur": 82, "plante": 80, "sécheresse": 78},
    "geler": {"gel": 84, "glace": 82, "froid": 80, "hiver": 78},
    "fondre": {"fonte": 84, "glace": 82, "neige": 82, "glacier": 80},
    "brûler": {"feu": 84, "flamme": 82, "incendie": 80, "combustion": 78},
    "exploser": {"explosion": 84, "bombe": 82, "détonation": 80, "dynamite": 78},
    "pleuvoir": {"pluie": 84, "nuage": 82, "averse": 80, "météo": 78},
    "neiger": {"neige": 84, "flocon": 82, "hiver": 80, "chute de neige": 78},
    "trembler": {"tremblement": 84, "séisme": 82, "terre": 78, "secousse": 78},
    "ouvrir": {"porte": 84, "serrure": 82, "ouverture": 82, "clé": 78},
    "fermer": {"porte": 84, "serrure": 82, "fermeture": 82, "clé": 78},
    "allumer": {"lampe": 84, "lumière": 82, "interrupteur": 82, "feu": 78},
    "éteindre": {"lumière": 84, "lampe": 82, "interrupteur": 80, "feu": 78},
    "recevoir": {"courrier": 84, "colis": 82, "réception": 82, "destinataire": 78},
    "envoyer": {"courrier": 84, "message": 82, "expéditeur": 80, "colis": 78},
    "transmettre": {"information": 84, "message": 82, "transmission": 82, "donnée": 78},
    "résoudre": {"problème": 84, "solution": 84, "équation": 82, "énigme": 80},
    "choisir": {"choix": 84, "option": 82, "décision": 80, "préférer": 78},
    "décider": {"décision": 84, "choix": 82, "délibérer": 78, "résolution": 76},
    "comparer": {"comparaison": 84, "différence": 82, "ressemblance": 80, "critère": 78},
    "créer": {"création": 84, "créateur": 82, "œuvre": 80, "artiste": 78},
    "transformer": {"transformation": 84, "changement": 82, "métamorphose": 80, "modifier": 78},
    "développer": {"développement": 84, "progrès": 82, "croissance": 80, "améliorer": 78},
    "proposer": {"proposition": 84, "offre": 82, "suggestion": 80, "candidat": 78},
    "répondre": {"réponse": 84, "question": 82, "répondant": 78, "dialogue": 78},
    "demander": {"question": 84, "demande": 84, "requête": 80, "réponse": 78},
    "expliquer": {"explication": 84, "raison": 82, "enseignant": 78, "comprendre": 78},
    "raconter": {"histoire": 84, "récit": 84, "conte": 82, "narrateur": 80},
    "oublier": {"mémoire": 82, "souvenir": 82, "amnésie": 78, "négligence": 76},
    "accepter": {"accord": 84, "consentement": 82, "refuser": 76, "proposition": 78},
    "refuser": {"refus": 84, "rejeter": 82, "décliner": 80, "accepter": 76},
    "soutenir": {"soutien": 84, "aide": 82, "appuyer": 80, "défendre": 78},
    "rejoindre": {"retrouver": 84, "groupe": 80, "rallier": 78},
    "quitter": {"départ": 84, "abandonner": 82, "partir": 80, "lieu": 76},
    "détruire": {"destruction": 84, "ruine": 82, "démolir": 82, "bâtiment": 80},
    "réduire": {"réduction": 84, "diminuer": 82, "baisser": 80, "quantité": 78},
}

CURATED_DOMAIN_ASSOCIATIONS: Dict[str, Dict[str, int]] = {
    "anatomie": {"corps": 88, "organe": 86, "squelette": 84, "muscle": 82, "médecine": 78},
    "cœur": {"cardiaque": 88, "sang": 84, "artère": 82, "battement": 82, "circulation": 80},
    "cerveau": {"neurone": 88, "mémoire": 84, "intelligence": 82, "crâne": 80, "système nerveux": 80},
    "poumon": {"respiration": 88, "bronche": 86, "oxygène": 84, "thorax": 80, "souffle": 78},
    "rein": {"urine": 86, "néphrologie": 84, "organe": 82, "filtration": 80, "vessie": 78},
    "foie": {"hépatique": 88, "organe": 84, "bile": 82, "digestion": 80, "hépatite": 78},
    "estomac": {"digestion": 88, "gastrique": 84, "intestin": 82, "repas": 78},
    "intestin": {"digestion": 88, "colon": 86, "estomac": 82, "bactérie": 80, "abdomen": 78},
    "os": {"squelette": 88, "fracture": 84, "articulation": 82, "moelle": 80, "calcium": 78},
    "muscle": {"musculaire": 88, "force": 84, "contraction": 82, "tendon": 80, "sport": 78},
    "peau": {"épiderme": 88, "derme": 86, "pore": 82, "toucher": 80, "dermatologie": 78},
    "sang": {"veine": 86, "artère": 86, "circulation": 84, "globule": 84, "hémorragie": 80},
    "médecine": {"médecin": 90, "patient": 86, "diagnostic": 84, "soin": 84, "hôpital": 82, "santé": 80},
    "maladie": {"symptôme": 88, "patient": 86, "diagnostic": 84, "traitement": 84, "infection": 82, "guérison": 80},
    "symptôme": {"maladie": 88, "diagnostic": 86, "fièvre": 84, "douleur": 82, "patient": 80},
    "traitement": {"thérapie": 88, "médicament": 86, "soin": 84, "maladie": 82, "guérison": 80},
    "pharmacie": {"pharmacien": 88, "médicament": 86, "ordonnance": 84, "officine": 84, "comprimé": 80},
    "hôpital": {"médecin": 88, "patient": 86, "infirmier": 84, "chirurgie": 82, "urgence": 82, "clinique": 80},
    "virus": {"infection": 88, "microbe": 86, "épidémie": 84, "maladie": 82, "vaccin": 80},
    "bactérie": {"microbe": 88, "infection": 86, "bactériologie": 84, "antibiotique": 82, "cellule": 78},
    "infection": {"virus": 86, "bactérie": 86, "inflammation": 84, "maladie": 82, "contagion": 80},
    "vaccin": {"vaccination": 90, "immunité": 86, "virus": 84, "prévention": 82, "dose": 78},
    "chirurgie": {"chirurgien": 90, "opération": 88, "hôpital": 84, "anesthésie": 82, "bloc": 78},
    "continent": {"terre": 84, "océan": 82, "pays": 82, "géographie": 88, "frontière": 78},
    "fleuve": {"rivière": 90, "embouchure": 86, "affluent": 86, "delta": 84, "bassin": 80, "eau": 78},
    "rivière": {"fleuve": 90, "cours": 84, "rive": 82, "affluent": 82, "pont": 78},
    "montagne": {"sommet": 88, "altitude": 86, "vallée": 84, "massif": 84, "escalade": 80, "alpinisme": 78},
    "volcan": {"éruption": 90, "lave": 88, "cratère": 86, "magma": 86, "géologie": 82},
    "désert": {"dune": 88, "aridité": 86, "sable": 84, "oasis": 84, "chameau": 78},
    "forêt": {"arbre": 88, "bois": 84, "sylviculture": 84, "faune": 82, "déforestation": 80},
    "lac": {"eau": 84, "rive": 82, "barrage": 80, "poisson": 78, "navigation": 76},
    "nuage": {"ciel": 84, "atmosphère": 82, "vapeur": 82, "pluie": 80, "orage": 80},
    "ordinateur": {"ordinateur portable": 86, "clavier": 84, "écran": 84, "processeur": 82, "logiciel": 82, "souris": 80},
    "internet": {"web": 90, "réseau": 88, "site": 84, "navigateur": 84, "serveur": 82, "connexion": 80},
    "logiciel": {"programme": 88, "application": 86, "ordinateur": 84, "code": 82, "développeur": 80},
    "réseau": {"connexion": 86, "serveur": 84, "internet": 84, "informatique": 82},
    "serveur": {"hébergement": 86, "réseau": 84, "ordinateur": 82, "donnée": 80, "client": 78},
    "robot": {"automate": 90, "robotique": 88, "machine": 84, "capteur": 82, "intelligence artificielle": 80},
    "téléphone": {"portable": 88, "appel": 86, "smartphone": 86, "écran": 78},
    "tablette": {"écran": 84, "tactile": 84, "ordinateur": 82, "application": 80, "numérique": 78},
    "programmation": {"code": 90, "programmeur": 88, "logiciel": 86, "algorithme": 84, "langage": 82},
    "algorithme": {"calcul": 86, "étape": 84, "programme": 84, "informatique": 82, "logique": 80},
    "moteur": {"automobile": 86, "mécanique": 84, "combustion": 82, "véhicule": 80, "puissance": 78},
    "batterie": {"accumulateur": 88, "électricité": 86, "énergie": 84, "pile": 82, "recharge": 80},
    "galaxie": {"univers": 88, "étoile": 86, "voie lactée": 86, "astronomie": 84, "cosmos": 82},
    "étoile": {"astronomie": 88, "constellation": 86, "galaxie": 84, "lumière": 82, "soleil": 80},
    "comète": {"queue": 86, "noyau": 84, "astronomie": 84, "orbite": 82, "glace": 78},
    "nébuleuse": {"gaz": 86, "poussière": 84, "étoile": 82, "astronomie": 84, "galaxie": 80},
    "satellite": {"orbite": 88, "espace": 86, "lune": 84, "télécommunication": 82, "fusée": 78},
    "télescope": {"astronomie": 90, "lunette": 86, "étoile": 84, "observatoire": 84, "optique": 80},
    "atome": {"noyau": 90, "électron": 88, "proton": 86, "neutron": 86, "molécule": 82},
    "molécule": {"atome": 86, "liaison": 84, "chimie": 84, "composé": 82, "formule": 80},
    "réaction": {"chimie": 88, "réactif": 86, "produit": 84, "équation": 82, "transformation": 80},
    "acide": {"base": 84, "pH": 84, "chimie": 82, "corrosif": 80, "solution": 78},
    "métal": {"alliage": 88, "minerai": 84, "métallurgie": 84, "fer": 82, "conducteur": 80},
    "élément": {"atome": 84, "chimie": 82, "tableau périodique": 82, "matière": 80, "substance": 78},
    "lumière": {"optique": 86, "rayon": 84, "soleil": 82, "éclairage": 80},
    "son": {"acoustique": 88, "onde": 86, "fréquence": 84, "vibration": 82, "bruit": 80},
    "chaleur": {"température": 86, "thermique": 84, "énergie": 82, "thermomètre": 80, "dilatation": 78},
    "magnétisme": {"aimant": 90, "champ": 84, "magnétique": 88, "électricité": 82, "boussole": 80},
    "aliment": {"nourriture": 90, "nutrition": 88, "repas": 84, "ingrédient": 82, "cuisine": 80},
    "recette": {"ingrédient": 88, "cuisine": 86, "préparation": 84, "plat": 82, "cuisson": 80},
    "pain": {"boulanger": 88, "farine": 86, "levure": 84, "baguette": 84, "boulangerie": 82},
    "fromage": {"lait": 88, "fromagerie": 86, "affinage": 84, "vache": 80, "crème": 78},
    "viande": {"boucher": 88, "boucherie": 86, "élevage": 82, "protéine": 80, "cuisson": 78},
    "fruit": {"arbre": 82, "verger": 86, "fruitier": 84, "vitamine": 82, "graine": 78},
    "légume": {"potager": 86, "jardinier": 82, "nutrition": 80, "récolte": 80, "racine": 78},
    "épice": {"arôme": 88, "assaisonnement": 86, "cuisine": 84, "poivre": 82, "cannelle": 80},
    "ferme": {"agriculteur": 88, "exploitation": 86, "étable": 84, "champ": 82, "rural": 80},
    "élevage": {"éleveur": 88, "bétail": 86, "ferme": 84, "animal": 82, "pâturage": 80},
    "moisson": {"blé": 88, "récolte": 86, "faucheuse": 84, "céréale": 82, "paysan": 80},
    "semence": {"graine": 90, "semis": 88, "agriculture": 82, "germination": 82, "variété": 78},
    "irrigation": {"eau": 86, "arrosage": 84, "agriculture": 84, "canal": 82, "sécheresse": 80},
    "graine": {"semence": 90, "germination": 86, "plante": 84, "fruit": 80, "semis": 82},
    "fleur": {"pétale": 88, "floraison": 86, "pollinisation": 84, "plante": 82, "bouquet": 80},
    "arbre": {"tronc": 88, "branche": 86, "feuille": 84, "racine": 84, "forêt": 82},
    "racine": {"plante": 86, "tige": 84, "sol": 82, "arbre": 82, "botanique": 80},
    "feuille": {"arbre": 86, "chlorophylle": 84, "photosynthèse": 84, "branche": 82, "plante": 80},
    "pollution": {"polluant": 88, "environnement": 86, "émission": 84, "déchet": 82, "écologie": 80},
    "recyclage": {"déchet": 90, "tri": 86, "réemploi": 86, "environnement": 84, "matière": 80},
    "déchet": {"ordure": 88, "recyclage": 88, "décharge": 86, "tri": 84, "pollution": 80},
    "train": {"gare": 88, "chemin de fer": 88, "wagon": 86, "rail": 84, "locomotive": 82},
    "tramway": {"transport": 86, "rail": 84, "station": 82, "ville": 80, "métro": 78},
    "métro": {"station": 88, "transport": 86, "souterrain": 84, "rame": 82, "ville": 80},
    "vélo": {"cycliste": 88, "pédale": 86, "bicyclette": 86, "guidon": 84, "cyclisme": 82},
    "pont": {"rivière": 82, "fleuve": 82, "ouvrage": 86, "arche": 84, "franchissement": 80},
    "tunnel": {"souterrain": 88, "galerie": 84, "route": 80, "montagne": 78, "chantier": 76},
    "aéroport": {"avion": 90, "piste": 88, "terminal": 86, "vol": 84},
    "navire": {"bateau": 90, "maritime": 86, "marin": 84, "port": 82, "coque": 80},
    "photographie": {"photographe": 90, "appareil": 86, "image": 84, "objectif": 82, "cliché": 80},
    "caméra": {"objectif": 88, "vidéo": 86, "tournage": 84, "image": 82, "cinéma": 80},
    "théâtre": {"comédien": 88, "scène": 86, "pièce": 84, "spectacle": 82, "metteur en scène": 80},
    "acteur": {"comédien": 90, "cinéma": 86, "rôle": 84, "film": 82, "tournage": 80},
    "scène": {"théâtre": 88, "spectacle": 86, "acteur": 84, "décor": 82, "plateau": 80},
    "céramique": {"poterie": 90, "argile": 86, "four": 82, "émaillage": 82, "artisanat": 80},
    "poterie": {"potier": 90, "argile": 86, "céramique": 86, "tour": 82, "vase": 80},
    "danse": {"danseur": 90, "chorégraphie": 88, "ballet": 86, "musique": 82, "mouvement": 80},
    "poésie": {"poème": 90, "poète": 88, "vers": 86, "strophe": 84, "littérature": 82},
    "grammaire": {"syntaxe": 88, "conjugaison": 86, "langue": 86, "orthographe": 84, "linguistique": 82},
    "vocabulaire": {"mot": 88, "lexique": 88, "dictionnaire": 86, "langue": 84, "terme": 82},
    "dictionnaire": {"lexique": 90, "définition": 88, "mot": 86, "vocabulaire": 86, "encyclopédie": 80},
    "traduction": {"traducteur": 90, "langue": 86, "texte": 84, "interprétation": 82, "vocabulaire": 80},
}

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
