from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .config import Settings


class OcrError(RuntimeError):
    pass


def extract_text(image_path: Path, settings: Settings) -> str:
    if settings.ocr_mode == "mock":
        return ""

    if settings.ocr_mode == "paddle":
        return _extract_text_with_paddle(image_path, settings)

    if settings.ocr_mode == "auto":
        try:
            return _extract_text_with_paddle(image_path, settings)
        except OcrError:
            return _extract_text_with_tesseract(image_path, settings)

    if settings.ocr_mode == "tesseract":
        return _extract_text_with_tesseract(image_path, settings)

    raise OcrError(f"Unsupported OCR mode: {settings.ocr_mode}")


def _extract_text_with_paddle(image_path: Path, settings: Settings) -> str:
    try:
        _configure_paddle_runtime()
        ocr = _get_paddle_ocr(settings)
        result = _run_paddle_ocr(ocr, image_path)
    except ImportError as exc:
        raise OcrError(
            "PaddleOCR is not installed. Install local dependencies with "
            "`.venv/bin/python3 -m pip install -r requirements.txt`."
        ) from exc
    except Exception as exc:
        raise OcrError(_describe_paddle_failure(exc)) from exc

    lines = _extract_paddle_text_lines(result)
    text = "\n".join(lines).strip()
    if not text:
        raise OcrError("PaddleOCR returned empty text")
    return text


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

    model_dir = settings.data_dir / "paddleocr_models"
    det_model_dir = model_dir / "det"
    rec_model_dir = model_dir / "rec"
    cls_model_dir = model_dir / "cls"
    model_dir.mkdir(parents=True, exist_ok=True)

    try:
        _PADDLE_OCR = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            det_model_dir=str(det_model_dir),
            rec_model_dir=str(rec_model_dir),
            cls_model_dir=str(cls_model_dir),
        )
    except ValueError:
        _PADDLE_OCR = PaddleOCR(
            lang="en",
            use_angle_cls=True,
            show_log=False,
            det_model_dir=str(det_model_dir),
            rec_model_dir=str(rec_model_dir),
            cls_model_dir=str(cls_model_dir),
        )
    return _PADDLE_OCR


def _run_paddle_ocr(ocr, image_path: Path):
    if hasattr(ocr, "predict"):
        return ocr.predict(str(image_path))
    return ocr.ocr(str(image_path), cls=True)


def _extract_paddle_text_lines(result) -> list[str]:
    lines: list[str] = []

    def visit(value) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("rec_texts", "texts"):
                text_values = value.get(key)
                if isinstance(text_values, list):
                    lines.extend(str(item).strip() for item in text_values if str(item).strip())
                    return
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple)) and len(value) >= 2 and isinstance(value[1], tuple):
            text = str(value[1][0]).strip()
            if text:
                lines.append(text)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)

    visit(result)
    return lines


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
        with Image.open(image_path) as image:
            base = _upscale_if_needed(ImageOps.grayscale(image))
            base = ImageOps.autocontrast(base)

            variants = [
                ("gray", base),
                ("contrast", ImageEnhance.Contrast(base).enhance(1.9)),
                (
                    "sharp",
                    ImageEnhance.Sharpness(ImageEnhance.Contrast(base).enhance(1.7)).enhance(1.8),
                ),
                (
                    "threshold",
                    ImageEnhance.Contrast(base).enhance(1.6).point(lambda pixel: 255 if pixel > 165 else 0),
                ),
                (
                    "denoise",
                    ImageEnhance.Contrast(base.filter(ImageFilter.MedianFilter(size=3))).enhance(1.8),
                ),
            ]

            paths = []
            for name, variant in variants:
                target = temp_dir / f"receipt_{name}.png"
                variant.save(target)
                paths.append(target)
            return paths
    except OSError as exc:
        raise OcrError(f"Cannot prepare image for OCR: {exc}") from exc


def _upscale_if_needed(image: Image.Image) -> Image.Image:
    if image.width >= 1600:
        return image
    ratio = 1600 / image.width
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
