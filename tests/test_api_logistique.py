"""Lot 3, tâche 2 : routes /api/logistique sur une copie de l'extrait figé des données réelles.

Points de rattachement et chefs-lieux : extrait réel de Fès-Meknès (tests/fixtures/logistique/).
Les valeurs « À compléter » des données livrées (F, volume, densité, k_col, k_pre, prix, u)
et les paramètres de l'entreprise sont des « saisies simulées pour le test », passées par les
routes de l'outil, comme le ferait l'entreprise.
"""

import json
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import creer_app
from api.dependances import obtenir_chemins, obtenir_referentiel
from api.routes.logistique import obtenir_provinces
from src.chemins import Chemins
from src.data.versions import Versions
from src.logistique.config import charger_config_logistique
from src.logistique.distances import FICHIER_CALIBRATION, commande_osrm, osrm_disponible
from tests.aides import copier_config
from tests.test_preparation import DEPOT, FIXTURES, _referentiel, _statistiques

AUTEUR = "test automatique"
SIMULE = "saisie simulée pour le test"
SIGNATURE = {"auteur": AUTEUR, "commentaire": SIMULE}
LOGISTIQUE = FIXTURES / "logistique"
MEKNES = "AGP-MEKNES"


def _regions() -> gpd.GeoDataFrame:
    regions = gpd.read_file(FIXTURES / "production" / "hdx_regions.geojson")
    return regions.rename(columns={"adm1_pcode": "code_province", "adm1_name": "nom_fr"})


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    shutil.copy(DEPOT.donnees / "sources.yaml", chemins.donnees / "sources.yaml")
    chemins.preparees.mkdir(parents=True)
    _statistiques().resultat.production.to_parquet(
        chemins.preparees / "production.parquet", index=False
    )
    pd.read_csv(
        FIXTURES / "production" / "surface_agricole.csv", sep=";", dtype={"code_province": str}
    ).to_parquet(chemins.preparees / "surface_agricole.parquet", index=False)
    config = charger_config_logistique(chemins)
    for source, cible in (
        ("rattachements_fes_meknes.csv", config.rattachement.sortie),
        ("chefs_lieux_fes_meknes.csv", config.sites.sortie_chefs_lieux),
    ):
        table = pd.read_csv(LOGISTIQUE / source, sep=";", dtype={"code_province": str})
        table.to_parquet(chemins.preparees / cible, index=False)
    Versions(chemins).initialiser(AUTEUR, "données livrées")
    return chemins


def _sans_osrm(chemins: Chemins, calibration: bool = True) -> None:
    fichier = chemins.config / "logistique.yaml"
    contenu = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    contenu["osrm"]["url"] = "http://127.0.0.1:9"
    contenu["osrm"]["delai_secondes"] = contenu["osrm"]["delai_test_secondes"] = 1
    fichier.write_text(yaml.safe_dump(contenu, allow_unicode=True), encoding="utf-8")
    if calibration:
        cache = chemins.donnees / "cache" / contenu["dossier_cache"]
        cache.mkdir(parents=True, exist_ok=True)
        valeur = {"coefficient": 1.3, "paires": 72, "date": "2026-11-22"}  # saisie simulée
        (cache / FICHIER_CALIBRATION).write_text(json.dumps(valeur), encoding="utf-8")


@pytest.fixture
def client(chemins: Chemins) -> TestClient:
    if not osrm_disponible(charger_config_logistique(chemins)):
        _sans_osrm(chemins)
    app = creer_app()
    app.dependency_overrides[obtenir_chemins] = lambda: chemins
    app.dependency_overrides[obtenir_referentiel] = _referentiel
    app.dependency_overrides[obtenir_provinces] = _regions
    return TestClient(app, raise_server_exceptions=False)


def _saisir(client: TestClient, table: str, cle: dict[str, str], valeur: str) -> None:
    corps = {**SIGNATURE, "cle": cle, "valeur": valeur, "source": SIMULE, "date": "2026-11-22"}
    reponse = client.put(f"/api/donnees/tables/{table}/valeur", json=corps)
    assert reponse.status_code == 200, reponse.json()


def _completer(client: TestClient, capacite: float, plafond: float) -> None:
    """Saisies simulées pour le test : tout ce qui manque pour la courbe de R01 (olivier).

    L'extrait de production couvre l'olivier, le blé et le palmier ; R13 exige aussi riz,
    avoine, seigle et orge (RG-06). f_col et f_eco de R01 sont livrés (SRC-08).
    """
    for parametre, valeur in (
        ("humidite", "30"),
        ("densite_apparente", "150"),
        ("k_col", "80"),
        ("k_pre", "60"),
    ):
        _saisir(
            client,
            "residus",
            {"code_residu": "R01", "parametre": parametre, "precision": ""},
            valeur,
        )
    for parametre, valeur in (("part_utilisee", "0.2"), ("prix_achat_dh_t", "0")):
        _saisir(
            client,
            "concurrence",
            {
                "code_province": "NATIONAL",
                "code_residu": "R01",
                "parametre": parametre,
                "precision": "",
            },
            valeur,
        )
    for identifiant, valeur in (("PAR-61", 300), ("PAR-32", 90)):
        corps = {"valeur": valeur, "source": SIMULE, "auteur": AUTEUR}
        assert client.put(f"/api/parametres/{identifiant}", json=corps).status_code == 200
    valeurs = {"PAR-01": capacite, "PAR-34": plafond, "PAR-37": 12.0, "PAR-21": "moyenne"}
    reponse = client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": valeurs})
    assert reponse.status_code == 200, reponse.json()


def test_sites_candidats_et_agropoles_a_placer(client: TestClient) -> None:
    corps = client.get("/api/logistique/sites").json()
    types = {s["type"] for s in corps["sites"]}
    assert {"chef-lieu", "agropole"} <= types
    meknes = next(s for s in corps["sites"] if s["id_site"] == MEKNES)
    assert meknes["impose"] is True
    assert {a["id_site"] for a in corps["a_completer"]} == {
        "AGP-BERKANE",
        "AGP-TADLA",
        "AGP-SOUSS",
        "AGP-LOUKKOS",
    }
    assert corps["methode"] in {"osrm", "vol_oiseau"}


def test_courbe_bloquee_liste_les_valeurs_a_saisir(client: TestClient) -> None:
    corps = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    assert corps["bloque"] is True
    texte = "\n".join(corps["a_saisir"])
    for attendu in ("PAR-01", "PAR-34", "PAR-61", "PAR-32", "gisement mobilisable M"):
        assert attendu in texte


def test_courbe_de_meknes_apres_saisies(client: TestClient) -> None:
    _completer(client, capacite=1000, plafond=100000)
    corps = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    assert corps["bloque"] is False, corps.get("a_saisir")
    points = corps["points"]
    assert points and all(p["code_residu"] == "R01" for p in points)
    couts = [p["cout_livre"] for p in points]
    assert couts == sorted(couts)
    assert corps["atteignable"] is (corps["tonnage_sous_plafond"] >= 1000)
    if corps["atteignable"]:
        assert corps["cout_moyen_k"] <= corps["cout_marginal_k"]
    bassin = client.get(f"/api/logistique/sites/{MEKNES}/bassin").json()
    assert bassin["gisements"]["features"]


def test_capacite_non_atteignable_sous_un_plafond_bas(client: TestClient) -> None:
    _completer(client, capacite=1000, plafond=1)  # plafond sous tout coût livré
    corps = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    assert corps["bloque"] is False
    assert corps["atteignable"] is False and corps["manque"] == pytest.approx(1000)


def test_repli_signale_quand_osrm_est_arrete(chemins: Chemins) -> None:
    _sans_osrm(chemins)
    app = creer_app()
    app.dependency_overrides[obtenir_chemins] = lambda: chemins
    app.dependency_overrides[obtenir_referentiel] = _referentiel
    app.dependency_overrides[obtenir_provinces] = _regions
    client = TestClient(app, raise_server_exceptions=False)
    etat = client.get("/api/logistique/etat").json()
    assert etat["osrm"] is False
    assert etat["commande"] == commande_osrm()
    corps = client.get("/api/logistique/sites").json()
    assert corps["methode"] == "vol_oiseau"
    assert "OSRM ne répond pas" in corps["message"]


def test_repli_impossible_sans_calibration_message_clair(chemins: Chemins) -> None:
    _sans_osrm(chemins, calibration=False)
    app = creer_app()
    app.dependency_overrides[obtenir_chemins] = lambda: chemins
    app.dependency_overrides[obtenir_referentiel] = _referentiel
    app.dependency_overrides[obtenir_provinces] = _regions
    reponse = TestClient(app, raise_server_exceptions=False).get("/api/logistique/sites")
    assert reponse.status_code == 503
    assert commande_osrm() in reponse.json()["erreur"]


@pytest.mark.parametrize(
    ("systeme", "script"), [("nt", "osrm_setup.ps1"), ("posix", "osrm_setup.sh")]
)
def test_commande_osrm_selon_le_systeme(systeme: str, script: str) -> None:
    # Windows : script PowerShell (osrm_setup.sh exige bash) ; les deux scripts sont livrés.
    commande = commande_osrm(systeme)
    assert script in commande
    assert (DEPOT.racine / "scripts" / script).is_file()


def test_ajout_d_un_site_par_coordonnees(client: TestClient) -> None:
    corps = {"nom": "Plateforme de Taza", "lon": -4.01, "lat": 34.21, "auteur": AUTEUR}
    site = client.post("/api/logistique/sites", json=corps).json()
    assert site["id_site"] == "UT-1"
    ids = {s["id_site"] for s in client.get("/api/logistique/sites").json()["sites"]}
    assert "UT-1" in ids
    refus = client.post("/api/logistique/sites", json={**corps, "lon": -9.9, "lat": 34.0})
    assert refus.status_code == 400 and "hors des 75 provinces" in refus.json()["erreur"]
    assert client.delete("/api/logistique/sites/UT-1").status_code == 200


def test_prix_observe_des_grignons_change_le_cout_livre(client: TestClient) -> None:
    """Recette 18.3 : un prix observé saisi avec sa source change le coût livré (R01 ici)."""
    _completer(client, capacite=1000, plafond=100000)
    avant = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    assert avant["bloque"] is False
    cout = {(p["code_province"], p["code_residu"]): p["cout_livre"] for p in avant["points"]}
    corps = {
        "date": "2026-11-23",
        "produit": "R01",
        "code_province": "NATIONAL",
        "prix": "150",  # DH/t brute, saisie simulée pour le test
        "unite": "DH/t",
        "source": SIMULE,
        "auteur": AUTEUR,
    }
    assert client.post("/api/donnees/prix", json=corps).status_code == 201
    apres = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    h = 0.30  # humidité R01 simulée par _completer
    for p in apres["points"]:
        ecart = p["cout_livre"] - cout[(p["code_province"], p["code_residu"])]
        assert ecart == pytest.approx(150 / (1 - h))  # a passe de 0 à 150 DH/t brute
