"""Huishoudelijk verbruik: apparaten die op wisselende momenten aan- en afschakelen.

Waarom dit bestaat:
    Een gemiddeld verbruiksprofiel is glad, en een glad profiel laat een
    batterij en een hoofdzekering er te goed uitzien. In het echt staat de
    kookplaat een halfuur op 3,5 kW op één fase. Daarom wordt het verbruik hier
    opgebouwd uit losse apparaten, elk met een vermogen, een duur, een fase en
    een tijdvenster, die op toevallige momenten binnen dat venster starten.

    De toevalsgenerator krijgt een vaste startwaarde: dezelfde instelling geeft
    dus altijd precies hetzelfde profiel, zodat twee scenario's alleen
    verschillen in wat er bewust anders is ingesteld.
"""

from __future__ import annotations

import numpy as np

from .config import Huishouden


def over_fasen(vermogen_kw: np.ndarray, fase: int) -> np.ndarray:
    """Verdeelt een vermogensreeks over de drie fasen.

    Dit is de ene plek waar "fase 0 = driefasig" wordt uitgelegd; warmtepomp,
    zonnepanelen, laadpaal en apparaten gebruiken allemaal deze functie.

    Args:
        vermogen_kw: vermogen per stap.
        fase: 1, 2 of 3 voor één fase; 0 voor gelijk verdeeld over alle drie.

    Returns:
        Een tabel van (aantal stappen, 3) met het vermogen per fase.
    """
    per_fase = np.zeros((len(vermogen_kw), 3))
    if fase in (1, 2, 3):
        per_fase[:, fase - 1] = vermogen_kw
    else:
        per_fase[:] = (vermogen_kw / 3.0)[:, None]
    return per_fase


def huishoud_profiel(
    huishouden: Huishouden,
    dag_nr: np.ndarray,
    lokaal_uur: np.ndarray,
    dt_h: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Bouwt het huishoudelijk verbruik per fase op.

    Args:
        huishouden: basislast en de lijst apparaten.
        dag_nr: volgnummer van de lokale dag per stap (begint bij 0).
        lokaal_uur: uur van de dag in lokale tijd per stap.
        dt_h: lengte van een stap in uren.
        rng: toevalsgenerator.

    Returns:
        Een tabel van (aantal stappen, 3) met het vermogen per fase in kW.
    """
    n = len(dag_nr)
    profiel = np.zeros((n, 3))

    # De basislast staat altijd aan.
    for fase in range(3):
        profiel[:, fase] = huishouden.basislast_w[fase] / 1000.0

    # Eerste stap van elke lokale dag, om een starttijd om te rekenen naar
    # een plaats in de reeks.
    aantal_dagen = int(dag_nr[-1]) + 1
    dag_begin = np.searchsorted(dag_nr, np.arange(aantal_dagen))

    for apparaat in huishouden.apparaten:
        if apparaat.vermogen_w <= 0 or apparaat.duur_min <= 0 or apparaat.keer_per_week <= 0:
            continue
        # De duur wordt niet afgerond op hele stappen: een waterkoker van drie
        # minuten zou bij een stap van vijf minuten anders 67% te veel
        # verbruiken. In plaats daarvan krijgt de laatste stap een deel.
        duur_stappen = apparaat.duur_min / 60.0 / dt_h
        venster = max(apparaat.tot_uur - apparaat.van_uur, 0.0)

        # Aantal keer per dag: gemiddeld keer_per_week / 7, met toeval.
        keren = rng.poisson(apparaat.keer_per_week / 7.0, size=aantal_dagen)
        vermogen = np.zeros(n)
        for dag in np.nonzero(keren)[0]:
            for _ in range(keren[dag]):
                start_uur = apparaat.van_uur + rng.random() * venster
                begin = dag_begin[dag] + int(round((start_uur - lokaal_uur[dag_begin[dag]]) / dt_h))
                hele = int(duur_stappen)
                rest = duur_stappen - hele
                eind = min(begin + hele, n)
                if begin >= n or begin < 0:
                    continue
                # "Maximum" in plaats van optellen: hetzelfde apparaat kan niet
                # twee keer tegelijk aanstaan.
                vermogen[begin:eind] = apparaat.vermogen_w / 1000.0
                if rest > 1e-9 and eind < n:
                    vermogen[eind] = max(vermogen[eind], rest * apparaat.vermogen_w / 1000.0)
        profiel += over_fasen(vermogen, apparaat.fase)

    return profiel
