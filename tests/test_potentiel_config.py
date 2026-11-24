"""Lot 2, tâche 1 : versions actives, configuration du potentiel, PAR-62, PAR-63, surfaces.

Les tables viennent de data/input/ (valeurs de référence livrées) et de l'extrait figé
tests/fixtures/production/. Les valeurs modifiées sont des « saisies simulées pour le test ».
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.chemins import Chemins, chemins_par_defaut
from src.data.provenance import Statut
from src.data.tables_reference import charger_tables_reference
from src.data.versions import Versions
from src.lecture_yaml import ErreurConfiguration
from src.potentiel.config import ConfigPotentiel, charger_config_potentiel
from src.scenarios.config import charger_parametres
from src.scenarios.parametres import ErreurParametre, regler_parametre, valeur_courante
from tests.aides import copier_config

DEPOT = chemins_par_defaut()
CONFIG = charger_config_potentiel(DEPOT)
RESIDUS = pd.read_csv(
    DEPOT.saisies / "residus.csv", sep=";", dtype=str, keep_default_na=False, encoding="utf-8"
)
FIXTURES = DEPOT.racine / "tests" / "fixtures" / "production"
AUTEUR = "test automatique"


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    return chemins


# --- Versions actives -------------------------------------------------------------------


def test_les_calculs_lisent_la_version_active(chemins: Chemins) -> None:
    versions = Versions(chemins)
    versions.initialiser(AUTEUR, "données livrées")
    residus = versions.lire("residus")
    ligne = (residus["code_residu"] == "R01") & (residus["parametre"] == "carbone")
    residus.loc[ligne, "valeur"] = "49"  # saisie simulée pour le test
    versions.enregistrer({"residus": residus}, AUTEUR, "saisie simulée pour le test")
    tables = charger_tables_reference(chemins)
    assert tables.residus.valeur("R01", "carbone").lire() == 49
    # Le fichier livré n'a pas changé (RG-17).
    livre = charger_tables_reference(chemins).residus
    assert livre is not None
    assert "48.3" in (chemins.saisies / "residus.csv").read_text(encoding="utf-8")


def test_sans_version_les_fichiers_livres_sont_lus(chemins: Chemins) -> None:
    assert charger_tables_reference(chemins).residus.valeur("R01", "carbone").lire() == 48.3


# --- Configuration du potentiel ----------------------------------------------------------


def test_configuration_chargee() -> None:
    assert CONFIG.unites_ratio["kg MS/arbre/an"].base == "MS"
    assert CONFIG.unites_ratio["t brute/t produit"].base == "brute"
    assert CONFIG.unites_fraction["% masse brute"] == pytest.approx(0.01)
    assert CONFIG.moins_fiable([Statut.MESUREE, Statut.ESTIMEE, Statut.LITTERATURE]) is (
        Statut.ESTIMEE
    )
    assert CONFIG.moins_fiable([Statut.MESUREE, Statut.HYPOTHESE]) is Statut.HYPOTHESE


def test_chaque_precision_de_residus_a_un_role() -> None:
    precisions = RESIDUS[RESIDUS["precision"] != ""][["code_residu", "parametre"]]
    sans_role = [
        f"{r} · {p}"
        for r, p in precisions.drop_duplicates().itertuples(index=False)
        if CONFIG.role(r, p) is None
    ]
    assert sans_role == []


def test_unites_des_ratios_et_des_fractions_connues() -> None:
    ratios = RESIDUS[RESIDUS["parametre"].isin(["rpr", "rendement_surf", "rendement_arbre"])]
    assert set(ratios["unite"]) <= set(CONFIG.unites_ratio)
    fractions = RESIDUS[RESIDUS["parametre"].isin(["humidite", "carbone", "f_col", "f_eco"])]
    assert set(fractions["unite"]) <= set(CONFIG.unites_fraction)
    densites = RESIDUS[RESIDUS["parametre"] == "densite_plantation"]
    assert set(densites["unite"]) == {CONFIG.unite_densite}


@pytest.mark.parametrize(
    ("identifiant", "residu", "parametre"),
    [("PAR-62", "R05", "rpr"), ("PAR-62", "R05", "humidite"), ("PAR-63", "R12", "rpr")],
)
def test_choix_des_variantes_egaux_aux_precisions(
    identifiant: str, residu: str, parametre: str
) -> None:
    role = CONFIG.role(residu, parametre)
    assert role is not None and role.choix_par == identifiant
    precisions = set(
        RESIDUS[(RESIDUS["code_residu"] == residu) & (RESIDUS["parametre"] == parametre)][
            "precision"
        ]
    )
    assert precisions <= set(charger_parametres(DEPOT)[identifiant].choix)


def test_variante_sans_parametre_de_choix_refusee(chemins: Chemins) -> None:
    chemin = chemins.config / "potentiel.yaml"
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    donnees["precisions"][2].pop("choix_par")
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="choix_par"):
        charger_config_potentiel(chemins)


def test_ordre_des_statuts_complet_exige() -> None:
    donnees = CONFIG.model_dump()
    donnees["ordre_statuts"] = ["Hypothèse", "Mesurée"]
    with pytest.raises(ValueError, match="ordre_statuts"):
        ConfigPotentiel.model_validate(donnees)


# --- PAR-62 et PAR-63 --------------------------------------------------------------------


def test_procede_de_trituration_a_completer_puis_choisi(chemins: Chemins) -> None:
    assert valeur_courante(chemins, "PAR-62").est_a_completer
    with pytest.raises(ErreurParametre, match="choisissez parmi"):
        regler_parametre(chemins, "PAR-62", "centrifugeuse", "choix de l'équipe", AUTEUR)
    # Saisie simulée pour le test : choix d'un procédé cité au §14.2.
    choisi = regler_parametre(chemins, "PAR-62", "trois phases", "choix de l'équipe", AUTEUR)
    assert choisi.lire() == "trois phases"


# --- Surface agricole ----------------------------------------------------------------------


def test_surface_agricole_couvre_les_cultures_du_lot() -> None:
    agricole = pd.read_csv(
        FIXTURES / "surface_agricole.csv", sep=";", dtype={"code_province": str}
    ).set_index("code_province")["surface_ha"]
    cultures = (
        pd.read_csv(FIXTURES / "surfaces_cropgrids.csv", sep=";", dtype={"code_province": str})
        .groupby("code_province")["surface_ha"]
        .sum()
    )
    assert len(agricole) == 75
    assert (agricole.reindex(cultures.index) + 1e-6 >= cultures).all()
    assert agricole.sum() > cultures.sum()
