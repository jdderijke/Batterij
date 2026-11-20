"""Tests van de rekenkern.

Waarom deze tests:
    De simulatie is alleen iets waard als de energie klopt. Deze tests draaien
    op een klein stuk verzonnen weer (geen netwerk nodig) en controleren de
    eigenschappen die in elk scenario moeten gelden: er verdwijnt geen energie,
    de batterij blijft binnen haar grenzen, en de architecturen gedragen zich
    zoals het ontwerp zegt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from batsim.config import Config
from batsim.huis import warmteverlies_w_per_k
from batsim.resultaat import in_bezit, investering
from batsim.simulatie import plan_handel, voer_uit, zonder_batterij


def _nepdata(dagen: int = 14, zomer: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Maakt een paar weken weer en prijzen met een herkenbaar dagritme."""
    begin = "2025-06-01" if zomer else "2025-01-06"
    uren = pd.date_range(begin, periods=dagen * 24, freq="h", tz="UTC")
    uur = uren.hour.to_numpy()
    # Zon tussen 4 en 18 uur UTC, als een halve sinus.
    zon = np.clip(np.sin((uur - 4) / 14 * np.pi), 0, None) * (750.0 if zomer else 150.0)
    temp = (18.0 if zomer else 2.0) + 5.0 * np.sin((uur - 8) / 24 * 2 * np.pi)
    weer = pd.DataFrame({"temp_c": temp, "ghi_wm2": zon}, index=uren)
    # Goedkoop 's nachts en midden op de dag, duur in de ochtend en avond.
    prijs = 0.08 + 0.06 * np.cos((uur - 18) / 24 * 4 * np.pi)
    prijzen = pd.DataFrame({"prijs_eur_kwh": prijs}, index=uren)
    return weer, prijzen


def _cfg(**batterij) -> Config:
    """Geeft de standaardinstelling met een kwartierstap en aangepaste batterij."""
    cfg = Config()
    cfg.algemeen.tijdstap_min = 15
    for naam, waarde in batterij.items():
        setattr(cfg.batterij, naam, waarde)
    return cfg


@pytest.mark.parametrize("topologie", ["1x3", "3x1"])
@pytest.mark.parametrize("koppeling", ["ac", "hybride"])
@pytest.mark.parametrize("strategie", ["eigen_verbruik", "piek_shaving", "handel"])
def test_energiebalans(topologie, koppeling, strategie):
    """Wat erin gaat, komt eruit, blijft in de accu of is verlies - nooit winst."""
    weer, prijzen = _nepdata()
    cfg = _cfg(topologie=topologie, koppeling=koppeling, strategie=strategie)
    uit = voer_uit(cfg, weer, prijzen)
    r = uit.reeksen
    dt = uit.profielen.basis.dt_h

    erin = (r["zon"].sum() + r["net"].sum()) * dt
    verbruik = (r["huishouden"] + r["warmtepomp"] + r["auto"]).sum() * dt
    accu_erbij = (r["soc"].iloc[-1] - cfg.batterij.start_soc_pct) / 100.0 * cfg.batterij.capaciteit_kwh
    verlies = erin - verbruik - accu_erbij

    # Verlies is er altijd (omvormers, accu, stand-by), maar het blijft klein
    # tegenover wat er door de installatie gaat.
    assert verlies > 0
    assert verlies < 0.25 * (r["zon"].sum() * dt + verbruik)


@pytest.mark.parametrize("topologie", ["1x3", "3x1"])
def test_batterij_blijft_binnen_grenzen(topologie):
    """De laadtoestand komt nooit onder het minimum of boven het maximum."""
    weer, prijzen = _nepdata()
    cfg = _cfg(topologie=topologie, min_soc_pct=10.0, max_soc_pct=90.0)
    r = voer_uit(cfg, weer, prijzen).reeksen
    kolommen = ["soc"] + [k for k in r.columns if k.startswith("soc_l")]
    for kolom in kolommen:
        assert r[kolom].min() >= 10.0 - 1e-6
        assert r[kolom].max() <= 90.0 + 1e-6


def test_batterij_verlaagt_afname_en_kosten():
    """Met een batterij voor eigen verbruik gaat er minder over de meter."""
    weer, prijzen = _nepdata()
    cfg = _cfg(strategie="eigen_verbruik")
    met = voer_uit(cfg, weer, prijzen).kentallen
    zonder = voer_uit(zonder_batterij(cfg), weer, prijzen).kentallen
    assert met["afname_kwh"] < zonder["afname_kwh"]
    assert met["teruglevering_kwh"] < zonder["teruglevering_kwh"]
    assert met["kosten_eur"] < zonder["kosten_eur"]


def test_hybride_vangt_afgeregelde_zon_op():
    """Hybride: zon boven het omvormervermogen gaat de accu in, niet verloren."""
    weer, prijzen = _nepdata()
    cfg = _cfg(koppeling="hybride", omvormer_kw_per_fase=1.0, capaciteit_kwh=40.0)
    cfg.zon.velden[0].aantal_panelen = 24
    cfg.auto.aanwezig = False
    met = voer_uit(cfg, weer, prijzen).kentallen
    cfg.batterij.capaciteit_kwh = 0.5
    bijna_zonder = voer_uit(cfg, weer, prijzen).kentallen
    assert bijna_zonder["afgeregeld_kwh"] > 0
    assert met["afgeregeld_kwh"] < bijna_zonder["afgeregeld_kwh"]


def test_load_balancing_houdt_fasen_onder_de_zekering():
    """Met load balancing blijft elke fase onder de hoofdzekering."""
    weer, prijzen = _nepdata(zomer=False)
    cfg = _cfg(strategie="eigen_verbruik")
    cfg.aansluiting.hoofdzekering_a = 20.0
    uit_aan = voer_uit(cfg, weer, prijzen).kentallen
    cfg.aansluiting.loadbalancing_actief = False
    uit_uit = voer_uit(cfg, weer, prijzen).kentallen
    assert uit_uit["minuten_boven_zekering"] > 0
    assert uit_aan["minuten_boven_zekering"] < uit_uit["minuten_boven_zekering"]
    assert max(uit_aan["max_stroom_a"]) <= 20.0 + 1e-6


def test_laadpaal_buiten_de_load_balancing():
    """Doet de laadpaal niet mee, dan wordt zijn laden niet meer tegengehouden."""
    weer, prijzen = _nepdata(zomer=False)
    cfg = _cfg()
    cfg.batterij.aanwezig = False
    cfg.aansluiting.hoofdzekering_a = 20.0
    mee = voer_uit(cfg, weer, prijzen).kentallen
    cfg.aansluiting.lb_laadpaal = False
    niet_mee = voer_uit(cfg, weer, prijzen).kentallen
    assert mee["laden_beperkt_kwh"] > 0
    assert niet_mee["laden_beperkt_kwh"] == 0
    assert niet_mee["minuten_boven_zekering"] > mee["minuten_boven_zekering"]


def test_warmtepomp_in_de_load_balancing():
    """Een eenfasige warmtepomp op de fase van de kookplaat wijkt als hij meedoet."""
    weer, prijzen = _nepdata(zomer=False)
    cfg = _cfg()
    cfg.batterij.aanwezig = False
    cfg.auto.aanwezig = False
    cfg.aansluiting.hoofdzekering_a = 20.0
    cfg.warmtepomp.fase = 2
    niet_mee = voer_uit(cfg, weer, prijzen).kentallen
    cfg.aansluiting.lb_warmtepomp = True
    mee = voer_uit(cfg, weer, prijzen).kentallen
    assert niet_mee["max_stroom_a"][1] > 20.0
    assert mee["max_stroom_a"][1] <= 20.0
    # De warmte wordt later ingehaald: het huis blijft warm.
    assert mee["laagste_binnentemperatuur_c"] > cfg.huis.binnentemperatuur_c - 1.5


@pytest.mark.parametrize("koppeling", ["ac", "hybride"])
def test_zonnepanelen_in_de_load_balancing(koppeling):
    """Veel panelen op één fase: als ze meedoen, blijft de teruglevering onder de grens."""
    weer, prijzen = _nepdata()
    cfg = _cfg(koppeling=koppeling, topologie="3x1", capaciteit_kwh=3.0, omvormer_kw_per_fase=8.0)
    cfg.auto.aanwezig = False
    cfg.aansluiting.hoofdzekering_a = 16.0
    cfg.aansluiting.lb_batterij = False
    cfg.zon.velden[0].aantal_panelen = 20
    cfg.zon.velden[0].fase = 1
    niet_mee = voer_uit(cfg, weer, prijzen).kentallen
    cfg.aansluiting.lb_zonnepanelen = True
    mee = voer_uit(cfg, weer, prijzen).kentallen
    assert niet_mee["max_stroom_a"][0] > 16.0
    assert mee["max_stroom_a"][0] <= 16.0
    assert mee["afgeregeld_kwh"] > niet_mee["afgeregeld_kwh"]


def test_handelsplan_koopt_laag_en_verkoopt_hoog():
    """Het plan laadt in het goedkoopste uur en ontlaadt in het duurste."""
    koop = np.array([0.30, 0.05, 0.30, 0.60, 0.30])
    plan = plan_handel(
        energie_nu=0.0,
        energie_min=0.0,
        energie_max=10.0,
        vermogen_max_kw=10.0,
        rendement_enkel=0.95,
        slijtage_eur_per_kwh=0.02,
        netto_kwh=np.zeros(5),
        koop=koop,
        verkoop=koop - 0.02,
    )
    assert plan[1] < 0  # laden in het goedkoopste uur
    assert plan[3] > 0  # ontladen in het duurste uur


def test_handelsplan_doet_niets_bij_vlakke_prijs():
    """Zonder prijsverschil is er niets te verdienen en blijft de batterij stil.

    De batterij begint leeg: energie die er al in zit, verkoopt het plan wel,
    omdat ze aan het eind van de planperiode niets meer waard is.
    """
    plan = plan_handel(0.0, 0.0, 10.0, 5.0, 0.95, 0.02, np.zeros(6), np.full(6, 0.25), np.full(6, 0.25))
    assert np.allclose(plan, 0.0)


def test_zonder_zonnepanelen_is_er_geen_zon():
    """Met de schakelaar uit leveren de panelen niets, in beide architecturen."""
    weer, prijzen = _nepdata()
    for koppeling in ("ac", "hybride"):
        cfg = _cfg(koppeling=koppeling)
        cfg.zon.aanwezig = False
        k = voer_uit(cfg, weer, prijzen).kentallen
        assert k["zon_kwh"] == 0
        assert k["kwp"] == 0
        assert k["investering"]["panelen"] == 0


def _congestie_cfg(**batterij) -> Config:
    """Geeft een instelling met stevige netcongestie en zonder auto (die leidt af)."""
    cfg = _cfg(**batterij)
    cfg.netcongestie.actief = True
    cfg.netcongestie.dagvariatie_v = 0.0
    cfg.auto.aanwezig = False
    return cfg


def test_netcongestie_schakelt_panelen_uit():
    """Bij overspanning valt een deel van de zonneproductie weg; zonder congestie niets."""
    weer, prijzen = _nepdata()
    cfg = _congestie_cfg()
    met = voer_uit(zonder_batterij(cfg), weer, prijzen)
    assert met.kentallen["uren_overspanning_straat"] > 0
    assert met.kentallen["uitgeschakeld_kwh"] > 0
    # Ligt de straat ruim boven de grens, dan kan geen enkele fase leveren:
    # het eigen verbruik trekt de spanning hooguit een paar tienden omlaag.
    r = met.reeksen
    ruim_boven = r["spanning_straat"] > cfg.zon.uitschakelspanning_v + 2.0
    assert ruim_boven.any()
    assert r.loc[ruim_boven, "zon"].max() == 0

    cfg.netcongestie.actief = False
    zonder = voer_uit(zonder_batterij(cfg), weer, prijzen)
    assert zonder.kentallen["uitgeschakeld_kwh"] == 0
    assert zonder.kentallen["zon_kwh"] > met.kentallen["zon_kwh"]


def test_spanningssteun_redt_zonneproductie():
    """Aparte omvormers: met spanningssteun gaat er minder zon verloren dan zonder."""
    weer, prijzen = _nepdata()
    cfg = _congestie_cfg(koppeling="ac", capaciteit_kwh=40.0, omvormer_kw_per_fase=5.0)
    zonder_steun = voer_uit(cfg, weer, prijzen).kentallen
    cfg.batterij.spanningssteun = True
    met_steun = voer_uit(cfg, weer, prijzen).kentallen
    assert met_steun["uitgeschakeld_kwh"] < zonder_steun["uitgeschakeld_kwh"]
    assert met_steun["zon_kwh"] > zonder_steun["zon_kwh"]


def test_hybride_redt_zon_ook_zonder_steun():
    """Hybride benut bij overspanning nog zon, en steun maakt het niet slechter.

    Een afgeschakelde hybride omvormer laadt de accu nog met zonnestroom aan de
    DC-kant; een afgeschakelde PV-omvormer levert niets meer. Ligt de straat
    ruim boven de grens, dan is er bij aparte omvormers dus geen zon (zie
    ``test_netcongestie_schakelt_panelen_uit``) en bij hybride wel.
    """
    weer, prijzen = _nepdata()
    cfg = _congestie_cfg(koppeling="hybride")
    uit = voer_uit(cfg, weer, prijzen)
    hybride = uit.kentallen
    r = uit.reeksen
    ruim_boven = r["spanning_straat"] > cfg.zon.uitschakelspanning_v + 2.0
    assert r.loc[ruim_boven, "zon"].max() > 0
    # Die zon gaat de accu in, niet het net op.
    assert r.loc[ruim_boven, "net"].min() >= -1e-9
    cfg.batterij.spanningssteun = True
    met_steun = voer_uit(cfg, weer, prijzen).kentallen
    assert met_steun["uitgeschakeld_kwh"] <= hybride["uitgeschakeld_kwh"] + 1e-6


@pytest.mark.parametrize("koppeling", ["ac", "hybride"])
def test_energiebalans_met_netcongestie(koppeling):
    """Ook met uitgeschakelde panelen en spanningssteun verdwijnt er geen energie."""
    weer, prijzen = _nepdata()
    cfg = _congestie_cfg(koppeling=koppeling, spanningssteun=True)
    uit = voer_uit(cfg, weer, prijzen)
    r = uit.reeksen
    dt = uit.profielen.basis.dt_h
    erin = (r["zon"].sum() + r["net"].sum()) * dt
    verbruik = (r["huishouden"] + r["warmtepomp"] + r["auto"]).sum() * dt
    accu_erbij = (r["soc"].iloc[-1] - cfg.batterij.start_soc_pct) / 100.0 * cfg.batterij.capaciteit_kwh
    verlies = erin - verbruik - accu_erbij
    assert 0 < verlies < 0.25 * (r["zon"].sum() * dt + verbruik)


def test_investering_per_onderdeel():
    """Apart: PV- en batterij-omvormers. Hybride: alleen hybride omvormers."""
    apart = investering(_cfg(koppeling="ac"))
    assert apart["pv_omvormers"] > 0 and apart["batterij_omvormers"] > 0 and apart["hybride_omvormers"] == 0
    hybride = investering(_cfg(koppeling="hybride"))
    assert hybride["pv_omvormers"] == 0 and hybride["batterij_omvormers"] == 0 and hybride["hybride_omvormers"] > 0
    for posten in (apart, hybride):
        assert posten["totaal"] == pytest.approx(sum(v for k, v in posten.items() if k != "totaal"))
    # Zonder batterij blijven alleen de panelen en hun omvormer over.
    kaal = investering(zonder_batterij(_cfg(koppeling="hybride")))
    assert kaal["batterijen"] == 0 and kaal["hybride_omvormers"] == 0 and kaal["pv_omvormers"] > 0


def test_wat_in_bezit_is_kost_niets():
    """Bestaande panelen, batterij en omvormers blijven buiten de investering; uitbreiding niet."""
    cfg = _cfg(koppeling="ac", capaciteit_kwh=15.0)
    alles_nieuw = investering(cfg)

    # Alle 12 panelen liggen er al: geen panelen en geen PV-omvormer.
    cfg.zon.velden[0].panelen_in_bezit = 12
    assert investering(cfg)["panelen"] == 0
    assert investering(cfg)["pv_omvormers"] == 0

    # Vier panelen erbij op hetzelfde veld: alleen die vier tellen.
    cfg.zon.velden[0].aantal_panelen = 16
    assert investering(cfg)["panelen"] == pytest.approx(alles_nieuw["panelen"] * 4 / 12)
    assert investering(cfg)["pv_omvormers"] == pytest.approx(alles_nieuw["pv_omvormers"] * 4 / 12)

    # 5 van de 15 kWh staat er al: 10 kWh kopen, zonder vaste kosten.
    cfg.batterij.in_bezit_kwh = 5.0
    assert investering(cfg)["batterijen"] == pytest.approx(10.0 * cfg.investering.batterij_eur_per_kwh)
    # Meer in bezit dan ingesteld levert geen geld op.
    cfg.batterij.in_bezit_kwh = 40.0
    assert investering(cfg)["batterijen"] == 0

    # De omvormers bij de batterij, apart en hybride.
    cfg.batterij.omvormers_in_bezit = True
    assert investering(cfg)["batterij_omvormers"] == 0
    cfg.batterij.koppeling = "hybride"
    assert investering(cfg)["hybride_omvormers"] == 0

    # De simulatie zelf verandert er niet door: het gaat alleen om geld.
    assert len(in_bezit(cfg)) == 3


def test_tapwater_schakelaar():
    """Zonder tapwater via de warmtepomp is er geen tapwaterwarmte en minder verbruik."""
    weer, prijzen = _nepdata(zomer=False)
    cfg = _cfg()
    met = voer_uit(cfg, weer, prijzen).kentallen
    cfg.warmtepomp.tapwater_via_warmtepomp = False
    zonder = voer_uit(cfg, weer, prijzen).kentallen
    assert met["tapwater_kwh"] > 0
    assert zonder["tapwater_kwh"] == 0
    assert zonder["warmtepomp_kwh"] < met["warmtepomp_kwh"]


def test_wtw_telt_alleen_als_hij_er_is():
    """Het WTW-rendement doet niets zolang er geen WTW-unit is."""
    cfg = Config()
    cfg.huis.wtw_aanwezig = False
    cfg.huis.wtw_rendement = 0.8
    zonder = warmteverlies_w_per_k(cfg.huis)
    cfg.huis.wtw_aanwezig = True
    assert warmteverlies_w_per_k(cfg.huis) < zonder


def test_config_heen_en_terug():
    """Een bewaarde instelling komt ongewijzigd terug."""
    cfg = Config()
    cfg.batterij.capaciteit_kwh = 22.5
    cfg.zon.velden[0].naam = "Schuur"
    assert Config.uit_dict(cfg.naar_dict()).naar_dict() == cfg.naar_dict()
