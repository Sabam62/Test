"""Valeur de chaque critère P1 pour chaque site candidat (section 9, RG-08).

Un critère de gisement est porté au site par la moyenne de ses couples pondérée par le
tonnage retenu dans le bassin pour atteindre K (courbe d'approvisionnement du module M2). Une
valeur qui ne peut pas être calculée porte son motif (RG-14) ; elle n'est jamais remplacée par
zéro. Ajouter un critère = une entrée de ``config/criteres.yaml`` et une fonction enregistrée
ici avec :func:`critere` (ENF-11).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.data.provenance import ValeurACompleter, ValeurSourcee
from src.data.tables_reference import TableLongue
from src.logistique.couts import Blocage, Courbe


@dataclass(frozen=True)
class Valeur:
    """Valeur d'un critère pour un site, ou motif de son absence."""

    valeur: float | None
    motif: str | None = None


@dataclass
class ContexteIndicateurs:
    """Entrées communes : sites, courbes, bilans, propriétés des résidus, indicateurs spatiaux."""

    sites: pd.DataFrame
    courbes: dict[str, Courbe | str]  # site → courbe ou motif
    bilans: pd.DataFrame  # table « bilans » de tous les couples × sites (module M3)
    residus: TableLongue
    concurrence: TableLongue
    national: str
    calendrier: pd.DataFrame
    mois: list[str]
    lire: Callable[[str], ValeurSourcee]
    parametres: dict[str, str]
    spatial: dict[str, dict[str, float]]  # critère → site → valeur
    tonnages_rayon: dict[str, float | None]
    gisements: pd.DataFrame
    pourcentage: float
    densites: pd.DataFrame = field(default_factory=pd.DataFrame)


Calcul = Callable[[ContexteIndicateurs, str], Valeur]
CALCULS: dict[str, Calcul] = {}


def critere(nom: str) -> Callable[[Calcul], Calcul]:
    """Enregistre la fonction de calcul d'un critère sous le nom de ``config/criteres.yaml``."""

    def enregistrer(fonction: Calcul) -> Calcul:
        CALCULS[nom] = fonction
        return fonction

    return enregistrer


def _retenus(ctx: ContexteIndicateurs, site: str) -> pd.DataFrame | str:
    courbe = ctx.courbes.get(site)
    if courbe is None:
        return "bassin d'approvisionnement non calculé"
    if isinstance(courbe, str):
        return courbe
    if courbe.retenus.empty:
        return "aucun gisement retenu sous le prix plafond"
    return courbe.retenus


def _moyenne_ponderee(
    ctx: ContexteIndicateurs, site: str, valeur: Callable[[pd.Series], float | str]
) -> Valeur:
    """Moyenne des couples retenus pondérée par leur tonnage retenu (RG-08)."""
    retenus = _retenus(ctx, site)
    if isinstance(retenus, str):
        return Valeur(None, retenus)
    total, somme = 0.0, 0.0
    for _, ligne in retenus.iterrows():
        v = valeur(ligne)
        if isinstance(v, str):
            return Valeur(None, v)
        somme += v * ligne["tonnage_retenu"]
        total += ligne["tonnage_retenu"]
    return Valeur(somme / total if total else None, None if total else "tonnage retenu nul")


def _propriete(
    ctx: ContexteIndicateurs, residu: str, parametre: str, facteur: float = 1
) -> float | str:
    try:
        precisions = ctx.residus.precisions(residu, parametre)
        precision = "" if "" in precisions or len(precisions) != 1 else precisions[0]
        return float(ctx.residus.valeur(residu, parametre, precision).lire_nombre()) * facteur
    except (ValeurACompleter, KeyError, TypeError) as erreur:
        return f"{residu} · {parametre} à compléter ({erreur})"


def _parametre(ctx: ContexteIndicateurs, cle: str) -> float | str:
    identifiant = ctx.parametres[cle]
    try:
        return float(ctx.lire(identifiant).lire_nombre())
    except (ValeurACompleter, TypeError):
        return f"{identifiant} à renseigner dans Paramètres"


def _bilan(ctx: ContexteIndicateurs, site: str, province: str, residu: str) -> pd.Series | str:
    b = ctx.bilans
    choix = b[
        (b["id_site"] == site) & (b["code_province"] == province) & (b["code_residu"] == residu)
    ]
    if choix.empty or pd.isna(choix["BN"].iloc[0]):
        motif = choix["motif"].iloc[0].split(" | ")[0] if not choix.empty else "bilan absent"
        return f"bilan climat non calculé : {motif}"
    return choix.iloc[0]


@critere("tonnage_bassin")
def _a1(ctx: ContexteIndicateurs, site: str) -> Valeur:
    retenus = _retenus(ctx, site)
    if isinstance(retenus, str):
        return Valeur(None, retenus)
    courbe = ctx.courbes[site]
    return Valeur(courbe.tonnage_sous_plafond)  # type: ignore[union-attr]


@critere("densite_gisement")
def _a2(ctx: ContexteIndicateurs, site: str) -> Valeur:
    return Valeur(None, "critère de gisement (niveau G) : non porté au site")


@critere("part_libre")
def _a3(ctx: ContexteIndicateurs, site: str) -> Valeur:
    def part(ligne: pd.Series) -> float | str:
        for cle in (
            (ligne["code_province"], ligne["code_residu"]),
            (ctx.national, ligne["code_residu"]),
        ):
            try:
                valeur = ctx.concurrence.valeur(cle, "part_utilisee")
            except KeyError:
                continue
            if valeur.valeur is None:
                continue
            return (1 - float(valeur.valeur)) * ctx.pourcentage
        return f"{ligne['code_residu']} · part_utilisee à compléter"

    return _moyenne_ponderee(ctx, site, part)


@critere("regularite_saisonniere")
def _a4(ctx: ContexteIndicateurs, site: str) -> Valeur:
    retenus = _retenus(ctx, site)
    if isinstance(retenus, str):
        return Valeur(None, retenus)
    capacite = _parametre(ctx, "capacite")
    if isinstance(capacite, str):
        return Valeur(None, capacite)
    calendrier = ctx.calendrier.set_index("code_residu") if not ctx.calendrier.empty else None
    mensuel = np.zeros(len(ctx.mois))
    for _, ligne in retenus.iterrows():
        if calendrier is None or ligne["code_residu"] not in calendrier.index:
            return Valeur(
                None, f"{ligne['code_residu']} : profil mensuel à compléter (calendrier.csv)"
            )
        profil = calendrier.loc[ligne["code_residu"], ctx.mois].astype(float).to_numpy()
        mensuel += ligne["tonnage_retenu"] * profil
    return Valeur(float((mensuel >= capacite / len(ctx.mois)).sum()))


@critere("teneur_carbone")
def _b1(ctx: ContexteIndicateurs, site: str) -> Valeur:
    return _moyenne_ponderee(
        ctx, site, lambda ligne: _propriete(ctx, ligne["code_residu"], "carbone")
    )


@critere("taux_cendres")
def _b2(ctx: ContexteIndicateurs, site: str) -> Valeur:
    return _moyenne_ponderee(
        ctx, site, lambda ligne: _propriete(ctx, ligne["code_residu"], "cendres")
    )


@critere("humidite")
def _b3(ctx: ContexteIndicateurs, site: str) -> Valeur:
    return _moyenne_ponderee(
        ctx, site, lambda ligne: _propriete(ctx, ligne["code_residu"], "humidite")
    )


@critere("rendement_biochar")
def _b4(ctx: ContexteIndicateurs, site: str) -> Valeur:
    return _moyenne_ponderee(
        ctx, site, lambda ligne: _propriete(ctx, ligne["code_residu"], "rendement_pyrolyse")
    )


@critere("eligibilite_ebc")
def _b5(ctx: ContexteIndicateurs, site: str) -> Valeur:
    """1 si tous les résidus retenus sont sur la liste positive EBC, 0 sinon (filtre)."""
    retenus = _retenus(ctx, site)
    if isinstance(retenus, str):
        return Valeur(None, retenus)
    for residu in retenus["code_residu"].unique():
        valeur = ctx.residus.valeur(residu, "eligible_ebc").valeur
        if valeur is None:
            return Valeur(None, f"{residu} · eligible_ebc à compléter (liste positive EBC, SRC-14)")
        if str(valeur) != "oui":
            return Valeur(0.0, f"{residu} absent de la liste positive EBC")
    return Valeur(1.0)


@critere("cout_livre")
def _c1(ctx: ContexteIndicateurs, site: str) -> Valeur:
    retenus = _retenus(ctx, site)
    if isinstance(retenus, str):
        return Valeur(None, retenus)
    courbe = ctx.courbes[site]
    if courbe.cout_moyen_k is None:  # type: ignore[union-attr]
        return Valeur(None, "capacité K non atteignable sous le prix plafond")
    return Valeur(courbe.cout_moyen_k)  # type: ignore[union-attr]


@critere("distance_moyenne")
def _c2(ctx: ContexteIndicateurs, site: str) -> Valeur:
    return _moyenne_ponderee(ctx, site, lambda ligne: float(ligne["distance_km"]))


@critere("tonnage_rayon")
def _c3(ctx: ContexteIndicateurs, site: str) -> Valeur:
    valeur = ctx.tonnages_rayon.get(site)
    return Valeur(valeur, None if valeur is not None else "gisement mobilisable M non calculé")


@critere("marge")
def _c6(ctx: ContexteIndicateurs, site: str) -> Valeur:
    prix_bc, prix_credit = _parametre(ctx, "prix_biochar"), _parametre(ctx, "prix_credit")
    for p in (prix_bc, prix_credit):
        if isinstance(p, str):
            return Valeur(None, p)

    def marge(ligne: pd.Series) -> float | str:
        y = _propriete(ctx, ligne["code_residu"], "rendement_pyrolyse")
        bilan = _bilan(ctx, site, ligne["code_province"], ligne["code_residu"])
        if isinstance(y, str):
            return y
        if isinstance(bilan, str):
            return bilan
        recettes = prix_bc * y + prix_credit * float(bilan["BN"]) * y  # type: ignore[operator]
        return recettes - float(ligne["cout_livre"])

    return _moyenne_ponderee(ctx, site, marge)


@critere("bilan_net")
def _d1(ctx: ContexteIndicateurs, site: str) -> Valeur:
    def bn(ligne: pd.Series) -> float | str:
        bilan = _bilan(ctx, site, ligne["code_province"], ligne["code_residu"])
        return bilan if isinstance(bilan, str) else float(bilan["BN"])

    return _moyenne_ponderee(ctx, site, bn)


@critere("part_transport")
def _d2(ctx: ContexteIndicateurs, site: str) -> Valeur:
    def part(ligne: pd.Series) -> float | str:
        bilan = _bilan(ctx, site, ligne["code_province"], ligne["code_residu"])
        if isinstance(bilan, str):
            return bilan
        total = sum(float(bilan[t]) for t in ("E_col", "E_pre", "E_tr", "E_pyr", "E_ep"))
        return float(bilan["E_tr"]) / total * ctx.pourcentage if total else "émissions nulles"

    return _moyenne_ponderee(ctx, site, part)


def _spatial(nom: str) -> Calcul:
    def calcul(ctx: ContexteIndicateurs, site: str) -> Valeur:
        valeurs = ctx.spatial.get(nom)
        if valeurs is None:
            return Valeur(None, f"{nom} : données spatiales absentes (python -m scripts.prepare)")
        valeur = valeurs.get(site)
        return Valeur(valeur, None if valeur is not None else "site hors des données")

    return calcul


for _nom in ("surface_agricole", "distance_route", "distance_zone", "population_rurale"):
    CALCULS[_nom] = _spatial(_nom)


def matrice_criteres(
    ctx: ContexteIndicateurs, calculs_par_critere: dict[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Valeurs (sites × critères) et motifs des valeurs manquantes."""
    valeurs, motifs = {}, {}
    for code, calcul in calculs_par_critere.items():
        fonction = CALCULS.get(calcul)
        if fonction is None:
            raise Blocage(f"critère {code} : fonction « {calcul} » non enregistrée")
        resultats = {s: fonction(ctx, s) for s in ctx.sites["id_site"]}
        valeurs[code] = {s: r.valeur for s, r in resultats.items()}
        motifs[code] = {s: r.motif for s, r in resultats.items()}
    index = ctx.sites["id_site"]
    return (
        pd.DataFrame(valeurs, index=index, dtype=float),
        pd.DataFrame(motifs, index=index, dtype=object),
    )
