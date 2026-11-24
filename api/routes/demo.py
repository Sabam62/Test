"""Scénarios de démonstration : lister, charger en un clic, quitter (config/demo.yaml).

Ces routes travaillent sur les dossiers réels (``obtenir_chemins_reels``) : elles posent ou
retirent le pointeur de la démonstration. Toutes les autres routes calculent sur la copie de
travail tant qu'une démonstration est chargée.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependances import obtenir_chemins_reels
from src.chemins import Chemins
from src.scenarios.demo import (
    DemoActive,
    charger_config_demo,
    charger_demo,
    demo_active,
    lister_scenarios_demo,
    quitter_demo,
)

routeur = APIRouter(prefix="/demo", tags=["démonstration"])
ReelDep = Annotated[Chemins, Depends(obtenir_chemins_reels)]


def _active(active: DemoActive | None) -> dict[str, str] | None:
    if active is None:
        return None
    return {
        "identifiant": active.identifiant,
        "nom": active.nom,
        "bandeau": active.bandeau,
        "date": active.date,
    }


@routeur.get("")
def etat(reel: ReelDep) -> dict[str, object]:
    """Scénarios de démonstration disponibles et scénario chargé (None hors démonstration)."""
    return {
        "active": _active(demo_active(reel)),
        "bandeau": charger_config_demo(reel).bandeau,
        "scenarios": [
            {"identifiant": s.identifiant, "nom": s.nom, "description": s.description}
            for s in lister_scenarios_demo(reel)
        ],
    }


@routeur.post("/{identifiant}")
def charger(identifiant: str, reel: ReelDep) -> dict[str, object]:
    """Charge le scénario dans une copie de travail ; les données réelles restent intactes."""
    active, rapport = charger_demo(reel, identifiant)
    return {
        "active": _active(active),
        "completees": len(rapport.completees),
        "ignorees": rapport.ignorees,
    }


@routeur.delete("")
def quitter(reel: ReelDep) -> dict[str, object]:
    """Quitte la démonstration : l'outil revient aux paramètres et données réels."""
    return {"quittee": quitter_demo(reel), "active": None}
