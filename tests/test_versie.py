"""Tests voor de melding van een nieuwe versie.

Waarom dit bestaat:
    De vraag aan GitHub mag de app nooit laten struikelen, en versienummers
    vergelijken gaat als tekst verkeerd ("0.10" is kleiner dan "0.9"). Beide
    worden hier vastgelegd, zonder echt het internet op te gaan.
"""

import requests

from batsim import versie


class _Antwoord:
    """Nagemaakt antwoord van GitHub met alleen het adres waarnaar wordt doorverwezen."""

    def __init__(self, locatie: str | None):
        self.headers = {"Location": locatie} if locatie else {}


def test_versies_worden_als_getallen_vergeleken():
    assert versie.is_nieuwer("0.4.0", "0.3.1")
    assert versie.is_nieuwer("0.10.0", "0.9.0")
    assert not versie.is_nieuwer("0.3.1", "0.3.1")
    assert not versie.is_nieuwer("0.3.0", "0.3.1")


def test_versienummer_komt_uit_het_adres_van_de_release(monkeypatch):
    doel = "https://github.com/jdderijke/Batterij/releases/tag/v0.4.0"
    monkeypatch.setattr(versie.requests, "get", lambda *a, **k: _Antwoord(doel))
    assert versie.nieuwste_versie() == "0.4.0"
    assert versie.beschikbare_update("0.3.1") == "0.4.0"
    # Wie de nieuwste versie al heeft, krijgt geen melding.
    assert versie.beschikbare_update("0.4.0") is None


def test_zonder_internet_is_er_geen_melding_en_geen_fout(monkeypatch):
    def geen_verbinding(*a, **k):
        raise requests.ConnectionError("geen internet")

    monkeypatch.setattr(versie.requests, "get", geen_verbinding)
    assert versie.nieuwste_versie() is None
    assert versie.beschikbare_update("0.3.1") is None


def test_onverwacht_antwoord_geeft_geen_melding(monkeypatch):
    """Geen doorverwijzing (bijvoorbeeld een inlogpagina van een bedrijfsnetwerk)."""
    monkeypatch.setattr(versie.requests, "get", lambda *a, **k: _Antwoord(None))
    assert versie.beschikbare_update("0.3.1") is None
