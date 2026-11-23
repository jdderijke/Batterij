"""Tests voor de scenario's: welke combinaties worden doorgerekend?

Waarom dit bestaat:
    Het tabblad Scenario's zet het aantal scenario's op de knop en rekent ze
    daarna door. De afspraak is: elk scenario is de baseline met een of meer
    onderdelen vervangen door een alternatief. Deze tests leggen die afspraak
    vast op de lijst van combinaties; de simulatie zelf wordt elders getest
    en hier niet gedraaid, zodat de tests snel blijven.
"""

from batsim.config import Config
from batsim.scenario import basiskeuze, combinaties, maak_variant


def _basis() -> Config:
    """Een baseline met panelen en een batterij van 15 kWh."""
    cfg = Config()
    cfg.batterij.aanwezig = True
    cfg.batterij.capaciteit_kwh = 15.0
    cfg.batterij.topologie = "1x3"
    cfg.batterij.koppeling = "ac"
    cfg.batterij.strategie = "eigen_verbruik"
    return cfg


def test_zonder_alternatieven_is_er_niets_te_rekenen():
    """De baseline zelf is al doorgerekend en is geen scenario."""
    assert combinaties(_basis()) == []


def test_alleen_een_andere_strategie_geeft_een_scenario():
    """Het voorbeeld uit de afspraak: de baseline met alleen de strategie vervangen."""
    assert combinaties(_basis(), strategieen=["handel"]) == [(15.0, 1.0, "1x3", "ac", "handel")]


def test_de_waarde_van_de_baseline_in_een_lijst_telt_niet_mee():
    """Factor 1 en de huidige batterijgrootte staan in de standaardlijsten, maar zijn de baseline."""
    lijst = combinaties(_basis(), capaciteiten=[15, 20], paneelfactoren=[1.0, 2.0])
    assert sorted(lijst) == sorted(
        [
            (15.0, 2.0, "1x3", "ac", "eigen_verbruik"),
            (20.0, 1.0, "1x3", "ac", "eigen_verbruik"),
            (20.0, 2.0, "1x3", "ac", "eigen_verbruik"),
        ]
    )


def test_zonder_batterij_tellen_topologie_en_strategie_een_keer():
    """Bij 0 kWh maakt de architectuur niet uit; er is dan één scenario per aantal panelen."""
    lijst = combinaties(_basis(), capaciteiten=[0], strategieen=["handel"], topologieen=["3x1"])
    zonder = [keuze for keuze in lijst if keuze[0] == 0]
    met = [keuze for keuze in lijst if keuze[0] > 0]
    assert len(zonder) == 1
    # Met batterij: 2 topologieën x 2 strategieën, min de baseline zelf.
    assert len(met) == 3


def test_baseline_zonder_batterij_varieert_alleen_de_panelen():
    """Staat de batterij uit, dan telt ze als 0 kWh, ook als er nog een grootte bewaard is."""
    cfg = _basis()
    cfg.batterij.aanwezig = False
    assert basiskeuze(cfg)[0] == 0.0
    lijst = combinaties(cfg, paneelfactoren=[0.5, 1.0, 1.5, 2.0])
    assert [keuze[1] for keuze in lijst] == [0.5, 1.5, 2.0]
    assert all(keuze[0] == 0 for keuze in lijst)
    # De variant blijft zonder batterij.
    assert maak_variant(cfg, *lijst[0]).batterij.aanwezig is False


def test_standaardlijsten_geven_alle_combinaties_behalve_de_baseline():
    """De reeksen die de app voorstelt: 4 aantallen panelen x 6 batterijgroottes, min de baseline."""
    lijst = combinaties(_basis(), capaciteiten=[0, 5, 10, 15, 20, 30], paneelfactoren=[0.5, 1.0, 1.5, 2.0])
    assert len(lijst) == 4 * 6 - 1
