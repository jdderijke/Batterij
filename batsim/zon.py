"""Zonopbrengst van panelen uit de gemeten straling van het KNMI.

Waarom dit bestaat:
    Het KNMI meet de straling op een horizontaal vlak. Een paneel ligt schuin en
    kijkt een kant op, dus de meting moet worden omgerekend. Dat gaat in drie
    stappen, elk een bekende standaardmethode:

    1. Waar staat de zon? (zonnestand uit datum, tijd en plaats)
    2. Hoeveel van de gemeten straling is directe zon en hoeveel is diffuus
       licht van de hemel? (model van Erbs, uit de helderheid van de lucht)
    3. Hoeveel valt daarvan op het schuine paneel, en wat levert het paneel
       daarmee, rekening houdend met de celtemperatuur?

    Afgewezen: een vaste opbrengst per kWp verdeeld over het jaar. Dat geeft
    wel het jaartotaal, maar niet het verschil tussen oost, zuid en west over
    de dag, en juist dat bepaalt hoeveel een batterij te doen heeft.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Zon, ZonneVeld

ZONNECONSTANTE_WM2 = 1361.0
# Deel van het licht dat de grond terugkaatst (gras, bestrating).
ALBEDO = 0.2


def zonnestand(tijd_utc: pd.DatetimeIndex, breedte: float, lengte: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Berekent waar de zon staat op elk tijdstip.

    Args:
        tijd_utc: tijdstippen (het midden van elke simulatiestap), in UTC.
        breedte: breedtegraad in graden noord.
        lengte: lengtegraad in graden oost.

    Returns:
        Drie reeksen: de cosinus van de zenithoek (1 = zon recht boven,
        0 = op de horizon, negatief = onder de horizon), het azimut van de zon
        in radialen (kompasrichting, 0 = noord, pi = zuid) en de straling
        buiten de dampkring op een horizontaal vlak (W/m²).
    """
    dag = tijd_utc.day_of_year.to_numpy(dtype=float)
    uur = tijd_utc.hour.to_numpy() + tijd_utc.minute.to_numpy() / 60.0 + tijd_utc.second.to_numpy() / 3600.0

    # Declinatie: hoe ver de zon ten noorden of zuiden van de evenaar staat.
    declinatie = np.radians(23.45) * np.sin(2 * np.pi * (284 + dag) / 365.0)

    # Tijdsvereffening: het verschil (in minuten) tussen kloktijd en ware
    # zonnetijd, door de scheve aardas en de ellipsvormige baan.
    b = 2 * np.pi * (dag - 1) / 365.0
    vereffening_min = 229.18 * (
        0.000075 + 0.001868 * np.cos(b) - 0.032077 * np.sin(b) - 0.014615 * np.cos(2 * b) - 0.040849 * np.sin(2 * b)
    )
    # Ware zonnetijd ter plaatse: 4 minuten per graad lengte ten opzichte van UTC.
    zonnetijd = uur + lengte / 15.0 + vereffening_min / 60.0
    uurhoek = np.radians(15.0 * (zonnetijd - 12.0))

    phi = np.radians(breedte)
    cos_zenit = np.sin(phi) * np.sin(declinatie) + np.cos(phi) * np.cos(declinatie) * np.cos(uurhoek)

    # Azimut gemeten vanaf het zuiden (west positief), daarna 180° erbij om
    # er een kompasrichting van te maken.
    azimut = np.arctan2(np.sin(uurhoek), np.cos(uurhoek) * np.sin(phi) - np.tan(declinatie) * np.cos(phi)) + np.pi

    # De afstand aarde-zon schommelt 3,3% over het jaar.
    buitenaards = ZONNECONSTANTE_WM2 * (1 + 0.033 * np.cos(2 * np.pi * dag / 365.0)) * np.clip(cos_zenit, 0, None)
    return cos_zenit, azimut, buitenaards


def splits_straling(ghi: np.ndarray, cos_zenit: np.ndarray, buitenaards: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Splitst de gemeten straling in directe zon en diffuus hemellicht (Erbs).

    Hoe helderder de lucht (gemeten straling als deel van wat er buiten de
    dampkring aankomt), hoe groter het aandeel directe zon.

    Returns:
        De directe straling loodrecht op de zonnestralen (DNI) en de diffuse
        straling op een horizontaal vlak (DHI), beide in W/m².
    """
    zon_op = cos_zenit > 0.02
    helderheid = np.where(zon_op, ghi / np.maximum(buitenaards, 1.0), 0.0)
    helderheid = np.clip(helderheid, 0.0, 1.0)

    diffuus_deel = np.where(
        helderheid <= 0.22,
        1.0 - 0.09 * helderheid,
        np.where(
            helderheid <= 0.80,
            0.9511 - 0.1604 * helderheid + 4.388 * helderheid**2 - 16.638 * helderheid**3 + 12.336 * helderheid**4,
            0.165,
        ),
    )
    dhi = diffuus_deel * ghi
    # Vlak boven de horizon deelt dit door bijna nul; de ondergrens van
    # ongeveer 5° zonshoogte en het plafond houden de uitkomst realistisch.
    dni = np.where(zon_op, (ghi - dhi) / np.maximum(cos_zenit, 0.087), 0.0)
    dni = np.clip(dni, 0.0, 1100.0)
    return dni, dhi


def veld_vermogen_dc(
    veld: ZonneVeld,
    zon: Zon,
    ghi: np.ndarray,
    temp_c: np.ndarray,
    cos_zenit: np.ndarray,
    zon_azimut: np.ndarray,
    dni: np.ndarray,
    dhi: np.ndarray,
) -> np.ndarray:
    """Berekent het DC-vermogen (kW) dat één veld panelen levert.

    Returns:
        Het vermogen aan de DC-kant van de panelen, na systeemverlies maar vóór
        de omvormer of MPPT-regelaar. Wat daarna gebeurt hangt af van de
        architectuur en hoort daarom in de simulatie thuis, niet hier.
    """
    helling = np.radians(veld.helling_graden)
    paneel_azimut = np.radians(veld.azimut_graden)
    sin_zenit = np.sqrt(np.clip(1.0 - cos_zenit**2, 0.0, 1.0))

    # Hoek tussen de zonnestralen en de loodlijn op het paneel.
    cos_inval = cos_zenit * np.cos(helling) + sin_zenit * np.sin(helling) * np.cos(zon_azimut - paneel_azimut)

    direct = dni * np.clip(cos_inval, 0.0, None)
    # Diffuus: het paneel ziet het deel van de hemelkoepel dat boven zijn vlak ligt.
    hemel = dhi * (1 + np.cos(helling)) / 2.0
    grond = ghi * ALBEDO * (1 - np.cos(helling)) / 2.0
    op_paneel = direct + hemel + grond

    # Een paneel in de zon wordt warm en levert dan minder. NOCT is de
    # celtemperatuur bij 800 W/m² en 20 °C buiten; daaruit volgt de opwarming.
    cel_temp = temp_c + op_paneel * (zon.noct_c - 20.0) / 800.0
    temperatuurfactor = 1.0 + zon.temperatuurcoefficient * (cel_temp - 25.0)

    piek_kw = veld.aantal_panelen * veld.wp_per_paneel / 1000.0
    vermogen = piek_kw * op_paneel / 1000.0 * temperatuurfactor * (1.0 - zon.systeemverlies)
    return np.clip(vermogen, 0.0, None)


def piekvermogen_kwp(zon: Zon) -> float:
    """Geeft het totale piekvermogen van alle velden in kWp (nul als er geen panelen zijn)."""
    if not zon.aanwezig:
        return 0.0
    return sum(v.aantal_panelen * v.wp_per_paneel for v in zon.velden) / 1000.0


def nieuw_piekvermogen_kwp(zon: Zon) -> float:
    """Geeft het piekvermogen van de panelen die er nog bij moeten komen, in kWp.

    Per veld tellen alleen de panelen boven het aantal dat al in bezit is. Een
    veld met meer panelen in bezit dan er nu ingesteld staan, telt als nul:
    weghalen levert geen geld op.
    """
    if not zon.aanwezig:
        return 0.0
    return sum(max(v.aantal_panelen - v.panelen_in_bezit, 0) * v.wp_per_paneel for v in zon.velden) / 1000.0
