from __future__ import annotations

import logging
import uuid
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .exporter import generate_register
from .models import ReceiptDraft
from .ocr import OcrError, extract_ocr_result
from .parser import apply_manual_edits, parse_receipt_text
from .sinks import BaseSink
from .state import StateStore, current_month_key

logger = logging.getLogger(__name__)

BTN_TABLE = "Tabela Excel"
BTN_ADD = "Dodaj paragon/fakturę"
BTN_STATUS = "Status"
BTN_RECENT = "Ostatnie zapisy"
BTN_HELP = "Instrukcja"


class ReceiptBot:
    def __init__(self, settings: Settings, sink: BaseSink, state: StateStore):
        self.settings = settings
        self.sink = sink
        self.state = state
        self.edit_sessions: dict[int, str] = {}

    def build(self) -> Application:
        application = (
            Application.builder()
            .token(self.settings.telegram_bot_token)
            .connect_timeout(20)
            .read_timeout(90)
            .write_timeout(90)
            .media_write_timeout(90)
            .pool_timeout(20)
            .get_updates_connect_timeout(20)
            .get_updates_read_timeout(60)
            .build()
        )
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("status", self.status))
        application.add_handler(CommandHandler("setbudget", self.setbudget))
        application.add_handler(CommandHandler("recent", self.recent))
        application.add_handler(CommandHandler("table", self.export))
        application.add_handler(CommandHandler("export", self.export))
        application.add_handler(CallbackQueryHandler(self.on_callback))
        application.add_handler(MessageHandler(filters.PHOTO, self.on_photo))
        application.add_handler(
            MessageHandler(filters.Document.IMAGE, self.on_document_image)
        )
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text_message)
        )
        application.add_error_handler(self.on_error)
        return application

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.message.reply_text(
            "Wyślij paragon albo fakturę. Najlepiej jako plik/dokument, bo zwykłe zdjęcie w Telegramie traci jakość.\n"
            "Bot odczyta dane, pokaże krótki podgląd i dopisze dokument do jednej tabeli Excel dopiero po kliknięciu Zapisz.",
            reply_markup=_main_keyboard(),
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.message.reply_text(
            "1. Wyślij paragon albo fakturę, najlepiej jako plik/dokument.\n"
            "2. Sprawdź: data, kwota, sprzedawca, NIP.\n"
            "3. Kliknij Zapisz albo Edytuj.\n\n"
            "Przyciski:\n"
            "Tabela Excel - pobiera aktualny plik.\n"
            "Ostatnie zapisy - pokazuje ostatnie dokumenty.\n"
            "Status - pokazuje budżet.\n\n"
            "Edycja: po kliknięciu Edytuj wyślij np. `kwota: 127.00` albo `sprzedawca: Nazwa firmy`.",
            reply_markup=_main_keyboard(),
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        month_key = current_month_key()
        total, spent = self.state.get_budget(month_key)
        remaining = round(total - spent, 2)
        await update.message.reply_text(
            f"Miesiąc: {month_key}\n"
            f"Budżet: {total:.2f} PLN\n"
            f"Wydane: {spent:.2f} PLN\n"
            f"Pozostało: {remaining:.2f} PLN\n"
            f"Tryb zapisu: lokalny Excel"
        )

    async def setbudget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        if not context.args:
            await update.message.reply_text("Podaj kwotę, np. /setbudget 1000")
            return
        try:
            amount = float(context.args[0].replace(",", "."))
        except ValueError:
            await update.message.reply_text("Nieprawidłowa kwota.")
            return
        month_key = current_month_key()
        self.state.set_budget(month_key, amount)
        await update.message.reply_text(f"Budżet na {month_key} ustawiony na {amount:.2f} PLN")

    async def export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        xlsx_path = generate_register(self.settings.data_dir)
        await update.message.reply_document(
            document=xlsx_path,
            filename=xlsx_path.name,
            caption="Aktualna tabela rozliczenia paragonów",
        )

    async def recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        rows = _read_recent_rows(self.settings.data_dir / "rows.jsonl", limit=5)
        if not rows:
            await update.message.reply_text("Brak zapisanych paragonów.")
            return
        lines = ["Ostatnie zapisy:"]
        for row in rows:
            date = row.get("data_dokumentu") or row.get("created_at", "")[:10] or "-"
            amount = row.get("kwota") or "-"
            seller = row.get("sprzedawca") or row.get("towar") or "-"
            category = row.get("kategoria") or "-"
            lines.append(f"{date} | {amount} PLN | {category} | {seller}")
        await update.message.reply_text("\n".join(lines), reply_markup=_main_keyboard())

    async def on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        photo = _select_photo(update.message.photo, self.settings.telegram_photo_max_pixels)
        file_obj = await self._get_file_or_notify(update, photo)
        if file_obj is None:
            return
        await self._process_file(update, file_obj.file_path, file_obj)

    async def on_document_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        file_obj = await self._get_file_or_notify(update, update.message.document)
        if file_obj is None:
            return
        await self._process_file(update, file_obj.file_path, file_obj)

    async def on_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        if text == BTN_TABLE:
            await self.export(update, context)
            return
        if text == BTN_ADD:
            await update.message.reply_text(
                "Wyślij tutaj paragon albo fakturę. Najlepiej jako plik/dokument; możesz wysłać kilka po kolei.",
                reply_markup=_main_keyboard(),
            )
            return
        if text == BTN_STATUS:
            await self.status(update, context)
            return
        if text == BTN_RECENT:
            await self.recent(update, context)
            return
        if text == BTN_HELP:
            await self.help(update, context)
            return
        if text.lower() in {"/menu", "menu"}:
            await update.message.reply_text("Menu", reply_markup=_main_keyboard())
            return

        draft_id = self.edit_sessions.get(chat_id)
        if not draft_id:
            await update.message.reply_text("Wyślij paragon/fakturę albo użyj przycisku Edytuj.")
            return
        draft = self.state.get_draft(draft_id)
        if not draft:
            self.edit_sessions.pop(chat_id, None)
            await update.message.reply_text("Brak szkicu do edycji.")
            return

        draft = apply_manual_edits(draft, update.message.text)
        self.state.save_draft(draft)
        month_key = current_month_key()
        remaining = self.state.preview_remaining(month_key, draft.kwota)
        suspicious = _needs_manual_check(
            draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
        )
        text = draft.to_preview_text(remaining)
        if suspicious:
            text += "\n\n" + _manual_check_message(
                draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
            )
        await update.message.reply_text(
            text,
            reply_markup=_preview_keyboard(draft.draft_id, suspicious),
        )

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled Telegram update error", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "Coś poszło nie tak podczas przetwarzania. Wyślij dokument jeszcze raz."
                )
            except TelegramError:
                logger.exception("Failed to notify user about update error")

    async def _get_file_or_notify(self, update: Update, media) -> object | None:
        try:
            return await media.get_file()
        except (TimedOut, NetworkError) as exc:
            logger.warning("Telegram file download request timed out: %s", exc)
            await update.message.reply_text(
                "Nie udało się pobrać pliku z Telegrama. Wyślij go jeszcze raz, najlepiej jako dokument."
            )
            return None

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        if not self._is_allowed(update):
            return

        action, draft_id, payload = _parse_callback_data(query.data)
        draft = self.state.get_draft(draft_id)
        if not draft:
            await query.edit_message_text("Szkic już nie istnieje.")
            return

        if action == "edit":
            self.edit_sessions[query.message.chat_id] = draft_id
            await query.message.reply_text(
                "Wyślij poprawki w formacie:\n"
                "wyjazd_nazwa: targi agroshow\n"
                "wyjazd_data: 2026-04-23\n"
                "typ_dokumentu: faktura_a4\n"
                "data_dokumentu: 2026-04-22\n"
                "nr_paragonu: 108592\n"
                "kwota: 123.45\n"
                "adres: Elektryczna 8A, 49-300 Brzeg\n"
                "towar: paliwo i parking\n"
                "uwagi: stoisko marketing"
            )
            return

        if action == "details":
            month_key = current_month_key()
            remaining = self.state.preview_remaining(month_key, draft.kwota)
            suspicious = _needs_manual_check(
                draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
            )
            await query.message.reply_text(
                draft.to_details_text(remaining),
                reply_markup=_preview_keyboard(draft.draft_id, suspicious),
            )
            return

        if action == "cancel":
            self.state.delete_draft(draft_id)
            self.edit_sessions.pop(query.message.chat_id, None)
            await query.edit_message_text("Anulowano zapis paragonu.")
            return

        if action in {"save", "force_save"}:
            needs_check = _needs_manual_check(
                draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
            )
            if needs_check and action != "force_save":
                await query.message.reply_text(
                    _manual_check_message(
                        draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
                    ),
                    reply_markup=_preview_keyboard(draft.draft_id, suspicious=True),
                )
                return
            month_key = current_month_key()
            budget_remaining = self.state.commit_spend(month_key, draft.kwota)
            receipt_url = self.sink.save_receipt(draft, budget_remaining)
            self.state.delete_draft(draft_id)
            self.edit_sessions.pop(query.message.chat_id, None)
            table_path = generate_register(self.settings.data_dir)
            await query.edit_message_text(
                "Dopisano do wspólnej tabeli Excel.\n"
                f"Pozostały budżet: {budget_remaining:.2f} PLN\n"
                f"Tabela: {table_path}\n"
                f"Zdjęcie: {receipt_url or 'brak'}"
            )
            return

        await query.message.reply_text("Nieznana akcja.")

    async def _process_file(self, update: Update, file_name: str, file_obj) -> None:
        chat_id = update.effective_chat.id
        draft_id = uuid.uuid4().hex[:10]
        suffix = Path(file_name or "receipt.jpg").suffix or ".jpg"
        target = self.settings.data_dir / "receipts" / f"{draft_id}{suffix}"
        await file_obj.download_to_drive(custom_path=str(target))

        draft = ReceiptDraft.empty(draft_id=draft_id, chat_id=chat_id, source_path=str(target))
        try:
            ocr_result = extract_ocr_result(target, self.settings)
            draft = parse_receipt_text(ocr_result.text, draft)
            draft.ocr_confidence = ocr_result.confidence
            draft.ocr_variant = ocr_result.variant
        except OcrError as exc:
            logger.warning("OCR failed: %s", exc)
            draft.uwagi = f"OCR error: {exc}"

        self.state.save_draft(draft)
        month_key = current_month_key()
        remaining = self.state.preview_remaining(month_key, draft.kwota)
        suspicious = _needs_manual_check(
            draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
        )
        text = draft.to_preview_text(remaining)
        if suspicious:
            text += "\n\n" + _manual_check_message(
                draft, self.settings.max_auto_save_amount, self.settings.ocr_confidence_warn
            )
        await update.message.reply_text(
            text,
            reply_markup=_preview_keyboard(draft.draft_id, suspicious),
        )

    def _is_allowed(self, update: Update) -> bool:
        chat_id = update.effective_chat.id if update.effective_chat else None
        allowed = self.settings.telegram_allowed_chat_id
        if allowed is None:
            return True
        return chat_id == allowed


def _preview_keyboard(draft_id: str, suspicious: bool = False) -> InlineKeyboardMarkup:
    if suspicious:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Edytuj", callback_data=f"edit:{draft_id}"),
                    InlineKeyboardButton("Szczegóły", callback_data=f"details:{draft_id}"),
                ],
                [
                    InlineKeyboardButton("Zapisz mimo to", callback_data=f"force_save:{draft_id}"),
                    InlineKeyboardButton("Anuluj", callback_data=f"cancel:{draft_id}"),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Zapisz", callback_data=f"save:{draft_id}"),
                InlineKeyboardButton("Edytuj", callback_data=f"edit:{draft_id}"),
            ],
            [
                InlineKeyboardButton("Szczegóły", callback_data=f"details:{draft_id}"),
                InlineKeyboardButton("Anuluj", callback_data=f"cancel:{draft_id}"),
            ],
        ]
    )


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_ADD],
            [BTN_TABLE, BTN_RECENT],
            [BTN_STATUS, BTN_HELP],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _select_photo(photos, max_pixels: int):
    if not photos:
        raise ValueError("No Telegram photos in message")
    sorted_photos = sorted(photos, key=lambda photo: photo.width * photo.height)
    for photo in reversed(sorted_photos):
        if photo.width * photo.height <= max_pixels:
            return photo
    return sorted_photos[-1]


def _read_recent_rows(rows_file: Path, limit: int = 5) -> list[dict]:
    import json

    if not rows_file.exists():
        return []
    rows = []
    with rows_file.open(encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[-limit:][::-1]


def _parse_callback_data(data: str) -> tuple[str, str, str | None]:
    parts = data.split(":", 2)
    action = parts[0]
    draft_id = parts[1] if len(parts) > 1 else ""
    payload = parts[2] if len(parts) > 2 else None
    return action, draft_id, payload


def _missing_critical_fields(draft: ReceiptDraft) -> bool:
    """Warn if a field we really need is empty: amount, date, or any seller identity."""
    if not draft.kwota:
        return True
    if not draft.data_dokumentu:
        return True
    if not draft.nip and not draft.sprzedawca:
        return True
    return False


def _low_confidence(draft: ReceiptDraft, confidence_warn: float) -> bool:
    """Low OCR confidence, but only when we actually have a confidence value (>0)."""
    return bool(draft.ocr_confidence) and draft.ocr_confidence < confidence_warn


def _needs_manual_check(
    draft: ReceiptDraft, max_auto_save_amount: float, confidence_warn: float = 0.0
) -> bool:
    if draft.kwota is None or draft.kwota <= 0 or draft.kwota > max_auto_save_amount:
        return True
    if _missing_critical_fields(draft):
        return True
    if _low_confidence(draft, confidence_warn):
        return True
    return False


def _manual_check_message(
    draft: ReceiptDraft, max_auto_save_amount: float, confidence_warn: float = 0.0
) -> str:
    reasons: list[str] = []
    if draft.kwota is None:
        reasons.append("nie udało się pewnie odczytać kwoty")
    elif draft.kwota <= 0:
        reasons.append("kwota wygląda nieprawidłowo")
    elif draft.kwota > max_auto_save_amount:
        reasons.append(
            f"kwota {draft.kwota:.2f} PLN wygląda bardzo wysoko "
            f"(limit bez ostrzeżenia: {max_auto_save_amount:.2f} PLN)"
        )
    if not draft.data_dokumentu:
        reasons.append("brak daty dokumentu")
    if not draft.nip and not draft.sprzedawca:
        reasons.append("brak NIP i sprzedawcy")
    if _low_confidence(draft, confidence_warn):
        reasons.append(f"niska pewność odczytu OCR ({draft.ocr_confidence:.0%})")
    if not reasons:
        reasons.append("sprawdź dane przed zapisem")
    return "Uwaga: " + "; ".join(reasons) + ". Sprawdź dane przed zapisem albo kliknij Edytuj."
