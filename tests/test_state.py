from pathlib import Path

from telegram_receipts_bot.models import ReceiptDraft
from telegram_receipts_bot.state import StateStore


def test_budget_commit_and_preview(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json", 1000)
    store.set_budget("2026-04", 1000)

    assert store.preview_remaining("2026-04", 120.50) == 879.50
    assert store.commit_spend("2026-04", 120.50) == 879.50
    assert store.commit_spend("2026-04", 79.50) == 800.00


def test_get_draft_ignores_unknown_fields(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json", 1000)
    draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
    draft.adres = "Elektryczna 8A"
    store.save_draft(draft)

    raw_state = (tmp_path / "state.json").read_text(encoding="utf-8")
    (tmp_path / "state.json").write_text(
        raw_state.replace('"adres": "Elektryczna 8A"', '"adres": "Elektryczna 8A", "extra": "x"'),
        encoding="utf-8",
    )

    restored = store.get_draft("abc")
    assert restored is not None
    assert restored.adres == "Elektryczna 8A"
