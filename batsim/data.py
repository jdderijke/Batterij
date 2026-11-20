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

Alle tijdstempels zijn UTC en wijzen naar het BEGIN van het uur.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .paden import gebruikersmap

# De map met opgehaalde data blijft buiten git: ze is altijd opnieuw op te
# halen. Als script staat ze in de projectmap, als Windows-programma in de
# eigen map van de gebruiker (zie ``paden.py``).
DATA_MAP = gebruikersmap() / "data"

KNMI_URL = "https://www.daggegevens.knmi.nl/klimatologie/uurgegevens"
PRIJS_URL = "https://api.energy-charts.info/price"

# Een eenvoudige naam voor de client; er gaat geen persoonlijke informatie mee.
_KOPPEN = {"User-Agent": "batsim"}


def uren_van_jaar(jaar: int) -> pd.DatetimeIndex:
    """Geeft alle uren van een (UTC-)jaar; dit is het raster van alle data."""
    return pd.date_range(f"{jaar}-01-01", f"{jaar}-12-31 23:00", freq="h", tz="UTC")


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
    weer = _op_uurraster(weer, jaar)
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
    prijzen = _op_uurraster(pd.DataFrame({"prijs_eur_kwh": per_uur}), jaar)
    _bewaar(prijzen, pad)
    return prijzen


def _op_uurraster(tabel: pd.DataFrame, jaar: int) -> pd.DataFrame:
    """Legt een tabel op het vaste uurraster van het jaar en vult gaten.

    Een ontbrekend uur (storing bij de bron) wordt lineair ingevuld uit de
    buren. Dat is voor een enkel uur onschuldig; een jaar dat grotendeels
    ontbreekt wordt geweigerd, want dan zou de simulatie op verzonnen data
    draaien.
    """
    raster = uren_van_jaar(jaar)
    tabel = tabel[~tabel.index.duplicated(keep="first")].reindex(raster)
    ontbreekt = float(tabel.isna().any(axis=1).mean())
    if ontbreekt > 0.05:
        raise RuntimeError(
            f"Voor {jaar} ontbreekt {ontbreekt:.0%} van de uren; dit jaar is niet bruikbaar."
        )
    tabel = tabel.interpolate(limit_direction="both")
    tabel.index.name = "tijd_utc"
    return tabel


def _bewaar(tabel: pd.DataFrame, pad: Path) -> None:
    """Schrijft een tabel als CSV; de map wordt bij de eerste keer aangemaakt."""
    pad.parent.mkdir(parents=True, exist_ok=True)
    tabel.to_csv(pad)


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
