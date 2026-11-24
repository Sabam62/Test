"""Découpe CROPGRIDS (SRC-04) sur l'emprise du Maroc dans ``data/processed/``.

Utilisation : python -m scripts.decouper_cropgrids

Si l'archive mondiale a été supprimée et que le découpage manque, elle est retéléchargée
(``python -m scripts.download --source SRC-04``). L'archive n'est jamais supprimée par ce script.
"""

import sys

from scripts.download import main as telecharger
from src.chemins import chemins_par_defaut
from src.data.cropgrids import ErreurCropgrids, charger_config_cropgrids, preparer_cropgrids

OCTETS_PAR_MO = 1_000_000


def _mo(octets: int) -> str:
    return f"{octets / OCTETS_PAR_MO:,.1f} Mo".replace(",", " ").replace(".", ",")


def main() -> int:
    """Point d'entrée de ``python -m scripts.decouper_cropgrids``."""
    chemins = chemins_par_defaut()
    try:
        bilan = preparer_cropgrids(
            chemins, lambda: telecharger(["--source", "SRC-04", "--retelecharger-supprimes"])
        )
    except ErreurCropgrids as erreur:
        print(f"Erreur : {erreur}.", file=sys.stderr)
        return 1
    etat = "écrit" if bilan.ecrit else "déjà à jour, non refait"
    print(
        f"{bilan.sortie.relative_to(chemins.racine)} : {etat} ({_mo(bilan.sortie.stat().st_size)})."
    )
    archive = chemins.brutes / "SRC-04" / charger_config_cropgrids(chemins).archive
    if archive.is_file():
        taille = _mo(archive.stat().st_size)
        print(
            f"L'archive mondiale {archive.relative_to(chemins.racine)} ({taille}) n'est plus "
            "nécessaire aux calculs ; elle reste en place tant que vous ne la supprimez pas. "
            "Ce script saura la retélécharger."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
