"""Fonction principale du module M3 : préparer le projet Brightway et calculer les bilans.

:func:`preparer_acv` lit les entrées actives, (re)construit le projet ``atlantic_biochar``
(méthode PRG100 AR6 et base ``ab_foreground``), calcule les scores unitaires des activités
agrégées avec Brightway et renvoie un :class:`ResultatAcv` qui donne le bilan de toute chaîne.
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from src.acv.bilan import _Calcul, bilans, charge_utile, facteur_reference
from src.acv.config import ConfigAcv
from src.acv.entrees import EntreesAcv, charger_entrees_acv
from src.acv.modele import (
    ScoresUnitaires,
    bilan_brightway,
    construire_avant_plan,
    creer_methode,
    ouvrir_projet,
    scores_unitaires,
)
from src.data.provenance import ValeurSourcee
from src.data.tables_reference import TableLongue


@dataclass(frozen=True)
class ResultatAcv:
    """Entrées, scores unitaires Brightway et configuration du bilan."""

    config: ConfigAcv
    entrees: EntreesAcv
    scores: ScoresUnitaires
    moins_fiable: Callable

    def bilans(self, distances: pd.DataFrame) -> pd.DataFrame:
        """Bilan de chaque couple × site de ``distances`` (table ``bilans``, section 13)."""
        return bilans(self.entrees, self.scores, distances, self.config, self.moins_fiable)

    def chaine_brightway(self, residu: str, distance_km: float) -> dict[str, float]:
        """Émissions par étape d'une chaîne, recalculées par Brightway (kg CO₂e/t biochar)."""
        q = charge_utile(self.entrees, residu, _Calcul(self.moins_fiable)) or 1.0
        return bilan_brightway(
            self.config,
            residu,
            distance_km,
            q,
            facteur_reference(self.entrees, residu, self.config),
        )


def preparer_acv(
    config: ConfigAcv,
    residus: TableLongue,
    facteurs: TableLongue,
    codes_residus: list[str],
    lire: Callable[[str], ValeurSourcee],
    unites_fraction: dict[str, float],
    moins_fiable: Callable,
) -> ResultatAcv:
    """Construit le projet Brightway et calcule les scores unitaires.

    Args:
        config: ``config/acv.yaml``.
        residus: ``residus.csv`` actif.
        facteurs: ``facteurs_emission.csv`` actif.
        codes_residus: codes des résidus du catalogue.
        lire: valeur d'un paramètre (entreprise, sinon technique).
        unites_fraction: conversions en fraction (``config/potentiel.yaml``).
        moins_fiable: statut le moins fiable d'une liste.
    """
    entrees = charger_entrees_acv(residus, facteurs, codes_residus, lire, config, unites_fraction)
    ouvrir_projet(config)
    creer_methode(config, entrees)
    construire_avant_plan(config, entrees, codes_residus)
    return ResultatAcv(config, entrees, scores_unitaires(config), moins_fiable)
