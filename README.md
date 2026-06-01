# Telegram Receipts Bot

A local Telegram bot for reading Polish receipts/invoices and appending confirmed
records to an Excel file.

The bot is designed for a simple monthly workflow:

1. Run the bot on a Windows laptop.
2. Send receipt photos to the bot in Telegram.
3. Review the extracted fields.
4. Click `Zapisz` to save, or `Edytuj` to correct the data first.
5. Download the updated Excel file from Telegram.

Nothing is saved automatically. Every receipt requires explicit confirmation.

## Windows Setup

Install Python 3.11 from python.org, then clone the repository:

```bat
git clone https://github.com/fearlesstilted/telegram_receipts_bot.git
cd telegram_receipts_bot
```

Start the bot:

```bat
RUN_WINDOWS.bat
```

On first run, fill `.env`:

```env
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here
TELEGRAM_ALLOWED_CHAT_ID=your-numeric-chat-id-here
OCR_MODE=paddle
```

If startup fails, run:

```bat
DIAGNOZA.bat
```

It writes a readable report to `logs\diagnoza.txt`.

## Useful Files

- `RUN_WINDOWS.bat` - install dependencies if needed and start the bot.
- `DIAGNOZA.bat` - one-click Windows diagnostics.
- `UPDATE_WINDOWS.bat` - pull the latest version and refresh dependencies.
- `RESET_EXCEL_WINDOWS.bat` - archive current local Excel/state and start clean.

Runtime data is local and ignored by git:

- `.env`
- `data/`
- `logs/`
- `.venv/`

## Telegram Commands

- `/start` - open the main menu.
- `/help` - show help.
- `/status` - show monthly budget status.
- `/table` or `/export` - send the Excel file.
- `/recent` - show recent saved receipts.
- `/setbudget 1000` - set the monthly budget.

## Development

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m pytest
```

Optional local OCR/parser evaluation:

```bash
PYTHONPATH=src .venv/bin/python tools/eval_ocr.py --init
PYTHONPATH=src .venv/bin/python tools/eval_ocr.py
```
