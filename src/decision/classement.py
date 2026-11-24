"""Classement des sites (section 10, UC-DEC-01, 02, 04, 06, RG-09 à RG-12).

Étapes : filtres éliminatoires et seuils (RG-09), capacité atteignable (RG-10), sites exclus
par l'entreprise (PAR-57) ; puis, sur les sites restants, critères actifs calculables ; un
critère constant est neutralisé et son poids redistribué (section 11.2.3) ; normalisation,
score (somme pondérée ou TOPSIS), rang et contribution de chaque critère. Un critère actif
dont une valeur manque est retiré du calcul et listé avec son motif (RG-14) : il n'est jamais
compté zéro.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.decision.config import CatalogueCriteres
from src.decision.methodes import (
    ErreurMethode,
    correlations,
    monte_carlo_dirichlet,
    normaliser_min_max,
    poids_directs,
    rangs,
    renormaliser,
    somme_ponderee,
    topsis,
)

WSM, TOPSIS = "somme_ponderee", "topsis"


@dataclass(frozen=True)
class Seuil:
    """Seuil éliminatoire de l'utilisateur sur un critère (UC-DEC-01)."""

    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class Reglages:
    """Choix de l'utilisateur pour un classement."""

    actifs: list[str]
    poids: dict[str, float] = field(default_factory=dict)  # vide : poids par défaut (PAR-45)
    seuils: dict[str, Seuil] = field(default_factory=dict)
    methode: str = WSM
    filtre_capacite: bool = True  # RG-10
    exclus: list[str] = field(default_factory=list)  # PAR-57
    imposes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Classement:
    """Résultat : tableau classé, exclusions, critères retirés, avertissements, poids."""

    tableau: pd.DataFrame  # id_site, score, rang, contributions par critère
    exclus: pd.DataFrame  # id_site, motif
    retires: dict[str, str]  # critère → motif (non calculable, constant)
    avertissements: list[str]
    poids: dict[str, float]  # poids effectifs (somme 1)
    criteres: list[str]  # critères utilisés
    normalisee: pd.DataFrame
    brute: pd.DataFrame

    @property
    def criteres_actifs(self) -> int:
        """Nombre N de critères actifs hors filtres : utilisés et retirés."""
        return len(self.criteres) + len(self.retires)

    @property
    def partiel(self) -> bool:
        """Vrai si des critères actifs n'entrent pas dans le classement (décision du 23/11/2026)."""
        return bool(self.retires)


def poids_par_defaut(criteres: list[str], catalogue: CatalogueCriteres) -> dict[str, float]:
    """PAR-45 : égaux entre axes actifs, puis entre critères d'un même axe."""
    axes: dict[str, list[str]] = {}
    for code in criteres:
        axes.setdefault(catalogue.criteres[code].axe, []).append(code)
    return {code: 1 / len(axes) / len(membres) for membres in axes.values() for code in membres}


def classer(
    valeurs: pd.DataFrame,
    motifs: pd.DataFrame,
    atteignable: dict[str, bool | None],
    reglages: Reglages,
    catalogue: CatalogueCriteres,
    seuil_correlation: float,
    minimum_sites: int,
    minimum_criteres: int,
    exclure_incompletes: bool = False,
    nom_alternatives: str = "sites",
) -> Classement:
    """Classe les sites de ``valeurs`` (index id_site, une colonne par critère).

    Args:
        valeurs: valeur de chaque critère par site (NaN si manquante).
        motifs: motif de chaque valeur manquante.
        atteignable: RG-10, la capacité K est-elle atteignable sous le prix plafond (None :
            inconnu, le filtre n'est pas appliqué).
        reglages: critères actifs, poids, seuils, méthode, filtres.
        catalogue: ``config/criteres.yaml``.
        seuil_correlation: PAR-43.
        minimum_sites: nombre minimal de sites non exclus (section 11.2.3).
        minimum_criteres: nombre minimal de critères actifs calculables.
        exclure_incompletes: pour les gisements, une alternative à qui manque la valeur d'un
            critère calculé ailleurs est exclue et listée ; un critère n'est retiré que s'il
            manque partout. Pour les sites (défaut), le critère incomplet est retiré.
        nom_alternatives: « sites » ou « gisements », pour les messages.
    """
    exclusions: dict[str, str] = {}
    avertissements: list[str] = []
    for site in reglages.exclus:
        if site in valeurs.index:
            exclusions[site] = "site exclu par l'entreprise (PAR-57)"
    filtres = [c for c in reglages.actifs if catalogue.criteres[c].sens == "filtre"]
    for code in filtres:
        for site, valeur in valeurs[code].items():
            if valeur == 0 and site not in reglages.imposes:
                exclusions.setdefault(str(site), f"{code} : {motifs.at[site, code]}")
        if valeurs[code].isna().any():
            connus = motifs[code].dropna()
            motif = connus.iloc[0] if not connus.empty else "valeur manquante"
            avertissements.append(
                f"filtre {code} non appliqué à {int(valeurs[code].isna().sum())} sites : {motif}"
            )
    for code, seuil in reglages.seuils.items():
        if code not in valeurs.columns:
            continue
        for site, valeur in valeurs[code].items():
            if pd.isna(valeur) or site in reglages.imposes:
                continue
            if seuil.minimum is not None and valeur < seuil.minimum:
                exclusions.setdefault(str(site), f"{code} sous le seuil {seuil.minimum:g}")
            if seuil.maximum is not None and valeur > seuil.maximum:
                exclusions.setdefault(str(site), f"{code} au-dessus du seuil {seuil.maximum:g}")
    if reglages.filtre_capacite:
        inconnus = 0
        for site, ok in atteignable.items():
            if ok is False and site not in reglages.imposes:
                exclusions.setdefault(
                    site, "capacité K non atteignable sous le prix plafond (RG-10)"
                )
            inconnus += ok is None
        if inconnus:
            avertissements.append(
                f"RG-10 non appliquée à {inconnus} sites : bassin d'approvisionnement non calculé"
            )
    restants = [s for s in valeurs.index if s not in exclusions]
    if len(restants) < minimum_sites:
        raise ErreurMethode(
            f"moins de {minimum_sites} {nom_alternatives} non exclus : assouplissez les filtres"
        )
    retires: dict[str, str] = {}
    criteres = []
    if exclure_incompletes:
        gardes = []
        for code in reglages.actifs:
            if catalogue.criteres[code].sens == "filtre":
                continue
            colonne = valeurs.loc[restants, code]
            if colonne.isna().all():
                manquant = motifs.loc[restants, code].dropna()
                retires[code] = (
                    f"non calculable pour les {len(restants)} {nom_alternatives} : "
                    f"{manquant.iloc[0] if not manquant.empty else 'valeur manquante'}"
                )
            else:
                gardes.append(code)
        for alternative in list(restants):
            for code in gardes:
                if pd.isna(valeurs.at[alternative, code]):
                    motif = motifs.at[alternative, code] or "valeur manquante"
                    exclusions[str(alternative)] = f"{code} manquant : {motif}"
                    break
        restants = [s for s in restants if s not in exclusions]
        if len(restants) < minimum_sites:
            raise ErreurMethode(
                f"moins de {minimum_sites} {nom_alternatives} ont toutes les valeurs des critères "
                "calculés : complétez les valeurs manquantes ou désactivez des critères"
            )
    for code in reglages.actifs:
        if catalogue.criteres[code].sens == "filtre" or code in retires:
            continue
        colonne = valeurs.loc[restants, code]
        if colonne.isna().any():
            manquant = motifs.loc[restants, code].dropna()
            retires[code] = (
                f"non calculable pour {int(colonne.isna().sum())} sites : "
                f"{manquant.iloc[0] if not manquant.empty else 'valeur manquante'}"
            )
        elif colonne.nunique() <= 1:
            retires[code] = (
                f"même valeur pour tous les {nom_alternatives} : neutralisé, poids redistribué"
            )
            avertissements.append(
                f"{code} neutralisé (même valeur pour tous les {nom_alternatives})"
            )
        else:
            criteres.append(code)
    if len(criteres) < minimum_criteres:
        raise ErreurMethode(
            "moins de 2 critères actifs calculables : complétez les valeurs manquantes ou "
            "activez d'autres critères"
        )
    if reglages.poids:
        brut = np.array([reglages.poids.get(c, 0.0) for c in criteres])
        poids = poids_directs(brut if brut.sum() > 0 else np.ones(len(criteres)))
    else:
        defaut = poids_par_defaut(criteres, catalogue)
        poids = poids_directs(np.array([defaut[c] for c in criteres]))
    x = valeurs.loc[restants, criteres].to_numpy(dtype=float)
    hausse = np.array([catalogue.criteres[c].sens == "hausse" for c in criteres])
    normalisee = normaliser_min_max(x, hausse)
    if reglages.methode == TOPSIS:
        scores = topsis(x, poids, hausse)
    else:
        scores = somme_ponderee(normalisee, poids)
    r = correlations(x)
    for i, a in enumerate(criteres):
        for j in range(i + 1, len(criteres)):
            if abs(r[i, j]) > seuil_correlation:
                avertissements.append(
                    f"{a} et {criteres[j]} sont fortement corrélés (r = {r[i, j]:.2f}, RG-11)"
                )
    tableau = pd.DataFrame({"id_site": restants, "score": scores, "rang": rangs(scores)})
    for k, code in enumerate(criteres):
        tableau[f"contribution_{code}"] = normalisee[:, k] * poids[k]
    return Classement(
        tableau=tableau.sort_values("rang").reset_index(drop=True),
        exclus=pd.DataFrame(
            {"id_site": list(exclusions), "motif": list(exclusions.values())},
            columns=["id_site", "motif"],
        ),
        retires=retires,
        avertissements=avertissements,
        poids=dict(zip(criteres, poids.tolist(), strict=True)),
        criteres=criteres,
        normalisee=pd.DataFrame(normalisee, index=restants, columns=criteres),
        brute=pd.DataFrame(x, index=restants, columns=criteres),
    )


def _scoreur(c: Classement, catalogue: CatalogueCriteres, methode: str):  # noqa: ANN202
    x = c.brute.to_numpy()
    n = c.normalisee.to_numpy()
    hausse = np.array([catalogue.criteres[k].sens == "hausse" for k in c.criteres])
    if methode == TOPSIS:
        return lambda p: topsis(x, p, hausse)
    return lambda p: somme_ponderee(n, p)


@dataclass(frozen=True)
class Robustesse:
    """Sensibilité « un poids à la fois », probabilités Monte Carlo et libellé RG-12."""

    un_poids: pd.DataFrame  # critere, variation, premier
    seuils_changement: dict[str, float | None]  # critère → variation où le 1er change
    proba_premier: dict[str, float]
    proba_tete: dict[str, float]
    rangs_wsm: dict[str, int]
    rangs_topsis: dict[str, int]
    robustes: list[str]


def robustesse(
    c: Classement,
    catalogue: CatalogueCriteres,
    methode: str,
    variations: np.ndarray,
    concentration: float,
    tirages: int,
    graine: int,
    tete: int,
    seuil_premier: float,
) -> Robustesse:
    """Analyse de robustesse du classement (section 10.4, RG-12).

    Args:
        c: classement de référence.
        catalogue: ``config/criteres.yaml``.
        methode: méthode du classement de référence.
        variations: variations relatives des poids (−50 % à +50 % par pas de 10 %).
        concentration: PAR-41 ; tirages : PAR-03 ; graine : PAR-04.
        tirages: nombre de tirages de Monte Carlo.
        graine: graine aléatoire.
        tete: taille du trio de tête (RG-12).
        seuil_premier: PAR-42, fraction des tirages où le site doit être 1er.
    """
    sites = list(c.normalisee.index)
    poids = np.array([c.poids[k] for k in c.criteres])
    score = _scoreur(c, catalogue, methode)
    premier_ref = sites[int(np.argmin(rangs(score(poids))))]
    lignes, seuils = [], {}
    for i, code in enumerate(c.criteres):
        seuil = None
        for v in variations:
            nouveau = min(max(poids[i] * (1 + v), 0.0), 1.0)
            premier = sites[int(np.argmin(rangs(score(renormaliser(poids, i, nouveau)))))]
            lignes.append({"critere": code, "variation": float(v), "premier": premier})
            if premier != premier_ref and (seuil is None or abs(v) < abs(seuil)):
                seuil = float(v)
        seuils[code] = seuil
    p1, p3 = monte_carlo_dirichlet(score, poids, concentration, tirages, graine, tete)
    rangs_wsm = dict(zip(sites, rangs(_scoreur(c, catalogue, WSM)(poids)).tolist(), strict=True))
    rangs_topsis = dict(
        zip(sites, rangs(_scoreur(c, catalogue, TOPSIS)(poids)).tolist(), strict=True)
    )
    robustes = [
        s
        for k, s in enumerate(sites)
        if p1[k] >= seuil_premier and rangs_wsm[s] <= tete and rangs_topsis[s] <= tete
    ]
    return Robustesse(
        un_poids=pd.DataFrame(lignes, columns=["critere", "variation", "premier"]),
        seuils_changement=seuils,
        proba_premier=dict(zip(sites, p1.tolist(), strict=True)),
        proba_tete=dict(zip(sites, p3.tolist(), strict=True)),
        rangs_wsm=rangs_wsm,
        rangs_topsis=rangs_topsis,
        robustes=robustes,
    )
