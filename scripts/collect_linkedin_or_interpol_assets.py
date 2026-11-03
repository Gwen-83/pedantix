#!/usr/bin/env python3
"""Download the complete public profile catalog for the original LinkedIn or Interpol game.

This script intentionally uses only public game endpoints exposed by the website itself.
It does not scrape private LinkedIn profiles or any non-public personal data.
The catalog is collected until the underlying API starts repeating IDs, which indicates the
full public set has been reached.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib import error, request

BASE_URL = "https://linkedin-or-interpol.com"
USER_AGENT = "Mozilla/5.0"


def fetch_json(url: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Any:
    data = None
    headers = {"User-Agent": USER_AGENT}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))


def download_binary(url: str, destination: Path) -> None:
    headers = {"User-Agent": USER_AGENT}
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=30) as resp:
        destination.write_bytes(resp.read())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _entry_from_person(person_id: str, photo_url: str, answer: Dict[str, Any]) -> Dict[str, Any]:
    person_record = answer.get("person") or {}
    label = person_record.get("type") or "unknown"
    if label not in {"linkedin", "interpol"}:
        label = "unknown"

    description = person_record.get("i18n", {}).get("fr") or person_record.get("i18n", {}).get("en")
    name = (person_record.get("name") or "").strip()
    surname = (person_record.get("surname") or "").strip()
    filename = f"{person_id}.webp"

    return {
        "id": person_id,
        "name": name,
        "surname": surname,
        "description": description,
        "label": label,
        "source": "linkedin-or-interpol-public-game",
        "source_url": photo_url,
        "image_path": f"images/{filename}",
    }


def collect(out_dir: Path, max_count: int | None = None) -> List[Dict[str, Any]]:
    ensure_dir(out_dir)
    images_dir = out_dir / "images"
    ensure_dir(images_dir)

    seen_ids: set[str] = set()
    records_by_id: Dict[str, Dict[str, Any]] = {}
    iteration = 0

    while True:
        iteration += 1
        try:
            person = fetch_json(f"{BASE_URL}/api/random-person")
        except (error.URLError, error.HTTPError, ValueError) as exc:
            print(f"[ERROR] fetch random person failed: {exc}", file=sys.stderr)
            break

        person_id = person.get("id")
        photo_url = person.get("photoUrl")
        if not person_id or not photo_url:
            continue

        if person_id in seen_ids:
            if len(seen_ids) > 0:
                break
            continue

        seen_ids.add(person_id)

        try:
            answer = fetch_json(
                f"{BASE_URL}/api/check-answer",
                method="POST",
                payload={"personId": person_id, "userChoice": "linkedin"},
            )
        except Exception as exc:  # pragma: no cover - network-specific
            print(f"[WARN] could not resolve metadata for {person_id}: {exc}", file=sys.stderr)
            continue

        record = _entry_from_person(person_id, photo_url, answer)
        target = images_dir / f"{person_id}.webp"
        if not target.exists():
            try:
                download_binary(photo_url, target)
            except Exception as exc:  # pragma: no cover - network-specific
                print(f"[WARN] could not download {photo_url}: {exc}", file=sys.stderr)
                continue

        records_by_id[person_id] = record

        if max_count is not None and len(records_by_id) >= max_count:
            break

        if iteration % 50 == 0:
            print(f"[INFO] collected {len(records_by_id)} unique profiles so far...")

    records = list(records_by_id.values())
    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(records)} public profiles in {out_dir}")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the complete public catalog of the original LinkedIn or Interpol game assets.")
    parser.add_argument("--count", type=int, default=0, help="Optional cap: stop after N unique profiles; default downloads the full public catalog until the API repeats IDs.")
    parser.add_argument("--out", type=str, default="app/data/linkedin_or_interpol", help="Output directory for images and metadata.")
    args = parser.parse_args()

    out_dir = Path(args.out)
    max_count = args.count if args.count > 0 else None
    collect(out_dir, max_count=max_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
