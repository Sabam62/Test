"""Emplacements des dossiers et détection des données préparées."""

from pathlib import Path

import pytest

from src.chemins import VARIABLE_RACINE, Chemins, chemins_par_defaut, donnees_preparees


def test_racine_par_defaut_est_le_depot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VARIABLE_RACINE, raising=False)
    chemins = chemins_par_defaut()
    assert (chemins.racine / "CLAUDE.md").is_file()


def test_racine_remplacee_par_la_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(VARIABLE_RACINE, str(tmp_path))
    chemins = chemins_par_defaut()
    assert chemins.racine == tmp_path.resolve()
    assert chemins.config == tmp_path.resolve() / "config"
    assert chemins.brutes == tmp_path.resolve() / "data" / "raw"
    assert chemins.manuelles == tmp_path.resolve() / "data" / "manuelles"
    assert chemins.saisies == tmp_path.resolve() / "data" / "input"
    assert chemins.preparees == tmp_path.resolve() / "data" / "processed"
    assert chemins.versions == tmp_path.resolve() / "data" / "versions"
    assert chemins.scenarios == tmp_path.resolve() / "scenarios"


def test_donnees_preparees(tmp_path: Path) -> None:
    chemins = Chemins(tmp_path)
    assert donnees_preparees(chemins) is False  # dossier absent
    chemins.preparees.mkdir(parents=True)
    (chemins.preparees / ".gitkeep").touch()
    assert donnees_preparees(chemins) is False  # dossier vide
    (chemins.preparees / "production.parquet").touch()
    assert donnees_preparees(chemins) is True
