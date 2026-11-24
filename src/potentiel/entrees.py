"""Entrées du calcul des gisements, lues dans leur version active (RG-17)."""

from dataclasses import dataclass

import pandas as pd

from src.chemins import Chemins
from src.data.provinces import ErreurRattachement, Referentiel
from src.data.tables_reference import (
    Catalogue,
    TableLongue,
    TablesReference,
    charger_catalogue,
    charger_tables_reference,
)
from src.data.versions import Versions
from src.potentiel.config import ConfigPotentiel, charger_config_potentiel
from src.potentiel.theorique import CalculTheorique, resoudre_variantes
from src.scenarios.parametres import valeur_courante


@dataclass(frozen=True)
class EntreesPotentiel:
    """Tables, configuration et référentiel nécessaires aux calculs de la section 8.1."""

    chemins: Chemins
    tables: TablesReference
    catalogue: Catalogue
    config: ConfigPotentiel
    referentiel: Referentiel
    production: pd.DataFrame

    @property
    def region_de(self) -> dict[str, str]:
        """Code de région de chaque province (RG-02)."""
        provinces = self.referentiel.provinces
        return dict(
            zip(provinces["code_province"], provinces["code_region"].astype(str), strict=True)
        )

    def code_region(self, nom: str) -> str | None:
        """Code d'une région désignée par son nom ou une variante ; None si inconnue."""
        try:
            return self.referentiel.rattacher(pd.Series([nom]), "region")[0]
        except ErreurRattachement:
            return None

    def residus_retenus(self) -> TableLongue:
        """Table des résidus avec les variantes choisies (PAR-62, PAR-63) en valeur générale.

        À utiliser hors du calcul des gisements (logistique, bilan climat, mélange, décision),
        pour que tous les calculs lisent la même humidité que les gisements.
        """
        return resoudre_variantes(
            self.tables.residus,
            self.config,
            lambda identifiant: valeur_courante(self.chemins, identifiant),
        )

    def calcul_theorique(self) -> CalculTheorique:
        """Calcul du gisement théorique sur ces entrées."""
        return CalculTheorique(
            self.tables.residus,
            self.catalogue.residus.codes,
            self.catalogue.ratio_par_mode,
            self.config,
            lambda identifiant: valeur_courante(self.chemins, identifiant),
            self.region_de,
            self.code_region,
        )


def charger_entrees(chemins: Chemins, referentiel: Referentiel) -> EntreesPotentiel:
    """Entrées du calcul : tables de référence et production dans leur version active."""
    return EntreesPotentiel(
        chemins=chemins,
        tables=charger_tables_reference(chemins),
        catalogue=charger_catalogue(chemins),
        config=charger_config_potentiel(chemins),
        referentiel=referentiel,
        production=Versions(chemins).lire("production"),
    )
