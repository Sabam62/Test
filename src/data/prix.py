"""Prix observés (UC-DAT-07, table ``prix_observes``) : historique conservé, le plus récent utilisé.

Un prix (grignons, paille, gazole…) est saisi avec sa date, sa source et son auteur (RG-18).
Il s'ajoute à l'historique, qui n'est jamais réécrit (RG-17) ; les calculs utilisent le prix le
plus récent pour un produit et une zone.
"""

import pandas as pd

from src.data.provinces import Referentiel
from src.data.saisie import ErreurSaisie, controler_fourchette, lire_date
from src.data.versions import Version, Versions
from src.scenarios.config import Controles

TABLE = "prix_observes"


def ajouter_prix(
    versions: Versions,
    controles: Controles,
    referentiel: Referentiel,
    *,
    date_prix: str,
    produit: str,
    code_province: str,
    prix: str,
    unite: str,
    source: str,
    auteur: str,
    note: str = "",
    confirmer: bool = False,
) -> Version:
    """Ajoute un prix observé à l'historique et crée une version."""
    jour = lire_date(date_prix)
    if not source.strip():
        raise ErreurSaisie("source obligatoire (RG-18) : lien, document ou « mesure interne »")
    if not produit.strip() or not unite.strip():
        raise ErreurSaisie("indiquez le produit et l'unité du prix")
    definition = versions.definition(TABLE)
    zone = code_province.strip()
    if definition.province and zone not in definition.province.codes_admis:
        zone = referentiel.rattacher(pd.Series([zone]), "province")[0]
    try:
        valeur = float(prix.replace(",", "."))
    except ValueError:
        raise ErreurSaisie(f"prix « {prix} » illisible : saisissez un nombre") from None
    controler_fourchette(controles.fourchette(TABLE, "prix"), "prix", valeur, confirmer)
    historique = versions.lire(TABLE)
    ligne = {
        "date": jour.isoformat(),
        "produit": produit.strip(),
        "code_province": zone,
        "prix": f"{valeur:g}",
        "unite": unite.strip(),
        "source": source.strip(),
        "auteur": auteur.strip(),
        "note": note.strip(),
    }
    nouvelle = pd.concat([historique, pd.DataFrame([ligne])], ignore_index=True)
    version = versions.enregistrer(
        {TABLE: nouvelle}, auteur, f"prix observé : {produit.strip()} au {jour.isoformat()}"
    )
    if version is None:
        raise ErreurSaisie(
            "ce prix figure déjà dans l'historique (même date, produit, zone, source)"
        )
    return version


def prix_courant(historique: pd.DataFrame, produit: str, code_province: str) -> pd.Series | None:
    """Prix le plus récent d'un produit dans une zone ; à date égale, le dernier saisi."""
    choix = historique[
        (historique["produit"] == produit) & (historique["code_province"] == code_province)
    ]
    if choix.empty:
        return None
    ordre = choix.assign(_rang=range(len(choix))).sort_values(["date", "_rang"])
    return ordre.drop(columns="_rang").iloc[-1]
