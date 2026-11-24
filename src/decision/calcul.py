"""Fonction principale du module M4 : valeurs des critères de chaque site, puis classement.

:func:`preparer_criteres` assemble les sorties des modules M1 à M3 (courbes et bassins,
bilans climat) et les indicateurs spatiaux, et calcule la matrice sites × critères. Le
classement (:func:`src.decision.classement.classer`) est ensuite recalculé à chaque changement
de poids, sans refaire cette matrice (UC-DEC-04 : moins de 2 s).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import xarray as xr

from src.chemins import Chemins
from src.data.provenance import ValeurACompleter
from src.decision.config import (
    CatalogueCriteres,
    ConfigDecision,
    charger_catalogue_criteres,
    charger_config_decision,
)
from src.decision.indicateurs import ContexteIndicateurs, matrice_criteres
from src.decision.spatial import distances_plus_proches, surface_dans_rayon
from src.logistique.calcul import ResultatLogistique
from src.logistique.couts import Blocage, Courbe


@dataclass(frozen=True)
class DonneesDecision:
    """Matrice des critères et informations nécessaires au classement."""

    catalogue: CatalogueCriteres
    config: ConfigDecision
    valeurs: pd.DataFrame
    motifs: pd.DataFrame
    atteignable: dict[str, bool | None]
    sites: pd.DataFrame


def _spatial(
    chemins: Chemins, config: ConfigDecision, logistique: ResultatLogistique
) -> dict[str, dict[str, float]]:
    sites = logistique.sites.sites
    ids = sites["id_site"].tolist()
    resultat: dict[str, dict[str, float]] = {}
    sortie = chemins.preparees
    routes = sortie / config.spatial.routes.sortie
    zones = sortie / config.spatial.zones.sortie
    if routes.is_file():
        d = distances_plus_proches(sites, gpd.read_file(routes), config)
        resultat["distance_route"] = dict(zip(ids, d.tolist(), strict=True))
    if zones.is_file():
        couche = gpd.read_file(zones)
        agropoles = sites[sites["type"] == "agropole"]
        if not agropoles.empty:
            points = gpd.GeoDataFrame(
                geometry=gpd.points_from_xy(agropoles["lon"], agropoles["lat"]), crs="EPSG:4326"
            ).to_crs(couche.crs)
            couche = pd.concat([couche[["geometry"]], points], ignore_index=True)
        d = distances_plus_proches(sites, gpd.GeoDataFrame(couche, crs=couche.crs), config)
        resultat["distance_zone"] = dict(zip(ids, d.tolist(), strict=True))
    population = sortie / config.population.sortie
    if population.is_file():
        table = pd.read_parquet(population).set_index("code_province")["population_rurale"]
        resultat["population_rurale"] = {
            s: float(table[str(p)])
            for s, p in zip(ids, sites["code_province"], strict=True)
            if p is not None and str(p) in table.index
        }
    cropgrids = sortie / "cropgrids_maroc.nc"
    try:
        rayon = float(logistique.lire(config.parametres.rayon_e1).lire_nombre())
    except (ValeurACompleter, TypeError):
        rayon = None
    if cropgrids.is_file() and rayon is not None:
        with xr.open_dataset(cropgrids) as grille:
            s = surface_dans_rayon(
                sites, grille, "croparea", rayon, logistique.config.rayon_terre_km
            )
        resultat["surface_agricole"] = dict(zip(ids, s.tolist(), strict=True))
    return resultat


def preparer_criteres(
    chemins: Chemins,
    logistique: ResultatLogistique,
    bilans: pd.DataFrame,
    calendrier: pd.DataFrame,
) -> DonneesDecision:
    """Matrice sites × critères P1 et capacité atteignable de chaque site (RG-10).

    Args:
        chemins: dossiers de l'outil.
        logistique: résultat du module M2 (sites, courbes, paramètres).
        bilans: bilans climat de tous les couples × sites (module M3).
        calendrier: ``calendrier.csv`` actif (critère A4).
    """
    catalogue = charger_catalogue_criteres(chemins)
    config = charger_config_decision(chemins)
    sites = logistique.sites.sites
    courbes: dict[str, Courbe | str] = {}
    atteignable: dict[str, bool | None] = {}
    for site in sites["id_site"]:
        try:
            courbe, _ = logistique.courbe(site)
            courbes[site] = courbe
            atteignable[site] = courbe.atteignable
        except Blocage as blocage:
            courbes[site] = (
                f"bassin d'approvisionnement non calculé : {str(blocage).splitlines()[0]}"
            )
            atteignable[site] = None
    ctx = ContexteIndicateurs(
        sites=sites,
        courbes=courbes,
        bilans=bilans,
        residus=logistique.residus,
        concurrence=logistique.concurrence,
        national=logistique.national,
        calendrier=calendrier,
        mois=config.mois,
        lire=logistique.lire,
        parametres=config.parametres.model_dump(),
        spatial=_spatial(chemins, config, logistique),
        tonnages_rayon={s: logistique.tonnage_rayon(s) for s in sites["id_site"]},
        gisements=logistique.gisements,
        pourcentage=config.pourcentage,
    )
    calculs = {
        code: c.calcul
        for code, c in catalogue.criteres.items()
        if c.priorite == "P1" and c.calcul and "S" in c.niveaux
    }
    valeurs, motifs = matrice_criteres(ctx, calculs)
    return DonneesDecision(catalogue, config, valeurs, motifs, atteignable, sites)


def actifs_par_defaut(catalogue: CatalogueCriteres, renseignes: set[str]) -> list[str]:
    """Critères actifs par défaut (section 9) ; C6 dès que PAR-55 et PAR-56 sont saisis."""
    return [
        code
        for code, c in catalogue.criteres.items()
        if c.priorite == "P1"
        and "S" in c.niveaux
        and (c.actif_defaut or (c.actif_si and set(c.actif_si) <= renseignes))
    ]


def variations_de_rang(
    dossier: Path, empreinte_parametres: str, rangs: dict[str, int]
) -> dict[str, int]:
    """RG-16 : gain (+) ou perte (−) de rang de chaque site depuis le réglage précédent.

    L'historique garde le dernier classement de chaque réglage des paramètres de l'entreprise ;
    la variation compare au dernier réglage différent du réglage courant.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / "historique_classements.json"
    historique = json.loads(fichier.read_text(encoding="utf-8")) if fichier.is_file() else []
    precedents = [h for h in historique if h["empreinte"] != empreinte_parametres]
    reference = precedents[-1]["rangs"] if precedents else {}
    historique = [h for h in historique if h["empreinte"] != empreinte_parametres]
    historique.append(
        {
            "empreinte": empreinte_parametres,
            "date": datetime.now().isoformat(timespec="seconds"),
            "rangs": rangs,
        }
    )
    fichier.write_text(json.dumps(historique[-20:], ensure_ascii=False), encoding="utf-8")
    return {s: reference[s] - r for s, r in rangs.items() if s in reference}


def empreinte(valeurs: dict[str, object]) -> str:
    """Empreinte d'un réglage des paramètres de l'entreprise."""
    texte = json.dumps(valeurs, sort_keys=True, default=str)
    return hashlib.sha256(texte.encode()).hexdigest()[:16]
