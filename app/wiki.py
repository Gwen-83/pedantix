import os
import urllib.request
import urllib.parse
import urllib.error
import json
import re
import random
import time
import logging
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup

logger = logging.getLogger("pedantix.wiki")

USER_AGENT = os.environ.get("PEDANTIX_USER_AGENT", "PedantixGame/2.0 (https://github.com/pedantix; pedantix-game@pedantix.org)")

# Minimum number of translation languages required to consider an article sufficiently well-known
DEFAULT_MIN_ARTICLE_LANGUAGES = int(os.environ.get("PEDANTIX_MIN_LANGUAGES", "25"))

# Strict notability criteria for biography / person articles (to prevent obscure athletes, regional figures, etc.)
DEFAULT_MIN_PERSON_LANGUAGES = int(os.environ.get("PEDANTIX_MIN_PERSON_LANGUAGES", "50"))
DEFAULT_MIN_PERSON_LANGUAGES_REGIONAL = int(os.environ.get("PEDANTIX_MIN_PERSON_LANGUAGES_REGIONAL", "28"))
DEFAULT_MIN_PERSON_PAGEVIEWS = int(os.environ.get("PEDANTIX_MIN_PERSON_PAGEVIEWS", "3000"))
DEFAULT_MIN_GENERAL_PAGEVIEWS = int(os.environ.get("PEDANTIX_MIN_GENERAL_PAGEVIEWS", "1000"))

# Difficulty presets specifying language translations, 90-day pageviews, word count, and pool distribution
DIFFICULTY_LEVELS = {
    "facile": {
        "id": "facile",
        "name": "Facile",
        "icon": "🟢",
        "min_languages": 45,
        "min_pageviews_90d": 20000,
        "min_general_pageviews_60d": 13500,
        "min_person_languages": 65,
        "min_person_languages_regional": 35,
        "min_person_pageviews_90d": 30000,
        "min_person_pageviews_60d": 20000,
        "min_words": 90,
        "curated_pool_prob": 0.75,
        "description": "Sujets très célèbres et incontournables (≥ 45 langues, ≥ 20k vues)"
    },
    "moyen": {
        "id": "moyen",
        "name": "Moyen",
        "icon": "🟡",
        "min_languages": 28,
        "min_pageviews_90d": 4000,
        "min_general_pageviews_60d": 2700,
        "min_person_languages": 45,
        "min_person_languages_regional": 28,
        "min_person_pageviews_90d": 4500,
        "min_person_pageviews_60d": 3000,
        "min_words": 65,
        "curated_pool_prob": 0.35,
        "description": "Culture générale classique (≥ 28 langues, ≥ 4k vues)"
    },
    "difficile": {
        "id": "difficile",
        "name": "Difficile",
        "icon": "🔴",
        "min_languages": 18,
        "min_pageviews_90d": 1500,
        "min_general_pageviews_60d": 1000,
        "min_person_languages": 30,
        "min_person_languages_regional": 20,
        "min_person_pageviews_90d": 2500,
        "min_person_pageviews_60d": 1700,
        "min_words": 50,
        "curated_pool_prob": 0.0,
        "description": "Sujets plus pointus ou spécialisés (≥ 18 langues, ≥ 1.5k vues)"
    }
}
DIFFICULTY_CONFIGS = DIFFICULTY_LEVELS

# Curated lists of iconic articles by category (universally known subjects)
THEMES_ARTICLES = {
    "histoire": [
        "Révolution française", "Empire romain", "Moyen Âge", "Première Guerre mondiale",
        "Seconde Guerre mondiale", "Guerre froide", "Renaissance", "Égypte antique",
        "Grèce antique", "Siècle des Lumières", "Débarquement de Normandie",
        "Chute du mur de Berlin", "Révolution industrielle", "Guerre de Cent Ans",
        "Traité de Versailles", "Déclaration des droits de l'homme et du citoyen de 1789",
        "Pompéi", "Croisades", "Guerre de Sécession", "Empire byzantin", "Bataille de Waterloo",
        "Bataille de Marignan", "Prise de la Bastille", "Guerre du Viêt Nam", "Guerre de Troie",
        "Empire ottoman", "Guerre des Gaules", "Révolution russe", "Affaire Dreyfus",
        "Bataille de Verdun", "Chute de Constantinople", "Guerre d'Espagne", "Guerre de Corée"
    ],
    "geographie": [
        "France", "Japon", "Brésil", "Islande", "Australie", "Canada", "Égypte",
        "Italie", "Inde", "Madagascar", "Mont Blanc", "Himalaya", "Sahara",
        "Forêt amazonienne", "Océan Pacifique", "Nil", "Mer Méditerranée", "Grand Canyon",
        "Antarctique", "Groenland", "Île de Pâques", "Tokyo", "Venise", "New York",
        "Londres", "Paris", "Rome", "Berlin", "Grèce", "Espagne", "Portugal",
        "Suisse", "Norvège", "Mexique", "Chine", "Russie", "États-Unis", "Royaume-Uni",
        "Océan Atlantique", "Mont Everest", "Mer Rouge", "Fleuve Amazone", "Kilimandjaro"
    ],
    "sciences": [
        "Système solaire", "Trou noir", "Voie lactée", "Mars (planète)", "Lune",
        "Big Bang", "Théorie de la relativité", "Atome", "Mécanique quantique",
        "Vitesse de la lumière", "Acide désoxyribonucléique", "Photosynthèse",
        "Évolution (biologie)", "Cerveau humain", "Radioactivité", "Gravitation",
        "Tableau périodique des éléments", "Télescope spatial James-Webb", "Étoile à neutrons",
        "Jupiter (planète)", "Soleil", "Terre", "Génétique", "Vaccin", "Pénicilline",
        "Théorie du chaos", "Énergie nucléaire", "Électron", "Dinosaure", "Laser",
        "Thermodynamique", "Tectonique des plaques", "Astéroïde", "Comète"
    ],
    "monuments": [
        "Tour Eiffel", "Musée du Louvre", "Cathédrale Notre-Dame de Paris",
        "Château de Versailles", "Pyramides de Gizeh", "Colisée", "Grande Muraille de Chine",
        "Taj Mahal", "Statue de la Liberté", "Sagrada Família", "Mont-Saint-Michel",
        "Acropole d'Athènes", "Machu Picchu", "Stonehenge", "Parthénon", "Tour de Pise",
        "Château de Chambord", "Arc de triomphe de l'Étoile", "Big Ben", "Opéra de Sydney",
        "Basilique Saint-Pierre", "Empire State Building", "Golden Gate Bridge",
        "Alhambra (Grenade)", "Angkor Wat", "Pont du Gard", "Sainte-Sophie (Istanbul)"
    ],
    "biographies": [
        "Albert Einstein", "Marie Curie", "Léonard de Vinci", "Victor Hugo",
        "Jeanne d'Arc", "Molière", "Napoléon Ier", "Louis XIV", "Charles de Gaulle",
        "Isaac Newton", "Charles Darwin", "Wolfgang Amadeus Mozart", "Ludwig van Beethoven",
        "Vincent van Gogh", "Claude Monet", "William Shakespeare", "Jules Verne",
        "Cléopâtre VII", "Alexandre le Grand", "Galilée (savant)", "Aristote",
        "Socrate", "Jules César", "Mahatma Gandhi", "Nelson Mandela", "Martin Luther King",
        "Pablo Picasso", "Jean-Jacques Rousseau", "Voltaire", "Sigmund Freud",
        "Christophe Colomb", "Marco Polo", "Louis Pasteur", "Frida Kahlo", "Jean Moulin",
        "Zinédine Zidane", "Carl Lewis", "Usain Bolt", "Michael Jackson", "Charlie Chaplin",
        "Coluche", "Alain Chabat", "Thomas Pesquet", "Simone Veil", "Georges Brassens",
        "Édith Piaf", "Jacques Brel", "Charles Aznavour", "Louis de Funès", "Jean Reno",
        "Stephen Hawking", "Nikola Tesla", "Archimède", "Michel-Ange", "Auguste Rodin",
        "Jean de La Fontaine", "Émile Zola", "Albert Camus", "Antoine de Saint-Exupéry",
        "Gustave Flaubert", "Honoré de Balzac", "Alexandre Dumas", "Arthur Rimbaud", "Charles Baudelaire"
    ],
    "arts_culture": [
        "La Joconde", "Impressionnisme", "Cinéma", "Photographie", "Bande dessinée",
        "Star Wars", "Le Seigneur des anneaux", "Hayao Miyazaki", "Titanic (film, 1997)",
        "Harry Potter", "Jazz", "Opéra", "Guernica (Picasso)", "Festival de Cannes",
        "Guitare", "Sculpture", "Théâtre", "Rock", "La Nuit étoilée", "Le Roi lion",
        "Peinture (art)", "Architecture", "Poterie", "Danse", "Violon", "Piano"
    ],
    "nature": [
        "Baleine bleue", "Loup gris", "Lion", "Grand requin blanc", "Tigre",
        "Éléphant", "Manchot empereur", "Pieuvre", "Abeille", "Dinosaure",
        "Tyrannosaure", "Mammouth", "Séquoia géant", "Corail", "Panda géant",
        "Girafe", "Dauphin", "Chauve-souris", "Ours polaire", "Aigle royal",
        "Guépard", "Caméléon", "Gorille", "Chimpanzé", "Kangourou", "Koala"
    ],
    "tech_jeux": [
        "Internet", "Intelligence artificielle", "Ordinateur", "Jeu d'échecs",
        "Jeu de go", "Nintendo", "Robotique", "Téléphone mobile", "Énergie solaire",
        "Horloge", "Imprimerie", "Microscope", "Satellite artificiel", "Web",
        "Jeux olympiques", "Football", "Tennis", "Jeux vidéo", "Cryptographie",
        "Roue", "Boussole", "Moteur à combustion interne", "Avion", "Automobile"
    ],
    "litterature": [
        "Les Misérables", "Le Petit Prince", "L'Étranger", "Odyssée",
        "Don Quichotte", "Philosophie", "Platon", "René Descartes",
        "Mythologie grecque", "Conte de fées", "Iliade", "Fables de La Fontaine",
        "Roméo et Juliette", "Hamlet", "Vingt Mille Lieues sous les mers",
        "Madame Bovary", "Le Rouge et le Noir", "Germinal (roman)", "L'Avare"
    ]
}

# Master list of all curated iconic articles
ALL_CURATED_TITLES = []
for articles in THEMES_ARTICLES.values():
    ALL_CURATED_TITLES.extend(articles)
ALL_CURATED_TITLES = list(dict.fromkeys(ALL_CURATED_TITLES))


def clean_html_extract(html_text: str) -> List[str]:
    """Cleans Wikipedia HTML extract into readable paragraphs without phonetic or reference junk."""
    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    paragraphs = []

    for p in soup.find_all("p"):
        raw = p.get_text()
        if not raw:
            continue

        # Remove phonetic transcriptions like [tuʁɛfɛl] or [/tuʁɛfɛl/]
        cleaned = re.sub(r'\[[^\w\s]*[a-zà-ÿ0-9 /:,.œæɑɛɔøœə̃ʁʃʒɲŋʔ\-\'\’]+\]', '', raw)
        # Remove footnote numbers [1], [note 1], [réf. nécessaire]
        cleaned = re.sub(r'\[\s*(?:\d+|note\s+\d+|réf\.[^\]]*)\s*\]', '', cleaned)
        # Remove audio play indicators (écouter)
        cleaned = re.sub(r'\(\s*écouter\s*\)', '', cleaned)
        # Normalize whitespace and non-breaking spaces
        cleaned = cleaned.replace('\xa0', ' ').replace('\u202f', ' ')
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Discard microscopic or empty paragraphs
        if len(cleaned) >= 25:
            paragraphs.append(cleaned)

    return paragraphs


def count_article_words(paragraphs: List[str]) -> int:
    """Counts the total number of words across all paragraphs."""
    if not paragraphs:
        return 0
    return sum(len(re.findall(r'\b\w+\b', p)) for p in paragraphs)


BIO_ROLES = [
    'homme politique', 'femme politique', 'homme d\'État', 'femme d\'État',
    'écrivain', 'écrivaine', 'acteur', 'actrice', 'chanteur', 'chanteuse',
    'musicien', 'musicienne', 'joueur', 'joueuse', 'sportif', 'sportive',
    'scientifique', 'général', 'roi', 'reine', 'président', 'présidente',
    'compositeur', 'compositrice', 'poète', 'poétesse', 'athlète', 'footballeur',
    'footballeuse', 'cycliste', 'souverain', 'souveraine', 'cinéaste', 'réalisateur',
    'réalisatrice', 'sculpteur', 'sculptrice', 'peintre', 'dramaturge', 'romancier',
    'romancière', 'médecin', 'biologiste', 'physicien', 'physicienne', 'chimiste',
    'mathématicien', 'mathématicienne', 'militaire', 'avocat', 'avocate', 'journaliste',
    'navigateur', 'navigatrice', 'explorateur', 'exploratrice', 'philosophe',
    'homme d\'affaires', 'femme d\'affaires', 'animateur', 'animatrice', 'humoriste',
    'militant', 'militante', 'évêque', 'archevêque', 'cardinal', 'pape', 'prince',
    'princesse', 'duc', 'duchesse', 'empereur', 'impératrice', 'seigneur', 'architecte',
    'historien', 'historienne', 'personnage', 'héros', 'héroïne', 'personnalité',
    'théologien', 'universitaire', 'chancelier', 'chancelière', 'ministre',
    'premier ministre', 'première ministre', 'sénateur', 'sénatrice', 'député',
    'députée', 'maréchal', 'amiral', 'pilote', 'astronaute', 'cosmonaute', 'spationaute',
    'rugbyman', 'basketteur', 'basketteuse', 'nageur', 'nageuse', 'skieur', 'skieuse',
    'boxeur', 'boxeuse', 'tennisman', 'mannequin', 'photographe', 'dessinateur',
    'dessinatrice', 'scénariste'
]

BIO_REGEX = re.compile(
    r'\b(?:est|était|fut)\s+(?:un|une)\s+(?:ancien\s+|ancienne\s+|célèbre\s+)?(?:' + '|'.join(BIO_ROLES) + r')\b',
    re.IGNORECASE
)

INVERTED_ARTICLES = {
    'le', 'la', 'les', "l'", 'un', 'une', 'des', 'du',
    'the', 'a', 'an', 'der', 'die', 'das', 'dem', 'den',
    'el', 'il', 'lo', 'los', 'las', 'gli', 'i'
}

NON_PERSON_WORDS = [
    'bataille', 'traité', 'commune', 'église', 'canton', 'rue', 'avenue',
    'boulevard', 'gare', 'pont', 'château', 'parc', 'lac', 'musée', 'famille',
    'parti', 'société', 'compagnie', 'groupe', 'île', 'îlot', 'mont', 'col',
    'vallée', 'rivière', 'fleuve', 'baie', 'golfe', 'cap', 'forêt', 'station',
    'canal', 'mer', 'océan', 'village', 'ville', 'royaume', 'dynastie',
    'abbaye', 'cathédrale', 'monastère', 'hôtel', 'palais', 'guerre', 'loi',
    'planète', 'étoile', 'galaxie', 'université', 'stade', 'aéroport', 'théâtre',
    'opéra', 'sympathie', 'théorie', 'principe', 'syndrome', 'maladie', 'accord',
    'concile', 'massacre', 'sommet', 'fondation', 'académie'
]


def is_person_article(title: str, pageprops: Dict[str, Any], html_extract: str) -> bool:
    """
    Determines whether a Wikipedia article represents a person (biography) or character.
    Uses microformats, birth/death patterns, biography vocabulary, defaultsort, and title patterns.
    """
    # 0. Title parenthetical indicates occupation or character disambiguation
    parenthetical = re.search(r'\(([^)]+)\)$', title)
    if parenthetical:
        p_content = parenthetical.group(1).lower()
        if any(r in p_content for r in [
            'chanteur', 'chanteuse', 'acteur', 'actrice', 'footballeur', 'football',
            'rugby', 'cyclisme', 'athlétisme', 'tennis', 'natation', 'basket-ball',
            'écrivain', 'peintre', 'sculpteur', 'sculptrice', 'compositeur', 'compositrice',
            'musicien', 'musicienne', 'politique', 'homme politique', 'femme politique',
            'personnalité', 'personnage', 'historien', 'philosophe', 'scientifique',
            'médecin', 'militaire', 'général', 'amiral', 'évêque', 'archevêque',
            'cardinal', 'animateur', 'humoriste', 'réalisateur'
        ]):
            return True

    # 1. Semantic microformats for birth/death dates (Wikipedia biographical infoboxes)
    if 'bday' in html_extract or 'dday' in html_extract:
        return True

    # 2. Extract clean lead text
    clean_paras = clean_html_extract(html_extract)
    lead_text = clean_paras[0] if clean_paras else ""

    # 2b. Inanimate work / object guard: e.g. "La Joconde ... est un tableau"
    if re.search(
        r'\b(?:est|était|fut)\s+(?:un|une)\s+(?:tableau|peinture|film|série|roman|chanson|album|jeu|livre|sculpture|opéra)\b',
        lead_text,
        re.IGNORECASE
    ):
        return False

    # 3. Explicit birth or death mentions in the lead
    if re.search(r'\b(?:né[e]?|baptisé[e]?)\s+(?:le|en|vers)\s+\d+', lead_text, re.IGNORECASE):
        return True
    if re.search(r'\b(?:mort[e]?|décédé[e]?)\s+(?:le|en|vers)\s+\d+', lead_text, re.IGNORECASE):
        if not re.search(r'\b(?:l\'artiste|l\'auteur|le peintre|le créateur)\s+(?:étant|est)\s+mort', lead_text, re.IGNORECASE):
            return True

    # 4. Lifespan in parentheses e.g. (1789-1845) or (vers 100 av. J.-C. - 44 av. J.-C.) in lead
    if re.search(r'\(\s*(?:vers\s+)?-?\d{1,4}\s*(?:av\. J\.-C\.)?\s*[-–—]\s*(?:vers\s+)?-?\d{1,4}(?:\s*av\. J\.-C\.)?\s*\)', lead_text):
        if not re.search(r'\b(?:guerre|bataille|traité|dynastie|période|siècle|révolution|accord|crise|empire|royaume)\b', lead_text, re.IGNORECASE):
            return True

    # 5. Sentence stating profession / role
    if BIO_REGEX.search(lead_text):
        return True

    # 6. MediaWiki defaultsort formatted as 'Nom, Prénom' (excluding inverted grammatical articles)
    defaultsort = pageprops.get("defaultsort", "")
    if defaultsort and "," in defaultsort:
        parts = [p.strip() for p in defaultsort.split(",", 1)]
        if len(parts) == 2 and parts[1].lower() not in INVERTED_ARTICLES:
            lower_t = title.lower()
            if not any(k in lower_t for k in NON_PERSON_WORDS):
                return True

    return False


def calculate_article_difficulty(
    lang_count: int,
    pageviews_90d: int,
    is_person: bool = False,
    title: str = ""
) -> str:
    """
    Classifies a Wikipedia article into a difficulty level: 'facile', 'moyen', or 'difficile'.
    - Facile: highly famous, ubiquitous subjects (>= 45 langs or >= 20 000 views / 90d, or curated iconic).
    - Moyen: classic general knowledge (>= 25 langs or >= 3 500 views / 90d).
    - Difficile: more specific or specialized (fewer translations/views, but still sufficiently notable).
    """
    if title in ALL_CURATED_TITLES and (lang_count >= 35 or pageviews_90d >= 10000):
        return "facile"

    if is_person:
        if lang_count >= 65 or (lang_count >= 35 and pageviews_90d >= 30000):
            return "facile"
        elif lang_count >= 38 or (lang_count >= 25 and pageviews_90d >= 4000):
            return "moyen"
        else:
            return "difficile"
    else:
        if lang_count >= 45 or pageviews_90d >= 20000:
            return "facile"
        elif lang_count >= 25 or pageviews_90d >= 3500:
            return "moyen"
        else:
            return "difficile"


class WikipediaClient:
    def __init__(self, min_languages: int = DEFAULT_MIN_ARTICLE_LANGUAGES):
        self.cached_articles: Dict[str, Dict[str, Any]] = {}
        self.pageviews_pool: List[str] = []
        self._pageviews_fetched = False
        self.min_languages = min_languages

    def _make_api_request(self, params: Dict[str, str], timeout: int = 7) -> Optional[Dict[str, Any]]:
        """Makes an HTTP GET request to fr.wikipedia.org API."""
        base_url = "https://fr.wikipedia.org/w/api.php"
        params["format"] = "json"
        query_string = urllib.parse.urlencode(params)
        full_url = f"{base_url}?{query_string}"

        req = urllib.request.Request(
            full_url,
            headers={"User-Agent": USER_AGENT}
        )
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    content = response.read().decode("utf-8")
                    return json.loads(content)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    time.sleep(1.0)
                    continue
                logger.warning(f"Wikipedia API request failed for {full_url}: {e}")
                return None
            except Exception as e:
                logger.warning(f"Wikipedia API request failed for {full_url}: {e}")
                return None
        return None

    def _get_pageviews_pool(self) -> List[str]:
        """Fetches Wikimedia top pageviews list of famous, widely read articles."""
        if self.pageviews_pool:
            return self.pageviews_pool

        months = ['2024/05', '2024/01', '2024/09', '2023/12', '2023/04', '2024/11']
        random.shuffle(months)
        for m in months:
            url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/fr.wikipedia/all-access/{m}/all-days"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    items = data["items"][0]["articles"]
                    valid = []
                    for a in items:
                        t = a["article"].replace("_", " ")
                        # Exclude meta, wiki namespaces, stubs, and lists
                        if any(t.startswith(p) for p in [
                            "Wikipédia:", "Spécial:", "Fichier:", "Aide:", "Portail:",
                            "Discussion:", "Catégorie:", "Modèle:", "Liste", "Saison",
                            "Épisode", "Chronologie", "Discographie", "Canton", "Sondage",
                            "Utilisateur:"
                        ]):
                            continue
                        if t in ["Cookie (informatique)", "Accueil", "Spécial:Recherche"]:
                            continue
                        if "(" in t and any(bad in t.lower() for bad in ["homonymie", "saison", "série télévisée"]):
                            continue
                        valid.append(t)
                    if len(valid) >= 100:
                        self.pageviews_pool = valid
                        return self.pageviews_pool
            except Exception as e:
                logger.debug(f"Failed fetching pageviews for month {m}: {e}")

        # Fallback to curated pool if Wikimedia API is unavailable
        self.pageviews_pool = list(ALL_CURATED_TITLES)
        return self.pageviews_pool

    def fetch_article_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Fetches full introductory extract, image, and metadata for a specific article title."""
        params = {
            "action": "query",
            "prop": "extracts|pageimages|info|pageprops|langlinks|pageviews",
            "inprop": "url",
            "titles": title,
            "redirects": "1",
            "exintro": "1",
            "pithumbsize": "600",
            "lllimit": "500"
        }

        data = self._make_api_request(params)
        if not data or "query" not in data or "pages" not in data["query"]:
            return None

        pages = data["query"]["pages"]
        page = list(pages.values())[0]

        if "missing" in page:
            return None

        real_title = page.get("title", title)
        html_extract = page.get("extract", "")
        paragraphs = clean_html_extract(html_extract)

        if not paragraphs or count_article_words(paragraphs) < 50:
            return None

        thumbnail = page.get("thumbnail", {}).get("source", "")
        page_url = page.get("fullurl", f"https://fr.wikipedia.org/wiki/{urllib.parse.quote(real_title)}")
        full_text_sample = " ".join(paragraphs)
        lang_count = len(page.get("langlinks", []))
        pviews = page.get("pageviews", {})
        total_pviews = sum(v for v in pviews.values() if v is not None) if pviews else 0
        pageviews_90d = int(total_pviews * 1.5)
        is_person = is_person_article(real_title, page.get("pageprops", {}), html_extract)
        difficulty = calculate_article_difficulty(lang_count, pageviews_90d, is_person, real_title)

        return {
            "title": real_title,
            "paragraphs": paragraphs,
            "image": thumbnail,
            "url": page_url,
            "page_id": page.get("pageid", 0),
            "text_sample": full_text_sample,
            "lang_count": lang_count,
            "pageviews_60d": total_pviews,
            "pageviews_90d": pageviews_90d,
            "difficulty": difficulty,
            "is_person": is_person
        }

    def search_and_fetch(self, query: str) -> Optional[Dict[str, Any]]:
        """Searches Wikipedia for a query string and fetches the top resulting article."""
        # Check if user entered a full wikipedia URL
        if "wikipedia.org/wiki/" in query:
            clean_title = query.split("wikipedia.org/wiki/")[-1].split("?")[0].split("#")[0]
            clean_title = urllib.parse.unquote(clean_title).replace("_", " ")
            return self.fetch_article_by_title(clean_title)

        params = {
            "action": "opensearch",
            "search": query,
            "limit": "5",
            "namespace": "0"
        }
        data = self._make_api_request(params)
        if data and len(data) >= 2 and data[1]:
            for candidate in data[1]:
                art = self.fetch_article_by_title(candidate)
                if art:
                    return art

        # Fallback to direct title fetch
        return self.fetch_article_by_title(query)

    def _get_article_lang_count(self, title: str) -> int:
        """Fetches the number of interwiki language links for an article to evaluate notability."""
        params = {
            "action": "query",
            "titles": title,
            "prop": "langlinks",
            "lllimit": "500",
            "redirects": "1"
        }
        data = self._make_api_request(params, timeout=4)
        if not data or "query" not in data or "pages" not in data["query"]:
            return 0
        pages = data["query"]["pages"]
        page = next(iter(pages.values()), {})
        return len(page.get("langlinks", []))

    def is_notable_candidate(
        self,
        title: str,
        page: Dict[str, Any],
        raw_extract: str,
        min_languages: int,
        min_person_languages: int = DEFAULT_MIN_PERSON_LANGUAGES,
        min_person_languages_regional: int = DEFAULT_MIN_PERSON_LANGUAGES_REGIONAL,
        min_person_pageviews: int = DEFAULT_MIN_PERSON_PAGEVIEWS,
        min_general_pageviews: int = DEFAULT_MIN_GENERAL_PAGEVIEWS
    ) -> bool:
        """
        Validates if an article candidate is sufficiently well known to be fun and fair in Pedantix.
        - Persons/biographies require either high international fame (min 50 langs)
          or significant French readership (min 28 langs + min 3,000 views over 60 days).
        - Non-person articles require >= 25 langs or (>= 18 langs + >= 1,000 views).
        - Discards numbered asteroids and obscure stubs.
        """
        # Always accept curated iconic subjects
        if title in ALL_CURATED_TITLES:
            return True

        # Exclude numbered asteroids like "(899) Jokaste"
        if re.match(r'^\(\d+\)', title):
            return False

        # Exclude technical, disambiguation, or ephemeral pages
        lower_title = title.lower()
        if "homonymie" in lower_title:
            return False
        if title.startswith((
            "Liste", "Chronologie", "Saison", "Épisode",
            "Discographie", "Canton", "Sondage", "Utilisateur:"
        )):
            return False

        langs_count = len(page.get("langlinks", []))
        pageviews_dict = page.get("pageviews", {})
        pageviews_60d = sum(v for v in pageviews_dict.values() if v is not None) if pageviews_dict else 0
        pageprops = page.get("pageprops", {})

        is_person = is_person_article(title, pageprops, raw_extract)

        if is_person:
            # Person criteria:
            # 1. Universally famous international person (e.g. Einstein 235, Zidane 122, Carl Lewis 72)
            if langs_count >= min_person_languages:
                return True
            # 2. Prominent Francophone/French cultural figure with solid translation count and strong pageviews
            # (e.g. Coluche 39 langs / 43k views, Jean Moulin 39 langs / 100k views, Thomas Pesquet 33 langs / 43k views)
            if langs_count >= min_person_languages_regional and pageviews_60d >= min_person_pageviews:
                return True
            # In Wikimedia top monthly pageviews pool:
            if bool(self.pageviews_pool) and title in self.pageviews_pool and langs_count >= 20:
                return True

            logger.info(
                f"Skipping obscure person article: '{title}' "
                f"({langs_count} languages, {pageviews_60d} views in 60d)"
            )
            return False
        else:
            # General (non-person) criteria:
            if langs_count >= min_languages:
                return True
            if langs_count >= 18 and pageviews_60d >= min_general_pageviews:
                return True
            if bool(self.pageviews_pool) and title in self.pageviews_pool and langs_count >= 15:
                return True

            logger.info(
                f"Skipping obscure concept/article: '{title}' "
                f"({langs_count} languages, {pageviews_60d} views in 60d)"
            )
            return False

    def fetch_random_wikipedia_article(
        self,
        difficulty: str = "moyen",
        min_languages: Optional[int] = None,
        min_person_languages: Optional[int] = None,
        min_person_languages_regional: Optional[int] = None,
        min_person_pageviews: Optional[int] = None,
        min_general_pageviews: Optional[int] = None,
        max_attempts: int = 6
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches a random article from French Wikipedia (fr.wikipedia.org) tailored to the requested difficulty level.
        - Difficulty levels:
          * 'facile': min 45 languages, min 20,000 views / 90d, high chance of iconic curated subjects, min 90 words.
          * 'moyen': min 28 languages, min 4,000 views / 90d, balanced pool, min 65 words.
          * 'difficile': min 18 languages, min 1,500 views / 90d, random Wikipedia topics, min 50 words.
        """
        diff_key = difficulty.lower() if difficulty and difficulty.lower() in DIFFICULTY_LEVELS else "moyen"
        cfg = DIFFICULTY_LEVELS[diff_key]

        if min_languages is None:
            min_languages = cfg["min_languages"]
        if min_person_languages is None:
            min_person_languages = cfg["min_person_languages"]
        if min_person_languages_regional is None:
            min_person_languages_regional = cfg["min_person_languages_regional"]
        if min_person_pageviews is None:
            min_person_pageviews = cfg["min_person_pageviews_60d"]
        if min_general_pageviews is None:
            min_general_pageviews = cfg["min_general_pageviews_60d"]
        min_words = cfg.get("min_words", 50)
        curated_prob = cfg.get("curated_pool_prob", 0.35)

        # Pre-populate pageviews pool if empty
        if not self.pageviews_pool:
            self._get_pageviews_pool()

        # In easy / medium mode, prioritize high pageviews / curated pool
        if curated_prob > 0 and random.random() < curated_prob and (self.pageviews_pool or ALL_CURATED_TITLES):
            pool = list(dict.fromkeys(list(ALL_CURATED_TITLES) + self.pageviews_pool))
            sample_candidates = random.sample(pool, min(5, len(pool)))
            for candidate in sample_candidates:
                art = self.fetch_article_by_title(candidate)
                if art and count_article_words(art.get("paragraphs", [])) >= min_words:
                    art["difficulty"] = diff_key
                    art["pageviews_90d"] = int(art.get("pageviews_60d", 0) * 1.5)
                    logger.info(
                        f"Accepted notable article from popular pool for difficulty '{diff_key}': '{art['title']}' "
                        f"({art.get('lang_count', 0)} languages)"
                    )
                    return art

        for attempt in range(max_attempts):
            params = {
                "action": "query",
                "generator": "random",
                "grnnamespace": "0",
                "grnfilterredir": "nonredirects",
                "grnlimit": "40",
                "prop": "extracts|pageimages|info|pageprops|langlinks|pageviews",
                "lllimit": "500",
                "inprop": "url",
                "exintro": "1",
                "pithumbsize": "600"
            }
            data = self._make_api_request(params)
            if not data or "query" not in data or "pages" not in data["query"]:
                continue

            candidates: List[Dict[str, Any]] = []

            for page in data["query"]["pages"].values():
                title = page.get("title", "")
                if not title:
                    continue

                raw_extract = page.get("extract", "")
                paragraphs = clean_html_extract(raw_extract)
                if not paragraphs:
                    continue

                # Enforce difficulty-specific minimum article length
                word_count = count_article_words(paragraphs)
                if word_count < min_words:
                    continue

                # Notability validation (person vs general)
                if not self.is_notable_candidate(
                    title=title,
                    page=page,
                    raw_extract=raw_extract,
                    min_languages=min_languages,
                    min_person_languages=min_person_languages,
                    min_person_languages_regional=min_person_languages_regional,
                    min_person_pageviews=min_person_pageviews,
                    min_general_pageviews=min_general_pageviews
                ):
                    continue

                langs_count = len(page.get("langlinks", []))
                pviews = page.get("pageviews", {})
                total_pviews = sum(v for v in pviews.values() if v is not None) if pviews else 0
                pageviews_90d = int(total_pviews * 1.5)

                # For hard difficulty, prefer articles that are not overly trivial
                if diff_key == "difficile" and langs_count > 90 and total_pviews > 40000:
                    continue

                is_person = is_person_article(title, page.get("pageprops", {}), raw_extract)
                thumbnail = page.get("thumbnail", {}).get("source", "")
                page_url = page.get("fullurl", f"https://fr.wikipedia.org/wiki/{urllib.parse.quote(title)}")

                candidates.append({
                    "title": title,
                    "paragraphs": paragraphs,
                    "image": thumbnail,
                    "url": page_url,
                    "page_id": page.get("pageid", 0),
                    "text_sample": " ".join(paragraphs),
                    "lang_count": langs_count,
                    "pageviews_60d": total_pviews,
                    "pageviews_90d": pageviews_90d,
                    "difficulty": diff_key,
                    "is_person": is_person
                })

            if candidates:
                chosen = random.choice(candidates)
                chosen["difficulty"] = diff_key
                logger.info(
                    f"Accepted article for difficulty '{diff_key}': '{chosen['title']}' "
                    f"({chosen['lang_count']} languages, {chosen['pageviews_90d']} views 90d, "
                    f"{count_article_words(chosen['paragraphs'])} words)"
                )
                return chosen

        # Fallback to curated only if live network request fails or no candidate met criteria
        logger.warning(
            f"Could not find random article meeting criteria for difficulty '{diff_key}' after {max_attempts} attempts; "
            "falling back to curated iconic articles."
        )
        fallback = self.fetch_curated_article(difficulty=diff_key)
        if fallback:
            fallback["difficulty"] = diff_key
            fallback["pageviews_90d"] = int(fallback.get("pageviews_60d", 0) * 1.5) or 25000
        return fallback

    fetch_notable_random_wikipedia_article = fetch_random_wikipedia_article

    def fetch_curated_article(self, category: Optional[str] = None, difficulty: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Picks a random article from the curated collections and fetches it."""
        if category and category in THEMES_ARTICLES:
            titles_pool = THEMES_ARTICLES[category]
        else:
            titles_pool = ALL_CURATED_TITLES

        chosen_titles = random.sample(titles_pool, min(5, len(titles_pool)))
        for title in chosen_titles:
            article = self.fetch_article_by_title(title)
            if article and count_article_words(article.get("paragraphs", [])) >= 50:
                if difficulty:
                    article["difficulty"] = difficulty
                return article

        # Fallback to local curated_articles.json if network is unavailable
        try:
            json_path = os.path.join(os.path.dirname(__file__), "curated_articles.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    local_curated = json.load(f)
                    if local_curated:
                        chosen = dict(random.choice(list(local_curated.values())))
                        if count_article_words(chosen.get("paragraphs", [])) >= 50:
                            chosen["difficulty"] = difficulty or chosen.get("difficulty", "facile")
                            chosen["pageviews_90d"] = chosen.get("pageviews_90d", 25000)
                            return chosen
        except Exception as e:
            logger.debug(f"Failed loading offline curated: {e}")

        return None

    def get_daily_article(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Deterministically picks an iconic article based on the date string."""
        import hashlib
        h = int(hashlib.md5(date_str.encode("utf-8")).hexdigest(), 16)
        index = h % len(ALL_CURATED_TITLES)
        title = ALL_CURATED_TITLES[index]
        return self.fetch_article_by_title(title)
