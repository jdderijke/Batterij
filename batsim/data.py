"""Historische weer- en prijsdata ophalen en lokaal bewaren.

Waarom dit bestaat:
    De simulatie moet draaien op wat er werkelijk gebeurd is: de temperatuur en
    de zonnestraling van het KNMI en de uurprijzen van de day-ahead-markt. Deze
    module is de enige plek die het netwerk op gaat. Wat ze ophaalt, bewaart ze
    als CSV in de map ``data/``, zodat een volgende run zonder internet en
    zonder wachten werkt.

Bronnen (beide openbaar, zonder aanmelding):
    - KNMI uurgegevens: https://www.daggegevens.knmi.nl/klimatologie/uurgegevens
    - Day-ahead-prijzen Nederland: https://api.energy-charts.info (Fraunhofer ISE)

Onbalansprijzen (alleen voor de strategie "handel op de onbalansmarkt"):
    Die komen van TenneT en zijn de enige data die NIET automatisch wordt
    opgehaald. De oude openbare export van TenneT bestaat niet meer; de nieuwe
    API vraagt een persoonlijke sleutel waarvoor je je moet aanmelden, en de
    downloadpagina zit achter een controle die alleen een mens doorkomt.

    Daarom worden ze MEEGELEVERD: in de map ``onbalans/`` van het project
    staat per jaar het bestand "Settlement prices" zoals het van de
    downloadpagina van TenneT komt, ongewijzigd. Die map zit in git en in het
    Windows-programma (zie ``batterij.spec``). Een nieuw jaar toevoegen is:
    het bestand van dat jaar in die map zetten. Bij het eerste gebruik van
    een jaar wordt het bestand omgezet en, net als weer en prijzen, als CSV in
    ``data/`` bewaard.

    Voor een jaar dat niet is meegeleverd kan de gebruiker zelf een bestand
    inlezen met ``importeer_onbalans``.

    Afgewezen: de bestanden omgezet (twee kolommen, kleiner) meeleveren. De
    ruwe bestanden zijn samen 13 MB, maar ze zijn zo na te lopen tegen de
    bron en een nieuw jaar vraagt geen omzetstap.

    Afgewezen (voorlopig): ophalen via de API van TenneT met een sleutel. Het
    vraagt van elke gebruiker een aanmelding bij TenneT en een plek om de
    sleutel te bewaren.

Alle tijdstempels zijn UTC en wijzen naar het BEGIN van het uur (of, bij de
onbalansprijzen, van het kwartier).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .paden import gebruikersmap, programmamap

# De map met opgehaalde data blijft buiten git: ze is altijd opnieuw op te
# halen. Als script staat ze in de projectmap, als Windows-programma in de
# eigen map van de gebruiker (zie ``paden.py``).
DATA_MAP = gebruikersmap() / "data"

KNMI_URL = "https://www.daggegevens.knmi.nl/klimatologie/uurgegevens"
PRIJS_URL = "https://api.energy-charts.info/price"

# De meegeleverde onbalansprijzen: per jaar het bestand van TenneT, met de
# naam die TenneT eraan geeft (``settlement_prices_<begin>_<eind>...csv``,
# begin en eind in UTC; het eind is 31 december 23:00 van het jaar zelf).
ONBALANS_MAP = programmamap() / "onbalans"
# Waar de bestanden vandaan komen (zie de uitleg bovenaan), voor een jaar dat
# niet is meegeleverd.
ONBALANS_DOWNLOADPAGINA = "https://www.tennet.eu/nl/de-elektriciteitsmarkt/transparantie/downloadpagina-transparantie"

# Een eenvoudige naam voor de client; er gaat geen persoonlijke informatie mee.
_KOPPEN = {"User-Agent": "batsim"}


class OnbalansOntbreekt(RuntimeError):
    """De onbalansprijzen van een jaar zijn nog niet ingelezen.

    Een eigen fout, zodat de app haar kan onderscheiden van een netwerkfout en
    kan uitleggen wat de gebruiker moet doen (een bestand inlezen).
    """


def uren_van_jaar(jaar: int) -> pd.DatetimeIndex:
    """Geeft alle uren van een (UTC-)jaar; dit is het raster van weer en uurprijzen."""
    return pd.date_range(f"{jaar}-01-01", f"{jaar}-12-31 23:00", freq="h", tz="UTC")


def kwartieren_van_jaar(jaar: int) -> pd.DatetimeIndex:
    """Geeft alle kwartieren van een (UTC-)jaar; dit is het raster van de onbalansprijzen."""
    return pd.date_range(f"{jaar}-01-01", f"{jaar}-12-31 23:45", freq="15min", tz="UTC")


def laad_weer(jaar: int, station: int) -> pd.DataFrame:
    """Geeft temperatuur en zonnestraling per uur voor één KNMI-station.

    Args:
        jaar: het kalenderjaar (UTC).
        station: KNMI-stationsnummer, bijvoorbeeld 260 voor De Bilt.

    Returns:
        DataFrame met een UTC-uurindex en de kolommen ``temp_c`` (°C) en
        ``ghi_wm2`` (gemiddelde globale straling in dat uur, W/m²).
    """
    pad = DATA_MAP / f"knmi_{station}_{jaar}.csv"
    if pad.exists():
        return pd.read_csv(pad, index_col=0, parse_dates=True)

    # Het KNMI nummert uren 1..24: uur 1 is 00:00-01:00 UTC. Het hele jaar
    # loopt dus van 1 januari uur 1 tot en met 31 december uur 24.
    antwoord = requests.post(
        KNMI_URL,
        data={
            "stns": str(station),
            "vars": "T:Q",
            "start": f"{jaar}010101",
            "end": f"{jaar}123124",
            "fmt": "json",
        },
        headers=_KOPPEN,
        timeout=120,
    )
    antwoord.raise_for_status()
    rijen = antwoord.json()
    if not rijen:
        raise RuntimeError(f"Het KNMI gaf geen data voor station {station} in {jaar}.")

    ruw = pd.DataFrame(rijen)
    # Begin van het uur = datum + (uurnummer - 1).
    tijd = pd.to_datetime(ruw["date"], utc=True) + pd.to_timedelta(ruw["hour"] - 1, unit="h")
    weer = pd.DataFrame(
        {
            # T staat in tienden van graden.
            "temp_c": pd.to_numeric(ruw["T"], errors="coerce").to_numpy() / 10.0,
            # Q is de straling in J/cm² over het uur. Maal 10.000 (cm² -> m²)
            # en gedeeld door 3600 (s) geeft het gemiddelde vermogen in W/m².
            "ghi_wm2": pd.to_numeric(ruw["Q"], errors="coerce").to_numpy() * 10000.0 / 3600.0,
        },
        index=pd.DatetimeIndex(tijd),
    )
    weer = _op_raster(weer, uren_van_jaar(jaar), jaar)
    weer["ghi_wm2"] = weer["ghi_wm2"].clip(lower=0.0)
    _bewaar(weer, pad)
    return weer


def laad_prijzen(jaar: int) -> pd.DataFrame:
    """Geeft de Nederlandse day-ahead-prijs per uur.

    Returns:
        DataFrame met een UTC-uurindex en de kolom ``prijs_eur_kwh``: de kale
        marktprijs, zonder belasting, opslag of btw.
    """
    pad = DATA_MAP / f"prijzen_nl_{jaar}.csv"
    if pad.exists():
        return pd.read_csv(pad, index_col=0, parse_dates=True)

    # Een dag extra aan beide kanten: de dienst rekent in lokale tijd, en zo
    # is het UTC-jaar zeker helemaal gedekt.
    antwoord = requests.get(
        PRIJS_URL,
        params={"bzn": "NL", "start": f"{jaar - 1}-12-31", "end": f"{jaar + 1}-01-01"},
        headers=_KOPPEN,
        timeout=120,
    )
    antwoord.raise_for_status()
    inhoud = antwoord.json()
    if not inhoud.get("unix_seconds"):
        raise RuntimeError(f"Geen day-ahead-prijzen gevonden voor {jaar}.")

    reeks = pd.Series(
        pd.to_numeric(pd.Series(inhoud["price"]), errors="coerce").to_numpy() / 1000.0,  # EUR/MWh -> EUR/kWh
        index=pd.to_datetime(inhoud["unix_seconds"], unit="s", utc=True),
    )
    # Sinds oktober 2025 zijn de prijzen per kwartier. De simulatie rekent met
    # uurprijzen (zo rekenen dynamische contracten voor consumenten ook af),
    # dus kwartieren worden per uur gemiddeld.
    per_uur = reeks.resample("h").mean()
    prijzen = _op_raster(pd.DataFrame({"prijs_eur_kwh": per_uur}), uren_van_jaar(jaar), jaar)
    _bewaar(prijzen, pad)
    return prijzen


def onbalans_pad(jaar: int) -> Path:
    """Geeft het pad waar de ingelezen onbalansprijzen van ``jaar`` bewaard worden."""
    return DATA_MAP / f"onbalans_nl_{jaar}.csv"


def _meegeleverd_onbalans(jaar: int) -> Path | None:
    """Zoekt het meegeleverde TenneT-bestand van ``jaar``, of geeft ``None``.

    Het jaar staat in de bestandsnaam als einddatum (31 december van dat
    jaar); de rest van de naam verschilt per export (soms met ``_CET``
    erachter) en doet er niet toe.
    """
    gevonden = sorted(ONBALANS_MAP.glob(f"settlement_prices_*_{jaar}1231*.csv"))
    return gevonden[0] if gevonden else None


def onbalans_beschikbaar(jaar: int) -> bool:
    """Zegt of er onbalansprijzen voor ``jaar`` zijn: meegeleverd of zelf ingelezen."""
    return onbalans_pad(jaar).exists() or _meegeleverd_onbalans(jaar) is not None


def laad_onbalans(jaar: int) -> pd.DataFrame:
    """Geeft de Nederlandse onbalansprijzen per kwartier.

    Anders dan weer en uurprijzen haalt deze functie niets op: de prijzen
    komen uit het meegeleverde bestand van TenneT, of uit een bestand dat de
    gebruiker zelf heeft ingelezen (zie de uitleg bovenaan deze module). Wat
    de gebruiker zelf inlas, gaat voor.

    Returns:
        DataFrame met een UTC-kwartierindex en twee kolommen, beide de kale
        prijs in euro per kWh zonder belasting, opslag of btw:
        ``afnemen_eur_kwh`` (wat een kWh uit het net in dat kwartier kost) en
        ``invoeden_eur_kwh`` (wat een kWh aan het net oplevert). Meestal zijn
        ze gelijk; in kwartieren waarin TenneT zowel op- als afregelt
        verschillen ze.

    Raises:
        OnbalansOntbreekt: als er voor dit jaar geen prijzen zijn.
    """
    pad = onbalans_pad(jaar)
    if pad.exists():
        return pd.read_csv(pad, index_col=0, parse_dates=True)
    meegeleverd = _meegeleverd_onbalans(jaar)
    if meegeleverd is not None:
        # Eerste gebruik van dit jaar: omzetten en bewaren, zodat het de
        # volgende keer meteen klaarstaat.
        return importeer_onbalans(meegeleverd, jaar)
    raise OnbalansOntbreekt(
        f"Voor {jaar} zijn geen onbalansprijzen meegeleverd. Kies een ander jaar, of download bij TenneT het "
        f"bestand 'Settlement prices' van {jaar} als CSV ({ONBALANS_DOWNLOADPAGINA}) en lees het in bij "
        "Instellingen, Batterij en omvormers."
    )


def importeer_onbalans(bestand: Path, jaar: int) -> pd.DataFrame:
    """Leest een CSV met verrekenprijzen van TenneT in en bewaart ze voor ``jaar``.

    Waarom zo:
        Het bestand komt van de downloadpagina van TenneT ("Settlement
        prices", per jaar, CSV); zowel de meegeleverde bestanden als een
        bestand van de gebruiker gaan hierdoor. De kolommen worden op naam
        gezocht en niet op positie, en het scheidingsteken wordt uit het
        bestand afgeleid: de bestanden tot en met 2024 gebruiken een
        puntkomma, dat van 2025 een komma.

        De tijd van een kwartier volgt uit de datum en het volgnummer van het
        kwartier op die dag (de kolom ``Isp``, 1 tot en met 96), niet uit de
        kloktijd. Het bestand staat in lokale tijd; op de dag dat de klok
        teruggaat komt het uur van 2 tot 3 twee keer voor en is de kloktijd
        dubbelzinnig, het volgnummer niet (die dag heeft 100 kwartieren).

    Args:
        bestand: het gedownloade CSV-bestand.
        jaar: het kalenderjaar waarvoor de prijzen bedoeld zijn.

    Returns:
        Dezelfde tabel als ``laad_onbalans``.

    Raises:
        ValueError: als de verwachte kolommen ontbreken.
        RuntimeError: als het bestand het jaar grotendeels niet dekt
            (bijvoorbeeld het bestand van een ander jaar).
    """
    # ``sep=None`` laat pandas zelf het scheidingsteken bepalen (komma of
    # puntkomma); alles als tekst lezen houdt de decimalen in eigen hand.
    ruw = pd.read_csv(bestand, sep=None, engine="python", dtype=str, encoding="utf-8-sig")

    def zoek(deel: str) -> str | None:
        """Geeft de eerste kolom waarvan de naam ``deel`` bevat (hoofdletters doen er niet toe)."""
        for kolom in ruw.columns:
            if deel in str(kolom).lower():
                return kolom
        return None

    # "Price Shortage" is de prijs bij een tekort (afnemen), "Price Surplus"
    # die bij een overschot (invoeden).
    tekort, overschot, begin, volgnummer = zoek("shortage"), zoek("surplus"), zoek("start"), zoek("isp")
    if tekort is None or overschot is None or begin is None:
        raise ValueError(
            "Dit lijkt geen bestand met verrekenprijzen van TenneT: er is een kolom nodig met 'Shortage', een met "
            f"'Surplus' en een met de begintijd ('Start'). Gevonden kolommen: {', '.join(map(str, ruw.columns))}."
        )

    def getal(kolom: str) -> np.ndarray:
        """Zet een tekstkolom om in getallen; een decimale komma mag ook."""
        return pd.to_numeric(ruw[kolom].str.strip().str.replace(",", ".", regex=False), errors="coerce").to_numpy()

    tijd = pd.to_datetime(ruw[begin].str.strip(), errors="coerce")
    if tijd.dt.tz is not None:
        # De tijd staat er met tijdzone bij: dan is ze ondubbelzinnig.
        tijd_utc = tijd.dt.tz_convert("UTC")
    elif volgnummer is not None:
        # Lokale tijd: datum plus volgnummer van het kwartier (zie hierboven).
        # Middernacht is in Nederland nooit dubbelzinnig; de klok verspringt
        # om 2 of 3 uur.
        middernacht = tijd.dt.normalize().dt.tz_localize("Europe/Amsterdam").dt.tz_convert("UTC")
        tijd_utc = middernacht + pd.to_timedelta((getal(volgnummer) - 1) * 15, unit="min")
    else:
        # Geen volgnummer: dan moet de kloktijd het doen. Het dubbele uur in
        # de herfst wordt uit de volgorde van de rijen afgeleid.
        tijd_utc = tijd.dt.tz_localize("Europe/Amsterdam", ambiguous="infer", nonexistent="shift_forward").dt.tz_convert("UTC")

    tabel = pd.DataFrame(
        {
            # EUR/MWh -> EUR/kWh
            "afnemen_eur_kwh": getal(tekort) / 1000.0,
            "invoeden_eur_kwh": getal(overschot) / 1000.0,
        },
        index=pd.DatetimeIndex(tijd_utc),
    )
    tabel = tabel[tabel.index.notna()].sort_index()
    # Het bestand loopt over het jaar in lokale tijd en mist daardoor het
    # laatste uur van het UTC-jaar; ``_op_raster`` vult dat uit de buren.
    tabel = _op_raster(tabel, kwartieren_van_jaar(jaar), jaar)
    _bewaar(tabel, onbalans_pad(jaar))
    return tabel


def _op_raster(tabel: pd.DataFrame, raster: pd.DatetimeIndex, jaar: int) -> pd.DataFrame:
    """Legt een tabel op het vaste raster van het jaar en vult gaten.

    Eén functie voor het uurraster (weer, uurprijzen) en het kwartierraster
    (onbalansprijzen); alleen het raster verschilt.

    Een ontbrekend tijdvak (storing bij de bron) wordt lineair ingevuld uit de
    buren. Dat is voor een enkel uur onschuldig; een jaar dat grotendeels
    ontbreekt wordt geweigerd, want dan zou de simulatie op verzonnen data
    draaien.
    """
    tabel = tabel[~tabel.index.duplicated(keep="first")].reindex(raster)
    ontbreekt = float(tabel.isna().any(axis=1).mean())
    if ontbreekt > 0.05:
        raise RuntimeError(
            f"Voor {jaar} ontbreekt {ontbreekt:.0%} van de data; dit jaar is niet bruikbaar."
        )
    tabel = tabel.interpolate(limit_direction="both")
    tabel.index.name = "tijd_utc"
    return tabel


def _bewaar(tabel: pd.DataFrame, pad: Path) -> None:
    """Schrijft een tabel als CSV; de map wordt bij de eerste keer aangemaakt."""
    pad.parent.mkdir(parents=True, exist_ok=True)
    tabel.to_csv(pad)


def kwartier_naar_tijdstap(waarden: np.ndarray, stap_min: int) -> np.ndarray:
    """Zet een reeks kwartierprijzen om naar de tijdstap van de simulatie.

    Waarom een eigen functie naast ``naar_tijdstap``:
        Die gaat uit van uurwaarden en een heel aantal stappen per uur. Een
        kwartier past niet op elke tijdstap: 10 minuten deelt een kwartier
        niet, en 30 of 60 minuten zijn langer dan een kwartier. Daarom gaat
        het hier via minuten: elke kwartierprijs geldt 15 minuten lang, en een
        stap krijgt het gemiddelde van zijn minuten. Bij stappen van 1, 5 en
        15 minuten houdt elk kwartier zo precies zijn eigen prijs; bij 10, 30
        en 60 minuten worden prijzen gemiddeld en vlakken de uitschieters af.

    Args:
        waarden: één prijs per kwartier.
        stap_min: de tijdstap van de simulatie in minuten (deelt een uur).

    Returns:
        Een reeks met ``len(waarden) * 15 / stap_min`` waarden.
    """
    per_minuut = np.repeat(np.asarray(waarden, dtype=float), 15)
    return per_minuut.reshape(-1, stap_min).mean(axis=1)


def naar_tijdstap(waarden: np.ndarray, stappen_per_uur: int, vloeiend: bool) -> np.ndarray:
    """Zet een reeks uurwaarden om naar de tijdstap van de simulatie.

    Args:
        waarden: één waarde per uur.
        stappen_per_uur: hoeveel simulatiestappen er in een uur gaan.
        vloeiend: True voor grootheden die geleidelijk verlopen (temperatuur,
            straling): er wordt lineair tussen de uurmiddens gerekend. False
            voor grootheden die per uur vastliggen (prijzen): elk uur houdt
            zijn waarde.

    Returns:
        Een reeks met ``len(waarden) * stappen_per_uur`` waarden.
    """
    waarden = np.asarray(waarden, dtype=float)
    if not vloeiend or stappen_per_uur == 1:
        return np.repeat(waarden, stappen_per_uur)
    # De uurwaarde geldt als gemiddelde van het uur en hoort dus bij het
    # midden ervan; de stappen liggen daar op gelijke afstand tussen.
    uur_midden = np.arange(len(waarden)) + 0.5
    stap_midden = (np.arange(len(waarden) * stappen_per_uur) + 0.5) / stappen_per_uur
    return np.interp(stap_midden, uur_midden, waarden)
