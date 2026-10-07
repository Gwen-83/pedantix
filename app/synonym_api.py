"""
Synonym API Client with persistent disk caching and background prefetching.
Uses the French Wiktionary MediaWiki API as an authoritative, free, unmetered lexical resource.
"""

import os
import json
import time
import urllib.request
import urllib.parse
import re
import threading
from typing import Set, Dict, List, Optional
import unicodedata

def normalize_text(text: str) -> str:
    """Lowercases and removes diacritics (accents) and extra spaces."""
    if not text:
        return ""
    text = text.lower().strip()
    nfkd = unicodedata.normalize('NFD', text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != 'Mn')
    stripped = stripped.replace("œ", "oe").replace("æ", "ae")
    return stripped

CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "api_synonyms_cache.json")

class SynonymAPIClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, List[str]] = {}
        self._pending_fetches: Set[str] = set()
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def fetch_online(self, word: str, timeout: float = 1.5) -> Set[str]:
        """Fetches synonyms and related vocabulary from fr.wiktionary.org."""
        norm = normalize_text(word)
        if not norm or len(norm) <= 1:
            return set()

        url_title = urllib.parse.quote(word)
        url = f"https://fr.wiktionary.org/w/api.php?action=parse&page={url_title}&prop=wikitext&format=json"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PedantixSynonymBot/1.0 (academic/game NLP enrichment)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        except Exception:
            return set()

        # Isolate the French section
        fr_match = re.search(r"==\s*\{\{langue\|fr\}\}\s*==.*?(?=(?:==\s*\{\{langue\||\Z))", wikitext, re.DOTALL)
        if not fr_match:
            return set()
        fr_text = fr_match.group(0)

        found_synonyms: Set[str] = set()
        sections_to_check = [
            "synonymes", "quasi-synonymes", "vocabulaire apparenté",
            "dérivés autres", "apparentés étymologiques"
        ]

        for sec in sections_to_check:
            pat = r"\{\{S\|" + re.escape(sec) + r"\}\}(.*?)(?=(?:\{\{S\||\Z))"
            matches = re.findall(pat, fr_text, re.DOTALL)
            for block in matches:
                # Extract internal wiki links [[target]] or [[target|label]]
                tokens = re.findall(r"\[\[([^\]\|#]+)(?:\|[^\]]+)?\]\]", block)
                for tok in tokens:
                    cand = tok.strip()
                    cand_norm = normalize_text(cand)
                    if (
                        cand_norm
                        and " " not in cand_norm
                        and len(cand_norm) >= 2
                        and not cand_norm.startswith(("categorie:", "fichier:", "modele:"))
                        and cand_norm != norm
                    ):
                        found_synonyms.add(cand_norm)

        return found_synonyms

    def get_synonyms(self, word: str, allow_network: bool = False) -> Set[str]:
        """Returns synonyms from cache, or fetches online if allow_network=True."""
        norm = normalize_text(word)
        if not norm:
            return set()

        with self._lock:
            if norm in self._cache:
                return set(self._cache[norm])

        if not allow_network:
            # Trigger background prefetch for future turns
            self.prefetch_words([norm])
            return set()

        fetched = self.fetch_online(norm)
        with self._lock:
            self._cache[norm] = sorted(list(fetched))
            self._save_cache()
        return fetched

    def prefetch_words(self, words: List[str]):
        """Asynchronously pre-fetches synonyms in background thread."""
        to_fetch = []
        with self._lock:
            for w in words:
                wn = normalize_text(w)
                if wn and wn not in self._cache and wn not in self._pending_fetches:
                    self._pending_fetches.add(wn)
                    to_fetch.append(wn)

        if not to_fetch:
            return

        def _worker():
            updated = False
            for w in to_fetch:
                try:
                    res = self.fetch_online(w)
                    with self._lock:
                        self._cache[w] = sorted(list(res))
                        self._pending_fetches.discard(w)
                        updated = True
                except Exception:
                    with self._lock:
                        self._pending_fetches.discard(w)
                time.sleep(0.1)  # Polite crawling rate

            if updated:
                with self._lock:
                    self._save_cache()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

# Global singleton client
SYNONYM_API = SynonymAPIClient()
