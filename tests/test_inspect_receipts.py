"""Tests for tools/inspect_receipts.py (import-level and smoke tests)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import inspect_receipts  # noqa: E402  (tools/ not a package)
from telegram_receipts_bot.ocr import OcrError, OcrResult  # noqa: E402


def _settings():
    return inspect_receipts._make_settings()


def test_make_settings_ocr_mode_auto():
    settings = _settings()
    assert settings.ocr_mode == "auto"


def test_inspect_image_prints_parsed_fields(capsys):
    fake_result = OcrResult(
        text=(
            "BIEDRONKA POZNAN\n"
            "NIP 7791011327\n"
            "PARAGON FISKALNY\n"
            "22-04-2026 14:33\n"
            "KAWA MIELONA 15,99\n"
            "SUMA PLN 15,99\n"
        ),
        confidence=0.92,
        variant="gray",
    )
    settings = _settings()
    with patch("inspect_receipts.extract_ocr_result", return_value=fake_result):
        inspect_receipts.inspect_image(Path("fake.jpg"), settings, raw_lines=40, show_raw=True)

    out = capsys.readouterr().out
    assert "fake.jpg" in out
    assert "gray" in out
    assert "92.0%" in out
    assert "7791011327" in out
    assert "paragon" in out
    assert "15.99" in out
    assert "BIEDRONKA POZNAN" in out
    assert "KAWA MIELONA" in out


def test_inspect_image_ocr_error_prints_and_continues(capsys):
    settings = _settings()
    with patch("inspect_receipts.extract_ocr_result", side_effect=OcrError("engine crash")):
        inspect_receipts.inspect_image(Path("bad.jpg"), settings, raw_lines=40, show_raw=True)

    out = capsys.readouterr().out
    assert "OCR ERROR" in out
    assert "engine crash" in out


def test_inspect_image_no_raw_hides_ocr_text(capsys):
    fake_result = OcrResult(text="NIP 7791011327\n22-04-2026\nSUMA PLN 5,00\n", confidence=0.8, variant="raw")
    settings = _settings()
    with patch("inspect_receipts.extract_ocr_result", return_value=fake_result):
        inspect_receipts.inspect_image(Path("r.jpg"), settings, raw_lines=40, show_raw=False)

    out = capsys.readouterr().out
    assert "Raw OCR" not in out


def test_inspect_image_raw_lines_truncates(capsys):
    text = "\n".join(f"line{i}" for i in range(100))
    fake_result = OcrResult(text=text, confidence=0.9, variant="raw")
    settings = _settings()
    with patch("inspect_receipts.extract_ocr_result", return_value=fake_result):
        inspect_receipts.inspect_image(Path("r.jpg"), settings, raw_lines=5, show_raw=True)

    out = capsys.readouterr().out
    assert "95 more lines hidden" in out
