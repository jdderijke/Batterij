"""De elektrische auto en de laadpaal, inclusief load balancing.

Waarom dit bestaat:
    De laadpaal is de grootste enkele last op de aansluiting (11 kW driefasig)
    en de last die het makkelijkst te verschuiven is. Hij bepaalt daarmee zowel
    of de hoofdzekering het houdt als hoeveel er voor de batterij te doen
    overblijft. Deze module maakt eerst een rijschema (wanneer is de auto thuis,
    hoeveel is er gereden) en rekent daarna stap voor stap door hoe er geladen
    wordt.

Load balancing:
    De laadpaal meet de stroom per fase op de hoofdaansluiting en neemt zelf
    niet meer dan wat er tot de hoofdzekering over is. Zakt de ruimte onder de
    laagste stroom waarop een auto kan laden (6 A), dan pauzeert het laden.

    De batterij telt hier bewust niet mee: de laadpaal kijkt naar de overige
    lasten en de zonnepanelen. De batterij wordt daarna in de simulatie zelf
    begrensd. Zo blijft het laden onafhankelijk van de batterijstrategie.
"""

from __future__ import annotations

import math

import numpy as np

from .config import Aansluiting, Auto


def rijschema(
    auto: Auto,
    dag_begin: np.ndarray,
    lokaal_uur: np.ndarray,
    weekdag: np.ndarray,
    n: int,
    dt_h: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Maakt een rijschema voor het hele jaar.

    Op werkdagen vertrekt de auto op het ingestelde uur en komt hij rond het
    ingestelde uur terug. In het weekend is hij op een deel van de dagen een
    paar uur weg.

    Args:
        auto: instellingen van de auto.
        dag_begin: plaats in de reeks van de eerste stap van elke lokale dag.
        lokaal_uur: uur van de dag in lokale tijd per stap.
        weekdag: dag van de week per lokale dag (0 = maandag).
        n: aantal stappen.
        dt_h: lengte van een stap in uren.
        rng: toevalsgenerator.

    Returns:
        ``thuis`` (per stap: staat de auto aan de laadpaal?) en ``verreden``
        (kWh uit de accu, geboekt op de stap van thuiskomst).
    """
    thuis = np.ones(n, dtype=bool)
    verreden = np.zeros(n)
    # Kans dat de auto op een weekenddag weg is. De kilometers op zo'n dag
    # worden hiermee gedeeld, zodat het gemiddelde per weekenddag klopt met
    # de instelling.
    kans_weekend = 0.6

    for dag, begin in enumerate(dag_begin):
        if weekdag[dag] < 5:
            vertrek = auto.vertrek_uur
            aankomst = max(auto.aankomst_uur + rng.normal(0.0, auto.spreiding_uur), vertrek + 1.0)
            km = auto.km_werkdag * rng.uniform(0.7, 1.3)
        else:
            if rng.random() > kans_weekend:
                continue
            vertrek = 10.0 + rng.uniform(0.0, 3.0)
            aankomst = vertrek + rng.uniform(2.0, 5.0)
            km = auto.km_weekenddag / kans_weekend * rng.uniform(0.5, 1.5)
        if km <= 0:
            continue

        uur_bij_begin = lokaal_uur[begin]
        weg = begin + int(round((vertrek - uur_bij_begin) / dt_h))
        terug = begin + int(round((aankomst - uur_bij_begin) / dt_h))
        weg = max(weg, 0)
        if terug <= weg or weg >= n:
            continue
        thuis[weg:terug] = False
        if terug < n:
            verreden[terug] += km * auto.verbruik_kwh_per_100km / 100.0

    return thuis, verreden


def laad_profiel(
    auto: Auto,
    aansluiting: Aansluiting,
    thuis: np.ndarray,
    verreden: np.ndarray,
    overig_kw: np.ndarray,
    prijs: np.ndarray,
    dt_h: float,
) -> dict[str, np.ndarray]:
    """Rekent stap voor stap door hoe de auto geladen wordt.

    Args:
        auto: instellingen van auto en laadpaal.
        aansluiting: hoofdzekering en load balancing.
        thuis: per stap of de auto aan de laadpaal staat.
        verreden: kWh uit de accu, geboekt op de stap van thuiskomst.
        overig_kw: tabel (stappen, 3) met wat de rest van het huis per fase
            van het net vraagt (verbruik min zonneproductie), zonder batterij.
        prijs: inkoopprijs per stap, voor het laden in de goedkoopste uren.
        dt_h: lengte van een stap in uren.

    Returns:
        ``per_fase`` (tabel (stappen, 3), kW), ``soc_pct`` (laadtoestand van de
        auto), ``beperkt_kw`` (vermogen dat de load balancing heeft
        tegengehouden) en ``soc_bij_vertrek`` (laadtoestand bij elk vertrek).
    """
    n = len(thuis)
    per_fase = np.zeros((n, 3))
    soc_reeks = np.full(n, auto.doel_soc_pct)
    beperkt = np.zeros(n)
    if not auto.aanwezig:
        return {"per_fase": per_fase, "soc_pct": soc_reeks, "beperkt_kw": beperkt, "soc_bij_vertrek": np.array([])}

    # Op welke fasen hangt de laadpaal?
    fasen = [0, 1, 2] if auto.laad_fasen == 3 else [min(max(auto.laad_fase, 1), 3) - 1]
    kw_per_a = aansluiting.spanning_v * len(fasen) / 1000.0
    p_max = auto.max_stroom_a * kw_per_a
    rendement = auto.laadrendement
    doel_kwh = auto.accu_kwh * auto.doel_soc_pct / 100.0
    stroomgrens = aansluiting.hoofdzekering_a - aansluiting.loadbalancing_marge_a

    # Voor elke stap: wanneer vertrekt de auto de volgende keer?
    volgend_vertrek = np.empty(n, dtype=int)
    volgende = n
    for k in range(n - 1, -1, -1):
        if not thuis[k]:
            volgende = k
        volgend_vertrek[k] = volgende

    # Bij "goedkoop" wordt per laadbeurt vastgelegd in welke stappen geladen mag worden.
    mag_laden = np.zeros(n, dtype=bool)
    overig = overig_kw.tolist()
    overig_som = overig_kw.sum(axis=1).tolist()
    thuis_l = thuis.tolist()
    verreden_l = verreden.tolist()
    vertrek_l = volgend_vertrek.tolist()

    soc = doel_kwh
    soc_bij_vertrek = []

    for k in range(n):
        if not thuis_l[k]:
            if k > 0 and thuis_l[k - 1]:
                soc_bij_vertrek.append(100.0 * soc / auto.accu_kwh)
            soc_reeks[k] = 100.0 * soc / auto.accu_kwh
            continue

        if k > 0 and not thuis_l[k - 1]:
            # Thuiskomst: de gereden kilometers gaan van de accu af.
            soc = max(soc - verreden_l[k], 0.0)
            if auto.strategie == "goedkoop":
                # Kies tussen nu en het volgende vertrek de goedkoopste
                # stappen, precies genoeg om de accu op het doel te brengen.
                eind = vertrek_l[k]
                nodig_ac = max(doel_kwh - soc, 0.0) / rendement
                aantal = min(int(math.ceil(nodig_ac / (p_max * dt_h))), eind - k)
                if aantal > 0:
                    goedkoopste = np.argsort(prijs[k:eind], kind="stable")[:aantal]
                    mag_laden[k + goedkoopste] = True

        tekort = doel_kwh - soc
        if tekort > 1e-6:
            # Vangnet voor elke strategie: als er alleen nog genoeg tijd is om
            # op vol vermogen het doel te halen, wordt er nu geladen. Zonder
            # dit zou "laden op zon" de auto op een bewolkte dag leeg laten.
            stappen_over = vertrek_l[k] - k
            haast = tekort / rendement >= (stappen_over - 1) * p_max * dt_h

            if auto.strategie == "direct" or haast:
                wens_a = auto.max_stroom_a
            elif auto.strategie == "goedkoop":
                wens_a = auto.max_stroom_a if mag_laden[k] else 0.0
            else:
                # Laden op zon: alleen wat het huis anders zou terugleveren.
                overschot_a = -overig_som[k] / kw_per_a
                wens_a = min(overschot_a, auto.max_stroom_a) if overschot_a >= auto.min_stroom_a else 0.0

            stroom = wens_a
            if aansluiting.loadbalancing_actief and aansluiting.lb_laadpaal and stroom > 0:
                # Ruimte op de krapste fase waar de laadpaal op hangt.
                ruimte = min(stroomgrens - overig[k][f] * 1000.0 / aansluiting.spanning_v for f in fasen)
                if ruimte < stroom:
                    stroom = ruimte if ruimte >= auto.min_stroom_a else 0.0
                    beperkt[k] = (wens_a - stroom) * kw_per_a

            # Niet meer laden dan er nog bij kan.
            vermogen = min(stroom * kw_per_a, tekort / rendement / dt_h)
            if vermogen > 0:
                soc += vermogen * rendement * dt_h
                for f in fasen:
                    per_fase[k, f] = vermogen / len(fasen)

        soc_reeks[k] = 100.0 * soc / auto.accu_kwh

    return {
        "per_fase": per_fase,
        "soc_pct": soc_reeks,
        "beperkt_kw": beperkt,
        "soc_bij_vertrek": np.array(soc_bij_vertrek),
    }
