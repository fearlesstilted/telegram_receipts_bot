#!/usr/bin/env python3
"""Inspect receipt images: run OCR + parser and print results.

Usage:
    PYTHONPATH=src python tools/inspect_receipts.py data/receipts/eval_20260602_*.jpg
    PYTHONPATH=src python tools/inspect_receipts.py image.jpg --raw-lines 20
    PYTHONPATH=src python tools/inspect_receipts.py image.jpg --no-raw
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from telegram_receipts_bot.config import Settings
from telegram_receipts_bot.models import ReceiptDraft
from telegram_receipts_bot.ocr import OcrError, extract_ocr_result
from telegram_receipts_bot.parser import parse_receipt_text


def _make_settings() -> Settings:
    data_dir = REPO_ROOT / "data"
    return Settings(
        telegram_bot_token="",
        telegram_allowed_chat_id=None,
        monthly_budget=0.0,
        data_dir=data_dir,
        ocr_mode="auto",
        telegram_photo_max_pixels=1_400_000,
        max_auto_save_amount=10_000.0,
        tesseract_cmd="tesseract",
        timezone_name="Europe/Warsaw",
    )


def inspect_image(image_path: Path, settings: Settings, raw_lines: int, show_raw: bool) -> None:
    sep = "-" * 60
    print(sep)
    print(f"File:       {image_path.name}")

    try:
        ocr = extract_ocr_result(image_path, settings)
    except OcrError as exc:
        print(f"OCR ERROR:  {exc}")
        return

    draft = parse_receipt_text(ocr.text, ReceiptDraft.empty(image_path.stem, 0, str(image_path)))

    kwota_str = f"{draft.kwota:.2f}" if draft.kwota is not None else "-"

    print(f"Variant:    {ocr.variant}")
    print(f"Confidence: {ocr.confidence:.1%}")
    print("Parsed fields:")
    print(f"  typ_dokumentu:  {draft.typ_dokumentu or '-'}")
    print(f"  data_dokumentu: {draft.data_dokumentu or '-'}")
    print(f"  kwota:          {kwota_str}")
    print(f"  nip:            {draft.nip or '-'}")
    print(f"  sprzedawca:     {draft.sprzedawca or '-'}")
    print(f"  nr_fv:          {draft.nr_fv or '-'}")
    print(f"  nr_paragonu:    {draft.nr_paragonu or '-'}")
    print(f"  adres:          {draft.adres or '-'}")
    print(f"  towar:          {draft.towar or '-'}")

    if show_raw:
        lines = ocr.text.splitlines()
        shown = lines[:raw_lines]
        print(f"Raw OCR ({len(lines)} lines, showing {len(shown)}):")
        for line in shown:
            print(f"  {line}")
        if len(lines) > raw_lines:
            print(f"  ... ({len(lines) - raw_lines} more lines hidden, use --raw-lines to show more)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect receipt images with OCR + parser.")
    parser.add_argument("images", nargs="+", type=Path, help="Receipt image files to inspect")
    parser.add_argument(
        "--raw-lines",
        type=int,
        default=40,
        metavar="N",
        help="Number of raw OCR lines to print (default: 40)",
    )
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Hide raw OCR text entirely",
    )
    args = parser.parse_args()

    settings = _make_settings()
    show_raw = not args.no_raw

    for image_path in args.images:
        inspect_image(image_path, settings, args.raw_lines, show_raw)

    print("-" * 60)


if __name__ == "__main__":
    main()
