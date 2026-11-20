"""Kentallen en kosten uit een simulatie.

Waarom dit bestaat:
    De simulatie levert een reeks per tijdstap; om scenario's te vergelijken
    zijn een paar getallen nodig. Die worden allemaal hier uitgerekend, uit de
    reeksen en nergens anders uit, zodat een getal in de app en hetzelfde getal
    in de scenariotabel altijd dezelfde berekening zijn.
"""

from __future__ import annotations

import math

import numpy as np

from .config import Config
from .huis import warmteverlies_w_per_k
from .simulatie import Uitkomst
from .zon import nieuw_piekvermogen_kwp, piekvermogen_kwp


def investering(cfg: Config) -> dict[str, float]:
    """Schat de aanschafkosten van panelen, omvormers en batterij.

    Het verschil tussen de architecturen zit in drie dingen: een hybride
    opstelling spaart de PV-omvormer uit maar heeft duurdere omvormers, en drie
    losse batterijen betalen drie keer de vaste kosten van een batterij.

    Wat al in bezit is, kost niets meer en telt dus niet mee: de panelen die er
    al liggen (met hun aandeel in de PV-omvormer), het deel van de batterij dat
    er al staat, en de omvormers bij de batterij als die er al zijn. Alleen wat
    erbij komt, is investering.

    Returns:
        De bedragen in euro per onderdeel: ``panelen``, ``pv_omvormers``,
        ``batterij_omvormers``, ``hybride_omvormers`` en ``batterijen``, plus
        ``totaal``. Bij een hybride opstelling zijn de twee soorten aparte
        omvormers nul, en omgekeerd.
    """
    inv = cfg.investering
    b = cfg.batterij
    kwp_nieuw = nieuw_piekvermogen_kwp(cfg.zon)
    heeft_batterij = b.aanwezig and b.capaciteit_kwh > 0
    hybride = b.aanwezig and b.koppeling == "hybride"

    posten = {
        "panelen": kwp_nieuw * 1000.0 * inv.pv_eur_per_wp,
        "pv_omvormers": 0.0,
        "batterij_omvormers": 0.0,
        "hybride_omvormers": 0.0,
        "batterijen": 0.0,
    }
    if hybride:
        # Eén hybride omvormer per fase doet het werk van beide.
        if not b.omvormers_in_bezit:
            posten["hybride_omvormers"] = 3 * inv.hybride_omvormer_eur
    else:
        # De PV-omvormer wordt betaald per kW AC-vermogen, en alleen voor de
        # nieuwe panelen: de bestaande hebben hun omvormer al.
        posten["pv_omvormers"] = kwp_nieuw * cfg.zon.pv_omvormer_verhouding * inv.pv_omvormer_eur_per_kw
        if heeft_batterij and not b.omvormers_in_bezit:
            posten["batterij_omvormers"] = 3 * inv.batterij_omvormer_eur
    if heeft_batterij:
        nieuw_kwh = max(b.capaciteit_kwh - b.in_bezit_kwh, 0.0)
        posten["batterijen"] = nieuw_kwh * inv.batterij_eur_per_kwh
        if b.in_bezit_kwh <= 0:
            # De vaste kosten (kast, BMS, montage) horen bij een nieuwe
            # batterij. Wie een bestaande batterij uitbreidt, betaalt alleen
            # de extra kWh.
            aantal = 1 if b.topologie == "1x3" else 3
            posten["batterijen"] += aantal * inv.batterij_vast_eur

    posten["totaal"] = sum(posten.values())
    return posten


def in_bezit(cfg: Config) -> list[str]:
    """Somt op wat al in bezit is en daarom buiten de investering blijft.

    De app toont deze regels bij de investering, zodat te zien is waarom een
    post lager is dan verwacht of helemaal ontbreekt.
    """
    regels = []
    b = cfg.batterij
    if cfg.zon.aanwezig:
        panelen = sum(min(v.panelen_in_bezit, v.aantal_panelen) for v in cfg.zon.velden)
        if panelen > 0:
            regels.append(f"{panelen} zonnepanelen met hun omvormer")
    if b.aanwezig and b.capaciteit_kwh > 0:
        kwh = min(b.in_bezit_kwh, b.capaciteit_kwh)
        if kwh > 0:
            regels.append(f"{kwh:g} kWh batterij")
        if b.omvormers_in_bezit:
            regels.append("de omvormers bij de batterij")
    return regels


def bereken_kentallen(uitkomst: Uitkomst) -> dict:
    """Vat een simulatie samen in kentallen.

    Energie in kWh, vermogen in kW, stroom in A, geld in euro; alles over de
    hele gesimuleerde periode.
    """
    cfg = uitkomst.cfg
    prof = uitkomst.profielen
    basis = prof.basis
    r = uitkomst.reeksen
    dt = basis.dt_h
    zekering = cfg.aansluiting.hoofdzekering_a

    net = r["net"].to_numpy()
    afname = float(np.clip(net, 0, None).sum() * dt)
    teruglevering = float(np.clip(-net, 0, None).sum() * dt)
    verbruik = float((r["huishouden"] + r["warmtepomp"] + r["auto"]).sum() * dt)
    zon = float(r["zon"].sum() * dt)

    k: dict = {
        "afname_kwh": afname,
        "teruglevering_kwh": teruglevering,
        "verbruik_kwh": verbruik,
        "huishouden_kwh": float(r["huishouden"].sum() * dt),
        "warmtepomp_kwh": float(r["warmtepomp"].sum() * dt),
        "auto_kwh": float(r["auto"].sum() * dt),
        "zon_kwh": zon,
        "zon_potentieel_kwh": float(prof.pv_potentieel.sum() * dt),
        "afgeregeld_kwh": float(r["afgeregeld"].sum() * dt),
        # Netcongestie: wat de panelen misliepen doordat ze uitgeschakeld
        # waren, en hoe lang de spanning in de straat boven de grens lag.
        "uitgeschakeld_kwh": float(r["uitgeschakeld"].sum() * dt),
        "uren_overspanning_straat": float((r["spanning_straat"] > cfg.zon.uitschakelspanning_v).sum() * dt)
        if cfg.netcongestie.actief
        else 0.0,
        "uren_panelen_uit": float((r["uitgeschakeld"] > 0).sum() * dt),
        "hoogste_spanning_v": float(r[["spanning_l1", "spanning_l2", "spanning_l3"]].to_numpy().max()),
        "kwp": piekvermogen_kwp(cfg.zon),
        "kosten_eur": float(r["kosten"].sum()),
    }

    # Eigen verbruik: welk deel van de zonnestroom blijft in huis?
    # Zelfvoorzienend: welk deel van het verbruik komt niet van het net?
    # Bij handel laadt de batterij ook uit het net en levert ze daaruit terug;
    # de begrenzing op 0..100% vangt dat op, maar de getallen zeggen dan minder.
    k["eigen_verbruik_pct"] = 100.0 * min(max((zon - teruglevering) / zon, 0.0), 1.0) if zon > 0 else 0.0
    k["zelfvoorzienend_pct"] = 100.0 * min(max(1.0 - afname / verbruik, 0.0), 1.0) if verbruik > 0 else 0.0

    # Piek: het hoogste kwartiergemiddelde, de maat die netbeheerders gebruiken.
    kwartier = r["net"].resample("15min").mean() if dt < 0.25 else r["net"]
    k["piek_afname_kw"] = float(kwartier.max())
    k["piek_teruglevering_kw"] = float(max(-kwartier.min(), 0.0))

    # Fasestromen tegenover de hoofdzekering.
    stroom = np.abs(r[["stroom_l1", "stroom_l2", "stroom_l3"]].to_numpy())
    k["max_stroom_a"] = [float(x) for x in stroom.max(axis=0)]
    k["minuten_boven_zekering"] = float((stroom > zekering).any(axis=1).sum() * dt * 60.0)
    k["minuten_boven_zekering_per_fase"] = [float(x) for x in (stroom > zekering).sum(axis=0) * dt * 60.0]

    # Batterij.
    accu = r["batterij"].to_numpy()
    capaciteit = cfg.batterij.capaciteit_kwh if cfg.batterij.aanwezig else 0.0
    ontladen = float(np.clip(accu, 0, None).sum() * dt)
    k["batterij_kwh"] = capaciteit
    k["batterij_geladen_kwh"] = float(np.clip(-accu, 0, None).sum() * dt)
    k["batterij_ontladen_kwh"] = ontladen
    # Eén cyclus = de bruikbare capaciteit één keer vol en leeg.
    bruikbaar = capaciteit * (cfg.batterij.max_soc_pct - cfg.batterij.min_soc_pct) / 100.0
    k["cycli"] = ontladen / bruikbaar if bruikbaar > 0 else 0.0

    # Warmtepomp en huis.
    wp = basis.warmtepomp
    warmte = float(wp["warmte_kw"].sum() * dt)
    tapwater = float(wp["tapwater_kw"].sum() * dt)
    compressor = float(wp["elektrisch_kw"].sum() * dt)
    bijverwarming = float(wp["bijverwarming_kw"].sum() * dt)
    k["warmte_kwh"] = warmte
    k["tapwater_kwh"] = tapwater
    k["compressor_kwh"] = compressor
    k["bijverwarming_kwh"] = bijverwarming
    # SCOP: geleverde warmte gedeeld door alle stroom die ervoor nodig was.
    stroom_wp = compressor + bijverwarming
    k["scop"] = (warmte + tapwater + bijverwarming) / stroom_wp if stroom_wp > 0 else 0.0
    k["warmteverlies_w_per_k"] = warmteverlies_w_per_k(cfg.huis)
    k["laagste_binnentemperatuur_c"] = float(wp["binnen_c"].min())

    # Auto en laadpaal.
    k["laden_beperkt_kwh"] = float(prof.auto["beperkt_kw"].sum() * dt)
    bij_vertrek = prof.auto["soc_bij_vertrek"]
    k["soc_bij_vertrek_pct"] = float(bij_vertrek.mean()) if len(bij_vertrek) else float("nan")
    k["vertrekken"] = int(len(bij_vertrek))
    k["vertrekken_onder_doel"] = int((bij_vertrek < cfg.auto.doel_soc_pct - 5.0).sum()) if len(bij_vertrek) else 0

    # Salderen is per kWh verrekend; dat klopt alleen als er niet meer wordt
    # teruggeleverd dan afgenomen.
    k["saldering_overschreden"] = bool(cfg.tarieven.salderen and teruglevering > afname)

    k["investering"] = investering(cfg)
    k["jaren"] = len(r) * dt / 8760.0
    return k


def vergelijk(uitkomst: Uitkomst, referentie: Uitkomst) -> dict[str, float]:
    """Zet een scenario af tegen een referentie (meestal: zonder batterij).

    Returns:
        ``besparing_eur_per_jaar``, ``meerinvestering_eur``,
        ``terugverdientijd_jaar`` (oneindig als er geen besparing is) en
        ``netto_voordeel_eur`` over de ingestelde levensduur.
    """
    k = uitkomst.kentallen
    ref = referentie.kentallen
    jaren = k["jaren"] if k["jaren"] > 0 else 1.0
    besparing = (ref["kosten_eur"] - k["kosten_eur"]) / jaren
    meer = k["investering"]["totaal"] - ref["investering"]["totaal"]
    if meer <= 0:
        terugverdientijd = 0.0
    elif besparing > 0:
        terugverdientijd = meer / besparing
    else:
        terugverdientijd = math.inf
    return {
        "besparing_eur_per_jaar": besparing,
        "meerinvestering_eur": meer,
        "terugverdientijd_jaar": terugverdientijd,
        "netto_voordeel_eur": besparing * uitkomst.cfg.investering.levensduur_jaren - meer,
    }
