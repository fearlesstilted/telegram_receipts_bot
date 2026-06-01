from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC


@dataclass
class ReceiptItem:
    name: str
    price: float | None = None


@dataclass
class ReceiptDraft:
    draft_id: str
    created_at: str
    chat_id: int
    source_path: str
    wyjazd_nazwa: str = ""
    wyjazd_data: str = ""
    typ_dokumentu: str = ""
    data_dokumentu: str = ""
    nr_fv: str = ""
    nr_paragonu: str = ""
    kwota: float | None = None
    sprzedawca: str = ""
    adres: str = ""
    nip: str = ""
    towar: str = ""
    uwagi: str = ""
    items: list[ReceiptItem] = field(default_factory=list)
    ocr_text: str = ""
    receipt_url: str = ""

    def to_preview_text(self, budget_remaining: float | None = None) -> str:
        budget_line = (
            f"\nPo zapisie zostanie: {budget_remaining:.2f} PLN"
            if budget_remaining is not None
            else ""
        )
        amount = f"{self.kwota:.2f} PLN" if self.kwota is not None else "-"
        seller = self.sprzedawca or self.towar or "-"
        document_no = self.nr_fv or self.nr_paragonu or "-"
        return (
            "Sprawdź i zapisz:\n\n"
            f"Data: {self.data_dokumentu or '-'}\n"
            f"Typ: {self.typ_dokumentu or '-'}\n"
            f"Kwota: {amount}\n"
            f"Sprzedawca: {seller}\n"
            f"NIP: {self.nip or '-'}\n"
            f"Nr dokumentu: {document_no}\n"
            f"Wyjazd: {self.wyjazd_nazwa or '-'}\n"
            f"Towar: {self.towar or '-'}"
            f"{budget_line}\n\n"
            "Jeżeli coś jest źle, kliknij Edytuj."
        )

    def to_details_text(self, budget_remaining: float | None = None) -> str:
        item_lines = []
        for item in self.items[:8]:
            if item.price is None:
                item_lines.append(f"- {item.name}")
            else:
                item_lines.append(f"- {item.name}: {item.price:.2f} PLN")
        items_block = "\n".join(item_lines) if item_lines else "- brak"
        budget_line = (
            f"\nPozostały budżet po zapisie: {budget_remaining:.2f} PLN"
            if budget_remaining is not None
            else ""
        )
        amount = f"{self.kwota:.2f} PLN" if self.kwota is not None else ""
        return (
            "Szczegóły OCR:\n\n"
            f"Wyjazd: {self.wyjazd_nazwa or '-'}\n"
            f"Data wyjazdu: {self.wyjazd_data or '-'}\n"
            f"Typ dokumentu: {self.typ_dokumentu or '-'}\n"
            f"Data dokumentu: {self.data_dokumentu or '-'}\n"
            f"Nr FV: {self.nr_fv or '-'}\n"
            f"Nr paragonu: {self.nr_paragonu or '-'}\n"
            f"Kwota: {amount or '-'}\n"
            f"Sprzedawca: {self.sprzedawca or '-'}\n"
            f"Adres: {self.adres or '-'}\n"
            f"NIP: {self.nip or '-'}\n"
            f"Towar: {self.towar or '-'}\n"
            f"Uwagi: {self.uwagi or '-'}\n"
            f"Pozycje:\n{items_block}"
            f"{budget_line}\n\n"
            "Po kliknięciu Edytuj wyślij linie `pole: wartość`."
        )

    def to_sheet_row(self, budget_remaining: float) -> list[str]:
        items_json = json.dumps([asdict(item) for item in self.items], ensure_ascii=False)
        return [
            self.wyjazd_nazwa,
            self.wyjazd_data,
            self.typ_dokumentu,
            self.data_dokumentu,
            self.nr_fv,
            self.nr_paragonu,
            "" if self.kwota is None else f"{self.kwota:.2f}",
            self.sprzedawca,
            self.adres,
            self.nip,
            self.towar,
            self.uwagi,
            f"{budget_remaining:.2f}",
            items_json,
            self.ocr_text,
            self.receipt_url,
            self.created_at,
        ]

    @classmethod
    def empty(cls, draft_id: str, chat_id: int, source_path: str) -> "ReceiptDraft":
        return cls(
            draft_id=draft_id,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            chat_id=chat_id,
            source_path=source_path,
        )
