"""Scenario's naast elkaar: welke batterij, hoeveel panelen, welke architectuur?

Waarom dit bestaat:
    Het doel van het hele project is kiezen. Deze module maakt uit één
    basisinstelling een reeks varianten (batterijgrootte x aantal panelen x
    topologie x koppeling x strategie), rekent ze allemaal door en zet ze af
    tegen dezelfde referentie: de basisinstelling zonder batterij. Omdat elke
    variant tegen dezelfde referentie wordt gemeten, telt de investering in
    extra panelen ook mee en zijn alle rijen onderling vergelijkbaar.
"""

from __future__ import annotations

import itertools
from typing import Callable, Iterable

import pandas as pd

from .config import KOPPELINGEN, STRATEGIEEN, TOPOLOGIEEN, Config
from .resultaat import vergelijk
from .simulatie import Uitkomst, voer_uit, zonder_batterij


def maak_variant(
    basis: Config, capaciteit_kwh: float, paneelfactor: float, topologie: str, koppeling: str, strategie: str
) -> Config:
    """Maakt één variant van de basisinstelling.

    Args:
        basis: de instelling waarvan wordt uitgegaan (blijft ongewijzigd).
        capaciteit_kwh: totale batterijcapaciteit; 0 betekent geen batterij.
        paneelfactor: vermenigvuldiger op het aantal panelen van elk veld.
        topologie, koppeling, strategie: sleutels uit ``config``.
    """
    cfg = basis.kopie()
    cfg.batterij.aanwezig = capaciteit_kwh > 0
    cfg.batterij.capaciteit_kwh = float(capaciteit_kwh)
    cfg.batterij.topologie = topologie
    cfg.batterij.koppeling = koppeling
    cfg.batterij.strategie = strategie
    for veld in cfg.zon.velden:
        veld.aantal_panelen = max(int(round(veld.aantal_panelen * paneelfactor)), 0)
    return cfg


def vergelijk_scenarios(
    basis: Config,
    weer: pd.DataFrame,
    prijzen: pd.DataFrame,
    capaciteiten: Iterable[float],
    paneelfactoren: Iterable[float],
    topologieen: Iterable[str],
    koppelingen: Iterable[str],
    strategieen: Iterable[str],
    voortgang: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Rekent alle combinaties door en geeft één rij per scenario.

    Zonder batterij doen topologie, koppeling en strategie er niet toe; die
    combinaties worden dan één keer gerekend in plaats van voor elke variant.

    Args:
        voortgang: wordt na elk scenario aangeroepen met (klaar, totaal).

    Returns:
        Tabel, gesorteerd op netto voordeel (beste bovenaan).
    """
    referentie: Uitkomst = voer_uit(zonder_batterij(basis), weer, prijzen)

    combinaties = []
    gezien = set()
    for cap, factor, topo, kop, strat in itertools.product(
        capaciteiten, paneelfactoren, topologieen, koppelingen, strategieen
    ):
        sleutel = (cap, factor, topo, kop, strat) if cap > 0 else (0.0, factor)
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        combinaties.append((cap, factor, topo, kop, strat))

    rijen = []
    for nummer, (cap, factor, topo, kop, strat) in enumerate(combinaties, start=1):
        uitkomst = voer_uit(maak_variant(basis, cap, factor, topo, kop, strat), weer, prijzen)
        k = uitkomst.kentallen
        v = vergelijk(uitkomst, referentie)
        met_batterij = cap > 0
        rijen.append(
            {
                "Batterij (kWh)": cap,
                "Panelen (kWp)": round(k["kwp"], 2),
                "Topologie": TOPOLOGIEEN[topo] if met_batterij else "-",
                "Koppeling": KOPPELINGEN[kop].split(":")[0] if met_batterij else "-",
                "Strategie": STRATEGIEEN[strat] if met_batterij else "-",
                "Kosten (€/jaar)": k["kosten_eur"] / k["jaren"],
                "Besparing (€/jaar)": v["besparing_eur_per_jaar"],
                "Meerinvestering (€)": v["meerinvestering_eur"],
                "Terugverdientijd (jaar)": v["terugverdientijd_jaar"],
                "Netto voordeel (€)": v["netto_voordeel_eur"],
                "Zelfvoorzienend (%)": k["zelfvoorzienend_pct"],
                "Eigen verbruik zon (%)": k["eigen_verbruik_pct"],
                "Afname (kWh)": k["afname_kwh"],
                "Teruglevering (kWh)": k["teruglevering_kwh"],
                "Piek afname (kW)": k["piek_afname_kw"],
                "Cycli": k["cycli"],
                "Afgeregeld (kWh)": k["afgeregeld_kwh"],
                "Zon uit door overspanning (kWh)": k["uitgeschakeld_kwh"],
            }
        )
        if voortgang is not None:
            voortgang(nummer, len(combinaties))

    tabel = pd.DataFrame(rijen)
    return tabel.sort_values("Netto voordeel (€)", ascending=False, ignore_index=True)
