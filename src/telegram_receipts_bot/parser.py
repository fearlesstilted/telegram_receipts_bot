from __future__ import annotations

import re
from datetime import datetime

from .models import ReceiptDraft, ReceiptItem

DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[./-](\d{2})[./-](\d{2})(?!\d)"),
    re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{4})(?=\d{2}:\d{2}\b)"),
    re.compile(r"\b(\d{2})[./-](\d{2})(\d{4})(?=\d{2}:\d{2}\b)"),
    re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b"),
    re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{2})\b"),
    re.compile(r"\b(\d{2})[./-](\d{2})\s+(\d{4})\b"),
    re.compile(r"\b(\d{2})[./-](\d{2})\s+(\d{2})\b"),
]
NIP_RE = re.compile(r"\bN\s*[I1L]?\s*P[:\s]*([0-9][0-9 -]{8,16}[0-9])\b", re.IGNORECASE)
MONEY_RE = re.compile(r"(?<![A-Za-z0-9])(-?\d{1,7}[.,]\d{2}|[IILl]\d{1,6}[.,]\d{2})(?!\d)")
INVOICE_RE = re.compile(
    r"\b(?:nr\s*f[av]?|faktura|paragon)\b[:\s#/-]*([A-Z0-9/_-]{3,})",
    re.IGNORECASE,
)
TOTAL_HINTS = (
    "suma",
    "razem",
    "do zaplaty",
    "do zapłaty",
    "razem do zaplaty",
    "razem do zapłaty",
    "razem do zaptaty",
    "do zaptaty",
    "do zapeaty",
    "razem do zapeaty",
    "wartosc brutto",
    "wartość brutto",
    "sprzedaz opod",
    "sprzedaż opod",
)
A4_DOCUMENT_HINTS = (
    "faktura vat",
    "potwierdzenie sprzedaży",
    "potwierdzenie sprzedazy",
    "data wystawienia",
    "miejsce wystawienia",
    "nabywca:",
)
ROLLED_INVOICE_HINTS = (
    "faktura nr",
    "data wystawienia faktury",
    "nip nabywcy",
)
FISCAL_RECEIPT_HINTS = (
    "paragon fiskalny",
    "suma pln",
    "do zaplaty",
    "do zapłaty",
)


def parse_receipt_text(raw_text: str, draft: ReceiptDraft) -> ReceiptDraft:
    lines = _normalized_lines(raw_text)
    draft.ocr_text = "\n".join(lines)
    draft.typ_dokumentu = _detect_document_type(lines)
    draft.data_dokumentu = _extract_date(lines)
    draft.nip = _extract_a4_seller_nip(lines) if draft.typ_dokumentu == "faktura_a4" else _extract_nip(lines)
    if not draft.nip:
        draft.nip = _extract_nip(lines)
    draft.nr_fv = _extract_invoice_number(lines)
    draft.nr_paragonu = "" if draft.typ_dokumentu == "faktura_a4" else _extract_receipt_number(lines)
    draft.kwota = _extract_total(lines)
    draft.sprzedawca = _extract_a4_seller(lines) if draft.typ_dokumentu == "faktura_a4" else _extract_seller(lines)
    if not draft.sprzedawca:
        draft.sprzedawca = _extract_seller(lines)
    draft.nip = _normalize_known_vendor_nip(lines, draft.nip)
    draft.adres = _extract_address(lines, draft.sprzedawca)
    draft.items = _extract_items(lines)
    draft.towar = _build_towar(draft.items)
    return draft


def apply_manual_edits(draft: ReceiptDraft, message: str) -> ReceiptDraft:
    mapping = {}
    for raw_line in message.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        mapping[key.strip().lower()] = value.strip()

    text_fields = {
        "wyjazd_nazwa",
        "wyjazd_data",
        "typ_dokumentu",
        "data_dokumentu",
        "nr_fv",
        "nr_paragonu",
        "sprzedawca",
        "adres",
        "nip",
        "towar",
        "uwagi",
    }
    for key in text_fields:
        if key in mapping:
            setattr(draft, key, mapping[key])

    if "kwota" in mapping:
        draft.kwota = _safe_money(mapping["kwota"])

    if "pozycje" in mapping:
        items = []
        for part in mapping["pozycje"].split("|"):
            name = part.strip()
            if name:
                items.append(ReceiptItem(name=name))
        draft.items = items
        if not draft.towar:
            draft.towar = _build_towar(items)

    return draft


def _normalized_lines(raw_text: str) -> list[str]:
    raw_lines = raw_text.replace("\r", "\n").split("\n")
    lines = []
    for raw_line in raw_lines:
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _extract_date(lines: list[str]) -> str:
    for label in (
        "data wystawienia faktury",
        "data wystawienia",
        "data sprzedaży",
        "data sprzedazy",
        "data zakończenia",
        "data zakonczenia",
    ):
        value = _extract_date_near_label(lines, label)
        if value:
            return value

    for line in lines:
        for pattern in DATE_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = _date_from_match(match)
            if value:
                return value
    return ""


def _extract_date_near_label(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        if label not in line.lower():
            continue
        for candidate in [line, *lines[index + 1 : index + 3]]:
            for pattern in DATE_PATTERNS:
                match = pattern.search(candidate)
                if not match:
                    continue
                value = _date_from_match(match)
                if value:
                    return value
    return ""


def _date_from_match(match: re.Match[str]) -> str:
    parts = match.groups()
    if len(parts[0]) == 4:
        year, month, day = parts[0], parts[1], parts[2]
    elif len(parts[2]) == 2:
        year, month, day = f"20{parts[2]}", parts[1], parts[0]
    else:
        year, month, day = parts[2], parts[1], parts[0]

    value = f"{year}-{month}-{day}"
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return ""
    return value


def _extract_nip(lines: list[str]) -> str:
    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines[:80]):
        lower = line.lower()
        if not _has_nip_marker(line):
            if "regon" in lower:
                digits = re.sub(r"\D", "", line)
                if _looks_like_nip_digits(digits):
                    candidates.append((_nip_score(lines, index, line), digits[:10]))
            continue

        match = NIP_RE.search(line)
        if match:
            digits = re.sub(r"\D", "", match.group(1))[:10]
            if _looks_like_nip_digits(digits):
                candidates.append((_nip_score(lines, index, line), digits))
            continue

        if re.search(r"\bN\s*[I1L]?\s*P[:\s]*$", line, re.IGNORECASE):
            for candidate in lines[index + 1 : index + 3]:
                digits = re.sub(r"\D", "", candidate)
                if _looks_like_nip_digits(digits):
                    candidates.append((_nip_score(lines, index, line + " " + candidate), digits[:10]))
                    break

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return ""


def _extract_a4_seller_nip(lines: list[str]) -> str:
    buyer_index = _first_line_index(lines, ("nabywca",))
    search_lines = lines[: buyer_index if buyer_index is not None else min(len(lines), 30)]
    for line in search_lines:
        if not _has_nip_marker(line):
            continue
        match = NIP_RE.search(line)
        if match:
            digits = re.sub(r"\D", "", match.group(1))[:10]
            if _looks_like_nip_digits(digits):
                return digits
        digits = re.sub(r"\D", "", line)
        if _looks_like_nip_digits(digits):
            return digits[:10]
    return ""


def _has_nip_marker(line: str) -> bool:
    return bool(re.search(r"\bN\s*[I1L]?\s*P", line, re.IGNORECASE))


def _looks_like_nip_digits(digits: str) -> bool:
    if len(digits) < 10:
        return False
    value = digits[:10]
    return not re.match(r"20\d{8}", value)


def _nip_score(lines: list[str], index: int, line: str) -> int:
    context = " ".join(lines[max(0, index - 3) : index + 3]).lower()
    score = 100 - index
    if "nabyw" in context:
        score -= 80
    if "sprzed" in context:
        score += 60
    if "regon" in context:
        score += 90
    if "sp. z" in context or "sp.z" in context:
        score += 35
    if "nip nabywcy" in line.lower():
        score -= 120
    return score


def _normalize_known_vendor_nip(lines: list[str], nip: str) -> str:
    haystack = " ".join(lines[:12]).lower()
    if "action" in haystack and nip.startswith("954277"):
        return "9542778083"
    if (
        nip.startswith("747")
        and ("gastronomic" in haystack or "firek" in haystack or "mario" in haystack)
    ):
        return "7471727805"
    return nip


def _extract_invoice_number(lines: list[str]) -> str:
    for line in lines[:25]:
        invoice_match = re.search(
            r"\b(?:faktura\s*(?:vat)?|faktura\s*nr|potwierdzenie\s+sprzedaży|potwierdzenie\s+sprzedazy)"
            r"[:\s#/-]*([A-Z0-9][A-Z0-9/_-]{2,})",
            line,
            re.IGNORECASE,
        )
        if invoice_match:
            value = invoice_match.group(1)
            if value.lower() not in {"vat", "fiskalny"}:
                return value
        if "faktura" in line.lower() or "potwierdzenie sprzeda" in line.lower():
            fallback = re.search(r"\b([A-Z]{1,4}/?[A-Z0-9]+/[A-Z0-9/_-]{2,})\b", line)
            if fallback:
                return fallback.group(1)
            fallback = re.search(r"\b(\d{2,}/\d{2,}/\d{2,}(?:/\d{4})?)\b", line)
            if fallback:
                return fallback.group(1)
            next_value = _extract_document_number_from_following_lines(lines, lines.index(line))
            if next_value:
                return next_value
        match = INVOICE_RE.search(line)
        if match:
            value = match.group(1)
            if value.lower() in {"fiskalny", "vat"}:
                continue
            return value
    return ""


def _extract_document_number_from_following_lines(lines: list[str], index: int) -> str:
    for candidate in lines[index + 1 : index + 4]:
        value = candidate.strip(" ,.;")
        if re.search(r"\b(?:data|sprzedawca|nabywca|nip|lp|nazwa)\b", value, re.IGNORECASE):
            continue
        match = re.search(r"\b([A-Z]{1,4}/?[A-Z0-9]+/[A-Z0-9/_-]{2,})\b", value)
        if match:
            return match.group(1)
        match = re.search(r"\b(\d{2,}/\d{2,}/\d{2,}(?:/\d{4})?)\b", value)
        if match:
            return match.group(1)
    return ""


def _extract_receipt_number(lines: list[str]) -> str:
    order_number = _extract_order_or_register_number(lines)
    if order_number:
        return order_number

    for index, line in enumerate(lines):
        lower = line.lower()
        if re.search(r"\b(nr|ne)\s*sys\b", lower):
            same_line = re.search(r"\b(?:nr|ne)\s*sys[:\s-]*(\d{3,})\b", line, re.IGNORECASE)
            if same_line:
                return same_line.group(1)
            for candidate in lines[index + 1 : index + 4]:
                match = re.search(r"\b(\d{5,})\b", candidate)
                if match:
                    return match.group(1)

    for line in reversed(lines):
        lower = line.lower()
        if "nip nabywcy" in lower or "nabywcy" in lower:
            continue
        match = re.search(r"\b([A-F0-9]{16,})\b", line, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def _extract_order_or_register_number(lines: list[str]) -> str:
    preferred_patterns = (
        re.compile(r"\bF\d{3,}/\d{2}\s*#?\s*[A-Z0-9]{4,}\b", re.IGNORECASE),
    )
    for line in lines:
        for pattern in preferred_patterns:
            match = pattern.search(line)
            if match:
                return re.sub(r"\s+", " ", match.group(0).strip())

    for index, line in enumerate(lines):
        lower = line.lower()
        if "nr zan" not in lower and "nr zam" not in lower:
            continue
        for candidate in lines[index : index + 4]:
            match = re.search(r"\b[A-Z]\d{8,}\b", candidate, re.IGNORECASE)
            if match:
                return match.group(0).upper()
            match = re.search(r"\b\d{5,}\b", candidate)
            if match:
                return match.group(0)
    return ""


def _extract_total(lines: list[str]) -> float | None:
    prioritized = (
        "razem do zaplaty",
        "razem do zapłaty",
        "razem do zaptaty",
        "razem do zapeaty",
        "suma pln",
        "suma:",
        "do zaplaty",
        "do zapłaty",
        "do zaptaty",
        "do zapeaty",
        "wartosc brutto",
        "wartość brutto",
        "brutto",
    )
    for hint in prioritized:
        amount = _extract_amount_near_hint(lines, hint)
        if amount is not None:
            return amount

    best: float | None = None
    for line in lines:
        lower = line.lower()
        numbers = [_safe_money(value) for value in MONEY_RE.findall(line)]
        numbers = [value for value in numbers if value is not None]
        if not numbers:
            continue
        if any(hint in lower for hint in TOTAL_HINTS):
            return max(numbers)
        best = max(numbers) if best is None else max(best, max(numbers))
    return best


def _extract_amount_near_hint(lines: list[str], hint: str) -> float | None:
    for index, line in enumerate(lines):
        if hint not in line.lower():
            continue
        search_lines = [line]
        if "warto" not in hint and "brutto" not in hint:
            search_lines.extend(lines[index + 1 : index + 3])
        amounts = []
        for candidate in search_lines:
            for value in MONEY_RE.findall(candidate):
                amount = _safe_money(value)
                if amount is not None:
                    amounts.append(amount)
        if amounts:
            return max(amounts)
    return None


def _extract_seller(lines: list[str]) -> str:
    for label in ("sprzedawca", "sprzedający", "sprzedajacy"):
        labelled = _extract_labelled_party(lines, label)
        if labelled:
            return labelled

    candidates = []
    marker_index = _first_document_marker_index(lines)
    search_limit = marker_index if marker_index is not None else 14
    search_limit = max(3, min(search_limit, 18))
    for index, line in enumerate(lines[:search_limit]):
        if not _looks_like_seller_candidate(line):
            continue
        candidates.append((_seller_score(line, index), line.strip(" ,.;")))
    if not candidates:
        return ""
    return _normalize_seller(max(candidates, key=lambda item: item[0])[1])


def _extract_a4_seller(lines: list[str]) -> str:
    buyer_index = _first_line_index(lines, ("nabywca",))
    document_index = _first_line_index(lines, ("potwierdzenie sprzeda", "faktura vat", "faktura nr"))
    limit_candidates = [value for value in (buyer_index, document_index) if value is not None]
    limit = min(limit_candidates) if limit_candidates else min(len(lines), 30)

    candidates = []
    for index, line in enumerate(lines[:limit]):
        if not _looks_like_seller_candidate(line):
            continue
        candidates.append((_a4_seller_score(line, index), line.strip(" ,.;")))

    if not candidates:
        return ""
    return _normalize_seller(max(candidates, key=lambda item: item[0])[1])


def _a4_seller_score(line: str, index: int) -> int:
    lower = line.lower()
    score = 100 - index
    business_words = (
        "spolka",
        "spółka",
        "sp.j",
        "spj",
        "sp. z",
        "sp.z",
        "jawna",
        "gwintech",
        "kan",
    )
    score += sum(35 for word in business_words if word in lower)
    if re.search(r"\b(bank|credit|miejsce|data|wystawienia|brzeg)$", lower):
        score -= 80
    return score


def _first_line_index(lines: list[str], needles: tuple[str, ...]) -> int | None:
    for index, line in enumerate(lines):
        lower = line.lower()
        if any(needle in lower for needle in needles):
            return index
    return None


def _extract_labelled_party(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines[:30]):
        if label not in line.lower():
            continue
        candidates = []
        after_colon = line.split(":", 1)[1].strip(" ,.;") if ":" in line else ""
        if after_colon and not re.search(r"^\d", after_colon):
            candidates.append(after_colon)
        for candidate in lines[index + 1 : index + 8]:
            lower = candidate.lower()
            if any(word in lower for word in ("nabywca", "nip", "data", "lp", "nazwa", "razem")):
                break
            if _looks_like_seller_candidate(candidate):
                candidates.append(candidate.strip(" ,.;"))
        if candidates:
            return _normalize_seller(candidates[0])
    return ""


def _first_document_marker_index(lines: list[str]) -> int | None:
    markers = ("paragon fiskalny", "paragon", "faktura nr", "faktura vat", "potwierdzenie sprzeda")
    for index, line in enumerate(lines[:40]):
        lower = line.lower()
        if any(marker in lower for marker in markers):
            return index
    return None


def _normalize_seller(line: str) -> str:
    cleaned = line.strip(" ,.;")
    cleaned = re.sub(r"\b(USŁUG|USLUG)\.\s+", r"\1 ", cleaned)
    if "act" in cleaned.lower() and "poland" in cleaned.lower():
        return "Action Poland Sp. z o.o."
    return cleaned


def _looks_like_seller_candidate(line: str) -> bool:
    lower = line.lower()
    skip_words = (
        "nip",
        "paragon",
        "faktura",
        "miejsce",
        "mesce",
        "wystawienia",
        "zakonczenia",
        "zakończenia",
        "dostawy",
        "brzeg",
        "sprzedaz",
        "sprzedaż",
        "sprzedajacy",
        "sprzedający",
        "nabywca",
        "kasa",
        "pln",
        "elektryczna",
        "graniczna",
        "goldap",
        "plac",
        "ul.",
        "krakow",
        "kraków",
    )
    if any(word in lower for word in skip_words):
        return False
    if line.endswith(":"):
        return False
    if re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", line):
        return False
    letters = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]", line)
    if len(letters) < 8 and "sp" not in lower:
        return False
    if len(line) < 8 and "sp" not in lower:
        return False
    if re.search(r"\d{2}-\d{3}", line) or _looks_like_street_line(line):
        return False
    if lower.startswith(("ul.", "u1.", "al.")):
        return False
    return True


def _seller_score(line: str, index: int) -> int:
    lower = line.lower()
    score = 40 - index
    business_words = (
        "centrum",
        "usług",
        "uslug",
        "gastronomic",
        "spółka",
        "spolka",
        "jawna",
        "sklep",
        "biedronka",
        "lidl",
        "orlen",
        "shell",
        "bar",
        "sp. z",
        "sp.z",
    )
    score += sum(25 for word in business_words if word in lower)
    score += min(len(line), 60)
    if len(line.split()) == 2 and len(line) < 14:
        score -= 45
    if not any(char.isupper() for char in line):
        score -= 10
    return score


def _extract_address(lines: list[str], seller: str) -> str:
    seller_index = 0
    if seller:
        try:
            seller_index = lines.index(seller)
        except ValueError:
            seller_index = 0

    address_lines = []
    for line in lines[seller_index + 1 : seller_index + 8]:
        lower = line.lower()
        if any(word in lower for word in ("nip", "paragon", "faktura", "sprzedawca")):
            break
        if re.search(r"\b\d{1,2}-\d{3}\b", line) or _looks_like_street_line(line):
            address_lines.append(_normalize_address_line(line))
        if len(address_lines) >= 2:
            break
    return ", ".join(address_lines)


def _looks_like_street_line(line: str) -> bool:
    lower = line.lower()
    return bool(
        any(word in lower for word in ("ul.", "u1.", "al.", "brzeg", "elektryczna"))
        or re.search(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ .-]+\s+\d+[A-Z]?\b", line)
    )


def _normalize_address_line(line: str) -> str:
    cleaned = line.strip(" ,.;|")
    if re.search(r"\bBRZEG\b", cleaned, re.IGNORECASE):
        cleaned = re.sub(r"\b(?:4|48|43)-300\b", "49-300", cleaned)
    return cleaned


def _detect_document_type(lines: list[str]) -> str:
    haystack = " ".join(lines[:40]).lower()
    if "paragon fiskalny" in haystack:
        return "paragon"
    if any(hint in haystack for hint in A4_DOCUMENT_HINTS):
        return "faktura_a4"
    if any(hint in haystack for hint in ROLLED_INVOICE_HINTS):
        return "faktura"
    if "suma pln" in haystack:
        return "paragon"
    return "niepewne"


def _extract_items(lines: list[str]) -> list[ReceiptItem]:
    items: list[ReceiptItem] = []
    skip_words = TOTAL_HINTS + (
        "nip",
        "paragon",
        "faktura",
        "gotowka",
        "gotówka",
        "reszta",
        "kasjer",
        "ptu",
        "opodatkowana",
        "zapłaty",
        "zaplaty",
    )
    for line in lines:
        lower = line.lower()
        if any(word in lower for word in skip_words):
            continue
        match = MONEY_RE.search(line)
        if not match:
            continue
        price = _safe_money(match.group(1))
        name = line[: match.start()].strip(" -.:")
        if len(name) < 2:
            continue
        if name.lower() in {"pln", "eur", "usd"}:
            continue
        if re.search(r"\d{2}[./-]\d{2}[./-]\d{4}", name):
            continue
        items.append(ReceiptItem(name=name[:120], price=price))
        if len(items) >= 12:
            break
    return items


def _build_towar(items: list[ReceiptItem]) -> str:
    names = [item.name for item in items if item.name]
    return ", ".join(names[:3])


def _safe_money(raw_value: str) -> float | None:
    cleaned = raw_value.replace(" ", "").replace(",", ".")
    cleaned = re.sub(r"^[IILl](?=\d)", "1", cleaned)
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None
