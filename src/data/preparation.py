"""Préparation des données : ``data/raw/`` → ``data/processed/`` (UC-DAT-01 à 04).

Étapes : vérification des fichiers bruts, référentiel des provinces (RG-02), découpage CROPGRIDS,
surfaces CROPGRIDS par province, lecture et contrôle des statistiques (SRC-18, SRC-01),
désagrégation hiérarchique (RG-04), tables de référence, rapport de contrôle. Rien n'est écrit
dans ``data/raw/`` (RG-01) ; chaque table écrite garde la provenance de chaque valeur (RG-03).
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd
import xarray as xr

from src.chemins import Chemins
from src.data.config_preparation import (
    ConfigPreparation,
    ConfigSurfaces,
    charger_config_preparation,
)
from src.data.controles import dedoublonner, rendre_rapport, signaler_aberrantes
from src.data.cropgrids import charger_config_cropgrids, preparer_cropgrids
from src.data.desagregation import ResultatDesagregation, desagreger
from src.data.lecteurs.src01 import SOURCE_ID as SRC01
from src.data.lecteurs.src01 import lire_src01
from src.data.lecteurs.src18 import lire_src18
from src.data.observations import BilanControle, ErreurPreparation, tableau_observations
from src.data.provinces import (
    Referentiel,
    charger_config_referentiel,
    charger_referentiel,
    enregistrer_referentiel,
)
from src.data.sources import charger_sources
from src.data.surfaces import surface_agricole_par_province, surfaces_par_province
from src.data.tables_reference import (
    TablesReference,
    charger_catalogue,
    charger_tables_reference,
    liste,
)
from src.data.versions import Version, Versions
from src.decision.config import charger_config_decision
from src.decision.spatial import extraire_couche, population_rurale
from src.logistique.config import charger_config_logistique
from src.logistique.rattachement import points_de_rattachement
from src.logistique.sites import chefs_lieux, lire_designations, lire_lieux_osm
from src.scenarios.config import Controles, charger_controles


@dataclass(frozen=True)
class Statistiques:
    """Observations contrôlées, résultat de la désagrégation et bilan des contrôles."""

    observations: pd.DataFrame
    resultat: ResultatDesagregation
    bilan: BilanControle


@dataclass(frozen=True)
class BilanPreparation:
    """Fichiers écrits par :func:`preparer`."""

    ecrits: list[Path]
    statistiques: Statistiques


def fichiers_requis(chemins: Chemins, config: ConfigPreparation) -> list[Path]:
    """Fichiers bruts indispensables à la préparation."""
    referentiel = charger_config_referentiel(chemins)
    brutes = chemins.brutes
    src18 = chemins.manuelles / config.src18.dossier
    requis = [
        brutes / referentiel.source_polygones / referentiel.fichier_regions,
        brutes / referentiel.source_polygones / referentiel.fichier_provinces,
        brutes / referentiel.source_noms / referentiel.fichier_rgph,
        brutes / config.src01.dossier / config.src01.fichier,
        src18 / config.src18.saisies,
        src18 / config.src18.verifiees,
        src18 / config.src18.references,
    ]
    return requis


def verifier_fichiers(chemins: Chemins, config: ConfigPreparation) -> None:
    """Arrête la préparation avec la liste des fichiers manquants (UC-DAT-01)."""
    manquants = [f for f in fichiers_requis(chemins, config) if not f.is_file()]
    if manquants:
        liste = "\n".join(f"  - {f.relative_to(chemins.racine)}" for f in manquants)
        raise ErreurPreparation(
            f"fichiers bruts manquants :\n{liste}\nLancez « python -m scripts.download » puis "
            "déposez les fichiers manuels décrits dans docs/donnees_manuelles.md"
        )


def statistiques(
    dossier_src18: Path,
    dossier_src01: Path,
    config: ConfigPreparation,
    controles: Controles,
    referentiel: Referentiel,
    cultures: set[str],
    surfaces: pd.DataFrame,
    url_src01: str | None = None,
) -> Statistiques:
    """Lit, contrôle et désagrège les statistiques de production et de superficie."""
    bilan = BilanControle()
    lignes = lire_src18(dossier_src18, config.src18, referentiel, cultures, bilan)
    lignes += lire_src01(dossier_src01, config.src01, bilan, url_src01)
    observations = dedoublonner(tableau_observations(lignes), bilan)
    signaler_aberrantes(observations, bilan, controles.aberrantes)
    resultat = desagreger(
        observations,
        surfaces,
        referentiel.provinces,
        controles.desagregation.tolerance_somme,
    )
    return Statistiques(observations, resultat, bilan)


def _ecrire_parquet(table: pd.DataFrame, cible: Path) -> Path:
    provisoire = cible.with_name(f".{cible.name}.provisoire")
    table.to_parquet(provisoire, index=False)
    os.replace(provisoire, cible)
    return cible


def _url(chemins: Chemins, source_id: str, fichier: str) -> str | None:
    entree = charger_sources(chemins).sources[source_id].fichiers.get(fichier)
    return entree.url if entree else None


AUTEUR_PREPARATION = "python -m scripts.prepare"


def _versionner(chemins: Chemins, production: pd.DataFrame) -> Version | None:
    """Version initiale au premier passage, puis une version si la production a changé (RG-17).

    La table active étant celle de la dernière version, une nouvelle préparation n'est pas
    masquée par une version plus ancienne.
    """
    versions = Versions(chemins)
    if not versions.journal():
        return versions.initialiser(AUTEUR_PREPARATION, "données livrées (première préparation)")
    return versions.enregistrer(
        {"production": production}, AUTEUR_PREPARATION, "nouvelle préparation des données brutes"
    )


def _preparer_logistique(
    chemins: Chemins,
    tables: TablesReference,
    provinces: gpd.GeoDataFrame,
    config_cropgrids: ConfigSurfaces,
    crs_surface: str,
) -> list[Path]:
    """Points de rattachement des gisements et chefs-lieux (section 8.2, lot 3)."""
    logistique = charger_config_logistique(chemins)
    sortie = chemins.preparees
    cultures_par_residu = {
        code: liste(tables.residus.valeur(code, "codes_culture"))
        for code in charger_catalogue(chemins).residus.codes
    }
    with xr.open_dataset(sortie / charger_config_cropgrids(chemins).sortie) as cropgrids:
        points = points_de_rattachement(
            cropgrids,
            provinces,
            tables.cultures,
            cultures_par_residu,
            logistique.rattachement.variable_cropgrids,
            config_cropgrids.crs,
            crs_surface,
            config_cropgrids.annee,
        )
    ecrits = [_ecrire_parquet(points, sortie / logistique.rattachement.sortie)]
    s = logistique.sites
    lieux = lire_lieux_osm(
        chemins.brutes / s.source_osm / s.fichier_osm, s.couche_osm, s.types_lieux
    )
    annee = date.fromtimestamp((chemins.brutes / s.source_osm / s.fichier_osm).stat().st_mtime).year
    designations = lire_designations(chemins.saisies / s.fichier_chefs_lieux)
    sites = chefs_lieux(lieux, provinces, crs_surface, annee, designations)
    ecrits.append(_ecrire_parquet(sites, sortie / s.sortie_chefs_lieux))
    return ecrits


def _preparer_decision(chemins: Chemins, provinces: gpd.GeoDataFrame) -> list[Path]:
    """Routes principales, zones d'activité (OSM) et population rurale (critères F1, F2, G1)."""
    config = charger_config_decision(chemins)
    logistique = charger_config_logistique(chemins)
    pbf = chemins.brutes / logistique.sites.source_osm / logistique.sites.fichier_osm
    sortie = chemins.preparees
    ecrits = [
        extraire_couche(
            pbf, config.spatial.routes, "highway", sortie / config.spatial.routes.sortie
        ),
        extraire_couche(pbf, config.spatial.zones, "landuse", sortie / config.spatial.zones.sortie),
    ]
    population = population_rurale(
        chemins.brutes / config.population.source / config.population.fichier,
        set(provinces["code_province"].astype(str)),
        config,
    )
    ecrits.append(_ecrire_parquet(population, sortie / config.population.sortie))
    return ecrits


def preparer(chemins: Chemins, retelecharger: Callable[[], object]) -> BilanPreparation:
    """Prépare toutes les tables de ``data/processed/`` et le rapport de contrôle.

    Args:
        chemins: dossiers de l'outil.
        retelecharger: appelée si l'archive CROPGRIDS manque et que son découpage doit être
            refait (``python -m scripts.download --source SRC-04``).
    """
    config = charger_config_preparation(chemins)
    verifier_fichiers(chemins, config)
    controles = charger_controles(chemins)
    if Versions(chemins).journal():
        # Fichiers livrés mis à jour (data/input/) : nouvelle version avant toute lecture.
        Versions(chemins).integrer_livraisons(AUTEUR_PREPARATION)
    tables = charger_tables_reference(chemins)
    sortie = chemins.preparees
    sortie.mkdir(parents=True, exist_ok=True)
    ecrits = enregistrer_referentiel(chemins, sortie)
    referentiel = charger_referentiel(chemins)
    preparer_cropgrids(chemins, retelecharger)
    provinces = gpd.read_file(sortie / "provinces.gpkg")
    with xr.open_dataset(sortie / charger_config_cropgrids(chemins).sortie) as cropgrids:
        crs_surface = charger_config_referentiel(chemins).crs_surface
        surfaces = surfaces_par_province(
            cropgrids, provinces, tables.cultures, config.cropgrids, crs_surface
        )
        agricole = surface_agricole_par_province(
            cropgrids, provinces, config.cropgrids, crs_surface
        )
    ecrits.append(_ecrire_parquet(surfaces, sortie / config.cropgrids.sortie))
    ecrits.append(_ecrire_parquet(agricole, sortie / config.cropgrids.sortie_agricole))
    ecrits += _preparer_logistique(chemins, tables, provinces, config.cropgrids, crs_surface)
    ecrits += _preparer_decision(chemins, provinces)
    resultats = statistiques(
        chemins.manuelles / config.src18.dossier,
        chemins.brutes / config.src01.dossier,
        config,
        controles,
        referentiel,
        set(tables.cultures["code_culture"]),
        surfaces,
        _url(chemins, SRC01, config.src01.fichier),
    )
    ecrits.append(_ecrire_parquet(resultats.observations, sortie / config.sorties.observations))
    ecrits.append(
        _ecrire_parquet(resultats.resultat.production, sortie / config.sorties.production)
    )
    for nom, table in (
        ("residus", tables.residus.tableau()),
        ("concurrence", tables.concurrence.tableau()),
        ("facteurs_emission", tables.facteurs_emission.tableau()),
        ("cultures", tables.cultures),
        ("calendrier", tables.calendrier),
    ):
        ecrits.append(_ecrire_parquet(table.astype(object).astype(str), sortie / f"{nom}.parquet"))
    titres = {
        identifiant: source.titre
        for identifiant, source in charger_sources(chemins).sources.items()
    }
    rapport = rendre_rapport(resultats.bilan, resultats.resultat, referentiel.provinces, titres)
    cible = sortie / config.sorties.rapport
    cible.write_text(rapport, encoding="utf-8")
    ecrits.append(cible)
    _versionner(chemins, resultats.resultat.production)
    return BilanPreparation(ecrits, resultats)
