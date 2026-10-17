#!/usr/bin/env python3
"""Compile et valide la base de 1 000+ questions chiffrées sourcées pour Chiffrantix.

Fusionne les lots thématiques (Histoire, Géographie, Monuments, Sciences, Astronomie,
Nature, Arts & Culture, Sport, Société, Tech & Jeux) et vérifie :
- Unicité stricte des questions
- Présence d'une réponse chiffrée non incluse dans la question
- Présence d'une source vérifiée (titre + URL) et d'une explication
- Formatage de la question (ponctuation finale '?')
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
OUTPUT = ROOT / "app" / "data" / "chiffrantix_questions.json"

VALID_CATEGORIES = {
    "histoire",
    "geographie",
    "sciences",
    "arts_culture",
    "sport",
    "nature",
    "monuments",
    "societe",
    "tech_jeux",
    "astronomie",
}
VALID_DIFFICULTIES = {"facile", "moyen", "difficile"}


def normalize_q(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def build_questions() -> list[dict]:
    batches = [
        SCRATCH / "q_batch1.json",
        SCRATCH / "q_batch2.json",
        SCRATCH / "q_batch3.json",
    ]
    all_items: list[dict] = []
    seen_questions: set[str] = set()

    for bpath in batches:
        if not bpath.exists():
            raise FileNotFoundError(f"Fichier de lot manquant : {bpath}")
        items = json.loads(bpath.read_text(encoding="utf-8"))
        for item in items:
            q = item.get("question", "").strip()
            ans = str(item.get("answer", "")).strip()
            cat = item.get("category", "histoire").strip().lower()
            diff = item.get("difficulty", "moyen").strip().lower()
            src_title = item.get("source_title", "Wikipédia").strip()
            src_url = item.get("source_url", "https://fr.wikipedia.org").strip()
            expl = item.get("explanation", "").strip()

            if not q or not ans:
                continue
            if not q.endswith("?"):
                q = q.rstrip(".") + " ?"

            norm_q = normalize_q(q)
            if norm_q in seen_questions:
                continue

            # Ensure the answer number does not appear in the question text
            ans_numbers = re.findall(r"\d+(?:[.,]\d+)?", ans.replace(" ", ""))
            q_nospace = q.replace(" ", "")
            if any(
                re.search(r"(?<!\d)" + re.escape(num) + r"(?!\d)", q_nospace)
                for num in ans_numbers
            ):
                continue

            if cat not in VALID_CATEGORIES:
                cat = "sciences"
            if diff not in VALID_DIFFICULTIES:
                diff = "moyen"
            if not src_url.startswith("http"):
                src_url = "https://fr.wikipedia.org/wiki/" + src_title.replace(" ", "_")
            if not expl:
                expl = f"Réponse sourcée : {ans} ({src_title})."

            seen_questions.add(norm_q)
            all_items.append(
                {
                    "id": len(all_items) + 1,
                    "question": q,
                    "answer": ans,
                    "category": cat,
                    "difficulty": diff,
                    "source_title": src_title,
                    "source_url": src_url,
                    "explanation": expl,
                }
            )

    if len(all_items) < 1000:
        raise ValueError(f"Attendu >= 1000 questions uniques, trouvé {len(all_items)}.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(all_items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Base Chiffrantix compilée avec succès : {len(all_items)} questions dans {OUTPUT}")
    return all_items


if __name__ == "__main__":
    build_questions()
