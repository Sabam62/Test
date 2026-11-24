"""Génération des variantes de noms de ``data/input/variantes_provinces.csv`` (RG-02).

Les noms officiels du RGPH 2024 sont reconnus d'office ; le fichier ne contient que les autres
graphies, chacune avec sa source :

- ``rapprochement spatial`` : noms des frontières HDX (SRC-05, en anglais), rattachés au code
  dont le polygone du HCP (SRC-19) contient un point intérieur de l'unité HDX ;
- ``nom des cartes`` : noms français et arabes des cartes du HCP (SRC-19), rattachés par code ;
- ``saisie`` : variantes ajoutées à la main (DRA, enquêtes…), conservées à chaque régénération.
"""

import geopandas as gpd
import pandas as pd

from src.data.provinces import (
    COLONNES_VARIANTES,
    ErreurReferentiel,
    Niveau,
    Referentiel,
    normaliser_nom,
)

METHODE_SPATIALE = "rapprochement spatial"
METHODE_NOMS = "nom des cartes"
METHODE_SAISIE = "saisie"


def variantes_par_code(
    referentiel: Referentiel,
    niveau: Niveau,
    noms: pd.DataFrame,
    colonnes_noms: list[str],
    source_id: str,
) -> pd.DataFrame:
    """Lignes de variantes pour des noms déjà associés à leur code (colonne ``code_<niveau>``).

    Seuls les noms qui ne sont pas déjà reconnus avec le même code sont retenus.
    """
    code = f"code_{niveau}"
    inconnus = sorted(set(noms[code]) - referentiel.codes(niveau))
    if inconnus:
        raise ErreurReferentiel(f"noms de {source_id} pour des codes inconnus : {inconnus}.")
    lignes = []
    for _, ligne in noms.iterrows():
        for colonne in colonnes_noms:
            nom = ligne[colonne]
            if pd.isna(nom) or not str(nom).strip():
                continue
            if referentiel.index.get(niveau, {}).get(normaliser_nom(nom)) == ligne[code]:
                continue
            lignes.append(
                {
                    "niveau": niveau,
                    "variante": str(nom).strip(),
                    "code": ligne[code],
                    "source_id": source_id,
                    "methode": METHODE_NOMS,
                    "note": f"colonne {colonne} des cartes du HCP",
                }
            )
    return pd.DataFrame(lignes, columns=COLONNES_VARIANTES)


def rapprocher(
    unites: gpd.GeoDataFrame, colonne_nom: str, colonne_id: str, cible: gpd.GeoDataFrame, code: str
) -> pd.DataFrame:
    """Rattache chaque unité au polygone de ``cible`` qui contient son point intérieur.

    Lève :class:`ErreurReferentiel` si une unité ne tombe dans aucun polygone, ou si deux unités
    tombent dans le même : le rapprochement doit être un à un.
    """
    points = unites[[colonne_nom, colonne_id, "geometry"]].to_crs(cible.crs)
    points = points.set_geometry(points.representative_point())
    jointure = points.sjoin(cible[[code, "geometry"]], predicate="within", how="left")
    erreurs = [
        f"{n} hors des polygones du HCP" for n in jointure.loc[jointure[code].isna(), colonne_nom]
    ]
    doubles = jointure[jointure[code].notna() & jointure.duplicated(code, keep=False)]
    erreurs += [
        f"{n} partage le code {c}" for n, c in zip(doubles[colonne_nom], doubles[code], strict=True)
    ]
    if erreurs:
        raise ErreurReferentiel("rapprochement spatial impossible : " + " ; ".join(erreurs) + ".")
    return jointure[[colonne_nom, colonne_id, code]]


def variantes_spatiales(
    referentiel: Referentiel,
    niveau: Niveau,
    rapprochement: pd.DataFrame,
    colonne_nom: str,
    colonne_id: str,
    source_id: str,
) -> pd.DataFrame:
    """Lignes de variantes pour les noms qui ne sont pas déjà reconnus avec le même code."""
    code = f"code_{niveau}"
    lignes = []
    for _, ligne in rapprochement.iterrows():
        reconnu = referentiel.index.get(niveau, {}).get(normaliser_nom(ligne[colonne_nom]))
        if reconnu == ligne[code]:
            continue
        lignes.append(
            {
                "niveau": niveau,
                "variante": ligne[colonne_nom],
                "code": ligne[code],
                "source_id": source_id,
                "methode": METHODE_SPATIALE,
                "note": (
                    f"unité {ligne[colonne_id]} ; point intérieur dans le polygone {ligne[code]}"
                ),
            }
        )
    return pd.DataFrame(lignes, columns=COLONNES_VARIANTES)


def fusionner(saisies: pd.DataFrame, generees: list[pd.DataFrame]) -> pd.DataFrame:
    """Variantes saisies conservées, puis variantes générées ; triées par niveau et par code."""
    a_garder = saisies[saisies["methode"] == METHODE_SAISIE]
    table = pd.concat([a_garder, *generees], ignore_index=True)[COLONNES_VARIANTES]
    table = table.drop_duplicates(subset=["niveau", "variante", "code", "source_id"])
    ordre = table["niveau"].map({"province": 0, "region": 1})
    return (
        table.assign(_ordre=ordre)
        .sort_values(["_ordre", "code", "variante"])
        .drop(columns="_ordre")
    )
