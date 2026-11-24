"""Surfaces CROPGRIDS par province et par culture : clé de répartition de la RG-04.

Chaque pixel de CROPGRIDS (SRC-04, grille de 0,05°) porte une surface en ha. Un pixel coupé par
une limite de province est partagé au prorata de l'aire de son intersection avec chaque province,
calculée dans la projection équivalente du référentiel (``crs_surface``). La surface d'une
culture de ``cultures.csv`` est la somme de ses codes CROPGRIDS (agrumes : cinq codes).

Ces surfaces sont des estimations (statut « Estimée », source SRC-04, année de CROPGRIDS).
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import xarray as xr
from shapely import box

from src.data.config_preparation import ConfigSurfaces
from src.data.provenance import Statut

COLONNES_SURFACES = [
    "code_province",
    "code_culture",
    "surface_ha",
    "source_id",
    "annee",
    "statut",
    "note",
]


class ErreurSurfaces(Exception):
    """Calcul des surfaces impossible ; message en français."""


def _bords(centres: np.ndarray) -> np.ndarray:
    """Bords des pixels à partir de leurs centres régulièrement espacés (n centres → n+1 bords)."""
    interieurs = np.mean([centres[:-1], centres[1:]], axis=0)
    premier = centres[0] - (interieurs[0] - centres[0])
    dernier = centres[-1] + (centres[-1] - interieurs[-1])
    return np.concatenate([[premier], interieurs, [dernier]])


def fractions_pixels(
    grille: xr.DataArray, provinces: gpd.GeoDataFrame, crs_surface: str
) -> pd.DataFrame:
    """Fraction de chaque pixel non nul de ``grille`` (lat × lon) comprise dans chaque province.

    Returns:
        Colonnes ``i_lat``, ``i_lon``, ``code_province``, ``fraction`` (0 à 1).
    """
    lat, lon = grille["lat"].to_numpy(), grille["lon"].to_numpy()
    bords_lat, bords_lon = _bords(lat), _bords(lon)
    i_lat, i_lon = np.nonzero(np.nan_to_num(grille.to_numpy()) > 0)
    if i_lat.size == 0:
        return pd.DataFrame(columns=["i_lat", "i_lon", "code_province", "fraction"])
    lat_a, lat_b = bords_lat[i_lat], bords_lat[i_lat + 1]
    lon_a, lon_b = bords_lon[i_lon], bords_lon[i_lon + 1]
    pixels = gpd.GeoDataFrame(
        {"i_lat": i_lat, "i_lon": i_lon},
        geometry=box(
            np.minimum(lon_a, lon_b),
            np.minimum(lat_a, lat_b),
            np.maximum(lon_a, lon_b),
            np.maximum(lat_a, lat_b),
        ),
        crs=provinces.crs,
    )
    zones = provinces[["code_province", "geometry"]]
    paires = gpd.sjoin(pixels, zones, predicate="intersects", how="inner")
    if paires.empty:
        return pd.DataFrame(columns=["i_lat", "i_lon", "code_province", "fraction"])
    geometries_provinces = zones.set_index("code_province").geometry
    intersections = gpd.GeoSeries(
        shapely.intersection(
            paires.geometry.to_numpy(),
            geometries_provinces.loc[paires["code_province"]].to_numpy(),
        ),
        crs=provinces.crs,
    )
    aire_inter = intersections.to_crs(crs_surface).area.to_numpy()
    aire_pixel = gpd.GeoSeries(paires.geometry, crs=provinces.crs).to_crs(crs_surface).area
    fractions = paires[["i_lat", "i_lon", "code_province"]].copy()
    fractions["fraction"] = aire_inter / aire_pixel.to_numpy()
    return fractions.reset_index(drop=True)


def surfaces_par_province(
    cropgrids: xr.Dataset,
    provinces: gpd.GeoDataFrame,
    cultures: pd.DataFrame,
    config: ConfigSurfaces,
    crs_surface: str,
) -> pd.DataFrame:
    """Surface CROPGRIDS (ha) de chaque culture de ``cultures`` dans chaque province.

    Args:
        cropgrids: découpage du Maroc (dimensions culture × lat × lon), en EPSG:4326.
        provinces: polygones du référentiel (``code_province``, géométrie).
        cultures: ``cultures.csv`` (``code_culture``, ``code_cropgrids``) ; une culture sans
            code CROPGRIDS (arganier) n'a pas de surface.
        config: variable de CROPGRIDS utilisée et année.
        crs_surface: projection équivalente pour les aires.

    Returns:
        Une ligne par province et par culture couverte par CROPGRIDS, y compris les surfaces
        nulles (une surface nulle est une valeur, pas une donnée manquante).
    """
    if config.variable not in cropgrids:
        raise ErreurSurfaces(f"variable « {config.variable} » absente du découpage CROPGRIDS")
    codes = cultures[cultures["code_cropgrids"].astype(str).str.len() > 0]
    absents = sorted(set(codes["code_cropgrids"]) - set(cropgrids["culture"].to_numpy()))
    if absents:
        raise ErreurSurfaces(f"codes CROPGRIDS absents du découpage : {', '.join(absents)}")
    source_id = str(cropgrids.attrs.get("source_id", ""))
    if not source_id:
        raise ErreurSurfaces("le découpage CROPGRIDS ne porte pas sa source (attribut source_id)")
    provinces = provinces.to_crs(config.crs)
    valeurs = cropgrids[config.variable].sel(culture=sorted(set(codes["code_cropgrids"])))
    valeurs = valeurs.fillna(0).clip(min=0)
    fractions = fractions_pixels(valeurs.sum("culture"), provinces, crs_surface)
    fractions = fractions[fractions["fraction"] > config.fraction_minimale]
    lignes = []
    tableau = valeurs.to_numpy()
    index_culture = {c: i for i, c in enumerate(valeurs["culture"].to_numpy())}
    for code_culture, groupe in codes.groupby("code_culture", sort=True):
        somme = np.sum([tableau[index_culture[c]] for c in groupe["code_cropgrids"]], axis=0)
        pondere = somme[fractions["i_lat"], fractions["i_lon"]] * fractions["fraction"]
        par_province = pondere.groupby(fractions["code_province"]).sum()
        par_province = par_province.reindex(provinces["code_province"], fill_value=0)
        noms = ", ".join(sorted(groupe["code_cropgrids"]))
        for code_province, surface in par_province.items():
            lignes.append(
                {
                    "code_province": code_province,
                    "code_culture": code_culture,
                    "surface_ha": float(surface),
                    "source_id": source_id,
                    "annee": config.annee,
                    "statut": Statut.ESTIMEE.value,
                    "note": f"CROPGRIDS {config.variable} ({noms}), pixels partagés au prorata "
                    "de l'aire",
                }
            )
    return pd.DataFrame(lignes, columns=COLONNES_SURFACES)


COLONNES_SURFACE_AGRICOLE = ["code_province", "surface_ha", "source_id", "annee", "statut", "note"]


def surface_agricole_par_province(
    cropgrids: xr.Dataset,
    provinces: gpd.GeoDataFrame,
    config: ConfigSurfaces,
    crs_surface: str,
) -> pd.DataFrame:
    """Surface cultivée CROPGRIDS (ha) de toutes les cultures dans chaque province.

    Dénominateur de la densité du gisement (critère A2, décision du 22/11/2026). Un pixel
    coupé par une limite est partagé au prorata de l'aire, comme pour chaque culture.
    """
    if config.variable not in cropgrids:
        raise ErreurSurfaces(f"variable « {config.variable} » absente du découpage CROPGRIDS")
    source_id = str(cropgrids.attrs.get("source_id", ""))
    if not source_id:
        raise ErreurSurfaces("le découpage CROPGRIDS ne porte pas sa source (attribut source_id)")
    provinces = provinces.to_crs(config.crs)
    total = cropgrids[config.variable].fillna(0).clip(min=0).sum("culture")
    fractions = fractions_pixels(total, provinces, crs_surface)
    fractions = fractions[fractions["fraction"] > config.fraction_minimale]
    grille = total.to_numpy()
    pondere = grille[fractions["i_lat"], fractions["i_lon"]] * fractions["fraction"]
    par_province = pondere.groupby(fractions["code_province"]).sum()
    par_province = par_province.reindex(provinces["code_province"], fill_value=0)
    nombre = int(cropgrids.sizes["culture"])
    return pd.DataFrame(
        [
            {
                "code_province": code,
                "surface_ha": float(surface),
                "source_id": source_id,
                "annee": config.annee,
                "statut": Statut.ESTIMEE.value,
                "note": f"CROPGRIDS {config.variable}, somme des {nombre} cultures, pixels "
                "partagés au prorata de l'aire",
            }
            for code, surface in par_province.items()
        ],
        columns=COLONNES_SURFACE_AGRICOLE,
    )
