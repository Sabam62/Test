"""Lot 2, tâche 4 : routes /api/potentiel sur une copie de l'extrait figé des données réelles.

f_col, f_eco et u sont « À compléter » dans les données livrées ; les valeurs saisies ici sont
des « saisies simulées pour le test », passées par la route de saisie directe (UC-DAT-07).
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.app import creer_app
from api.dependances import obtenir_chemins, obtenir_referentiel
from src.chemins import Chemins
from src.data.versions import Versions
from tests.aides import copier_config
from tests.test_preparation import DEPOT, FIXTURES, TAOUNATE, _referentiel, _statistiques

AUTEUR = "test automatique"
SIGNATURE = {"auteur": AUTEUR, "commentaire": "saisie simulée pour le test"}


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    chemins.preparees.mkdir(parents=True)
    _statistiques().resultat.production.to_parquet(
        chemins.preparees / "production.parquet", index=False
    )
    pd.read_csv(
        FIXTURES / "production" / "surface_agricole.csv", sep=";", dtype={"code_province": str}
    ).to_parquet(chemins.preparees / "surface_agricole.parquet", index=False)
    Versions(chemins).initialiser(AUTEUR, "données livrées")
    return chemins


@pytest.fixture
def client(chemins: Chemins) -> TestClient:
    app = creer_app()
    app.dependency_overrides[obtenir_chemins] = lambda: chemins
    app.dependency_overrides[obtenir_referentiel] = _referentiel
    return TestClient(app, raise_server_exceptions=False)


def _province(carte: dict, code: str) -> dict:
    return next(p for p in carte["provinces"] if p["code_province"] == code)


def test_indicateurs_et_residus(client: TestClient) -> None:
    corps = client.get("/api/potentiel/indicateurs").json()
    codes = {i["code"] for i in corps["indicateurs"]}
    assert {"T", "M", "C", "B", "C_T", "B_T", "densite_M"} <= codes
    assert len(corps["residus"]) == 13
    assert corps["residus"][0] == {"code": "R01", "nom": "Taille d'olivier"}


def test_carte_des_75_provinces_avec_classes(client: TestClient) -> None:
    carte = client.get("/api/potentiel/carte", params={"residu": "R01", "indicateur": "T"}).json()
    assert len(carte["provinces"]) == 75
    assert carte["unite"] == "t MS/an"
    assert carte["provinces_avec_valeur"] > 0
    taounate = _province(carte, TAOUNATE)
    assert taounate["valeur"] > 0
    assert taounate["statut"] == "Hypothèse"
    assert "SRC-16-ZARAGOZA" in taounate["sources"]
    assert carte["bornes"] == sorted(carte["bornes"])
    classes = {p["classe"] for p in carte["provinces"] if p["valeur"] is not None}
    assert classes <= set(range(len(carte["bornes"])))


def test_m_bloque_explique_par_province(client: TestClient) -> None:
    carte = client.get("/api/potentiel/carte", params={"residu": "R01", "indicateur": "M"}).json()
    assert carte["provinces_avec_valeur"] == 0
    taounate = _province(carte, TAOUNATE)
    assert taounate["valeur"] is None and taounate["classe"] is None
    assert any("part_utilisee à compléter" in m for m in taounate["motifs"])


def test_somme_des_residus_et_indicateur_non_additif(client: TestClient) -> None:
    tous = client.get("/api/potentiel/carte", params={"residu": "tous", "indicateur": "T"}).json()
    r01 = client.get("/api/potentiel/carte", params={"residu": "R01", "indicateur": "T"}).json()
    assert _province(tous, TAOUNATE)["valeur"] >= _province(r01, TAOUNATE)["valeur"]
    refus = client.get("/api/potentiel/carte", params={"residu": "tous", "indicateur": "cv_M"})
    assert refus.status_code == 400 and "choisissez un résidu" in refus.json()["erreur"]


@pytest.mark.parametrize(
    ("parametres", "fragment"),
    [({"residu": "R99"}, "résidu « R99 » inconnu"), ({"indicateur": "X"}, "indicateur « X »")],
)
def test_filtres_inconnus(client: TestClient, parametres: dict, fragment: str) -> None:
    reponse = client.get("/api/potentiel/carte", params=parametres)
    assert reponse.status_code == 400 and fragment in reponse.json()["erreur"]


def test_tableau_province_par_residu(client: TestClient) -> None:
    tableau = client.get("/api/potentiel/tableau", params={"indicateur": "T"}).json()
    assert len(tableau["lignes"]) == 75
    taounate = next(ligne for ligne in tableau["lignes"] if ligne["code_province"] == TAOUNATE)
    assert taounate["cellules"]["R01"]["valeur"] > 0
    assert "humidite à compléter" in taounate["cellules"]["R10"]["motif"]


def test_synthese_nationale_et_bloquants(client: TestClient) -> None:
    synthese = client.get("/api/potentiel/synthese").json()
    totaux = {t["indicateur"]: t for t in synthese["totaux"]}
    assert totaux["T"]["total"] > 0 and "R01" in totaux["T"]["residus_calcules"]
    assert totaux["M"]["total"] is None
    assert any("PAR-62" in b["motif"] for b in synthese["bloquants"])
    exclus = client.get("/api/potentiel/exclus", params={"residu": "R05", "indicateur": "T"}).json()
    assert len(exclus) == 75


def test_recalcul_apres_une_saisie_sans_redemarrage(client: TestClient) -> None:
    """Le cache dépend de la version active : une saisie dans Données relance le calcul."""
    # f_col (0,96) et f_eco (0,375) de R01 sont livrés dans residus.csv.
    corps = {
        **SIGNATURE,
        "cle": {
            "code_province": "NATIONAL",
            "code_residu": "R01",
            "parametre": "part_utilisee",
            "precision": "",
        },
        "valeur": "0.25",  # saisie simulée pour le test
        "source": "saisie simulée pour le test",
        "date": "2026-11-22",
    }
    assert client.put("/api/donnees/tables/concurrence/valeur", json=corps).status_code == 200
    carte = client.get("/api/potentiel/carte", params={"residu": "R01", "indicateur": "M"}).json()
    assert carte["provinces_avec_valeur"] > 0
    t = _province(
        client.get("/api/potentiel/carte", params={"residu": "R01", "indicateur": "T"}).json(),
        TAOUNATE,
    )["valeur"]
    assert _province(carte, TAOUNATE)["valeur"] == pytest.approx(t * 0.96 * 0.375 * 0.75, rel=1e-3)
