from __future__ import annotations

import logging
import sys

from .bot import ReceiptBot
from .config import load_settings
from .sinks import build_sink
from .state import StateStore


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    settings = load_settings()
    if not settings.telegram_bot_token:
        sys.exit("Set TELEGRAM_BOT_TOKEN in .env")

    sink = build_sink(settings)
    state = StateStore(settings.data_dir / "state.json", settings.monthly_budget)
    bot = ReceiptBot(settings=settings, sink=sink, state=state).build()
    bot.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
