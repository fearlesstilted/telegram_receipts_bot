from telegram_receipts_bot.ocr import _extract_paddle_text_lines


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
