# Telegram Receipts Bot

A local Telegram bot for reading Polish receipts/invoices and appending confirmed
records to an Excel file.

The bot is designed for a simple monthly workflow:

1. Run the bot on a Windows laptop.
2. Send receipt/invoice images to the bot in Telegram.
3. Review the extracted fields.
4. Click `Zapisz` to save, or `Edytuj` to correct the data first.
5. Download the updated Excel file from Telegram.

Nothing is saved automatically. Every receipt requires explicit confirmation.

For best OCR quality, send receipts as a Telegram file/document when possible.
Regular Telegram photos are compressed and can lose small receipt text.

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

`RUN_WINDOWS.bat` creates a local `.venv` with Python 3.11 and installs the pinned
PaddleOCR 2.7.x dependencies from `requirements.txt`.

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
- `.venv311/`

## Telegram Commands

- `/start` - open the main menu.
- `/help` - show help.
- `/status` - show monthly budget status.
- `/table` or `/export` - send the Excel file.
- `/recent` - show recent saved receipts.
- `/setbudget 1000` - set the monthly budget.

## Development

```bash
python3.11 -m venv .venv311
.venv311/bin/python -m pip install --upgrade pip
.venv311/bin/python -m pip install -r requirements.txt
PYTHONPATH=src .venv311/bin/python -m pytest
```

Use Python 3.11 for development. Do not reuse an existing Python 3.13 `.venv`
for OCR work: the pinned PaddleOCR/Paddle stack is tested against Python 3.11.

Optional local OCR/parser evaluation:

```bash
PYTHONPATH=src .venv311/bin/python tools/eval_ocr.py --init
PYTHONPATH=src .venv311/bin/python tools/eval_ocr.py
PYTHONPATH=src .venv311/bin/python tools/inspect_receipts.py data/receipts/*.jpg --no-raw
```
