"""Warmtevraag van het huis en het stroomverbruik van de warmtepomp.

Waarom dit bestaat:
    Het verbruik van de warmtepomp is in de winter de grootste last in huis en
    valt juist dan als de zon weinig levert. Om dat verbruik uit het weer te
    kunnen afleiden, wordt het huis hier beschreven met een paar kentallen
    (oppervlak, Rc-waarde, ramen, ventilatie).

Het model:
    Het huis is één warmtevoorraad met één temperatuur (een "1R1C-model"): het
    verliest warmte naar buiten in verhouding tot het temperatuurverschil, en
    krijgt warmte van de warmtepomp, de zon door de ramen en de bewoners.

    Afgewezen: de warmtevraag direct uit graaddagen berekenen. Dat geeft een
    goed jaartotaal, maar geen binnentemperatuur en geen aan- en afschakelende
    compressor, en dus geen realistische vermogenspieken per fase.
"""

from __future__ import annotations

import numpy as np

from .config import Huis, Warmtepomp

# Warmtecapaciteit van lucht per m³ per graad, in Wh.
LUCHT_WH_M3K = 0.34


def warmteverlies_w_per_k(huis: Huis) -> float:
    """Geeft het warmteverlies van het huis in watt per graad temperatuurverschil.

    Drie wegen waarlangs warmte weglekt: door de dichte schil (oppervlak
    gedeeld door Rc), door de ramen (oppervlak maal U-waarde) en met de
    ventilatielucht (voor zover een WTW die niet terugwint).
    """
    schil_m2 = max(huis.vloeroppervlak_m2 * huis.schilfactor - huis.raamoppervlak_m2, 0.0)
    door_schil = schil_m2 / max(huis.rc_waarde, 0.1)
    door_ramen = huis.raamoppervlak_m2 * huis.u_raam
    volume_m3 = huis.vloeroppervlak_m2 * huis.plafondhoogte_m
    teruggewonnen = huis.wtw_rendement if huis.wtw_aanwezig else 0.0
    door_ventilatie = LUCHT_WH_M3K * huis.ventilatievoud * volume_m3 * (1.0 - teruggewonnen)
    return door_schil + door_ramen + door_ventilatie


def cop_bij(wp: Warmtepomp, buiten_c: float) -> float:
    """Geeft de COP van de warmtepomp bij een buitentemperatuur.

    De ingestelde COP geldt bij 7 °C buiten. Voor andere temperaturen wordt hij
    geschaald met het theoretische (Carnot-)rendement: hoe groter het verschil
    tussen bron en afgifte, hoe lager de COP. De toeslagen van 3 en 5 graden
    zijn de temperatuurverschillen over de warmtewisselaars.
    """
    if not wp.cop_temperatuurafhankelijk:
        return wp.cop_nominaal

    afgifte_k = wp.aanvoertemperatuur_c + 3.0 + 273.15

    def carnot(buiten: float) -> float:
        bron_k = buiten - 5.0 + 273.15
        return afgifte_k / max(afgifte_k - bron_k, 5.0)

    cop = wp.cop_nominaal * carnot(buiten_c) / carnot(7.0)
    return min(max(cop, 1.5), 8.0)


def warmtepomp_profiel(
    huis: Huis,
    wp: Warmtepomp,
    temp_c: np.ndarray,
    ghi: np.ndarray,
    lokaal_uur: np.ndarray,
    dag_nr: np.ndarray,
    dt_h: float,
    max_elektrisch_kw: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Rekent stap voor stap door wat de warmtepomp doet.

    Met ``max_elektrisch_kw`` doet de warmtepomp mee aan de load balancing:
    per stap mag hij (compressor en bijverwarming samen) niet meer stroom
    nemen dan die waarde. Hij levert dan minder warmte; het huis koelt iets af
    en de regeling haalt het vanzelf in zodra er weer ruimte is.

    Args:
        huis: kentallen van het huis.
        wp: instellingen van de warmtepomp.
        temp_c: buitentemperatuur per stap.
        ghi: zonnestraling op een horizontaal vlak per stap (W/m²).
        lokaal_uur: uur van de dag in lokale tijd per stap (0..24).
        dag_nr: volgnummer van de lokale dag per stap.
        dt_h: lengte van een stap in uren.
        max_elektrisch_kw: grootste stroomverbruik per stap (kW), of None als
            de warmtepomp niet meedoet aan de load balancing.

    Returns:
        Reeksen per stap: ``elektrisch_kw`` (compressor), ``bijverwarming_kw``
        (elektrisch element), ``warmte_kw`` (geleverde warmte voor het huis),
        ``tapwater_kw`` (geleverde warmte voor tapwater), ``cop`` en
        ``binnen_c``.
    """
    n = len(temp_c)
    uit = {
        naam: np.zeros(n)
        for naam in ("elektrisch_kw", "bijverwarming_kw", "warmte_kw", "tapwater_kw", "cop", "binnen_c")
    }
    if not wp.aanwezig:
        uit["binnen_c"][:] = huis.binnentemperatuur_c
        return uit

    verlies_kw_k = warmteverlies_w_per_k(huis) / 1000.0
    capaciteit_kwh_k = max(huis.vloeroppervlak_m2 * huis.warmtecapaciteit_wh_m2k / 1000.0, 0.5)
    gewenst = huis.binnentemperatuur_c
    p_max = wp.thermisch_vermogen_kw
    p_min = p_max * wp.min_modulatie

    # Warmte die er zonder verwarming al is: bewoners, apparaten en zon.
    gratis_kw = huis.interne_warmte_w / 1000.0 + ghi * huis.raamoppervlak_m2 * huis.zonwinst_factor / 1000.0

    # Gewone lijsten zijn in een Python-lus merkbaar sneller dan numpy-reeksen.
    temp = temp_c.tolist()
    gratis = gratis_kw.tolist()
    uur = lokaal_uur.tolist()
    dag = dag_nr.tolist()
    plafond = None if max_elektrisch_kw is None else np.clip(max_elektrisch_kw, 0.0, None).tolist()

    binnen = gewenst
    compressor_aan = False
    bijverwarming_aan = False
    tapwater_rest = 0.0
    vorige_dag = None

    for k in range(n):
        buiten = temp[k]
        if dag[k] != vorige_dag:
            # Nieuwe dag: de boiler moet vandaag weer één keer worden opgewarmd.
            vorige_dag = dag[k]
            # Alleen als de warmtepomp het tapwater maakt.
            tapwater_rest = wp.tapwater_kwh_per_dag if wp.tapwater_via_warmtepomp else 0.0

        warmte = 0.0
        tap = 0.0
        elektrisch = 0.0
        cop = cop_bij(wp, buiten)

        if tapwater_rest > 1e-9 and uur[k] >= wp.tapwater_startuur:
            # Tapwater gaat voor: de compressor kan maar één ding tegelijk. De
            # ruimteverwarming wacht; het huis koelt in dat halfuur nauwelijks af.
            tap = min(p_max, tapwater_rest / dt_h)
            tapwater_rest -= tap * dt_h
            elektrisch = tap / wp.tapwater_cop
            cop = wp.tapwater_cop
        else:
            # Hoeveel warmte is nodig om het huis op temperatuur te houden én
            # binnen één stap terug te brengen naar de gewenste temperatuur?
            nodig = verlies_kw_k * (gewenst - buiten) - gratis[k] + capaciteit_kwh_k * (gewenst - binnen) / dt_h
            if nodig >= p_min:
                # Genoeg vraag om te moduleren: de compressor levert precies
                # wat nodig is, tot zijn maximum.
                warmte = min(nodig, p_max)
                compressor_aan = True
            else:
                # Te weinig vraag voor de laagste stand: aan/uit met hysterese
                # rond de gewenste temperatuur.
                if compressor_aan and binnen >= gewenst + wp.hysterese_k:
                    compressor_aan = False
                elif not compressor_aan and binnen <= gewenst - wp.hysterese_k:
                    compressor_aan = True
                warmte = p_min if compressor_aan else 0.0
            elektrisch = warmte / cop

        # Bijverwarming: springt bij als het huis ondanks de warmtepomp ruim
        # onder de gewenste temperatuur zakt, en stopt als het bijna hersteld is.
        if binnen < gewenst - 1.5:
            bijverwarming_aan = True
        elif binnen >= gewenst - 0.5:
            bijverwarming_aan = False
        extra = wp.bijverwarming_kw if bijverwarming_aan else 0.0

        if plafond is not None:
            # Load balancing: eerst wordt de bijverwarming teruggenomen (die
            # levert het minst per kW stroom), daarna de compressor. Warmte en
            # tapwater krimpen in dezelfde verhouding mee.
            ruimte = plafond[k]
            if elektrisch > ruimte:
                factor = ruimte / elektrisch
                elektrisch = ruimte
                warmte *= factor
                if tap > 0:
                    # Wat nu niet in de boiler gaat, blijft voor straks staan.
                    tapwater_rest += tap * (1.0 - factor) * dt_h
                    tap *= factor
            if extra > ruimte - elektrisch:
                extra = ruimte - elektrisch

        # Warmtebalans van het huis over deze stap.
        binnen += (warmte + extra + gratis[k] - verlies_kw_k * (binnen - buiten)) * dt_h / capaciteit_kwh_k
        # In de zomer loopt de temperatuur door zonwinst op. Bewoners zetten
        # dan ramen open of doen de zonwering dicht; drie graden boven de
        # gewenste temperatuur is daarom het plafond.
        if binnen > gewenst + 3.0:
            binnen = gewenst + 3.0

        uit["elektrisch_kw"][k] = elektrisch
        uit["bijverwarming_kw"][k] = extra
        uit["warmte_kw"][k] = warmte
        uit["tapwater_kw"][k] = tap
        uit["cop"][k] = cop
        uit["binnen_c"][k] = binnen

    return uit
