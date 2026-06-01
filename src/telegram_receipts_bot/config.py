from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_chat_id: int | None
    monthly_budget: float
    data_dir: Path
    ocr_mode: str
    telegram_photo_max_pixels: int
    max_auto_save_amount: float
    tesseract_cmd: str
    timezone_name: str
    ocr_confidence_warn: float = 0.75


def load_settings() -> Settings:
    load_dotenv()

    chat_id_raw = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "receipts").mkdir(parents=True, exist_ok=True)

    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_allowed_chat_id=int(chat_id_raw) if chat_id_raw else None,
        monthly_budget=float(os.getenv("MONTHLY_BUDGET", "1000")),
        data_dir=data_dir,
        ocr_mode=os.getenv("OCR_MODE", "paddle").strip().lower(),
        telegram_photo_max_pixels=int(os.getenv("TELEGRAM_PHOTO_MAX_PIXELS", "1400000")),
        max_auto_save_amount=float(os.getenv("MAX_AUTO_SAVE_AMOUNT", "10000")),
        tesseract_cmd=os.getenv("TESSERACT_CMD", "tesseract").strip(),
        timezone_name=os.getenv("TZ", "Europe/Warsaw").strip(),
        ocr_confidence_warn=float(os.getenv("OCR_CONFIDENCE_WARN", "0.75")),
    )
