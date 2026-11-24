# ruff: noqa: F811 — les fixtures chemins et client viennent de test_api_logistique.
"""Lot 5, tâche 4 : routes /api/decision et /api/melange sur l'extrait figé des données réelles.

Les valeurs « À compléter » des données livrées (camion, densité, coûts, part utilisée,
paramètres de l'entreprise, données de l'ACV) sont des « saisies simulées pour le test »,
passées par les routes de l'outil.
"""

import time

import pytest
from fastapi.testclient import TestClient

from tests.test_api_acv import _completer as completer_acv
from tests.test_api_logistique import AUTEUR, _completer, chemins, client  # noqa: F401

MEKNES = "AGP-MEKNES"


def _tout_completer(client: TestClient, plafond: float) -> None:
    _completer(client, capacite=5000, plafond=plafond)
    completer_acv(client)


def test_classement_bloque_sans_parametres_obligatoires(client: TestClient) -> None:
    corps = client.get("/api/decision/classement").json()
    assert corps["bloque"] is True
    assert set(corps["a_renseigner"]) == {"PAR-01", "PAR-21", "PAR-34", "PAR-37"}


def test_criteres_catalogue_et_valeurs(client: TestClient) -> None:
    corps = client.get("/api/decision/criteres").json()
    assert len(corps["criteres"]) == 19
    assert {"A1", "C1", "D1", "G1"} <= set(corps["actifs"])
    assert "C6" not in corps["actifs"]  # PAR-55 et PAR-56 non saisis
    assert corps["methode"] == "somme_ponderee"


def test_classement_en_moins_de_2_s_et_prix_plafond(client: TestClient) -> None:
    _tout_completer(client, plafond=100000)
    corps = client.get("/api/decision/classement").json()
    assert corps["bloque"] is False, corps
    assert {"A1", "C1", "C2", "D1"} <= set(corps["criteres"])
    partiel = corps["partiel"]
    assert partiel["utilises"] == len(corps["criteres"])
    assert partiel["actifs"] == partiel["utilises"] + len(corps["retires"])
    assert partiel["partiel"] is bool(corps["retires"])
    assert set(corps["libelles_retires"]) == set(corps["retires"])
    # Carte des sites colorée par rang (§11.2.3) : classes ordonnées par rang, positions.
    sites = sorted(corps["classement"], key=lambda s: s["rang"])
    assert [s["classe"] for s in sites] == sorted(s["classe"] for s in sites)
    assert sites[0]["classe"] == 0 and all(-20 < s["lon"] < 0 for s in sites)
    legende = corps["legende_rangs"]
    assert legende[0]["rang_min"] == 1 and legende[-1]["rang_max"] == len(sites)
    meknes = next(s for s in corps["classement"] if s["id_site"] == MEKNES)
    assert meknes["rang"] >= 1
    # Changement de poids : seul le classement est recalculé (UC-DEC-04, moins de 2 s).
    poids = dict.fromkeys(corps["criteres"], 1.0) | {"C1": 5.0}
    assert client.put("/api/decision/reglages", json={"poids": poids}).status_code == 200
    debut = time.perf_counter()
    apres = client.get("/api/decision/classement").json()
    assert time.perf_counter() - debut < 2
    assert apres["poids"]["C1"] == pytest.approx(5 / (len(poids) + 4))
    # Prix plafond plus bas : le classement est mis à jour, avec la variation de rang (RG-16).
    a1_avant = {s: v["A1"] for s, v in apres["valeurs"].items()}
    bas = 400.0  # DH/t MS, saisie simulée pour le test
    reponse = client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": {"PAR-34": bas}})
    assert reponse.status_code == 200
    nouveau = client.get("/api/decision/classement").json()
    if nouveau["bloque"] is False:
        a1_apres = {s: v["A1"] for s, v in nouveau.get("valeurs", {}).items() if "A1" in v}
        assert a1_apres != a1_avant or nouveau["exclus"]
        assert any(s["variation"] is not None for s in nouveau["classement"])
    else:
        pytest.fail(f"classement bloqué après le changement de prix plafond : {nouveau}")


def test_robustesse_et_ahp(client: TestClient) -> None:
    _tout_completer(client, plafond=100000)
    corps = client.get("/api/decision/robustesse").json()
    assert corps["bloque"] is False
    assert sum(s["proba_premier"] for s in corps["sites"]) == pytest.approx(1)
    ahp = client.post(
        "/api/decision/ahp",
        json={
            "axes": {
                "codes": ["A", "C", "D"],
                "matrice": [[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]],
            },
            "criteres": {"C": {"codes": ["C1", "C2"], "matrice": [[1, 2], [0.5, 1]]}},
        },
    ).json()
    assert ahp["matrices"]["axes"]["cr"] == pytest.approx(0.033, abs=1e-3)
    assert ahp["poids"]["C1"] == pytest.approx(ahp["matrices"]["axes"]["poids"]["C"] * 2 / 3)
    assert client.put("/api/decision/reglages", json={"actifs": ["X9"]}).status_code == 400


def test_melange_de_meknes(client: TestClient) -> None:
    _tout_completer(client, plafond=100000)
    corps = client.get(f"/api/melange/{MEKNES}").json()
    assert corps["bloque"] is False
    if corps["faisable"]:
        assert sum(m["tonnage"] for m in corps["melange"]) == pytest.approx(5000)
    else:
        assert corps["message"]
    assert len(corps["non_appliquees"]) == 3  # PAR-51, 52, 53 non saisis


def test_scenario_garde_et_restaure_les_reglages_de_decision(client: TestClient) -> None:
    reglages = {
        "actifs": ["A1", "C1", "C2"],
        "poids": {"C1": 3.0},
        "seuils": {"C2": {"maximum": 80}},
    }
    assert client.put("/api/decision/reglages", json=reglages).status_code == 200
    corps = {"nom": "essai décision", "auteur": AUTEUR}
    scenario = client.post("/api/scenarios", json=corps).json()
    assert scenario["criteres_actifs"] == ["A1", "C1", "C2"]
    assert scenario["seuils"] == {"C2.maximum": 80}
    assert client.delete("/api/decision/reglages").status_code == 200
    reponse = client.post("/api/scenarios/essai décision/appliquer", json={"auteur": AUTEUR})
    assert reponse.status_code == 200, reponse.json()
    criteres = client.get("/api/decision/criteres").json()
    assert criteres["actifs"] == ["A1", "C1", "C2"] and criteres["poids"] == {"C1": 3.0}
    assert criteres["seuils"] == {"C2": {"minimum": None, "maximum": 80.0}}


def test_classement_des_gisements(client: TestClient) -> None:
    _tout_completer(client, plafond=100000)
    corps = client.get("/api/decision/gisements", params={"site": MEKNES}).json()
    assert corps["bloque"] is False and corps["classable"] is True, corps
    assert {"A1", "C1", "D1"} <= set(corps["criteres"])
    premiers = corps["classement"]
    assert premiers[0]["rang"] == 1 and premiers[0]["code_residu"] == "R01"
    assert corps["exclus"]["total"] + corps["classes"] == corps["couples"]
    assert corps["partiel"]["actifs"] == corps["partiel"]["utilises"] + len(corps["retires"])


def test_gisements_non_classables_sur_les_donnees_livrees(client: TestClient) -> None:
    corps = client.put(
        "/api/entreprise",
        json={
            "auteur": AUTEUR,
            "valeurs": {"PAR-01": 5000, "PAR-21": 600, "PAR-34": 900, "PAR-37": 12},
        },
    )
    assert corps.status_code == 200
    reponse = client.get("/api/decision/gisements").json()
    assert reponse["classable"] is False and reponse["message"]
    assert "A1" in reponse["retires"]
