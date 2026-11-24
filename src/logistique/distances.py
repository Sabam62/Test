"""Distances routières province × résidu × site (SRC-07, UC-LOG-02, RG-13).

La matrice est demandée au service OSRM local (``/table``) et mise en cache dans
``data/cache/logistique/`` avec une empreinte des points et des sites : elle n'est recalculée
que si un point de rattachement ou un site change. Si OSRM ne répond pas, la distance vaut la
distance à vol d'oiseau × le coefficient de détour PAR-30, calibré sur la dernière matrice OSRM
(médiane du rapport distance routière ÷ vol d'oiseau) ; la méthode est écrite sur chaque ligne
et l'interface l'affiche. Sans calibration, le repli est impossible et le calcul est bloqué
(RG-14).
"""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from src.chemins import Chemins
from src.logistique.config import ConfigLogistique

OSRM, VOL_OISEAU = "osrm", "vol_oiseau"
COLONNES_DISTANCES = [
    "code_province",
    "code_residu",
    "id_site",
    "distance_km",
    "duree_min",
    "methode",
]
FICHIER_CALIBRATION = "calibration_detour.json"


class OsrmIndisponible(Exception):
    """Le service OSRM ne répond pas ou renvoie une erreur."""


class ErreurDistances(Exception):
    """Distances impossibles à calculer ; message en français qui dit quoi faire."""


@dataclass(frozen=True)
class Calibration:
    """Coefficient de détour PAR-30 calibré sur une matrice OSRM."""

    coefficient: float
    paires: int
    date: str


@dataclass(frozen=True)
class Matrice:
    """Table ``distances`` (section 13) et méthode utilisée."""

    distances: pd.DataFrame
    methode: str
    calibration: Calibration | None
    message: str | None


def vol_oiseau_km(
    lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray, rayon_km: float
) -> np.ndarray:
    """Distance du grand cercle (loi des cosinus sphérique), en km ; tableaux diffusables.

    En double précision, l'erreur reste inférieure au mètre pour des distances de quelques km.
    """
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    cosinus = np.sin(phi1) * np.sin(phi2) + np.cos(phi1) * np.cos(phi2) * np.cos(
        np.radians(lon2 - lon1)
    )
    return rayon_km * np.arccos(np.clip(cosinus, -1, 1))


def _coordonnees(points: pd.DataFrame) -> str:
    return ";".join(f"{x:.6f},{y:.6f}" for x, y in zip(points["lon"], points["lat"], strict=True))


def table_osrm(
    sources: pd.DataFrame, destinations: pd.DataFrame, config: ConfigLogistique
) -> tuple[np.ndarray, np.ndarray]:
    """Matrices distance (km) et durée (min) sources × destinations, par lots de sources."""
    osrm = config.osrm
    distances, durees = [], []
    nb_dest = len(destinations)
    with httpx.Client(timeout=osrm.delai_secondes) as client:
        for debut in range(0, len(sources), osrm.lot):
            lot = sources.iloc[debut : debut + osrm.lot]
            tous = pd.concat([lot[["lon", "lat"]], destinations[["lon", "lat"]]])
            src = ";".join(str(i) for i in range(len(lot)))
            dst = ";".join(str(len(lot) + i) for i in range(nb_dest))
            url = f"{osrm.url}/table/v1/{osrm.profil}/{_coordonnees(tous)}"
            try:
                reponse = client.get(
                    url,
                    params={
                        "sources": src,
                        "destinations": dst,
                        "annotations": "distance,duration",
                    },
                )
                corps = reponse.json()
            except (httpx.HTTPError, ValueError) as erreur:
                raise OsrmIndisponible(f"OSRM ne répond pas ({osrm.url}) : {erreur}") from None
            if reponse.status_code != httpx.codes.OK or corps.get("code") != "Ok":
                raise OsrmIndisponible(f"OSRM a refusé la requête : {corps.get('message', '')}")
            d = np.array(corps["distances"], dtype=float)
            t = np.array(corps["durations"], dtype=float)
            distances.append(d / config.metres_par_km)
            durees.append(t / config.secondes_par_minute)
    return np.vstack(distances), np.vstack(durees)


def commande_osrm(systeme: str | None = None) -> str:
    """Commande qui démarre le service OSRM, selon le système (``os.name`` ; Windows : « nt »)."""
    if (systeme or os.name) == "nt":
        return "powershell -ExecutionPolicy Bypass -File scripts\\osrm_setup.ps1 -Serveur"
    return "bash scripts/osrm_setup.sh --serveur"


def osrm_disponible(config: ConfigLogistique) -> bool:
    """Vrai si le service OSRM répond (requête /health… ou racine du service)."""
    try:
        reponse = httpx.get(f"{config.osrm.url}/", timeout=config.osrm.delai_test_secondes)
        # Sans itinéraire demandé, OSRM répond 400 « InvalidUrl » : le service est joignable.
        return reponse.json().get("code") is not None
    except (httpx.HTTPError, ValueError):
        return False


def _dossier_cache(chemins: Chemins, config: ConfigLogistique) -> Path:
    dossier = chemins.donnees / "cache" / config.dossier_cache
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def empreinte(points: pd.DataFrame, sites: pd.DataFrame, config: ConfigLogistique) -> str:
    """Empreinte des entrées de la matrice (RG-13) : points, sites, profil de routage."""
    parties = [
        config.osrm.profil,
        points[["code_province", "code_residu", "lon", "lat"]].to_csv(index=False),
        sites[["id_site", "lon", "lat"]].to_csv(index=False),
    ]
    return hashlib.sha256("|".join(parties).encode()).hexdigest()


def lire_calibration(chemins: Chemins, config: ConfigLogistique) -> Calibration | None:
    """Dernier coefficient de détour calibré, s'il existe."""
    fichier = _dossier_cache(chemins, config) / FICHIER_CALIBRATION
    if not fichier.is_file():
        return None
    return Calibration(**json.loads(fichier.read_text(encoding="utf-8")))


def calibrer(routieres: np.ndarray, oiseau: np.ndarray, jour: str) -> Calibration:  # PAR-30 calculé
    """Médiane du rapport distance routière ÷ vol d'oiseau sur les paires valides."""
    valides = np.isfinite(routieres) & (oiseau > 0) & (routieres > 0)
    if not valides.any():
        raise ErreurDistances("aucune paire valide pour calibrer le coefficient de détour")
    rapports = routieres[valides] / oiseau[valides]
    return Calibration(float(np.median(rapports)), int(valides.sum()), jour)


def matrice_distances(
    chemins: Chemins,
    config: ConfigLogistique,
    points: pd.DataFrame,
    sites: pd.DataFrame,
    jour: str,
    forcer_repli: bool = False,
) -> Matrice:
    """Distances de chaque point de rattachement à chaque site, depuis le cache si possible.

    Args:
        chemins: dossiers de l'outil (cache dans ``data/cache/``).
        config: ``config/logistique.yaml``.
        points: ``code_province``, ``code_residu``, ``lon``, ``lat``.
        sites: ``id_site``, ``lon``, ``lat``.
        jour: date du calcul (AAAA-MM-JJ), écrite avec la calibration.
        forcer_repli: True pour ignorer OSRM (tests du repli).
    """
    dossier = _dossier_cache(chemins, config)
    cle = empreinte(points, sites, config)
    cache = dossier / f"distances_{cle}.parquet"
    if cache.is_file() and not forcer_repli:
        table = pd.read_parquet(cache)
        return Matrice(table, OSRM, lire_calibration(chemins, config), None)
    oiseau = vol_oiseau_km(
        points["lon"].to_numpy()[:, None],
        points["lat"].to_numpy()[:, None],
        sites["lon"].to_numpy()[None, :],
        sites["lat"].to_numpy()[None, :],
        config.rayon_terre_km,
    )
    message = None
    try:
        if forcer_repli:
            raise OsrmIndisponible("repli demandé")
        distances, durees = table_osrm(points, sites, config)
        methode = OSRM
        calibration = calibrer(distances, oiseau, jour)
        (dossier / FICHIER_CALIBRATION).write_text(
            json.dumps(calibration.__dict__), encoding="utf-8"
        )
    except OsrmIndisponible as erreur:
        calibration = lire_calibration(chemins, config)
        if calibration is None:
            raise ErreurDistances(
                f"{erreur} ; le repli à vol d'oiseau exige le coefficient de détour "
                f"{config.parametre_detour}, calibré sur une première matrice OSRM : démarrez "
                f"OSRM (« {commande_osrm()} ») puis relancez le calcul"
            ) from None
        distances = oiseau * calibration.coefficient
        durees = np.full_like(distances, np.nan)
        methode = VOL_OISEAU
        message = (
            f"OSRM ne répond pas : distances à vol d'oiseau × {calibration.coefficient:.2f} "
            f"(coefficient de détour {config.parametre_detour}, calibré le {calibration.date} "
            f"sur {calibration.paires} trajets)"
        )
    n_points, n_sites = distances.shape
    table = pd.DataFrame(
        {
            "code_province": np.repeat(points["code_province"].to_numpy(), n_sites),
            "code_residu": np.repeat(points["code_residu"].to_numpy(), n_sites),
            "id_site": np.tile(sites["id_site"].to_numpy(), n_points),
            "distance_km": distances.ravel(),
            "duree_min": durees.ravel(),
            "methode": methode,
        },
        columns=COLONNES_DISTANCES,
    )
    if methode == OSRM:
        table.to_parquet(cache, index=False)
    return Matrice(table, methode, calibration, message)


def isodistance(
    lon: float,
    lat: float,
    distance_routiere_km: float,
    coefficient: float,
    config: ConfigLogistique,
) -> dict[str, object]:
    """Contour approché d'un bassin (UC-LOG-04) : cercle de rayon distance routière ÷ détour.

    Le rayon est la distance à vol d'oiseau équivalente à ``distance_routiere_km`` avec le
    coefficient de détour calibré ; le cercle est tracé dans une projection azimutale
    équidistante centrée sur le site, puis ramené en WGS 84 (GeoJSON).
    """
    import geopandas as gpd
    from shapely.geometry import Point, mapping

    projection = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"
    rayon = distance_routiere_km / coefficient * config.metres_par_km
    cercle = gpd.GeoSeries([Point(0, 0).buffer(rayon)], crs=projection).to_crs("EPSG:4326")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(cercle.iloc[0]),
                "properties": {"distance_routiere_km": distance_routiere_km},
            }
        ],
    }
