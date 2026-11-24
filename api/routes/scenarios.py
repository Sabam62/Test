"""Scénarios : enregistrer, lister, recharger, appliquer (UC-SCN-02, UC-DAT-08)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependances import obtenir_chemins
from api.schemas import Auteur, NouveauScenario
from src.chemins import Chemins
from src.decision.config import charger_catalogue_criteres, charger_config_decision
from src.decision.reglages import (
    ReglagesUtilisateur,
    SeuilUtilisateur,
    enregistrer_reglages,
    lire_reglages,
)
from src.scenarios.scenarios import (
    Scenario,
    appliquer_scenario,
    charger_scenario,
    ecart_de_version,
    enregistrer_scenario,
    lister_scenarios,
    scenario_courant,
)

routeur = APIRouter(prefix="/scenarios", tags=["scénarios"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
SEPARATEUR_SEUIL = "."  # « C2.maximum » : seuil d'un critère dans un scénario


def _avec_ecart(chemins: Chemins, scenario: Scenario) -> dict[str, object]:
    return scenario.model_dump(mode="json") | {"ecart_version": ecart_de_version(chemins, scenario)}


@routeur.get("")
def lister(chemins: CheminsDep) -> list[dict[str, object]]:
    """Scénarios enregistrés, du plus récent au plus ancien."""
    return [_avec_ecart(chemins, s) for s in lister_scenarios(chemins)]


@routeur.post("", status_code=201)
def enregistrer(requete: NouveauScenario, chemins: CheminsDep) -> dict[str, object]:
    """Enregistre l'état courant (paramètres, réglages, version des données) sous un nom.

    Sans critères, poids ni méthode dans la requête, ce sont les réglages de l'écran Décision.
    """
    decision = lire_reglages(chemins)
    seuils = {
        f"{code}{SEPARATEUR_SEUIL}{borne}": valeur
        for code, s in decision.seuils.items()
        for borne, valeur in (("minimum", s.minimum), ("maximum", s.maximum))
        if valeur is not None
    }
    scenario = scenario_courant(
        chemins,
        requete.nom,
        requete.auteur,
        criteres_actifs=requete.criteres_actifs or (decision.actifs or []),
        seuils=requete.seuils or seuils,
        poids=requete.poids or decision.poids,
        methode=requete.methode or decision.methode,
        sites=requete.sites,
    )
    enregistrer_scenario(chemins, scenario, remplacer=requete.remplacer)
    return _avec_ecart(chemins, scenario)


@routeur.get("/{nom}")
def lire(nom: str, chemins: CheminsDep) -> dict[str, object]:
    """Scénario rechargé, avec l'écart éventuel de version des données."""
    return _avec_ecart(chemins, charger_scenario(chemins, nom))


@routeur.post("/{nom}/appliquer")
def appliquer(nom: str, requete: Auteur, chemins: CheminsDep) -> dict[str, object]:
    """Rend actifs les paramètres et réglages du scénario."""
    scenario = charger_scenario(chemins, nom)
    appliquer_scenario(chemins, scenario, requete.auteur)
    seuils: dict[str, dict[str, float]] = {}
    for cle, valeur in scenario.seuils.items():
        code, _, borne = cle.partition(SEPARATEUR_SEUIL)
        seuils.setdefault(code, {})[borne or "minimum"] = valeur
    enregistrer_reglages(
        chemins,
        ReglagesUtilisateur(
            actifs=scenario.criteres_actifs or None,
            poids=scenario.poids,
            seuils={c: SeuilUtilisateur(**s) for c, s in seuils.items()},
            methode=scenario.methode,
            auteur=requete.auteur,
        ),
        charger_catalogue_criteres(chemins),
        charger_config_decision(chemins),
    )
    return _avec_ecart(chemins, scenario)
