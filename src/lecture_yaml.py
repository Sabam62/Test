"""Lecture des fichiers YAML et validation par un modèle pydantic, avec messages en français.

Toute erreur (fichier absent, syntaxe, clé en double, valeur invalide) devient une
:class:`ErreurConfiguration` qui nomme le fichier, l'emplacement fautif et ce qu'il faut corriger
(ENF-12).
"""

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

M = TypeVar("M", bound=BaseModel)

MESSAGES = {
    "missing": "champ obligatoire absent",
    "extra_forbidden": "champ inconnu (vérifiez l'orthographe)",
    "float_type": "doit être un nombre",
    "float_parsing": "doit être un nombre",
    "int_type": "doit être un nombre entier",
    "int_parsing": "doit être un nombre entier",
    "int_from_float": "doit être un nombre entier",
    "string_type": "doit être un texte",
    "string_too_short": "ne doit pas être vide",
    "bool_type": "doit valoir true ou false",
    "dict_type": "doit être une liste de clés et de valeurs",
    "list_type": "doit être une liste",
    "tuple_type": "doit être une liste",
    "date_type": "doit être une date au format AAAA-MM-JJ",
    "date_parsing": "doit être une date au format AAAA-MM-JJ",
    "date_from_datetime_parsing": "doit être une date au format AAAA-MM-JJ",
    "model_type": "doit être une liste de clés et de valeurs",
}

# Noms de branches d'union que pydantic ajoute à l'emplacement d'une erreur.
TYPES_UNION = frozenset({"float", "int", "str", "bool", "none"})
PREFIXES_UNION = ("list[", "dict[", "tuple[", "function-")


class ErreurConfiguration(Exception):
    """Fichier de configuration absent ou invalide ; le message dit quoi corriger."""


class _ChargeurStrict(yaml.SafeLoader):
    """Chargeur YAML qui refuse les clés en double (PyYAML garde sinon la dernière)."""


def _construire_dictionnaire(chargeur: _ChargeurStrict, noeud: yaml.MappingNode) -> dict[Any, Any]:
    vues: set[Any] = set()
    for noeud_cle, _ in noeud.value:
        cle = chargeur.construct_object(noeud_cle)
        if cle in vues:
            ligne = noeud_cle.start_mark.line + 1
            raise ErreurConfiguration(f"clé « {cle} » en double, ligne {ligne}")
        vues.add(cle)
    return chargeur.construct_mapping(noeud)


_ChargeurStrict.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construire_dictionnaire
)


def lire_yaml(chemin: Path) -> object:
    """Lit un fichier YAML ; lève :class:`ErreurConfiguration` s'il est absent ou mal formé."""
    if not chemin.is_file():
        raise ErreurConfiguration(f"Fichier introuvable : {chemin}.")
    try:
        return yaml.load(chemin.read_text(encoding="utf-8"), Loader=_ChargeurStrict)
    except ErreurConfiguration as erreur:
        raise ErreurConfiguration(f"{chemin.name} : {erreur}.") from None
    except yaml.MarkedYAMLError as erreur:
        marque = erreur.problem_mark
        ligne = f", ligne {marque.line + 1}" if marque is not None else ""
        raise ErreurConfiguration(
            f"{chemin.name} : syntaxe YAML invalide{ligne}. "
            "Vérifiez l'indentation, les deux-points et les crochets."
        ) from None


def _message(erreur: ErrorDetails) -> str:
    if erreur["type"] == "value_error":
        return str(erreur.get("ctx", {}).get("error", erreur["msg"]))
    if erreur["type"] == "enum":
        attendus = erreur.get("ctx", {}).get("expected", "")
        return f"valeur non autorisée ; valeurs possibles : {attendus}"
    return MESSAGES.get(erreur["type"], "valeur invalide")


def _est_branche_d_union(element: str | int) -> bool:
    """Vrai si ``element`` est le nom d'un type d'union ajouté par pydantic à l'emplacement."""
    if not isinstance(element, str):
        return False
    return element in TYPES_UNION or element.startswith(PREFIXES_UNION)


def traduire(erreur: ValidationError) -> list[str]:
    """Traduit les erreurs pydantic en lignes françaises « emplacement : motif ».

    Les erreurs des branches d'une union (nombre, texte…) sont fusionnées en une seule ligne.
    """
    motifs: dict[str, list[str]] = {}
    for detail in erreur.errors(include_url=False):
        loc = list(detail["loc"])
        while loc and _est_branche_d_union(loc[-1]):
            loc.pop()
        emplacement = " › ".join(str(e) for e in loc)
        motif = _message(detail)
        if motif not in motifs.setdefault(emplacement, []):
            motifs[emplacement].append(motif)
    return [
        f"{emplacement} : {' ou '.join(m)}" if emplacement else " ou ".join(m)
        for emplacement, m in motifs.items()
    ]


def valider(donnees: object, modele: type[M], nom: str) -> M:
    """Valide ``donnees`` avec ``modele`` ; ``nom`` désigne le fichier dans le message d'erreur."""
    try:
        return modele.model_validate(donnees)
    except ValidationError as erreur:
        details = "\n".join(f"  - {ligne}" for ligne in traduire(erreur))
        raise ErreurConfiguration(f"{nom} contient des erreurs :\n{details}") from None


def lire_modele(chemin: Path, modele: type[M]) -> M:
    """Lit un fichier YAML et le valide avec ``modele``."""
    return valider(lire_yaml(chemin), modele, chemin.name)
