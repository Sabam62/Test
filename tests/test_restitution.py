# ruff: noqa: F811 — les fixtures chemins et client viennent de test_api_logistique.
"""Lot 6 : exports CSV et Excel (UC-RES-02, ENF-05, ENF-14) et fiche site (UC-RES-01).

Les valeurs « À compléter » des données livrées sont des « saisies simulées pour le test ».
"""

import io

import pandas as pd
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from src.chemins import chemins_par_defaut
from src.restitution.annexes import table_parametres, table_sources
from src.restitution.exports import (
    Colonne,
    Export,
    Partiel,
    charger_config_restitution,
    classeur_excel,
    fichier_csv,
)
from tests.test_api_decision import _tout_completer
from tests.test_api_logistique import AUTEUR, chemins, client  # noqa: F401

DEPOT = chemins_par_defaut()
CONFIG = charger_config_restitution(DEPOT)
MEKNES = "AGP-MEKNES"


def _export(partiel: Partiel | None) -> Export:
    return Export(
        titre="Classement des sites",
        colonnes=[Colonne("nom", "Site"), Colonne("score", "Score", "0 à 1")],
        lignes=[{"nom": "Settat", "score": 0.8942}, {"nom": "Taounate", "score": 0.8567}],
        parametres=table_parametres(DEPOT),
        sources=table_sources(DEPOT),
        partiel=partiel,
    )


def test_classeur_avec_parametres_sources_et_bandeau() -> None:
    partiel = Partiel(4, 11, {"C1": "PAR-61 à compléter"}, {"C1": "Coût livré à l'usine"})
    classeur = load_workbook(io.BytesIO(classeur_excel(_export(partiel), CONFIG.excel)))
    assert classeur.sheetnames == ["Classement des sites", "paramètres", "sources"]
    lignes = [r[0] for r in classeur["Classement des sites"].iter_rows(values_only=True)]
    assert "Classement partiel : 4 critères sur 11" in lignes
    assert "C1 · Coût livré à l'usine : PAR-61 à compléter" in lignes
    assert "Score (0 à 1)" in [c.value for row in classeur.worksheets[0].iter_rows() for c in row]
    sources = pd.DataFrame(classeur["sources"].values)
    assert "SRC-19" in set(sources[0]) and "© Haut-Commissariat au Plan" in set(sources[4])
    parametres = pd.DataFrame(classeur["paramètres"].values)
    assert {"PAR-01", "PAR-34", "PAR-20:haute"} <= set(parametres[1])


def test_csv_francais_et_bandeau_en_commentaire() -> None:
    texte = fichier_csv(_export(Partiel(4, 11, {"C1": "PAR-61"}, {})), CONFIG.csv).decode("utf-8")
    assert texte.startswith("﻿# Classement partiel : 4 critères sur 11")
    assert "Site;Score (0 à 1)" in texte and "Settat;0,8942" in texte
    sans = fichier_csv(_export(None), CONFIG.csv).decode("utf-8")
    assert "#" not in sans


def test_export_d_un_tableau_affiche(client: TestClient) -> None:
    corps = {
        "titre": "Bilan net par résidu",
        "colonnes": [
            {"cle": "code", "libelle": "Résidu"},
            {"cle": "bn", "libelle": "Bilan", "unite": "t CO₂e/t biochar"},
        ],
        "lignes": [{"code": "R01", "bn": 2.49}],
    }
    reponse = client.post("/api/exports/xlsx", json=corps)
    assert reponse.status_code == 200
    assert reponse.headers["content-disposition"].endswith('bilan-net-par-residu.xlsx"')
    assert load_workbook(io.BytesIO(reponse.content)).sheetnames[1:] == ["paramètres", "sources"]


def test_export_du_classement_des_sites(client: TestClient) -> None:
    assert client.get("/api/exports/classement.xlsx").status_code == 409  # RG-15
    _tout_completer(client, plafond=100000)
    reponse = client.get("/api/exports/classement.xlsx")
    assert reponse.status_code == 200
    classeur = load_workbook(io.BytesIO(reponse.content))
    assert classeur.sheetnames == ["Classement des sites", "paramètres", "sources"]
    valeurs = [r for r in classeur.worksheets[0].iter_rows(values_only=True)]
    assert any(r[1] == "Agropolis de Meknès" for r in valeurs if len(r) > 1)
    csv = client.get("/api/exports/classement.csv")
    assert csv.status_code == 200 and "Agropolis de Meknès" in csv.content.decode("utf-8")


def test_fiche_site_complete(client: TestClient) -> None:
    _tout_completer(client, plafond=100000)
    fiche = client.get(f"/api/fiche/{MEKNES}").json()
    assert fiche["site"]["nom"] == "Agropolis de Meknès"
    assert fiche["classement"]["rang"] >= 1 and fiche["robustesse"] is not None
    assert fiche["bassin"]["bloque"] is False and fiche["bassin"]["tonnage_sous_plafond"] > 0
    assert fiche["melange"]["bloque"] is False
    assert fiche["bilan"]["unite_fonctionnelle"] == "1 t de biochar produite et épandue"
    codes = {c["code"] for c in fiche["criteres"]}
    assert {"A1", "C1", "D1"} <= codes
    assert client.get("/api/fiche/INCONNU").status_code == 404


def test_fiche_site_sans_parametres_obligatoires(client: TestClient) -> None:
    fiche = client.get(f"/api/fiche/{MEKNES}").json()
    assert set(fiche["a_renseigner"]) == {"PAR-01", "PAR-21", "PAR-34", "PAR-37"}
    assert fiche["bassin"]["bloque"] is True
