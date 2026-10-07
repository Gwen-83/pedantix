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
DEFAULT_MIN_ARTICLE_LANGUAGES = int(os.environ.get("PEDANTIX_MIN_LANGUAGES", "15"))

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
        "Théorie du chaos", "Énergie nucléaire", "Électron", "Dinausore", "Laser",
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
        "Christophe Colomb", "Marco Polo", "Pasteur (Louis)", "Frida Kahlo", "Jean Moulin"
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
        "Gépard", "Caméléon", "Gorille", "Chimpanzé", "Kangourou", "Koala"
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
    'homme politique', 'femme politique', 'écrivain', 'écrivaine', 'acteur', 'actrice',
    'chanteur', 'chanteuse', 'musicien', 'musicienne', 'joueur', 'joueuse', 'sportif', 'sportive',
    'scientifique', 'général', 'roi', 'reine', 'président', 'présidente', 'compositeur', 'compositrice',
    'poète', 'poétesse', 'athlète', 'footballeur', 'footballeuse', 'cycliste', 'souverain', 'souveraine',
    'cinéaste', 'réalisateur', 'réalisatrice', 'sculpteur', 'sculptrice', 'peintre', 'dramaturge',
    'romancier', 'romancière', 'médecin', 'biologiste', 'physicien', 'physicienne', 'chimiste',
    'mathématicien', 'mathématicienne', 'militaire', 'avocat', 'avocate', 'journaliste',
    'navigateur', 'navigatrice', 'explorateur', 'exploratrice', 'philosophe', 'homme d\'affaires',
    'femme d\'affaires', 'animateur', 'animatrice', 'humoriste', 'militant', 'militante',
    'évêque', 'archevêque', 'cardinal', 'pape', 'prince', 'princesse', 'duc', 'duchesse',
    'empereur', 'impératrice', 'seigneur', 'architecte', 'historien', 'historienne',
    'personnage', 'héros', 'héroïne', 'personnalité', 'théologien', 'universitaire'
]

BIO_REGEX = re.compile(
    r'\b(?:est|était|fut)\s+(?:un|une)\s+(?:' + '|'.join(BIO_ROLES) + r')\b',
    re.IGNORECASE
)

DATES_REGEX = re.compile(
    r'\(\s*(?:né[e]?\s+(?:le|en|vers)\s+\d{1,4}|\d{3,4}\s*[-–—]\s*(?:\d{3,4}|mort|décédé))',
    re.IGNORECASE
)

DEFAULTSORT_PERSON = re.compile(
    r'^[A-ZÀ-ÖØ-ß][a-zà-öø-ÿ\-\']{1,25},\s+[A-ZÀ-ÖØ-ß]'
)

NON_PERSON_WORDS = [
    'bataille', 'traité', 'commune', 'église', 'canton', 'rue', 'avenue',
    'boulevard', 'gare', 'pont', 'château', 'parc', 'lac', 'musée', 'famille',
    'parti', 'société', 'compagnie', 'groupe', 'île', 'îlot', 'mont', 'col',
    'vallée', 'rivière', 'fleuve', 'baie', 'golfe', 'cap', 'forêt', 'station',
    'canal', 'mer', 'océan', 'village', 'ville', 'royaume', 'dynastie',
    'abbaye', 'cathédrale', 'monastère', 'hôtel', 'palais'
]


def is_person_article(title: str, pageprops: Dict[str, Any], html_extract: str) -> bool:
    """
    Determines whether a Wikipedia article represents a person (biography) or character.
    Uses microformats, birth/death patterns, biography vocabulary, defaultsort, and title patterns.
    """
    # 1. Semantic microformats for birth/death dates
    if 'bday' in html_extract or 'dday' in html_extract:
        return True

    # 2. Explicit birth or death mentions
    if re.search(r'\b(?:né[e]?|baptisé[e]?)\s+(?:le|en|vers)\s+\d+', html_extract, re.IGNORECASE):
        return True
    if re.search(r'\b(?:mort[e]?|décédé[e]?)\s+(?:le|en|vers)\s+\d+', html_extract, re.IGNORECASE):
        return True

    # 3. Lifespan in parentheses e.g. (1789-1845)
    if DATES_REGEX.search(html_extract):
        return True

    # 4. Sentence stating profession / role
    if BIO_REGEX.search(html_extract):
        return True

    # 5. MediaWiki defaultsort formatted as 'Nom, Prénom'
    defaultsort = pageprops.get("defaultsort", "")
    if defaultsort and DEFAULTSORT_PERSON.match(defaultsort):
        lower_t = title.lower()
        if not any(k in lower_t for k in NON_PERSON_WORDS):
            return True

    # 6. Title parenthetical indicates occupation or character
    parenthetical = re.search(r'\(([^)]+)\)$', title)
    if parenthetical:
        p_content = parenthetical.group(1).lower()
        if any(r in p_content for r in [
            'chanteur', 'chanteuse', 'acteur', 'actrice', 'football', 'rugby',
            'cyclisme', 'athlétisme', 'écrivain', 'peintre', 'politique', 'personnalité',
            'personnage'
        ]):
            return True

    return False


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

        months = ['2024/05', '2023/10', '2024/01', '2024/09', '2023/12', '2023/04']
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
                            "Épisode", "Chronologie", "Discographie", "Canton"
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
            "prop": "extracts|pageimages|info|langlinks",
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

        return {
            "title": real_title,
            "paragraphs": paragraphs,
            "image": thumbnail,
            "url": page_url,
            "page_id": page.get("pageid", 0),
            "text_sample": full_text_sample,
            "lang_count": lang_count
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

    def fetch_random_wikipedia_article(
        self,
        min_languages: Optional[int] = None,
        max_attempts: int = 6
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches a random article from French Wikipedia (fr.wikipedia.org) that is sufficiently well known.
        - Requires the article to have at least 50 words.
        - Requires the article to be sufficiently known:
          * Must have at least `min_languages` interwiki translations (default: 15), OR
          * Must be in curated iconic articles / Wikimedia top pageviews list.
        - Filters out disambiguation pages, technical lists, and obscure articles.
        """
        if min_languages is None:
            min_languages = self.min_languages

        for attempt in range(max_attempts):
            params = {
                "action": "query",
                "generator": "random",
                "grnnamespace": "0",
                "grnfilterredir": "nonredirects",
                "grnlimit": "40",
                "prop": "extracts|pageimages|info|pageprops|langlinks",
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

                # Filter out technical disambiguation pages and technical list prefixes
                lower_title = title.lower()
                if "homonymie" in lower_title:
                    continue
                if title.startswith(("Liste", "Chronologie", "Saison", "Épisode", "Discographie")):
                    continue

                raw_extract = page.get("extract", "")
                paragraphs = clean_html_extract(raw_extract)
                if not paragraphs:
                    continue

                # Enforce minimum article length of 50 words
                word_count = count_article_words(paragraphs)
                if word_count < 50:
                    continue

                langs_count = len(page.get("langlinks", []))

                # Check notability: iconic curated, top pageviews, or minimum translation languages
                is_curated = title in ALL_CURATED_TITLES or (bool(self.pageviews_pool) and title in self.pageviews_pool)
                if not is_curated and langs_count < min_languages:
                    logger.debug(f"Skipping obscure article: '{title}' ({langs_count} languages < {min_languages})")
                    continue

                thumbnail = page.get("thumbnail", {}).get("source", "")
                page_url = page.get("fullurl", f"https://fr.wikipedia.org/wiki/{urllib.parse.quote(title)}")

                candidates.append({
                    "title": title,
                    "paragraphs": paragraphs,
                    "image": thumbnail,
                    "url": page_url,
                    "page_id": page.get("pageid", 0),
                    "text_sample": " ".join(paragraphs),
                    "lang_count": langs_count
                })

            if candidates:
                chosen = random.choice(candidates)
                logger.info(
                    f"Accepted sufficiently known article: '{chosen['title']}' "
                    f"({chosen['lang_count']} languages >= {min_languages}, "
                    f"{count_article_words(chosen['paragraphs'])} words)"
                )
                return chosen

        # Fallback to curated only if live network request fails or no candidate met criteria
        logger.warning(
            f"Could not find random article meeting >= {min_languages} languages after {max_attempts} attempts; "
            "falling back to curated iconic articles."
        )
        return self.fetch_curated_article()

    fetch_notable_random_wikipedia_article = fetch_random_wikipedia_article

    def fetch_curated_article(self, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Picks a random article from the curated collections and fetches it."""
        if category and category in THEMES_ARTICLES:
            titles_pool = THEMES_ARTICLES[category]
        else:
            titles_pool = ALL_CURATED_TITLES

        chosen_titles = random.sample(titles_pool, min(5, len(titles_pool)))
        for title in chosen_titles:
            article = self.fetch_article_by_title(title)
            if article and count_article_words(article.get("paragraphs", [])) >= 50:
                return article

        # Fallback to local curated_articles.json if network is unavailable
        try:
            json_path = os.path.join(os.path.dirname(__file__), "curated_articles.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    local_curated = json.load(f)
                    if local_curated:
                        chosen = random.choice(list(local_curated.values()))
                        if count_article_words(chosen.get("paragraphs", [])) >= 50:
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
