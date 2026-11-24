"""Produit l'extrait figé du référentiel des provinces utilisé par les tests.

Seuls des attributs sont extraits (codes et noms des unités), jamais les géométries du HCP,
dont la licence exclut la redistribution des cartes :

- hcp_regions.csv, hcp_provinces.csv : codes et noms des couches RGPH:regions et
  RGPH:provinces (SRC-19, tables de noms sans géométrie de data/raw/SRC-19/) ;
- rgph2024_lignes.csv : colonnes « Collectivités territoriales », « الجماعات الترابية » et
  « Code géographique » de la population légale du RGPH 2024 (SRC-09).

Utilisation : python -m tests.fixtures.extraire_referentiel
"""

import json
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[2]
SORTIE = Path(__file__).resolve().parent / "referentiel"


def _attributs(fichier: Path, colonnes: list[str]) -> pd.DataFrame:
    entites = json.loads(fichier.read_text(encoding="utf-8"))["features"]
    return pd.DataFrame([e["properties"] for e in entites])[colonnes]


def main() -> None:
    """Écrit les trois fichiers CSV dans tests/fixtures/referentiel/."""
    brutes = RACINE / "data" / "raw"
    SORTIE.mkdir(exist_ok=True)
    regions = _attributs(
        brutes / "SRC-19/hcp_regions_noms.json", ["code_reg", "libelle_fr", "libelle_ar"]
    )
    regions.sort_values("code_reg").to_csv(SORTIE / "hcp_regions.csv", sep=";", index=False)
    provinces = _attributs(
        brutes / "SRC-19/hcp_provinces_noms.json",
        ["code_reg", "code_prov", "libelle_fr", "libelle_ar"],
    )
    provinces.sort_values(["code_reg", "code_prov"]).to_csv(
        SORTIE / "hcp_provinces.csv", sep=";", index=False
    )
    lignes = pd.read_excel(brutes / "SRC-09/rgph2024_population_legale.xlsx", header=None)
    lignes = lignes.iloc[:, [0, 5, 6]]
    lignes.columns = ["nom_fr", "nom_ar", "code"]
    lignes.to_csv(SORTIE / "rgph2024_lignes.csv", sep=";", index=False)
    for f in sorted(SORTIE.iterdir()):
        print(f.relative_to(RACINE), f.stat().st_size, "octets")


if __name__ == "__main__":
    main()
