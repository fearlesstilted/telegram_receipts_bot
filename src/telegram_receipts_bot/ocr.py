from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .config import Settings

logger = logging.getLogger(__name__)


class OcrError(RuntimeError):
    pass


@dataclass
class OcrResult:
    """Outcome of an OCR run.

    text:       recognised text joined by newlines
    confidence: mean per-line recognition confidence in [0, 1] (0.0 if unknown,
                e.g. the Tesseract path which has no probability)
    variant:    which preprocessing variant / engine produced this result
    """

    text: str
    confidence: float
    variant: str


def extract_text(image_path: Path, settings: Settings) -> str:
    """Backward-compatible entry point: return only the recognised text."""
    return extract_ocr_result(image_path, settings).text


def extract_ocr_result(image_path: Path, settings: Settings) -> OcrResult:
    """Confidence-aware entry point: return text, confidence and chosen variant."""
    if settings.ocr_mode == "mock":
        return OcrResult("", 0.0, "mock")

    if settings.ocr_mode == "paddle":
        return _extract_paddle_ocr_result(image_path, settings)

    if settings.ocr_mode == "auto":
        try:
            return _extract_paddle_ocr_result(image_path, settings)
        except OcrError:
            text = _extract_text_with_tesseract(image_path, settings)
            return OcrResult(text, 0.0, "tesseract")

    if settings.ocr_mode == "tesseract":
        text = _extract_text_with_tesseract(image_path, settings)
        return OcrResult(text, 0.0, "tesseract")

    raise OcrError(f"Unsupported OCR mode: {settings.ocr_mode}")


def _extract_paddle_ocr_result(image_path: Path, settings: Settings) -> OcrResult:
    """Run PaddleOCR over several gentle image variants and keep the best result.

    "Best" combines recognition confidence with how many key fields the parser can
    recover from the text (see _select_best_paddle_result). No hard thresholding is
    used: Paddle does better on near-natural images than on binarised ones.
    """
    try:
        _configure_paddle_runtime()
        ocr = _get_paddle_ocr(settings)
    except ImportError as exc:
        raise OcrError(
            "PaddleOCR is not installed. Install local dependencies with "
            "`.venv/bin/python3 -m pip install -r requirements.txt`."
        ) from exc
    except Exception as exc:
        raise OcrError(_describe_paddle_failure(exc)) from exc

    candidates: list[OcrResult] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        for variant_name, variant_path in _prepare_paddle_variants(image_path, Path(temp_dir)):
            try:
                result = _run_paddle_ocr(ocr, variant_path)
            except Exception as exc:  # an inference crash on one variant aborts the run
                raise OcrError(_describe_paddle_failure(exc)) from exc
            lines, scores = _extract_paddle_text_and_scores(result)
            text = "\n".join(lines).strip()
            if not text:
                continue
            confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
            candidates.append(OcrResult(text, confidence, variant_name))

    if not candidates:
        raise OcrError("PaddleOCR returned empty text")
    return _select_best_paddle_result(candidates)


def _prepare_paddle_variants(image_path: Path, temp_dir: Path) -> list[tuple[str, Path]]:
    """Gentle preprocessing variants for the Paddle path (no binarisation).

    Always includes the raw image. Adds grayscale+autocontrast+upscale and a mild
    contrast/sharpen pass. If the image cannot be opened we fall back to raw only.
    """
    variants: list[tuple[str, Path]] = [("raw", image_path)]
    try:
        base = _prepare_base_image(image_path)
        sharp = ImageEnhance.Sharpness(ImageEnhance.Contrast(base).enhance(1.5)).enhance(1.6)
        for name, prepared in (("gray", base), ("sharp", sharp)):
            target = temp_dir / f"paddle_{name}.png"
            prepared.save(target)
            variants.append((name, target))
    except OSError as exc:
        logger.warning("Could not build Paddle preprocessing variants, using raw image: %s", exc)
    return variants


def _field_completeness(draft) -> float:
    """Fraction of the key fields the parser managed to fill (0.0 - 1.0)."""
    checks = (
        bool(draft.kwota),
        bool(draft.data_dokumentu),
        bool(draft.nip or draft.sprzedawca),
        bool(draft.nr_fv or draft.nr_paragonu),
    )
    return sum(checks) / len(checks)


def _select_best_paddle_result(candidates: list[OcrResult]) -> OcrResult:
    """Pick the variant whose text both reads confidently and parses into key fields."""
    # Deferred imports to break circular dependency: ocr → parser → models → ocr.
    from .models import ReceiptDraft
    from .parser import parse_receipt_text

    best: OcrResult | None = None
    best_key: tuple[float, int] = (float("-inf"), -1)
    for candidate in candidates:
        if not candidate.text.strip():
            continue
        draft = parse_receipt_text(candidate.text, ReceiptDraft.empty("select", 0, ""))
        completeness = _field_completeness(draft)
        # Equal weight on confidence and completeness; longer text breaks ties.
        key = (candidate.confidence + completeness, len(candidate.text))
        if key > best_key:
            best_key = key
            best = candidate
    # candidates is non-empty and all entries have text, so best is set.
    assert best is not None
    return best


_PADDLE_OCR = None


def _describe_paddle_failure(exc: Exception) -> str:
    """Turn a raw Paddle exception into an actionable message.

    The known Windows/CPU failure surfaces as oneDNN/MKLDNN or PIR-related errors. When we
    recognise that signature we point the user at DIAGNOZA.bat instead of leaking a raw
    traceback they cannot act on.
    """
    text = str(exc).lower()
    crash_markers = ("onednn", "mkldnn", "pir", "primitive", "oneapi")
    if any(marker in text for marker in crash_markers):
        return (
            "PaddleOCR crashed (known Windows/CPU oneDNN/PIR issue). "
            "Uruchom DIAGNOZA.bat, sprawdź wersje paddlepaddle/paddleocr i spróbuj ponownie. "
            f"Szczegóły: {exc}"
        )
    return f"PaddleOCR failed: {exc}"


def _configure_paddle_runtime() -> None:
    # These flags must be set before importing Paddle. They avoid a known
    # Windows/CPU oneDNN/PIR runtime crash in PaddleOCR 3.x.
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_use_onednn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")


def _get_paddle_ocr(settings: Settings):
    global _PADDLE_OCR
    if _PADDLE_OCR is not None:
        return _PADDLE_OCR

    from paddleocr import PaddleOCR

    # Prefer the Latin recognition model (covers Polish diacritics); fall back to the
    # English model if this PaddleOCR build does not ship/accept lang="latin".
    try:
        _PADDLE_OCR = _build_paddle_ocr(PaddleOCR, "latin", _paddle_model_dirs(settings, "latin"))
    except Exception as exc:  # noqa: BLE001 - any failure here means "lang unsupported"
        logger.warning('PaddleOCR lang="latin" unavailable (%s); falling back to "en".', exc)
        _PADDLE_OCR = _build_paddle_ocr(PaddleOCR, "en", _paddle_model_dirs(settings, "en"))
    return _PADDLE_OCR


def _paddle_model_dirs(settings: Settings, lang: str) -> dict[str, str]:
    model_dir = settings.data_dir / "paddleocr_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    return {
        "det_model_dir": str(model_dir / "det"),
        "rec_model_dir": str(model_dir / f"rec_{lang}"),
        "cls_model_dir": str(model_dir / "cls"),
    }


def _build_paddle_ocr(paddle_cls, lang: str, dirs: dict[str, str]):
    """Construct a PaddleOCR instance, tolerating the 2.x vs 3.x constructor differences."""
    try:
        return paddle_cls(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            **dirs,
        )
    except ValueError:
        return paddle_cls(
            lang=lang,
            use_angle_cls=True,
            show_log=False,
            **dirs,
        )


def _run_paddle_ocr(ocr, image_path: Path):
    if hasattr(ocr, "predict"):
        return ocr.predict(str(image_path))
    return ocr.ocr(str(image_path), cls=True)


def _extract_paddle_text_lines(result) -> list[str]:
    return _extract_paddle_text_and_scores(result)[0]


def _extract_paddle_text_and_scores(result) -> tuple[list[str], list[float]]:
    """Extract recognised lines and their confidence scores from a PaddleOCR result.

    Handles both the 3.x dict form ({"rec_texts": [...], "rec_scores": [...]}) and the
    legacy nested-list form ([(bbox, (text, score)), ...]). Lines without a usable score
    simply contribute no score; confidence is averaged over whatever scores are present.
    """
    lines: list[str] = []
    scores: list[float] = []

    def add_score(raw) -> None:
        try:
            scores.append(float(raw))
        except (TypeError, ValueError):
            pass

    def visit(value) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            texts = value.get("rec_texts")
            if not isinstance(texts, list):
                texts = value.get("texts")
            if isinstance(texts, list):
                raw_scores = value.get("rec_scores")
                for index, item in enumerate(texts):
                    text = str(item).strip()
                    if not text:
                        continue
                    lines.append(text)
                    if isinstance(raw_scores, list) and index < len(raw_scores):
                        add_score(raw_scores[index])
                return
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple)) and len(value) >= 2 and isinstance(value[1], tuple):
            text = str(value[1][0]).strip()
            if text:
                lines.append(text)
                if len(value[1]) >= 2:
                    add_score(value[1][1])
            return
        if isinstance(value, list):
            for item in value:
                visit(item)

    visit(result)
    return lines, scores


def _extract_text_with_tesseract(image_path: Path, settings: Settings) -> str:
    if shutil.which(settings.tesseract_cmd) is None:
        raise OcrError(
            "Tesseract is not installed or not available in PATH. "
            "Install `tesseract` and `tesseract-langpack-pol`."
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        prepared_paths = _prepare_image_variants(image_path, Path(temp_dir))
        text = _best_tesseract_text(prepared_paths, settings)

    if not text:
        raise OcrError("OCR returned empty text")
    return text


def _prepare_image_variants(image_path: Path, temp_dir: Path) -> list[Path]:
    try:
        base = _prepare_base_image(image_path)
        contrast = ImageEnhance.Contrast(base).enhance(1.5)
        variants = [
            ("gray", base),
            ("contrast", contrast),
            ("sharp", ImageEnhance.Sharpness(contrast).enhance(1.8)),
            ("threshold", _otsu_threshold(contrast)),
            ("denoise", ImageEnhance.Contrast(base).enhance(1.5).filter(ImageFilter.MedianFilter(size=3))),
        ]
        paths = []
        for name, variant in variants:
            target = temp_dir / f"receipt_{name}.png"
            variant.save(target)
            paths.append(target)
        return paths
    except OSError as exc:
        raise OcrError(f"Cannot prepare image for OCR: {exc}") from exc


def _prepare_base_image(image_path: Path) -> Image.Image:
    """Shared first step: open, grayscale, upscale, autocontrast."""
    with Image.open(image_path) as img:
        gray = ImageOps.grayscale(img)
    return ImageOps.autocontrast(_upscale_if_needed(gray))


def _otsu_threshold(image: Image.Image) -> Image.Image:
    """Adaptive binarization using Otsu's method (pure PIL, no extra deps)."""
    hist = image.histogram()
    total = sum(hist)
    sum_all = sum(i * hist[i] for i in range(256))
    best_t, best_var = 0, 0.0
    w0 = sum0 = 0
    for t in range(256):
        w0 += hist[t]
        if w0 == 0:
            continue
        w1 = total - w0
        if w1 == 0:
            break
        sum0 += t * hist[t]
        m0, m1 = sum0 / w0, (sum_all - sum0) / w1
        var = w0 * w1 * (m0 - m1) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return image.point(lambda p: 255 if p > best_t else 0)


def _upscale_if_needed(image: Image.Image) -> Image.Image:
    short = min(image.width, image.height)
    if short >= 1000:
        return image
    ratio = 1000 / short
    return image.resize(
        (int(image.width * ratio), int(image.height * ratio)),
        Image.Resampling.LANCZOS,
    )


def _best_tesseract_text(image_paths: list[Path], settings: Settings) -> str:
    best_text = ""
    best_score = -1
    errors = []
    for image_path in image_paths:
        for psm in ("6", "4", "11"):
            proc = subprocess.run(
                [
                    settings.tesseract_cmd,
                    str(image_path),
                    "stdout",
                    "-l",
                    "pol+eng",
                    "--psm",
                    psm,
                    "--oem",
                    "1",
                    "--dpi",
                    "300",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                errors.append(proc.stderr.strip())
                continue
            text = proc.stdout.strip()
            score = _score_ocr_text(text)
            if score > best_score:
                best_text = text
                best_score = score
    if not best_text and errors:
        raise OcrError(errors[-1] or "Tesseract OCR failed")
    return best_text


def _score_ocr_text(text: str) -> int:
    lower = text.lower()
    keywords = (
        "nip",
        "faktura",
        "paragon",
        "suma",
        "razem",
        "sprzedawca",
        "data",
        "paliw",
        "shell",
    )
    score = sum(15 for keyword in keywords if keyword in lower)
    score += min(text.count("\n"), 80)
    score += min(sum(char.isdigit() for char in text), 120)
    score -= text.count("|") * 2
    score -= text.count("~") * 3
    return score
