"""Télécharge les sources ouvertes à adresse stable dans ``data/raw/`` (RG-01, RG-05).

Utilisation :

    python -m scripts.download                    # toutes les sources automatiques
    python -m scripts.download --source SRC-05    # une ou plusieurs sources (option répétable)

Un fichier déjà présent n'est jamais réécrit. Une source qui échoue n'arrête pas les autres ;
le message indique la procédure manuelle de ``docs/donnees_manuelles.md``.
"""

import argparse
import sys
from datetime import date

import httpx

from src.chemins import chemins_par_defaut
from src.data.telechargement import ErreurTelechargement, telecharger_tout

# Réglages réseau (techniques, pas métier) : délai d'attente d'une lecture, en secondes.
DELAI_RESEAU_S = 120.0
AGENT = "ab-dss/0.1 (outil local d'aide a la decision)"
OCTETS_PAR_MO = 1_000_000


def _mo(octets: int) -> str:
    return f"{octets / OCTETS_PAR_MO:,.1f} Mo".replace(",", " ").replace(".", ",")


def main(arguments: list[str] | None = None) -> int:
    """Point d'entrée de ``python -m scripts.download``."""
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("--source", action="append", help="identifiant SRC-xx (répétable)")
    analyseur.add_argument(
        "--retelecharger-supprimes",
        action="store_true",
        help="retélécharge aussi les fichiers supprimés volontairement (supprime_le)",
    )
    options = analyseur.parse_args(arguments)
    chemins = chemins_par_defaut()
    print("Téléchargement des sources ouvertes ; les fichiers lourds peuvent prendre du temps.")
    with httpx.Client(
        timeout=httpx.Timeout(DELAI_RESEAU_S),
        follow_redirects=True,
        headers={"User-Agent": AGENT},
    ) as client:
        try:
            resultats = telecharger_tout(
                chemins, client, date.today(), options.source, options.retelecharger_supprimes
            )
        except ErreurTelechargement as erreur:
            print(f"Erreur : {erreur}.", file=sys.stderr)
            return 1
    echecs = 0
    for resultat in resultats:
        source = resultat.source
        for nom in resultat.ecrits:
            taille = _mo(source.fichiers[nom].taille_octets)
            print(f"  {source.identifiant} : {nom} téléchargé ({taille})")
        for nom in resultat.supprimes:
            print(f"  {source.identifiant} : {nom} supprimé volontairement, non retéléchargé")
        for nom in resultat.deja_presents:
            print(f"  {source.identifiant} : {nom} déjà présent, non réécrit (RG-01)")
        if resultat.erreur:
            echecs += 1
            print(f"  {resultat.erreur}", file=sys.stderr)
    total = sum(f.stat().st_size for f in chemins.brutes.rglob("*") if f.is_file())
    print(f"Contenu de data/raw/ : {_mo(total)}. Manifeste mis à jour : data/sources.yaml.")
    if echecs:
        print(f"{echecs} source(s) à déposer à la main : voir docs/donnees_manuelles.md.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
