#!/usr/bin/env python3
"""Download a small public sample of the original LinkedIn or Interpol public assets.

This script intentionally uses only public game endpoints exposed by the website itself.
It does not scrape private LinkedIn profiles or non-public personal data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib import request, error

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


def collect(count: int, out_dir: Path) -> List[Dict[str, Any]]:
    ensure_dir(out_dir)
    images_dir = out_dir / "images"
    ensure_dir(images_dir)

    seen_ids: set[str] = set()
    records: List[Dict[str, Any]] = []

    for _ in range(max(1, count)):
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
            continue
        seen_ids.add(person_id)

        # Use a neutral guess to reveal the actual answer from the public API.
        answer = fetch_json(
            f"{BASE_URL}/api/check-answer",
            method="POST",
            payload={"personId": person_id, "userChoice": "linkedin"},
        )

        person_record = answer.get("person") or {}
        label = person_record.get("type") or "unknown"
        if label not in {"linkedin", "interpol"}:
            label = "unknown"

        filename = f"{person_id}_{label}.webp"
        target = images_dir / filename
        if not target.exists():
            try:
                download_binary(photo_url, target)
            except Exception as exc:  # pragma: no cover - network-specific
                print(f"[WARN] could not download {photo_url}: {exc}", file=sys.stderr)
                continue

        records.append(
            {
                "id": person_id,
                "label": label,
                "source": "linkedin-or-interpol-public-game",
                "source_url": photo_url,
                "image_path": str(target.relative_to(out_dir)),
                "name": person_record.get("name"),
                "surname": person_record.get("surname"),
                "description": person_record.get("i18n", {}).get("fr")
                or person_record.get("i18n", {}).get("en"),
            }
        )

        if len(records) >= count:
            break

    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(records)} public images in {out_dir}")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a small public sample of the original LinkedIn or Interpol game assets.")
    parser.add_argument("--count", type=int, default=12, help="Number of public images to download.")
    parser.add_argument("--out", type=str, default="app/data/linkedin_or_interpol", help="Output directory for images and metadata.")
    args = parser.parse_args()

    out_dir = Path(args.out)
    collect(args.count, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
