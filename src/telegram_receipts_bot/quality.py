from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .models import ReceiptDraft

logger = logging.getLogger(__name__)

_MIN_OCR_LINES = 3
_MIN_OCR_CHARS = 30
_MIN_IMAGE_PIXELS = 200_000  # ~447×447 px
_DARK_THRESHOLD = 50         # mean brightness out of 255
_BRIGHT_THRESHOLD = 240
_LOW_CONTRAST_STD = 20       # pixel std-dev below this is flat/washed-out

_FISCAL_MARKERS = frozenset({
    "paragon", "faktura", "nip", "zł", "razem", "suma",
    "łącznie", "podatek", "vat", "gotówka", "sprzedawca", "kwota",
})


@dataclass
class OcrQualitySignals:
    line_count: int = 0
    char_count: int = 0          # non-whitespace chars
    has_fiscal_marker: bool = False
    image_too_small: bool = False
    image_too_dark: bool = False
    image_too_bright: bool = False
    image_low_contrast: bool = False
    image_readable: bool = True  # set to False when path exists but open() fails


@dataclass
class ReceiptRiskAssessment:
    suspicious: bool
    severity: Literal["ok", "warn", "manual"]
    reasons: list[str] = field(default_factory=list)   # Polish user-facing lines
    photo_hint: str = ""                                # non-empty only when source_kind=="photo" and not suspicious
    signals: OcrQualitySignals | None = None


def assess_receipt_risk(
    draft: ReceiptDraft,
    *,
    source_kind: str = "",
    image_path: Path | None = None,
    ocr_text: str = "",
    confidence_warn: float = 0.75,
    max_auto_save_amount: float = 10_000.0,
) -> ReceiptRiskAssessment:
    """Return a risk assessment combining OCR signals, image quality, and field completeness."""
    reasons: list[str] = []

    # 1. OCR confidence — 0.0 means unknown, not bad.
    if draft.ocr_confidence and draft.ocr_confidence < confidence_warn:
        reasons.append(f"niska pewność odczytu OCR ({draft.ocr_confidence:.0%})")

    # 2. OCR text quality — only when text is non-empty (empty may mean OCR not yet run).
    text = ocr_text or draft.ocr_text or ""
    signals = _analyse_ocr_text(text)
    if text:
        if signals.line_count < _MIN_OCR_LINES or signals.char_count < _MIN_OCR_CHARS:
            reasons.append("tekst OCR jest za krótki – sprawdź czy obraz jest czytelny")
        elif not signals.has_fiscal_marker:
            reasons.append("tekst OCR nie zawiera typowych znaczników dokumentu fiskalnego")

    # 3. Image quality via Pillow (safe — never crashes on missing/bad file).
    if image_path is not None:
        _check_image(image_path, signals)
    if signals.image_too_small:
        reasons.append("obraz jest za mały – jakość OCR może być niska")
    if signals.image_too_dark:
        reasons.append("obraz jest bardzo ciemny – sprawdź oświetlenie")
    if signals.image_too_bright:
        reasons.append("obraz jest bardzo jasny – sprawdź oświetlenie")
    if signals.image_low_contrast and not signals.image_too_dark and not signals.image_too_bright:
        reasons.append("niski kontrast obrazu – tekst może być słabo widoczny")

    # 4. Field completeness.
    if draft.kwota is None:
        reasons.append("nie udało się odczytać kwoty")
    elif draft.kwota <= 0:
        reasons.append("kwota wygląda nieprawidłowo")
    elif draft.kwota > max_auto_save_amount:
        reasons.append(
            f"kwota {draft.kwota:.2f} PLN wygląda bardzo wysoko "
            f"(limit bez ostrzeżenia: {max_auto_save_amount:.2f} PLN)"
        )

    if not draft.data_dokumentu:
        reasons.append("brak daty dokumentu")

    if not draft.nip and not draft.sprzedawca:
        reasons.append("brak NIP i nazwy sprzedawcy")

    # 5. Source kind nudge — photo is mildly risky, but alone never forces suspicious.
    if source_kind == "photo" and reasons:
        reasons.append("następnym razem wyślij jako plik/dokument – zdjęcia w Telegramie są kompresowane")

    suspicious = bool(reasons)
    photo_hint = (
        "Wskazówka: najlepsza jakość OCR jest po wysłaniu jako plik/dokument."
        if source_kind == "photo" and not suspicious
        else ""
    )

    if suspicious:
        severity: Literal["ok", "warn", "manual"] = "manual"
    elif source_kind == "photo":
        severity = "warn"
    else:
        severity = "ok"

    return ReceiptRiskAssessment(
        suspicious=suspicious,
        severity=severity,
        reasons=reasons,
        photo_hint=photo_hint,
        signals=signals,
    )


def _analyse_ocr_text(text: str) -> OcrQualitySignals:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    char_count = len(text.replace(" ", "").replace("\n", "").replace("\r", ""))
    lower = text.lower()
    has_marker = any(marker in lower for marker in _FISCAL_MARKERS)
    return OcrQualitySignals(
        line_count=len(lines),
        char_count=char_count,
        has_fiscal_marker=has_marker,
    )


def _check_image(image_path: Path, signals: OcrQualitySignals) -> None:
    try:
        from PIL import Image, ImageStat  # type: ignore[import]

        with Image.open(image_path) as img:
            w, h = img.size
            if w * h < _MIN_IMAGE_PIXELS:
                signals.image_too_small = True
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            mean = stat.mean[0]
            std = stat.stddev[0]
            if mean < _DARK_THRESHOLD:
                signals.image_too_dark = True
            elif mean > _BRIGHT_THRESHOLD:
                signals.image_too_bright = True
            if std < _LOW_CONTRAST_STD:
                signals.image_low_contrast = True
    except Exception:
        logger.debug("Image quality check skipped for %s", image_path)
        signals.image_readable = False
