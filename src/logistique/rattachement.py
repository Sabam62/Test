"""Points de rattachement des gisements (H1, section 8.2).

Le gisement d'une province pour un résidu est placé au barycentre des surfaces cultivées
CROPGRIDS de ses cultures d'origine (pixels partagés au prorata de l'aire) ; à défaut (culture
absente de CROPGRIDS, comme l'arganier, ou surface nulle), au centroïde géométrique de la
province, et c'est signalé (colonne ``methode``).
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

from src.data.provenance import Statut
from src.data.surfaces import fractions_pixels

BARYCENTRE = "barycentre_cropgrids"
CENTROIDE = "centroide"
COLONNES_RATTACHEMENTS = [
    "code_province",
    "code_residu",
    "lon",
    "lat",
    "methode",
    "source_id",
    "annee",
    "statut",
    "note",
]


def points_de_rattachement(
    cropgrids: xr.Dataset,
    provinces: gpd.GeoDataFrame,
    cultures: pd.DataFrame,
    cultures_par_residu: dict[str, list[str]],
    variable: str,
    crs_geographique: str,
    crs_surface: str,
    annee: int,
) -> pd.DataFrame:
    """Point de rattachement de chaque province × résidu.

    Args:
        cropgrids: découpage du Maroc (culture × lat × lon), en degrés.
        provinces: polygones du référentiel (``code_province``, géométrie).
        cultures: ``cultures.csv`` (``code_culture``, ``code_cropgrids``).
        cultures_par_residu: codes de cultures d'origine de chaque résidu (§8.1).
        variable: variable de CROPGRIDS (surface cultivée).
        crs_geographique: système de la grille CROPGRIDS (WGS 84).
        crs_surface: projection équivalente pour les aires et les centroïdes.
        annee: année de CROPGRIDS.

    Returns:
        Une ligne par province × résidu, en WGS 84 (``lon``, ``lat``).
    """
    provinces = provinces.to_crs(crs_geographique)
    source_id = str(cropgrids.attrs.get("source_id", ""))
    centroides = provinces.to_crs(crs_surface).geometry.centroid.to_crs(crs_geographique)
    centre = dict(
        zip(provinces["code_province"], zip(centroides.x, centroides.y, strict=True), strict=True)
    )
    valeurs = cropgrids[variable].fillna(0).clip(min=0)
    disponibles = set(valeurs["culture"].to_numpy())
    lat, lon = valeurs["lat"].to_numpy(), valeurs["lon"].to_numpy()
    lignes: list[dict[str, object]] = []
    for residu, codes_culture in sorted(cultures_par_residu.items()):
        codes = sorted(
            c
            for c in cultures[cultures["code_culture"].isin(codes_culture)]["code_cropgrids"]
            if isinstance(c, str) and c in disponibles
        )
        par_province: dict[str, tuple[float, float]] = {}
        if codes:
            grille = valeurs.sel(culture=codes).sum("culture")
            fractions = fractions_pixels(grille, provinces, crs_surface)
            if not fractions.empty:
                tableau = grille.to_numpy()
                poids = tableau[fractions["i_lat"], fractions["i_lon"]] * fractions["fraction"]
                fractions = fractions.assign(
                    poids=poids.to_numpy(),
                    lon=lon[fractions["i_lon"]],
                    lat=lat[fractions["i_lat"]],
                )
                for code, groupe in fractions.groupby("code_province"):
                    total = float(groupe["poids"].sum())
                    if total > 0:
                        par_province[str(code)] = (
                            float(np.average(groupe["lon"], weights=groupe["poids"])),
                            float(np.average(groupe["lat"], weights=groupe["poids"])),
                        )
        noms = ", ".join(codes) if codes else "aucune culture CROPGRIDS"
        for code_province in provinces["code_province"]:
            if code_province in par_province:
                x, y = par_province[code_province]
                methode, note = BARYCENTRE, f"barycentre des surfaces CROPGRIDS ({noms})"
            else:
                x, y = centre[code_province]
                methode = CENTROIDE
                note = f"centroïde géométrique de la province : surface CROPGRIDS nulle ({noms})"
            lignes.append(
                {
                    "code_province": code_province,
                    "code_residu": residu,
                    "lon": x,
                    "lat": y,
                    "methode": methode,
                    "source_id": source_id or "SRC-04",
                    "annee": annee,
                    "statut": Statut.ESTIMEE.value,
                    "note": note,
                }
            )
    return pd.DataFrame(lignes, columns=COLONNES_RATTACHEMENTS)
