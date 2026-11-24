"""SRC-01 : Open Data Maroc, Production végétale 2010-2022, total national par culture.

Le fichier est au format long (campagne, filière, produit, indicateur, valeur). Les produits
de chaque culture de ``cultures.csv`` sont additionnés (``config/preparation.yaml``). Une
campagne n'est utilisée que si chaque produit et indicateur n'y figure qu'une fois : sinon ses
lignes n'ont pas de maille géographique lisible et leur somme n'est pas un total national
vérifiable (lignes rejetées, avec le motif).
"""

from pathlib import Path

import pandas as pd

from src.data.config_preparation import ConfigSrc01
from src.data.observations import (
    NATIONAL,
    BilanControle,
    Categorie,
    ErreurPreparation,
    Niveau,
    annee_campagne,
    campagne_valide,
)
from src.data.provenance import Statut

SOURCE_ID = "SRC-01"


def lire_src01(
    dossier: Path, config: ConfigSrc01, bilan: BilanControle, url: str | None = None
) -> list[dict[str, object]]:
    """Totaux nationaux (production en t, superficie en ha) par culture et par campagne.

    Args:
        dossier: ``data/raw/SRC-01/`` (ou son extrait figé).
        config: section ``src01`` de ``config/preparation.yaml``.
        bilan: bilan des contrôles, complété (lignes numérotées à partir de la première ligne
            de données).
        url: adresse de téléchargement inscrite au manifeste, si elle est connue.
    """
    chemin = dossier / config.fichier
    if not chemin.is_file():
        raise ErreurPreparation(
            f"{chemin} est absent : lancez « python -m scripts.download --source {SOURCE_ID} » "
            "(voir docs/donnees_manuelles.md)"
        )
    table = pd.read_excel(chemin)
    table.columns = [str(c).strip() for c in table.columns]
    colonnes = config.colonnes
    attendues = [
        colonnes.campagne,
        colonnes.filiere,
        colonnes.produit,
        colonnes.indicateur,
        colonnes.valeur,
    ]
    absentes = [c for c in attendues if c not in table.columns]
    if absentes:
        raise ErreurPreparation(f"{chemin.name} : colonnes absentes {', '.join(absentes)}")
    table = table.set_axis(range(1, len(table) + 1))
    bilan.lire(SOURCE_ID, config.fichier, len(table))
    culture_de = {p: c for c, produits in config.produits.items() for p in produits}
    table["campagne"] = (
        table[colonnes.campagne]
        .astype(str)
        .str.strip()
        .str.replace(config.separateur_campagne, "-")
    )
    table["produit"] = table[colonnes.produit].astype(str).str.strip()
    table["indicateur"] = table[colonnes.indicateur].astype(str).str.strip()
    multiples = table.duplicated(["campagne", "produit", "indicateur"], keep=False)
    campagnes_multiples = set(table.loc[multiples, "campagne"])

    def signaler(numero: int, categorie: Categorie, motif: str) -> None:
        bilan.signaler(SOURCE_ID, config.fichier, numero, categorie, motif)

    retenues: list[tuple[int, str, str, str, float]] = []
    for numero, ligne in table.iterrows():
        numero = int(numero)
        campagne = ligne["campagne"]
        if not campagne_valide(campagne):
            signaler(numero, Categorie.REJETEE, f"campagne « {campagne} » illisible")
            continue
        if campagne in campagnes_multiples:
            signaler(
                numero,
                Categorie.REJETEE,
                f"campagne {campagne} : plusieurs lignes par produit sans colonne géographique ; "
                "total national non vérifiable",
            )
            continue
        culture = culture_de.get(ligne["produit"])
        variable = config.indicateurs.get(ligne["indicateur"])
        if culture is None:
            signaler(numero, Categorie.NON_UTILISEE, "produit hors des cultures de cultures.csv")
            continue
        if variable is None:
            signaler(numero, Categorie.NON_UTILISEE, f"indicateur « {ligne['indicateur']} »")
            continue
        valeur = pd.to_numeric(ligne[colonnes.valeur], errors="coerce")
        if pd.isna(valeur) or valeur < 0:
            signaler(numero, Categorie.REJETEE, "valeur manquante ou négative")
            continue
        signaler(numero, Categorie.VALIDE, f"{culture}, {variable}")
        retenues.append((numero, culture, campagne, variable, float(valeur)))
    if not retenues:
        return []
    lignes = pd.DataFrame(retenues, columns=["ligne", "culture", "campagne", "variable", "valeur"])
    observations = []
    for (culture, campagne, variable), groupe in lignes.groupby(
        ["culture", "campagne", "variable"], sort=True
    ):
        produits = len(groupe)
        observations.append(
            {
                "source_id": SOURCE_ID,
                "document": config.fichier,
                "url": url,
                "organisme": "Ministère de l'Agriculture (Open Data Maroc)",
                "ligne": int(groupe["ligne"].min()),
                "niveau": Niveau.NATIONAL.value,
                "code_zone": NATIONAL,
                "codes_provinces": "",
                "code_culture": culture,
                "campagne": campagne,
                "periode": "campagne",
                "variable": variable,
                "valeur": float(groupe["valeur"].sum()),
                "unite": "t" if variable == "production_t" else "ha",
                "previsionnel": False,
                "statut": Statut.MESUREE.value,
                "annee": annee_campagne(campagne),
                "version": None,
                "methode": "somme des produits" if produits > 1 else "citee",
                "note": f"lignes {', '.join(str(n) for n in groupe['ligne'])}",
            }
        )
    return observations
