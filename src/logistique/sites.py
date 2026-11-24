"""Sites candidats (section 4, UC-LOG-01) : chefs-lieux, agropoles et sites de l'utilisateur.

- Chefs-lieux : pour chaque province, la ville (``place`` = city ou town) de l'extrait
  OpenStreetMap (SRC-06) située dans la province et dont le nom correspond à celui de la
  province ; à défaut la ville la plus peuplée de la province, à défaut son centroïde. Le choix
  est écrit dans la note de chaque site.
- Agropoles : ``data/input/sites.csv`` ; une agropole sans coordonnées reste « À compléter »
  (RG-14) et n'entre dans aucun calcul.
- Sites de l'utilisateur : ``config/sites.local.yaml`` (local, ignoré par Git), ajoutés par
  coordonnées ou par clic sur la carte.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import Point

from src.chemins import Chemins
from src.data.provenance import A_COMPLETER, Statut
from src.data.provinces import normaliser_nom
from src.lecture_yaml import lire_yaml
from src.logistique.config import ConfigLogistique

CHEF_LIEU, AGROPOLE, UTILISATEUR = "chef-lieu", "agropole", "utilisateur"
PREFIXE_CHEF_LIEU, PREFIXE_UTILISATEUR = "CL-", "UT-"
COLONNES_SITES = [
    "id_site",
    "nom",
    "type",
    "lon",
    "lat",
    "code_province",
    "impose",
    "source_id",
    "annee",
    "statut",
    "note",
]
_LATIN = re.compile(r"[A-Za-zÀ-ÿ'’\- ]+")
# Préférence entre lieux de même nom : ville, puis bourg, puis village.
_RANG_LIEU = {t: i for i, t in enumerate(("city", "town", "village"))}


class ErreurSite(Exception):
    """Site refusé ou illisible ; message en français."""


@dataclass(frozen=True)
class SitesCandidats:
    """Sites utilisables par les calculs et sites dont les coordonnées manquent (RG-14)."""

    sites: pd.DataFrame
    a_completer: pd.DataFrame


def _nom_latin(nom: str, autres: str) -> str:
    """Nom français d'un lieu OSM (``name:fr``), sinon la partie en alphabet latin de ``name``."""
    trouve = re.search(r'"name:fr"=>"([^"]+)"', autres or "")
    if trouve:
        return trouve.group(1)
    morceau = _LATIN.match(nom or "")
    return morceau.group(0).strip() if morceau else (nom or "")


def _population(autres: str) -> float:
    trouve = re.search(r'"population"=>"(\d+)"', autres or "")
    return float(trouve.group(1)) if trouve else 0.0


def lire_lieux_osm(chemin: Path, couche: str, types: list[str]) -> gpd.GeoDataFrame:
    """Villes de l'extrait OpenStreetMap : nom français, type de lieu, population."""
    import pyogrio

    if not chemin.is_file():
        raise ErreurSite(
            f"{chemin} est absent : lancez « python -m scripts.download » (SRC-06) "
            "pour placer les chefs-lieux"
        )
    liste = ", ".join(f"'{t}'" for t in types)
    lieux = pyogrio.read_dataframe(
        chemin, layer=couche, columns=["name", "place", "other_tags"], where=f"place IN ({liste})"
    )
    lieux["nom"] = [
        _nom_latin(n, a) for n, a in zip(lieux["name"], lieux["other_tags"], strict=True)
    ]
    lieux["population"] = [_population(a) for a in lieux["other_tags"]]
    return lieux[["nom", "place", "population", "geometry"]]


def lire_designations(chemin: Path) -> dict[str, dict[str, str]]:
    """Chefs-lieux administratifs désignés (``data/input/chefs_lieux.csv``), par province.

    Une province absente du fichier a pour chef-lieu la ville OSM qui porte son nom.
    """
    if not chemin.is_file():
        return {}
    table = pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False)
    manquantes = [x for x in table.to_dict("records") if not x["source_id"].strip()]
    if manquantes:
        raise ErreurSite(f"{chemin.name} : source obligatoire (RG-18)")
    return {str(x["code_province"]): x for x in table.to_dict("records")}


def chefs_lieux(
    lieux: gpd.GeoDataFrame,
    provinces: gpd.GeoDataFrame,
    crs_surface: str,
    annee: int,
    designations: dict[str, dict[str, str]] | None = None,
) -> pd.DataFrame:
    """Un chef-lieu par province, placé sur un lieu OSM situé dans la province.

    Le chef-lieu désigné dans ``designations`` (nom administratif et graphie OSM) est cherché
    parmi les lieux de la province ; sinon, la ville qui porte le nom de la province ; à défaut,
    la ville la plus peuplée ou le centroïde, signalés « à vérifier ».
    """
    designations = designations or {}
    provinces = provinces.to_crs(lieux.crs)
    paires = gpd.sjoin(lieux, provinces[["code_province", "nom_fr", "geometry"]], how="inner")
    centroides = provinces.to_crs(crs_surface).geometry.centroid.to_crs(lieux.crs)
    lignes = []
    for position, province in enumerate(provinces.itertuples()):
        candidats = paires[paires["code_province"] == province.code_province]
        designation = designations.get(str(province.code_province))
        statut = Statut.ESTIMEE.value
        if designation is not None:
            cle_osm = normaliser_nom(designation["nom_osm"])
            trouves = candidats[[normaliser_nom(n) == cle_osm for n in candidats["nom"]]]
            trouves = trouves.assign(rang=trouves["place"].map(_RANG_LIEU)).sort_values(
                ["rang", "population"], ascending=[True, False]
            )
            if not trouves.empty:
                lieu = trouves.iloc[0]
                x, y = lieu.geometry.x, lieu.geometry.y
                nom = designation["chef_lieu"]
                note = (
                    f"chef-lieu administratif ({designation['note']}) ; position du lieu "
                    f"OpenStreetMap « {lieu['nom']} » ({lieu['place']})"
                )
                lignes.append(
                    _ligne_chef_lieu(province.code_province, nom, x, y, annee, note, statut)
                )
                continue
        cle = normaliser_nom(province.nom_fr)
        par_nom = candidats[
            [
                bool(k) and (k == cle or cle.startswith(k) or k.startswith(cle))
                for k in (normaliser_nom(n) for n in candidats["nom"])
            ]
        ]
        if not par_nom.empty:
            choix = par_nom.assign(rang=par_nom["place"].map(_RANG_LIEU)).sort_values(
                ["rang", "population"], ascending=[True, False]
            )
            lieu = choix.iloc[0]
            x, y, nom = lieu.geometry.x, lieu.geometry.y, str(lieu["nom"])
            note = f"ville OpenStreetMap « {nom} » ({lieu['place']}), même nom que la province"
        elif not candidats.empty:
            lieu = candidats.sort_values("population", ascending=False).iloc[0]
            x, y, nom = lieu.geometry.x, lieu.geometry.y, str(lieu["nom"])
            note = (
                f"à vérifier : ville OpenStreetMap la plus peuplée de la province (« {nom} »), "
                "aucune ville ne porte son nom ; désignez le chef-lieu dans "
                "data/input/chefs_lieux.csv"
            )
        else:
            centre = centroides.iloc[position]
            x, y, nom = centre.x, centre.y, str(province.nom_fr)
            note = "centroïde de la province : aucune ville OpenStreetMap dans la province"
        lignes.append(_ligne_chef_lieu(province.code_province, nom, x, y, annee, note, statut))
    return pd.DataFrame(lignes, columns=COLONNES_SITES)


def _ligne_chef_lieu(
    code: object, nom: str, x: float, y: float, annee: int, note: str, statut: str
) -> dict[str, object]:
    return {
        "id_site": f"{PREFIXE_CHEF_LIEU}{code}",
        "nom": nom,
        "type": CHEF_LIEU,
        "lon": float(x),
        "lat": float(y),
        "code_province": str(code),
        "impose": False,
        "source_id": "SRC-06",
        "annee": annee,
        "statut": statut,
        "note": note,
    }


def province_du_point(provinces: gpd.GeoDataFrame, lon: float, lat: float) -> str | None:
    """Code de la province qui contient le point (WGS 84) ; None hors du Maroc."""
    point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(provinces.crs).iloc[0]
    dedans = provinces[provinces.geometry.contains(point)]
    return str(dedans["code_province"].iloc[0]) if not dedans.empty else None


def _agropoles(chemin: Path) -> pd.DataFrame:
    if not chemin.is_file():
        raise ErreurSite(f"{chemin} est absent (agropoles, section 4)")
    return pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False)


def _utilisateur(chemin: Path) -> list[dict[str, object]]:
    if not chemin.is_file():
        return []
    contenu = lire_yaml(chemin)
    if not isinstance(contenu, dict):
        return []
    return list(contenu.get("sites") or [])


def charger_sites(
    chemins: Chemins, config: ConfigLogistique, provinces: gpd.GeoDataFrame
) -> SitesCandidats:
    """Tous les sites candidats ; les agropoles sans coordonnées sont listées à part."""
    cible = chemins.preparees / config.sites.sortie_chefs_lieux
    if not cible.is_file():
        raise ErreurSite(
            "les chefs-lieux ne sont pas encore placés : lancez « python -m scripts.prepare »"
        )
    tables = [pd.read_parquet(cible)]
    agropoles = _agropoles(chemins.saisies / config.sites.fichier_agropoles)
    manquants = agropoles[(agropoles["lon"] == A_COMPLETER) | (agropoles["lat"] == A_COMPLETER)]
    connues = agropoles.drop(manquants.index)
    if not connues.empty:
        connues = connues.assign(
            lon=connues["lon"].astype(float),
            lat=connues["lat"].astype(float),
            impose=connues["impose"] == "oui",
            annee=pd.to_numeric(connues["annee"], errors="coerce"),
        )
        connues["code_province"] = [
            province_du_point(provinces, x, y)
            for x, y in zip(connues["lon"], connues["lat"], strict=True)
        ]
        tables.append(connues[COLONNES_SITES])
    utilisateur = _utilisateur(chemins.config / config.sites.fichier_utilisateur)
    if utilisateur:
        tables.append(pd.DataFrame(utilisateur).reindex(columns=COLONNES_SITES))
    sites = pd.concat(tables, ignore_index=True)
    sites["impose"] = sites["impose"].astype(bool)
    return SitesCandidats(sites, manquants[["id_site", "nom", "type", "ou_trouver"]])


def _ecrire_utilisateur(chemin: Path, sites: list[dict[str, object]]) -> None:
    entete = (
        "# Sites ajoutés par l'utilisateur (écran « Sites et logistique », UC-LOG-01).\n"
        "# Fichier local, ignoré par Git ; il est copié dans chaque scénario enregistré.\n"
    )
    texte = yaml.safe_dump({"sites": sites}, allow_unicode=True, sort_keys=False)
    provisoire = chemin.with_suffix(".tmp")
    provisoire.write_text(entete + texte, encoding="utf-8")
    provisoire.replace(chemin)


def ajouter_site(
    chemins: Chemins,
    config: ConfigLogistique,
    provinces: gpd.GeoDataFrame,
    nom: str,
    lon: float,
    lat: float,
    auteur: str,
) -> dict[str, object]:
    """Ajoute un site de l'utilisateur ; refusé hors des 75 provinces ou sans nom."""
    if not nom.strip():
        raise ErreurSite("donnez un nom au site")
    if not auteur.strip():
        raise ErreurSite("indiquez l'auteur de l'ajout")
    code = province_du_point(provinces, lon, lat)
    if code is None:
        raise ErreurSite(
            f"le point ({lat:.4f} ; {lon:.4f}) est hors des 75 provinces : vérifiez l'ordre "
            "latitude, longitude"
        )
    chemin = chemins.config / config.sites.fichier_utilisateur
    existants = _utilisateur(chemin)
    numeros = [int(str(s["id_site"])[len(PREFIXE_UTILISATEUR) :]) for s in existants]
    site: dict[str, object] = {
        "id_site": f"{PREFIXE_UTILISATEUR}{max(numeros, default=0) + 1}",
        "nom": nom.strip(),
        "type": UTILISATEUR,
        "lon": float(lon),
        "lat": float(lat),
        "code_province": code,
        "impose": False,
        "source_id": "SRC-17",
        "annee": date.today().year,
        "statut": Statut.TERRAIN.value,
        "note": f"ajouté par {auteur.strip()} le {date.today().isoformat()}",
    }
    _ecrire_utilisateur(chemin, [*existants, site])
    return site


def supprimer_site(chemins: Chemins, config: ConfigLogistique, id_site: str) -> None:
    """Retire un site de l'utilisateur (les chefs-lieux et agropoles ne se retirent pas)."""
    chemin = chemins.config / config.sites.fichier_utilisateur
    existants = _utilisateur(chemin)
    restants = [s for s in existants if s["id_site"] != id_site]
    if len(restants) == len(existants):
        raise ErreurSite(f"site « {id_site} » inconnu parmi les sites ajoutés par l'utilisateur")
    _ecrire_utilisateur(chemin, restants)
