"""Conversion des objets de ``src/`` en JSON : tables avec provenance, valeurs sourcées."""

import math

import pandas as pd

from src.data.provenance import ValeurSourcee


def lignes(table: pd.DataFrame) -> list[dict[str, object]]:
    """Lignes d'une table ; une valeur absente (NaN) devient ``null``."""
    resultat = []
    for ligne in table.astype(object).to_dict(orient="records"):
        resultat.append(
            {k: None if isinstance(v, float) and math.isnan(v) else v for k, v in ligne.items()}
        )
    return resultat


def valeur_sourcee(valeur: ValeurSourcee | None) -> dict[str, object] | None:
    """Valeur, unité, provenance (source, année, statut, version) et fourchette (UC-01)."""
    if valeur is None:
        return None
    return valeur.model_dump(mode="json") | {"a_completer": valeur.est_a_completer}
