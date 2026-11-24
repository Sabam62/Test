"""Routes de l'API (tâche 9) sur une copie temporaire de l'extrait figé des données réelles.

Messages d'erreur en français, sans trace Python (ENF-12). Les valeurs modifiées sont des
« saisies simulées pour le test ».
"""

import io
import shutil
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.app import creer_app
from api.dependances import obtenir_chemins, obtenir_referentiel
from src.chemins import Chemins
from src.data.controles import rendre_rapport
from src.data.excel import FEUILLE_DONNEES
from src.data.versions import Versions
from tests.aides import copier_config
from tests.test_preparation import DEPOT, TAOUNATE, VALEUR_TAOUNATE, _referentiel, _statistiques
from tests.test_scenarios import SAISIE_SIMULEE
from tests.test_versions import CLE_TAOUNATE, SAISIE_SIMULEE_TAOUNATE, plage_simulee

AUTEUR = "test automatique"
SIGNATURE = {"auteur": AUTEUR, "commentaire": "saisie simulée pour le test"}


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    shutil.copyfile(DEPOT.donnees / "sources.yaml", chemins.donnees / "sources.yaml")
    chemins.preparees.mkdir(parents=True)
    stats = _statistiques()
    stats.resultat.production.to_parquet(chemins.preparees / "production.parquet", index=False)
    rapport = rendre_rapport(stats.bilan, stats.resultat, _referentiel().provinces, {})
    (chemins.preparees / "rapport_controle.html").write_text(rapport, encoding="utf-8")
    Versions(chemins).initialiser(AUTEUR, "données livrées")
    return chemins


@pytest.fixture
def client(chemins: Chemins) -> TestClient:
    app = creer_app()
    app.dependency_overrides[obtenir_chemins] = lambda: chemins
    app.dependency_overrides[obtenir_referentiel] = _referentiel
    return TestClient(app, raise_server_exceptions=False)


def _erreur(reponse, code: int, fragment: str) -> None:
    assert reponse.status_code == code, reponse.text
    message = reponse.json()["erreur"]
    assert fragment in message
    assert "Traceback" not in reponse.text


# --- Entreprise ---------------------------------------------------------------------------


def test_entreprise_obligatoires_puis_enregistrement(client: TestClient) -> None:
    etat = client.get("/api/entreprise").json()
    assert etat["renseignement_requis"] is True
    assert etat["a_renseigner"] == ["PAR-01", "PAR-21", "PAR-34", "PAR-37"]
    assert etat["obligatoires"] == etat["a_renseigner"]
    reponse = client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": SAISIE_SIMULEE})
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["renseignement_requis"] is False
    assert set(corps["modifies"]) == set(SAISIE_SIMULEE)
    assert corps["auteur"] == AUTEUR


def test_entreprise_valeur_refusee(client: TestClient) -> None:
    reponse = client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": {"PAR-01": -1}})
    _erreur(reponse, 400, "positive")


def test_entreprise_requete_invalide(client: TestClient) -> None:
    _erreur(client.put("/api/entreprise", json={"valeurs": {}}), 422, "auteur")


# --- Paramètres techniques ----------------------------------------------------------------


def test_parametres_regler_et_revenir_au_defaut(client: TestClient) -> None:
    liste = {p["identifiant"]: p for p in client.get("/api/parametres").json()}
    defaut = liste["PAR-35"]["defaut"]["valeur"]
    assert liste["PAR-35"]["courante"]["provenance"]["source_id"]
    assert liste["PAR-61"]["courante"]["a_completer"] is True
    reglee = client.put(
        "/api/parametres/PAR-35", json={"valeur": 80, "source": "réglage", "auteur": AUTEUR}
    )
    assert reglee.status_code == 200 and reglee.json()["valeur"] == 80
    assert client.delete("/api/parametres/PAR-35").json()["valeur"] == defaut


def test_parametre_calcule_refuse(client: TestClient) -> None:
    reponse = client.put(
        "/api/parametres/PAR-33", json={"valeur": 1, "source": "x", "auteur": AUTEUR}
    )
    _erreur(reponse, 400, "calculé par l'outil")


# --- Scénarios ----------------------------------------------------------------------------


def test_scenario_enregistre_recharge_applique(client: TestClient) -> None:
    client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": SAISIE_SIMULEE})
    cree = client.post("/api/scenarios", json={"nom": "Test API", "auteur": AUTEUR})
    assert cree.status_code == 201
    assert cree.json()["version_donnees"] == "v0001"
    assert cree.json()["ecart_version"] is None
    _erreur(
        client.post("/api/scenarios", json={"nom": "Test API", "auteur": AUTEUR}), 400, "existe"
    )
    recharge = client.get("/api/scenarios/Test API").json()
    assert recharge["parametres_entreprise"]["PAR-34"] == SAISIE_SIMULEE["PAR-34"]
    assert [s["nom"] for s in client.get("/api/scenarios").json()] == ["Test API"]
    client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": {"PAR-34": 900}})
    client.post("/api/scenarios/Test API/appliquer", json={"auteur": AUTEUR})
    etat = client.get("/api/entreprise").json()
    par34 = next(p for p in etat["parametres"] if p["identifiant"] == "PAR-34")
    assert par34["valeur"] == SAISIE_SIMULEE["PAR-34"]


def test_scenario_introuvable(client: TestClient) -> None:
    _erreur(client.get("/api/scenarios/absent"), 400, "introuvable")


# --- Référentiel --------------------------------------------------------------------------


def test_referentiel_regions_et_provinces(client: TestClient) -> None:
    assert len(client.get("/api/referentiel/regions").json()) == 12
    provinces = client.get("/api/referentiel/provinces").json()
    assert len(provinces) == 75
    assert {"code_province", "code_region", "nom_fr"} <= set(provinces[0])


def test_contours_absents_message_clair(client: TestClient) -> None:
    _erreur(client.get("/api/referentiel/provinces/geojson"), 503, "python -m scripts.prepare")
    _erreur(client.get("/api/referentiel/communes/geojson"), 404, "inconnu")


@pytest.mark.donnees_reelles
def test_contours_reels_avec_attribution() -> None:
    if not (DEPOT.preparees / "provinces.gpkg").is_file():
        pytest.skip("lancez python -m scripts.prepare")
    geojson = TestClient(creer_app()).get("/api/referentiel/provinces/geojson").json()
    assert len(geojson["features"]) == 75
    assert geojson["attribution"] == "© Haut-Commissariat au Plan"


# --- Données : tables, import Excel, saisie -----------------------------------------------


def test_tables_et_provenance(client: TestClient) -> None:
    tables = {t["table"]: t for t in client.get("/api/donnees/tables").json()}
    assert {"production", "residus", "concurrence", "prix_observes"} <= set(tables)
    assert tables["production"]["mise_a_jour"]
    page = client.get("/api/donnees/tables/production", params={"filtre": "fes-meknes_2017"}).json()
    assert page["total"] > 0
    assert {"source_id", "annee", "statut", "version"} <= set(page["colonnes"])
    _erreur(client.get("/api/donnees/tables/inexistante"), 400, "inconnue")


def _classeur_modifie(client: TestClient, valeur: float) -> bytes:
    reponse = client.get("/api/donnees/tables/production/modele.xlsx")
    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("application/vnd.openxmlformats")
    donnees = pd.read_excel(io.BytesIO(reponse.content), sheet_name=FEUILLE_DONNEES, dtype=object)
    masque = pd.Series(True, index=donnees.index)
    for colonne, attendu in CLE_TAOUNATE.items():
        masque &= donnees[colonne].astype(str) == attendu
    donnees.loc[masque, "valeur"] = valeur
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as classeur:
        donnees.to_excel(classeur, sheet_name=FEUILLE_DONNEES, index=False)
    return tampon.getvalue()


def _importer(client: TestClient, contenu: bytes) -> dict:
    reponse = client.post(
        "/api/donnees/tables/production/import",
        files={"fichier": ("production.xlsx", contenu, "application/octet-stream")},
    )
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


def test_import_inconnu_et_fichier_illisible(client: TestClient) -> None:
    _erreur(client.post("/api/donnees/imports/inconnu/valider", json=SIGNATURE), 404, "introuvable")
    reponse = client.post(
        "/api/donnees/tables/production/import",
        files={"fichier": ("x.xlsx", b"pas un classeur", "application/octet-stream")},
    )
    _erreur(reponse, 400, "Excel")


def test_saisie_directe_et_refus_sans_date(client: TestClient) -> None:
    corps = {
        **SIGNATURE,
        "cle": CLE_TAOUNATE,
        "valeur": str(SAISIE_SIMULEE_TAOUNATE),
        "source": "mesure interne",
        "date": "",
    }
    _erreur(client.put("/api/donnees/tables/production/valeur", json=corps), 400, "date")
    corps["date"] = "2026-11-22"
    reponse = client.put("/api/donnees/tables/production/valeur", json=corps)
    assert reponse.status_code == 200 and reponse.json()["version"]["id_version"] == "v0002"


def _saisie_f_col(valeur: str) -> dict:
    return {
        **SIGNATURE,
        "cle": {"code_residu": "R05", "parametre": "f_col", "precision": ""},
        "valeur": valeur,
        "source": "mesure interne",
        "date": "2026-11-22",
    }


def test_saisie_hors_domaine_refusee(client: TestClient) -> None:
    reponse = client.put("/api/donnees/tables/residus/valeur", json=_saisie_f_col("1.5"))
    _erreur(reponse, 400, "domaine physique")


def test_saisie_peu_plausible_demande_confirmation(client: TestClient, chemins: Chemins) -> None:
    plage_simulee(chemins, "residus", "f_col", 0.2, 0.8)
    reponse = client.put("/api/donnees/tables/residus/valeur", json=_saisie_f_col("0.95"))
    assert reponse.status_code == 409
    assert reponse.json()["confirmation_requise"] is True
    confirmee = client.put(
        "/api/donnees/tables/residus/valeur", json=_saisie_f_col("0.95") | {"confirmer": True}
    )
    assert confirmee.status_code == 200


# --- Prix ---------------------------------------------------------------------------------


def test_prix_observes(client: TestClient) -> None:
    for jour, prix in (("2026-10-01", "650"), ("2026-11-15", "670")):
        corps = {
            "date": jour,
            "produit": "grignons",
            "code_province": "Meknès",
            "prix": prix,
            "unite": "DH/t",
            "source": "saisie simulée pour le test",
            "auteur": AUTEUR,
        }
        assert client.post("/api/donnees/prix", json=corps).status_code == 201
    prix = client.get("/api/donnees/prix", params={"produit": "grignons"}).json()
    assert len(prix["historique"]) == 2
    (courant,) = prix["courants"]
    assert courant["prix"] == "670" and courant["code_province"] == "3061"
    corps["source"] = ""
    _erreur(client.post("/api/donnees/prix", json=corps), 400, "source obligatoire")


def test_prix_province_inconnue(client: TestClient) -> None:
    corps = {
        "date": "2026-11-15",
        "produit": "paille",
        "code_province": "Atlantide",
        "prix": "10",
        "unite": "DH/botte",
        "source": "x",
        "auteur": AUTEUR,
    }
    _erreur(client.post("/api/donnees/prix", json=corps), 422, "Atlantide")


# --- Sources, rapport, versions -----------------------------------------------------------


def test_sources_et_rapport(client: TestClient) -> None:
    sources = {s["source_id"]: s for s in client.get("/api/donnees/sources").json()}
    assert "SRC-18" in sources and sources["SRC-01"]["licence"]
    rapport = client.get("/api/donnees/rapport")
    assert rapport.status_code == 200 and "Rapport de contrôle" in rapport.text


def test_resume_pour_les_titres(client: TestClient) -> None:
    resume = client.get("/api/donnees/resume").json()
    assert resume["provinces_total"] == 75
    assert resume["provinces_avec_production"] == 75
    assert 0 < resume["provinces_avec_valeur_reelle"] < 75
    assert {"olivier", "palmier_dattier", "ble"} <= set(resume["cultures"])
    assert resume["campagne_min"] == "2010-2011"
    assert resume["a_completer"]["facteurs_emission"] > 0
    assert resume["derniere_version"]["id_version"] == "v0001"


def test_rapport_absent(client: TestClient, chemins: Chemins) -> None:
    (chemins.preparees / "rapport_controle.html").unlink()
    _erreur(client.get("/api/donnees/rapport"), 503, "scripts.prepare")


def test_restauration_version_inconnue(client: TestClient) -> None:
    _erreur(client.post("/api/donnees/versions/v9999/restaurer", json=SIGNATURE), 400, "inconnue")


# --- Parcours complet de la condition de fin du lot 1 -------------------------------------


def test_parcours_condition_de_fin(client: TestClient, chemins: Chemins) -> None:
    """75 provinces avec une production ; import Excel → version → restauration identique."""
    statut = client.get("/api/donnees/statut-provinces").json()
    assert statut["total"] == 75
    assert "absente" not in statut["resume"]
    taounate = next(p for p in statut["provinces"] if p["code_province"] == TAOUNATE)
    assert taounate["statut"] == "réelle"
    assert all(p["sources"] for p in statut["provinces"])

    apercu = _importer(client, _classeur_modifie(client, SAISIE_SIMULEE_TAOUNATE))
    assert len(apercu["modifiees"]) == 1 and not apercu["rejetees"]
    validee = client.post(f"/api/donnees/imports/{apercu['import']}/valider", json=SIGNATURE)
    version = validee.json()["version"]
    assert version["id_version"] == "v0002" and version["nb_lignes_modifiees"] == 1

    journal = client.get("/api/donnees/versions").json()
    assert [v["id_version"] for v in journal] == ["v0002", "v0001"]
    difference = client.get(
        "/api/donnees/versions/v0001/comparer/v0002", params={"table": "production"}
    ).json()
    assert difference["avant"][0]["valeur"] == VALEUR_TAOUNATE
    assert difference["modifiees"][0]["valeur"] == SAISIE_SIMULEE_TAOUNATE

    restauree = client.post(
        "/api/donnees/versions/v0001/restaurer", json={**SIGNATURE, "commentaire": "retour"}
    ).json()["version"]
    assert restauree["restauration_de"] == "v0001"
    versions = Versions(chemins)
    assert versions.fichier("production").read_bytes() == (
        versions.fichier("production", "v0001").read_bytes()
    )
