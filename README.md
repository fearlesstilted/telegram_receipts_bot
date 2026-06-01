# Telegram Receipts Bot

Локальный Telegram-бот для разбора польских paragon/faktura и ведения одного
общего Excel-файла.

## Как работает

- пользователь запускает бота на своем компьютере;
- отправляет фото чеков в Telegram;
- бот читает фото через PaddleOCR;
- показывает preview полей;
- пользователь жмет `Zapisz` или правит через `Edytuj`;
- подозрительно большие/пустые суммы требуют ручной проверки;
- каждая сохраненная запись добавляется в `data/rows.jsonl`;
- общий Excel пересобирается в `data/rozliczenie_paragonow.xlsx`;
- `/table` или кнопка `Tabela Excel` отправляет текущий Excel в Telegram.

Компьютер должен быть включен, пока бот нужен. Облака, Google billing и Cloud
Run в текущем MVP не используются.

## Быстрый запуск

Linux:

```bash
cd /home/fidaczjo/Загрузки/f/telegram_receipts_bot
./start_bot.sh
```

Windows:

```bat
RUN_WINDOWS.bat
```

Остановить: `Ctrl+C`.

## Установка на новом компьютере

Нужен Python 3.11. Не использовать Python 3.13 для PaddleOCR: связка
`paddlepaddle 3.x + paddleocr 3.x` падает на CPU runtime.

Linux:

```bash
cd telegram_receipts_bot
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Windows:

```bat
RUN_WINDOWS.bat
```

В `.env` заполнить:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=...
OCR_MODE=paddle
```

`TELEGRAM_ALLOWED_CHAT_ID` ограничивает доступ к боту одним Telegram chat id.

## Команды в Telegram

- `/start` - запуск и основное меню
- `/help` - инструкция
- `/status` - бюджет за текущий месяц
- `/table` - отправить общий Excel
- `/export` - то же самое
- `/recent` - последние сохраненные чеки
- `/setbudget 1000` - установить локальный счетчик бюджета

В меню также есть кнопки:

- `Dodaj paragon/fakturę`
- `Tabela Excel`
- `Ostatnie zapisy`
- `Status`
- `Instrukcja`

## Excel

Основной файл:

```text
data/rozliczenie_paragonow.xlsx
```

Листы:

- `Miesiące` - zaliczka, сумма чеков, остаток;
- `Paragony` - все сохраненные чеки по строкам;
- `OCR raw` - сырой OCR для проверки ошибок;
- `Kategorie` - скрытый лист с категориями.

В `Miesiące` пользователь вручную вписывает `Zaliczka`. Остальные суммы считаются
формулами.

## Скорость OCR

Основной режим:

```text
OCR_MODE=paddle
```

PaddleOCR тяжелый, но читает лучше Tesseract. Используется стабильная локальная
связка `Python 3.11 + paddlepaddle 2.6.2 + paddleocr 2.7.3`.
Первый чек после запуска может обрабатываться дольше из-за загрузки моделей.
Следующие обычно быстрее.

Для ускорения бот не берет самый огромный Telegram-размер фото, а выбирает
вариант до лимита:

```text
TELEGRAM_PHOTO_MAX_PIXELS=1400000
```

Если качество падает, можно поднять до `2200000`. Если слишком медленно, можно
снизить до `900000`.

Защита от битого OCR суммы:

```text
MAX_AUTO_SAVE_AMOUNT=10000
```

Если OCR нашел сумму выше этого лимита или не нашел сумму вообще, бот покажет
предупреждение и предложит поправить данные перед записью.

RTX на ноутбуке поможет только если отдельно поставить GPU-версию PaddlePaddle
под ее CUDA. Обычная установка из `requirements.txt` обычно работает на CPU.

Для Paddle выставляются compatibility flags:

```text
FLAGS_use_mkldnn=0
FLAGS_use_onednn=0
FLAGS_enable_pir_api=0
```

Они уже прописаны в `start_bot.sh`, `start_bot.bat` и дополнительно выставляются
в коде перед импортом PaddleOCR.

## Проверка

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
PYTHONPATH=src .venv/bin/python -m compileall -q src
```

## Windows-сервисные файлы

- `RUN_WINDOWS.bat` - установка зависимостей и запуск.
- `RESET_EXCEL_WINDOWS.bat` - архивирует старый Excel/rows/state и создает чистый Excel.
- `UPDATE_WINDOWS.bat` - делает `git pull`, если папка является git-клоном; иначе показывает ручной порядок обновления.
