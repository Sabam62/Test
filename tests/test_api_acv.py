# ruff: noqa: F811 — les fixtures chemins et client viennent de test_api_logistique.
"""Lot 4, tâche 2 : routes /api/acv sur une copie de l'extrait figé des données réelles.

Les facteurs d'émission et données d'activité « À compléter » sont des « saisies simulées pour
le test », passées par la route de saisie directe comme le ferait l'entreprise.
"""

import pytest
from fastapi.testclient import TestClient

from tests.test_api_logistique import AUTEUR, SIMULE, _saisir, chemins, client  # noqa: F401

MEKNES = "AGP-MEKNES"
TAOUNATE = "3531"


def _facteur(client: TestClient, activite: str, parametre: str, valeur: str) -> None:
    _saisir(
        client,
        "facteurs_emission",
        {"code_activite": activite, "parametre": parametre, "precision": ""},
        valeur,
    )


def _completer(client: TestClient) -> None:
    """Saisies simulées pour le test : tout ce que la chaîne R01 attend."""
    for activite, parametre, valeur in (
        ("gazole_amont", "kg_co2e", "0.6"),
        ("pyrolyse", "kg_ch4_bio", "0.5"),
        ("pyrolyse", "kg_n2o", "0.01"),
        ("pyrolyse", "consommation_electricite", "150"),
        ("collecte", "consommation_gazole", "2"),
        ("broyage", "consommation_electricite", "30"),
        ("epandage", "consommation_gazole", "3"),
        ("transport_biochar", "distance_km", "40"),
    ):
        _facteur(client, activite, parametre, valeur)
    for parametre, valeur in (
        ("humidite", "30"),
        ("densite_apparente", "150"),
        ("scenario_reference", "brûlage à l'air libre"),
    ):
        _saisir(
            client,
            "residus",
            {"code_residu": "R01", "parametre": parametre, "precision": ""},
            valeur,
        )
    corps = {"valeur": 90, "source": SIMULE, "auteur": AUTEUR}
    assert client.put("/api/parametres/PAR-32", json=corps).status_code == 200
    reponse = client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": {"PAR-21": 600}})
    assert reponse.status_code == 200, reponse.json()


def test_etat_rappelle_unite_fonctionnelle_et_standard(client: TestClient) -> None:
    corps = client.get("/api/acv/etat").json()
    assert corps["unite_fonctionnelle"] == "1 t de biochar produite et épandue"
    assert corps["standard"] == "neutre"
    assert corps["projet"] == "atlantic_biochar"
    assert "PAR-21" in corps["permanence_motif"]  # RG-15 : température non renseignée
    assert corps["scores_unitaires"]["electricite_reseau"] == pytest.approx(0.69)


def test_bilans_bloques_sur_les_donnees_livrees(client: TestClient) -> None:
    corps = client.get(f"/api/acv/sites/{MEKNES}").json()
    assert corps["couples"] > 0 and corps["couples_calcules"] == 0
    motifs = " ".join(m["motif"] for m in corps["a_saisir"])
    assert "kg_co2e à compléter" in motifs  # amont du gazole


def test_chaine_calculee_et_contributions_brightway(client: TestClient) -> None:
    _completer(client)
    corps = client.get(f"/api/acv/sites/{MEKNES}").json()
    r01 = next(r for r in corps["par_residu"] if r["code_residu"] == "R01")
    assert r01["couples_calcules"] > 0 and r01["scenario"] == "brûlage à l'air libre"
    assert corps["classe_temperature"] == "haute" and corps["permanence"] == pytest.approx(0.89)
    chaine = client.get(
        "/api/acv/chaine", params={"province": TAOUNATE, "residu": "R01", "site": MEKNES}
    ).json()
    assert chaine["bloque"] is False
    bilan, brightway = chaine["bilan"], chaine["brightway"]
    for etape, terme in (
        ("collecte", "E_col"),
        ("pretraitement", "E_pre"),
        ("transport", "E_tr"),
        ("pyrolyse", "E_pyr"),
        ("epandage", "E_ep"),
        ("reference", "E_ref"),
    ):
        assert brightway[etape] == pytest.approx(bilan[terme], rel=1e-6), etape
    assert bilan["stock"] == pytest.approx(0.709 * 0.89 * 44 / 12)


def test_reference_sans_substitution(client: TestClient) -> None:
    """« Sans substitution » (décision du 23/11/2026) : E_ref = 0, dans la formule et Brightway."""
    _completer(client)
    _saisir(
        client,
        "residus",
        {"code_residu": "R01", "parametre": "scenario_reference", "precision": ""},
        "sans substitution",
    )
    chaine = client.get(
        "/api/acv/chaine", params={"province": TAOUNATE, "residu": "R01", "site": MEKNES}
    ).json()
    assert chaine["bloque"] is False
    assert chaine["bilan"]["E_ref"] == 0
    assert chaine["brightway"]["reference"] == pytest.approx(0)


def test_chaine_inconnue(client: TestClient) -> None:
    reponse = client.get(
        "/api/acv/chaine", params={"province": "0000", "residu": "R01", "site": MEKNES}
    )
    assert reponse.status_code == 404


def test_saisie_d_un_choix_controlee(client: TestClient) -> None:
    """Le scénario de référence se saisit dans Données ; un choix inconnu est refusé."""
    corps = {
        "auteur": AUTEUR,
        "commentaire": SIMULE,
        "cle": {"code_residu": "R02", "parametre": "scenario_reference", "precision": ""},
        "valeur": "enfouissement",
        "source": SIMULE,
        "date": "2026-11-23",
    }
    refus = client.put("/api/donnees/tables/residus/valeur", json=corps)
    assert refus.status_code == 400 and "choisissez parmi" in refus.json()["erreur"]
    corps["valeur"] = "décomposition au champ"
    assert client.put("/api/donnees/tables/residus/valeur", json=corps).status_code == 200
