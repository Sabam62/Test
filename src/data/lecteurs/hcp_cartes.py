"""Lecteur des cartes du HCP (SRC-19) : polygones des régions et des provinces.

Les couches RGPH:regions et RGPH:provinces portent de nombreux indicateurs du RGPH 2014, qui ne
sont pas utilisés : seuls les géométries, les codes (``code_reg``, ``code_prov``) et les noms
(``libelle_fr``, ``libelle_ar``, variantes de graphie) sont lus.

Les coordonnées sont lues dans leur système natif, déclaré dans ``config/referentiel.yaml``
(``crs_natif_polygones``), puis converties en EPSG:4326.
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

CODE_REGION, CODE_PROVINCE = "code_reg", "code_prov"
NOMS = ["libelle_fr", "libelle_ar"]


CRS_SORTIE = "EPSG:4326"


def lire_couche_hcp(chemin: Path, colonnes_codes: list[str], crs_natif: str) -> gpd.GeoDataFrame:
    """Lit une couche du HCP, impose son système natif et la convertit en EPSG:4326.

    Seuls ``colonnes_codes`` et la géométrie sont conservés.
    """
    couche = gpd.read_file(chemin).set_crs(crs_natif, allow_override=True).to_crs(CRS_SORTIE)
    absentes = [c for c in colonnes_codes if c not in couche.columns]
    if absentes:
        raise ValueError(f"{chemin.name} : colonnes absentes {absentes}")
    couche = couche[[*colonnes_codes, "geometry"]].copy()
    for colonne in colonnes_codes:
        couche[colonne] = couche[colonne].astype(int)
    return couche


def lire_noms_hcp(chemin: Path, colonnes_codes: list[str]) -> pd.DataFrame:
    """Codes et noms (français, arabe) d'une table de noms du HCP, sans géométrie."""
    entites = json.loads(chemin.read_text(encoding="utf-8"))["features"]
    table = pd.DataFrame([e["properties"] for e in entites])
    absentes = [c for c in [*colonnes_codes, *NOMS] if c not in table.columns]
    if absentes:
        raise ValueError(f"{chemin.name} : colonnes absentes {absentes}")
    table = table[[*colonnes_codes, *NOMS]].copy()
    for colonne in colonnes_codes:
        table[colonne] = table[colonne].astype(int)
    return table
