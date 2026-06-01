from telegram_receipts_bot.ocr import (
    OcrResult,
    _extract_paddle_text_and_scores,
    _extract_paddle_text_lines,
    _field_completeness,
    _paddle_model_dirs,
    _select_best_paddle_result,
)
from telegram_receipts_bot.config import Settings
from telegram_receipts_bot.models import ReceiptDraft
from telegram_receipts_bot.parser import parse_receipt_text


def test_extract_paddle_text_lines_from_v3_dict_result() -> None:
    result = [{"rec_texts": ["FAKTURA", "Suma: PLN 212,51", "NIP: 5261009190"]}]

    assert _extract_paddle_text_lines(result) == [
        "FAKTURA",
        "Suma: PLN 212,51",
        "NIP: 5261009190",
    ]


def test_extract_paddle_text_lines_from_legacy_result() -> None:
    result = [[[[0, 0], [1, 0], [1, 1], [0, 1]], ("Shell FuelSave Diesel", 0.96)]]

    assert _extract_paddle_text_lines(result) == ["Shell FuelSave Diesel"]


def test_extract_scores_from_v3_dict_result() -> None:
    result = [
        {
            "rec_texts": ["FAKTURA", "Suma 212,51", "NIP 5261009190"],
            "rec_scores": [0.99, 0.80, 0.91],
        }
    ]

    lines, scores = _extract_paddle_text_and_scores(result)

    assert lines == ["FAKTURA", "Suma 212,51", "NIP 5261009190"]
    assert scores == [0.99, 0.80, 0.91]


def test_extract_scores_from_legacy_result() -> None:
    result = [
        [[[0, 0], [1, 0], [1, 1], [0, 1]], ("Shell FuelSave Diesel", 0.96)],
        [[[0, 2], [1, 2], [1, 3], [0, 3]], ("SUMA PLN 50,00", 0.88)],
    ]

    lines, scores = _extract_paddle_text_and_scores(result)

    assert lines == ["Shell FuelSave Diesel", "SUMA PLN 50,00"]
    assert scores == [0.96, 0.88]


def test_extract_scores_missing_scores_are_skipped() -> None:
    # Dict form without rec_scores: lines still parsed, no scores produced.
    result = [{"rec_texts": ["A", "B"]}]

    lines, scores = _extract_paddle_text_and_scores(result)

    assert lines == ["A", "B"]
    assert scores == []


def test_field_completeness_counts_key_fields() -> None:
    draft = ReceiptDraft.empty("x", 0, "")
    assert _field_completeness(draft) == 0.0

    draft.kwota = 12.0
    draft.data_dokumentu = "2026-04-09"
    # kwota + date present, no nip/seller, no document number -> 2 of 4
    assert _field_completeness(draft) == 0.5


# A text that parses into many key fields (date, nip, kwota, seller).
_RICH_TEXT = "\n".join(
    [
        "CENTRUM USŁUG GASTRONOMICZNYCH MARIO",
        "NIP: 7471727805",
        "Data sprzedaży: 2026-04-09",
        "SUMA PLN 127,00",
    ]
)
# A text that parses into nothing useful.
_POOR_TEXT = "MULRR\nxxxx"


def test_select_best_prefers_completeness_over_raw_confidence() -> None:
    # The "raw" variant reads more confidently but yields no fields; the "gray" variant
    # reads slightly less confidently but parses into several key fields and should win.
    poor = OcrResult(_POOR_TEXT, confidence=0.95, variant="raw")
    rich = OcrResult(_RICH_TEXT, confidence=0.80, variant="gray")

    best = _select_best_paddle_result([poor, rich])

    assert best.variant == "gray"
    # Sanity: the winning text really does parse into the key fields.
    draft = parse_receipt_text(best.text, ReceiptDraft.empty("x", 0, ""))
    assert _field_completeness(draft) >= 0.75


def test_select_best_uses_confidence_as_tiebreaker_when_completeness_equal() -> None:
    high = OcrResult(_RICH_TEXT, confidence=0.90, variant="sharp")
    low = OcrResult(_RICH_TEXT, confidence=0.50, variant="gray")

    best = _select_best_paddle_result([low, high])

    assert best.variant == "sharp"


def test_paddle_model_dirs_keep_language_recognition_models_separate(tmp_path) -> None:
    settings = Settings(
        telegram_bot_token="",
        telegram_allowed_chat_id=None,
        monthly_budget=1000,
        data_dir=tmp_path,
        ocr_mode="paddle",
        telegram_photo_max_pixels=1400000,
        max_auto_save_amount=10000,
        tesseract_cmd="tesseract",
        timezone_name="Europe/Warsaw",
    )

    latin = _paddle_model_dirs(settings, "latin")
    english = _paddle_model_dirs(settings, "en")

    assert latin["det_model_dir"] == english["det_model_dir"]
    assert latin["cls_model_dir"] == english["cls_model_dir"]
    assert latin["rec_model_dir"].endswith("rec_latin")
    assert english["rec_model_dir"].endswith("rec_en")
