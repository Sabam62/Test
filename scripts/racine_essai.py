"""Prépare une copie des données réelles pour les tests de bout en bout (Playwright).

Utilisation : python -m scripts.racine_essai <dossier>

Le dossier reçoit config/ sans les fichiers locaux (modèle livré vide, RG-15),
data/input/, data/sources.yaml, data/processed/, les versions et les fichiers bruts du
référentiel (SRC-09, SRC-19). L'outil y est lancé avec AB_DSS_RACINE : les essais ne modifient
jamais les données de l'utilisateur. Un dossier existant n'est remplacé que s'il a été créé par
ce script (fichier témoin).
"""

import shutil
import sys
from pathlib import Path

from src.chemins import chemins_par_defaut
from src.data.provinces import charger_config_referentiel

TEMOIN = ".racine_essai"


def preparer(cible: Path) -> None:
    """Copie les données utiles dans ``cible``."""
    depot = chemins_par_defaut()
    if cible.exists():
        if not (cible / TEMOIN).is_file():
            raise SystemExit(f"{cible} existe et n'a pas été créé par ce script : arrêt.")
        shutil.rmtree(cible)
    cible.mkdir(parents=True)
    (cible / TEMOIN).write_text("copie d'essai\n", encoding="utf-8")
    # Les fichiers locaux (saisies de l'entreprise, réglages) ne sont jamais copiés : la copie
    # d'essai part du modèle livré vide, quelles que soient les saisies faites sur le poste.
    shutil.copytree(
        depot.config,
        cible / "config",
        ignore=shutil.ignore_patterns(
            "entreprise.local.yaml",
            "parametres_modifies.yaml",
            "sites.local.yaml",
            "decision.local.yaml",
        ),
    )
    data = cible / "data"
    shutil.copytree(depot.saisies, data / "input")
    shutil.copytree(depot.preparees, data / "processed")
    shutil.copyfile(depot.donnees / "sources.yaml", data / "sources.yaml")
    if depot.versions.is_dir():
        shutil.copytree(depot.versions, data / "versions")
    # Cache des distances et calibration du détour (RG-13) : la copie fonctionne sans OSRM.
    cache = depot.donnees / "cache" / "logistique"
    if cache.is_dir():
        shutil.copytree(cache, data / "cache" / "logistique")
    journal = depot.donnees / "versions.yaml"
    if journal.is_file():
        shutil.copyfile(journal, data / "versions.yaml")
    config = charger_config_referentiel(depot)
    for source in (config.source_noms, config.source_polygones):
        shutil.copytree(depot.brutes / source, data / "raw" / source)
    (cible / "scenarios").mkdir()
    # Scénarios de démonstration (suivis par Git) : ils se chargent dans la copie d'essai.
    demo = depot.scenarios / "demo"
    if demo.is_dir():
        shutil.copytree(demo, cible / "scenarios" / "demo")


def main() -> int:
    """Point d'entrée."""
    if len(sys.argv) != len(["programme", "dossier"]):
        print("Utilisation : python -m scripts.racine_essai <dossier>", file=sys.stderr)
        return 1
    preparer(Path(sys.argv[1]).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
