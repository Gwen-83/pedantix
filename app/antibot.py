"""
Protection Anti-Bot & Anti-Triche pour Pédantix.
Bloque les scripts d'automatisation, dictionnaires massifs, IA automatisées et requêtes à cadence surhumaine.
"""

import os
import time
import math
import re
import secrets
from collections import deque
from typing import Dict, Any, Tuple, Optional

# Format autorisé : lettres, chiffres (dates/siècles), accents français, apostrophe, trait d'union, espace.
WORD_ALLOWED_RE = re.compile(r"^[a-zA-Z0-9À-ÿ\u0100-\u017F\u0180-\u024F\-' ]+$")

# Mots pièges (canaris) invisibles dans le DOM : si soumis, ils trahissent un scraper DOM / extension
HONEYPOT_WORDS = {
    "piegebothoney",
    "canaritrichebot",
    "xylophonepiege",
    "botdetecttrap",
    "scrpcanarytrap"
}

class AntiBotGuard:
    def __init__(self):
        # Tracking cadence par joueur/session: identifier -> {
        #   "last_guess_time": float,
        #   "history": deque([timestamps]),
        #   "rapid_strikes": int,
        #   "penalty_until": float,
        #   "token": str,
        #   "token_issued_at": float
        # }
        self.players: Dict[str, Dict[str, Any]] = {}
        
        # Tracking cadence par IP: ip -> deque([timestamps])
        self.ip_history: Dict[str, deque] = {}
        
        # Paramètres anti-cadence
        self.min_interval_seconds = 0.35      # 350ms minimum entre 2 mots
        self.min_token_age_seconds = 0.0 if os.environ.get("PEDANTIX_TEST_MODE") == "1" else 0.15  # 150ms pour contrer les scripts super-rapides
        self.max_in_2s = 3                    # Max 3 mots en 2s
        self.max_in_10s = 10                  # Max 10 mots en 10s
        self.max_in_30s = 22                  # Max 22 mots en 30s
        self.max_ip_per_minute = 60           # Max 60 requêtes par minute par IP
        self.penalty_duration = 15.0          # 15 secondes de pénalité en cas d'abus répété

    def clean_old_records(self, now: float):
        """Nettoie les enregistrements inactifs depuis plus de 10 minutes."""
        stale_threshold = now - 600
        to_del = [pid for pid, data in self.players.items() if data.get("last_guess_time", 0) < stale_threshold and data.get("penalty_until", 0) < now]
        for pid in to_del:
            del self.players[pid]

    def _get_or_create_player(self, identifier: str) -> Dict[str, Any]:
        now = time.time()
        if identifier not in self.players:
            self.players[identifier] = {
                "last_guess_time": 0.0,
                "history": deque(maxlen=40),
                "rapid_strikes": 0,
                "penalty_until": 0.0,
                "token": secrets.token_urlsafe(16),
                "token_issued_at": now
            }
        return self.players[identifier]

    def get_or_issue_token(self, identifier: str) -> str:
        """Génère ou renvoie le jeton actif pour l'identifiant."""
        p = self._get_or_create_player(identifier)
        return p["token"]

    def rotate_token(self, identifier: str) -> str:
        """Génère un nouveau jeton cryptographique à usage unique."""
        p = self._get_or_create_player(identifier)
        new_tok = secrets.token_urlsafe(16)
        p["token"] = new_tok
        p["token_issued_at"] = time.time()
        return new_tok

    def validate_word(self, raw_word: Any) -> Tuple[bool, str]:
        """Vérifie que le mot proposé est propre et non issu d'une injection de bot."""
        if not isinstance(raw_word, str):
            return False, "Format de mot invalide."

        word = raw_word.strip()
        if not word:
            return False, "Mot vide."

        if len(word) > 35:
            return False, "Mot anormalement long (35 caractères maximum autorisés)."

        # Caractères suspects ou injection de script/code
        if any(char in word for char in ('<', '>', '{', '}', ';', '$', '`', '\\', '|', '[', ']', '(', ')', '"', '\n', '\r', '\t')):
            return False, "Caractères suspects ou injection de code détectée."

        if not WORD_ALLOWED_RE.match(word):
            return False, "Le mot contient des caractères non autorisés."

        return True, ""

    def is_honeypot_word(self, raw_word: Any) -> bool:
        """Détecte si le mot correspond à un piège canari invisible inséré dans le DOM."""
        if not isinstance(raw_word, str):
            return False
        w = raw_word.strip().lower().replace("-", "").replace(" ", "").replace("'", "")
        return w in HONEYPOT_WORDS

    def trigger_cheat_penalty(self, identifier: str, duration: float = 30.0) -> float:
        """Applique une pénalité maximale immédiate suite à une triche formellement identifiée."""
        now = time.time()
        p = self._get_or_create_player(identifier)
        p["rapid_strikes"] = 5
        p["penalty_until"] = max(p["penalty_until"], now + duration)
        return duration

    def verify_token(self, identifier: str, client_token: Optional[str]) -> Tuple[bool, str, str]:
        """Vérifie le jeton fourni par le client et le renouvelle."""
        p = self._get_or_create_player(identifier)
        current_token = p["token"]
        issued_at = p["token_issued_at"]
        now = time.time()

        # Si le client fournit un jeton erroné ou manquant
        if not client_token or client_token != current_token:
            new_token = self.rotate_token(identifier)
            return False, "Jeton de sécurité invalide ou expiré (Protection anti-bot).", new_token

        # Vérification cadence surhumaine (un script qui répond en < 150ms du token)
        if (now - issued_at) < self.min_token_age_seconds:
            new_token = self.rotate_token(identifier)
            return False, "Cadence surhumaine détectée ! Veuillez taper vos mots manuellement.", new_token

        # Tout est valide, on renouvelle le jeton pour le coup suivant
        new_token = self.rotate_token(identifier)
        return True, "", new_token

    def check_rate_limit(self, identifier: str, ip: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Contrôle la cadence de soumission.
        Renvoie (autorisé, message_erreur, métadonnées).
        """
        now = time.time()
        p = self._get_or_create_player(identifier)

        # 1. Vérification si joueur sous pénalité anti-bot
        if now < p["penalty_until"]:
            remaining = int(math.ceil(p["penalty_until"] - now))
            return False, f"Suspension anti-bot active : patientez encore {remaining} s avant de proposer un mot.", {
                "blocked": True,
                "remaining": remaining,
                "penalty": True
            }

        # 2. Vérification IP globale
        if ip:
            if ip not in self.ip_history:
                self.ip_history[ip] = deque(maxlen=80)
            ip_q = self.ip_history[ip]
            while ip_q and (now - ip_q[0] > 60.0):
                ip_q.popleft()
            if len(ip_q) >= self.max_ip_per_minute:
                return False, "Trop de requêtes émises depuis cette adresse IP. Ralentissez.", {
                    "blocked": True,
                    "remaining": 10,
                    "penalty": False
                }
            ip_q.append(now)

        # 3. Vérification cadence inter-mots (< 350ms)
        last_t = p["last_guess_time"]
        diff = now - last_t
        if last_t > 0 and diff < self.min_interval_seconds:
            p["rapid_strikes"] += 1
            if p["rapid_strikes"] >= 4:
                p["penalty_until"] = now + self.penalty_duration
                return False, f"Cadence automatisée / bot détectée ! Vous êtes suspendu pendant {int(self.penalty_duration)} secondes.", {
                    "blocked": True,
                    "remaining": int(self.penalty_duration),
                    "penalty": True
                }
            return False, "Ralentissez ! Trop de mots proposés en peu de temps (Protection anti-bot).", {
                "blocked": True,
                "remaining": 1,
                "penalty": False
            }

        # 4. Vérification fenêtre glissante
        hist = p["history"]
        while hist and (now - hist[0] > 30.0):
            hist.popleft()

        in_2s = sum(1 for t in hist if now - t <= 2.0)
        in_10s = sum(1 for t in hist if now - t <= 10.0)
        in_30s = len(hist)

        if in_2s >= self.max_in_2s or in_10s >= self.max_in_10s or in_30s >= self.max_in_30s:
            p["rapid_strikes"] += 1
            if p["rapid_strikes"] >= 4:
                p["penalty_until"] = now + self.penalty_duration
                return False, f"Spam massif de mots détecté ! Vous êtes suspendu pendant {int(self.penalty_duration)} secondes.", {
                    "blocked": True,
                    "remaining": int(self.penalty_duration),
                    "penalty": True
                }
            return False, "Fréquence de saisie trop élevée. Prenez le temps de réfléchir !", {
                "blocked": True,
                "remaining": 2,
                "penalty": False
            }

        # Tout est bon : on valide le coup
        if diff > 4.0:
            p["rapid_strikes"] = max(0, p["rapid_strikes"] - 1)

        p["last_guess_time"] = now
        hist.append(now)
        return True, "", {"blocked": False, "remaining": 0, "penalty": False}


anti_bot_guard = AntiBotGuard()
