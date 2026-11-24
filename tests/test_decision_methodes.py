"""Lot 5 : méthodes multicritères (section 10, tests de la section 18.1).

Matrice 4 × 3 tirée de l'extrait figé réel (tests/fixtures/logistique/) : 4 villes, avec leur
population OpenStreetMap (↑), leur distance routière OSRM à l'Agropolis de Meknès (↓) et leur
distance à vol d'oiseau (↓). Les poids des tests sont des saisies simulées pour le test.
"""

import json

import numpy as np
import pandas as pd
import pytest
from pymcdm.methods import TOPSIS
from pymcdm.normalizations import vector_normalization

from src.chemins import chemins_par_defaut
from src.decision.config import charger_config_decision
from src.decision.methodes import (
    ErreurMethode,
    ahp,
    correlations,
    monte_carlo_dirichlet,
    normaliser_min_max,
    poids_directs,
    rangs,
    renormaliser,
    somme_ponderee,
    topsis,
)
from src.logistique.distances import vol_oiseau_km

DEPOT = chemins_par_defaut()
LOGISTIQUE = DEPOT.racine / "tests" / "fixtures" / "logistique"
CONFIG = charger_config_decision(DEPOT)
HAUSSE = np.array([True, False, False])
POIDS = np.array([0.5, 0.3, 0.2])  # saisie simulée pour le test


def _matrice() -> np.ndarray:
    osrm = json.loads((LOGISTIQUE / "osrm_table.json").read_text(encoding="utf-8"))
    lieux = pd.read_csv(LOGISTIQUE / "lieux_osm.csv", sep=";")
    points = osrm["points"]
    lignes = []
    for i in (1, 2, 3, 4):
        lon, lat = points[i]
        lieu = lieux[
            (lieux["lon"].round(5) == round(lon, 5)) & (lieux["lat"].round(5) == round(lat, 5))
        ]
        oiseau = vol_oiseau_km(points[0][0], points[0][1], lon, lat, 6371.0088)
        lignes.append(
            [float(lieu["population"].iloc[0]), osrm["distances"][0][i] / 1000, float(oiseau)]
        )
    return np.array(lignes)


X = _matrice()


def test_normalisation_min_max_a_la_main() -> None:
    n = normaliser_min_max(X, HAUSSE)
    for i in range(4):
        assert n[i, 0] == pytest.approx((X[i, 0] - X[:, 0].min()) / (X[:, 0].max() - X[:, 0].min()))
        assert n[i, 1] == pytest.approx((X[:, 1].max() - X[i, 1]) / (X[:, 1].max() - X[:, 1].min()))
    assert n.min() == 0 and n.max() == 1
    constant = normaliser_min_max(np.ones((4, 1)), np.array([True]))
    assert (constant == 0).all()


def test_somme_ponderee_a_la_main() -> None:
    n = normaliser_min_max(X, HAUSSE)
    scores = somme_ponderee(n, POIDS)
    assert scores[2] == pytest.approx(0.5 * n[2, 0] + 0.3 * n[2, 1] + 0.2 * n[2, 2])


def test_topsis_egal_a_pymcdm() -> None:
    attendu = TOPSIS(normalization_function=vector_normalization)(X, POIDS, np.where(HAUSSE, 1, -1))
    assert topsis(X, POIDS, HAUSSE) == pytest.approx(attendu, abs=1e-6)


def test_ahp_exemple_de_saaty_et_coherence() -> None:
    matrice = np.array([[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]])
    resultat = ahp(matrice, CONFIG.indice_aleatoire)
    assert resultat.poids == pytest.approx([0.637, 0.258, 0.105], abs=1e-3)
    assert resultat.lambda_max == pytest.approx(3.039, abs=1e-3)
    assert resultat.cr == pytest.approx(0.033, abs=1e-3)
    incoherente = np.array([[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]])
    assert ahp(incoherente, CONFIG.indice_aleatoire).cr > 0.10
    with pytest.raises(ErreurMethode, match="réciproque"):
        ahp(np.array([[1, 2], [2, 1]]), CONFIG.indice_aleatoire)


def test_proprietes_des_poids_et_du_classement() -> None:
    assert poids_directs(np.array([2, 1, 1])).sum() == pytest.approx(1)
    n = normaliser_min_max(X, HAUSSE)
    base = rangs(somme_ponderee(n, POIDS))
    # Multiplier tous les poids par une constante ne change pas le classement.
    assert (rangs(somme_ponderee(n, POIDS * 7)) == base).all()
    assert (rangs(topsis(X, POIDS * 7, HAUSSE)) == rangs(topsis(X, POIDS, HAUSSE))).all()
    # Une alternative qui domine sur tous les critères est 1re pour toutes les méthodes.
    dominante = np.vstack([X, [X[:, 0].max() * 2, X[:, 1].min() / 2, X[:, 2].min() / 2]])
    assert rangs(somme_ponderee(normaliser_min_max(dominante, HAUSSE), POIDS))[-1] == 1
    assert rangs(topsis(dominante, POIDS, HAUSSE))[-1] == 1
    with pytest.raises(ErreurMethode):
        poids_directs(np.array([0, 0]))


def test_renormalisation_un_poids_a_la_fois() -> None:
    nouveau = renormaliser(POIDS, 0, 0.6)
    assert nouveau.sum() == pytest.approx(1) and nouveau[0] == pytest.approx(0.6)
    assert nouveau[1] / nouveau[2] == pytest.approx(POIDS[1] / POIDS[2])


def test_monte_carlo_reproductible_et_probabilites() -> None:
    n = normaliser_min_max(X, HAUSSE)

    def score(p: np.ndarray) -> np.ndarray:
        return somme_ponderee(n, p)

    p1, p3 = monte_carlo_dirichlet(score, POIDS, 50, 1000, 42, 3)
    q1, q3 = monte_carlo_dirichlet(score, POIDS, 50, 1000, 42, 3)
    assert (p1 == q1).all() and (p3 == q3).all()  # même graine, mêmes résultats (ENF-04)
    assert p1.sum() == pytest.approx(1) and p3.sum() == pytest.approx(3)


def test_correlations_pearson() -> None:
    r = correlations(X)
    assert r[1, 2] == pytest.approx(np.corrcoef(X[:, 1], X[:, 2])[0, 1])
    assert np.diag(r) == pytest.approx(1)
