import random
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from app.nlp import FRENCH_DICTIONARY, normalize_text

MOTUS_WORD_LENGTH = 6
MOTUS_MAX_ATTEMPTS = 6
MOTUS_DIFFICULTIES = {"facile": 8, "moyen": 6, "difficile": 4}

# Keep answer selection to familiar 6-letter canonical words (singular nouns, adjectives, infinitives).
MOTUS_ANSWERS = frozenset(
    normalize_text(word)
    for word in (
        "abimer", "abuser", "acajou", "accord", "achat", "acteur", "actuel", "adorer",
        "adulte", "agenda", "agneau", "aidant", "aimant", "alarme", "alerte", "alibi",
        "allier", "allonger", "amande", "amener", "amical", "amitie", "amour", "amuser",
        "ananas", "ancien", "animal", "anneau", "annuel", "apache", "apercu", "appeler",
        "apport", "appuyer", "arbitre", "arcade", "archet", "ardent", "argent", "armure",
        "arome", "arreter", "astuce", "atome", "atout", "avaler", "avance", "avenir",
        "aviron", "avocat", "avouer", "bagage", "baigner", "balade", "balai", "balcon",
        "ballon", "bambou", "banane", "banque", "barber", "barque", "barrer", "bassin",
        "bateau", "baton", "battre", "beaute", "bebe", "berger", "besoin", "betail",
        "beurre", "biberon", "bidon", "bijou", "billet", "bistro", "blague", "blason",
        "blesser", "blonde", "blouse", "bobine", "boiser", "boiter", "bomber", "bonbon",
        "bondir", "bonnet", "border", "bottes", "bouche", "boucle", "bouder", "bouger",
        "bougie", "boulon", "ourse", "bourse", "bouton", "boxeur", "branche", "briser",
        "bronze", "brosse", "bruit", "bruler", "brume", "budget", "buffet", "bureau",
        "cabane", "cabine", "cacher", "cadeau", "cadran", "cafard", "cahier", "caillou",
        "caisse", "calcul", "calmer", "camera", "camion", "camper", "canard", "canari",
        "canot", "canton", "canyon", "capote", "captif", "carafe", "caresse", "carnet",
        "carpe", "carton", "casier", "casque", "casser", "castor", "causer", "caverne",
        "caviar", "ceinture", "cellule", "cendre", "centre", "cercle", "cerise", "cerner",
        "cerveau", "chacal", "chacun", "chagrin", "chaine", "chaire", "chaise", "chalet",
        "chaleur", "chameau", "champ", "chance", "change", "chanvre", "chapeau", "charbon",
        "charge", "charme", "chasse", "chaton", "chaud", "chauffer", "chemin", "chenil",
        "cheque", "cherir", "cheval", "cheveu", "chevre", "chiffon", "chimie", "chiot",
        "choeur", "choisir", "chomer", "entrer", "chorus", "ciment", "cinema", "cirque",
        "ciseau", "citron", "civile", "clair", "cloche", "cloner", "cloture", "clouer",
        "cochon", "cocon", "coffre", "cognac", "coiffe", "colere", "coller", "collier",
        "colline", "colombe", "combat", "comble", "comete", "comite", "commun", "compact",
        "compas", "compte", "conflit", "confort", "congel", "connue", "conte", "contre",
        "convive", "copain", "copier", "coque", "corail", "corbeau", "cordon", "cornet",
        "corps", "cosmos", "costume", "coton", "couche", "coude", "coudre", "couler",
        "couloir", "couper", "couple", "courbe", "courir", "couronne", "course", "cousin",
        "coussin", "couteau", "couter", "coutume", "couvrir", "crabe", "crainte", "crampe",
        "crane", "crapaud", "cravate", "crayon", "creche", "credit", "creme", "creuser",
        "crever", "crier", "crime", "criniere", "crique", "crise", "cristal", "croche",
        "croire", "croiser", "croix", "croquer", "croute", "cruche", "cueillir", "cuir",
        "cuire", "cuisine", "cuisse", "cuivre", "culte", "cupide", "curieux", "cuve",
        "cuvette", "cycle", "cygne", "cymbale", "dague", "daigner", "dallage", "damier",
        "danger", "danser", "dauphin", "debat", "outiller", "debut", "decent", "dechet",
        "decider", "declin", "decor", "decret", "dedans", "defaut", "defier", "degel",
        "degout", "degre", "dehors", "delai", "delice", "delire", "deluge", "demain",
        "demence", "demeure", "demon", "durer", "dense", "dentier", "depart", "depend",
        "deplier", "depit", "deposer", "depot", "depute", "deriver", "dernier", "derober",
        "desert", "desir", "dessin", "dessous", "dessus", "destin", "detail", "detente",
        "detour", "dette", "deuil", "devant", "devenir", "deviner", "devis", "devoir",
        "devorer", "diable", "dialogue", "diamant", "dicter", "diete", "dieu", "diffus",
        "digerer", "digne", "digue", "diluer", "dindon", "diner", "diplome", "direct",
        "diriger", "discours", "discret", "disque", "distant", "divan", "divers", "divin",
        "diviser", "divorce", "docile", "docteur", "dogme", "doigt", "domaine", "domino",
        "dompter", "donjon", "donner", "dorure", "dormir", "dossier", "douane", "double",
        "douche", "douceur", "douleur", "douter", "douze", "dragon", "drame", "draper",
        "dresser", "droit", "drole", "duche", "duel", "dune", "duper", "durant",
        "durcir", "duree", "duvet", "ecart", "echange", "echappe", "echec", "echelle",
        "echoir", "eclair", "eclat", "eclipse", "eclore", "ecluse", "ecole", "ecorce",
        "ecouler", "ecoute", "ecran", "ecraser", "ecrire", "ecrou", "ecueil", "ecume",
        "ecurie", "edifice", "editer", "effacer", "effet", "effort", "egal", "egarer",
        "eglise", "egoiste", "elargir", "elever", "elire", "elite", "eloge", "eloigne",
        "email", "emancip", "emballer", "embauche", "embleme", "emeute", "emettre", "emigre",
        "eminent", "emotion", "emousser", "emparer", "empereur", "empire", "emploi", "emporter",
        "emprunt", "encens", "enchere", "enclos", "encre", "endormi", "endroit", "enduire",
        "energie", "enfance", "enfant", "enfer", "enfiler", "enfin", "enfler", "enfoncer",
        "engager", "engin", "enigme", "enjeu", "enlever", "ennemi", "ennui", "enorme",
        "enquete", "enrichi", "enseigne", "ensemble", "ensuite", "entamer", "entente", "enterrer",
        "entier", "entourer", "offrir", "envahir", "envers", "envie", "environ", "envoi",
        "envoler", "epais", "epaule", "epave", "epee", "epice", "epiler", "epine",
        "epingle", "episode", "epoque", "epouse", "epreuve", "epuiser", "equipe", "equite",
        "erable", "erreur", "escale", "esclave", "escorte", "espace", "espece", "esperer",
        "espoir", "esprit", "essayer", "essence", "estime",
        "etable", "etage", "etaler", "etalon", "etang", "etape",
        "eternel", "ethique", "etirer", "etoile", "etonner",
        "etrange", "etroit", "etude", "etudier", "evader", "evaluer",
        "eviter", "evoluer", "evoquer", "exact",
        "examen", "exaucer", "exceder", "exciter", "exclure", "excuse",
        "exemple", "exercer", "exiger", "exiler", "exister",
        "expert", "expirer", "exploit", "exposer",
        "exquis", "extase",
        "facade", "facher", "facile", "faisan", "famille", "famine",
        "fardeau", "farine", "fatigue", "faucon",
        "fausser", "faveur", "favori", "fecond",
        "feminin", "fendre", "fermer", "feroce",
        "fertile", "ferveur", "festin", "fetide", "feutre", "fevrier", "fiable",
        "fiance", "ficher", "fictif", "fidele", "fievre", "figure",
        "filmer", "filtre", "finance",
        "flacon", "flambe", "flamme", "flaner", "flaque",
        "fleche", "flemme", "fleuve", "flocon", "flotte",
        "fluide", "foncer", "fonder", "fondre",
        "forage", "forcer", "forger", "format", "former",
        "fouille", "fouler", "fourbi", "fourmi",
        "fracas", "fraise", "frange", "fraude", "frayer", "frelon",
        "fremir", "friand", "friche", "frimas", "friser",
        "froler", "fronde",
        "fumeur", "fureur",
        "furtif", "fuseau", "fusion", "futile",
        "fuyant", "gacher", "gadget", "gagner", "gaiete", "galant",
        "galere", "galet", "gamme",
        "garage", "garant", "garcon", "garder", "garnir", "gateau",
        "gauche", "gaufre", "gazon",
        "gemeau", "gendre", "genial", "gentil", "gerant", "germer",
        "gibier", "gicler", "gifler", "girafe",
        "glacer", "glacon", "glaive", "glande", "glaner", "global",
        "gloire", "gluant", "gober", "godet",
        "gommer", "gondole", "gorge", "gosier",
        "goujon", "goulot", "gourde", "goutte", "gouter",
        "gradin", "graine", "gramme", "grange", "granit",
        "grappe", "graver", "gravir", "greffe",
        "griffe", "grimper", "grippe", "griser",
        "gronder", "grosse", "grotte", "groupe",
        "guerir", "guerre", "gueule", "guider",
        "guigne", "habile", "hacher",
        "hameau", "hanche", "hangar",
        "hanter", "happer", "hareng", "hasard",
        "hausse", "helice", "heraut",
        "heurter", "hideux",
        "homard", "honnete", "honte", "hoquet",
        "hostile", "houblon", "housse", "hublot", "huiler", "huitre", "humain", "humble",
        "humeur", "humide", "humour", "hurler",
        "idiome", "idole", "ignorer", "iguane",
        "imiter", "immoral", "impact", "impair", "impoli",
        "import", "imposer", "inceste", "inciser", "inciter",
        "inclure", "indice", "indigne", "indique", "inegal", "inerte", "infame",
        "infect", "infime", "infini", "infirme", "influer", "informe", "infuser", "ingrat",
        "inhaler", "initial", "injure", "injuste", "innover", "inonder", "inquiet",
        "insecte", "inserer", "insigne", "insiste", "instant",
        "insulte", "intact", "integre", "intense", "interet", "interne",
        "intime", "intrus", "inutile", "inverse", "inviter", "invoque",
        "ironie", "irriter", "isoler", "ivoire", "jaguar", "jaillir",
        "jaloux", "jamais", "jambon", "jardin", "jargon", "jarret",
        "jasmin", "jauger", "jaunir",
        "jeuner", "joindre", "jonche", "jongler",
        "joueur", "joyeux", "jubiler", "jucher", "jumeau", "jument",
        "jungle", "junior", "juriste", "jusque",
        "juteux", "klaxon", "labeur",
        "labour", "lacher", "lacune", "lagune", "laisser",
        "laiton", "laitue", "lancer",
        "langue", "laquer", "lardon",
        "lasser", "latent", "lavabo", "lavoir", "leader", "lecher",
        "lecteur", "lecture", "legende", "legion", "legume",
        "liberté", "limite", "livrer", "logique", "loisir", "longue", "louer", "lourde",
        "lumiere", "lunette", "lutter", "luxury", "lyceen",
        "macon", "madame", "magie", "maigre", "maille", "maison", "maitre", "majeur",
        "malade", "malice", "maman", "manche", "manege", "manger", "manier", "manoir",
        "manque", "manteau", "manuel", "marais", "marbre", "marche", "mardi", "maree",
        "marge", "marier", "marine", "marque", "marron", "marteau", "masque", "masser",
        "massif", "matin", "matelas", "matiere", "maudit", "mauvais", "maxime", "medecin",
        "mediter", "mefier", "meilleur", "melange", "melodie", "membre", "memoire", "menace",
        "menage", "mener", "mensonge", "menthe", "mentir", "menton", "mepris", "merite",
        "mesure", "metier", "mettre", "meuble", "meute", "miette", "mignon", "milieu",
        "mince", "mineur", "minime", "minute", "miracle", "miroir", "misere", "mobile",
        "modele", "moderne", "modeste", "module", "moelle", "moitie", "moment", "monde",
        "monnaie", "monstre", "monter", "montre", "moquer", "morale", "morceau", "mordre",
        "morsure", "mortel", "moteur", "motif", "moufle", "moulin", "mourir", "mousse",
        "mouton", "mouvoir", "moyen", "muette", "muguet", "muscle", "museau", "musique",
        "mystere", "nageur", "naitre", "nappe", "narine", "nation", "nature", "navire",
        "nectar", "neiger", "nerveux", "nettoyer", "neveu", "nicher", "nickel", "niveau",
        "noble", "noeud", "noirceur", "noiset", "nomade", "nombre", "nommer", "normal",
        "notaire", "notice", "notion", "nouer", "nourrir", "nouveau", "novice", "noyau",
        "noyer", "nuage", "nuance", "nudite", "nuire", "numero", "nuque",
        "obeir", "objet", "obliger", "obscur", "obstacle", "obtenir", "obus", "occasion",
        "occuper", "ocean", "odeur", "odieux", "oeillet", "oeuvre", "offense", "office",
        "offrir", "oignon", "oiseau", "oisif", "olivier", "ombre", "omelette", "omettre",
        "oncle", "ongle", "opale", "opera", "operer", "opinion", "opposer", "optique",
        "oracle", "orage", "orange", "orbite", "ordre", "oreille", "organe", "orgueil",
        "orient", "origine", "orner", "orphelin", "orteil", "ortie", "osier", "otage",
        "otarie", "oubli", "oublier", "ourlet", "ourson", "outil", "outrage", "ouvert",
        "ouvrier", "ouvrir", "ovale", "oxygene", "ozone",
        "pacte", "pagode", "paille", "pain", "palais", "paleur", "palier", "palmier",
        "panier", "panique", "panneau", "panser", "pantin", "papier", "paquet", "parade",
        "paradis", "pardon", "parent", "paresse", "parfait", "parfum", "parier", "parler",
        "parole", "paroi", "parquet", "partage", "partir", "parure", "passer", "passion",
        "pasteur", "patate", "patient", "patiner", "patrie", "patron", "paume", "paupiere",
        "pauvre", "paver", "pavot", "payer", "paysage", "paysan", "peau", "peche",
        "pecher", "pedale", "peigne", "peindre", "peine", "peintre", "pelage", "peler",
        "pelote", "pelouse", "peluche", "pencher", "pendre", "pendule", "penser", "pensee",
        "pension", "pente", "pepite", "percer", "perche", "perdre", "perle", "permettre",
        "permis", "periple", "periode", "perir", "perroquet", "persil", "peser", "petale",
        "petit", "petrole", "peuple", "phare", "phase", "phoque", "photo", "phrase",
        "piano", "piece", "piege", "pierre", "pieton", "pieuvre", "pigeon", "pilier",
        "piller", "pilote", "pilule", "piment", "pinceau", "pincer", "pinte", "pioche",
        "piquer", "pirate", "pisser", "piste", "piston", "pitie", "pivot", "placard",
        "place", "placer", "plafond", "plage", "plaie", "plainte", "plaine", "plaire",
        "plaisir", "planche", "planer", "planete", "plante", "plaque", "platine", "platre",
        "pleurer", "pleuvoir", "plier", "plomb", "plonger", "pluie", "plume", "plupart",
        "poche", "poele", "poeme", "poesie", "poete", "poids", "poignee", "poignet",
        "poil", "point", "pointe", "poire", "poireau", "poison", "poisson", "poitrine",
        "poivre", "polaire", "police", "polir", "pomme", "pommier", "pompe", "pompier",
        "poncer", "pondre", "poney", "ponton", "populaire", "porche", "portail", "porte",
        "porter", "porteur", "portion", "portrait", "poser", "posture", "potage", "poteau",
        "potier", "potion", "pouce", "poudre", "poulain", "poule", "poulet", "poulie",
        "poulpe", "poumon", "poupee", "pourpre", "pousser", "poutre", "pouvoir", "prairie",
        "preface", "premier", "prendre", "prenom", "presque", "presser", "pretexte", "pretre",
        "preuve", "prevoir", "prier", "priere", "prince", "printemps", "priorite", "prise",
        "prison", "priver", "proche", "prodige", "produit", "profil", "profit", "profond",
        "progres", "proie", "projet", "promener", "promesse", "pronom", "propos", "propre",
        "proteger", "prouver", "proverbe", "prudence", "prune", "pruneau", "public", "publier",
        "pudeur", "puiser", "puits", "pull", "pulpe", "punir", "pupille", "purete",
        "puzzle", "pyjama", "python",
        "qualite", "quand", "quartier", "quatre", "quitter", "quota",
        "rabais", "rachat", "racine", "raconter", "radar", "radeau", "radieux", "radis",
        "rafale", "rage", "raide", "raisin", "raison", "ralentir", "rallonge", "ramasser",
        "rameau", "ramer", "rampe", "ramper", "rancune", "ranger", "rapide", "rappel",
        "rapport", "raquette", "rarete", "raser", "rasoir", "rassurer", "rateau", "rater",
        "ration", "ravage", "ravioli", "ravir", "rayer", "rayon", "reagir", "realite",
        "rebelle", "rebond", "rebord", "recette", "recevoir", "rechauffer", "recherche", "recif",
        "recit", "reclame", "recolte", "record", "recours", "recreer", "recrue", "recteur",
        "recul", "reculer", "rediger", "redire", "reduire", "reel", "refaire", "reflet",
        "reflexe", "reforme", "refouler", "refrain", "refuge", "refuser", "regal", "regaler",
        "regard", "regime", "region", "regle", "regler", "regner", "regret", "reine",
        "rejeter", "rejoindre", "relais", "relation", "relever", "relief", "relier", "relire",
        "reluire", "remede", "remettre", "remise", "remonter", "remords", "remorque", "remous",
        "rempart", "remplir", "remuer", "renard", "rendre", "renfort", "renier", "renom",
        "renoncer", "renover", "rentree", "rentrer", "renverser", "renvoi", "repaire", "repas",
        "repasser", "repere", "repeter", "replier", "repondre", "reponse", "report", "repos",
        "reposer", "repousser", "reprise", "reproche", "reptile", "requin", "reseau", "reserve",
        "resider", "resine", "resister", "resoudre", "respect", "respirer", "ressort", "reste",
        "rester", "resultat", "resumer", "retard", "retenir", "retirer", "retomber", "retour",
        "retrait", "retraite", "retrouver", "reunion", "reunir", "reussir", "revanche", "reve",
        "reveil", "reveler", "revendre", "revenir", "revenu", "rever", "revers", "revetir",
        "reveur", "revoir", "revolte", "revue", "rhume", "ruban", "ricaner", "riche",
        "rideau", "ridicule", "rien", "rigide", "rigoler", "rigueur", "rimer", "rincer",
        "riposte", "risque", "risquer", "rituel", "rivage", "rival", "riviere", "robe",
        "robinet", "robot", "robuste", "roche", "rocher", "roder", "rogner", "roman",
        "rompre", "ronce", "ronde", "ronfler", "ronger", "rosier", "rossignol", "rotir",
        "rouage", "rouble", "roue", "rouge", "rougir", "rouille", "rouler", "rouleau",
        "roulis", "route", "routine", "royal", "royaume", "rubis", "ruche", "rude",
        "ruelle", "ruer", "rugby", "rugir", "ruine", "ruiner", "ruisseau", "rumeur",
        "ruminer", "rupture", "rural", "ruse", "rustre", "rythme",
        "sable", "sablier", "sabot", "sabre", "sachet", "sacrer", "sagesse", "saisir",
        "saison", "salade", "salaire", "saler", "saleté", "salir", "salive", "salle",
        "salon", "saluer", "salut", "samedi", "sandale", "sanglot", "sangle", "sante",
        "sapin", "sardine", "satin", "satire", "sauce", "saucisse", "sauge", "saule",
        "saumon", "sauter", "sauvage", "sauver", "savant", "saveur", "savoir", "savon",
        "scandale", "scarabee", "sceau", "scene", "sceptre", "schema", "science", "scier",
        "scinder", "score", "scorpion", "scout", "scruter", "sculpter", "seance", "seau",
        "secher", "second", "secouer", "secours", "secousse", "secret", "secteur", "section",
        "seduire", "sejour", "select", "seller", "semaine", "sembler", "semelle", "semence",
        "semer", "semis", "senat", "sens", "sentier", "sentir", "separer", "sergent",
        "serie", "serieux", "serment", "sermon", "serpent", "serrer", "serrure", "serveur",
        "service", "servir", "seuil", "seul", "severe", "sevir", "sevrer", "short",
        "siecle", "siege", "sieste", "siffler", "signal", "signer", "silence", "sillon",
        "simple", "sincere", "singe", "sinon", "sinueux", "siphon", "sirene", "sirop",
        "site", "situer", "skieur", "slogan", "sobre", "social", "societe", "socle",
        "soeur", "soie", "soif", "soigner", "soir", "soiree", "soldat", "solde",
        "soleil", "solide", "solitude", "sombre", "somme", "sommeil", "sommet", "sonde",
        "sonder", "songe", "songer", "sonner", "sonore", "sorcier", "sorte", "sortie",
        "sortir", " sottise", "souci", "soucier", "soudain", "souder", "souffle", "souffrir",
        "souhait", "souiller", "soulager", "soulever", "soulier", "soumettre", "soupcon", "soupe",
        "souper", "soupir", "souple", "source", "sourcil", "sourd", "sourire", "souris",
        "soutien", "souvenir", "souvent", "soyeux", "spatial", "special", "spectre", "sphere",
        "sphinx", "spirale", "sport", "sportif", "square", "stade", "stage", "stand",
        "statue", "statut", "steak", "steppe", "sterile", "stocker", "stopper", "store",
        "stress", "strict", "strophe", "studio", "stupide", "style", "stylo", "suave",
        "subir", "subit", "sublime", "subtil", "succes", "sucer", "sucre", "sucrer",
        "sueur", "suffire", "suffixe", "suicider", "suie", "suinter", "suisse", "suite",
        "suivant", "suivre", "sujet", "sultan", "superbe", "supplice", "support", "supposer",
        "supreme", "surete", "surface", "surfer", "surgir", "surmonter", "surnom", "surprise",
        "sursaut", "surtout", "survie", "suspect", "syllabe", "symbole", "syndicat", "syntaxe",
        "systeme",
        "tacher", "taille", "talent", "tambour", "tamiser", "tanner", "tarder", "tardif",
        "tasser", "tatouer", "taureau", "taverne", "teindre", "temoin", "temple", "tendre",
        "teneur", "tennis", "tenter", "ternir", "terrain", "terreur", "terrier", "tester",
        "tetard", "ticket", "timbre", "timide", "tinter", "tirade", "tirage", "tiroir",
        "tisane", "tisser", "tituber", "tocsin", "toiser", "toiture", "tolerer", "tomate",
        "tomber", "tombeau", "tondre", "tonneau", "tonner", "tonton", "topaze", "toquer",
        "torche", "tordre", "tornade", "torpeur", "torrent", "tortue", "toucher", "touffe",
        "toupet", "toupie", "tourbe", "tourner", "tournoi", "tourte", "tousser", "toxine",
        "tracer", "trafic", "trahir", "trainer", "traire", "traiter", "trajet", "tranche",
        "transit", "trappe", "traquer", "travail", "travers", "travee", "trefle", "treize",
        "tremble", "tremper", "trente", "trepied", "tresor", "tresse", "treuil", "tribun",
        "tricher", "tricot", "trimer", "tringle", "trinite", "triple", "tripler", "triste",
        "trompe", "trophee", "trotter", "trouer", "troupe", "trousse", "trouver", "truand",
        "truche", "truffe", "truite", "tsunami", "tuerie", "tulipe", "tumeur", "tumulte",
        "tunique", "tunnel", "turbine", "turban", "tuteur", "tympan", "typhon", "ulcere",
        "ultime", "unifier", "unique", "urgent", "usager", "utopie", "vacance", "vaccin",
        "vaincre", "valeur", "valide", "valise", "vallee", "valoir", "valser", "vampire",
        "vanille", "vanite", "vanter", "vapeur", "varier", "varice", "vasque", "vassal",
        "vautour", "vecteur", "vedette", "vegetal", "veiller", "velours", "vendre", "venerer",
        "venger", "venter", "ventre", "verdict", "verdure", "verger", "verglas", "verite",
        "vermeil", "vermine", "vernis", "verrou", "verser", "verset", "version", "vertige",
        "vessie", "vestige", "veteran", "viaduc", "viande", "vibrer", "vicaire", "victime",
        "vierge", "vigile", "vigueur", "vilain", "village", "violon", "vipere", "virage",
        "virgule", "virtuel", "visage", "visible", "vision", "visite", "visser", "visuel",
        "vitesse", "vitrail", "vitrine", "vivace", "vivant", "vivier", "voguer", "voiler",
        "voisin", "voiture", "volage", "volant", "volcan", "voleur", "volonte", "volume",
        "vorace", "vouloir", "voyage", "voyant", "voyelle", "vulgaire", "whisky", "yaourt",
        "zenith", "zigzag",
    )
    if len(normalize_text(word)) == MOTUS_WORD_LENGTH
    and re.fullmatch(r"[a-z]+", normalize_text(word))
    and normalize_text(word) in FRENCH_DICTIONARY
)


def evaluate_guess(guess: str, target: str) -> List[str]:
    """Return Wordle-style letter marks, accounting for repeated letters."""
    feedback = ["absent"] * len(target)
    remaining: Dict[str, int] = {}

    for index, (letter, answer_letter) in enumerate(zip(guess, target)):
        if letter == answer_letter:
            feedback[index] = "correct"
        else:
            remaining[answer_letter] = remaining.get(answer_letter, 0) + 1

    for index, letter in enumerate(guess):
        if feedback[index] == "correct":
            continue
        if remaining.get(letter, 0):
            feedback[index] = "present"
            remaining[letter] -= 1

    return feedback


@dataclass
class MotusPlayer:
    player_id: str
    name: str
    guesses: List[Dict[str, Any]] = field(default_factory=list)
    solved: bool = False
    finished: bool = False
    score: int = 0
    connected: bool = True
    is_spectator: bool = False

    def submit(
        self,
        raw_guess: str,
        target: str,
        dictionary: set[str],
        max_attempts: int = MOTUS_MAX_ATTEMPTS,
    ) -> Dict[str, Any]:
        guess = normalize_text(raw_guess.strip())
        if not re.fullmatch(r"[a-z]+", guess):
            raise ValueError("Utilisez uniquement des lettres.")
        if len(guess) != len(target):
            raise ValueError(f"Le mot doit contenir {len(target)} lettres.")
        if guess[0] != target[0]:
            raise ValueError(f"Le mot doit commencer par la lettre « {target[0].upper()} ».")
        if guess not in dictionary:
            raise ValueError("Ce mot n'est pas reconnu dans le dictionnaire français.")
        if self.finished:
            raise ValueError("Vous avez déjà terminé cette partie.")
        if guess in {item["word"] for item in self.guesses}:
            raise ValueError("Vous avez déjà proposé ce mot.")

        feedback = evaluate_guess(guess, target)
        self.guesses.append({"word": guess, "feedback": feedback})
        self.solved = guess == target
        self.finished = self.solved or len(self.guesses) >= max_attempts
        if self.solved:
            self.score = (max_attempts - len(self.guesses) + 1) * 100

        return {
            "word": guess,
            "feedback": feedback,
            "solved": self.solved,
            "finished": self.finished,
            "score": self.score,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "guesses": self.guesses,
            "solved": self.solved,
            "finished": self.finished,
            "score": self.score,
            "attempts": len(self.guesses),
            "connected": self.connected,
            "is_spectator": self.is_spectator,
        }


@dataclass
class MotusGame:
    game_id: str
    target: str
    player: MotusPlayer
    difficulty: str = "moyen"
    status: str = "playing"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "status": self.status,
            "word_length": len(self.target),
            "max_attempts": MOTUS_DIFFICULTIES[self.difficulty],
            "difficulty": self.difficulty,
            "first_letter": self.target[0].upper(),
            "target": self.target.upper() if self.player.finished else None,
            "player": self.player.to_dict(),
        }


@dataclass
class MotusRoom:
    room_id: str
    target: str
    host_player_id: str
    difficulty: str = "moyen"
    players: Dict[str, MotusPlayer] = field(default_factory=dict)
    status: str = "lobby"
    started_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    match_number: int = 1
    stats_recorded: bool = False

    def to_dict(self, player_id: str) -> Dict[str, Any]:
        player = self.players[player_id]
        players = []
        for item in self.players.values():
            player_state = item.to_dict()
            if item.player_id != player_id:
                player_state["guesses"] = []
            players.append(player_state)
        return {
            "room_id": self.room_id,
            "status": self.status,
            "match_number": self.match_number,
            "host_player_id": self.host_player_id,
            "word_length": len(self.target),
            "max_attempts": MOTUS_DIFFICULTIES[self.difficulty],
            "difficulty": self.difficulty,
            "first_letter": self.target[0].upper(),
            "target": self.target.upper() if self.status == "finished" else None,
            "player": player.to_dict(),
            "players": players,
            "player_count": sum(not item.is_spectator for item in self.players.values()),
            "spectator_count": sum(item.is_spectator for item in self.players.values()),
            "can_start": self.status == "lobby"
            and sum(not item.is_spectator for item in self.players.values()) >= 2,
            "can_restart": self.status == "finished" and player_id == self.host_player_id,
            "restart_available": self.status == "finished",
        }


class MotusManager:
    def __init__(
        self,
        words: Optional[Iterable[str]] = None,
        answers: Optional[Iterable[str]] = None,
    ):
        self.dictionary = {
            normalize_text(word)
            for word in (words if words is not None else FRENCH_DICTIONARY)
            if re.fullmatch(r"[a-z]{6}", normalize_text(word))
        }
        self.answers = sorted(
            {
                normalize_text(word)
                for word in (answers if answers is not None else MOTUS_ANSWERS)
                if normalize_text(word) in self.dictionary
            }
        )
        if not self.answers:
            raise ValueError("La liste de réponses Motus ne contient aucun mot reconnu.")
        self.solo_games: Dict[str, MotusGame] = {}
        self.rooms: Dict[str, MotusRoom] = {}
        self._lock = threading.RLock()

    def _pick_target(self) -> str:
        return random.choice(self.answers)

    @staticmethod
    def _validate_difficulty(difficulty: str) -> str:
        if difficulty not in MOTUS_DIFFICULTIES:
            raise ValueError("Difficulté invalide. Choisissez facile, moyen ou difficile.")
        return difficulty

    def create_solo(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> MotusGame:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            player = MotusPlayer(player_id=player_id, name=player_name)
            game = MotusGame(
                game_id=uuid.uuid4().hex,
                target=self._pick_target(),
                player=player,
                difficulty=difficulty,
            )
            self.solo_games[game.game_id] = game
            return game

    def get_solo(self, game_id: str, player_id: str) -> MotusGame:
        with self._lock:
            game = self.solo_games.get(game_id)
            if not game or game.player.player_id != player_id:
                raise KeyError("Cette partie solo est introuvable.")
            return game

    def guess_solo(self, game_id: str, player_id: str, guess: str) -> tuple[MotusGame, Dict[str, Any]]:
        with self._lock:
            game = self.get_solo(game_id, player_id)
            result = game.player.submit(
                guess,
                game.target,
                self.dictionary,
                MOTUS_DIFFICULTIES[game.difficulty],
            )
            if game.player.finished:
                game.status = "finished"
            return game, result

    def create_room(
        self, player_id: str, player_name: str, difficulty: str = "moyen"
    ) -> MotusRoom:
        with self._lock:
            difficulty = self._validate_difficulty(difficulty)
            room_id = uuid.uuid4().hex[:6].upper()
            while room_id in self.rooms:
                room_id = uuid.uuid4().hex[:6].upper()
            room = MotusRoom(
                room_id=room_id,
                target=self._pick_target(),
                host_player_id=player_id,
                difficulty=difficulty,
            )
            room.players[player_id] = MotusPlayer(player_id=player_id, name=player_name)
            self.rooms[room_id] = room
            return room

    def join_room(self, room_id: str, player_id: str, player_name: str) -> MotusRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room:
                raise KeyError("Salon introuvable ou expiré.")
            if player_id in room.players:
                room.players[player_id].connected = True
                room.players[player_id].name = player_name
                return room
            if room.status == "playing":
                if len(room.players) >= 8:
                    raise ValueError("Ce salon est complet (8 joueurs maximum).")
                room.players[player_id] = MotusPlayer(
                    player_id=player_id, name=player_name, is_spectator=True
                )
                return room
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà commencé. Seuls les joueurs déjà inscrits peuvent revenir.")
            if len(room.players) >= 8:
                raise ValueError("Ce salon est complet (8 joueurs maximum).")
            room.players[player_id] = MotusPlayer(player_id=player_id, name=player_name)
            return room

    def get_room(self, room_id: str, player_id: str) -> MotusRoom:
        with self._lock:
            room = self.rooms.get(room_id.upper())
            if not room or player_id not in room.players:
                raise KeyError("Salon ou joueur introuvable.")
            return room

    def list_rooms(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "room_id": room.room_id,
                    "status": room.status,
                    "player_count": sum(
                        not player.is_spectator for player in room.players.values()
                    ),
                    "spectator_count": sum(
                        player.is_spectator for player in room.players.values()
                    ),
                    "host_name": room.players[room.host_player_id].name,
                    "difficulty": room.difficulty,
                    "is_member": player_id in room.players if player_id else False,
                }
                for room in self.rooms.values()
                if room.status != "finished"
            ]

    def start_room(self, room_id: str, player_id: str) -> MotusRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut démarrer la partie.")
            if room.status != "lobby":
                raise ValueError("Cette partie a déjà démarré.")
            if sum(not player.is_spectator for player in room.players.values()) < 2:
                raise ValueError("Il faut au moins deux joueurs pour démarrer.")
            room.status = "playing"
            room.started_at = time.time()
            room.stats_recorded = False
            return room

    def restart_room(self, room_id: str, player_id: str) -> MotusRoom:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.host_player_id != player_id:
                raise PermissionError("Seul l'hôte peut redémarrer la partie.")
            if room.status != "finished":
                raise ValueError("La partie doit être terminée pour être redémarrée.")
            room.target = self._pick_target()
            room.match_number += 1
            for player in room.players.values():
                player.guesses.clear()
                player.solved = False
                player.finished = False
                player.score = 0
                player.is_spectator = False
            room.status = "playing"
            room.started_at = time.time()
            room.stats_recorded = False
            return room

    def guess_room(self, room_id: str, player_id: str, guess: str) -> tuple[MotusRoom, Dict[str, Any]]:
        with self._lock:
            room = self.get_room(room_id, player_id)
            if room.status != "playing":
                raise ValueError("La partie n'est pas en cours.")
            if room.players[player_id].is_spectator:
                raise ValueError("Les spectateurs ne peuvent pas proposer de mot.")
            result = room.players[player_id].submit(
                guess,
                room.target,
                self.dictionary,
                MOTUS_DIFFICULTIES[room.difficulty],
            )
            if all(
                player.finished
                for player in room.players.values()
                if not player.is_spectator
            ):
                room.status = "finished"
            return room, result


motus_manager = MotusManager()
