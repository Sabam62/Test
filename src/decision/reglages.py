"""Réglages de la décision choisis par l'utilisateur (UC-DEC-01, 02).

Critères actifs, poids, seuils, méthode, filtre de capacité.

Ils sont écrits dans ``config/decision.local.yaml`` (local, ignoré par Git) et copiés dans chaque
scénario enregistré (UC-SCN-02). Sans fichier, les critères actifs et les poids sont ceux par
défaut (section 9, PAR-45) et la méthode est PAR-40.
"""

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.decision.classement import Reglages, Seuil
from src.decision.config import CatalogueCriteres, ConfigDecision
from src.lecture_yaml import lire_yaml

FICHIER_REGLAGES = "decision.local.yaml"


class ErreurReglages(Exception):
    """Réglage refusé ; message en français."""


class SeuilUtilisateur(BaseModel):
    """Seuil éliminatoire d'un critère."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum: float | None = None
    maximum: float | None = None


class ReglagesUtilisateur(BaseModel):
    """Contenu de ``config/decision.local.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    actifs: list[str] | None = None  # None : critères actifs par défaut
    poids: dict[str, float] = {}
    seuils: dict[str, SeuilUtilisateur] = {}
    methode: str | None = None
    filtre_capacite: bool = True
    auteur: str | None = Field(default=None)


def lire_reglages(chemins: Chemins) -> ReglagesUtilisateur:
    """Réglages enregistrés, ou réglages vides."""
    fichier = chemins.config / FICHIER_REGLAGES
    if not fichier.is_file():
        return ReglagesUtilisateur()
    return ReglagesUtilisateur.model_validate(lire_yaml(fichier) or {})


def verifier(
    reglages: ReglagesUtilisateur, catalogue: CatalogueCriteres, config: ConfigDecision
) -> None:
    """Critères connus, poids positifs, méthode connue."""
    codes = set(catalogue.criteres)
    inconnus = [
        c for c in [*(reglages.actifs or []), *reglages.poids, *reglages.seuils] if c not in codes
    ]
    if inconnus:
        raise ErreurReglages(f"critères inconnus : {', '.join(sorted(set(inconnus)))}")
    negatifs = [c for c, p in reglages.poids.items() if p < 0]
    if negatifs:
        raise ErreurReglages(f"poids négatifs : {', '.join(negatifs)}")
    if reglages.methode is not None and reglages.methode not in config.methodes:
        raise ErreurReglages(
            f"méthode « {reglages.methode} » inconnue : {', '.join(config.methodes)}"
        )


def enregistrer_reglages(
    chemins: Chemins,
    reglages: ReglagesUtilisateur,
    catalogue: CatalogueCriteres,
    config: ConfigDecision,
) -> ReglagesUtilisateur:
    """Contrôle puis écrit les réglages dans le fichier local."""
    verifier(reglages, catalogue, config)
    texte = yaml.safe_dump(reglages.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
    cible = chemins.config / FICHIER_REGLAGES
    provisoire = cible.with_suffix(".tmp")
    provisoire.write_text(
        "# Réglages de la décision (écran Décision), fichier local ignoré par Git.\n" + texte,
        encoding="utf-8",
    )
    provisoire.replace(cible)
    return reglages


def reglages_de_calcul(
    reglages: ReglagesUtilisateur,
    actifs_defaut: list[str],
    methode_defaut: str,
    exclus: list[str],
    imposes: list[str],
) -> Reglages:
    """Réglages du classement : choix de l'utilisateur, sinon valeurs par défaut."""
    return Reglages(
        actifs=reglages.actifs if reglages.actifs is not None else actifs_defaut,
        poids=dict(reglages.poids),
        seuils={c: Seuil(s.minimum, s.maximum) for c, s in reglages.seuils.items()},
        methode=reglages.methode or methode_defaut,
        filtre_capacite=reglages.filtre_capacite,
        exclus=exclus,
        imposes=imposes,
    )
