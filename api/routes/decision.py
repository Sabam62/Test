"""Décision et mélange (UC-DEC-01, 02, 04, 06, UC-MIX-01, RG-09 à RG-12, RG-15, RG-16).

La matrice des critères (sites × critères) est mise en cache avec la clé du bilan climat : un
changement de poids ne recalcule que le classement (moins de 2 s, UC-DEC-04) ; un changement
d'un paramètre de l'entreprise (prix plafond, capacité…) change la clé et recalcule tout.
"""

import hashlib
from threading import Lock
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependances import charger_config_api, obtenir_chemins
from api.routes.acv import AcvDep
from api.routes.logistique import LogistiqueDep, cle_logistique
from api.routes.potentiel import CalculDep
from api.serialisation import lignes
from src.chemins import Chemins
from src.decision.calcul import (
    DonneesDecision,
    actifs_par_defaut,
    empreinte,
    preparer_criteres,
    variations_de_rang,
)
from src.decision.classement import Classement, classer, robustesse
from src.decision.config import charger_catalogue_criteres, charger_config_decision
from src.decision.gisements import SEPARATEUR as SEPARATEUR_COUPLE
from src.decision.gisements import matrice_gisements
from src.decision.methodes import ErreurMethode, ahp
from src.decision.reglages import (
    ErreurReglages,
    ReglagesUtilisateur,
    enregistrer_reglages,
    lire_reglages,
    reglages_de_calcul,
)
from src.logistique.couts import Blocage
from src.melange.entrees import couples_du_bassin
from src.melange.programme import Contraintes, melange_optimal
from src.scenarios.config import charger_entreprise
from src.scenarios.demo import bandeau_demo

routeur = APIRouter(tags=["décision"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
_cache: dict[str, tuple[DonneesDecision, object]] = {}
_verrou = Lock()


def _empreinte_fichiers(chemins: Chemins) -> str:
    morceaux = []
    for nom in ("criteres.yaml", "decision.yaml"):
        fichier = chemins.config / nom
        morceaux.append(
            hashlib.sha256(fichier.read_bytes()).hexdigest() if fichier.is_file() else ""
        )
    return "|".join(morceaux)


def donnees_decision(
    chemins: CheminsDep, calcul: CalculDep, logistique: LogistiqueDep, acv: AcvDep
) -> DonneesDecision:
    """Matrice des critères, depuis le cache si les entrées n'ont pas changé."""
    cle = hashlib.sha256(
        f"{cle_logistique(chemins)}|{_empreinte_fichiers(chemins)}".encode()
    ).hexdigest()
    with _verrou:
        if cle not in _cache:
            bilans = acv.bilans(logistique.matrice.distances)
            donnees = preparer_criteres(
                chemins, logistique, bilans, calcul.entrees.tables.calendrier
            )
            _cache.clear()
            _cache[cle] = (donnees, bilans)
        return _cache[cle][0]  # type: ignore[return-value]


def _bilans_en_cache() -> object:
    return next(iter(_cache.values()))[1] if _cache else None


DonneesDep = Annotated[DonneesDecision, Depends(donnees_decision)]


def _entreprise(chemins: Chemins) -> tuple[dict[str, object], list[str], list[str], list[str]]:
    entreprise = charger_entreprise(chemins)
    valeurs = {i: p.valeur for i, p in entreprise.parametres.items()}
    sites = valeurs.get("PAR-57") or {}
    exclus = list(sites.get("exclus", [])) if isinstance(sites, dict) else []
    imposes = list(sites.get("imposes", [])) if isinstance(sites, dict) else []
    return valeurs, entreprise.a_renseigner, exclus, imposes


def _reglages(chemins: Chemins, donnees: DonneesDecision, methode: str | None):  # noqa: ANN202
    valeurs, _, exclus, imposes = _entreprise(chemins)
    renseignes = {i for i, v in valeurs.items() if v is not None}
    utilisateur = lire_reglages(chemins)
    defaut_methode = str(
        _lire_technique(chemins, donnees.config.parametres.methode) or "somme_ponderee"
    )
    reglages = reglages_de_calcul(
        utilisateur,
        actifs_par_defaut(donnees.catalogue, renseignes),
        defaut_methode,
        exclus,
        imposes,
    )
    if methode is not None:
        if methode not in donnees.config.methodes:
            raise HTTPException(400, f"méthode « {methode} » inconnue")
        reglages = reglages.__class__(**{**reglages.__dict__, "methode": methode})
    return reglages, utilisateur


def _lire_technique(chemins: Chemins, identifiant: str) -> object:
    from src.scenarios.parametres import valeur_courante

    return valeur_courante(chemins, identifiant).valeur


def _classer(chemins: Chemins, donnees: DonneesDecision, methode: str | None) -> Classement:
    reglages, _ = _reglages(chemins, donnees, methode)
    try:
        return classer(
            donnees.valeurs,
            donnees.motifs,
            donnees.atteignable,
            reglages,
            donnees.catalogue,
            float(_lire_technique(chemins, donnees.config.parametres.seuil_correlation)),
            donnees.config.minimum_sites,
            donnees.config.minimum_criteres,
        )
    except ErreurMethode as erreur:
        raise HTTPException(409, str(erreur)) from None


@routeur.get("/decision/criteres")
def criteres(chemins: CheminsDep, donnees: DonneesDep) -> dict[str, object]:
    """Catalogue des 29 critères, réglages courants et valeurs de chaque site (UC-DEC-01)."""
    reglages, utilisateur = _reglages(chemins, donnees, None)
    catalogue = donnees.catalogue
    noms = dict(zip(donnees.sites["id_site"], donnees.sites["nom"], strict=True))
    valeurs = []
    for site in donnees.valeurs.index:
        valeurs.append(
            {
                "id_site": site,
                "nom": noms.get(site, site),
                "valeurs": {
                    c: (None if np.isnan(v) else float(v))
                    for c, v in donnees.valeurs.loc[site].items()
                },
                "motifs": {c: m for c, m in donnees.motifs.loc[site].items() if m},
            }
        )
    return {
        "axes": catalogue.axes,
        "criteres": [
            {
                "code": code,
                **c.model_dump(),
                "calculable": bool(donnees.valeurs.get(code, np.nan).notna().any())
                if code in donnees.valeurs
                else False,
            }
            for code, c in catalogue.criteres.items()
        ],
        "actifs": reglages.actifs,
        "poids": reglages.poids,
        "seuils": {
            c: {"minimum": s.minimum, "maximum": s.maximum} for c, s in reglages.seuils.items()
        },
        "methode": reglages.methode,
        "methodes": donnees.config.methodes,
        "filtre_capacite": reglages.filtre_capacite,
        "personnalises": utilisateur.actifs is not None or bool(utilisateur.poids),
        "sites": valeurs,
    }


@routeur.put("/decision/reglages")
def regler(corps: ReglagesUtilisateur, chemins: CheminsDep) -> dict[str, object]:
    """Enregistre critères actifs, poids, seuils, méthode et filtre de capacité."""
    try:
        enregistrer_reglages(
            chemins, corps, charger_catalogue_criteres(chemins), charger_config_decision(chemins)
        )
    except ErreurReglages as erreur:
        raise HTTPException(400, str(erreur)) from None
    return corps.model_dump(mode="json")


@routeur.delete("/decision/reglages")
def reinitialiser(chemins: CheminsDep) -> dict[str, str]:
    """Revient aux critères et poids par défaut (section 9, PAR-45)."""
    fichier = chemins.config / "decision.local.yaml"
    if fichier.is_file():
        fichier.unlink()
    return {"reglages": "par défaut"}


class MatriceAhp(BaseModel):
    """Comparaisons par paires (échelle de Saaty) d'une liste d'éléments."""

    codes: list[str] = Field(min_length=1)
    matrice: list[list[float]]


class DemandeAhp(BaseModel):
    """AHP hiérarchique : axes, puis critères de chaque axe (section 10.2)."""

    axes: MatriceAhp
    criteres: dict[str, MatriceAhp] = {}


@routeur.post("/decision/ahp")
def poids_ahp(corps: DemandeAhp, chemins: CheminsDep) -> dict[str, object]:
    """Poids AHP : poids de l'axe × poids du critère dans l'axe ; CR de chaque matrice."""
    config = charger_config_decision(chemins)
    cr_max = float(_lire_technique(chemins, config.parametres.cr_maximal))
    try:
        axes = ahp(np.array(corps.axes.matrice), config.indice_aleatoire)
        resultats = {
            "axes": {
                "poids": dict(zip(corps.axes.codes, axes.poids.tolist(), strict=True)),
                "cr": axes.cr,
            }
        }
        poids: dict[str, float] = {}
        for k, axe in enumerate(corps.axes.codes):
            m = corps.criteres.get(axe)
            if m is None:
                continue
            r = ahp(np.array(m.matrice), config.indice_aleatoire)
            resultats[axe] = {
                "poids": dict(zip(m.codes, r.poids.tolist(), strict=True)),
                "cr": r.cr,
            }
            for code, p in zip(m.codes, r.poids, strict=True):
                poids[code] = float(axes.poids[k] * p)
    except ErreurMethode as erreur:
        raise HTTPException(400, str(erreur)) from None
    avertissements = [
        f"{nom} : ratio de cohérence {r['cr']:.2f} supérieur à {cr_max:.2f} (PAR-44), "
        "revoyez les comparaisons"
        for nom, r in resultats.items()
        if r["cr"] is not None and r["cr"] > cr_max
    ]
    return {
        "poids": poids,
        "matrices": resultats,
        "cr_maximal": cr_max,
        "avertissements": avertissements,
    }


@routeur.get("/decision/classement")
def classement(
    chemins: CheminsDep, donnees: DonneesDep, methode: str | None = None
) -> dict[str, object]:
    """Sites classés avec score, rang, contributions, exclusions et variation de rang."""
    valeurs, a_renseigner, _, _ = _entreprise(chemins)
    if a_renseigner:
        return {"bloque": True, "a_renseigner": a_renseigner}
    c = _classer(chemins, donnees, methode)
    noms = dict(zip(donnees.sites["id_site"], donnees.sites["nom"], strict=True))
    types = dict(zip(donnees.sites["id_site"], donnees.sites["type"], strict=True))
    rangs = dict(zip(c.tableau["id_site"], c.tableau["rang"].astype(int).tolist(), strict=True))
    variations = variations_de_rang(
        chemins.donnees / "cache" / donnees.config.dossier_cache,
        empreinte({k: v for k, v in valeurs.items()}),
        rangs,
    )
    # Carte des sites colorée par rang (§11.2.3) : classes de rang de même effectif.
    nombre_classes = charger_config_api(chemins).classes_carte
    classes = ((c.tableau["rang"] - 1) * nombre_classes // max(len(c.tableau), 1)).astype(int)
    lon = dict(zip(donnees.sites["id_site"], donnees.sites["lon"], strict=True))
    lat = dict(zip(donnees.sites["id_site"], donnees.sites["lat"], strict=True))
    tableau = c.tableau.assign(
        nom=c.tableau["id_site"].map(noms),
        type=c.tableau["id_site"].map(types),
        variation=c.tableau["id_site"].map(variations),
        classe=classes,
        lon=c.tableau["id_site"].map(lon),
        lat=c.tableau["id_site"].map(lat),
    )
    legende = [
        {
            "classe": int(k),
            "rang_min": int(groupe["rang"].min()),
            "rang_max": int(groupe["rang"].max()),
        }
        for k, groupe in tableau.groupby("classe", sort=True)
    ]
    axes = {code: donnees.catalogue.criteres[code].axe for code in c.criteres}
    # Score normalisé de chaque axe (0 à 1) : contributions de ses critères ÷ son poids.
    par_axe: dict[str, dict[str, float]] = {}
    for _, ligne in c.tableau.iterrows():
        scores: dict[str, float] = {}
        for axe in sorted(set(axes.values())):
            membres = [k for k, a in axes.items() if a == axe]
            poids_axe = sum(c.poids[k] for k in membres)
            contribution = sum(float(ligne[f"contribution_{k}"]) for k in membres)
            scores[axe] = contribution / poids_axe if poids_axe else 0.0
        par_axe[str(ligne["id_site"])] = scores
    return {
        "bloque": False,
        "methode": _reglages(chemins, donnees, methode)[0].methode,
        "classement": lignes(tableau),
        "exclus": lignes(
            c.exclus.assign(
                nom=c.exclus["id_site"].map(noms),
                lon=c.exclus["id_site"].map(lon),
                lat=c.exclus["id_site"].map(lat),
            )
        ),
        "legende_rangs": legende,
        "retires": c.retires,
        "partiel": {"utilises": len(c.criteres), "actifs": c.criteres_actifs, "partiel": c.partiel},
        "libelles_retires": {k: donnees.catalogue.criteres[k].libelle for k in c.retires},
        "avertissements": c.avertissements,
        "poids": c.poids,
        "criteres": c.criteres,
        "axes_criteres": axes,
        "scores_axes": par_axe,
        "libelles_axes": donnees.catalogue.axes,
        "libelles_criteres": {k: donnees.catalogue.criteres[k].libelle for k in c.criteres},
        "valeurs": {s: {k: float(v) for k, v in c.brute.loc[s].items()} for s in c.brute.index},
    }


@routeur.get("/decision/robustesse")
def analyse_robustesse(
    chemins: CheminsDep, donnees: DonneesDep, methode: str | None = None
) -> dict[str, object]:
    """Un poids à la fois, probabilités Monte Carlo d'être 1er et dans le trio, RG-12."""
    _, a_renseigner, _, _ = _entreprise(chemins)
    if a_renseigner:
        return {"bloque": True, "a_renseigner": a_renseigner}
    c = _classer(chemins, donnees, methode)
    config = donnees.config
    p = config.parametres
    s = config.sensibilite
    variations = np.round(np.arange(s.variation_min, s.variation_max + s.pas / 2, s.pas), 10)
    seuil = float(_lire_technique(chemins, p.seuil_robustesse)) / donnees.config.pourcentage
    r = robustesse(
        c,
        donnees.catalogue,
        _reglages(chemins, donnees, methode)[0].methode,
        variations,
        float(_lire_technique(chemins, p.concentration)),
        int(_lire_technique(chemins, p.tirages)),
        int(_lire_technique(chemins, p.graine)),
        config.rang_tete,
        seuil,
    )
    noms = dict(zip(donnees.sites["id_site"], donnees.sites["nom"], strict=True))
    return {
        "bloque": False,
        "un_poids": lignes(r.un_poids),
        "seuils_changement": r.seuils_changement,
        "sites": [
            {
                "id_site": site,
                "nom": noms.get(site, site),
                "proba_premier": r.proba_premier[site],
                "proba_tete": r.proba_tete[site],
                "rang_wsm": r.rangs_wsm[site],
                "rang_topsis": r.rangs_topsis[site],
                "robuste": site in r.robustes,
            }
            for site in sorted(
                r.proba_premier,
                key=lambda x: (-r.proba_premier[x], -r.proba_tete[x], r.rangs_wsm[x]),
            )
        ],
        "seuil_robustesse": seuil,
        "tirages": int(_lire_technique(chemins, p.tirages)),
    }


@routeur.get("/melange/{id_site}")
def melange(
    id_site: str,
    chemins: CheminsDep,
    donnees: DonneesDep,
    logistique: LogistiqueDep,
    calcul: CalculDep,
) -> dict[str, object]:
    """Mélange de coût minimal pour le site et la capacité K (UC-MIX-01)."""
    p = donnees.config.parametres
    lire = logistique.lire

    def nombre(identifiant: str) -> float | None:
        valeur = lire(identifiant).valeur
        return float(valeur) if isinstance(valeur, int | float) else None

    try:
        courbe, _ = logistique.courbe(id_site)
    except Blocage as blocage:
        return {"bloque": True, "a_saisir": str(blocage).splitlines()}
    couples, motifs = couples_du_bassin(courbe, logistique.residus, _bilans_en_cache(), id_site)  # type: ignore[arg-type]
    part = nombre(p.part_maximale)
    contraintes = Contraintes(
        capacite=courbe.capacite,
        part_maximale=part / donnees.config.pourcentage if part is not None else None,
        cendres_maximales=nombre(p.cendres_maximales),
        humidite_maximale=nombre(p.humidite_maximale),
        lambda_carbone=float(_lire_technique(chemins, p.lambda_carbone) or 0),
    )
    m = melange_optimal(couples, contraintes)
    provinces = calcul.entrees.referentiel.provinces
    noms_p = dict(zip(provinces["code_province"], provinces["nom_fr"], strict=True))
    residus = calcul.entrees.tables.residus
    noms_r = {
        c: str(residus.valeur(c, "nom").lire()) for c in calcul.entrees.catalogue.residus.codes
    }
    tableau = m.tableau.assign(
        nom_province=m.tableau["code_province"].map(noms_p),
        nom_residu=m.tableau["code_residu"].map(noms_r),
    )
    return {
        "bloque": False,
        "faisable": m.faisable,
        "message": m.message,
        "melange": lignes(tableau),
        "cout_moyen": m.cout_moyen,
        "cendres_moyennes": m.cendres_moyennes,
        "humidite_moyenne": m.humidite_moyenne,
        "bilan_moyen": m.bilan_moyen,
        "bloquantes": m.bloquantes,
        "non_appliquees": m.non_appliquees,
        "exclus": motifs,
        "capacite": courbe.capacite,
    }


@routeur.get("/decision/gisements")
def classement_gisements(
    chemins: CheminsDep,
    donnees: DonneesDep,
    calcul: CalculDep,
    logistique: LogistiqueDep,
    site: str = "AGP-MEKNES",
    methode: str | None = None,
) -> dict[str, object]:
    """Couples province × résidu classés sur les critères de niveau G (UC-DEC-04).

    C1, C6 et D1 dépendent du site choisi. Un couple à qui manque la valeur d'un critère calculé
    pour d'autres couples est exclu et listé ; un critère qui manque partout est retiré.
    """
    _, a_renseigner, _, _ = _entreprise(chemins)
    if a_renseigner:
        return {"bloque": True, "a_renseigner": a_renseigner}
    reglages, _ = _reglages(chemins, donnees, methode)
    catalogue = donnees.catalogue
    niveau_g = [
        c
        for c in reglages.actifs
        if "G" in catalogue.criteres[c].niveaux and catalogue.criteres[c].priorite == "P1"
    ]
    resultat = calcul.resultat
    try:
        couts, _ = logistique.couts(site)
        motif_couts = None
    except Blocage as blocage:
        couts, motif_couts = None, str(blocage).splitlines()[0]
    bilans = _bilans_en_cache()
    bilans_site = bilans[bilans["id_site"] == site] if bilans is not None else None  # type: ignore[index]
    p = donnees.config.parametres
    valeurs, motifs = matrice_gisements(
        resultat.reference("T"),
        resultat.reference("M"),
        resultat.reference("densite_M"),
        resultat.exclus,
        logistique.residus,
        logistique.concurrence,
        logistique.national,
        couts,
        motif_couts,
        bilans_site,  # type: ignore[arg-type]
        logistique.lire,
        (p.prix_biochar, p.prix_credit),
        donnees.config.pourcentage,
    )
    provinces = calcul.entrees.referentiel.provinces
    noms_p = dict(zip(provinces["code_province"], provinces["nom_fr"], strict=True))
    residus = calcul.entrees.tables.residus
    noms_r = {
        c: str(residus.valeur(c, "nom").lire()) for c in calcul.entrees.catalogue.residus.codes
    }

    def noms(couple: str) -> dict[str, str]:
        province, residu = couple.split(SEPARATEUR_COUPLE)
        return {
            "code_province": province,
            "nom_province": noms_p.get(province, province),
            "code_residu": residu,
            "nom_residu": noms_r.get(residu, residu),
        }

    base = {"site": site, "couples": len(valeurs), "criteres_actifs_g": niveau_g}
    try:
        c = classer(
            valeurs,
            motifs,
            {},
            reglages.__class__(
                **{**reglages.__dict__, "actifs": niveau_g, "filtre_capacite": False}
            ),
            catalogue,
            float(_lire_technique(chemins, p.seuil_correlation)),
            donnees.config.minimum_sites,
            donnees.config.minimum_criteres,
            exclure_incompletes=True,
            nom_alternatives="gisements",
        )
    except ErreurMethode as erreur:
        retires = {
            k: (motifs[k].dropna().iloc[0] if motifs[k].notna().any() else "valeur manquante")
            for k in niveau_g
            if catalogue.criteres[k].sens != "filtre" and valeurs[k].isna().all()
        }
        manquants = {
            k: int(valeurs[k].isna().sum())
            for k in niveau_g
            if catalogue.criteres[k].sens != "filtre" and k not in retires
        }
        return base | {
            "bloque": False,
            "classable": False,
            "message": str(erreur),
            "manquants": manquants,
            "motifs_manquants": {
                k: (motifs[k].dropna().iloc[0] if motifs[k].notna().any() else "")
                for k in manquants
            },
            "libelles_manquants": {k: catalogue.criteres[k].libelle for k in manquants},
            "retires": retires,
            "libelles_retires": {k: catalogue.criteres[k].libelle for k in retires},
            "partiel": {
                "utilises": 0,
                "actifs": len([k for k in niveau_g if catalogue.criteres[k].sens != "filtre"]),
                "partiel": True,
            },
        }
    lignes_classement = [
        {
            **noms(str(ligne["id_site"])),
            "rang": int(ligne["rang"]),
            "score": float(ligne["score"]),
            "valeurs": {k: float(c.brute.at[ligne["id_site"], k]) for k in c.criteres},
        }
        for _, ligne in c.tableau.iterrows()
    ]
    motifs_exclus = c.exclus["motif"].str.split(" : ").str[0].value_counts()
    return base | {
        "bloque": False,
        "classable": True,
        "classement": lignes_classement[:300],
        "classes": len(lignes_classement),
        "exclus": {
            "total": len(c.exclus),
            "motifs": {str(k): int(v) for k, v in motifs_exclus.items()},
        },
        "retires": c.retires,
        "libelles_retires": {k: catalogue.criteres[k].libelle for k in c.retires},
        "partiel": {"utilises": len(c.criteres), "actifs": c.criteres_actifs, "partiel": c.partiel},
        "criteres": c.criteres,
        "libelles_criteres": {k: catalogue.criteres[k].libelle for k in c.criteres},
        "unites": {k: catalogue.criteres[k].unite for k in c.criteres},
        "poids": c.poids,
        "avertissements": c.avertissements,
    }


@routeur.get("/fiche/{id_site}")
def fiche_site(
    id_site: str,
    chemins: CheminsDep,
    donnees: DonneesDep,
    calcul: CalculDep,
    logistique: LogistiqueDep,
    acv: AcvDep,
) -> dict[str, object]:
    """Fiche d'un site (UC-RES-01) : rang, score, critères, bassin, mélange, bilan, robustesse."""
    from api.routes.acv import bilans_site
    from api.routes.logistique import courbe as courbe_site

    sites = donnees.sites
    choix = sites[sites["id_site"] == id_site]
    if choix.empty:
        raise HTTPException(404, f"site « {id_site} » inconnu")
    site = lignes(choix)[0]
    provinces = calcul.entrees.referentiel.provinces
    noms_p = dict(zip(provinces["code_province"], provinces["nom_fr"], strict=True))
    site["nom_province"] = noms_p.get(str(site.get("code_province")))
    reglages, _ = _reglages(chemins, donnees, None)
    catalogue = donnees.catalogue
    criteres = [
        {
            "code": code,
            "libelle": catalogue.criteres[code].libelle,
            "axe": catalogue.criteres[code].axe,
            "unite": catalogue.criteres[code].unite,
            "sens": catalogue.criteres[code].sens,
            "valeur": (
                None
                if np.isnan(donnees.valeurs.at[id_site, code])
                else float(donnees.valeurs.at[id_site, code])
            ),
            "motif": donnees.motifs.at[id_site, code],
        }
        for code in reglages.actifs
        if code in donnees.valeurs.columns
    ]
    resultat: dict[str, object] = {
        "site": site,
        "criteres": criteres,
        "axes": catalogue.axes,
        "demo": bandeau_demo(chemins),  # repris en tête de la fiche imprimée
    }
    c = classement(chemins, donnees, None)
    if not c.get("bloque"):
        ligne = next((s for s in c["classement"] if s["id_site"] == id_site), None)  # type: ignore[union-attr]
        exclu = next((e for e in c["exclus"] if e["id_site"] == id_site), None)  # type: ignore[union-attr]
        resultat |= {
            "classement": ligne,
            "exclu": exclu,
            "sites_classes": len(c["classement"]),  # type: ignore[arg-type]
            "scores_axes": c["scores_axes"].get(id_site, {}),  # type: ignore[union-attr]
            "partiel": c["partiel"],
            "retires": c["retires"],
            "libelles_retires": c["libelles_retires"],
            "methode": c["methode"],
        }
        r = analyse_robustesse(chemins, donnees, None)
        if not r.get("bloque"):
            resultat["robustesse"] = next(
                (s for s in r["sites"] if s["id_site"] == id_site),  # type: ignore[union-attr]
                None,
            )
    else:
        resultat["a_renseigner"] = c["a_renseigner"]
    courbe = courbe_site(id_site, logistique, calcul)
    resultat["bassin"] = {k: v for k, v in courbe.items() if k not in {"points", "site"}}
    resultat["melange"] = melange(id_site, chemins, donnees, logistique, calcul)
    bilan = bilans_site(id_site, acv, logistique, calcul)
    resultat["bilan"] = {
        k: bilan[k]
        for k in ("bilan_site", "motif_site", "par_residu", "unite_fonctionnelle", "standard")
    }
    return resultat
