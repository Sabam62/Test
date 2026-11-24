"""Tables de référence de data/input/ (§7.1, §13, §14.2) : provenance, lois, unités, liens."""

import math
import shutil
import statistics
from pathlib import Path

import pandas as pd
import pytest

from src.chemins import Chemins, chemins_par_defaut
from src.data.provenance import Loi, Statut, ValeurACompleter
from src.data.sources import charger_sources
from src.data.tables_reference import (
    ErreurTable,
    charger_catalogue,
    charger_tables_reference,
    liste,
)
from src.scenarios.config import charger_parametres
from tests.aides import copier_config

DEPOT = chemins_par_defaut()
CULTURES_CROPGRIDS = DEPOT.racine / "tests/fixtures/SRC-04/cultures_cropgrids.csv"


@pytest.fixture(scope="module")
def tables():
    return charger_tables_reference(DEPOT)


@pytest.fixture
def copie(tmp_path: Path) -> Chemins:
    """Copie de config/ et de data/input/, modifiable par le test."""
    copier_config(DEPOT.config, tmp_path / "config")
    shutil.copytree(DEPOT.saisies, tmp_path / "data" / "input")
    return Chemins(tmp_path)


def _remplacer(chemin: Path, ancien: str, nouveau: str) -> None:
    texte = chemin.read_text(encoding="utf-8")
    assert ancien in texte, ancien
    chemin.write_text(texte.replace(ancien, nouveau, 1), encoding="utf-8")


def _toutes(tables) -> list:
    return [*tables.residus.lignes, *tables.concurrence.lignes, *tables.facteurs_emission.lignes]


# --- Contenu ------------------------------------------------------------------------------


def test_treize_residus(tables) -> None:
    codes = sorted({ligne.cle[0] for ligne in tables.residus.lignes})
    assert codes == [f"R{n:02d}" for n in range(1, 14)]
    assert tables.residus.valeur("R05", "nom").lire() == "Grignons d'olive"


def test_chaque_valeur_a_une_source_ou_est_a_completer(tables) -> None:
    connues = set(charger_sources(DEPOT).sources)
    for ligne in _toutes(tables):
        v = ligne.valeur
        if v.est_a_completer:
            assert v.ou_trouver, v.nom
            with pytest.raises(ValeurACompleter):
                v.lire()
        else:
            assert v.provenance is not None, v.nom
            assert v.provenance.source_id in connues, v.nom
            assert set(v.provenance.autres_sources) <= connues, v.nom


def test_bornes_et_lois(tables) -> None:
    for ligne in _toutes(tables):
        v = ligne.valeur
        if v.loi is None:
            assert v.min is None and v.max is None and v.mode is None, v.nom
            continue
        assert v.min <= v.lire_nombre() <= v.max, v.nom
        if v.loi is Loi.UNIFORME:
            assert math.isclose(v.lire_nombre(), statistics.fmean((v.min, v.max))), v.nom
            assert v.provenance.statut is Statut.HYPOTHESE, v.nom
            assert "milieu de fourchette" in (v.provenance.note or ""), v.nom
        else:
            assert v.mode is not None and v.provenance.source_id, v.nom
            assert math.isclose(v.lire_nombre(), v.mode), v.nom


def test_unites_autorisees(tables) -> None:
    catalogue = charger_catalogue(DEPOT)
    for table, cat in (
        (tables.residus, catalogue.residus),
        (tables.concurrence, catalogue.concurrence),
        (tables.facteurs_emission, catalogue.facteurs_emission),
    ):
        for ligne in table.lignes:
            assert ligne.valeur.unite in cat.parametres[ligne.parametre].unites, ligne.valeur.nom


def test_valeurs_du_cahier(tables) -> None:
    r = tables.residus
    assert r.valeur("R01", "carbone").lire() == 48.3
    assert r.valeur("R05", "rpr", "trois phases").lire() == pytest.approx(0.50)
    assert r.valeur("R05", "humidite", "trois phases").lire() == 45
    riz = r.valeur("R11", "rpr")
    assert (riz.loi, riz.min, riz.mode, riz.max) == (Loi.TRIANGULAIRE, 0.17, 0.20, 0.24)
    assert r.valeur("R03", "rendement_pyrolyse").lire() == pytest.approx(0.345)
    assert r.valeur("R08", "rendement_pyrolyse").lire() == pytest.approx(0.395)
    assert set(r.precisions("R05", "rpr")) == {
        "traditionnel (presse)",
        "trois phases",
        "deux phases",
    }


def test_cellules_a_completer_du_cahier(tables) -> None:
    r = tables.residus
    # Humidité de R01, R02 et R04 : page source inaccessible lors de la vérification SRC-08.
    for code in ("R01", "R02", "R04"):
        assert r.valeur(code, "humidite").est_a_completer  # « À compléter (Phyllis) »
    assert r.valeur("R09", "rpr").est_a_completer  # « part des coques : à compléter »
    for code in [f"R{n:02d}" for n in range(1, 14)]:
        assert r.valeur(code, "eligible_ebc").est_a_completer
        assert r.valeur(code, "k_col").est_a_completer
    # f_col et f_eco intégrés pour les bois de taille seulement (SRC-08, Dyjakon 2019).
    for code in [f"R{n:02d}" for n in range(5, 14)]:
        assert r.valeur(code, "f_col").est_a_completer


def test_facteur_electricite_identique_a_par24(tables) -> None:
    facteur = tables.facteurs_emission.valeur(
        ("electricite_reseau", "Électricité du réseau marocain"), "kg_co2e"
    )
    par24 = charger_parametres(DEPOT)["PAR-24"].valeur
    assert (facteur.min, facteur.mode, facteur.max) == (par24.min, par24.mode, par24.max)
    assert facteur.provenance.source_id == par24.provenance.source_id


def test_concurrence_ligne_nationale_par_residu(tables) -> None:
    codes = {ligne.cle for ligne in tables.concurrence.lignes}
    assert {("NATIONAL", f"R{n:02d}") for n in range(1, 14)} <= codes
    # Seule valeur provinciale livrée : part utilisée de R06 à Errachidia (SRC-08).
    assert codes - {("NATIONAL", f"R{n:02d}") for n in range(1, 14)} == {("8201", "R06")}
    grignons = tables.concurrence.valeur(("NATIONAL", "R05"), "prix_achat_dh_t")
    assert (grignons.min, grignons.max, grignons.lire()) == (650, 670, 660)
    assert tables.concurrence.valeur(("NATIONAL", "R13"), "prix_achat_dh_t").est_a_completer


def test_cultures_et_codes_cropgrids(tables) -> None:
    cropgrids = set(pd.read_csv(CULTURES_CROPGRIDS, sep=";")["code_cropgrids"])
    codes = set(tables.cultures["code_cropgrids"]) - {""}
    assert codes <= cropgrids
    cultures = {
        culture
        for ligne in tables.residus.lignes
        if ligne.parametre == "codes_culture"
        for culture in liste(ligne.valeur)
    }
    assert "barley" in set(tables.cultures["code_cropgrids"])
    assert cultures <= set(tables.cultures["code_culture"])


def test_calendrier_vide_faute_de_source(tables) -> None:
    assert tables.calendrier.empty
    assert list(tables.calendrier.columns)[1] == "m01"


# --- Refus (RG-14, RG-18, RG-19) ----------------------------------------------------------


def test_valeur_sans_source_refusee(copie: Chemins) -> None:
    _remplacer(
        copie.saisies / "residus.csv", "48.3;;;;;% MS;SRC-16-SUSTAINABILITY-2022", "48.3;;;;;% MS;"
    )
    with pytest.raises(ErreurTable, match="RG-18"):
        charger_tables_reference(copie)


def test_unite_non_autorisee_refusee(copie: Chemins) -> None:
    _remplacer(copie.saisies / "residus.csv", "48.3;;;;;% MS;", "48.3;;;;;g/kg;")
    with pytest.raises(ErreurTable, match="unité « g/kg » non autorisée"):
        charger_tables_reference(copie)


def test_humidite_superieure_a_cent_refusee(copie: Chemins) -> None:
    _remplacer(
        copie.saisies / "residus.csv",
        "R05;humidite;trois phases;45;",
        "R05;humidite;trois phases;145;",
    )
    with pytest.raises(ErreurTable, match="RG-19") as erreur:
        charger_tables_reference(copie)
    assert "R05 · humidite" in str(erreur.value)


def test_uniforme_hors_milieu_refusee(copie: Chemins) -> None:
    _remplacer(copie.saisies / "residus.csv", "R13;rpr;;1.45;", "R13;rpr;;1.5;")
    with pytest.raises(ErreurTable, match="milieu"):
        charger_tables_reference(copie)


def test_parametre_inconnu_refuse(copie: Chemins) -> None:
    _remplacer(copie.saisies / "residus.csv", "R01;carbone;", "R01;carbon;")
    with pytest.raises(ErreurTable, match="paramètre inconnu"):
        charger_tables_reference(copie)


def test_residu_manquant_refuse(copie: Chemins) -> None:
    fichier = copie.saisies / "residus.csv"
    lignes = fichier.read_text(encoding="utf-8").splitlines()
    fichier.write_text(
        "\n".join(x for x in lignes if not x.startswith("R12;")) + "\n", encoding="utf-8"
    )
    with pytest.raises(ErreurTable, match="R12 absent"):
        charger_tables_reference(copie)


def test_culture_inconnue_refusee(copie: Chemins) -> None:
    _remplacer(
        copie.saisies / "residus.csv", "R11;codes_culture;;riz;", "R11;codes_culture;;paddy;"
    )
    with pytest.raises(ErreurTable, match="paddy"):
        charger_tables_reference(copie)


def test_calendrier_qui_ne_somme_pas_a_un(copie: Chemins) -> None:
    fichier = copie.saisies / "calendrier.csv"
    # Profil construit pour le test du contrôle seulement : 12 × 0,1 = 1,2 ≠ 1.
    parts = ";".join(["0.1"] * 12)
    fichier.write_text(
        fichier.read_text(encoding="utf-8") + f"R05;{parts};CDC;2026;Hypothèse;\n", encoding="utf-8"
    )
    with pytest.raises(ErreurTable, match="somment"):
        charger_tables_reference(copie)


# --- Décisions du 22/11/2026 (§8.1) -------------------------------------------------------


def test_listes_de_cultures(tables) -> None:
    r = tables.residus
    assert liste(r.valeur("R04", "codes_culture")) == ["amandier", "rosacees"]
    assert liste(r.valeur("R13", "codes_culture")) == ["ble", "riz", "avoine", "seigle", "orge"]
    assert set(r.precisions("R04", "rendement_surf")) == {"amandier", "rosacees"}


def test_orge_avec_le_coefficient_du_ble_en_hypothese(tables) -> None:
    general = tables.residus.valeur("R13", "rpr")
    orge = tables.residus.valeur("R13", "rpr", "orge")
    assert (orge.min, orge.max, orge.lire()) == (general.min, general.max, general.lire())
    assert orge.provenance.statut is Statut.HYPOTHESE


def test_palmes_en_nombre_de_pieds_avec_densite_le360(tables) -> None:
    r = tables.residus
    assert r.valeur("R06", "mode_calcul").lire() == "nombre de pieds"
    assert r.valeur("R06", "rendement_arbre").lire() == 21.2
    densite = r.valeur("R06", "densite_plantation", "secours")
    assert densite.lire() == pytest.approx(
        7_200_000 / 64_000
    )  # 7,2 millions de palmiers, 64 000 ha
    assert densite.provenance.statut is Statut.ESTIMEE
    assert densite.provenance.source_id == "SRC-16-LE360-2024"
    assert (
        charger_sources(DEPOT).sources["SRC-16-LE360-2024"].url.startswith("https://fr.le360.ma/")
    )
    assert r.precisions("R06", "rendement_surf") == []


def test_mode_sans_son_ratio_refuse(copie: Chemins) -> None:
    _remplacer(
        copie.saisies / "residus.csv",
        "R06;mode_calcul;;nombre de pieds;",
        "R06;mode_calcul;;surface;",
    )
    with pytest.raises(ErreurTable, match="exige rendement_surf"):
        charger_tables_reference(copie)


def test_precision_de_culture_hors_liste_refusee(copie: Chemins) -> None:
    _remplacer(
        copie.saisies / "residus.csv",
        "R13;codes_culture;;ble, riz, avoine, seigle, orge;",
        "R13;codes_culture;;ble, riz, avoine, seigle;",
    )
    with pytest.raises(ErreurTable, match="« orge » hors de codes_culture"):
        charger_tables_reference(copie)
