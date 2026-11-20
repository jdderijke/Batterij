"""Tests voor de uitlegteksten achter de vraagtekens in de app.

Waarom dit bestaat:
    Elk invoerveld en elke uitkomst in de app hoort uitleg te hebben. Een
    ontbrekende tekst valt in de app pas op als iemand toevallig dat veld in
    beeld heeft, en sommige velden verschijnen alleen bij een bepaalde keuze
    (de piekgrens alleen bij piek shaving). Deze tests lopen daarom de
    broncode van ``app.py`` na in plaats van de app te starten: zo worden ook
    de velden gevonden die bij de standaardinstelling verborgen zijn.

    Afgewezen: ``app.py`` importeren en de schermopbouw uitvoeren. Het bestand
    start bij import de hele app en heeft daarvoor een Streamlit-sessie nodig.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from batsim import config
from uitleg import UITKOMSTEN, VELDEN, bij_uitkomst, bij_veld

APP = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")

# In ``app.py`` heeft elk onderdeel van de Config een vaste korte naam. Deze
# tabel vertaalt die naam naar de klasse, zodat uit een aanroep als
# ``getal(k1, b, "capaciteit_kwh", ...)`` de sleutel ``Batterij.capaciteit_kwh``
# volgt. Komt er in de app een onderdeel bij, dan hoort het ook hier.
VARIABELEN = {
    "alg": "Algemeen",
    "a": "Aansluiting",
    "h": "Huis",
    "w": "Warmtepomp",
    "z": "Zon",
    "b": "Batterij",
    "au": "Auto",
    "nc": "Netcongestie",
    "t": "Tarieven",
    "i": "Investering",
}


def _velden_in_app() -> list[str]:
    """Zoekt alle invoervelden op die ``app.py`` met een hulpfunctie toont.

    De hulpfuncties ``getal``, ``keuze`` en ``schakelaar`` krijgen altijd eerst
    de plek op het scherm, dan het onderdeel van de Config en dan de veldnaam.
    """
    patroon = re.compile(r"\b(?:getal|keuze|schakelaar)\(\s*\w+,\s*(\w+),\s*\"(\w+)\"")
    return [f"{VARIABELEN[variabele]}.{veld}" for variabele, veld in patroon.findall(APP)]


def test_app_gebruikt_de_hulpfuncties():
    """De zoekactie hierboven vindt echt velden; anders bewijzen de andere tests niets."""
    assert len(_velden_in_app()) > 80


@pytest.mark.parametrize("sleutel", sorted(set(_velden_in_app())))
def test_elk_invoerveld_heeft_uitleg(sleutel):
    """Elk veld dat de app toont, heeft een tekst achter zijn vraagteken."""
    assert sleutel in VELDEN


def test_letterlijke_sleutels_in_app_bestaan():
    """Sleutels die ``app.py`` zelf uitschrijft (tabelkolommen, uitkomsten) bestaan.

    De investeringsposten worden in de app met ``inv_`` plus de sleutel van de
    post samengesteld en staan dus niet letterlijk in de broncode; die worden
    hier apart nagelopen.
    """
    for sleutel in re.findall(r"bij_veld\(\"([\w.]+)\"\)", APP):
        assert sleutel in VELDEN, sleutel
    for sleutel in re.findall(r"bij_uitkomst\(\"(\w+)\"\)", APP):
        assert sleutel in UITKOMSTEN, sleutel
    for post in ("panelen", "pv_omvormers", "batterij_omvormers", "hybride_omvormers", "batterijen", "totaal"):
        assert f"inv_{post}" in UITKOMSTEN, post


def test_uitleg_verwijst_naar_bestaande_velden():
    """Een tikfout in een sleutel zou een tekst opleveren die nergens bij hoort.

    ``Scenario`` is geen onderdeel van de Config: dat zijn de invoervelden van
    het tabblad Scenario's.
    """
    for sleutel in VELDEN:
        klasse, veld = sleutel.split(".")
        if klasse == "Scenario":
            continue
        namen = {f.name for f in dataclasses.fields(getattr(config, klasse))}
        assert veld in namen, sleutel


def test_elke_uitleg_heeft_de_vaste_opbouw():
    """Elke tekst beantwoordt de drie vaste vragen, en geen ervan is afgeraffeld."""
    for sleutel, tekst in VELDEN.items():
        for kop in ("**Wat is het?**", "**Wat vul je in?**", "**Waar heeft het invloed op?**"):
            assert kop in tekst, sleutel
        assert len(tekst) > 200, sleutel
    for sleutel, tekst in UITKOMSTEN.items():
        for kop in ("**Wat is het?**", "**Eenheid en periode:**", "**Hoe lees je het?**"):
            assert kop in tekst, sleutel
        assert len(tekst) > 200, sleutel


def test_onbekende_sleutel_geeft_een_foutmelding():
    """Een veld zonder uitleg mag niet stilletjes een leeg vraagteken geven."""
    with pytest.raises(KeyError):
        bij_veld("Batterij.bestaat_niet")
    with pytest.raises(KeyError):
        bij_uitkomst("bestaat_niet")
