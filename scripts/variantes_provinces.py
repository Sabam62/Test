"""Régénère ``data/input/variantes_provinces.csv`` à partir des sources brutes (RG-02).

Utilisation : python -m scripts.variantes_provinces

Les noms des cartes du HCP (SRC-19) sont rattachés par leur code, les noms HDX (SRC-05) par
rapprochement spatial aux polygones du HCP ; les variantes saisies à la main (méthode « saisie »)
sont conservées.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.chemins import chemins_par_defaut
from src.data.lecteurs.hcp_cartes import (
    CODE_PROVINCE,
    CODE_REGION,
    NOMS,
    lire_couche_hcp,
    lire_noms_hcp,
)
from src.data.lecteurs.rgph2024 import lire_lignes_rgph2024, unites_rgph2024
from src.data.provinces import (
    COLONNES_VARIANTES,
    ErreurReferentiel,
    charger_config_referentiel,
    charger_variantes,
    code_province,
    construire_referentiel,
)
from src.data.variantes import fusionner, rapprocher, variantes_par_code, variantes_spatiales

SOURCE_HDX = "SRC-05"
ARCHIVE_HDX = "mar_admin_boundaries.shp.zip"


def _hdx(archive: Path, couche: str) -> gpd.GeoDataFrame:
    return gpd.read_file(f"zip://{archive}!{couche}.shp")


def main() -> int:
    """Point d'entrée de ``python -m scripts.variantes_provinces``."""
    chemins = chemins_par_defaut()
    config = charger_config_referentiel(chemins)
    dossier = chemins.brutes / config.source_polygones
    crs = config.crs_natif_polygones
    regions = lire_couche_hcp(dossier / config.fichier_regions, [CODE_REGION], crs)
    provinces = lire_couche_hcp(
        dossier / config.fichier_provinces, [CODE_REGION, CODE_PROVINCE], crs
    )
    unites = unites_rgph2024(
        lire_lignes_rgph2024(chemins.brutes / config.source_noms / config.fichier_rgph)
    )
    base = construire_referentiel(unites, regions, provinces, config)
    regions["code_region"] = regions[CODE_REGION].astype(str)
    provinces["code_province"] = [
        code_province(r, p, config.chiffres_code_province)
        for r, p in zip(provinces[CODE_REGION], provinces[CODE_PROVINCE], strict=True)
    ]
    noms_regions = lire_noms_hcp(dossier / config.fichier_noms_regions, [CODE_REGION])
    noms_regions["code_region"] = noms_regions[CODE_REGION].astype(str)
    noms_provinces = lire_noms_hcp(
        dossier / config.fichier_noms_provinces, [CODE_REGION, CODE_PROVINCE]
    )
    noms_provinces["code_province"] = [
        code_province(r, p, config.chiffres_code_province)
        for r, p in zip(noms_provinces[CODE_REGION], noms_provinces[CODE_PROVINCE], strict=True)
    ]
    archive = chemins.brutes / SOURCE_HDX / ARCHIVE_HDX
    try:
        generees = [
            variantes_par_code(base, "province", noms_provinces, NOMS, config.source_polygones),
            variantes_par_code(base, "region", noms_regions, NOMS, config.source_polygones),
            variantes_spatiales(
                base,
                "province",
                rapprocher(
                    _hdx(archive, "mar_admin2"),
                    "adm2_name",
                    "adm2_pcode",
                    provinces,
                    "code_province",
                ),
                "adm2_name",
                "adm2_pcode",
                SOURCE_HDX,
            ),
            variantes_spatiales(
                base,
                "region",
                rapprocher(
                    _hdx(archive, "mar_admin1"), "adm1_name", "adm1_pcode", regions, "code_region"
                ),
                "adm1_name",
                "adm1_pcode",
                SOURCE_HDX,
            ),
        ]
        fichier = chemins.saisies / config.fichier_variantes
        saisies = (
            charger_variantes(fichier)
            if fichier.is_file()
            else pd.DataFrame(columns=COLONNES_VARIANTES)
        )
        table = fusionner(saisies, generees)
        base.avec_variantes(table)
    except ErreurReferentiel as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1
    table.to_csv(fichier, sep=";", index=False, encoding="utf-8")
    print(f"{fichier.relative_to(chemins.racine)} : {len(table)} variantes.")
    print(table.groupby(["niveau", "source_id", "methode"]).size().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
