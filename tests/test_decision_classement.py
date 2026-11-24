"""Lot 5 : classement des sites, filtres, robustesse, variations de rang (UC-DEC-01 à 06).

Matrice tirée de l'extrait figé réel (villes OSM et distances OSRM de tests/fixtures/), poids,
seuils et capacités atteignables en saisies simulées pour le test.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.chemins import chemins_par_defaut
from src.decision.calcul import actifs_par_defaut, variations_de_rang
from src.decision.classement import TOPSIS, Reglages, Seuil, classer, poids_par_defaut, robustesse
from src.decision.config import charger_catalogue_criteres, charger_config_decision
from src.decision.methodes import ErreurMethode
from src.decision.spatial import distances_plus_proches, surface_dans_rayon
from src.logistique.distances import vol_oiseau_km
from tests.test_acv import FIXTURES
from tests.test_decision_methodes import X
from tests.test_logistique import _cropgrids_olivier, _lieux

DEPOT = chemins_par_defaut()
CATALOGUE = charger_catalogue_criteres(DEPOT)
CONFIG = charger_config_decision(DEPOT)
SITES = ["S1", "S2", "S3", "S4"]


def _valeurs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """G1 (↑), C2 (↓), F1 (↓) et B5 (filtre) : extrait réel, B5 en saisie simulée."""
    valeurs = pd.DataFrame(
        {"G1": X[:, 0], "C2": X[:, 1], "F1": X[:, 2], "B5": [1.0, 1.0, 0.0, np.nan]},
        index=pd.Index(SITES, name="id_site"),
    )
    motifs = pd.DataFrame(
        {
            "G1": None,
            "C2": None,
            "F1": None,
            "B5": [None, None, "R13 absent de la liste", "à compléter"],
        },
        index=valeurs.index,
    )
    return valeurs, motifs


def _classer(reglages: Reglages, atteignable: dict | None = None):
    valeurs, motifs = _valeurs()
    return classer(
        valeurs,
        motifs,
        atteignable or dict.fromkeys(SITES, True),
        reglages,
        CATALOGUE,
        0.8,
        CONFIG.minimum_sites,
        CONFIG.minimum_criteres,
    )


def test_poids_par_defaut_egaux_entre_axes_puis_criteres() -> None:
    poids = poids_par_defaut(["G1", "C2", "F1", "F2"], CATALOGUE)
    assert poids == pytest.approx({"G1": 1 / 3, "C2": 1 / 3, "F1": 1 / 6, "F2": 1 / 6})
    assert sum(poids.values()) == pytest.approx(1)


def test_filtre_eliminatoire_reste_visible_avec_son_motif() -> None:
    c = _classer(Reglages(actifs=["G1", "C2", "F1", "B5"]))
    assert c.exclus.set_index("id_site").loc["S3", "motif"].startswith("B5")
    assert "S3" not in set(c.tableau["id_site"])
    assert any("filtre B5 non appliqué à 1 sites" in a for a in c.avertissements)
    assert sorted(c.tableau["rang"]) == [1, 2, 3]


def test_seuils_capacite_et_sites_exclus_ou_imposes() -> None:
    ordre = [SITES[k] for k in np.argsort(X[:, 1])]  # du plus proche au plus loin (C2)
    proches = ordre
    seuil = float(np.sort(X[:, 1])[-2])  # C2 au plus la 3e distance : exclut le plus lointain
    atteignable = dict.fromkeys(SITES, True) | {proches[0]: False, proches[1]: None}
    exclu = _classer(Reglages(actifs=["G1", "C2", "F1"], exclus=["S1"]))
    assert exclu.exclus.set_index("id_site").loc["S1", "motif"] == (
        "site exclu par l'entreprise (PAR-57)"
    )
    c = _classer(
        Reglages(actifs=["G1", "C2", "F1"], seuils={"C2": Seuil(maximum=seuil)}), atteignable
    )
    motifs = dict(zip(c.exclus["id_site"], c.exclus["motif"], strict=True))
    assert "RG-10" in motifs[proches[0]]
    assert "au-dessus du seuil" in motifs[ordre[-1]]
    assert any("RG-10 non appliquée à 1 sites" in a for a in c.avertissements)
    impose = _classer(
        Reglages(actifs=["G1", "C2", "F1"], imposes=[proches[0]]),
        dict.fromkeys(SITES, True) | {proches[0]: False},
    )
    assert proches[0] in set(impose.tableau["id_site"])


def test_critere_constant_neutralise_et_critere_manquant_retire() -> None:
    valeurs, motifs = _valeurs()
    valeurs["E1"] = 5.0
    valeurs["A1"] = [1.0, np.nan, 2.0, 3.0]
    motifs["A1"] = [None, "bassin non calculé", None, None]
    c = classer(
        valeurs,
        motifs,
        dict.fromkeys(SITES, True),
        Reglages(actifs=["G1", "C2", "F1", "E1", "A1"]),
        CATALOGUE,
        0.8,
        CONFIG.minimum_sites,
        CONFIG.minimum_criteres,
    )
    assert "neutralisé" in c.retires["E1"] and "bassin non calculé" in c.retires["A1"]
    assert c.criteres == ["G1", "C2", "F1"]
    assert sum(c.poids.values()) == pytest.approx(1)


def test_contributions_et_methodes() -> None:
    c = _classer(Reglages(actifs=["G1", "C2", "F1"], poids={"G1": 2, "C2": 1, "F1": 1}))
    contributions = c.tableau[[f"contribution_{k}" for k in c.criteres]].sum(axis=1)
    assert contributions.to_numpy() == pytest.approx(c.tableau["score"].to_numpy())
    assert c.poids == pytest.approx({"G1": 0.5, "C2": 0.25, "F1": 0.25})
    t = _classer(Reglages(actifs=["G1", "C2", "F1"], methode=TOPSIS))
    assert t.tableau["score"].between(0, 1).all()


def test_correlation_forte_signalee() -> None:
    c = _classer(Reglages(actifs=["G1", "C2", "F1"]))
    r = np.corrcoef(X[:, 1], X[:, 2])[0, 1]
    assert (abs(r) > 0.8) == any("C2 et F1" in a for a in c.avertissements)


def test_moins_de_deux_sites_refuse() -> None:
    with pytest.raises(ErreurMethode, match="moins de 2 sites"):
        _classer(Reglages(actifs=["G1", "C2", "F1"], exclus=["S1", "S2", "S3"]))


def test_robustesse_un_poids_a_la_fois_et_monte_carlo() -> None:
    c = _classer(Reglages(actifs=["G1", "C2", "F1"]))
    s = CONFIG.sensibilite
    variations = np.round(np.arange(s.variation_min, s.variation_max + s.pas / 2, s.pas), 10)
    r = robustesse(c, CATALOGUE, "somme_ponderee", variations, 50, 1000, 42, 3, 0.6)
    assert len(r.un_poids) == 3 * 11
    assert sum(r.proba_premier.values()) == pytest.approx(1)
    premier = c.tableau["id_site"].iloc[0]
    assert (premier in r.robustes) == (
        r.proba_premier[premier] >= 0.6
        and r.rangs_wsm[premier] <= 3
        and r.rangs_topsis[premier] <= 3
    )
    again = robustesse(c, CATALOGUE, "somme_ponderee", variations, 50, 1000, 42, 3, 0.6)
    assert again.proba_premier == r.proba_premier  # ENF-04


def test_classement_de_76_sites_en_moins_de_2_secondes() -> None:
    generateur = np.random.default_rng(
        0
    )  # permutation de valeurs réelles, pas de données inventées
    lignes = np.vstack([X[generateur.permutation(4)] for _ in range(19)])
    valeurs = pd.DataFrame(lignes, columns=["G1", "C2", "F1"], index=[f"S{i}" for i in range(76)])
    valeurs["G1"] += np.arange(76)  # départage les copies
    debut = time.perf_counter()
    c = classer(
        valeurs,
        pd.DataFrame(index=valeurs.index, columns=valeurs.columns),
        {},
        Reglages(actifs=["G1", "C2", "F1"]),
        CATALOGUE,
        0.8,
        2,
        2,
    )
    assert time.perf_counter() - debut < 2 and len(c.tableau) == 76


def test_variations_de_rang_apres_un_changement_de_parametre(tmp_path: Path) -> None:
    assert variations_de_rang(tmp_path, "plafond-600", {"S1": 1, "S2": 2}) == {}
    assert variations_de_rang(tmp_path, "plafond-900", {"S1": 2, "S2": 1}) == {"S1": -1, "S2": 1}
    # Un recalcul au même réglage compare toujours au réglage précédent.
    assert variations_de_rang(tmp_path, "plafond-900", {"S1": 2, "S2": 1}) == {"S1": -1, "S2": 1}


def test_criteres_actifs_par_defaut_et_c6() -> None:
    sans = actifs_par_defaut(CATALOGUE, set())
    assert "C6" not in sans and {"A1", "C1", "D1", "G1"} <= set(sans)
    assert "C6" in actifs_par_defaut(CATALOGUE, {"PAR-55", "PAR-56"})


def test_indicateurs_spatiaux() -> None:
    lieux = _lieux()
    sites = pd.DataFrame(
        {"id_site": ["a", "b"], "lon": lieux["lon"].iloc[:2], "lat": lieux["lat"].iloc[:2]}
    )
    autres = lieux.iloc[2:]
    d = distances_plus_proches(sites, autres, CONFIG)
    attendu = [
        vol_oiseau_km(x, y, autres["lon"].to_numpy(), autres["lat"].to_numpy(), 6371.0088).min()
        for x, y in zip(sites["lon"], sites["lat"], strict=True)
    ]
    assert d == pytest.approx(attendu, rel=0.01)  # projection UTM 29N contre grand cercle
    grille = _cropgrids_olivier()
    surface = surface_dans_rayon(sites, grille, "croparea", 50, 6371.0088)
    total = grille["croparea"].fillna(0).sum().item()
    assert (surface > 0).all() and (surface < total).all()
    assert FIXTURES.is_dir()


def test_gisements_couple_incomplet_exclu_critere_absent_partout_retire() -> None:
    valeurs, motifs = _valeurs()
    valeurs["A1"] = [1.0, 2.0, np.nan, 3.0]  # manque pour un couple : couple exclu
    motifs["A1"] = [None, None, "M non calculé", None]
    valeurs["D1"] = np.nan  # manque partout : critère retiré
    motifs["D1"] = "bilan climat non calculé"
    c = classer(
        valeurs,
        motifs,
        {},
        Reglages(actifs=["G1", "C2", "A1", "D1"], filtre_capacite=False),
        CATALOGUE,
        0.8,
        CONFIG.minimum_sites,
        CONFIG.minimum_criteres,
        exclure_incompletes=True,
        nom_alternatives="gisements",
    )
    assert c.exclus.set_index("id_site").loc["S3", "motif"] == "A1 manquant : M non calculé"
    assert "bilan climat non calculé" in c.retires["D1"]
    assert c.criteres == ["G1", "C2", "A1"] and c.partiel and c.criteres_actifs == 4
