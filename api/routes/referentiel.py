"""Référentiel des régions et provinces : attributs et contours GeoJSON simplifiés (RG-02)."""

import json
from typing import Annotated

import geopandas as gpd
from fastapi import APIRouter, Depends, HTTPException

from api.dependances import charger_config_api, obtenir_chemins, obtenir_referentiel
from api.serialisation import lignes
from src.chemins import Chemins
from src.data.provinces import Referentiel

routeur = APIRouter(prefix="/referentiel", tags=["référentiel"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
ReferentielDep = Annotated[Referentiel, Depends(obtenir_referentiel)]
NIVEAUX = {"regions": "regions.gpkg", "provinces": "provinces.gpkg"}


@routeur.get("/regions")
def regions(referentiel: ReferentielDep) -> list[dict[str, object]]:
    """Les 12 régions : code et noms officiels (RGPH 2024)."""
    return lignes(referentiel.regions)


@routeur.get("/provinces")
def provinces(referentiel: ReferentielDep) -> list[dict[str, object]]:
    """Les 75 provinces : code, région et noms officiels (RGPH 2024)."""
    return lignes(referentiel.provinces)


@routeur.get("/{niveau}/geojson")
def contours(niveau: str, chemins: CheminsDep) -> dict[str, object]:
    """Contours simplifiés pour la carte, avec l'attribution des cartes du HCP (SRC-19)."""
    if niveau not in NIVEAUX:
        raise HTTPException(404, f"niveau « {niveau} » inconnu : regions ou provinces")
    fichier = chemins.preparees / NIVEAUX[niveau]
    if not fichier.is_file():
        raise HTTPException(
            503, f"{fichier.name} absent de data/processed/ : lancez « python -m scripts.prepare »"
        )
    config = charger_config_api(chemins)
    table = gpd.read_file(fichier).to_crs("EPSG:4326")
    table["geometry"] = table.geometry.simplify(
        config.simplification_geojson_degres, preserve_topology=True
    )
    geojson = json.loads(table.to_json(drop_id=True, to_wgs84=True))
    geojson["attribution"] = config.attribution_cartes
    return geojson
