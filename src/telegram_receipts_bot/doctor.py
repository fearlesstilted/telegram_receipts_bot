"""Self-test / onboarding diagnostics for the receipts bot.

Run with:  python -m telegram_receipts_bot.doctor
or, on Windows, via DIAGNOZA.bat.

The diagnosis is split into two independent parts:

1. CORE install checks (Python version, dependencies, .env, data dir). A failure here
   means the bot cannot run; the process exits with a non-zero code.
2. An OPTIONAL OCR smoke test that actually runs OCR on a local receipt photo. This may
   download models on first run or hit the known Windows/CPU Paddle crash. A failure here
   is reported as a warning and never fails the overall diagnosis.

All user-facing messages are in Polish; a copy of the report is written to
logs/diagnoza.txt so the user can send it back if something is wrong.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Core third-party modules the bot imports at runtime. Tuples are
# (import_name, friendly_name) so the report names the missing package clearly.
CORE_IMPORTS = (
    ("telegram", "python-telegram-bot"),
    ("dotenv", "python-dotenv"),
    ("PIL", "Pillow"),
    ("numpy", "numpy"),
    ("paddle", "paddlepaddle"),
    ("paddleocr", "paddleocr"),
)

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str = "") -> None:
        self.name = name
        self.ok = ok
        self.detail = detail


def _check_python() -> CheckResult:
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info[2]}"
    if (major, minor) == (3, 11):
        return CheckResult("Python 3.11", True, version)
    return CheckResult(
        "Python 3.11",
        False,
        f"Wykryto Python {version}. Zainstaluj Python 3.11 z python.org "
        "i zaznacz 'Add python.exe to PATH'.",
    )


def _check_imports() -> list[CheckResult]:
    results: list[CheckResult] = []
    for module_name, friendly in CORE_IMPORTS:
        try:
            __import__(module_name)
            results.append(CheckResult(f"Pakiet: {friendly}", True))
        except Exception as exc:  # noqa: BLE001 - report any import problem verbatim
            results.append(
                CheckResult(
                    f"Pakiet: {friendly}",
                    False,
                    f"Nie można zaimportować ({exc}). Uruchom RUN_WINDOWS.bat, "
                    "aby zainstalować zależności.",
                )
            )
    return results


def _check_env_and_data() -> list[CheckResult]:
    results: list[CheckResult] = []
    try:
        from .config import load_settings

        settings = load_settings()
    except Exception as exc:  # noqa: BLE001
        results.append(CheckResult("Konfiguracja .env", False, f"Błąd wczytywania: {exc}"))
        return results

    if settings.telegram_bot_token:
        results.append(CheckResult("TELEGRAM_BOT_TOKEN", True))
    else:
        results.append(
            CheckResult(
                "TELEGRAM_BOT_TOKEN",
                False,
                "Pusty token. Otwórz plik .env i uzupełnij TELEGRAM_BOT_TOKEN=...",
            )
        )

    if settings.telegram_allowed_chat_id is not None:
        results.append(CheckResult("TELEGRAM_ALLOWED_CHAT_ID", True))
    else:
        results.append(
            CheckResult(
                "TELEGRAM_ALLOWED_CHAT_ID",
                False,
                "Brak ID czatu. Otwórz plik .env i uzupełnij TELEGRAM_ALLOWED_CHAT_ID=...",
            )
        )

    receipts_dir = settings.data_dir / "receipts"
    try:
        receipts_dir.mkdir(parents=True, exist_ok=True)
        probe = receipts_dir / ".diagnoza_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        results.append(CheckResult("Zapis do folderu data", True, str(settings.data_dir)))
    except Exception as exc:  # noqa: BLE001
        results.append(
            CheckResult("Zapis do folderu data", False, f"Nie można pisać do {receipts_dir}: {exc}")
        )

    return results


def _find_sample_image() -> Path | None:
    """Return a local receipt image to smoke-test OCR, or None if none exists.

    We never bundle a private photo in the repo; we reuse whatever the user already
    received under data/receipts. If the folder is empty the smoke test is skipped.
    """
    try:
        from .config import load_settings

        receipts_dir = load_settings().data_dir / "receipts"
    except Exception:  # noqa: BLE001
        return None
    if not receipts_dir.exists():
        return None
    for path in sorted(receipts_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            return path
    return None


def _ocr_smoke_test() -> CheckResult:
    """Optional: run OCR on a local image. Failure here never fails the diagnosis."""
    sample = _find_sample_image()
    if sample is None:
        return CheckResult(
            "Test OCR (opcjonalny)",
            True,
            "Pominięto: brak zdjęcia w data/receipts. Wyślij paragon do bota, "
            "aby przetestować OCR.",
        )

    try:
        from .config import load_settings
        from .ocr import extract_text

        settings = load_settings()
        started = time.monotonic()
        text = extract_text(sample, settings)
        elapsed = time.monotonic() - started
    except Exception as exc:  # noqa: BLE001 - smoke test must not crash diagnosis
        return CheckResult(
            "Test OCR (opcjonalny)",
            False,
            f"OCR nie zadziałał na {sample.name}: {exc}. To nie blokuje instalacji - "
            "przy pierwszym uruchomieniu mogą pobierać się modele. Spróbuj ponownie.",
        )

    preview = " | ".join(text.splitlines()[:3]) if text else "(pusto)"
    return CheckResult(
        "Test OCR (opcjonalny)",
        bool(text.strip()),
        f"Plik {sample.name}, {elapsed:.1f}s, początek tekstu: {preview}",
    )


def _format_report(core: list[CheckResult], optional: list[CheckResult]) -> str:
    lines = ["=" * 60, "DIAGNOZA - Bot do paragonów", "=" * 60, "", "Sprawdzenie instalacji:"]
    for result in core:
        mark = "OK  " if result.ok else "BŁĄD"
        lines.append(f"  [{mark}] {result.name}")
        if result.detail:
            lines.append(f"         {result.detail}")
    lines.append("")
    lines.append("Test dodatkowy (nie blokuje instalacji):")
    for result in optional:
        mark = "OK  " if result.ok else "UWAGA"
        lines.append(f"  [{mark}] {result.name}")
        if result.detail:
            lines.append(f"         {result.detail}")
    lines.append("")
    if all(result.ok for result in core):
        lines.append("WYNIK: Instalacja wygląda dobrze. Możesz uruchomić RUN_WINDOWS.bat.")
    else:
        lines.append("WYNIK: Instalacja ma problem. Przeczytaj wiersze [BŁĄD] powyżej.")
    lines.append("=" * 60)
    return "\n".join(lines)


def _write_report(report: str) -> None:
    try:
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "diagnoza.txt").write_text(report, encoding="utf-8")
    except Exception:  # noqa: BLE001 - writing the report is best-effort
        pass


def run_diagnosis() -> int:
    core: list[CheckResult] = [_check_python()]
    core.extend(_check_imports())
    core.extend(_check_env_and_data())
    optional: list[CheckResult] = [_ocr_smoke_test()]

    report = _format_report(core, optional)
    print(report)
    _write_report(report)

    return 0 if all(result.ok for result in core) else 1


def main() -> None:
    sys.exit(run_diagnosis())


if __name__ == "__main__":
    main()
