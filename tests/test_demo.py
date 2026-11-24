# ruff: noqa: F811 — la fixture chemins vient de test_api_logistique.
"""Scénarios de démonstration (scenarios/demo/, config/demo.yaml) sur l'extrait figé.

Vérifié : les 5 scénarios se chargent en un clic et débloquent les écrans (gisement
mobilisable, courbe de Meknès, bilan climat, classement, mélange) ; les saisies réelles de
l'entreprise et les données ne sont jamais modifiées ; une valeur connue n'est jamais
remplacée ; « Quitter la démonstration » revient à l'état réel ; le bandeau est repris en tête
des exports. La saisie réelle de l'entreprise ci-dessous est une « saisie simulée pour le test ».
"""

import hashlib
import shutil
import sys
import types
from pathlib import Path

import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from api.app import creer_app
from api.dependances import obtenir_chemins_reels, obtenir_referentiel
from api.routes.logistique import obtenir_provinces
from src.chemins import Chemins
from src.data.versions import Versions
from src.logistique.config import charger_config_logistique
from src.logistique.distances import osrm_disponible
from src.scenarios import demo
from src.scenarios.demo import (
    RapportChargement,
    _completer_table,
    charger_config_demo,
    charger_hypotheses,
    charger_scenario_demo,
    chemins_de_travail,
    demo_active,
    lier_dossier,
    lister_identifiants,
)
from tests.test_api_logistique import AUTEUR, MEKNES, _regions, _sans_osrm, chemins  # noqa: F401
from tests.test_preparation import DEPOT, _referentiel

SAISIE_REELLE = {"PAR-01": 7000.0}  # saisie simulée pour le test
SCENARIOS = ["demo-1", "demo-2", "demo-3", "demo-4", "demo-5"]


@pytest.fixture
def reel(chemins: Chemins) -> Chemins:
    """Dossiers « réels » du test : extrait figé, scénarios de démonstration du dépôt."""
    shutil.copytree(DEPOT.scenarios / "demo", chemins.scenarios / "demo")
    return chemins


@pytest.fixture
def client(reel: Chemins) -> TestClient:
    if not osrm_disponible(charger_config_logistique(reel)):
        _sans_osrm(reel)
    app = creer_app()
    # Seuls les dossiers réels sont remplacés : la bascule vers la copie de travail est testée.
    app.dependency_overrides[obtenir_chemins_reels] = lambda: reel
    app.dependency_overrides[obtenir_referentiel] = _referentiel
    app.dependency_overrides[obtenir_provinces] = _regions
    return TestClient(app, raise_server_exceptions=False)


def _empreintes(racine: Path) -> dict[str, str]:
    """Empreinte de chaque fichier de config/ et de data/ (hors copies de démonstration)."""
    miroirs = racine / charger_config_demo(Chemins(racine)).miroirs
    return {
        str(f.relative_to(racine)): hashlib.sha256(f.read_bytes()).hexdigest()
        for dossier in (racine / "config", racine / "data")
        for f in sorted(dossier.rglob("*"))
        if f.is_file() and miroirs not in f.parents
    }


def test_cinq_scenarios_et_heritage(reel: Chemins) -> None:
    assert lister_identifiants(reel) == SCENARIOS
    reference = charger_scenario_demo(reel, "demo-1")
    assert {i: p.valeur for i, p in reference.entreprise.items()} == {
        "PAR-01": 10000,
        "PAR-21": 450,
        "PAR-34": 1200,
        "PAR-37": 12,
    }
    cher = charger_scenario_demo(reel, "demo-5")
    assert cher.entreprise["PAR-37"].valeur == 15.5
    assert cher.entreprise["PAR-01"].valeur == reference.entreprise["PAR-01"].valeur
    assert charger_scenario_demo(reel, "demo-2").entreprise["PAR-59"].valeur == 50
    climat = charger_scenario_demo(reel, "demo-4")
    assert climat.entreprise["PAR-21"].valeur == 600 and climat.decision.poids == {"D1": 5}


def test_hypotheses_sourcees_ou_signalees(reel: Chemins) -> None:
    """Chaque valeur a une note ; une valeur « Littérature » cite sa source."""
    hypotheses = charger_hypotheses(reel)
    valeurs = [
        v
        for table in (hypotheses.residus, hypotheses.concurrence, hypotheses.facteurs_emission)
        for parametres in table.values()
        for v in parametres.values()
    ] + list(hypotheses.reglages.values())
    assert valeurs and all(v.note for v in valeurs)
    assert all(v.source_id for v in valeurs if v.statut.value == "Littérature")
    connues = set(hypotheses.sources) | {"CDC", "SRC-15-GIEC-2019", "SRC-16-LAHBOUBI-2023"}
    # Substitution par le fioul seulement quand une source documente l'usage combustible.
    for code, parametres in hypotheses.residus.items():
        reference = parametres.get("scenario_reference")
        if reference is not None and reference.valeur == "usage concurrent":
            assert reference.source_id, code
    assert {v.source_id for v in valeurs if v.source_id} <= connues


def test_une_valeur_connue_n_est_jamais_remplacee(reel: Chemins) -> None:
    config = charger_config_demo(reel)
    residus = Versions(reel).lire("residus")
    hypotheses = charger_hypotheses(reel)
    # R01 · carbone est connu (48,3 % MS, SRC-16-SUSTAINABILITY-2022) : il doit rester intact.
    valeur = hypotheses.residus["R01"]["humidite"].model_copy(update={"valeur": 99.0})
    rapport = RapportChargement()
    complete = _completer_table(
        residus, {"R01": {"carbone": valeur}}, "code_residu", {}, config, rapport, "residus"
    )
    pd.testing.assert_frame_equal(complete, residus)
    assert rapport.ignorees == ["residus · R01 · carbone (valeur connue conservée)"]


def test_charger_puis_quitter_sans_toucher_au_reel(client: TestClient, reel: Chemins) -> None:
    reponse = client.put("/api/entreprise", json={"auteur": AUTEUR, "valeurs": SAISIE_REELLE})
    assert reponse.status_code == 200
    avant = _empreintes(reel.racine)
    corps = client.post("/api/demo/demo-1").json()
    assert corps["active"]["nom"] == "Unité de référence à Meknès"
    assert corps["completees"] > 0
    etat = client.get("/api/demo").json()
    assert etat["active"]["identifiant"] == "demo-1"
    assert [s["identifiant"] for s in etat["scenarios"]] == SCENARIOS
    # Les écrans lisent la copie de travail : paramètres du scénario.
    valeurs = {
        p["identifiant"]: p["valeur"] for p in client.get("/api/entreprise").json()["parametres"]
    }
    assert valeurs["PAR-01"] == 10000 and valeurs["PAR-37"] == 12
    travail = chemins_de_travail(reel)
    assert travail.racine != reel.racine and demo_active(travail) is not None
    residus = Versions(travail).lire("residus")
    k_col = residus[(residus["code_residu"] == "R01") & (residus["parametre"] == "k_col")].iloc[0]
    assert k_col["valeur"] == "432" and k_col["statut"] == "Hypothèse"
    assert "valeur de démonstration" in k_col["note"]
    projet = yaml.safe_load((travail.config / "acv.yaml").read_text(encoding="utf-8"))["projet"]
    assert projet.endswith(charger_config_demo(reel).suffixe_projet_brightway)
    # Rien de réel n'a changé hormis le pointeur local de la démonstration.
    apres = _empreintes(reel.racine)
    pointeur = f"config/{charger_config_demo(reel).pointeur}"
    assert {k: v for k, v in apres.items() if k != pointeur} == avant
    # Quitter : retour aux saisies réelles, intactes.
    assert client.delete("/api/demo").json()["quittee"] is True
    assert client.get("/api/demo").json()["active"] is None
    valeurs = {
        p["identifiant"]: p["valeur"] for p in client.get("/api/entreprise").json()["parametres"]
    }
    assert valeurs["PAR-01"] == SAISIE_REELLE["PAR-01"] and valeurs["PAR-37"] is None
    assert _empreintes(reel.racine) == avant


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_chaque_scenario_debloque_les_ecrans(client: TestClient, scenario: str) -> None:
    assert client.post(f"/api/demo/{scenario}").status_code == 200
    synthese = client.get("/api/potentiel/synthese").json()
    mobilisable = next(t for t in synthese["totaux"] if t["indicateur"] == "M")
    assert mobilisable["total"] > 0
    courbe = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    assert courbe["bloque"] is False and courbe["points"]
    bilan = client.get(f"/api/acv/sites/{MEKNES}").json()
    assert bilan["couples_calcules"] > 0 and bilan["bilan_site"] is not None
    classement = client.get("/api/decision/classement").json()
    assert classement["bloque"] is False and len(classement["classement"]) >= 3
    melange = client.get(f"/api/melange/{MEKNES}").json()
    assert melange["bloque"] is False


def test_bandeau_en_tete_des_exports(client: TestClient) -> None:
    client.post("/api/demo/demo-1")
    texte = client.get("/api/exports/classement.csv").content.decode("utf-8-sig")
    bandeau = charger_config_demo(Chemins(DEPOT.racine)).bandeau
    assert texte.splitlines()[0] == f"# {bandeau} · Unité de référence à Meknès"
    client.delete("/api/demo")
    texte = client.get("/api/exports/classement.csv").content.decode("utf-8-sig")
    assert "Démonstration" not in texte


def test_scenario_inconnu(client: TestClient) -> None:
    reponse = client.post("/api/demo/hypotheses")
    assert reponse.status_code == 400
    assert "introuvable" in reponse.json()["erreur"]


def test_lien_vers_les_donnees_brutes_sans_copie(tmp_path: Path) -> None:
    source = tmp_path / "raw"
    source.mkdir()
    (source / "fichier.csv").write_text("a;b\n", encoding="utf-8")
    lien = tmp_path / "copie" / "raw"
    lien.parent.mkdir()
    lier_dossier(source, lien)
    assert (lien / "fichier.csv").read_text(encoding="utf-8") == "a;b\n"
    shutil.rmtree(lien.parent)
    assert (source / "fichier.csv").is_file()  # supprimer la copie ne touche pas aux données


def test_lien_sous_windows_sans_droits_jonction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sous Windows sans mode développeur, os.symlink échoue : une jonction le remplace.
    appels: list[tuple[str, str]] = []

    def refuser(*_: object, **__: object) -> None:
        raise OSError("privilège requis")

    module = types.ModuleType("_winapi")
    module.CreateJunction = lambda source, lien: appels.append((source, lien))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "_winapi", module)
    monkeypatch.setattr(demo.os, "symlink", refuser)
    with monkeypatch.context() as m:
        m.setattr(demo.os, "name", "nt")
        lier_dossier(tmp_path / "raw", tmp_path / "lien")
    assert appels == [(str(tmp_path / "raw"), str(tmp_path / "lien"))]
    with pytest.raises(OSError, match="privilège"):  # hors Windows, l'erreur n'est pas masquée
        lier_dossier(tmp_path / "raw", tmp_path / "lien")
