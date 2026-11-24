"""Produit l'extrait figé des statistiques de production utilisé par les tests (tâche 6).

Fichiers écrits dans tests/fixtures/production/, tous tirés des données réelles :

- SRC-18/ : copie intégrale des trois fichiers saisis et vérifiés par l'équipe ;
- SRC-01/production_vegetale_2010_2022.xlsx : lignes réelles du fichier Open Data pour
  l'olivier, le palmier dattier et le blé (dur et tendre), toutes campagnes, plus les lignes
  « Ail » de 2010/2011 (produit hors périmètre) ;
- surfaces_cropgrids.csv : surfaces CROPGRIDS calculées par scripts.prepare pour l'olivier, le
  palmier dattier et le blé dans les 75 provinces (attributs seulement, aucune géométrie du HCP) ;
- surface_agricole.csv : surface cultivée CROPGRIDS de toutes les cultures par province ;
- hdx_regions.geojson : polygones de deux régions de HDX (SRC-05, CC BY-IGO, © OCHA/HCP),
  Fès-Meknès et Oriental, simplifiés, pour tester la statistique zonale.

Utilisation (après python -m scripts.prepare) : python -m tests.fixtures.extraire_production
"""

import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
SORTIE = Path(__file__).resolve().parent / "production"
BRUTES = RACINE / "data" / "raw"
FICHIERS_SRC18 = ["references.csv", "valeurs_saisies.csv", "valeurs_verifiees.csv"]
PRODUITS = ["Olivier", "Palmier dattier", "Blé dur", "Blé tendre"]
CULTURES = ["olivier", "palmier_dattier", "ble"]
REGIONS_HDX = ["MA004", "MA007"]
TOLERANCE_SIMPLIFICATION = 0.005


def main() -> None:
    """Écrit l'extrait dans tests/fixtures/production/."""
    (SORTIE / "SRC-18").mkdir(parents=True, exist_ok=True)
    (SORTIE / "SRC-01").mkdir(parents=True, exist_ok=True)
    for nom in FICHIERS_SRC18:
        shutil.copyfile(BRUTES / "SRC-18" / nom, SORTIE / "SRC-18" / nom)
    src01 = pd.read_excel(BRUTES / "SRC-01" / "production_vegetale_2010_2022.xlsx")
    produits = src01["Produit"].astype(str).str.strip()
    garder = produits.isin(PRODUITS) | (
        (produits == "Ail") & (src01["Occurrence"].astype(str).str.strip() == "2010/2011")
    )
    src01[garder].to_excel(SORTIE / "SRC-01" / "production_vegetale_2010_2022.xlsx", index=False)
    surfaces = pd.read_parquet(RACINE / "data/processed/surfaces_cropgrids.parquet")
    surfaces[surfaces["code_culture"].isin(CULTURES)].to_csv(
        SORTIE / "surfaces_cropgrids.csv", sep=";", index=False
    )
    agricole = pd.read_parquet(RACINE / "data/processed/surface_agricole.parquet")
    agricole.to_csv(SORTIE / "surface_agricole.csv", sep=";", index=False)
    hdx = gpd.read_file(f"zip://{BRUTES}/SRC-05/mar_admin_boundaries.shp.zip!mar_admin1.shp")
    hdx = hdx[hdx["adm1_pcode"].isin(REGIONS_HDX)][["adm1_pcode", "adm1_name", "geometry"]]
    hdx["geometry"] = hdx.geometry.simplify(TOLERANCE_SIMPLIFICATION)
    hdx.to_file(SORTIE / "hdx_regions.geojson", driver="GeoJSON")
    for fichier in sorted(SORTIE.rglob("*")):
        if fichier.is_file():
            print(fichier.relative_to(RACINE), fichier.stat().st_size, "octets")


if __name__ == "__main__":
    main()
