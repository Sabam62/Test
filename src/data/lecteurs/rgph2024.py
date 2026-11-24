"""Lecteur du RGPH 2024 (SRC-09) : unités administratives et codes géographiques.

Le fichier « Population légale du Royaume du Maroc » liste, sur une seule feuille, l'ensemble
du territoire, les régions, les provinces et préfectures, leurs milieux urbain et rural, les
préfectures d'arrondissements et les communes. Seules les régions et les provinces ou préfectures
sont retenues ici ; la population est lue à la tâche 6.
"""

import re
from pathlib import Path

import pandas as pd

# En-têtes des trois colonnes utiles de la feuille « Population_légale ».
COLONNE_FR, COLONNE_AR, COLONNE_CODE = (
    "Collectivités territoriales",
    "الجماعات الترابية",
    "Code géographique",
)

PREFIXE_FR = re.compile(
    r"^(?:Région|Province|Préfecture)(?: d'arrondissements?)?\s+(?:de la |de l'|de |d'|des |du )?"
)
PREFIXE_AR = re.compile(r"^(?:جهة|إقليم|عمالة(?: مقاطعات)?)\s+")
REGION = re.compile(r"^Région ")
PROVINCE = re.compile(r"^(?:Province|Préfecture) ")
SOUS_UNITE = re.compile(r"\(milieu|arrondissement")


def lire_lignes_rgph2024(chemin: Path) -> pd.DataFrame:
    """Lit les trois colonnes utiles du fichier XLSX : ``nom_fr``, ``nom_ar``, ``code``."""
    brut = pd.read_excel(chemin, header=None, dtype=str)
    entetes = brut.apply(lambda ligne: set(ligne.dropna().astype(str).str.strip()), axis=1)
    colonnes = {}
    for nom in (COLONNE_FR, COLONNE_AR, COLONNE_CODE):
        trouvee = [i for i, ligne in brut.iterrows() if nom in entetes[i]]
        if not trouvee:
            raise ValueError(f"{chemin.name} : colonne « {nom} » introuvable")
        rang = brut.loc[trouvee[0]].astype(str).str.strip().tolist().index(nom)
        colonnes[nom] = brut.columns[rang]
    lignes = brut[[colonnes[COLONNE_FR], colonnes[COLONNE_AR], colonnes[COLONNE_CODE]]]
    lignes.columns = ["nom_fr", "nom_ar", "code"]
    return lignes


def unites_rgph2024(lignes: pd.DataFrame) -> pd.DataFrame:
    """Régions et provinces du RGPH 2024.

    Args:
        lignes: colonnes ``nom_fr``, ``nom_ar``, ``code`` (voir :func:`lire_lignes_rgph2024`).

    Returns:
        Colonnes ``niveau`` (region ou province), ``code``, ``nom_officiel`` (libellé du RGPH),
        ``nom_fr`` (sans « Région de », « Province de »…), ``nom_ar_officiel`` et ``nom_ar``.
    """
    lignes = lignes.astype("string").apply(lambda colonne: colonne.str.strip())
    lignes = lignes[lignes["code"].fillna("").str.fullmatch(r"\d+")]
    noms = lignes["nom_fr"].fillna("")
    niveau = pd.Series(pd.NA, index=lignes.index, dtype="string")
    niveau[noms.str.match(REGION)] = "region"
    niveau[noms.str.match(PROVINCE) & ~noms.str.contains(SOUS_UNITE)] = "province"
    unites = lignes.assign(niveau=niveau).dropna(subset=["niveau"])
    unites = unites.drop_duplicates(subset=["niveau", "code"])
    return pd.DataFrame(
        {
            "niveau": unites["niveau"].astype(str),
            "code": unites["code"].astype(str),
            "nom_officiel": unites["nom_fr"].astype(str),
            "nom_fr": unites["nom_fr"].astype(str).str.replace(PREFIXE_FR, "", regex=True),
            "nom_ar_officiel": unites["nom_ar"].astype(str),
            "nom_ar": unites["nom_ar"].astype(str).str.replace(PREFIXE_AR, "", regex=True),
        }
    ).reset_index(drop=True)
