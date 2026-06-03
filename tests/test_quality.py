"""Tests for the OCR/image/field quality gate in quality.py."""
from pathlib import Path

import pytest

from telegram_receipts_bot.models import ReceiptDraft
from telegram_receipts_bot.quality import assess_receipt_risk


# ── helpers ──────────────────────────────────────────────────────────────────


def _complete_draft(confidence: float = 0.95) -> ReceiptDraft:
    """Complete draft with all critical fields and realistic OCR text."""
    draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
    draft.kwota = 127.00
    draft.data_dokumentu = "2026-04-09"
    draft.nip = "7471727805"
    draft.sprzedawca = "Sklep ABC"
    draft.ocr_confidence = confidence
    draft.ocr_variant = "gray"
    draft.ocr_text = (
        "Sklep ABC Sp. z o.o.\n"
        "NIP: 7471727805\n"
        "Data: 2026-04-09\n"
        "Paragon nr 12345\n"
        "Razem: 127.00 zł\n"
    )
    return draft


def _make_tiny_image(tmp_path: Path) -> Path:
    from PIL import Image  # type: ignore[import]

    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    path = tmp_path / "tiny.jpg"
    img.save(path)
    return path


def _make_dark_image(tmp_path: Path) -> Path:
    from PIL import Image  # type: ignore[import]

    img = Image.new("RGB", (800, 600), color=(15, 15, 15))
    path = tmp_path / "dark.jpg"
    img.save(path)
    return path


# ── test cases ────────────────────────────────────────────────────────────────


class TestCompleteDocument:
    def test_not_suspicious(self) -> None:
        result = assess_receipt_risk(
            _complete_draft(),
            source_kind="document",
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert not result.suspicious
        assert result.severity == "ok"
        assert result.reasons == []
        assert result.photo_hint == ""

    def test_complete_photo_not_suspicious_but_hint_present(self) -> None:
        result = assess_receipt_risk(
            _complete_draft(),
            source_kind="photo",
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert not result.suspicious
        assert result.severity == "warn"
        assert result.photo_hint != ""
        assert "dokument" in result.photo_hint.lower()


class TestOcrConfidence:
    def test_low_nonzero_confidence_is_suspicious(self) -> None:
        result = assess_receipt_risk(
            _complete_draft(confidence=0.40),
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert result.suspicious
        assert any("pewność" in r for r in result.reasons)

    def test_unknown_confidence_zero_not_suspicious_by_itself(self) -> None:
        result = assess_receipt_risk(
            _complete_draft(confidence=0.0),
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert not result.suspicious


class TestFieldCompleteness:
    def test_missing_date_is_suspicious(self) -> None:
        draft = _complete_draft()
        draft.data_dokumentu = ""
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert result.suspicious
        assert any("daty" in r for r in result.reasons)

    def test_missing_kwota_is_suspicious(self) -> None:
        draft = _complete_draft()
        draft.kwota = None
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert result.suspicious
        assert any("kwot" in r for r in result.reasons)

    def test_missing_nip_and_seller_is_suspicious(self) -> None:
        draft = _complete_draft()
        draft.nip = ""
        draft.sprzedawca = ""
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert result.suspicious
        assert any("NIP" in r for r in result.reasons)

    def test_nip_present_without_seller_is_ok(self) -> None:
        draft = _complete_draft()
        draft.sprzedawca = ""
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert not result.suspicious

    def test_seller_present_without_nip_is_ok(self) -> None:
        draft = _complete_draft()
        draft.nip = ""
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert not result.suspicious


class TestOcrTextQuality:
    def test_short_ocr_text_is_suspicious(self) -> None:
        draft = _complete_draft()
        draft.ocr_text = "AB"   # well below _MIN_OCR_CHARS
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert result.suspicious
        assert any("krótki" in r for r in result.reasons)

    def test_few_lines_is_suspicious(self) -> None:
        draft = _complete_draft()
        draft.ocr_text = "razem 127 zł paragon sklep gotówka"  # 1 line, few chars
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        assert result.suspicious
        assert any("krótki" in r for r in result.reasons)

    def test_empty_ocr_text_does_not_flag_text_quality(self) -> None:
        # Empty text means OCR was not run yet; field checks cover real issues.
        draft = _complete_draft()
        draft.ocr_text = ""
        result = assess_receipt_risk(draft, confidence_warn=0.75, max_auto_save_amount=10_000)
        # No text quality reasons — only field checks apply (all fields OK here).
        assert not result.suspicious


class TestImageQuality:
    def test_tiny_image_is_suspicious(self, tmp_path: Path) -> None:
        path = _make_tiny_image(tmp_path)
        draft = _complete_draft()
        result = assess_receipt_risk(
            draft,
            image_path=path,
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert result.suspicious
        assert result.signals is not None
        assert result.signals.image_too_small
        assert any("mały" in r for r in result.reasons)

    def test_dark_image_is_suspicious(self, tmp_path: Path) -> None:
        path = _make_dark_image(tmp_path)
        draft = _complete_draft()
        result = assess_receipt_risk(
            draft,
            image_path=path,
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert result.suspicious
        assert result.signals is not None
        assert result.signals.image_too_dark
        assert any("ciemny" in r for r in result.reasons)

    def test_unreadable_image_path_no_crash(self, tmp_path: Path) -> None:
        draft = _complete_draft()
        result = assess_receipt_risk(
            draft,
            image_path=tmp_path / "nonexistent.jpg",
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        # Must not raise; image signals should mark as unreadable.
        assert result.signals is not None
        assert result.signals.image_readable is False
        # Field checks still work — this draft is complete, so not suspicious.
        assert not result.suspicious

    def test_none_image_path_no_crash(self) -> None:
        draft = _complete_draft()
        result = assess_receipt_risk(
            draft,
            image_path=None,
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert not result.suspicious


class TestSourceKindPhoto:
    def test_photo_with_real_issues_appends_document_nudge(self) -> None:
        draft = _complete_draft()
        draft.data_dokumentu = ""  # real issue
        result = assess_receipt_risk(
            draft, source_kind="photo", confidence_warn=0.75, max_auto_save_amount=10_000
        )
        assert result.suspicious
        assert any("plik" in r or "dokument" in r for r in result.reasons)

    def test_photo_alone_does_not_cause_suspicious(self) -> None:
        result = assess_receipt_risk(
            _complete_draft(),
            source_kind="photo",
            confidence_warn=0.75,
            max_auto_save_amount=10_000,
        )
        assert not result.suspicious
