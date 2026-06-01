from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import ReceiptDraft

SHEET_HEADERS = [
    "wyjazd_nazwa",
    "wyjazd_data",
    "typ_dokumentu",
    "data_dokumentu",
    "nr_fv",
    "nr_paragonu",
    "kwota",
    "sprzedawca",
    "adres",
    "nip",
    "towar",
    "uwagi",
    "budget_remaining",
    "items_json",
    "ocr_text",
    "receipt_url",
    "created_at",
]


class BaseSink:
    mode = "base"

    def save_receipt(self, draft: ReceiptDraft, budget_remaining: float) -> str:
        raise NotImplementedError

    def append_row(self, row: list[str]) -> None:
        raise NotImplementedError


class LocalJsonSink(BaseSink):
    mode = "local"

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.rows_file = data_dir / "rows.jsonl"
        self.receipts_dir = data_dir / "receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def save_receipt(self, draft: ReceiptDraft, budget_remaining: float) -> str:
        src = Path(draft.source_path)
        target = self.receipts_dir / src.name
        if src.resolve() != target.resolve():
            shutil.copy2(src, target)
        url = str(target)
        draft.receipt_url = url
        self.append_row(draft.to_sheet_row(budget_remaining))
        return url

    def append_row(self, row: list[str]) -> None:
        payload = dict(zip(SHEET_HEADERS, row, strict=False))
        with self.rows_file.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload, ensure_ascii=False) + "\n")


def build_sink(settings) -> BaseSink:
    return LocalJsonSink(settings.data_dir)
