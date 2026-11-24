"""Produit les extraits figés du lot 3 (logistique) utilisés par les tests.

- ``lieux_osm.csv`` : villes (place = city ou town) de l'extrait OpenStreetMap du Maroc
  (SRC-06, © contributeurs OpenStreetMap, ODbL) situées dans les deux régions de
  ``production/hdx_regions.geojson`` ;
- ``osrm_table.json`` : réponse réelle du service OSRM local (``/table``) entre l'Agropolis
  de Meknès et ces villes, pour tester la calibration du coefficient de détour sans OSRM.

Utilisation (OSRM démarré) : python -m tests.fixtures.extraire_logistique
"""

import json
from pathlib import Path

import geopandas as gpd
import httpx

from src.chemins import chemins_par_defaut
from src.logistique.config import charger_config_logistique
from src.logistique.sites import lire_lieux_osm

DOSSIER = Path(__file__).resolve().parent
AGROPOLIS = (-5.4532051, 33.8344655)  # data/input/sites.csv, AGP-MEKNES


def main() -> None:
    """Écrit les deux extraits dans tests/fixtures/logistique/."""
    chemins = chemins_par_defaut()
    config = charger_config_logistique(chemins)
    s = config.sites
    lieux = lire_lieux_osm(
        chemins.brutes / s.source_osm / s.fichier_osm, s.couche_osm, s.types_lieux
    )
    regions = gpd.read_file(DOSSIER / "production" / "hdx_regions.geojson")
    dedans = gpd.sjoin(lieux, regions[["adm1_pcode", "geometry"]], how="inner")
    table = dedans.assign(lon=dedans.geometry.x.round(7), lat=dedans.geometry.y.round(7))
    table = table[["nom", "place", "population", "lon", "lat"]].sort_values("nom")
    table.to_csv(DOSSIER / "logistique" / "lieux_osm.csv", sep=";", index=False)
    points = ";".join(f"{x},{y}" for x, y in [AGROPOLIS, *zip(table.lon, table.lat, strict=True)])
    reponse = httpx.get(
        f"{config.osrm.url}/table/v1/{config.osrm.profil}/{points}",
        params={"sources": "0", "annotations": "distance,duration"},
        timeout=30,
    ).json()
    sortie = {
        "points": [AGROPOLIS, *zip(table.lon, table.lat, strict=True)],
        "distances": reponse["distances"],
    }
    (DOSSIER / "logistique" / "osrm_table.json").write_text(json.dumps(sortie), encoding="utf-8")
    print(len(table), "villes")


if __name__ == "__main__":
    main()


def extraire_preparees() -> None:
    """Points de rattachement et chefs-lieux de Fès-Meknès, tirés de data/processed/.

    Ce sont des points calculés (barycentres, villes OSM), pas des géométries du HCP.
    Utilisation : python -c "from tests.fixtures.extraire_logistique import extraire_preparees;
    extraire_preparees()"
    """
    import pandas as pd

    chemins = chemins_par_defaut()
    config = charger_config_logistique(chemins)
    for source, cible in (
        (config.rattachement.sortie, "rattachements_fes_meknes.csv"),
        (config.sites.sortie_chefs_lieux, "chefs_lieux_fes_meknes.csv"),
    ):
        table = pd.read_parquet(chemins.preparees / source)
        table = table[table["code_province"].astype(str).str.startswith("3")]
        table.to_csv(DOSSIER / "logistique" / cible, sep=";", index=False)
