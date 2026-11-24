"""Annexes de tout export (ENF-05, ENF-14) : paramètres utilisés et liste des sources."""

import pandas as pd

from src.chemins import Chemins
from src.data.sources import charger_sources
from src.decision.reglages import lire_reglages
from src.scenarios.config import charger_entreprise
from src.scenarios.parametres import etat_parametres

COLONNES_PARAMETRES = ["rubrique", "identifiant", "libelle", "valeur", "unite", "source", "statut"]
COLONNES_SOURCES = ["source_id", "titre", "url", "licence", "attribution", "parent"]


def table_parametres(chemins: Chemins) -> pd.DataFrame:
    """Paramètres de l'entreprise (14.1), techniques (14.3) et réglages de la décision."""
    lignes = []
    for identifiant, p in charger_entreprise(chemins).parametres.items():
        lignes.append(
            {
                "rubrique": "entreprise (14.1)",
                "identifiant": identifiant,
                "libelle": p.libelle,
                "valeur": "non renseigné" if p.valeur is None else p.valeur,
                "unite": p.unite,
                "source": "Atlantic Biochar",
                "statut": "Terrain" if p.valeur is not None else "",
            }
        )
    for etat in etat_parametres(chemins):
        courante = etat.courante
        provenance = courante.provenance if courante else None
        lignes.append(
            {
                "rubrique": "technique (14.3)" + (", modifié" if etat.modifie else ""),
                "identifiant": etat.identifiant,
                "libelle": etat.libelle,
                "valeur": (
                    etat.calcul
                    if etat.calcul
                    else (
                        "À compléter"
                        if courante is None or courante.valeur is None
                        else courante.valeur
                    )
                ),
                "unite": courante.unite if courante else "",
                "source": provenance.source_id if provenance else "",
                "statut": provenance.statut.value if provenance else "",
            }
        )
    reglages = lire_reglages(chemins)
    for nom, valeur in (
        (
            "critères actifs",
            reglages.actifs if reglages.actifs is not None else "par défaut (section 9)",
        ),
        ("poids", reglages.poids or "par défaut (PAR-45)"),
        ("seuils", {c: s.model_dump() for c, s in reglages.seuils.items()} or "aucun"),
        ("méthode", reglages.methode or "PAR-40"),
        ("filtre de capacité (RG-10)", "oui" if reglages.filtre_capacite else "non"),
    ):
        lignes.append(
            {
                "rubrique": "décision",
                "identifiant": "",
                "libelle": nom,
                "valeur": valeur,
                "unite": "",
                "source": "écran Décision",
                "statut": "",
            }
        )
    return pd.DataFrame(lignes, columns=COLONNES_PARAMETRES)


def table_sources(chemins: Chemins) -> pd.DataFrame:
    """Manifeste des sources (RG-05) avec licence et attribution (ENF-14)."""
    lignes = [
        {
            "source_id": identifiant,
            "titre": s.titre,
            "url": s.url or "",
            "licence": s.licence or "",
            "attribution": s.attribution or "",
            "parent": s.parent or "",
        }
        for identifiant, s in charger_sources(chemins).sources.items()
    ]
    return pd.DataFrame(lignes, columns=COLONNES_SOURCES)
