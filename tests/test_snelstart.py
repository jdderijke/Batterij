"""Tests voor de snelstart: van gewone antwoorden naar instellingen.

Waarom deze tests:
    De snelstart overschrijft instellingen. Dat mag alleen gebeuren waar de
    gebruiker het vooraf te zien krijgt. Deze tests bewaken daarom vooral de
    afspraken eromheen: ongewijzigd toepassen verandert niets, er wordt niets
    gewijzigd buiten de lijst die de app toont, en een afgewezen wijziging
    blijft ook echt achterwege.
"""

from __future__ import annotations

import dataclasses

import pytest

from batsim.config import Config, ZonneVeld
from batsim.snelstart import AFGELEIDE_VELDEN, Snelstart, leid_af, pas_toe, wijzigingen


def test_standaardantwoorden_horen_bij_de_standaardinstelling():
    """De beginwaarden van ``Snelstart`` zijn geen tweede, losse set standaarden."""
    assert Snelstart.uit_config(Config()) == Snelstart()


def test_ongewijzigd_toepassen_laat_de_standaardinstelling_bijna_heel():
    """Alleen het vermogen van de warmtepomp wordt opnieuw uitgerekend.

    De standaardinstelling heeft een ruim gekozen warmtepomp van 8 kW; de
    snelstart rekent voor hetzelfde huis een kleinere uit. Dat ene verschil is
    bedoeld: het laat zien dat het vermogen uit het huis volgt.
    """
    cfg = Config()
    verschillen = wijzigingen(cfg, leid_af(Snelstart.uit_config(cfg), cfg))
    assert [(w.onderdeel, w.veld) for w in verschillen] == [("warmtepomp", "thermisch_vermogen_kw")]


# Een paar uiteenlopende huishoudens; samen raken ze elke keuzelijst.
ANTWOORDEN = [
    Snelstart(),
    Snelstart(
        jaar=2023,
        knmi_station=280,
        woningtype="vrijstaand",
        bouwjaar=1962,
        na_isolatie="grondig",
        bouwmateriaal="beton",
        vloeren="beton",
        glas="dubbel",
        oppervlak_m2=210.0,
        wtw=False,
        personen=2,
        afgifte="radiatoren",
        panelen=25,
        richting="oost_west",
        panelen_in_bezit=True,
        netcongestie=True,
        batterij_kwh=10.0,
        strategie="handel",
        km_per_jaar=12000,
        contract="vast",
    ),
    Snelstart(
        woningtype="appartement",
        bouwjaar=2022,
        bouwmateriaal="houtskelet",
        glas="triple",
        oppervlak_m2=75.0,
        wtw=True,
        personen=1,
        warmtepomp=False,
        zonnepanelen=False,
        batterij=False,
        # Antwoorden bij een onderdeel dat uitstaat tellen niet mee.
        batterij_kwh=40.0,
        strategie="onbalans",
        auto=False,
    ),
    Snelstart(woningtype="tussenwoning", bouwjaar=1984, na_isolatie="deels", glas="enkel", afgifte="lt_radiatoren", richting="zuidwest"),
]


@pytest.mark.parametrize("antwoorden", ANTWOORDEN)
def test_twee_keer_toepassen_verandert_de_tweede_keer_niets(antwoorden):
    """Wat de snelstart heeft ingesteld, leest ze ook weer terug als dezelfde antwoorden.

    Zonder deze eigenschap zou het venster na een snelstart openen met een
    lijst wijzigingen, terwijl de gebruiker niets heeft aangeraakt.
    """
    cfg = leid_af(antwoorden, Config())
    opnieuw = Snelstart.uit_config(cfg)
    assert wijzigingen(cfg, leid_af(opnieuw, cfg)) == []


@pytest.mark.parametrize("antwoorden", ANTWOORDEN)
def test_er_verandert_niets_buiten_de_getoonde_velden(antwoorden):
    """``AFGELEIDE_VELDEN`` is de volledige lijst; de waarschuwing in de app slaat niets over."""
    oud = Config()
    nieuw = leid_af(antwoorden, oud)
    voor, na = oud.naar_dict(), nieuw.naar_dict()
    for onderdeel, veld in AFGELEIDE_VELDEN:
        del voor[onderdeel][veld]
        del na[onderdeel][veld]
    assert voor == na


def test_leid_af_laat_de_huidige_instelling_ongemoeid():
    """De app zet oud en nieuw naast elkaar; oud mag dus niet meeveranderen."""
    cfg = Config()
    voor = cfg.naar_json()
    leid_af(ANTWOORDEN[1], cfg)
    assert cfg.naar_json() == voor


def test_kentallen_volgen_de_antwoorden():
    """Een oud, groot en na-geïsoleerd huis met gewone radiatoren."""
    cfg = leid_af(ANTWOORDEN[1], Config())
    assert cfg.huis.schilfactor == 2.5
    # Grondig na-geïsoleerd tilt een huis uit 1962 naar Rc 3,5, maar de kieren
    # blijven die van het bouwjaar.
    assert cfg.huis.rc_waarde == 3.5
    assert cfg.huis.ventilatievoud == 1.0
    assert cfg.huis.u_raam == 2.9
    assert cfg.huis.raamoppervlak_m2 == 35.0
    assert cfg.huis.warmtecapaciteit_wh_m2k == 150.0
    assert cfg.warmtepomp.aanvoertemperatuur_c == 55.0
    assert cfg.warmtepomp.cop_nominaal == 3.0
    assert cfg.tarieven.contract == "vast"
    assert (cfg.batterij.capaciteit_kwh, cfg.batterij.strategie) == (10.0, "handel")
    # Oost en west: twee velden, alle panelen verdeeld en in bezit.
    assert [(v.aantal_panelen, v.azimut_graden, v.panelen_in_bezit) for v in cfg.zon.velden] == [(12, 90.0, 12), (13, 270.0, 13)]


def test_slechter_huis_krijgt_een_grotere_warmtepomp():
    """Het vermogen van de warmtepomp volgt uit het warmteverlies van het huis."""
    goed = leid_af(Snelstart(bouwjaar=2020), Config())
    slecht = leid_af(Snelstart(bouwjaar=1960, glas="enkel"), Config())
    assert slecht.warmtepomp.thermisch_vermogen_kw > 2 * goed.warmtepomp.thermisch_vermogen_kw


def test_afwezig_onderdeel_wordt_alleen_uitgezet():
    """Geen warmtepomp, panelen, batterij of auto: de schakelaar gaat uit, de rest blijft bewaard."""
    oud = Config()
    nieuw = leid_af(ANTWOORDEN[2], oud)
    assert not nieuw.warmtepomp.aanwezig and not nieuw.zon.aanwezig and not nieuw.auto.aanwezig
    assert not nieuw.batterij.aanwezig
    assert nieuw.warmtepomp.thermisch_vermogen_kw == oud.warmtepomp.thermisch_vermogen_kw
    assert nieuw.zon.velden == oud.zon.velden
    assert (nieuw.batterij.capaciteit_kwh, nieuw.batterij.strategie) == (oud.batterij.capaciteit_kwh, oud.batterij.strategie)
    assert nieuw.auto.km_werkdag == oud.auto.km_werkdag


def test_netcongestie_volgt_het_antwoord_en_alleen_met_panelen():
    """De vraag hoort bij de panelen: zonder panelen blijft netcongestie zoals het was."""
    aan = leid_af(Snelstart(netcongestie=True), Config())
    assert aan.netcongestie.actief
    # Alleen de schakelaar; de zwaarte van de overspanning en de inzet van de
    # batterij blijven ongemoeid.
    assert not aan.batterij.spanningssteun
    assert leid_af(Snelstart(netcongestie=False), aan).netcongestie.actief is False
    assert leid_af(Snelstart(zonnepanelen=False, netcongestie=False), aan).netcongestie.actief is True


def test_uitgezette_panelen_houden_hun_aantal_in_het_venster():
    """Wie de panelen uitzet en het venster heropent, ziet zijn eigen aantal terug."""
    cfg = leid_af(Snelstart(zonnepanelen=False), leid_af(Snelstart(panelen=22, richting="west"), Config()))
    terug = Snelstart.uit_config(cfg)
    assert (terug.zonnepanelen, terug.panelen, terug.richting) == (False, 22, "west")


def test_zonneveld_houdt_wat_de_snelstart_niet_vraagt():
    """Vermogen per paneel, helling en fase overleven een snelstart."""
    cfg = Config()
    cfg.zon.velden = [ZonneVeld("Schuur", 8, 375.0, 15.0, 180.0, 2, 0)]
    veld = leid_af(Snelstart(panelen=10, richting="west"), cfg).zon.velden[0]
    assert (veld.aantal_panelen, veld.azimut_graden) == (10, 270.0)
    assert (veld.wp_per_paneel, veld.helling_graden, veld.fase) == (375.0, 15.0, 2)


def test_fijn_afgestelde_waarde_komt_in_de_waarschuwing():
    """Een waarde die tussen twee keuzes in ligt, wordt overschreven en dus gemeld."""
    cfg = Config()
    cfg.huis.rc_waarde = 3.2
    verschillen = {(w.onderdeel, w.veld): w for w in wijzigingen(cfg, leid_af(Snelstart.uit_config(cfg), cfg))}
    melding = verschillen[("huis", "rc_waarde")]
    assert (melding.nu, melding.wordt) == ("3,2", "3,5")


def test_keuzes_staan_als_tekst_in_de_waarschuwing():
    """Een station of strategie staat er met zijn naam, niet met zijn sleutel."""
    cfg = Config()
    verschillen = {(w.onderdeel, w.veld): w for w in wijzigingen(cfg, leid_af(ANTWOORDEN[1], cfg))}
    station = verschillen[("algemeen", "knmi_station")]
    assert (station.nu, station.wordt, station.waarde) == ("De Bilt", "Eelde (Groningen)", 280)
    assert (verschillen[("algemeen", "jaar")].nu, verschillen[("algemeen", "jaar")].wordt) == ("2025", "2023")
    assert verschillen[("batterij", "strategie")].wordt == "Handel op uurprijzen"
    assert verschillen[("tarieven", "contract")].wordt == "Vast tarief"


def test_alleen_gekozen_wijzigingen_worden_doorgevoerd():
    """Wat de gebruiker afwijst, houdt zijn huidige waarde."""
    cfg = Config()
    alle = wijzigingen(cfg, leid_af(ANTWOORDEN[1], cfg))
    gekozen = [w for w in alle if w.onderdeel != "huis"]
    nieuw = pas_toe(cfg, gekozen)
    assert dataclasses.asdict(nieuw.huis) == dataclasses.asdict(cfg.huis)
    assert nieuw.tarieven.contract == "vast"
    assert len(nieuw.zon.velden) == 2
    # Alles overnemen geeft precies de afgeleide instelling.
    assert pas_toe(cfg, alle).naar_dict() == leid_af(ANTWOORDEN[1], cfg).naar_dict()
