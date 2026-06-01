from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .config import load_settings
from .exporter import REGISTER_FILENAME, generate_register


def main() -> None:
    settings = load_settings()
    archive_dir = settings.data_dir / "archive" / datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived = []
    for path in _paths_to_archive(settings.data_dir):
        if not path.exists():
            continue
        target = archive_dir / path.name
        shutil.move(str(path), str(target))
        archived.append(target)

    state_file = settings.data_dir / "state.json"
    if state_file.exists():
        state_archive = archive_dir / "state.json"
        shutil.copy2(state_file, state_archive)
        archived.append(state_archive)

    _reset_state(settings.data_dir / "state.json")
    workbook_path = generate_register(settings.data_dir)

    print("Reset wykonany.")
    print(f"Nowa tabela: {workbook_path}")
    if archived:
        print(f"Archiwum starych danych: {archive_dir}")
    else:
        print("Nie było starych danych do archiwizacji.")


def _paths_to_archive(data_dir: Path) -> list[Path]:
    paths = [
        data_dir / "rows.jsonl",
        data_dir / REGISTER_FILENAME,
    ]
    paths.extend(sorted(data_dir.glob("export_*.xlsx")))
    return paths


def _reset_state(state_file: Path) -> None:
    if not state_file.exists():
        return

    archive_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    monthly_budget = archive_snapshot.get("monthly_budget", {})
    for month_state in monthly_budget.values():
        if isinstance(month_state, dict):
            month_state["spent"] = 0.0

    state_file.write_text(
        json.dumps(
            {
                "monthly_budget": monthly_budget,
                "pending_drafts": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
