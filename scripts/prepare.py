"""Prépare les tables de ``data/processed/`` à partir de ``data/raw/`` (UC-DAT-01 à 04).

Utilisation : python -m scripts.prepare

S'arrête avec un message clair si un fichier brut manque. Écrit le référentiel (GeoPackage),
les surfaces CROPGRIDS, les observations, la production par province (RG-04), les tables de
référence (Parquet) et ``rapport_controle.html``.
"""

import sys

from scripts.download import main as telecharger
from src.chemins import chemins_par_defaut
from src.data.cropgrids import ErreurCropgrids
from src.data.observations import ErreurPreparation
from src.data.preparation import preparer
from src.data.provinces import ErreurRattachement, ErreurReferentiel
from src.data.surfaces import ErreurSurfaces
from src.data.tables_reference import ErreurTable
from src.lecture_yaml import ErreurConfiguration


def main() -> int:
    """Point d'entrée de ``python -m scripts.prepare``."""
    chemins = chemins_par_defaut()
    print("Préparation des données : data/raw/ → data/processed/.")
    try:
        bilan = preparer(
            chemins, lambda: telecharger(["--source", "SRC-04", "--retelecharger-supprimes"])
        )
    except (
        ErreurPreparation,
        ErreurRattachement,
        ErreurReferentiel,
        ErreurCropgrids,
        ErreurSurfaces,
        ErreurTable,
        ErreurConfiguration,
    ) as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1
    for fichier in bilan.ecrits:
        print(f"  {fichier.relative_to(chemins.racine)}")
    resultat = bilan.statistiques.resultat
    production = resultat.production
    couvertes = production.loc[production["variable"] == "production_t", "code_province"]
    print(
        f"{couvertes.nunique()} provinces ont une production réelle ou estimée ; "
        f"{len(resultat.incoherences)} incohérence(s) ; détail dans rapport_controle.html."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
