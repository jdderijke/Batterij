"""Scenario's naast elkaar: wat als ik meer panelen, een andere batterij of een andere architectuur neem?

Waarom dit bestaat:
    Het doel van het hele project is kiezen. Deze module gaat uit van één
    basisinstelling, de *baseline*: de instelling zoals ze nu is doorgerekend.
    De gebruiker geeft per onderdeel (aantal panelen, batterijgrootte,
    topologie, koppeling, strategie) de alternatieven op die hij wil zien. Elk
    scenario is de baseline met een of meer onderdelen vervangen door een
    alternatief, en wordt afgezet tegen diezelfde baseline. Wie alleen een
    andere strategie kiest, krijgt dus precies één scenario: de baseline met
    die strategie.

    Afgewezen: vergelijken met "de huidige panelen zonder batterij", zoals
    eerder. Dat beantwoordt de vraag "loont een batterij?", en die staat al op
    het Overzicht. Hier is de vraag "wat levert een verandering op ten
    opzichte van wat ik nu heb ingesteld?", en daar hoort de baseline als
    nulpunt bij. Het werkt bovendien ook zonder batterij of zonder panelen.

    Afgewezen: de gebruiker de volledige lijsten laten opgeven, met de waarde
    van de baseline erbij. Dan moet hij bij elk onderdeel dat hij níet wil
    variëren toch de huidige waarde aanvinken, en rekent één extra vinkje
    ongemerkt een verdubbeling van het aantal scenario's uit.
"""

from __future__ import annotations

import itertools
from typing import Callable, Iterable

import pandas as pd

from .config import KOPPELINGEN, STRATEGIEEN, TOPOLOGIEEN, Config
from .resultaat import vergelijk
from .simulatie import Uitkomst, voer_uit

# Eén scenario: (batterij in kWh, paneelfactor, topologie, koppeling, strategie).
Keuze = tuple[float, float, str, str, str]


def basiskeuze(basis: Config) -> Keuze:
    """Geeft de baseline in dezelfde vorm als een scenario.

    Waarom dit bestaat:
        Om te weten welke combinaties nieuw zijn, moet de baseline in dezelfde
        termen staan als de alternatieven. Een batterij die uit staat telt als
        0 kWh, ook als er nog een grootte in de instelling bewaard is.
    """
    b = basis.batterij
    capaciteit = float(b.capaciteit_kwh) if b.aanwezig else 0.0
    return (capaciteit, 1.0, b.topologie, b.koppeling, b.strategie)


def combinaties(
    basis: Config,
    capaciteiten: Iterable[float] = (),
    paneelfactoren: Iterable[float] = (),
    topologieen: Iterable[str] = (),
    koppelingen: Iterable[str] = (),
    strategieen: Iterable[str] = (),
) -> list[Keuze]:
    """Maakt de lijst van door te rekenen scenario's uit de opgegeven alternatieven.

    Waarom dit bestaat:
        De app wil het aantal scenario's op de knop zetten voordat er gerekend
        wordt, en de berekening wil dezelfde lijst aflopen. Eén functie voor
        beide voorkomt dat het getal op de knop afwijkt van wat er gebeurt.

    Per onderdeel doet de waarde van de baseline altijd mee, naast de
    opgegeven alternatieven; een leeg onderdeel blijft dus zoals het is. Alle
    combinaties daarvan zijn een scenario, behalve de baseline zelf: die is al
    doorgerekend en is het nulpunt van de vergelijking.

    Zonder batterij (0 kWh) doen topologie, koppeling en strategie er niet
    toe; die combinaties tellen dan één keer in plaats van voor elke variant.

    Args:
        basis: de baseline.
        capaciteiten: alternatieve batterijgroottes in kWh; 0 is geen batterij.
        paneelfactoren: alternatieve vermenigvuldigers op het aantal panelen
            van elk veld; 1 is het aantal van de baseline.
        topologieen, koppelingen, strategieen: alternatieve sleutels uit
            ``config``.

    Returns:
        De scenario's, in de volgorde waarin ze worden doorgerekend.
    """
    nul = basiskeuze(basis)
    reeksen = []
    for eigen, alternatieven in zip(nul, (capaciteiten, paneelfactoren, topologieen, koppelingen, strategieen)):
        # ``dict.fromkeys`` haalt dubbelen weg en houdt de volgorde: eerst de
        # baseline, dan de alternatieven zoals ze zijn opgegeven.
        reeksen.append(list(dict.fromkeys([eigen, *alternatieven])))

    def sleutel(keuze: Keuze) -> tuple:
        return keuze if keuze[0] > 0 else (0.0, keuze[1])

    gezien = {sleutel(nul)}
    uit = []
    for keuze in itertools.product(*reeksen):
        if sleutel(keuze) not in gezien:
            gezien.add(sleutel(keuze))
            uit.append(keuze)
    return uit


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
    capaciteiten: Iterable[float] = (),
    paneelfactoren: Iterable[float] = (),
    topologieen: Iterable[str] = (),
    koppelingen: Iterable[str] = (),
    strategieen: Iterable[str] = (),
    voortgang: Callable[[int, int], None] | None = None,
    onbalans: pd.DataFrame | None = None,
    referentie: Uitkomst | None = None,
) -> pd.DataFrame:
    """Rekent alle scenario's door en geeft één rij per scenario.

    Welke scenario's dat zijn, staat bij ``combinaties``. Besparing,
    meerinvestering, terugverdientijd en netto voordeel zijn steeds het
    verschil met de baseline.

    Args:
        basis: de baseline.
        capaciteiten, paneelfactoren, topologieen, koppelingen, strategieen:
            de alternatieven per onderdeel; zie ``combinaties``.
        voortgang: wordt na elk scenario aangeroepen met (klaar, totaal).
        onbalans: kwartiertabel van ``data.laad_onbalans``; alleen nodig als
            "onbalans" de strategie is van de baseline of van een alternatief.
        referentie: de uitkomst van de baseline, als de aanroeper die al
            heeft (de app heeft haar altijd). Zonder wordt ze hier berekend.

    Returns:
        Tabel, gesorteerd op netto voordeel (beste bovenaan). Leeg als er
        geen alternatieven zijn opgegeven.
    """
    if referentie is None:
        referentie = voer_uit(basis.kopie(), weer, prijzen, onbalans)
    lijst = combinaties(basis, capaciteiten, paneelfactoren, topologieen, koppelingen, strategieen)

    rijen = []
    for nummer, (cap, factor, topo, kop, strat) in enumerate(lijst, start=1):
        uitkomst = voer_uit(maak_variant(basis, cap, factor, topo, kop, strat), weer, prijzen, onbalans)
        k = uitkomst.kentallen
        v = vergelijk(uitkomst, referentie)
        met_batterij = cap > 0
        rijen.append(
            {
                # Eerst de panelen, dan de batterij: dezelfde volgorde als de
                # invoervelden en de samenvatting van de baseline in de app.
                "Panelen (kWp)": round(k["kwp"], 2),
                "Batterij (kWh)": cap,
                "Topologie": TOPOLOGIEEN[topo] if met_batterij else "-",
                "Koppeling": KOPPELINGEN[kop].split(":")[0] if met_batterij else "-",
                "Strategie": STRATEGIEEN[strat] if met_batterij else "-",
                "Kosten (€/jaar)": k["kosten_eur"] / k["jaren"],
                "Besparing (€/jaar)": v["besparing_eur_per_jaar"],
                "Meerinvestering (€)": v["meerinvestering_eur"],
                "Terugverdientijd (jaar)": v["terugverdientijd_jaar"],
                "Netto voordeel (€)": v["netto_voordeel_eur"],
                # Voor wie onafhankelijk van het net wil zijn, telt dit getal
                # zwaarder dan de terugverdientijd.
                "Dagen off-grid": k["offgrid_dagen"],
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
            voortgang(nummer, len(lijst))

    tabel = pd.DataFrame(rijen)
    if tabel.empty:
        return tabel
    return tabel.sort_values("Netto voordeel (€)", ascending=False, ignore_index=True)
