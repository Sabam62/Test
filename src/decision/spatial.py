"""Indicateurs spatiaux des sites : E1, F1, F2 et G1 (section 9).

- F1 : distance du site à l'autoroute ou à la route nationale la plus proche (OSM, SRC-06) ;
- F2 : distance à la zone industrielle (OSM ``landuse=industrial``) ou à l'agropole placée la
  plus proche ;
- E1 : surface cultivée CROPGRIDS (toutes cultures, SRC-04) dont le centre du pixel est à moins
  de R_v km du site (PAR-36) ;
- G1 : population rurale de la province du site (RGPH 2024, SRC-09).

Les couches OSM et la population sont préparées une fois par ``scripts.prepare``.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

from src.data.provenance import Statut
from src.decision.config import ConfigDecision, CoucheOsm
from src.logistique.distances import vol_oiseau_km

COLONNES_POPULATION = ["code_province", "population_rurale", "source_id", "annee", "statut", "note"]


class ErreurSpatiale(Exception):
    """Indicateur spatial impossible ; message en français."""


def extraire_couche(pbf: Path, couche: CoucheOsm, etiquette: str, cible: Path) -> Path:
    """Écrit la couche OSM filtrée (``etiquette`` IN valeurs) dans un GeoPackage."""
    import pyogrio

    valeurs = ", ".join(f"'{v}'" for v in couche.valeurs)
    table = pyogrio.read_dataframe(
        pbf, layer=couche.couche_osm, columns=[etiquette], where=f"{etiquette} IN ({valeurs})"
    )
    table = table[table.geometry.notna() & ~table.geometry.is_empty]
    provisoire = cible.with_suffix(".tmp.gpkg")
    table.to_file(provisoire, driver="GPKG")
    provisoire.replace(cible)
    return cible


def population_rurale(xlsx: Path, codes: set[str], config: ConfigDecision) -> pd.DataFrame:
    """Population rurale de chaque province (lignes « milieu rural » du RGPH 2024).

    Une préfecture sans ligne rurale est entièrement urbaine : sa population rurale vaut 0.
    """
    brut = pd.read_excel(xlsx, header=None, dtype=str)
    entete = next(
        i for i, ligne in brut.iterrows() if config.population.colonne_population in set(ligne)
    )
    colonne = brut.loc[entete].tolist().index(config.population.colonne_population)
    code = brut.columns[-1]
    rurales = brut[brut[0].fillna("").str.contains(config.population.motif_rural, regex=False)]
    valeurs = {
        str(ligne[code]).strip(): float(ligne[colonne])
        for _, ligne in rurales.iterrows()
        if str(ligne[code]).strip() in codes
    }
    lignes = []
    for c in sorted(codes):
        presente = c in valeurs
        lignes.append(
            {
                "code_province": c,
                "population_rurale": valeurs.get(c, 0.0),
                "source_id": config.population.source,
                "annee": config.population.annee,
                "statut": Statut.MESUREE.value,
                "note": "RGPH 2024, milieu rural"
                if presente
                else "aucune ligne « milieu rural » au RGPH 2024 : préfecture entièrement urbaine",
            }
        )
    return pd.DataFrame(lignes, columns=COLONNES_POPULATION)


def distances_plus_proches(
    sites: pd.DataFrame, couche: gpd.GeoDataFrame, config: ConfigDecision
) -> np.ndarray:
    """Distance (km) de chaque site à l'objet le plus proche de ``couche``."""
    if couche.empty:
        raise ErreurSpatiale("couche vide : relancez « python -m scripts.prepare »")
    points = gpd.GeoDataFrame(
        sites[["id_site"]].reset_index(drop=True),
        geometry=gpd.points_from_xy(sites["lon"], sites["lat"]),
        crs="EPSG:4326",
    ).to_crs(config.spatial.crs_metrique)
    objets = couche[["geometry"]].to_crs(config.spatial.crs_metrique)
    proches = gpd.sjoin_nearest(points, objets, how="left", distance_col="distance_m")
    proches = proches[~proches.index.duplicated(keep="first")].sort_index()
    return proches["distance_m"].to_numpy() / config.spatial.metres_par_km


def surface_dans_rayon(
    sites: pd.DataFrame, cropgrids: xr.Dataset, variable: str, rayon_km: float, rayon_terre: float
) -> np.ndarray:
    """Surface cultivée (ha) des pixels dont le centre est à moins de ``rayon_km`` du site."""
    total = cropgrids[variable].fillna(0).clip(min=0).sum("culture")
    lat, lon = total["lat"].to_numpy(), total["lon"].to_numpy()
    grille = total.to_numpy()
    lon2, lat2 = np.meshgrid(lon, lat)
    masque = grille > 0
    lons, lats, surfaces = lon2[masque], lat2[masque], grille[masque]
    resultats = []
    for x, y in zip(sites["lon"], sites["lat"], strict=True):
        d = vol_oiseau_km(x, y, lons, lats, rayon_terre)
        resultats.append(float(surfaces[d <= rayon_km].sum()))
    return np.array(resultats)
