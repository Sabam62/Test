"""Versions, import Excel, saisie directe et prix observés (UC-DAT-06 à 08, RG-17 à RG-19).

Les tables viennent de l'extrait figé des données réelles (tests/fixtures/production/) et de
data/input/, copiés dans un dossier temporaire. Les valeurs modifiées sont nommées « saisie
simulée pour le test » : elles imitent une correction de l'utilisateur, jamais une donnée livrée.
"""

import io
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.chemins import Chemins
from src.data.excel import (
    FEUILLE_DONNEES,
    FEUILLE_MODE,
    FEUILLE_UNITES,
    ErreurImport,
    analyser_import,
    modele_excel,
    valider_import,
)
from src.data.prix import ajouter_prix, prix_courant
from src.data.provinces import ErreurRattachement
from src.data.saisie import ConfirmationRequise, ErreurSaisie, corriger_valeur
from src.data.versions import ErreurVersion, Versions
from src.scenarios.config import charger_controles
from tests.aides import copier_config
from tests.test_preparation import DEPOT, TAOUNATE, VALEUR_TAOUNATE, _referentiel, _statistiques

CONTROLES = charger_controles(DEPOT)
AUTEUR = "test automatique"
# Saisie simulée pour le test : correction d'une production par l'utilisateur.
SAISIE_SIMULEE_TAOUNATE = 371000.0
CLE_TAOUNATE = {
    "code_province": TAOUNATE,
    "code_culture": "olivier",
    "campagne": "2017-2018",
    "variable": "production_t",
}


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    chemins.preparees.mkdir(parents=True)
    _statistiques().resultat.production.to_parquet(
        chemins.preparees / "production.parquet", index=False
    )
    Versions(chemins).initialiser(AUTEUR, "données livrées")
    return chemins


def _classeur(versions: Versions, table: str) -> pd.DataFrame:
    contenu = modele_excel(versions, table, CONTROLES)
    return pd.read_excel(io.BytesIO(contenu), sheet_name=FEUILLE_DONNEES, dtype=object)


def _deposer(donnees: pd.DataFrame) -> bytes:
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as classeur:
        donnees.to_excel(classeur, sheet_name=FEUILLE_DONNEES, index=False)
    return tampon.getvalue()


def _ligne(donnees: pd.DataFrame, cle: dict[str, str]) -> pd.Index:
    masque = pd.Series(True, index=donnees.index)
    for colonne, valeur in cle.items():
        masque &= donnees[colonne].astype(str) == valeur
    return donnees.index[masque]


def _analyser(versions: Versions, table: str, donnees: pd.DataFrame):
    return analyser_import(_deposer(donnees), table, versions, CONTROLES, _referentiel())


# --- Versions (RG-17, UC-DAT-08) ----------------------------------------------------------


def test_version_initiale_copie_les_fichiers_de_base(chemins: Chemins) -> None:
    versions = Versions(chemins)
    (initiale,) = versions.journal()
    assert initiale.id_version == "v0001"
    assert "production" in initiale.tables_modifiees
    base = chemins.donnees / versions.definition("residus").fichier
    assert versions.fichier("residus").read_bytes() == base.read_bytes()
    assert Versions(chemins).initialiser(AUTEUR, "deuxième fois") is None


def test_signature_obligatoire(chemins: Chemins) -> None:
    versions = Versions(chemins)
    with pytest.raises(ErreurVersion, match="auteur"):
        versions.enregistrer({"residus": versions.lire("residus")}, " ", "commentaire")
    with pytest.raises(ErreurVersion, match="commentaire"):
        versions.enregistrer({"residus": versions.lire("residus")}, AUTEUR, "")


def test_aucune_version_sans_modification(chemins: Chemins) -> None:
    versions = Versions(chemins)
    assert versions.enregistrer({"production": versions.lire("production")}, AUTEUR, "rien") is None
    assert len(versions.journal()) == 1


def test_table_inconnue(chemins: Chemins) -> None:
    with pytest.raises(ErreurVersion, match="table « inexistante » inconnue"):
        Versions(chemins).lire("inexistante")


# --- Import Excel (UC-DAT-06) -------------------------------------------------------------


def test_modele_pre_rempli_et_feuilles_d_aide(chemins: Chemins) -> None:
    versions = Versions(chemins)
    contenu = modele_excel(versions, "residus", CONTROLES)
    feuilles = pd.read_excel(io.BytesIO(contenu), sheet_name=None, dtype=object)
    assert set(feuilles) == {FEUILLE_DONNEES, FEUILLE_MODE, FEUILLE_UNITES}
    assert len(feuilles[FEUILLE_DONNEES]) == len(versions.lire("residus"))
    assert "humidite" in set(feuilles[FEUILLE_UNITES]["grandeur"])


def test_modele_redepose_sans_changement(chemins: Chemins) -> None:
    versions = Versions(chemins)
    for table in ("production", "residus", "concurrence"):
        analyse = _analyser(versions, table, _classeur(versions, table))
        assert (analyse.ajoutees, analyse.modifiees, analyse.rejetees) == ([], [], {}), table


def test_aller_retour_modification_version_restauration(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees = _classeur(versions, "production")
    position = _ligne(donnees, CLE_TAOUNATE)
    donnees.loc[position, "valeur"] = SAISIE_SIMULEE_TAOUNATE
    analyse = _analyser(versions, "production", donnees)
    assert len(analyse.modifiees) == 1 and not analyse.ajoutees and not analyse.rejetees
    version = valider_import(analyse, versions, set(), AUTEUR, "saisie simulée pour le test")
    assert version is not None and version.nb_lignes_modifiees == 1
    production = versions.lire("production")
    ligne = production.loc[_ligne(production, CLE_TAOUNATE)].iloc[0]
    assert ligne["valeur"] == SAISIE_SIMULEE_TAOUNATE
    assert ligne["version"] == version.id_version
    difference = versions.comparer("production", "v0001", version.id_version)
    assert len(difference.modifiees) == 1
    assert difference.avant.iloc[0]["valeur"] == VALEUR_TAOUNATE
    copie_modifiee = versions.fichier("production").read_bytes()
    restauration = versions.restaurer("v0001", AUTEUR, "retour aux données livrées")
    assert restauration is not None and restauration.restauration_de == "v0001"
    assert versions.fichier("production").read_bytes() == (
        versions.fichier("production", "v0001").read_bytes()
    )
    # Rien n'est écrasé : la version modifiée reste consultable.
    assert versions.fichier("production", version.id_version).read_bytes() == copie_modifiee
    assert [v.id_version for v in versions.journal()] == ["v0001", "v0002", "v0003"]


def test_ligne_sans_source_rejetee(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees = _classeur(versions, "production")
    position = _ligne(donnees, CLE_TAOUNATE)
    donnees.loc[position, "valeur"] = SAISIE_SIMULEE_TAOUNATE
    donnees.loc[position, "source_id"] = None
    analyse = _analyser(versions, "production", donnees)
    (motif,) = analyse.rejetees.values()
    assert "source obligatoire (RG-18)" in motif
    assert valider_import(analyse, versions, set(), AUTEUR, "rien") is None


def _humidite_r05(versions: Versions, valeur: str) -> tuple[pd.DataFrame, int]:
    donnees = _classeur(versions, "residus")
    position = _ligne(donnees, {"code_residu": "R05", "parametre": "humidite"})[0]
    donnees.loc[position, "valeur"] = valeur
    donnees.loc[position, ["min", "mode", "max", "loi"]] = None
    donnees.loc[position, "source_id"] = "mesure interne"
    donnees.loc[position, "annee"] = "2026"
    return donnees, position


def plage_simulee(chemins: Chemins, table: str, colonne: str, bas: float, haut: float) -> None:
    """Ajoute à la copie de controles.yaml une plage plausible simulée pour le test."""
    chemin = chemins.config / "controles.yaml"
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    donnees["fourchettes"][table][colonne]["plausible"] = {
        "min": bas,
        "max": haut,
        "motif": "plage simulée pour le test",
    }
    chemin.write_text(yaml.safe_dump(donnees, allow_unicode=True), encoding="utf-8")


def test_humidite_hors_domaine_physique_rejetee(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees, _ = _humidite_r05(versions, "150")  # saisie simulée pour le test : humidité > 100 %
    analyse = _analyser(versions, "residus", donnees)
    assert not analyse.a_confirmer
    (motif,) = analyse.rejetees.values()
    assert "hors du domaine physique" in motif
    assert valider_import(analyse, versions, set(analyse.rejetees), AUTEUR, "rejetée") is None


def test_valeur_peu_plausible_a_confirmer(chemins: Chemins) -> None:
    plage_simulee(chemins, "residus", "humidite", 20, 80)
    controles = charger_controles(chemins)
    versions = Versions(chemins)
    donnees, _ = _humidite_r05(versions, "90")  # saisie simulée : dans le domaine, hors plage
    analyse = analyser_import(_deposer(donnees), "residus", versions, controles, _referentiel())
    (ligne,) = analyse.a_confirmer
    assert "fourchette plausible" in analyse.a_confirmer[ligne]
    assert valider_import(analyse, versions, set(), AUTEUR, "non confirmée") is None
    version = valider_import(analyse, versions, {ligne}, AUTEUR, "confirmée par l'utilisateur")
    assert version is not None


def test_production_dix_fois_superieure_a_confirmer(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees = _classeur(versions, "production")
    cle = {**CLE_TAOUNATE, "campagne": "2018-2019"}
    position = _ligne(donnees, cle)
    donnees.loc[position, "valeur"] = VALEUR_TAOUNATE * 11  # saisie simulée pour le test
    analyse = _analyser(versions, "production", donnees)
    (ligne,) = analyse.a_confirmer
    assert "fois la campagne précédente" in analyse.a_confirmer[ligne]
    assert valider_import(analyse, versions, set(), AUTEUR, "non confirmée") is None


def test_ligne_ajoutee(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees = _classeur(versions, "concurrence")
    nouvelle = donnees[donnees["code_province"] == "NATIONAL"].iloc[[0]].copy()
    nouvelle["code_province"] = "Taounate"  # nom de province, rattaché à son code (RG-02)
    analyse = _analyser(versions, "concurrence", pd.concat([donnees, nouvelle]))
    assert len(analyse.ajoutees) == 1
    version = valider_import(analyse, versions, set(), AUTEUR, "ligne provinciale")
    assert version is not None and version.nb_lignes_ajoutees == 1
    assert TAOUNATE in set(versions.lire("concurrence")["code_province"])


def test_province_inconnue_bloque_l_import(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees = _classeur(versions, "production")
    position = _ligne(donnees, CLE_TAOUNATE)
    donnees.loc[position, "code_province"] = "Taounat"
    with pytest.raises(ErreurRattachement, match="Taounat"):
        _analyser(versions, "production", donnees)


def test_classeur_sans_feuille_donnees(chemins: Chemins) -> None:
    tampon = io.BytesIO()
    pd.DataFrame({"a": [1]}).to_excel(tampon, sheet_name="autre", index=False)
    with pytest.raises(ErreurImport, match="feuille « données » introuvable"):
        analyser_import(tampon.getvalue(), "residus", Versions(chemins), CONTROLES, _referentiel())


def test_colonne_absente(chemins: Chemins) -> None:
    versions = Versions(chemins)
    donnees = _classeur(versions, "residus").drop(columns=["source_id"])
    with pytest.raises(ErreurImport, match="colonnes absentes"):
        _analyser(versions, "residus", donnees)


# --- Saisie directe (UC-DAT-07) -----------------------------------------------------------


def test_saisie_refusee_sans_date_ni_source(chemins: Chemins) -> None:
    versions = Versions(chemins)
    arguments = dict(table="production", cle=CLE_TAOUNATE, valeur="371000", auteur=AUTEUR)
    with pytest.raises(ErreurSaisie, match="date obligatoire"):
        corriger_valeur(
            versions,
            CONTROLES,
            source="mesure interne",
            date_valeur="",
            commentaire="c",
            **arguments,
        )
    with pytest.raises(ErreurSaisie, match="source obligatoire"):
        corriger_valeur(
            versions, CONTROLES, source="", date_valeur="2026-11-22", commentaire="c", **arguments
        )
    with pytest.raises(ErreurSaisie, match="illisible"):
        corriger_valeur(
            versions, CONTROLES, source="x", date_valeur="22/11/2026", commentaire="c", **arguments
        )


def test_saisie_cree_une_version(chemins: Chemins) -> None:
    versions = Versions(chemins)
    version = corriger_valeur(
        versions,
        CONTROLES,
        table="production",
        cle=CLE_TAOUNATE,
        valeur=str(SAISIE_SIMULEE_TAOUNATE),
        source="mesure interne",
        date_valeur="2026-11-22",
        auteur=AUTEUR,
        commentaire="saisie simulée pour le test",
    )
    assert version is not None
    ligne = (
        versions.lire("production").set_index(list(CLE_TAOUNATE)).loc[tuple(CLE_TAOUNATE.values())]
    )
    assert ligne["valeur"] == SAISIE_SIMULEE_TAOUNATE
    assert ligne["source_id"] == "mesure interne"
    assert ligne["annee"] == 2026


def test_saisie_hors_domaine_physique_refusee(chemins: Chemins) -> None:
    arguments = dict(
        table="residus",
        cle={"code_residu": "R05", "parametre": "f_col", "precision": ""},
        valeur="1,5",  # saisie simulée pour le test : fraction > 1
        source="mesure interne",
        date_valeur="2026-11-22",
        auteur=AUTEUR,
        commentaire="c",
    )
    for confirmer in (False, True):
        with pytest.raises(ErreurSaisie, match="domaine physique") as erreur:
            corriger_valeur(Versions(chemins), CONTROLES, confirmer=confirmer, **arguments)
        assert not isinstance(erreur.value, ConfirmationRequise)


def test_saisie_peu_plausible_a_confirmer(chemins: Chemins) -> None:
    plage_simulee(chemins, "residus", "f_col", 0.2, 0.8)
    controles = charger_controles(chemins)
    arguments = dict(
        table="residus",
        cle={"code_residu": "R05", "parametre": "f_col", "precision": ""},
        valeur="0,95",  # saisie simulée pour le test
        source="mesure interne",
        date_valeur="2026-11-22",
        auteur=AUTEUR,
        commentaire="c",
    )
    with pytest.raises(ConfirmationRequise, match="RG-19"):
        corriger_valeur(Versions(chemins), controles, **arguments)
    assert corriger_valeur(Versions(chemins), controles, confirmer=True, **arguments) is not None


# --- Prix observés (UC-DAT-07) ------------------------------------------------------------


def test_deux_prix_successifs_le_plus_recent_retenu(chemins: Chemins) -> None:
    versions = Versions(chemins)
    # Saisies simulées pour le test : deux prix de grignons relevés par l'équipe.
    for jour, prix in (("2026-10-01", "650"), ("2026-11-15", "670")):
        ajouter_prix(
            versions,
            CONTROLES,
            _referentiel(),
            date_prix=jour,
            produit="grignons",
            code_province="NATIONAL",
            prix=prix,
            unite="DH/t",
            source="saisie simulée pour le test",
            auteur=AUTEUR,
        )
    historique = versions.lire("prix_observes")
    assert len(historique) == 2
    courant = prix_courant(historique, "grignons", "NATIONAL")
    assert courant is not None and courant["prix"] == "670"
    assert prix_courant(historique, "paille", "NATIONAL") is None


def test_prix_refuse_sans_source_ou_negatif(chemins: Chemins) -> None:
    arguments = dict(
        date_prix="2026-11-15",
        produit="gazole",
        code_province="NATIONAL",
        unite="DH/L",
        auteur=AUTEUR,
    )
    versions = Versions(chemins)
    with pytest.raises(ErreurSaisie, match="source obligatoire"):
        ajouter_prix(versions, CONTROLES, _referentiel(), prix="12", source="", **arguments)
    with pytest.raises(ErreurSaisie, match="domaine physique") as erreur:
        ajouter_prix(
            versions, CONTROLES, _referentiel(), prix="-1", source="x", confirmer=True, **arguments
        )
    assert not isinstance(erreur.value, ConfirmationRequise)
