"""Paramètres de l'entreprise : onglet Paramètres et paramètres obligatoires (UC-ENT-01, RG-15)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependances import obtenir_chemins
from api.schemas import MiseAJourEntreprise
from src.chemins import Chemins
from src.scenarios.config import ParametresEntreprise, charger_entreprise
from src.scenarios.entreprise import mettre_a_jour_entreprise

routeur = APIRouter(prefix="/entreprise", tags=["entreprise"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]


def _etat(entreprise: ParametresEntreprise) -> dict[str, object]:
    return {
        "renseignement_requis": entreprise.renseignement_requis,
        "obligatoires": entreprise.obligatoires,
        "a_renseigner": entreprise.a_renseigner,
        "date_modification": entreprise.date_modification,
        "auteur": entreprise.auteur,
        "parametres": [p.model_dump(mode="json") for p in entreprise.parametres.values()],
    }


@routeur.get("")
def lire(chemins: CheminsDep) -> dict[str, object]:
    """Paramètres de la section 14.1 et paramètres obligatoires encore vides (RG-15)."""
    return _etat(charger_entreprise(chemins))


@routeur.put("")
def mettre_a_jour(requete: MiseAJourEntreprise, chemins: CheminsDep) -> dict[str, object]:
    """Enregistre les valeurs saisies, datées et signées ; signale les paramètres modifiés."""
    entreprise, evenement = mettre_a_jour_entreprise(chemins, requete.valeurs, requete.auteur)
    return _etat(entreprise) | {
        "modifies": list(evenement.identifiants) if evenement else [],
    }
