"""Paramètres de l'entreprise, paramètres techniques et scénarios (UC-ENT-01, UC-SCN-01, 02).

Chaque test travaille sur une copie de config/. Les valeurs de l'entreprise sont des « saisies
simulées pour le test » : aucune n'est livrée dans config/ (RG-15).
"""

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from src.chemins import Chemins
from src.data.provenance import ValeurACompleter
from src.data.versions import Versions
from src.scenarios.config import charger_entreprise, charger_parametres
from src.scenarios.entreprise import ErreurEntreprise, abonner, mettre_a_jour_entreprise
from src.scenarios.parametres import (
    ErreurParametre,
    etat_parametres,
    regler_parametre,
    revenir_au_defaut,
    valeur_courante,
)
from src.scenarios.scenarios import (
    ErreurScenario,
    Site,
    appliquer_scenario,
    charger_scenario,
    dernier_scenario,
    ecart_de_version,
    enregistrer_scenario,
    lister_scenarios,
    nom_de_fichier,
    scenario_courant,
)
from tests.aides import copier_config
from tests.test_preparation import DEPOT

AUTEUR = "test automatique"
# Saisies simulées pour le test (UC-ENT-02 cite un prix plafond de 300 à 900 DH/t).
# Gazole à 12 DH/L : exemple du calcul de PAR-33 au §14.3.
SAISIE_SIMULEE = {"PAR-01": 20000, "PAR-21": "moyenne", "PAR-34": 600, "PAR-37": 12}


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    return chemins


# --- Paramètres de l'entreprise (RG-15, RG-16) ---------------------------------------------


def test_renseignement_requis_tant_qu_un_parametre_manque(chemins: Chemins) -> None:
    entreprise, _ = mettre_a_jour_entreprise(
        chemins, {"PAR-21": SAISIE_SIMULEE["PAR-21"], "PAR-34": SAISIE_SIMULEE["PAR-34"]}, AUTEUR
    )
    assert entreprise.renseignement_requis
    with pytest.raises(ValeurACompleter):
        entreprise.lire("PAR-01")  # aucun défaut n'est appliqué
    assert entreprise.a_renseigner == ["PAR-01", "PAR-37"]
    entreprise, _ = mettre_a_jour_entreprise(
        chemins, {"PAR-01": SAISIE_SIMULEE["PAR-01"], "PAR-37": SAISIE_SIMULEE["PAR-37"]}, AUTEUR
    )
    assert not entreprise.renseignement_requis
    assert entreprise.lire("PAR-01") == SAISIE_SIMULEE["PAR-01"]


def test_saisie_ecrite_dans_le_fichier_local_jamais_dans_le_modele(chemins: Chemins) -> None:
    modele = (chemins.config / "entreprise.yaml").read_bytes()
    mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, AUTEUR)
    assert (chemins.config / "entreprise.yaml").read_bytes() == modele
    local = yaml.safe_load((chemins.config / "entreprise.local.yaml").read_text(encoding="utf-8"))
    assert local["valeurs"] == SAISIE_SIMULEE
    assert local["auteur"] == AUTEUR
    # Effacer une valeur la retire du fichier local.
    mettre_a_jour_entreprise(chemins, {"PAR-37": None}, AUTEUR)
    local = yaml.safe_load((chemins.config / "entreprise.local.yaml").read_text(encoding="utf-8"))
    assert "PAR-37" not in local["valeurs"]


def test_mise_a_jour_datee_et_signee(chemins: Chemins) -> None:
    jour = date(2026, 11, 22)
    mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, AUTEUR, jour)
    relue = charger_entreprise(chemins)
    assert relue.date_modification == jour
    assert relue.auteur == AUTEUR
    texte = (chemins.config / "entreprise.local.yaml").read_text(encoding="utf-8")
    assert texte.startswith("# Saisies d'Atlantic Biochar")
    assert relue.parametres["PAR-21"].choix == ["basse", "moyenne", "haute"]


def test_evenement_parametres_modifies(chemins: Chemins) -> None:
    recus = []
    desabonner = abonner(recus.append)
    try:
        mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, AUTEUR)
        mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, AUTEUR)  # aucun changement
        mettre_a_jour_entreprise(chemins, {"PAR-34": 900}, AUTEUR)
    finally:
        desabonner()
    assert len(recus) == 2
    assert set(recus[0].identifiants) == set(SAISIE_SIMULEE)
    assert recus[1].avant == {"PAR-34": SAISIE_SIMULEE["PAR-34"]}
    assert recus[1].apres == {"PAR-34": 900}


@pytest.mark.parametrize(
    ("valeurs", "motif"),
    [
        ({"PAR-01": -5}, "positive"),
        ({"PAR-52": 120}, "entre 0 et 100"),
        ({"PAR-21": "tiède"}, "n'est pas un nombre"),
        ({"PAR-57": ["site"]}, "imposes et exclus"),
        ({"PAR-99": 1}, "inconnus"),
    ],
)
def test_valeurs_refusees(chemins: Chemins, valeurs: dict, motif: str) -> None:
    with pytest.raises(ErreurEntreprise, match=motif):
        mettre_a_jour_entreprise(chemins, valeurs, AUTEUR)
    assert charger_entreprise(chemins).renseignement_requis


def test_auteur_obligatoire(chemins: Chemins) -> None:
    with pytest.raises(ErreurEntreprise, match="auteur"):
        mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, " ")


def test_sites_imposes_et_exclus(chemins: Chemins) -> None:
    entreprise, _ = mettre_a_jour_entreprise(
        chemins, {"PAR-57": {"imposes": ["meknes"], "exclus": []}}, AUTEUR
    )
    assert entreprise.lire("PAR-57") == {"imposes": ["meknes"], "exclus": []}


# --- Paramètres techniques (UC-SCN-01) --------------------------------------------------------


def test_retour_au_defaut_d_un_parametre_technique(chemins: Chemins) -> None:
    defaut = charger_parametres(chemins)["PAR-35"].valeur
    assert defaut is not None
    reglee = regler_parametre(chemins, "PAR-35", "80", "réglage de l'équipe", AUTEUR)
    assert reglee.lire() == 80
    assert reglee.provenance is not None and reglee.provenance.source_id == "réglage de l'équipe"
    assert valeur_courante(chemins, "PAR-35").lire() == 80
    etat = {e.identifiant: e for e in etat_parametres(chemins)}["PAR-35"]
    assert etat.modifie and etat.defaut == defaut
    assert revenir_au_defaut(chemins, "PAR-35") == defaut
    assert valeur_courante(chemins, "PAR-35") == defaut
    assert not {e.identifiant: e for e in etat_parametres(chemins)}["PAR-35"].modifie


def test_composante_et_valeur_a_completer(chemins: Chemins) -> None:
    regler_parametre(chemins, "PAR-20:moyenne", "0,78", "réglage de l'équipe", AUTEUR)
    assert valeur_courante(chemins, "PAR-20:moyenne").lire() == pytest.approx(0.78)
    assert valeur_courante(chemins, "PAR-20:haute").lire() == pytest.approx(0.89)
    assert valeur_courante(chemins, "PAR-61").est_a_completer
    identifiants = {e.identifiant for e in etat_parametres(chemins)}
    assert {"PAR-20:basse", "PAR-20:moyenne", "PAR-20:haute", "PAR-33"} <= identifiants


@pytest.mark.parametrize(
    ("identifiant", "valeur", "source", "motif"),
    [
        ("PAR-33", "10", "x", "calculé par l'outil"),
        ("PAR-20", "0.8", "x", "composantes"),
        ("PAR-35", "beaucoup", "x", "n'est pas un nombre"),
        ("PAR-35", "80", "", "source obligatoire"),
    ],
)
def test_reglages_refuses(
    chemins: Chemins, identifiant: str, valeur: str, source: str, motif: str
) -> None:
    with pytest.raises(ErreurParametre, match=motif):
        regler_parametre(chemins, identifiant, valeur, source, AUTEUR)


# --- Scénarios (UC-SCN-02, UC-DAT-08) ----------------------------------------------------------


def test_scenario_enregistre_puis_recharge_a_l_identique(chemins: Chemins) -> None:
    mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, AUTEUR)
    regler_parametre(chemins, "PAR-35", "80", "réglage de l'équipe", AUTEUR)
    scenario = scenario_courant(
        chemins,
        "Scénario de test Meknès",
        AUTEUR,
        criteres_actifs=["A1", "C1"],
        seuils={"C1": 600},
        poids={"A1": 0.5, "C1": 0.5},
        methode="WSM",
        sites=[Site(id_site="meknes", nom="Meknès", type="chef-lieu", lon=-5.55, lat=33.9)],
    )
    chemin = enregistrer_scenario(chemins, scenario)
    assert chemin.name == "scenario-de-test-meknes.yaml"
    assert charger_scenario(chemins, "Scénario de test Meknès") == scenario
    assert dernier_scenario(chemins) == scenario
    assert [s.nom for s in lister_scenarios(chemins)] == [scenario.nom]
    with pytest.raises(ErreurScenario, match="existe déjà"):
        enregistrer_scenario(chemins, scenario)
    assert enregistrer_scenario(chemins, scenario, remplacer=True) == chemin


def test_scenario_indique_sa_version_de_donnees(chemins: Chemins) -> None:
    versions = Versions(chemins)
    versions.initialiser(AUTEUR, "données livrées")
    scenario = scenario_courant(chemins, "avec version", AUTEUR)
    enregistrer_scenario(chemins, scenario)
    recharge = charger_scenario(chemins, "avec version")
    assert recharge.version_donnees == "v0001"
    assert ecart_de_version(chemins, recharge) is None
    residus = versions.lire("residus")
    residus.loc[0, "note"] = "saisie simulée pour le test"
    versions.enregistrer({"residus": residus}, AUTEUR, "note modifiée")
    message = ecart_de_version(chemins, recharge)
    assert message is not None and "v0001" in message and "v0002" in message


def test_appliquer_un_scenario_restaure_ses_parametres(chemins: Chemins) -> None:
    mettre_a_jour_entreprise(chemins, SAISIE_SIMULEE, AUTEUR)
    regler_parametre(chemins, "PAR-35", "80", "réglage de l'équipe", AUTEUR)
    scenario = scenario_courant(chemins, "référence", AUTEUR)
    mettre_a_jour_entreprise(chemins, {"PAR-34": 900}, AUTEUR)
    revenir_au_defaut(chemins, "PAR-35")
    appliquer_scenario(chemins, scenario, AUTEUR)
    assert charger_entreprise(chemins).lire("PAR-34") == SAISIE_SIMULEE["PAR-34"]
    assert valeur_courante(chemins, "PAR-35").lire() == 80


def test_nom_de_scenario_et_fichier_illisible(chemins: Chemins) -> None:
    assert nom_de_fichier("  Été 2026 / Fès ") == "ete-2026-fes.yaml"
    with pytest.raises(ErreurScenario, match="inutilisable"):
        nom_de_fichier("!!!")
    with pytest.raises(ErreurScenario, match="introuvable"):
        charger_scenario(chemins, "absent")
    assert dernier_scenario(chemins) is None


def test_livraison_sans_valeur_supposee() -> None:
    entreprise = charger_entreprise(DEPOT, avec_saisies=False)
    assert entreprise.obligatoires == ["PAR-01", "PAR-21", "PAR-34", "PAR-37"]
    assert all(not entreprise.parametres[p].renseigne for p in entreprise.obligatoires)
