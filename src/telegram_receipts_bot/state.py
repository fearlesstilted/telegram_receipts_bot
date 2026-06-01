from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from .models import ReceiptDraft, ReceiptItem


class StateStore:
    def __init__(self, state_file: Path, default_budget: float):
        self.state_file = state_file
        self.default_budget = default_budget
        if not self.state_file.exists():
            self._write(
                {
                    "monthly_budget": {},
                    "pending_drafts": {},
                }
            )

    def save_draft(self, draft: ReceiptDraft) -> None:
        state = self._read()
        draft_dict = asdict(draft)
        state["pending_drafts"][draft.draft_id] = draft_dict
        self._write(state)

    def get_draft(self, draft_id: str) -> ReceiptDraft | None:
        state = self._read()
        data = state["pending_drafts"].get(draft_id)
        if not data:
            return None
        draft_fields = {field.name for field in fields(ReceiptDraft)}
        data = {key: value for key, value in data.items() if key in draft_fields}
        data["items"] = [ReceiptItem(**item) for item in data.get("items", [])]
        return ReceiptDraft(**data)

    def delete_draft(self, draft_id: str) -> None:
        state = self._read()
        state["pending_drafts"].pop(draft_id, None)
        self._write(state)

    def set_budget(self, month_key: str, total: float) -> None:
        state = self._read()
        month_state = state["monthly_budget"].setdefault(month_key, {})
        month_state["total"] = round(total, 2)
        month_state.setdefault("spent", 0.0)
        self._write(state)

    def get_budget(self, month_key: str) -> tuple[float, float]:
        state = self._read()
        month_state = state["monthly_budget"].setdefault(
            month_key,
            {"total": self.default_budget, "spent": 0.0},
        )
        self._write(state)
        return float(month_state["total"]), float(month_state["spent"])

    def preview_remaining(self, month_key: str, amount: float | None) -> float:
        total, spent = self.get_budget(month_key)
        if amount is None:
            return round(total - spent, 2)
        return round(total - spent - amount, 2)

    def commit_spend(self, month_key: str, amount: float | None) -> float:
        state = self._read()
        month_state = state["monthly_budget"].setdefault(
            month_key,
            {"total": self.default_budget, "spent": 0.0},
        )
        if amount is not None:
            month_state["spent"] = round(float(month_state.get("spent", 0.0)) + amount, 2)
        self._write(state)
        return round(float(month_state["total"]) - float(month_state["spent"]), 2)

    def _read(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def current_month_key(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%Y-%m")
