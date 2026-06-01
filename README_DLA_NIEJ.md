# Bot do paragonów

Bot działa lokalnie na komputerze. Nie ma chmury i nie ma Google billing.
Komputer musi być włączony tylko wtedy, kiedy bot ma przetwarzać paragony.

## Pierwsza instalacja na Windows

Uruchom:

```bat
RUN_WINDOWS.bat
```

Ten plik sam sprawdzi instalację i uruchomi bota. Jeśli `.env` nie istnieje,
utworzy go z `.env.example`.

Przed uruchomieniem lub po pierwszym błędzie uzupełnij plik `.env`:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=...
OCR_MODE=paddle
```

## Normalne uruchomienie

Windows:

```bat
RUN_WINDOWS.bat
```

Linux:

```bash
./start_bot.sh
```

Zatrzymanie: `Ctrl+C`.

## Jak używać

1. Otwórz bota w Telegramie.
2. Kliknij `Dodaj paragon/fakturę` albo po prostu wyślij zdjęcie.
3. Poczekaj na odczyt OCR.
4. Sprawdź krótki podgląd: data, kwota, sprzedawca, NIP.
5. Jeśli coś jest źle, kliknij `Edytuj` i wyślij poprawkę.
6. Jeśli dane są OK, kliknij `Zapisz`.
7. Paragon zostanie dopisany do wspólnego pliku Excel.

Można wysłać kilka zdjęć po kolei. Bot zrobi osobny podgląd dla każdego
paragonu. Każdy paragon trzeba zatwierdzić przyciskiem `Zapisz`.

## Przyciski w Telegramie

- `Dodaj paragon/fakturę` - pokazuje, że można wysłać zdjęcie.
- `Tabela Excel` - wysyła aktualny plik Excel.
- `Ostatnie zapisy` - pokazuje ostatnie zapisane paragony.
- `Status` - pokazuje budżet i wydaną kwotę.
- `Instrukcja` - pokazuje krótką pomoc.

Jeśli bot pokaże ostrzeżenie o bardzo dużej kwocie, sprawdź kwotę przed zapisem.
To zabezpiecza tabelę przed błędem OCR.

## Plik Excel

Główny plik:

```text
data/rozliczenie_paragonow.xlsx
```

Arkusze:

- `Miesiące` - tutaj wpisujesz zaliczkę za miesiąc;
- `Paragony` - tutaj bot dopisuje paragony;
- `OCR raw` - techniczny podgląd tekstu odczytanego ze zdjęć.

W arkuszu `Miesiące` wpisz kwotę w kolumnie `Zaliczka`. Excel sam policzy sumę
paragonów i pozostałą kwotę.

## Reset tabeli

Jeśli trzeba zacząć od czystego Excela, uruchom:

```bat
RESET_EXCEL_WINDOWS.bat
```

Stare dane zostaną przeniesione do `data/archive`. Zdjęcia zostają w
`data/receipts`.

## Aktualizacja aplikacji

Jeśli aplikacja była pobrana przez git, uruchom:

```bat
UPDATE_WINDOWS.bat
```

Jeśli to zwykły folder z ZIP-a, aktualizacja jest ręczna: zamknij bota, zostaw
`data` i `.env`, podmień pliki aplikacji i uruchom `RUN_WINDOWS.bat`.

## Poprawianie danych

Po kliknięciu `Edytuj` można wysłać np.:

```text
data_dokumentu: 2026-04-09
kwota: 127.00
sprzedawca: CENTRUM USŁUG GASTRONOMICZNYCH MARIO
nip: 7471727805
adres: ELEKTRYCZNA 8A, 49-300 BRZEG
towar: obiad
uwagi: delegacja
```

## Ważne

OCR nie zawsze jest idealny. Przed kliknięciem `Zapisz` warto sprawdzić przede
wszystkim kwotę, datę, NIP, sprzedawcę i kategorię.
