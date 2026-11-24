"""Arborescence de la section 16 et règle d'architecture : src/ ne connaît ni api/ ni frontend/."""

import ast
import importlib
import pkgutil
from pathlib import Path

import src

RACINE = Path(__file__).resolve().parents[1]

DOSSIERS_ATTENDUS = [
    "ab_dss",
    "api",
    "frontend/src/screens",
    "frontend/src/components",
    "frontend/src/map",
    "frontend/src/theme",
    "src/data",
    "src/potentiel",
    "src/logistique",
    "src/acv",
    "src/decision",
    "src/melange",
    "src/restitution",
    "src/scenarios",
    "scripts",
    "config",
    "data/raw",
    "data/input",
    "data/processed",
    "data/versions",
    "scenarios",
    "tests/fixtures",
    "docs",
]

ECRANS = [
    "Accueil",
    "Gisements",
    "Sites",
    "BilanClimat",
    "Decision",
    "Melange",
    "FicheSite",
    "ParametresEntreprise",
    "Donnees",
]


def test_dossiers_de_la_section_16() -> None:
    manquants = [d for d in DOSSIERS_ATTENDUS if not (RACINE / d).is_dir()]
    assert manquants == []


def test_fichiers_racine() -> None:
    for nom in ["environment.yml", "README.md", "docs/methode.md", "frontend/tailwind.config.ts"]:
        assert (RACINE / nom).is_file(), nom


def test_neuf_ecrans() -> None:
    for ecran in ECRANS:
        assert (RACINE / "frontend/src/screens" / f"{ecran}.tsx").is_file(), ecran


def test_modules_src_importables() -> None:
    for module in pkgutil.walk_packages(src.__path__, prefix="src."):
        importlib.import_module(module.name)


def test_src_n_importe_ni_api_ni_frontend() -> None:
    interdits = {"api", "ab_dss", "frontend"}
    for fichier in (RACINE / "src").rglob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                racines = {alias.name.split(".")[0] for alias in noeud.names}
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                racines = {noeud.module.split(".")[0]}
            else:
                continue
            assert not racines & interdits, f"{fichier} importe {racines & interdits}"
