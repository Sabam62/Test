"""Méthodes multicritères codées avec NumPy (section 10.5).

Normalisation, pondération directe et AHP, somme pondérée, TOPSIS, sensibilité, Monte Carlo sur
les poids, corrélations.

Toutes les fonctions sont pures : une matrice ``x`` a une ligne par alternative et une colonne
par critère ; ``hausse`` vaut True pour un critère « plus c'est élevé, mieux c'est ».
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


class ErreurMethode(Exception):
    """Calcul multicritère impossible ; message en français."""


def normaliser_min_max(x: np.ndarray, hausse: np.ndarray) -> np.ndarray:
    """Min-max de la section 10.1 ; un critère constant vaut 0 (il est neutralisé à part)."""
    x = np.asarray(x, dtype=float)
    minimum, maximum = x.min(axis=0), x.max(axis=0)
    etendue = maximum - minimum
    sur = np.where(etendue > 0, etendue, 1)
    montee = (x - minimum) / sur
    descente = (maximum - x) / sur
    resultat = np.where(hausse, montee, descente)
    return np.where(etendue > 0, resultat, 0.0)


def poids_directs(curseurs: np.ndarray) -> np.ndarray:
    """Poids des curseurs ramenés à une somme de 1 (section 10.2)."""
    curseurs = np.asarray(curseurs, dtype=float)
    if (curseurs < 0).any():
        raise ErreurMethode("un poids ne peut pas être négatif")
    total = curseurs.sum()
    if total <= 0:
        raise ErreurMethode("au moins un poids doit être positif")
    return curseurs / total


@dataclass(frozen=True)
class ResultatAhp:
    """Poids AHP (vecteur propre principal) et cohérence de la matrice."""

    poids: np.ndarray
    lambda_max: float
    ci: float
    cr: float | None


def ahp(matrice: np.ndarray, indice_aleatoire: dict[int, float]) -> ResultatAhp:
    """Poids AHP d'une matrice de comparaisons par paires (échelle de Saaty, 1 à 9).

    CI = (λmax − n) / (n − 1) ; CR = CI / RI(n). CR vaut None pour n ≤ 2 (RI nul).
    """
    a = np.asarray(matrice, dtype=float)
    n = a.shape[0]
    if a.shape != (n, n) or (a <= 0).any():
        raise ErreurMethode("la matrice AHP doit être carrée, à valeurs positives")
    if not np.allclose(a * a.T, 1):
        raise ErreurMethode("la matrice AHP doit être réciproque : a(j, i) = 1 / a(i, j)")
    valeurs, vecteurs = np.linalg.eig(a)
    rang = int(np.argmax(valeurs.real))
    lambda_max = float(valeurs[rang].real)
    poids = np.abs(vecteurs[:, rang].real)
    poids = poids / poids.sum()
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    ri = indice_aleatoire.get(n)
    if ri is None:
        raise ErreurMethode(f"indice aléatoire de Saaty inconnu pour {n} éléments")
    cr = ci / ri if ri > 0 else None
    return ResultatAhp(poids, lambda_max, ci, cr)


def somme_ponderee(normalisee: np.ndarray, poids: np.ndarray) -> np.ndarray:
    """Score WSM : somme des valeurs normalisées × poids (section 10.3)."""
    return np.asarray(normalisee, dtype=float) @ np.asarray(poids, dtype=float)


def topsis(x: np.ndarray, poids: np.ndarray, hausse: np.ndarray) -> np.ndarray:
    """Score TOPSIS S = D⁻ / (D⁺ + D⁻), normalisation vectorielle (section 10.3)."""
    x = np.asarray(x, dtype=float)
    normes = np.sqrt(np.square(x).sum(axis=0))
    v = x / np.where(normes > 0, normes, 1) * np.asarray(poids, dtype=float)
    ideal = np.where(hausse, v.max(axis=0), v.min(axis=0))
    anti = np.where(hausse, v.min(axis=0), v.max(axis=0))
    d_plus = np.sqrt(np.square(v - ideal).sum(axis=1))
    d_moins = np.sqrt(np.square(v - anti).sum(axis=1))
    total = d_plus + d_moins
    return np.where(total > 0, d_moins / np.where(total > 0, total, 1), 0.0)


def rangs(scores: np.ndarray) -> np.ndarray:
    """Rang de chaque alternative (1 = meilleur score) ; ex æquo départagés par l'ordre."""
    ordre = np.argsort(-np.asarray(scores, dtype=float), kind="stable")
    resultat = np.empty(len(ordre), dtype=int)
    resultat[ordre] = np.arange(1, len(ordre) + 1)
    return resultat


def renormaliser(poids: np.ndarray, indice: int, nouveau: float) -> np.ndarray:
    """Fixe le poids ``indice`` à ``nouveau`` et répartit le reste au prorata des autres."""
    poids = np.asarray(poids, dtype=float)
    autres = poids.sum() - poids[indice]
    resultat = poids * ((1 - nouveau) / autres) if autres > 0 else np.zeros_like(poids)
    resultat[indice] = nouveau
    return resultat


def monte_carlo_dirichlet(
    score: Callable[[np.ndarray], np.ndarray],
    poids: np.ndarray,
    concentration: float,
    tirages: int,
    graine: int,
    tete: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Probabilités d'être 1er et dans les ``tete`` premiers (section 10.4).

    Les jeux de poids suivent une loi de Dirichlet de paramètre concentration × poids,
    centrée sur les poids choisis ; la graine rend les tirages reproductibles (ENF-04).
    """
    generateur = np.random.default_rng(graine)
    alpha = np.maximum(np.asarray(poids, dtype=float) * concentration, np.finfo(float).tiny)
    jeux = generateur.dirichlet(alpha, size=tirages)
    premiers, tetes = None, None
    for jeu in jeux:
        r = rangs(score(jeu))
        premiers = (r == 1).astype(float) if premiers is None else premiers + (r == 1)
        tetes = (r <= tete).astype(float) if tetes is None else tetes + (r <= tete)
    return premiers / tirages, tetes / tirages


def correlations(x: np.ndarray) -> np.ndarray:
    """Matrice des coefficients de Pearson entre critères (RG-11) ; constant → 0."""
    x = np.asarray(x, dtype=float)
    centre = x - x.mean(axis=0)
    ecart = np.sqrt(np.square(centre).sum(axis=0))
    produit = centre.T @ centre
    denominateur = np.outer(ecart, ecart)
    return np.where(denominateur > 0, produit / np.where(denominateur > 0, denominateur, 1), 0.0)
