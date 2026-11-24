"""Lot 2, tâche 2 : gisement théorique T (section 8.1, UC-POT-01).

Production : extrait figé des données réelles (tests/fixtures/production/, olivier, palmier
dattier et blé). Valeurs de référence : data/input/residus.csv. Les valeurs attendues sont
recalculées à la main dans chaque test à partir de ces données ; les saisies de l'utilisateur
sont nommées « saisie simulée pour le test ».
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest

from src.chemins import Chemins
from src.data.versions import Versions
from src.potentiel.entrees import EntreesPotentiel, charger_entrees
from src.potentiel.theorique import CAMPAGNE_REFERENCE, campagnes_reference
from src.scenarios.parametres import regler_parametre
from tests.aides import copier_config
from tests.test_preparation import DEPOT, TAOUNATE, _referentiel, _statistiques

AUTEUR = "test automatique"
PRECISION = 1e-3  # 0,1 % (critère UC-POT-01)
FIGUIG = "2251"
REGION_FES_MEKNES = "3"
CAMPAGNES = 5  # PAR-02 livré : moyenne des 5 dernières campagnes disponibles


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    chemins.preparees.mkdir(parents=True)
    _statistiques().resultat.production.to_parquet(
        chemins.preparees / "production.parquet", index=False
    )
    return chemins


def _entrees(chemins: Chemins) -> EntreesPotentiel:
    return charger_entrees(chemins, _referentiel())


def _moyenne_a_la_main(production: pd.DataFrame, province: str, culture: str, variable: str):
    """Moyenne des 5 campagnes les plus récentes disponibles, recalculée sans le code testé."""
    lignes = production[
        (production["code_province"] == province)
        & (production["code_culture"] == culture)
        & (production["variable"] == variable)
    ].sort_values("campagne", ascending=False)
    retenues = lignes.head(CAMPAGNES)
    return retenues["valeur"].sum() / len(retenues), list(retenues["campagne"])


def _t(resultat, province: str, residu: str, campagne: str = CAMPAGNE_REFERENCE) -> pd.Series:
    g = resultat.gisements
    choix = g[
        (g["code_province"] == province)
        & (g["code_residu"] == residu)
        & (g["campagne"] == campagne)
    ]
    assert len(choix) == 1, f"{residu} × {province} × {campagne} absent"
    return choix.iloc[0]


def test_couple_r01_taounate_recalcule_a_la_main(chemins: Chemins) -> None:
    """R01 (taille d'olivier, mode surface, ratio en t MS : pas d'humidité) :
    T = superficie moyenne d'olivier × 1,23 t MS/ha/an (milieu de 1,15 à 1,31, §14.2)."""
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    superficie, campagnes = _moyenne_a_la_main(
        entrees.production, TAOUNATE, "olivier", "superficie_ha"
    )
    attendu = superficie * 1.23
    ligne = _t(resultat, TAOUNATE, "R01")
    assert ligne["valeur"] == pytest.approx(attendu, rel=PRECISION)
    assert ligne["unite"] == "t MS/an"
    assert ligne["campagnes"].split("; ") == sorted(campagnes)
    # Le ratio est un milieu de fourchette (Hypothèse) : statut le moins fiable des entrées.
    assert ligne["statut"] == "Hypothèse"
    assert "SRC-16-ZARAGOZA" in ligne["sources"]
    assert "humidité" not in ligne["note"]


def test_t_par_campagne(chemins: Chemins) -> None:
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    p = entrees.production
    superficie = p[
        (p["code_province"] == TAOUNATE)
        & (p["code_culture"] == "olivier")
        & (p["variable"] == "superficie_ha")
        & (p["campagne"] == "2017-2018")
    ]["valeur"].iloc[0]
    ligne = _t(resultat, TAOUNATE, "R01", "2017-2018")
    assert ligne["valeur"] == pytest.approx(superficie * 1.23, rel=PRECISION)


def test_campagnes_de_reference_et_prevision_signalee(chemins: Chemins) -> None:
    production = _entrees(chemins).production
    reference = campagnes_reference(production, CAMPAGNES)
    taounate = reference[
        (reference["code_province"] == TAOUNATE)
        & (reference["code_culture"] == "olivier")
        & (reference["variable"] == "production_t")
    ].iloc[0]
    # Olivier : 2023-2024 (total national prévisionnel) et 2018-2019 (prévision de la DRA).
    assert taounate["campagnes"].split("; ") == [
        "2016-2017",
        "2017-2018",
        "2018-2019",
        "2019-2020",
        "2023-2024",
    ]
    assert taounate["previsionnel"]


def test_r06_nombre_de_pieds_avec_densite_de_secours(chemins: Chemins) -> None:
    """R06 : N = superficie de palmier × 112,5 pieds/ha (statut Estimée) ; 21,2 kg MS/pied/an."""
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    superficie, _ = _moyenne_a_la_main(
        entrees.production, FIGUIG, "palmier_dattier", "superficie_ha"
    )
    attendu = superficie * 112.5 * 21.2 / 1000
    ligne = _t(resultat, FIGUIG, "R06")
    assert ligne["valeur"] == pytest.approx(attendu, rel=PRECISION)
    assert ligne["statut"] in {"Estimée", "Hypothèse"}
    assert "densité de plantation de secours" in ligne["note"]


def test_r04_un_ratio_par_culture(chemins: Chemins) -> None:
    residu = _entrees(chemins).calcul_theorique()._residu("R04")
    assert residu.ratios["amandier"].valeur == pytest.approx(0.755)
    assert residu.ratios["rosacees"].valeur == pytest.approx(2.16)


def test_r13_orge_au_coefficient_du_ble_statut_hypothese(chemins: Chemins) -> None:
    versions = Versions(chemins)
    versions.initialiser(AUTEUR, "données livrées")
    residus = versions.lire("residus")
    ligne = (residus["code_residu"] == "R13") & (residus["parametre"] == "humidite")
    residus.loc[ligne, ["valeur", "source_id", "annee", "statut"]] = [
        "15",  # saisie simulée pour le test
        "mesure interne",
        "2026",
        "Terrain",
    ]
    versions.enregistrer({"residus": residus}, AUTEUR, "saisie simulée pour le test")
    residu = _entrees(chemins).calcul_theorique()._residu("R13")
    assert residu.ratios["orge"].valeur == residu.ratios["ble"].valeur
    assert residu.ratios["orge"].statut.value == "Hypothèse"
    assert residu.humidite is not None and residu.humidite.valeur == pytest.approx(0.15)


def test_ratio_en_masse_brute_sans_humidite_exclu(chemins: Chemins) -> None:
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    r10 = resultat.exclus[resultat.exclus["code_residu"] == "R10"]
    assert len(r10) == len(_referentiel().provinces)
    assert r10["motif"].str.contains("humidite à compléter").all()
    # Un couple exclu n'est jamais compté zéro (RG-06).
    assert not (resultat.gisements["code_residu"] == "R10").any()


def test_r05_bloque_sans_procede_puis_calcule_en_fes_meknes_seulement(chemins: Chemins) -> None:
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    motifs = resultat.exclus[resultat.exclus["code_residu"] == "R05"]["motif"]
    assert motifs.str.contains("PAR-62").all()
    # Saisie simulée pour le test : procédé à trois phases (0,5 t brute/t, humidité 45 %).
    regler_parametre(chemins, "PAR-62", "trois phases", "choix de l'équipe", AUTEUR)
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    production, _ = _moyenne_a_la_main(entrees.production, TAOUNATE, "olivier", "production_t")
    attendu = production * 0.8 * 0.5 * (1 - 0.45)
    ligne = _t(resultat, TAOUNATE, "R05")
    assert ligne["valeur"] == pytest.approx(attendu, rel=PRECISION)
    calcules = set(resultat.gisements[resultat.gisements["code_residu"] == "R05"]["code_province"])
    assert {entrees.region_de[p] for p in calcules} == {REGION_FES_MEKNES}
    hors = resultat.exclus[resultat.exclus["code_residu"] == "R05"]
    assert hors["motif"].str.contains("Fès-Meknès seulement").all()


def test_chaque_couple_est_calcule_ou_exclu(chemins: Chemins) -> None:
    entrees = _entrees(chemins)
    resultat = entrees.calcul_theorique().calculer(entrees.production)
    reference = resultat.gisements[resultat.gisements["campagne"] == CAMPAGNE_REFERENCE]
    calcules = set(zip(reference["code_province"], reference["code_residu"], strict=True))
    exclus = set(zip(resultat.exclus["code_province"], resultat.exclus["code_residu"], strict=True))
    assert not calcules & exclus
    assert len(calcules | exclus) == len(_referentiel().provinces) * len(
        entrees.catalogue.residus.codes
    )
    assert (reference["valeur"] >= 0).all()
