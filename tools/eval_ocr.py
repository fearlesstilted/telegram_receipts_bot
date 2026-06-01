#!/usr/bin/env python3
"""Lightweight OCR/parser evaluation harness.

Runs the real OCR + parser pipeline over a small set of labelled receipt photos and prints
a per-field accuracy table. Intended for 10-15 real receipts, not a large benchmark.

Privacy: labels and images stay under data/ (local, untracked). This script contains no
receipt data itself.

Usage:
    # 1. Generate a starter label file from previously confirmed saves (data/rows.jsonl):
    python tools/eval_ocr.py --init

    # 2. Open data/eval_labels.json, fill in the blank/placeholder entries by hand.

    # 3. Run the evaluation:
    python tools/eval_ocr.py
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_LABELS = REPO_ROOT / "data" / "eval_labels.json"
RECEIPTS_DIR = REPO_ROOT / "data" / "receipts"
ROWS_FILE = REPO_ROOT / "data" / "rows.jsonl"

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
FIELDS = ("data_dokumentu", "nip", "kwota", "sprzedawca", "nr")
SELLER_FUZZY_THRESHOLD = 0.80


def _label_template() -> dict:
    return {"data_dokumentu": "", "nip": "", "kwota": None, "sprzedawca": "", "nr": ""}


def init_labels(labels_path: Path) -> None:
    """Seed a label file from data/rows.jsonl, mapping rows to images via receipt_url."""
    images = _existing_images()
    seeded: dict[str, dict] = {name: _label_template() for name in images}
    unmapped: list[dict] = []

    if ROWS_FILE.exists():
        with ROWS_FILE.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                truth = {
                    "data_dokumentu": row.get("data_dokumentu") or "",
                    "nip": row.get("nip") or "",
                    "kwota": row.get("kwota"),
                    "sprzedawca": row.get("sprzedawca") or "",
                    "nr": row.get("nr_fv") or row.get("nr_paragonu") or "",
                }
                filename = Path(row.get("receipt_url") or "").name
                if filename and filename in seeded:
                    seeded[filename] = truth
                else:
                    unmapped.append({"original_receipt_url": row.get("receipt_url"), **truth})

    payload = {
        "_note": (
            "Fill in one entry per image in data/receipts. 'kwota' is a number or null. "
            "'nr' is the invoice or receipt number. Delete entries you do not want to score. "
            "Entries with all-empty fields are skipped."
        ),
        "_unmapped_known_values": unmapped,
        "labels": seeded,
    }
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    mapped = sum(1 for v in seeded.values() if any(_truth_present(v).values()))
    print(f"Wrote {labels_path}")
    print(f"  images found: {len(images)}, auto-seeded from rows.jsonl: {mapped}")
    print(f"  unmapped known values (assign by hand): {len(unmapped)}")


def _existing_images() -> list[str]:
    if not RECEIPTS_DIR.exists():
        return []
    return sorted(
        p.name for p in RECEIPTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def _truth_present(truth: dict) -> dict[str, bool]:
    return {
        "data_dokumentu": bool(truth.get("data_dokumentu")),
        "nip": bool(truth.get("nip")),
        "kwota": truth.get("kwota") is not None,
        "sprzedawca": bool(truth.get("sprzedawca")),
        "nr": bool(truth.get("nr")),
    }


def _field_match(field: str, truth, got) -> bool:
    if field == "kwota":
        if truth is None or got is None:
            return False
        return abs(float(truth) - float(got)) <= 0.01
    truth_s = (str(truth) if truth is not None else "").strip()
    got_s = (str(got) if got is not None else "").strip()
    if field == "sprzedawca":
        if not truth_s:
            return False
        ratio = SequenceMatcher(None, truth_s.lower(), got_s.lower()).ratio()
        return ratio >= SELLER_FUZZY_THRESHOLD
    if field == "nip":
        return _digits(truth_s) == _digits(got_s) and bool(_digits(truth_s))
    return truth_s == got_s and bool(truth_s)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def run_eval(labels_path: Path) -> int:
    if not labels_path.exists():
        print(f"Brak pliku etykiet: {labels_path}")
        print("Najpierw uruchom: python tools/eval_ocr.py --init")
        return 1

    from telegram_receipts_bot.config import load_settings
    from telegram_receipts_bot.models import ReceiptDraft
    from telegram_receipts_bot.ocr import extract_text
    from telegram_receipts_bot.parser import parse_receipt_text

    data = json.loads(labels_path.read_text(encoding="utf-8"))
    labels = data.get("labels", {})
    settings = load_settings()

    totals = {field: [0, 0] for field in FIELDS}  # [correct, scored]
    detail_rows: list[str] = []
    scored_images = 0

    for filename, truth in sorted(labels.items()):
        present = _truth_present(truth)
        if not any(present.values()):
            continue  # unlabeled entry, skip
        image_path = RECEIPTS_DIR / filename
        if not image_path.exists():
            detail_rows.append(f"{filename:<16} BRAK PLIKU")
            continue

        scored_images += 1
        draft = ReceiptDraft.empty(draft_id="eval", chat_id=0, source_path=str(image_path))
        try:
            text = extract_text(image_path, settings)
            draft = parse_receipt_text(text, draft)
        except Exception as exc:  # noqa: BLE001 - record OCR failure, keep going
            detail_rows.append(f"{filename:<16} OCR ERROR: {exc}")
            for field in FIELDS:
                if present[field]:
                    totals[field][1] += 1
            continue

        got = {
            "data_dokumentu": draft.data_dokumentu,
            "nip": draft.nip,
            "kwota": draft.kwota,
            "sprzedawca": draft.sprzedawca,
            "nr": draft.nr_fv or draft.nr_paragonu,
        }
        marks = []
        for field in FIELDS:
            if not present[field]:
                marks.append(f"{field}:-")
                continue
            ok = _field_match(field, truth.get(field), got.get(field))
            totals[field][1] += 1
            totals[field][0] += int(ok)
            marks.append(f"{field}:{'OK' if ok else 'X'}")
        detail_rows.append(f"{filename:<16} " + "  ".join(marks))

    print("=" * 60)
    print(f"OCR eval - {scored_images} receipt(s) scored")
    print("=" * 60)
    for row in detail_rows:
        print(row)
    print("-" * 60)
    print("Per-field accuracy:")
    for field in FIELDS:
        correct, scored = totals[field]
        pct = f"{100 * correct / scored:.0f}%" if scored else "n/a"
        print(f"  {field:<16} {correct}/{scored}  ({pct})")
    print("=" * 60)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight OCR/parser eval")
    parser.add_argument("--init", action="store_true", help="seed data/eval_labels.json from rows.jsonl")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS, help="path to labels json")
    args = parser.parse_args()

    if args.init:
        init_labels(args.labels)
        return
    sys.exit(run_eval(args.labels))


if __name__ == "__main__":
    main()
