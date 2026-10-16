"""Module du Gardien du Seuil — Défi des 10 Sceaux pour l'accès au jeu caché."""

import hashlib
import hmac
import os
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

GATE_SECRET = os.environ.get("PEDANTIX_GATE_SECRET", "pedantix-gate-arcane-salt-2026-xyz")
MIN_SECONDS_BETWEEN_GUESSES = 1.0
MAX_RAPID_FAILS = 5
LOCKOUT_PENALTY_SECONDS = 15.0


def normalize_answer(text: str) -> str:
    """Normalise une réponse utilisateur : minuscules, sans accents, sans ponctuation."""
    if not text:
        return ""
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[\s\-_’']+", " ", text).strip()
    text = re.sub(r"[^a-z0-9 ]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hash_normalized(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_gate_token(player_id: str) -> str:
    """Génère un jeton signé HMAC prouvant la résolution des 10 énigmes."""
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    payload = f"{player_id}:{ts}:{nonce}"
    sig = hmac.new(GATE_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_gate_token(token: str, player_id: Optional[str] = None) -> bool:
    """Vérifie la validité cryptographique d'un jeton d'accès au jeu secret."""
    if not token or not isinstance(token, str):
        return False
    import urllib.parse
    token = urllib.parse.unquote(token).strip()
    parts = token.split(":")
    if len(parts) != 4:
        return False
    tok_player_id, ts_str, nonce, sig = parts
    if player_id and tok_player_id != player_id:
        return False
    payload = f"{tok_player_id}:{ts_str}:{nonce}"
    expected_sig = hmac.new(GATE_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return secrets.compare_digest(expected_sig, sig)


@dataclass(frozen=True)
class GateRiddle:
    step: int
    title: str
    category: str
    epigraph: str
    prompt: str
    detail: Optional[str]
    accepted_hashes: Set[str]


# Les solutions ne sont JAMAIS stockées en clair, uniquement leurs empreintes SHA-256.
_GATE_RIDDLES: Tuple[GateRiddle, ...] = (
    GateRiddle(
        step=1,
        title="I. Le Berceau de Plomb",
        category="Histoire & Typographie ancienne",
        epigraph="« D'un métal fondu naquirent mille voix silencieuses. »",
        prompt=(
            "Quarante-deux lignes par colonne, deux colonnes par page. "
            "Trois années d'un labeur fiévreux à Mayence pour faire parler les premiers caractères mobiles de plomb. "
            "Pourtant, ce n'est pas le nom de l'inventeur qui figure au colophon, mais celui de ses créanciers Fust et Schöffer, "
            "car l'homme mourut ruiné.\n\n"
            "Quel nom masculin singulier désigne tout livre imprimé dans ce tout premier berceau typographique, "
            "avant l'aube du 1er janvier 1501 ?"
        ),
        detail=None,
        accepted_hashes={
            "14bd69daa79fe2a3636bcf94138f01af6b4cf830083b2fbf7bde22f29fecb931",
            "1f62f2a487f07344906ceb8b818c399592869173570c460822569f551a433124",
            "55cb68bd27325ea1bb89f319068f5424f9bd010157bf604c1e99ed638e446e6e",
            "57044f2bb158506372f9ce80ef6ed78ba181840bc042206b956b88431ceb200d",
            "9e08e8123bd6412ccbbc0256d1d825e0d199e09c8b59660d83a3ffce2236323c",
            "a6d3a52f3626e94966d011214a40a097199a926cd30d8dc6b71e2211b6aa5eeb",
            "eba2f262d73e9937bdfc15b787519a89d46740978d7c28f26b0e1e0fda303b07",
        },
    ),
    GateRiddle(
        step=2,
        title="II. Le Seuil de l'Indécidable",
        category="Logique mathématique & Informatique théorique",
        epigraph="« La certitude de la fin n'est pas accessible au calcul. »",
        prompt=(
            "Je suis un nombre réel compris strictement entre 0 et 1.\n"
            "Je représente la probabilité exacte qu'un programme informatique généré de manière purement aléatoire "
            "sur une machine de Turing universelle finisse par s'arrêter.\n"
            "Bien que rigoureusement défini et mathématiquement unique, je suis formellement non calculable : "
            "aucun algorithme ne pourra jamais en déterminer la suite des décimales au-delà des premières.\n\n"
            "Quel est le nom de cette constante ?"
        ),
        detail=None,
        accepted_hashes={
            "18f4c8315a1f7fc7beeaaf5b5dd92b0e5584d6219f0df65f4bff416a4c5a9f0f",
            "304b4a90a76a1cbe4c112e074b30e75181f54df43d60f883597457844293b341",
            "3afe7712b5e78c2ddd951361aec38fde27019c686550c1b4861a9f0525cfd121",
            "4b462a98ec61b4c0843473618cb5579adaef3bf6bf2f04196187ee13e35dc64a",
            "5383c1b18c96db50d17d9014507fb8eea273469425b8c816a50204ce9799b563",
            "69ae38f0d012f63381589db7ab55c2adcf81204f39608057e99a434cacb35bcf",
            "befa77ec1604ce7361dce02232585b6ef265d0db40aaa38516271f3afcb8eefd",
            "d089bc0823b1b608fde9ce91f0dbab8d3af50a3badbf1b952f1e5dca5b0dda96",
            "d73e88c597ebe21f833fb8b3eaf452868680f7f34d81df5f962e4be874e9de79",
        },
    ),
    GateRiddle(
        step=3,
        title="III. La Trace du 15 Août",
        category="Radioastronomie & Anomalies spatiales",
        epigraph="« 72 secondes de vacarme sur la ligne de l'hydrogène neutre. »",
        prompt=(
            "Le 15 août 1977, le radiotélescope « The Big Ear » de l'université de l'Ohio enregistre pendant 72 secondes "
            "une anomalie radio d'une puissance stupéfiante calée sur la raie d'émission de l'hydrogène neutre (1420,405 MHz).\n"
            "Sur le listing papier de l'ordinateur IBM 1130, l'astronome Jerry Ehman découvre la montée et la descente de l'intensité du signal, "
            "codée par une séquence exacte de six caractères alphanumériques qu'il entoure au stylo rouge avant d'écrire son exclamation légendaire dans la marge.\n\n"
            "Quelle est cette suite brute exacte de 6 caractères imprimée sur le télétype ?"
        ),
        detail=None,
        accepted_hashes={
            "06fddfcbe9f1c0a617f151d730de0c826ef8b622951e8a85970a7819e8635d1f",
            "1afaecf55e011918ea108a859f723797cca09d4196b92a0d935410fd3bad859f",
        },
    ),
    GateRiddle(
        step=4,
        title="IV. L'Ombre du Midi",
        category="Géodésie antique & Alexandrie",
        epigraph="« Partout le second, jamais le premier. »",
        prompt=(
            "Au solstice d'été, à midi pile, les rayons du soleil atteignent le fond des puits de Syène sans faire d'ombre. "
            "Au même instant à Alexandrie, le gnomon projette une ombre mesurée à 1/50 de cercle. "
            "J'ai ainsi calculé pour la première fois la circonférence de la Terre avec une précision remarquable, deux siècles avant notre ère.\n\n"
            "Pourtant, mes rivaux envieux de la Bibliothèque d'Alexandrie me donnèrent un surnom méprisant, "
            "affirmant que j'étais le second dans tous les domaines du savoir sans jamais dominer aucun.\n"
            "Quel était ce surnom ?"
        ),
        detail=None,
        accepted_hashes={
            "00b00792685215694e875bc2fcf721d176c8c8d357a3e5747ff40b7e32e8fd1d",
            "22823651d6970216215315d7ca04cbdc72db9a11f0e264698d0f27177ae921db",
            "6c508a28b122aa1182918999ccf3088e23a0eaf6c86cf55e28dac4e4d280d92e",
            "ead449b00ce5ddb785da40f9368cc95a6e95e6031b94e6e1c21ccff4a46ce6a2",
            "f44e64e75f3948e9f73f8dfa94721c4ce8cbb4f265c4790c702b2d41cfbf2753",
        },
    ),
    GateRiddle(
        step=5,
        title="V. Le Polyalphabète Déchu",
        category="Cryptanalyse classique & Littérature",
        epigraph="« Le Prince des nuées détient la clé du dédale. »",
        prompt=(
            "Voici un message intercepté, chiffré selon la table de Vigenère standard (A=0, B=1 ... Z=25) :\n\n"
            "La clé de déchiffrement est le prénom du poète maudit qui écrivit « L'Albatros » et « Les Fleurs du Mal » (7 lettres).\n"
            "Déchiffrez le cryptogramme pour révéler le mot secret de 10 lettres en français."
        ),
        detail="CRYPTOGRAMME : N H B P C M F V O E",
        accepted_hashes={
            "2f599fd8dc89ac65ff74a7ca6b3a789147eecc4b4254f8cbfdd4e5bf94c6fd0c",
            "4610d8b51a5fc1686917f5f2c22b8a98b71c5bea5e56d0c0a9c8e79427a09a3d",
            "b24fb9c07f5d7f5bcc23ec1086224abb4685f9a96386c3610cd16465fd98d637",
        },
    ),
    GateRiddle(
        step=6,
        title="VI. L'Écho des Nombres Premiers",
        category="Théorie de la démonstration & Fondements logiques",
        epigraph="« Le miroir arithmétique où la syntaxe se contemple elle-même. »",
        prompt=(
            "En 1931, pour démontrer que tout système formel contenant l'arithmétique élémentaire comporte des propositions indécidables, "
            "Kurt Gödel conçoit une méthode révolutionnaire : il assigne à chaque symbole, formule et démonstration une signature numérique unique "
            "en utilisant la décomposition en puissances de nombres premiers consécutifs (2^a * 3^b * 5^c...).\n\n"
            "Quel mot (ou nom composé) désigne ce procédé d'arithmétisation de la syntaxe ou le nombre entier unique résultant de ce codage ?"
        ),
        detail=None,
        accepted_hashes={
            "1062eaea18c8c632b65777b35a8c91bf14bd9437b6d1c826b18a0e7e872fad2d",
            "205dced5834a3479c6085512bf9fdf81185d24b449638ef26f5108fef88bbd05",
            "2fec49d3d855b2a7361dcee58a9566f102f3bea39ac2d11419eb5017380d3460",
            "32c84c41fafb36b7a58058d312afecaf2bb19fcfd41dd42d75a946933c255f3a",
            "5c6665cb841bc264408f42eb2675453acb90f596476ac5e1a32de1d5f76ec63f",
            "a384cf147f20980fd4fe49088f4bfa74385542ac45f93e444a9431e597c10180",
            "bd83fd7f645be053680321dac812291e6fe7ecc59616f29ab7078a75f02325f7",
        },
    ),
    GateRiddle(
        step=7,
        title="VII. La Première Voix",
        category="Histoire antique & Épigraphie sumérienne",
        epigraph="« Vingt-trois siècles avant notre ère, une plume grave son nom. »",
        prompt=(
            "Vers 2300 avant notre ère, dans la cité sumérienne d'Ur, la fille du roi Sargon d'Akkad fut nommée grande prêtresse du dieu lunaire Nanna.\n"
            "Sur des tablettes d'argile en écriture cunéiforme, elle composa des hymnes sacrés dédiés à la déesse Inanna et grava sa propre signature, "
            "devenant la toute première personne de l'histoire humaine universelle — tous genres et continents confondus — "
            "dont une œuvre littéraire porte le nom d'auteur attesté.\n\n"
            "Quel est le nom de cette poétesse et prêtresse ?"
        ),
        detail=None,
        accepted_hashes={
            "156bf1c5b6f99c5535d18f707446430dbd4091a60802c42d8639781a93cb9d7f",
            "399f1fa6358edb26cbaa0c7f86ab4f4b567b8bd579fc0a06cf3fdae0d35dad54",
            "7d7db6c033a3b4c36fcb64fa2e80ccf719057735341944d9882125ad9b88ccf2",
            "89cc66929daa90f423b1a2c4902bf83714f39034dd4bf51d1da8e9fbd8b79be1",
            "d8475ebc11c99fca7365aeffae03f861cfaa53440d2a7f57d7a7aa22d2127ccc",
        },
    ),
    GateRiddle(
        step=8,
        title="VIII. L'Horloge de Bronze",
        category="Archéoastronomie & Mécanique céleste",
        epigraph="« Deux cent vingt-trois lunes pour annoncer l'obscurité. »",
        prompt=(
            "Repêchée en 1901 au large d'une île grecque dans l'épave d'une galère romaine, "
            "cette machine stupéfiante à engrenages différentiels de bronze modélisait le cosmos.\n"
            "Sur sa spirale arrière comportant 223 cases, elle calculait avec exactitude la récurrence des éclipses solaires et lunaires.\n\n"
            "Ce cycle astronomique d'origine chaldéenne, correspondant à 223 mois synodiques (soit exactement 18 ans, 11 jours et 8 heures), "
            "porte un nom séculaire universellement connu. Quel est ce mot ?"
        ),
        detail=None,
        accepted_hashes={
            "1416f32848a017b085e373064f7a661f4917690f35b12687546cbbd07f5e9e1c",
            "1546c8505ce6a07a85653f8420d1afa9c84a5f5f7fb81a2219261659b06a66f5",
            "4bf8e7970a6fe46e29c4185462a22bb000823a818f7327d34c8e82ff05c4fcbd",
            "605d2a8d9690a01215fe8182d1c253e79d4435fafa835df92eda2ccd1cdf1f3b",
            "9288af2a090de7f92a166178ae6c56973bb97737b9fa19512c206cf53d57f911",
            "9df5e1801c7ef733e13bf99b53045557a16690df1e87c55fa3a0174307710e38",
            "c137b2b79594ffed1913cfe39a67e226e7cc0338357015fbfb9c28093a49e686",
        },
    ),
    GateRiddle(
        step=9,
        title="IX. Le Prix de l'Oubli",
        category="Thermodynamique & Théorie de l'information",
        epigraph="« Traiter l'information ne brûle rien ; c'est la détruire qui réchauffe le monde. »",
        prompt=(
            "Pour terrasser le Démon imaginé par James Clerk Maxwell en 1867, il fallut près d'un siècle.\n"
            "En 1961, le physicien Rolf Landauer découvrit le principe fondamental reliant physique et information : "
            "la mesure et le calcul logique d'une donnée peuvent être théoriquement réversibles sans dissiper d'énergie.\n"
            "En revanche, une opération logique bien particulière détruit de l'information de manière irréversible "
            "et dissipe obligatoirement dans l'environnement une quantité minimale de chaleur de kT ln(2) joules par bit.\n\n"
            "Quelle est cette opération élémentaire et inéluctable sur un bit de mémoire ?"
        ),
        detail=None,
        accepted_hashes={
            "03fc180b4bbace2cd4ad4b15fbc117f3c565d8f9f241d2eed4acedf5c4c87102",
            "1a162e3b22cfafe50e7358f1058661674073c52e423cefbaa740c959411ea390",
            "2159d0395613a518eca34f16e02abb4de14168513d738ca4e15592d5527ba876",
            "39aeabd73539cacad8c79a75a23855e2bed137be7977ca6f8cb867a6957ddc02",
            "708be5bd415989998e5586342060085e5a0887c5ecbd93b67d82077e4d0972d6",
            "83275efa55a391a480e92a1c3dc70f41b2e62f047021ad0743fccdd030e47125",
            "83b27bf85945230d7856f77da4eb94a3319ad82292cfc3793753f1b3d9b45e18",
            "bdfde66470f9864fe2deed0856bef310f22b92e7c063ad0408ee0d8fcbccb50c",
            "bffd4ba2c38e5b712b55057072e9b3cc1c02e0bdd5f50038ac0cebd47e00de58",
            "d5685fa6feadf3c191ee70f4fc45b001e4f1898468da9f9b7e1d8e591f8ee57a",
            "f35b75d8fa4c1debcb3d5905ce10573b13f8c508086c42dac3cac18edc6b89b4",
        },
    ),
    GateRiddle(
        step=10,
        title="X. Le Verbe Carré",
        category="Épigraphie romaine & Cryptogramme mystique",
        epigraph="« S A T O R / A R E P O / T E N E T / O P E R A / R O T A S »",
        prompt=(
            "Gravé dans la pierre à Pompéi avant l'éruption du Vésuve en 79, "
            "ce carré magique de 25 lettres forme un palindrome parfait lisible en tous sens.\n\n"
            "Comme l'ont démontré les érudits Grosser et Agrell en 1926, ses 25 lettres peuvent être exactement réarrangées "
            "pour former une croix grecque articulée autour de la lettre N centrale.\n"
            "Aux quatre branches de cette croix se tiennent deux A et deux O (Alpha et Oméga).\n"
            "La croix elle-même, répétée horizontalement et verticalement en traversant le N commun, épelle deux mots en latin.\n\n"
            "Quelle est cette locution latine sacrée qui brise le dixième et dernier sceau ?"
        ),
        detail="S A T O R\nA R E P O\nT E N E T\nO P E R A\nR O T A S",
        accepted_hashes={
            "0001f129ff21e00f006e07882969723d089275abaab8c3eca07102d998059fd0",
            "5c5a6fc39e510ac2dc87e6421dd794e93154879ae4b4723b992f75e0b6d500a5",
            "6f44b07d419cd7fdc00ca5bb41fd14e87bdd2adb9c437a212dddafb85f8d4f13",
        },
    ),
)


class SecretGateManager:
    """Gère la progression chiffrée des 10 énigmes sans jamais exposer les réponses."""

    def __init__(self) -> None:
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}

    def get_riddle(self, step: int) -> Optional[GateRiddle]:
        if 1 <= step <= len(_GATE_RIDDLES):
            return _GATE_RIDDLES[step - 1]
        return None

    def get_player_session(self, player_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        """Récupère la session du joueur depuis la mémoire ou la base de données."""
        if not player_id:
            return {"step": 1, "completed": False, "attempts": 0, "last_attempt": 0}

        if player_id in self._memory_sessions:
            return self._memory_sessions[player_id]

        try:
            from app.database import get_gate_progress, is_gate_unlocked
            if is_gate_unlocked(player_id, username):
                sess = {"step": 11, "completed": True, "attempts": 0, "last_attempt": 0}
                self._memory_sessions[player_id] = sess
                return sess
            prog = get_gate_progress(player_id)
            if prog and (prog["step"] > 1 or prog["completed"] or prog["attempts"] > 0):
                self._memory_sessions[player_id] = prog
                return prog
        except Exception:
            pass

        self._memory_sessions[player_id] = {
            "step": 1,
            "completed": False,
            "attempts": 0,
            "last_attempt": 0,
        }
        return self._memory_sessions[player_id]

    def get_current_state(self, player_id: str, username: Optional[str] = None) -> Dict[str, Any]:
        """Renvoie l'état public de l'énigme active pour le joueur (sans jamais exposer de réponse)."""
        session = self.get_player_session(player_id, username)
        step = session.get("step", 1)
        if session.get("completed") or step > len(_GATE_RIDDLES):
            token = generate_gate_token(player_id)
            return {
                "completed": True,
                "step": 11,
                "total": len(_GATE_RIDDLES),
                "token": token,
                "message": "Tous les sceaux sont brisés. Le sanctuaire est ouvert.",
            }

        riddle = self.get_riddle(step)
        if not riddle:
            return {
                "completed": False,
                "step": 1,
                "total": len(_GATE_RIDDLES),
                "error": "Énigme introuvable.",
            }

        return {
            "completed": False,
            "step": riddle.step,
            "total": len(_GATE_RIDDLES),
            "riddle": {
                "step": riddle.step,
                "title": riddle.title,
                "category": riddle.category,
                "epigraph": riddle.epigraph,
                "prompt": riddle.prompt,
                "detail": riddle.detail,
            },
        }

    def verify_guess(
        self,
        player_id: str,
        guess: str,
        username: Optional[str] = None,
    ) -> Tuple[bool, bool, Dict[str, Any]]:
        """
        Vérifie la réponse proposée.
        Retourne (is_correct, is_completed, payload_result).
        """
        now = time.time()
        session = self.get_player_session(player_id, username)

        # Vérification du verrouillage temporaire en cas d'échecs excessifs (anti-bruteforce)
        lockout_until = session.get("lockout_until", 0)
        if now < lockout_until:
            remaining = round(lockout_until - now, 1)
            return False, False, {
                "error": f"Le Gardien s'est retiré face à cette précipitation. Réessayez dans {remaining}s.",
                "retry_after": remaining,
            }

        time_since_last = now - session.get("last_attempt", 0)
        if time_since_last < MIN_SECONDS_BETWEEN_GUESSES:
            remaining = round(MIN_SECONDS_BETWEEN_GUESSES - time_since_last, 1)
            return False, False, {
                "error": "Trop de tentatives rapides. Veuillez patienter au moins 1 seconde.",
                "retry_after": remaining,
            }

        step = session.get("step", 1)
        if session.get("completed") or step > len(_GATE_RIDDLES):
            token = generate_gate_token(player_id)
            return True, True, {
                "correct": True,
                "completed": True,
                "token": token,
                "message": "Vous avez déjà brisé tous les sceaux. Le passage est ouvert.",
            }

        riddle = self.get_riddle(step)
        if not riddle:
            return False, False, {"error": "Énigme introuvable."}

        norm_guess = normalize_answer(guess)
        guess_hash = _hash_normalized(norm_guess)

        session["last_attempt"] = now

        if guess_hash in riddle.accepted_hashes:
            # Réinitialisation du compteur d'erreurs en cas de succès
            session["rapid_fails"] = 0
            session["lockout_until"] = 0

            is_final_step = step == len(_GATE_RIDDLES)
            if is_final_step:
                session["completed"] = True
                session["step"] = 11
                token = generate_gate_token(player_id)
                self._save_session(player_id, session, username=username)
                return True, True, {
                    "correct": True,
                    "completed": True,
                    "token": token,
                    "step": step,
                    "message": "L'ultime sceau s'effondre dans un halo d'or. Le passage est ouvert !",
                }
            else:
                session["step"] = step + 1
                self._save_session(player_id, session, username=username)
                next_riddle = self.get_riddle(session["step"])
                return True, False, {
                    "correct": True,
                    "completed": False,
                    "step": session["step"],
                    "total": len(_GATE_RIDDLES),
                    "riddle": {
                        "step": next_riddle.step,
                        "title": next_riddle.title,
                        "category": next_riddle.category,
                        "epigraph": next_riddle.epigraph,
                        "prompt": next_riddle.prompt,
                        "detail": next_riddle.detail,
                    },
                    "message": f"Sceau {step} brisé avec succès ! Le sceau suivant apparaît...",
                }
        else:
            session["attempts"] = session.get("attempts", 0) + 1
            rapid_fails = session.get("rapid_fails", 0) + 1
            session["rapid_fails"] = rapid_fails

            if rapid_fails >= MAX_RAPID_FAILS:
                session["lockout_until"] = now + LOCKOUT_PENALTY_SECONDS
                session["rapid_fails"] = 0
                self._save_session(player_id, session, username=username)
                return False, False, {
                    "correct": False,
                    "completed": False,
                    "step": step,
                    "error": f"Trop d'échecs consécutifs. Le Gardien s'enferme dans le silence pendant {int(LOCKOUT_PENALTY_SECONDS)} secondes.",
                    "retry_after": LOCKOUT_PENALTY_SECONDS,
                }

            self._save_session(player_id, session, username=username)
            return False, False, {
                "correct": False,
                "completed": False,
                "step": step,
                "message": "Ce n'est pas la réponse attendue. Le sceau demeure impassible.",
            }

    def reset_progress(self, player_id: str, username: Optional[str] = None) -> None:
        """Réinitialise la progression d'un joueur."""
        if player_id in self._memory_sessions:
            del self._memory_sessions[player_id]
        try:
            from app.database import reset_gate_progress
            reset_gate_progress(player_id=player_id, username=username)
        except Exception:
            pass

    def _save_session(self, player_id: str, session: Dict[str, Any], username: Optional[str] = None):
        self._memory_sessions[player_id] = session
        try:
            from app.database import save_gate_progress
            save_gate_progress(
                player_id=player_id,
                step=session.get("step", 1),
                completed=session.get("completed", False),
                attempts=session.get("attempts", 0),
                last_attempt=session.get("last_attempt", 0),
                username=username,
            )
        except Exception:
            pass


secret_gate_manager = SecretGateManager()
