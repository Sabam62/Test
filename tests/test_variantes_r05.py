# ruff: noqa: F811 — les fixtures chemins et client viennent de test_api_logistique.
"""Non-régression : la logistique et le bilan climat lisent l'humidité du procédé de PAR-62.

Avant le correctif, seul le calcul des gisements appliquait PAR-62 (procédé de trituration des
grignons, R05) ; la logistique et l'ACV cherchaient une humidité de R05 sans précision et
excluaient les grignons (« aucune valeur humidite pour R05 »). Les valeurs « À compléter » de
R05 sont des « saisies simulées pour le test », passées par les routes de l'outil.
"""

from fastapi.testclient import TestClient

from src.chemins import Chemins
from src.data.tables_reference import charger_tables_reference
from src.potentiel.config import charger_config_potentiel
from src.potentiel.theorique import resoudre_variantes
from src.scenarios.parametres import regler_parametre, valeur_courante
from tests.test_api_acv import _completer as completer_acv
from tests.test_api_logistique import (  # noqa: F401
    AUTEUR,
    MEKNES,
    SIMULE,
    _completer,
    _saisir,
    chemins,
    client,
)

GRIGNONS = "R05"
# Humidité de chaque procédé dans data/input/residus.csv (SRC-16-PROCESSES), en % masse brute.
HUMIDITES = {"trois phases": 45.0, "deux phases": 70.0}


def _humidite(chemins: Chemins) -> float | None:
    residus = resoudre_variantes(
        charger_tables_reference(chemins).residus,
        charger_config_potentiel(chemins),
        lambda identifiant: valeur_courante(chemins, identifiant),
    )
    try:
        return float(residus.valeur(GRIGNONS, "humidite").lire_nombre())
    except KeyError:
        return None


def test_variante_choisie_devient_la_valeur_generale(chemins: Chemins) -> None:
    assert _humidite(chemins) is None  # PAR-62 « À compléter » : table laissée telle quelle
    for procede, humidite in HUMIDITES.items():
        regler_parametre(chemins, "PAR-62", procede, SIMULE, AUTEUR)
        assert _humidite(chemins) == humidite


def test_logistique_et_bilan_climat_comptent_les_grignons(client: TestClient) -> None:
    _completer(client, capacite=1000, plafond=100000)
    completer_acv(client)
    for parametre, valeur in (
        ("f_col", "0.95"),
        ("f_eco", "1"),
        ("densite_apparente", "675"),
        ("k_col", "20"),
        ("k_pre", "100"),
        ("carbone_biochar", "74"),
        ("scenario_reference", "usage concurrent"),
    ):
        cle = {"code_residu": GRIGNONS, "parametre": parametre, "precision": ""}
        _saisir(client, "residus", cle, valeur)
    cle = {
        "code_province": "NATIONAL",
        "code_residu": GRIGNONS,
        "parametre": "part_utilisee",
        "precision": "",
    }
    _saisir(client, "concurrence", cle, "0.6")
    corps = {"valeur": "trois phases", "source": SIMULE, "auteur": AUTEUR}
    assert client.put("/api/parametres/PAR-62", json=corps).status_code == 200

    courbe = client.get(f"/api/logistique/sites/{MEKNES}/courbe").json()
    assert courbe["bloque"] is False, courbe.get("a_saisir")
    assert not [e for e in courbe["exclus"] if GRIGNONS in e["residus"]], courbe["exclus"]
    assert any(p["code_residu"] == GRIGNONS for p in courbe["points"])

    bilan = client.get(f"/api/acv/sites/{MEKNES}").json()
    grignons = next(r for r in bilan["par_residu"] if r["code_residu"] == GRIGNONS)
    assert grignons["couples_calcules"] > 0, grignons["motif"]
