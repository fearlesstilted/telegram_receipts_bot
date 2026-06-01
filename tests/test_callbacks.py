"""Tests for bot callback parsing and exporter backward compatibility — no Telegram needed."""
import json
from pathlib import Path

from telegram_receipts_bot.bot import _needs_manual_check, _parse_callback_data, _select_photo
from telegram_receipts_bot.exporter import generate_export
from telegram_receipts_bot.models import ReceiptDraft


class TestCallbackParsing:
    def test_save(self) -> None:
        action, draft_id, payload = _parse_callback_data("save:abc1234567")
        assert action == "save"
        assert draft_id == "abc1234567"
        assert payload is None

    def test_edit(self) -> None:
        action, draft_id, payload = _parse_callback_data("edit:abc1234567")
        assert action == "edit"
        assert draft_id == "abc1234567"
        assert payload is None

    def test_cancel(self) -> None:
        action, draft_id, payload = _parse_callback_data("cancel:abc1234567")
        assert action == "cancel"

    def test_cat_with_index(self) -> None:
        action, draft_id, payload = _parse_callback_data("cat:abc1234567:3")
        assert action == "cat"
        assert draft_id == "abc1234567"
        assert payload == "3"

    def test_cat_index_zero(self) -> None:
        action, draft_id, payload = _parse_callback_data("cat:abc1234567:0")
        assert payload == "0"

    def test_malformed_no_draft_id(self) -> None:
        action, draft_id, payload = _parse_callback_data("save")
        assert action == "save"
        assert draft_id == ""
        assert payload is None

    def test_cat_index_is_string_not_crash(self) -> None:
        """int() on non-numeric payload raises ValueError — bot should handle it."""
        _, _, payload = _parse_callback_data("cat:abc:notanumber")
        assert payload == "notanumber"
        try:
            idx = int(payload)
        except ValueError:
            idx = -1
        assert idx == -1


class TestPhotoSelection:
    def test_selects_largest_photo_under_limit(self) -> None:
        class Photo:
            def __init__(self, width: int, height: int) -> None:
                self.width = width
                self.height = height

        small = Photo(320, 240)
        medium = Photo(1280, 960)
        huge = Photo(2560, 1920)

        assert _select_photo([small, medium, huge], max_pixels=1_400_000) is medium

    def test_selects_largest_when_all_photos_are_above_limit(self) -> None:
        class Photo:
            def __init__(self, width: int, height: int) -> None:
                self.width = width
                self.height = height

        first = Photo(2000, 1500)
        second = Photo(2500, 2000)

        assert _select_photo([first, second], max_pixels=1_000_000) is second


class TestManualCheck:
    def test_normal_amount_does_not_need_manual_check(self) -> None:
        draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
        draft.kwota = 127.00

        assert not _needs_manual_check(draft, max_auto_save_amount=10_000)

    def test_missing_amount_needs_manual_check(self) -> None:
        draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")

        assert _needs_manual_check(draft, max_auto_save_amount=10_000)

    def test_huge_amount_needs_manual_check(self) -> None:
        draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
        draft.kwota = 2_000_000

        assert _needs_manual_check(draft, max_auto_save_amount=10_000)


class TestExporterBackwardCompat:
    def test_old_rows_without_kategoria(self, tmp_path: Path) -> None:
        """Rows saved before kategoria field was added must export without error."""
        rows_file = tmp_path / "rows.jsonl"
        old_row = {
            "wyjazd_nazwa": "Targi",
            "wyjazd_data": "2026-04-01",
            "data_dokumentu": "2026-04-01",
            "nr_fv": "FV001",
            "kwota": "127.00",
            "sprzedawca": "Sklep ABC",
            "nip": "1234567890",
            "towar": "chleb, mleko",
            "uwagi": "",
            "budget_remaining": "873.00",
            "items_json": "[]",
            "ocr_text": "raw text",
            "receipt_url": "/tmp/r.jpg",
            "created_at": "2026-04-01T12:00:00+00:00",
        }
        rows_file.write_text(json.dumps(old_row) + "\n", encoding="utf-8")
        (tmp_path / "receipts").mkdir()

        xlsx = generate_export(tmp_path, month_key="2026-04")
        assert xlsx.exists()
        assert xlsx.suffix == ".xlsx"

    def test_empty_month_no_crash(self, tmp_path: Path) -> None:
        """Export for month with zero receipts must produce valid xlsx."""
        rows_file = tmp_path / "rows.jsonl"
        rows_file.write_text("", encoding="utf-8")
        (tmp_path / "receipts").mkdir()

        xlsx = generate_export(tmp_path, month_key="2026-04")
        assert xlsx.exists()

    def test_missing_rows_file(self, tmp_path: Path) -> None:
        """No rows.jsonl at all — must not crash."""
        (tmp_path / "receipts").mkdir()
        xlsx = generate_export(tmp_path, month_key="2026-04")
        assert xlsx.exists()
