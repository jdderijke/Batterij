"""De simulatie zelf: batterij, omvormers, regelstrategie en de tijdlus.

Waarom dit bestaat:
    Hier komen alle onderdelen samen op de driefasige aansluiting. Per tijdstap
    en per fase wordt de balans opgemaakt: verbruik, zonneproductie, wat de
    batterij doet, en wat er dan over de hoofdaansluiting loopt.

Twee stappen, om een reden:
    1. ``bouw_profielen`` rekent alles uit wat NIET van de batterij afhangt:
       weer, zonopbrengst, huishouden, warmtepomp en laadpaal.
    2. ``simuleer`` laat daar de batterij op los.

    Door die splitsing hoeft bij het vergelijken van batterijen alleen stap 2
    opnieuw, en is er vanzelf een eerlijke referentie: dezelfde profielen
    zonder batterij.

Het model van de omvormers (één per fase):
    Elke fase heeft een "eenheid": een omvormer met aan de DC-kant de batterij
    en, bij een hybride opstelling, ook de zonnepanelen. Dezelfde berekening
    dekt daardoor alle vier de architecturen:

    - AC-gekoppeld: de panelen hebben een eigen omvormer en tellen mee als
      negatief verbruik op hun fase. De eenheid heeft geen zon aan de DC-kant.
    - Hybride: de panelen zitten aan de DC-kant van de eenheid. Zonnestroom
      gaat zonder omweg de batterij in, en wat boven het AC-vermogen van de
      omvormer uitkomt kan nog de batterij in in plaats van verloren te gaan.
    - 1 batterij met 3 omvormers: de drie eenheden delen één accu. Energie die
      op de ene fase geladen is, kan op een andere fase ontladen worden.
    - 3 batterijen: elke eenheid heeft een eigen accu van een derde van de
      capaciteit. De ene kan leeg zijn terwijl de andere vol is.

Tekens: vermogen aan de netkant is positief bij AFNAME van het net en negatief
bij teruglevering. Batterijvermogen is positief bij ONTLADEN.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import auto as auto_mod
from . import zon as zon_mod
from .belasting import huishoud_profiel, over_fasen
from .config import KNMI_STATIONS, TIJDSTAPPEN_MIN, Config
from .data import naar_tijdstap
from .huis import warmtepomp_profiel

TIJDZONE = "Europe/Amsterdam"
# Uur (lokale tijd) waarop de day-ahead-prijzen voor morgen bekend zijn. Het
# handelsplan wordt op dat moment opnieuw gemaakt.
PRIJZEN_BEKEND_UUR = 13.0
# Aantal laadniveaus waarmee het handelsplan rekent (zie ``plan_handel``).
PLAN_NIVEAUS = 41


@dataclass
class Basis:
    """Alles wat alleen van weer, huis, panelen en huishouden afhangt."""

    index: pd.DatetimeIndex
    lokaal: pd.DatetimeIndex
    dt_h: float
    stappen_per_uur: int
    lokaal_uur: np.ndarray
    dag_nr: np.ndarray
    dag_begin: np.ndarray
    weekdag: np.ndarray
    temp_c: np.ndarray
    ghi: np.ndarray
    prijs_markt: np.ndarray
    # DC-vermogen per zonneveld (kW), in de volgorde van cfg.zon.velden.
    pv_dc_velden: list[np.ndarray]
    huishouden: np.ndarray
    warmtepomp: dict[str, np.ndarray]
    warmtepomp_fasen: np.ndarray


@dataclass
class Profielen:
    """De basis plus alles wat nog van architectuur en tarieven afhangt."""

    basis: Basis
    hybride: bool
    # Netspanning in de straat, zonder de invloed van dit huis (V).
    spanning_net: np.ndarray
    # Zonneproductie aan de AC-kant per fase (alleen AC-gekoppeld; anders nul).
    pv_ac: np.ndarray
    # Zonneproductie aan de DC-kant per eenheid (alleen hybride; anders nul).
    pv_dc: np.ndarray
    # Wat de panelen maximaal hadden kunnen leveren (kW DC, alle velden samen).
    pv_potentieel: np.ndarray
    auto: dict[str, np.ndarray]
    auto_thuis: np.ndarray
    # Totaal verbruik per fase: huishouden + warmtepomp + auto.
    last: np.ndarray
    koop: np.ndarray
    verkoop: np.ndarray


@dataclass
class Uitkomst:
    """Het resultaat van één simulatie."""

    cfg: Config
    profielen: Profielen
    # Eén rij per tijdstap; kolommen staan beschreven in ``simuleer``.
    reeksen: pd.DataFrame
    kentallen: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stap 1: profielen
# ---------------------------------------------------------------------------

# Kleine voorraad van eerder berekende bases. Bij het vergelijken van
# scenario's verandert vaak alleen de batterij; de basis (met de trage
# warmtepomplus) is dan steeds dezelfde.
_basis_voorraad: dict[str, Basis] = {}


def bouw_basis(cfg: Config, weer: pd.DataFrame, prijzen: pd.DataFrame) -> Basis:
    """Rekent uit wat alleen van weer, huis, panelen en huishouden afhangt.

    Args:
        cfg: de instelling.
        weer: uurtabel van ``data.laad_weer``.
        prijzen: uurtabel van ``data.laad_prijzen``.
    """
    # De sleutel bevat ook een vingerafdruk van de data zelf: dezelfde
    # instelling op ander weer is een andere basis.
    vingerafdruk = [
        str(weer.index[0]),
        len(weer),
        float(weer["temp_c"].sum()),
        float(weer["ghi_wm2"].sum()),
        float(prijzen["prijs_eur_kwh"].sum()),
    ]
    als_dict = cfg.naar_dict()
    sleutel = json.dumps(
        [vingerafdruk] + [als_dict[deel] for deel in ("algemeen", "aansluiting", "huis", "warmtepomp", "zon", "huishouden")],
        sort_keys=True,
    )
    if sleutel in _basis_voorraad:
        return _basis_voorraad[sleutel]

    stap_min = cfg.algemeen.tijdstap_min
    if stap_min not in TIJDSTAPPEN_MIN:
        raise ValueError(f"Tijdstap {stap_min} minuten is niet toegestaan; kies uit {TIJDSTAPPEN_MIN}.")
    spu = 60 // stap_min
    dt_h = stap_min / 60.0

    n = len(weer) * spu
    index = pd.date_range(weer.index[0], periods=n, freq=f"{stap_min}min")
    lokaal = index.tz_convert(TIJDZONE)

    # Uur van de dag en volgnummer van de dag in lokale tijd: apparaten, de
    # auto en de boiler volgen de klok van de bewoners, niet UTC.
    lokaal_uur = lokaal.hour.to_numpy() + lokaal.minute.to_numpy() / 60.0
    datums = lokaal.tz_localize(None).normalize()
    dag_nr = np.asarray((datums - datums[0]).days, dtype=int)
    dag_begin = np.searchsorted(dag_nr, np.arange(dag_nr[-1] + 1))
    weekdag = np.asarray(lokaal.day_of_week)[dag_begin]

    temp = naar_tijdstap(weer["temp_c"].to_numpy(), spu, vloeiend=True)
    ghi = np.clip(naar_tijdstap(weer["ghi_wm2"].to_numpy(), spu, vloeiend=True), 0.0, None)
    prijs = naar_tijdstap(prijzen["prijs_eur_kwh"].to_numpy(), spu, vloeiend=False)

    # Zonnestand op het midden van elke stap.
    _, breedte, lengte = KNMI_STATIONS[cfg.algemeen.knmi_station]
    midden = index + pd.Timedelta(minutes=stap_min / 2.0)
    cos_zenit, azimut, buitenaards = zon_mod.zonnestand(midden, breedte, lengte)
    dni, dhi = zon_mod.splits_straling(ghi, cos_zenit, buitenaards)
    # Zonder panelen levert elk veld nul. De lijst houdt wel één reeks per
    # veld, zodat ze overal naast cfg.zon.velden gelegd kan worden.
    pv_velden = [
        zon_mod.veld_vermogen_dc(veld, cfg.zon, ghi, temp, cos_zenit, azimut, dni, dhi)
        if cfg.zon.aanwezig
        else np.zeros(n)
        for veld in cfg.zon.velden
    ]

    # Eén toevalsgenerator per onderwerp, elk afgeleid van dezelfde seed. Zo
    # verandert het rijschema van de auto niet als er een apparaat bijkomt.
    rng_huis = np.random.default_rng([cfg.algemeen.seed, 1])
    huishouden = huishoud_profiel(cfg.huishouden, dag_nr, lokaal_uur, dt_h, rng_huis)

    # Doet de warmtepomp mee aan de load balancing, dan mag hij per stap niet
    # meer nemen dan wat het huishouden op zijn fase(n) tot de grens overlaat.
    # Hij kijkt alleen naar het huishouden: de laadpaal wordt pas hierna
    # berekend en wijkt, als die ook meedoet, op zijn beurt voor de warmtepomp.
    a = cfg.aansluiting
    wp_plafond = None
    if a.loadbalancing_actief and a.lb_warmtepomp:
        ruimte = (a.hoofdzekering_a - a.loadbalancing_marge_a) * a.spanning_v / 1000.0 - huishouden
        if cfg.warmtepomp.fase in (1, 2, 3):
            wp_plafond = ruimte[:, cfg.warmtepomp.fase - 1]
        else:
            # Driefasig: gelijk verdeeld, dus de krapste fase bepaalt het totaal.
            wp_plafond = ruimte.min(axis=1) * 3.0
    wp = warmtepomp_profiel(cfg.huis, cfg.warmtepomp, temp, ghi, lokaal_uur, dag_nr, dt_h, wp_plafond)
    wp_fasen = over_fasen(wp["elektrisch_kw"] + wp["bijverwarming_kw"], cfg.warmtepomp.fase)

    basis = Basis(
        index=index,
        lokaal=lokaal,
        dt_h=dt_h,
        stappen_per_uur=spu,
        lokaal_uur=lokaal_uur,
        dag_nr=dag_nr,
        dag_begin=dag_begin,
        weekdag=weekdag,
        temp_c=temp,
        ghi=ghi,
        prijs_markt=prijs,
        pv_dc_velden=pv_velden,
        huishouden=huishouden,
        warmtepomp=wp,
        warmtepomp_fasen=wp_fasen,
    )
    if len(_basis_voorraad) >= 8:
        _basis_voorraad.pop(next(iter(_basis_voorraad)))
    _basis_voorraad[sleutel] = basis
    return basis


def prijzen_per_stap(cfg: Config, prijs_markt: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Geeft per stap wat een kWh kost en wat een teruggeleverde kWh oplevert.

    Salderen wordt per kWh verrekend: een teruggeleverde kWh is dan evenveel
    waard als een afgenomen kWh op dat moment. Dat klopt zolang er over het
    jaar niet meer wordt teruggeleverd dan afgenomen; ``resultaat`` meldt het
    als dat niet zo is.

    Returns:
        ``koop`` en ``verkoop``, beide in euro per kWh.
    """
    t = cfg.tarieven
    if t.contract == "vast":
        koop = np.full(len(prijs_markt), t.vaste_prijs)
        verkoop = koop.copy() if t.salderen else np.full(len(prijs_markt), t.vaste_terugleverprijs)
        return koop, verkoop

    koop = (prijs_markt + t.inkoopopslag + t.energiebelasting) * (1.0 + t.btw)
    if t.salderen:
        # Met salderen krijgt de klant ook belasting en btw terug.
        verkoop = (prijs_markt - t.terugleveropslag + t.energiebelasting) * (1.0 + t.btw)
    else:
        # Zonder salderen: alleen de kale marktprijs, min de opslag. Bij een
        # negatieve marktprijs kost terugleveren dus geld.
        verkoop = prijs_markt - t.terugleveropslag
    return koop, verkoop


def netspanning_straat(cfg: Config, ghi: np.ndarray, dag_nr: np.ndarray) -> np.ndarray:
    """Geeft de netspanning in de straat bij netcongestie, zonder dit huis.

    Waarom zo:
        Overspanning ontstaat doordat alle panelen in de wijk tegelijk
        terugleveren. Hoeveel ze leveren volgt de zonnestraling, dus de
        spanning doet dat ook: rustspanning plus een stijging die evenredig is
        met de straling. Boven het plafond komt ze niet, omdat de omvormers van
        de buren dan zelf al zijn uitgeschakeld. Een toevallige afwijking per
        dag staat voor het wisselende verbruik in de wijk.

        Het patroon dat hieruit volgt is het bekende: geen probleem in de
        winter en op bewolkte dagen, en op heldere zomerdagen een blok
        overspanning rond het middaguur.

    Args:
        cfg: de instelling (netcongestie en seed).
        ghi: zonnestraling op een horizontaal vlak (W/m²).
        dag_nr: volgnummer van de dag bij elke waarde van ``ghi``.

    Returns:
        De spanning in volt, één waarde per waarde van ``ghi``.
    """
    nc = cfg.netcongestie
    rng = np.random.default_rng([cfg.algemeen.seed, 3])
    per_dag = rng.normal(0.0, nc.dagvariatie_v, size=int(np.max(dag_nr)) + 1)
    spanning = nc.rustspanning_v + nc.stijging_v_per_1000wm2 * ghi / 1000.0 + per_dag[dag_nr]
    return np.minimum(spanning, nc.plafond_v)


def bouw_profielen(cfg: Config, weer: pd.DataFrame, prijzen: pd.DataFrame) -> Profielen:
    """Maakt de profielen compleet: zon per fase, laadpaal en tarieven."""
    basis = bouw_basis(cfg, weer, prijzen)
    n = len(basis.index)
    b = cfg.batterij
    # Zonder batterij is er ook geen hybride omvormer: de panelen hebben dan
    # altijd hun eigen omvormer.
    hybride = b.aanwezig and b.koppeling == "hybride"

    pv_ac = np.zeros((n, 3))
    pv_dc = np.zeros((n, 3))
    pv_potentieel = np.zeros(n)
    for veld, dc in zip(cfg.zon.velden, basis.pv_dc_velden):
        pv_potentieel += dc
        if hybride:
            via_mppt = dc * cfg.zon.mppt_rendement
            if b.topologie == "1x3":
                # Eén gezamenlijke DC-rail: de zonnestroom is van alle drie
                # de omvormers, welke fase het veld "heeft" doet er niet toe.
                pv_dc += over_fasen(via_mppt, 0)
            else:
                # Drie losse systemen: het veld hangt aan de omvormer van zijn fase.
                pv_dc += over_fasen(via_mppt, veld.fase)
        else:
            piek_kw = veld.aantal_panelen * veld.wp_per_paneel / 1000.0
            # De PV-omvormer kan niet meer leveren dan zijn eigen AC-vermogen.
            ac = np.minimum(dc * cfg.zon.pv_omvormer_rendement, piek_kw * cfg.zon.pv_omvormer_verhouding)
            pv_ac += over_fasen(ac, veld.fase)

    koop, verkoop = prijzen_per_stap(cfg, basis.prijs_markt)

    # Wat de laadpaal "ziet": de overige lasten min de zonneproductie zoals
    # die zonder batterij op het net zou komen.
    pv_zichtbaar = np.minimum(pv_dc * b.omvormer_rendement, b.omvormer_kw_per_fase) if hybride else pv_ac
    overig = basis.huishouden + basis.warmtepomp_fasen - pv_zichtbaar

    rng_auto = np.random.default_rng([cfg.algemeen.seed, 2])
    thuis, verreden = auto_mod.rijschema(
        cfg.auto, basis.dag_begin, basis.lokaal_uur, basis.weekdag, n, basis.dt_h, rng_auto
    )
    auto = auto_mod.laad_profiel(cfg.auto, cfg.aansluiting, thuis, verreden, overig, koop, basis.dt_h)

    # Zonder netcongestie staat het net gewoon op zijn nominale spanning.
    if cfg.netcongestie.actief:
        spanning_net = netspanning_straat(cfg, basis.ghi, basis.dag_nr)
    else:
        spanning_net = np.full(n, cfg.aansluiting.spanning_v)

    return Profielen(
        basis=basis,
        hybride=hybride,
        spanning_net=spanning_net,
        pv_ac=pv_ac,
        pv_dc=pv_dc,
        pv_potentieel=pv_potentieel,
        auto=auto,
        auto_thuis=thuis,
        last=basis.huishouden + basis.warmtepomp_fasen + auto["per_fase"],
        koop=koop,
        verkoop=verkoop,
    )


# ---------------------------------------------------------------------------
# Handelsplan
# ---------------------------------------------------------------------------


def plan_handel(
    energie_nu: float,
    energie_min: float,
    energie_max: float,
    vermogen_max_kw: float,
    rendement_enkel: float,
    slijtage_eur_per_kwh: float,
    netto_kwh: np.ndarray,
    koop: np.ndarray,
    verkoop: np.ndarray,
) -> np.ndarray:
    """Maakt het goedkoopste laad- en ontlaadplan voor de komende uren.

    Waarom zo:
        Handelen is: laden als stroom goedkoop is en ontladen als ze duur is,
        maar alleen als het prijsverschil de verliezen en de slijtage goedmaakt
        en er op het goede moment ruimte in de batterij is. Een vaste regel
        ("laad de vier goedkoopste uren") houdt daar geen rekening mee. Dit plan
        rekent daarom alle mogelijkheden door met dynamisch programmeren: de
        laadtoestand wordt in een vast aantal niveaus verdeeld, en van achter
        naar voren wordt per uur en per niveau de goedkoopste vervolgstap
        bepaald.

        Het eigen verbruik en de eigen zonneproductie van dat uur tellen mee:
        ontladen naar het eigen huis bespaart de volle inkoopprijs, ontladen
        naar het net levert alleen de terugleverprijs op.

    Args:
        energie_nu: energie in de batterij op dit moment (kWh).
        energie_min, energie_max: grenzen van de bruikbare energie (kWh).
        vermogen_max_kw: grootste laad- en ontlaadvermogen aan de AC-kant.
        rendement_enkel: rendement in één richting (omvormer maal accu).
        slijtage_eur_per_kwh: slijtagekosten per kWh die door de accu gaat.
        netto_kwh: per uur de verwachte afname van het huis zonder batterij
            (negatief = overschot).
        koop, verkoop: prijzen per uur.

    Returns:
        Per uur het batterijvermogen aan de AC-kant in kW (positief = ontladen).
    """
    uren = len(netto_kwh)
    plan = np.zeros(uren)
    bereik = energie_max - energie_min
    if uren == 0 or bereik <= 1e-9 or vermogen_max_kw <= 0:
        return plan

    stap = bereik / (PLAN_NIVEAUS - 1)
    niveau = np.arange(PLAN_NIVEAUS)
    # verschil[van, naar]: verandering van de energie in de accu (kWh) in één
    # uur; positief = laden.
    verschil = (niveau[None, :] - niveau[:, None]) * stap
    # Wat dat aan de AC-kant betekent: laden kost meer dan er in de accu komt,
    # ontladen levert minder dan eruit gaat. Positief = ontladen.
    ac_kwh = np.where(verschil > 0, -verschil / rendement_enkel, -verschil * rendement_enkel)
    # Overgangen die meer vermogen vragen dan er is, zijn niet toegestaan.
    vast = np.where(np.abs(ac_kwh) <= vermogen_max_kw + 1e-9, np.abs(verschil) * slijtage_eur_per_kwh / 2.0, np.inf)

    # Van achter naar voren: wat kost de rest van de periode vanaf elk niveau?
    restkosten = np.zeros(PLAN_NIVEAUS)
    keuze = np.empty((uren, PLAN_NIVEAUS), dtype=int)
    for uur in range(uren - 1, -1, -1):
        net = netto_kwh[uur] - ac_kwh
        kosten = np.where(net > 0, net * koop[uur], net * verkoop[uur]) + vast + restkosten[None, :]
        keuze[uur] = np.argmin(kosten, axis=1)
        restkosten = kosten[niveau, keuze[uur]]

    # Van voren naar achteren: volg vanaf de huidige laadtoestand de beste keuzes.
    nu = int(round((energie_nu - energie_min) / stap))
    nu = min(max(nu, 0), PLAN_NIVEAUS - 1)
    for uur in range(uren):
        naar = keuze[uur, nu]
        plan[uur] = ac_kwh[nu, naar]
        nu = naar
    return plan


# ---------------------------------------------------------------------------
# Stap 2: de batterij
# ---------------------------------------------------------------------------


def simuleer(cfg: Config, prof: Profielen) -> Uitkomst:
    """Laat de batterij los op de profielen en geeft het verloop per stap.

    De kolommen van ``Uitkomst.reeksen`` (vermogens in kW):
        ``net_l1..3``        afname van het net per fase (negatief = terugleveren)
        ``net``              som van de drie fasen
        ``stroom_l1..3``     stroom per fase in A (met teken)
        ``huishouden``, ``warmtepomp``, ``auto``   verbruik per onderdeel
        ``zon``              benutte zonneproductie (na afregelen)
        ``afgeregeld``       zonneproductie die verloren ging door een te kleine omvormer
                             of door de load balancing van de panelen
        ``uitgeschakeld``    zonneproductie die verloren ging door overspanning
        ``spanning_straat``  netspanning in de straat, zonder dit huis (V)
        ``spanning_l1..3``   spanning op de eigen aansluiting per fase (V)
        ``batterij``         batterijvermogen aan de DC-kant (positief = ontladen)
        ``soc``              laadtoestand van de hele batterij in %
        ``soc_l1..3``        laadtoestand per batterij (alleen bij 3 batterijen)
        ``koop``, ``verkoop``  prijzen in euro per kWh
        ``kosten``           kosten van deze stap in euro (negatief = opbrengst)
    """
    basis = prof.basis
    n = len(basis.index)
    dt = basis.dt_h
    spu = basis.stappen_per_uur
    b = cfg.batterij
    aansl = cfg.aansluiting

    capaciteit = b.capaciteit_kwh if b.aanwezig else 0.0
    heeft_eenheden = capaciteit > 0 or prof.hybride
    eta = b.omvormer_rendement
    # Het accurendement geldt heen en terug samen; per richting de wortel.
    eta_accu = math.sqrt(b.batterij_rendement)
    p_omvormer = b.omvormer_kw_per_fase if heeft_eenheden else 0.0

    # Welke eenheden delen een accu? Eén groep van drie, of drie groepen van één.
    groepen = [[0, 1, 2]] if b.topologie == "1x3" else [[0], [1], [2]]
    cap_groep = [capaciteit * len(g) / 3.0 for g in groepen]
    e_min = [c * b.min_soc_pct / 100.0 for c in cap_groep]
    e_max = [c * b.max_soc_pct / 100.0 for c in cap_groep]
    energie = [min(max(c * b.start_soc_pct / 100.0, lo), hi) for c, lo, hi in zip(cap_groep, e_min, e_max)]
    p_accu = [c * b.max_c_rate for c in cap_groep]

    # Verbruik per fase, met het stand-by-verbruik van de omvormers erbij. De
    # AC-gekoppelde zonneproductie blijft apart, omdat die bij overspanning
    # per fase kan wegvallen.
    standby = b.standby_w_per_omvormer / 1000.0 if heeft_eenheden else 0.0
    vraag = (prof.last + standby).tolist()
    pv_ac = prof.pv_ac.tolist()
    pv_dc = prof.pv_dc.tolist()
    hybride = prof.hybride

    # Netcongestie: spanning in de straat, de uitschakelgrens van de
    # omvormers, en hoeveel de eigen stroom de spanning verschuift.
    nc = cfg.netcongestie
    congestie = nc.actief
    spanning_straat = prof.spanning_net.tolist()
    uitschakel_v = cfg.zon.uitschakelspanning_v
    # Volt verschuiving per kW op één fase (afname verlaagt de spanning).
    volt_per_kw = 1000.0 / aansl.spanning_v * nc.netimpedantie_ohm
    steun = congestie and capaciteit > 0 and b.spanningssteun and volt_per_kw > 0
    steun_doel_v = uitschakel_v - b.spanningssteun_marge_v

    strategie = b.strategie if capaciteit > 0 else "geen"
    per_fase = b.regeling == "per_fase"
    piek_fase = b.piekgrens_kw / 3.0
    # Load balancing: grootste vermogen per fase, in beide richtingen.
    lb = aansl.loadbalancing_actief
    lb_batterij = lb and aansl.lb_batterij and capaciteit > 0
    lb_zon = lb and aansl.lb_zonnepanelen
    p_grens = (aansl.hoofdzekering_a - aansl.loadbalancing_marge_a) * aansl.spanning_v / 1000.0

    # Voorbereiding voor het handelsplan: de afname zonder batterij per uur.
    plan = np.zeros(n // spu)
    if strategie == "handel":
        zonder = prof.last.sum(axis=1) + 3 * standby - prof.pv_ac.sum(axis=1)
        zonder -= np.minimum(prof.pv_dc * eta, p_omvormer).sum(axis=1)
        netto_uur = zonder.reshape(-1, spu).mean(axis=1)
        koop_uur = prof.koop.reshape(-1, spu).mean(axis=1)
        verkoop_uur = prof.verkoop.reshape(-1, spu).mean(axis=1)
        handel_vermogen = min(3 * p_omvormer, sum(p_accu))
    lokaal_uur = basis.lokaal_uur.tolist()

    net_reeks = [[0.0] * n for _ in range(3)]
    batterij_reeks = [0.0] * n
    afgeregeld_reeks = [0.0] * n
    soc_reeks = [[0.0] * n for _ in groepen]

    spanning_reeks = [[0.0] * n for _ in range(3)]
    uitgeschakeld_reeks = [0.0] * n

    wens = [0.0, 0.0, 0.0]
    accu_dc = [0.0, 0.0, 0.0]
    ac_uit = [0.0, 0.0, 0.0]
    energie_nieuw = list(energie)
    # Per fase: mogen de panelen deze stap leveren? Bij overspanning gaat de
    # vlag van die fase uit en wordt de stap opnieuw gerekend.
    aan = [True, True, True]
    opnieuw = False

    # Een while-lus in plaats van een for-lus, omdat een stap bij overspanning
    # twee keer gerekend wordt: eerst met de panelen aan, en als de spanning
    # dan te hoog blijkt nog een keer met de panelen van die fase uit. Tot de
    # stap is afgerond, wordt er niets definitief geboekt.
    k = 0
    while k < n:
        vraag_k = vraag[k]
        pv_k = pv_dc[k]
        pv_ac_k = pv_ac[k]
        if not opnieuw:
            aan[0] = aan[1] = aan[2] = True

        if (
            strategie == "handel"
            and not opnieuw
            and k % spu == 0
            and (k == 0 or lokaal_uur[k] == PRIJZEN_BEKEND_UUR)
        ):
            # Nieuw plan zodra de prijzen van morgen bekend zijn. Het plan
            # loopt tot het eind van de laatste dag waarvan de prijzen bekend
            # zijn: bij de start is dat vandaag, om 13:00 is dat morgen.
            uur_nu = k // spu
            vooruit = int(24 - lokaal_uur[k]) + (24 if k > 0 else 0)
            eind = min(uur_nu + vooruit, len(plan))
            plan[uur_nu:eind] = plan_handel(
                sum(energie),
                sum(e_min),
                sum(e_max),
                handel_vermogen,
                eta * eta_accu,
                b.slijtage_eur_per_kwh,
                netto_uur[uur_nu:eind],
                koop_uur[uur_nu:eind],
                verkoop_uur[uur_nu:eind],
            )

        # --- 1. Wat zou er zonder batterij over elke fase lopen? ------------
        # (verbruik min de zonnestroom: van de PV-omvormer als die aan staat,
        # en wat de eenheid bij een hybride opstelling vanzelf doorgeeft)
        rest0 = vraag_k[0] - (pv_ac_k[0] if aan[0] else 0.0) - pv_k[0] * eta
        rest1 = vraag_k[1] - (pv_ac_k[1] if aan[1] else 0.0) - pv_k[1] * eta
        rest2 = vraag_k[2] - (pv_ac_k[2] if aan[2] else 0.0) - pv_k[2] * eta

        # --- 2. Wat wil de regelstrategie dat de batterij doet? -------------
        # (positief = ontladen, aan de AC-kant)
        if strategie == "eigen_verbruik":
            # Elke fase (of het totaal) naar nul: laden bij overschot,
            # ontladen bij tekort.
            if per_fase:
                wens[0], wens[1], wens[2] = rest0, rest1, rest2
            else:
                wens[0] = wens[1] = wens[2] = (rest0 + rest1 + rest2) / 3.0
        elif strategie == "piek_shaving":
            # Boven de grens: het teveel uit de batterij. Onder de grens:
            # bijladen tot aan de grens, of alleen met overschot.
            if per_fase:
                for i, rest in enumerate((rest0, rest1, rest2)):
                    if rest > piek_fase:
                        wens[i] = rest - piek_fase
                    elif b.herladen_uit_net:
                        wens[i] = rest - piek_fase
                    else:
                        wens[i] = rest if rest < 0 else 0.0
            else:
                som = rest0 + rest1 + rest2
                if som > b.piekgrens_kw or b.herladen_uit_net:
                    totaal = som - b.piekgrens_kw
                else:
                    totaal = som if som < 0 else 0.0
                wens[0] = wens[1] = wens[2] = totaal / 3.0
        elif strategie == "handel":
            wens[0] = wens[1] = wens[2] = plan[k // spu] / 3.0
        else:
            wens[0] = wens[1] = wens[2] = 0.0

        # --- 2b. Spanningssteun: de panelen aan het net houden ---------------
        if steun:
            # Hoeveel moet deze fase van het net afnemen om de spanning op de
            # aansluiting onder de uitschakelgrens te houden? Is de afname
            # kleiner (of wordt er teruggeleverd), dan laadt de batterij het
            # verschil bij. Alleen op fasen waar nu zon is: anders valt er
            # niets te redden. Lukt het niet (batterij vol, omvormer te
            # klein), dan schakelen de panelen alsnog uit en wordt de stap
            # opnieuw gerekend zonder deze steun.
            #
            #
            # Ligt de straat zelf al boven de grens, dan moet er stroom uit
            # het net de batterij in om de spanning omlaag te trekken. Of dat
            # loont, verschilt per architectuur (nagerekend op het jaar 2025):
            # - Aparte omvormers: ja. Zonder steun staat de PV-omvormer uit en
            #   is alle zon van die fase weg; met steun blijft hij aan.
            # - Hybride: nee. Een afgeschakelde hybride omvormer laadt de accu
            #   toch al met zonnestroom aan de DC-kant. Netstroom erbij halen
            #   vult de accu alleen maar sneller, waarna de zon alsnog verloren
            #   gaat. Daarom hier alleen steun als er niets uit het net bij
            #   hoeft: de teruglevering beperken is dan genoeg.
            nodig = (spanning_straat[k] - steun_doel_v) / volt_per_kw
            for i, rest in enumerate((rest0, rest1, rest2)):
                if not aan[i] or rest - wens[i] >= nodig:
                    continue
                if (pv_k[i] > 0 and nodig <= 0) if hybride else pv_ac_k[i] > 0:
                    wens[i] = rest - nodig

        # --- 3. Load balancing gaat boven de strategie -----------------------
        # (alleen als de batterij meedoet aan de load balancing)
        if lb_batterij:
            for i, rest in enumerate((rest0, rest1, rest2)):
                if rest - wens[i] > p_grens:
                    # De fase zou over de grens gaan: ontladen (of minder
                    # laden) tot precies op de grens.
                    wens[i] = rest - p_grens
                elif rest - wens[i] < -p_grens:
                    # Te veel teruglevering op deze fase: het teveel de batterij in.
                    wens[i] = rest + p_grens

        # --- 4. Wat vraagt dat van de accu, per eenheid? ---------------------
        for i in range(3):
            # Gewenst AC-vermogen van de eenheid: zonnestroom plus batterij,
            # begrensd door wat de omvormer aankan.
            ac = pv_k[i] * eta + wens[i]
            if ac > p_omvormer:
                ac = p_omvormer
            elif ac < -p_omvormer:
                ac = -p_omvormer
            if hybride and not aan[i] and ac > 0:
                # Een hybride omvormer die door overspanning is afgeschakeld
                # levert niets aan de AC-kant. De zonnestroom kan dan alleen
                # nog aan de DC-kant de accu in.
                ac = 0.0
            # Terug naar de DC-kant; het verschil met de zonnestroom komt
            # uit (positief) of gaat in (negatief) de accu.
            dc = ac / eta if ac >= 0 else ac * eta
            accu_dc[i] = dc - pv_k[i]

        # --- 5. Kan de accu dat leveren? --------------------------------------
        totaal_accu = 0.0
        for g, leden in enumerate(groepen):
            max_ontladen = min(p_accu[g], (energie[g] - e_min[g]) * eta_accu / dt)
            max_laden = min(p_accu[g], (e_max[g] - energie[g]) / (eta_accu * dt))
            if max_ontladen < 0:
                max_ontladen = 0.0
            if max_laden < 0:
                max_laden = 0.0
            som = 0.0
            plus = 0.0
            for i in leden:
                som += accu_dc[i]
                if accu_dc[i] > 0:
                    plus += accu_dc[i]
            min_ = som - plus
            if som > max_ontladen:
                # Te veel gevraagd: de ontladende eenheden leveren naar rato in.
                factor = (max_ontladen - min_) / plus
                for i in leden:
                    if accu_dc[i] > 0:
                        accu_dc[i] *= factor
                som = max_ontladen
            elif som < -max_laden:
                # Te veel aangeboden: de ladende eenheden nemen naar rato minder.
                factor = (-max_laden - plus) / min_
                for i in leden:
                    if accu_dc[i] < 0:
                        accu_dc[i] *= factor
                som = -max_laden
            # Bereken de nieuwe energie: ontladen kost meer dan er uitkomt,
            # laden levert minder op dan erin gaat. Nog niet definitief: bij
            # overspanning wordt de stap opnieuw gerekend.
            if som > 0:
                energie_nieuw[g] = energie[g] - som / eta_accu * dt
            else:
                energie_nieuw[g] = energie[g] - som * eta_accu * dt
            totaal_accu += som
            soc_reeks[g][k] = 100.0 * energie_nieuw[g] / cap_groep[g] if cap_groep[g] > 0 else 0.0

        # --- 6. Wat komt er dus werkelijk uit elke eenheid? ------------------
        afgeregeld = 0.0
        uitgeschakeld = 0.0
        for i in range(3):
            dc = pv_k[i] + accu_dc[i]
            if dc >= 0:
                ac = dc * eta
                if hybride and not aan[i]:
                    # Afgeschakelde hybride omvormer: wat de accu niet kon
                    # opnemen, gaat verloren.
                    uitgeschakeld += dc
                    ac = 0.0
                elif ac > p_omvormer:
                    # Meer zon dan de omvormer kwijt kan en de accu kan
                    # opnemen: de panelen worden teruggeregeld.
                    afgeregeld += dc - p_omvormer / eta
                    ac = p_omvormer
            else:
                ac = dc / eta
            ac_uit[i] = ac
            if aan[i]:
                net_reeks[i][k] = vraag_k[i] - pv_ac_k[i] - ac
            else:
                # De PV-omvormer van deze fase staat uit: zijn productie is weg.
                net_reeks[i][k] = vraag_k[i] - ac
                uitgeschakeld += pv_ac_k[i]

            if lb_zon and net_reeks[i][k] < -p_grens:
                # Load balancing van de zonnepanelen: de teruglevering op deze
                # fase zou over de grens gaan, dus de panelen regelen terug.
                # Dit komt na de batterij: wat die kon opnemen, is al van de
                # teruglevering af. Er kan niet meer worden teruggeregeld dan
                # de panelen op deze fase nu leveren.
                teveel = -p_grens - net_reeks[i][k]
                if hybride:
                    minder = min(teveel, ac if ac > 0 else 0.0)
                    afgeregeld += minder / eta
                    ac_uit[i] = ac - minder
                else:
                    minder = min(teveel, pv_ac_k[i] if aan[i] else 0.0)
                    afgeregeld += minder
                net_reeks[i][k] += minder

        # --- 7. Netcongestie: houdt de spanning het? -------------------------
        if congestie:
            te_hoog = False
            for i in range(3):
                # Spanning op de eigen aansluiting: die van de straat, omlaag
                # door afname en omhoog door teruglevering.
                spanning = spanning_straat[k] - net_reeks[i][k] * volt_per_kw
                spanning_reeks[i][k] = spanning
                # Een omvormer die nu levert en boven de grens zit, moet eraf:
                # de PV-omvormer van deze fase, of de hybride omvormer.
                levert = ac_uit[i] > 0 and pv_k[i] > 0 if hybride else pv_ac_k[i] > 0
                if aan[i] and levert and spanning > uitschakel_v:
                    aan[i] = False
                    te_hoog = True
            if te_hoog and not opnieuw:
                # Dezelfde stap nog een keer, nu met die fase(n) uit. Daarna
                # staat de uitkomst vast: een tweede herhaling is er niet.
                opnieuw = True
                continue
        else:
            for i in range(3):
                spanning_reeks[i][k] = spanning_straat[k]

        # --- 8. De stap is rond: boek hem definitief -------------------------
        for g in range(len(groepen)):
            energie[g] = energie_nieuw[g]
        batterij_reeks[k] = totaal_accu
        afgeregeld_reeks[k] = afgeregeld
        uitgeschakeld_reeks[k] = uitgeschakeld
        opnieuw = False
        k += 1

    # --- Reeksen samenstellen ------------------------------------------------
    net = np.array(net_reeks).T
    afgeregeld_np = np.array(afgeregeld_reeks)
    reeksen = pd.DataFrame(index=basis.lokaal)
    for i in range(3):
        reeksen[f"net_l{i + 1}"] = net[:, i]
    reeksen["net"] = net.sum(axis=1)
    for i in range(3):
        reeksen[f"stroom_l{i + 1}"] = net[:, i] * 1000.0 / aansl.spanning_v
    reeksen["huishouden"] = basis.huishouden.sum(axis=1)
    reeksen["warmtepomp"] = basis.warmtepomp_fasen.sum(axis=1)
    reeksen["auto"] = prof.auto["per_fase"].sum(axis=1)
    uitgeschakeld_np = np.array(uitgeschakeld_reeks)
    reeksen["zon"] = prof.pv_ac.sum(axis=1) + prof.pv_dc.sum(axis=1) - afgeregeld_np - uitgeschakeld_np
    reeksen["afgeregeld"] = afgeregeld_np
    reeksen["uitgeschakeld"] = uitgeschakeld_np
    reeksen["spanning_straat"] = prof.spanning_net
    for i in range(3):
        reeksen[f"spanning_l{i + 1}"] = spanning_reeks[i]
    reeksen["batterij"] = batterij_reeks
    cap_totaal = sum(cap_groep)
    if cap_totaal > 0:
        reeksen["soc"] = sum(np.array(s) * c for s, c in zip(soc_reeks, cap_groep)) / cap_totaal
    else:
        reeksen["soc"] = 0.0
    if len(groepen) == 3:
        for i in range(3):
            reeksen[f"soc_l{i + 1}"] = soc_reeks[i]
    reeksen["koop"] = prof.koop
    reeksen["verkoop"] = prof.verkoop
    # De meter telt de drie fasen bij elkaar op: afname op de ene fase en
    # teruglevering op de andere vallen op hetzelfde moment tegen elkaar weg.
    reeksen["kosten"] = np.where(reeksen["net"] > 0, reeksen["net"] * prof.koop, reeksen["net"] * prof.verkoop) * dt

    return Uitkomst(cfg=cfg, profielen=prof, reeksen=reeksen)


def zonder_batterij(cfg: Config) -> Config:
    """Geeft dezelfde instelling zonder batterij: de referentie voor elke vergelijking."""
    referentie = cfg.kopie()
    referentie.batterij.aanwezig = False
    return referentie


def voer_uit(cfg: Config, weer: pd.DataFrame, prijzen: pd.DataFrame) -> Uitkomst:
    """Doet een complete simulatie en rekent de kentallen uit.

    Dit is de ene ingang voor de app, de scenariovergelijking en de tests.
    """
    # Hier geïmporteerd omdat ``resultaat`` op zijn beurt de types van deze
    # module gebruikt.
    from .resultaat import bereken_kentallen

    uitkomst = simuleer(cfg, bouw_profielen(cfg, weer, prijzen))
    uitkomst.kentallen = bereken_kentallen(uitkomst)
    return uitkomst
