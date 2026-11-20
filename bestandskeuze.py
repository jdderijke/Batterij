"""De Windows-vensters "Openen" en "Opslaan als" voor de app.

Waarom dit bestaat:
    De app draait in de browser, en een browser geeft een webpagina nooit het
    pad van een bestand: uploaden levert alleen de inhoud, downloaden gaat
    altijd naar de map Downloads onder een nieuwe naam. "Opslaan in hetzelfde
    bestand als waaruit geladen is" kan zo niet. De app zelf draait echter als
    gewoon programma op dezelfde computer en mag wel bij de schijf. Deze module
    laat dat programma de vertrouwde vensters van Windows tonen; die geven een
    echt pad terug, waar de app daarna zelf leest en schrijft.

    Afgewezen: ``tkinter.filedialog``. Tkinter mag alleen vanuit de hoofddraad
    gebruikt worden en Streamlit voert de app in een andere draad uit; het zit
    bovendien bewust niet in het Windows-programma (zie ``batterij.spec``).
    De vensters van Windows zelf werken vanuit elke draad en vragen niets
    extra's in het programma.

    Afgewezen: een eigen lijst met bewaarde varianten in de app, zonder
    vensters. Eenvoudiger, maar dan bepaalt de app waar de bestanden staan en
    is een bestand van iemand anders niet zomaar te openen.

Beperking:
    Alleen Windows. Op een ander systeem geven de functies een
    ``NotImplementedError``; de app toont die als melding. Het venster
    verschijnt op de computer waar de app draait. Dat is de bedoeling: het
    Windows-programma is alleen vanaf de eigen computer te bereiken.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Welke bestanden de vensters tonen: paren van omschrijving en patroon,
# gescheiden door nultekens, zoals Windows het vraagt.
_FILTER = "Instellingen (*.json)\0*.json\0Alle bestanden (*.*)\0*.*\0"
# Windows-paden kunnen tot 32.767 tekens lang zijn.
_MAX_PAD = 32768

# Vlaggen van het venster (namen uit de Windows-documentatie, OFN_...).
_VERBERG_ALLEEN_LEZEN = 0x00000004
# Windows verplaatst anders de werkmap van het hele programma naar de gekozen
# map. Streamlit zoekt zijn instellingen in de werkmap; die moet blijven staan.
_WERKMAP_LATEN_STAAN = 0x00000008
_VRAAG_BIJ_OVERSCHRIJVEN = 0x00000002
_MAP_MOET_BESTAAN = 0x00000800
_BESTAND_MOET_BESTAAN = 0x00001000
_MODERN_VENSTER = 0x00080000


def _venster(opslaan: bool, titel: str, beginmap: Path | None, naam: str) -> Path | None:
    """Toont het venster van Windows en geeft het gekozen pad, of ``None`` bij annuleren.

    Args:
        opslaan: ``True`` voor "Opslaan als", ``False`` voor "Openen".
        titel: tekst in de titelbalk.
        beginmap: map waarin het venster opent; ``None`` laat Windows kiezen
            (de laatst gebruikte map).
        naam: bestandsnaam die alvast is ingevuld.
    """
    if sys.platform != "win32":
        raise NotImplementedError("Bestanden kiezen kan alleen op Windows.")

    # Pas hier importeren: op een ander systeem bestaan deze onderdelen niet.
    import ctypes
    from ctypes import wintypes

    class Invoer(ctypes.Structure):
        """De structuur OPENFILENAMEW; volgorde en typen liggen vast in Windows."""

        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    # Het filter bevat nultekens en kan daardoor niet als gewone tekst worden
    # doorgegeven; een buffer kan dat wel. In dezelfde soort buffer schrijft
    # Windows het gekozen pad terug.
    filterbuffer = ctypes.create_unicode_buffer(_FILTER + "\0")
    padbuffer = ctypes.create_unicode_buffer(naam, _MAX_PAD)

    invoer = Invoer()
    invoer.lStructSize = ctypes.sizeof(Invoer)
    # Het venster hoort bij het venster dat nu vooraan staat: de browser waarin
    # net op de knop is geklikt. Zonder eigenaar opent het venster geregeld
    # ACHTER de browser en lijkt de app te hangen.
    invoer.hwndOwner = ctypes.windll.user32.GetForegroundWindow()
    invoer.lpstrFilter = ctypes.cast(filterbuffer, wintypes.LPCWSTR)
    invoer.nFilterIndex = 1
    invoer.lpstrFile = ctypes.cast(padbuffer, wintypes.LPWSTR)
    invoer.nMaxFile = _MAX_PAD
    invoer.lpstrInitialDir = str(beginmap) if beginmap else None
    invoer.lpstrTitle = titel
    # Wie een naam zonder extensie typt, krijgt er .json achter.
    invoer.lpstrDefExt = "json"
    invoer.Flags = _MODERN_VENSTER | _WERKMAP_LATEN_STAAN | _VERBERG_ALLEEN_LEZEN | _MAP_MOET_BESTAAN
    invoer.Flags |= _VRAAG_BIJ_OVERSCHRIJVEN if opslaan else _BESTAND_MOET_BESTAAN

    # Het venster gebruikt onderdelen van de Windows-verkenner en die
    # verwachten dat de draad zich eerst aanmeldt (COM, "apartment"). De
    # hoofddraad van een gewoon programma doet dat vanzelf; de draad waarin
    # Streamlit de app uitvoert niet.
    ole32 = ctypes.windll.ole32
    aangemeld = ole32.CoInitializeEx(None, 0x2) >= 0
    try:
        functie = ctypes.windll.comdlg32.GetSaveFileNameW if opslaan else ctypes.windll.comdlg32.GetOpenFileNameW
        gekozen = functie(ctypes.byref(invoer))
    finally:
        if aangemeld:
            ole32.CoUninitialize()
    # Nul betekent: geannuleerd (of het venster kon niet getoond worden). In
    # beide gevallen is er niets gekozen.
    return Path(padbuffer.value) if gekozen else None


def kies_om_te_openen(beginmap: Path | None = None) -> Path | None:
    """Laat de gebruiker een bestaand instellingenbestand kiezen.

    Returns:
        Het gekozen pad, of ``None`` als de gebruiker annuleert.

    Raises:
        NotImplementedError: op een ander systeem dan Windows.
    """
    return _venster(False, "Instellingen laden", beginmap, "")


def kies_om_op_te_slaan(beginmap: Path | None = None, naam: str = "batterij-instellingen.json") -> Path | None:
    """Laat de gebruiker kiezen waar de instellingen bewaard worden.

    Bestaat het bestand al, dan vraagt Windows zelf of het overschreven mag
    worden.

    Returns:
        Het gekozen pad, of ``None`` als de gebruiker annuleert.

    Raises:
        NotImplementedError: op een ander systeem dan Windows.
    """
    return _venster(True, "Instellingen opslaan als", beginmap, naam)
