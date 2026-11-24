"""Projet Brightway 2.5 de l'ACV, sans ecoinvent (section 8.3, ENF-15).

Le projet ``atlantic_biochar`` contient :

- la biosphère de bw2io (liste des flux élémentaires, sans inventaire) ;
- la méthode PRG100 AR6 créée par code à partir de PAR-27 ;
- la base d'avant-plan ``ab_foreground`` : les activités agrégées d'arrière-plan (une par ligne
  de ``facteurs_emission.csv``), puis, pour chaque résidu, une activité par étape (collecte,
  prétraitement, transport, pyrolyse, épandage), la chaîne complète (1 t de biochar) et le
  scénario de référence. Les quantités qui dépendent du couple et du site (distance, charge
  utile, rendement) sont des paramètres Brightway du groupe du résidu, recalculés pour chaque
  chaîne ; le projet reste lisible dans Activity Browser 3.

Une entrée « À compléter » est écrite avec la valeur 0 et le commentaire « À compléter » :
les bilans qui en dépendent sont bloqués par :mod:`src.acv.bilan`, jamais affichés.
"""

from dataclasses import dataclass

import bw2calc as bc
import bw2data as bd

from src.acv.config import ConfigAcv
from src.acv.entrees import Entree, EntreesAcv
from src.logistique.couts import Terme

A_COMPLETER = "À compléter"
ETAPES = ("collecte", "pretraitement", "transport", "pyrolyse", "epandage")
# Paramètres de projet : nom Brightway → donnée d'activité de config/acv.yaml.
PARAMETRES_PROJET = {
    "gaz_col": "gazole_collecte",
    "elec_broy": "electricite_broyage",
    "elec_pyr": "electricite_pyrolyse",
    "gaz_ep": "gazole_epandage",
    "d_bc": "distance_biochar",
}


def _nombre(entree: Entree) -> float:
    return entree.valeur if isinstance(entree, Terme) else 0.0


def _commentaire(entree: Entree) -> str:
    return (
        f"source : {entree.source}, statut {entree.statut.value}"
        if isinstance(entree, Terme)
        else f"{A_COMPLETER} : {entree}"
    )


def ouvrir_projet(config: ConfigAcv) -> None:
    """Ouvre (ou crée) le projet et sa biosphère, sans ecoinvent."""
    bd.projects.set_current(config.projet)
    if config.base_biosphere not in bd.databases:
        import bw2io

        bw2io.create_default_biosphere3()


def _flux(config: ConfigAcv) -> dict[str, tuple[str, str]]:
    """Clé Brightway de chaque flux élémentaire de ``config/acv.yaml``."""
    biosphere = bd.Database(config.base_biosphere)
    cles = {}
    for nom, definition in config.flux.items():
        trouves = [
            f
            for f in biosphere
            if f["name"] == definition.nom and list(f["categories"]) == definition.compartiment
        ]
        if len(trouves) != 1:
            raise RuntimeError(
                f"flux « {definition.nom} » introuvable dans {config.base_biosphere}"
            )
        cles[nom] = trouves[0].key
    return cles


def creer_methode(config: ConfigAcv, entrees: EntreesAcv) -> tuple[str, ...]:
    """Méthode PRG100 AR6 (PAR-27) : un facteur par flux ; un PRG à compléter vaut 0."""
    cles = _flux(config)
    methode = bd.Method(tuple(config.methode))
    if methode.name in bd.methods:
        methode.deregister()
    methode.register(unit=config.unite_methode, description="PRG à 100 ans du GIEC AR6 (PAR-27)")
    methode.write([(cles[nom], _nombre(entrees.prg[nom])) for nom in config.flux])
    return methode.name


def construire_avant_plan(config: ConfigAcv, entrees: EntreesAcv, codes_residus: list[str]) -> None:
    """(Re)construit ``ab_foreground`` à partir des entrées actives."""
    cles = _flux(config)
    nom_base = config.base_avant_plan
    if nom_base in bd.databases:
        del bd.databases[nom_base]
    base = bd.Database(nom_base)
    base.register(description="Avant-plan de l'outil Atlantic Biochar, construit par code")

    def activite(code: str, nom: str, unite: str, commentaire: str = "") -> bd.backends.Activity:
        act = base.new_activity(code=code, name=nom, unit=unite, comment=commentaire)
        act.save()
        act.new_exchange(input=act, amount=1, type="production").save()
        return act

    fond = {}
    for code, definition in config.arriere_plan.items():
        act = activite(code, f"{code} (arrière-plan agrégé)", definition.unite)
        multiplicateur = definition.facteur
        for parametre in definition.multiplicateurs:
            multiplicateur *= _nombre(entrees.facteurs[code][parametre])
        for parametre, flux in definition.echanges.items():
            valeur = entrees.facteurs[code][parametre]
            act.new_exchange(
                input=cles[flux],
                amount=_nombre(valeur) * multiplicateur,
                type="biosphere",
                comment=f"{parametre} · {_commentaire(valeur)}",
            ).save()
        fond[code] = act

    bd.parameters.new_project_parameters(
        [
            {
                "name": nom,
                "amount": _nombre(entrees.activites[donnee]),
                "comment": _commentaire(entrees.activites[donnee]),
            }
            for nom, donnee in PARAMETRES_PROJET.items()
        ]
        + [
            {"name": "conso", "amount": _nombre(entrees.consommation_camion), "comment": "L/km"},
            {"name": "charge", "amount": _nombre(entrees.charge_camion) or 1, "comment": "t"},
            {"name": "trajets", "amount": config.trajets_par_rotation, "comment": "aller-retour"},
        ],
        overwrite=True,
    )
    gazole = [fond["gazole_combustion"], fond["gazole_amont"]]
    for residu in codes_residus:
        proprietes = entrees.residus[residu]
        y = _nombre(proprietes.rendement)
        groupe = f"chaine_{residu}"
        etapes = {
            "collecte": activite(f"collecte_{residu}", f"Collecte · {residu}", "ton"),
            "pretraitement": activite(
                f"pretraitement_{residu}", f"Prétraitement · {residu}", "ton"
            ),
            "transport": activite(
                f"transport_{residu}", f"Transport vers l'usine · {residu}", "ton"
            ),
            "pyrolyse": activite(f"pyrolyse_{residu}", f"Pyrolyse · {residu}", "ton"),
            "epandage": activite(f"epandage_{residu}", f"Transport et épandage · {residu}", "ton"),
        }
        chaine = activite(
            f"chaine_{residu}",
            f"Biochar produit et épandu · {residu}",
            "ton",
            f"unité fonctionnelle : {config.unite_fonctionnelle}",
        )
        reference = activite(
            f"reference_{residu}",
            f"Scénario de référence · {residu} · {proprietes.scenario or A_COMPLETER}",
            "ton",
        )
        for act in etapes.values():
            chaine.new_exchange(input=act, amount=1, type="technosphere").save()
        formules = [
            (etapes["collecte"], gazole, "m * gaz_col"),
            (etapes["pretraitement"], [fond["electricite_reseau"]], "m * elec_broy"),
            (etapes["transport"], gazole, "m * conso * trajets * distance / q"),
            (etapes["pyrolyse"], [fond["electricite_reseau"]], "elec_pyr"),
            (etapes["pyrolyse"], [fond["pyrolyse"]], "1"),
            (etapes["epandage"], gazole, "gaz_ep + conso * trajets * d_bc / charge"),
        ]
        activite_reference = config.scenarios_reference.get(proprietes.scenario or "")
        if activite_reference:
            formules.append((reference, [fond[activite_reference]], "m * facteur_ref"))
        for act, entrants, formule in formules:
            for entrant in entrants:
                act.new_exchange(
                    input=entrant, amount=0, formula=formule, type="technosphere"
                ).save()
        bd.parameters.new_activity_parameters(
            [
                {
                    "name": "m",
                    "amount": 1 / y if y else 0,
                    "database": nom_base,
                    "code": chaine["code"],
                    "comment": "t MS par t de biochar (1 / rendement)",
                },
                {
                    "name": "distance",
                    "amount": 0,
                    "database": nom_base,
                    "code": chaine["code"],
                    "comment": "km, distance routière du couple au site",
                },
                {
                    "name": "q",
                    "amount": 1,
                    "database": nom_base,
                    "code": chaine["code"],
                    "comment": "t MS, charge utile du camion",
                },
                {
                    "name": "facteur_ref",
                    "amount": 1,
                    "database": nom_base,
                    "code": chaine["code"],
                    "comment": "unités de référence par t MS",
                },
            ],
            group=groupe,
            overwrite=True,
        )
        for act in [*etapes.values(), reference]:
            bd.parameters.add_exchanges_to_group(groupe, act)
    bd.parameters.recalculate()


@dataclass(frozen=True)
class ScoresUnitaires:
    """kg CO₂e par unité de référence de chaque activité d'arrière-plan (calcul Brightway)."""

    scores: dict[str, float]


def scores_unitaires(config: ConfigAcv) -> ScoresUnitaires:
    """Score PRG100 de chaque activité agrégée, pour une unité (LCA Brightway)."""
    base = bd.Database(config.base_avant_plan)
    methode = tuple(config.methode)
    scores = {}
    for code in config.arriere_plan:
        lca = bc.LCA({base.get(code): 1}, methode)
        lca.lci()
        lca.lcia()
        scores[code] = float(lca.score)
    return ScoresUnitaires(scores)


def bilan_brightway(
    config: ConfigAcv, residu: str, distance: float, charge_utile: float, facteur_ref: float
) -> dict[str, float]:
    """Émissions de chaque étape et du scénario de référence d'une chaîne (kg CO₂e/t biochar).

    Les paramètres du groupe du résidu (distance, charge utile, facteur de référence) prennent
    les valeurs du couple, puis Brightway recalcule les échanges et chaque étape est évaluée.
    """
    from bw2data.parameters import ActivityParameter

    groupe = f"chaine_{residu}"
    for nom, valeur in (("distance", distance), ("q", charge_utile), ("facteur_ref", facteur_ref)):
        parametre = ActivityParameter.get(name=nom, group=groupe)
        parametre.amount = valeur
        parametre.save()
    bd.parameters.recalculate()
    base = bd.Database(config.base_avant_plan)
    resultats = {}
    for nom in (*ETAPES, "reference"):
        lca = bc.LCA({base.get(f"{nom}_{residu}"): 1}, tuple(config.methode))
        lca.lci()
        lca.lcia()
        resultats[nom] = float(lca.score)
    return resultats
