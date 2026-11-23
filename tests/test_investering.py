"""Tests voor de vergelijking met "zonder investering" en voor de getallen van de scenario's.

Waarom dit bestaat:
    Het Overzicht en de scenario's meten alles tegen de installatie zonder
    investering: alleen wat er al is. De investering die daartegenover staat
    is het hele bedrag dat nog moet worden uitgegeven. Deze tests leggen vast
    wat er in die referentie overblijft, en dat een scenario de investering
    van de baseline heeft plus of min zijn verschil.
"""

import pytest

from batsim.resultaat import investering, vergelijk
from batsim.scenario import ALTERNATIEF, BASELINE, maak_variant, vergelijk_scenarios
from batsim.simulatie import voer_uit, zonder_investering

# Dezelfde nagemaakte weken weer en prijzen als de tests van de simulatie.
from test_simulatie import _cfg, _nepdata


def test_zonder_investering_houdt_alleen_wat_er_al_is():
    """Niets in bezit: geen panelen en geen batterij, en er valt niets te betalen."""
    cfg = _cfg()
    kaal = zonder_investering(cfg)
    assert all(veld.aantal_panelen == 0 for veld in kaal.zon.velden)
    assert kaal.batterij.aanwezig is False
    assert investering(kaal)["totaal"] == 0
    # De instelling zelf blijft ongemoeid.
    assert cfg.batterij.aanwezig is True
    assert cfg.zon.velden[0].aantal_panelen > 0


def test_zonder_investering_laat_staan_wat_in_bezit_is():
    """Panelen in bezit blijven liggen; een batterij in bezit blijft met haar eigen grootte."""
    cfg = _cfg(capaciteit_kwh=15.0, in_bezit_kwh=5.0, omvormers_in_bezit=True)
    cfg.zon.velden[0].aantal_panelen = 12
    cfg.zon.velden[0].panelen_in_bezit = 8
    kaal = zonder_investering(cfg)
    assert kaal.zon.velden[0].aantal_panelen == 8
    assert kaal.batterij.aanwezig is True
    assert kaal.batterij.capaciteit_kwh == 5.0
    assert investering(kaal)["totaal"] == 0


def test_batterij_in_bezit_zonder_omvormers_telt_niet_mee():
    """Een batterij zonder omvormer kan niets; zonder investering is ze er dus niet."""
    kaal = zonder_investering(_cfg(in_bezit_kwh=5.0, omvormers_in_bezit=False))
    assert kaal.batterij.aanwezig is False
    assert investering(kaal)["totaal"] == 0


def test_investering_op_het_overzicht_is_de_hele_aanschaf():
    """Tegenover "zonder investering" is de investering alles wat nog gekocht moet worden."""
    weer, prijzen = _nepdata()
    cfg = _cfg()
    uit = voer_uit(cfg, weer, prijzen)
    ref = voer_uit(zonder_investering(cfg), weer, prijzen)
    assert vergelijk(uit, ref)["meerinvestering_eur"] == pytest.approx(uit.kentallen["investering"]["totaal"])


def test_scenario_heeft_de_investering_van_de_baseline_plus_het_verschil():
    """De baseline staat in de tabel met haar eigen getallen; een grotere batterij kost het verschil meer."""
    weer, prijzen = _nepdata()
    cfg = _cfg(capaciteit_kwh=10.0)
    tabel = vergelijk_scenarios(cfg, weer, prijzen, capaciteiten=[20.0])
    baseline = tabel[tabel["Scenario"] == BASELINE].iloc[0]
    scenario = tabel[tabel["Scenario"] == ALTERNATIEF].iloc[0]

    assert baseline["Investering (€)"] == pytest.approx(investering(cfg)["totaal"])
    groter = maak_variant(cfg, 20.0, 1.0, cfg.batterij.topologie, cfg.batterij.koppeling, cfg.batterij.strategie)
    verschil = investering(groter)["totaal"] - investering(cfg)["totaal"]
    assert verschil > 0
    assert scenario["Investering (€)"] == pytest.approx(baseline["Investering (€)"] + verschil)
    # De besparing volgt het verschil in stroomkosten met de baseline.
    assert scenario["Besparing (€/jaar)"] - baseline["Besparing (€/jaar)"] == pytest.approx(
        baseline["Kosten (€/jaar)"] - scenario["Kosten (€/jaar)"]
    )
