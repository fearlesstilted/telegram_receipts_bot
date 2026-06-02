from telegram_receipts_bot.models import ReceiptDraft
from telegram_receipts_bot.parser import apply_manual_edits, parse_receipt_text


def test_parse_polish_receipt_text_extracts_core_fields() -> None:
    raw_text = """
    BIEDRONKA POZNAN
    ul. Testowa 1
    NIP 7791011327
    PARAGON 123456
    22-04-2026 14:33
    KAWA MIELONA 15,99
    WODA 3,49
    SUMA PLN 19,48
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.sprzedawca == "BIEDRONKA POZNAN"
    assert parsed.nip == "7791011327"
    assert parsed.typ_dokumentu == "paragon"
    assert parsed.data_dokumentu == "2026-04-22"
    assert parsed.nr_fv == "123456"
    assert parsed.kwota == 19.48
    assert parsed.towar.startswith("KAWA MIELONA")
    assert len(parsed.items) >= 2


def test_apply_manual_edits_overrides_values() -> None:
    draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
    edited = apply_manual_edits(
        draft,
        "wyjazd_nazwa: agroshow\ntyp_dokumentu: faktura_a4\nkwota: 100,50\nuwagi: marketing\npozycje: parking | paliwo",
    )

    assert edited.wyjazd_nazwa == "agroshow"
    assert edited.typ_dokumentu == "faktura_a4"
    assert edited.kwota == 100.50
    assert edited.uwagi == "marketing"
    assert [item.name for item in edited.items] == ["parking", "paliwo"]


def test_parse_noisy_fiscal_receipt_extracts_vendor_and_document_fields() -> None:
    raw_text = """
    >
    6 er Aire
    CENTRUM USŁUG. GASTRONOMICZNYCH MARIO
    ELEKTRYCZNA 8A
    48-300 BRZEG
    MARIUSZ FIREK, ALICJA FIREK SPÓŁKA JAWNA
    NIP: 7474727805,
    10770
    PARAGON FISKALNY
    DANIE DNIA 2 3 szt.*28.00
    84,008
    OPAKOWANIE NA 1 ZUPĘ 3 szt.#1.50
    TORBA PAPIEROWA 1 szt.*1.50
    DANIE DNIA 2 1 szt.+28.00
    OPAKOWANIE NA 1 ZUPĘ 1 szt.*1.50
    TORBA PAPIEROWA 1 szt.+1.50
    Sprzedaż opodatkowana A:
    112.00
    SUMA:
    PLN 127.00
    DO ZAPŁATY:
    127.00
    NIP nabywcy:
    8471616578
    09-04-2026 16: 14
    Ne Sys
    108592
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/r.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.sprzedawca == "CENTRUM USŁUG GASTRONOMICZNYCH MARIO"
    assert parsed.typ_dokumentu == "paragon"
    assert parsed.adres == "ELEKTRYCZNA 8A, 49-300 BRZEG"
    assert parsed.nip == "7471727805"
    assert parsed.data_dokumentu == "2026-04-09"
    assert parsed.nr_fv == ""
    assert parsed.nr_paragonu == "108592"
    assert parsed.kwota == 127.00
    assert all(item.name != "PLN" for item in parsed.items)


def test_parse_a4_invoice_extracts_invoice_fields() -> None:
    raw_text = """
    Sprzedający
    KAN Sp. z o.o.
    ul. Wiączyńska 8A
    92-760 ŁÓDŹ
    NIP: 725-10-19-880
    Faktura VAT
    FV/000003/26-S162
    Data wystawienia faktury 2026-03-02
    Data sprzedaży 2026-03-02
    Nabywca
    RCM
    NIP: 8471616578
    Nazwa art.
    koszula damska 1 SZT 162,59 37,40 199,99
    Wartość brutto
    199,99
    Do zapłaty:
    199,99 PLN
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/f.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.typ_dokumentu == "faktura_a4"
    assert parsed.nr_fv == "FV/000003/26-S162"
    assert parsed.data_dokumentu == "2026-03-02"
    assert parsed.nip == "7251019880"
    assert parsed.kwota == 199.99
    assert parsed.sprzedawca == "KAN Sp. z o.o"


def test_parse_a4_sales_confirmation_extracts_total_and_number() -> None:
    raw_text = """
    GWINTECH Roman i Marek Kowalik spółka jawna
    ul. Włościańska 18A
    49-304 BRZEG
    NIP: 747-14-91-314
    Miejsce wystawienia:
    BRZEG
    Data wystawienia
    09.04.2026
    Nabywca:
    RCM SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ
    NIP: 8471616578
    Potwierdzenie sprzedaży 1693/2026 oryginał
    lina stal.zn fi 02,0/6x7l
    Razem do zapłaty:
    518,76
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/f.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.typ_dokumentu == "faktura_a4"
    assert parsed.nr_fv == "1693/2026"
    assert parsed.nr_paragonu == ""
    assert parsed.data_dokumentu == "2026-04-09"
    assert parsed.nip == "7471491314"
    assert parsed.kwota == 518.76


def test_parse_a4_sales_confirmation_prefers_seller_block_before_buyer() -> None:
    raw_text = """
    Miejsce wystawienia:
    BRZEG
    Mesce wystawienia:
    GWINTECH Roman i Marek Kowalik spolka jawna
    Data zakonczenia dostawy/uslug
    ul.Wlosanska 18A.49-304 BRZEG
    09.04.2026
    Tel774115442.NIP747-14-91-314
    Data wystawienia
    CREDIT AGRICOLE Bank Polska SA,
    09.04.2026
    80194010763007202400000000
    Nabywca:
    Sprzedawca:
    RCM SPOLKA Z OGRANICZONA
    ODPOWIEDZIALNOSCIA
    GWINTECH Roman i Marek Kowalik spolka jawna
    Graniczna 3
    19-500Niedrzwica
    NIP8471616578
    NIP747-14-91-314
    Potwierdzenie sprzedazy 1693/2026 oryginat
    Razem do zaplaty:
    518,76
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/a4.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.typ_dokumentu == "faktura_a4"
    assert parsed.sprzedawca == "GWINTECH Roman i Marek Kowalik spolka jawna"
    assert parsed.nip == "7471491314"
    assert parsed.nr_fv == "1693/2026"
    assert parsed.nr_paragonu == ""
    assert parsed.kwota == 518.76


def test_parse_action_receipt_handles_short_date_and_payment_amount() -> None:
    raw_text = """
    Acton Poland Sp.Z.0.0.
    40-026 Ktowiceul.Wjewodzka 10
    NIP:9542778093
    PARAGON FISKALNY
    2511736 action torba 1*2.99 2.99A
    2506494 teddycare chus 1*3.99 3.99A
    Sprzedaz opodat kowana A
    166.97
    SUMA PTU
    PLN 175.92
    SUMA:
    175.92
    DO ZAPLATY
    ROZLICZENIE PLATNOSCI
    205.92
    Gotowka:
    30.00
    F0159/48 #A534101
    Nip nabywcy:
    PL8471616578
    09-04-26 11:10
    AD85F871403B032803S40370D80A6C2
    A53410190003114
    Nr zamowienia
    10066102
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/action.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.typ_dokumentu == "paragon"
    assert parsed.data_dokumentu == "2026-04-09"
    assert parsed.kwota == 175.92
    assert parsed.nip == "9542778083"
    assert parsed.nr_paragonu == "F0159/48 #A534101"
    assert parsed.sprzedawca == "Action Poland Sp. z o.o."


def test_parse_action_receipt_handles_date_glued_to_time() -> None:
    raw_text = """
    Acton Poland Sp.Z.0.0.
    NIP:9542778093
    PARAGON FISKALNY
    PLN 175.92
    SUMA:
    175.92
    09-04-202611:10
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/action.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.data_dokumentu == "2026-04-09"


def test_parse_action_receipt_ignores_bdo_as_document_number() -> None:
    raw_text = """
    IACTION
    Acton Poland Sp.70.0
    BO000066044
    NIP:9542778093
    PARAGON FISKALNY
    PLN 175.92
    SUMA:
    175.92
    DO ZAPLATY
    175.92
    NIP nabywcy:
    PL8471616578
    09-04 2026 11:10
    Nr zanowienia
    A53410190003114
    10066102
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/action.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.data_dokumentu == "2026-04-09"
    assert parsed.nr_paragonu == "A53410190003114"
    assert parsed.nr_paragonu != "B000066044"
    assert parsed.sprzedawca == "Action Poland Sp. z o.o."


def test_parse_lewiatan_ocr_noise_extracts_nip_date_and_total() -> None:
    raw_text = """
    LEWIATAN
    Ftrma Handtowo-Ustugowa "AMI"
    ul. warnenczyka 3
    87-860 cnodecz
    NP8881008080
    PARAGON FISKALNY
    Sprzeda2 opodat kowana A:
    122.33
    SUMA :
    PlN i22.33
    DO ZAPEATY:
    122.33
    Gotowka:
    225.00
    NIP nabywcy
    8471616678
    29-05202608:23
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/lewiatan.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.nip == "8881008080"
    assert parsed.data_dokumentu == "2026-05-29"
    assert parsed.kwota == 122.33


def test_parse_netto_ocr_noise_skips_invalid_dates_and_cash_amount() -> None:
    raw_text = """
    Netto Indygo Sp. z 0.0
    Motaniec 30,73-108Kobylanka
    Sklep nr 4666
    19-500 Goldap.Ul.Wolnosci 2
    N1P526-10-37-737
    2026-05-27Sr
    PARAGON FISKALNY
    Suma PLN
    16:28
    HPLATA GOTOWKA
    600.00
    Do zaptaty:
    463.63
    136.37
    Reszta.PLN
    4666/26/05/27/1/554
    NUMER SYSTEMOWY
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/netto.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.sprzedawca == "Netto Indygo Sp. z 0.0"
    assert parsed.nip == "5261037737"
    assert parsed.data_dokumentu == "2026-05-27"
    assert parsed.kwota == 463.63


def test_parse_a4_invoice_ignores_long_product_codes_as_money() -> None:
    raw_text = """
    FAKTURA
    Numer5919/F/833/26
    Data wystawienia27-05-202621:46
    Data sprzedazy:27-05-2026
    Sprzedawca:
    MOLPolska sp.Z0.0
    NIP:583-10-23182
    Nabywca:
    TK SPOKA Z OGRANICZONA ODPOWEDZIALNOSCIA
    NIP:8471628972
    Wart.Brutto
    BEVDselCN2102011.2710194401.00001t6.56
    BEVODs10211.2710194401470001r6.57
    Wart.Brutto
    8%
    284.08
    22.73
    306.81
    SUMA:
    PLN306.81
    27-05-202621:46
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/mol.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.kwota == 306.81
    assert parsed.kwota < 1_000_000


def test_parse_bar_receipt_does_not_choose_plac_address_as_seller() -> None:
    raw_text = """
    BAR U HUBERTA
    HUBERT JANKOWSK!
    PLAC WOLNOSC1 24 24
    LUBIEN KUJAWSKI
    87-840 LUB1EN KUJAWSKI
    NIP: 8883005335
    PARAGON FISKALNY
    1x795.00
    795.00 B
    SUMA:
    795.00
    30-05-2026 12:30
    """
    draft = ReceiptDraft.empty("abc", 1, "/tmp/bar.jpg")
    parsed = parse_receipt_text(raw_text, draft)

    assert parsed.sprzedawca == "BAR U HUBERTA"
    assert parsed.nip == "8883005335"
    assert parsed.data_dokumentu == "2026-05-30"
