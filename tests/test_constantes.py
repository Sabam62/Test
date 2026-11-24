"""ENF-08 : aucune constante métier dans src/ ; tout vient de config/ ou de data/."""

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

# Seuls 0 et 1 sont admis, ainsi que les indices (x[2], x[-1], x[1:3]).
ADMIS = {0, 1}


def _indices(arbre: ast.AST) -> set[int]:
    """Identifiants des nœuds situés dans l'indice d'un accès x[…]."""
    ids: set[int] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Subscript):
            ids.update(id(n) for n in ast.walk(noeud.slice))
    return ids


def _litteraux_numeriques(fichier: Path, base: Path = RACINE) -> list[str]:
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    indices = _indices(arbre)
    trouves = []
    for noeud in ast.walk(arbre):
        if (
            isinstance(noeud, ast.Constant)
            and isinstance(noeud.value, int | float | complex)
            and not isinstance(noeud.value, bool)
            and noeud.value not in ADMIS
            and id(noeud) not in indices
        ):
            trouves.append(f"{fichier.relative_to(base)}:{noeud.lineno} → {noeud.value!r}")
    return trouves


def test_aucune_constante_numerique_dans_src() -> None:
    trouves = [t for f in sorted((RACINE / "src").rglob("*.py")) for t in _litteraux_numeriques(f)]
    assert trouves == [], "constantes métier à déplacer dans config/ :\n" + "\n".join(trouves)


def test_le_detecteur_trouve_une_constante(tmp_path: Path) -> None:
    exemple = tmp_path / "exemple.py"
    exemple.write_text("CHARGE = 25\nTROISIEME = valeurs[2]\nVRAI = True\n", encoding="utf-8")
    assert _litteraux_numeriques(exemple, tmp_path) == ["exemple.py:1 → 25"]
