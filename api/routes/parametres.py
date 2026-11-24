"""Paramètres techniques : valeur courante, défaut, source, retour au défaut (UC-SCN-01)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependances import obtenir_chemins
from api.schemas import ReglageParametre
from api.serialisation import valeur_sourcee
from src.chemins import Chemins
from src.scenarios.parametres import etat_parametres, regler_parametre, revenir_au_defaut

routeur = APIRouter(prefix="/parametres", tags=["paramètres"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]


@routeur.get("")
def lister(chemins: CheminsDep) -> list[dict[str, object]]:
    """Chaque paramètre de la section 14.3 (composantes séparées « PAR-20:basse »)."""
    return [
        {
            "identifiant": e.identifiant,
            "libelle": e.libelle,
            "defaut": valeur_sourcee(e.defaut),
            "courante": valeur_sourcee(e.courante),
            "modifie": e.modifie,
            "calcul": e.calcul,
        }
        for e in etat_parametres(chemins)
    ]


@routeur.put("/{identifiant}")
def regler(
    identifiant: str, requete: ReglageParametre, chemins: CheminsDep
) -> dict[str, object] | None:
    """Remplace la valeur par défaut ; source et auteur obligatoires (RG-18)."""
    return valeur_sourcee(
        regler_parametre(chemins, identifiant, requete.valeur, requete.source, requete.auteur)
    )


@routeur.delete("/{identifiant}")
def defaut(identifiant: str, chemins: CheminsDep) -> dict[str, object] | None:
    """Retour à la valeur par défaut de ``config/parametres.yaml``."""
    return valeur_sourcee(revenir_au_defaut(chemins, identifiant))
