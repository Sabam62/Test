"""Découpage de CROPGRIDS (SRC-04) sur l'emprise du Maroc.

Les tests utilisent l'extrait réel figé tests/fixtures/SRC-04/CROPGRIDSv1.08_NC_maps_extrait.zip
(fenêtre 15° à 40° N, 20° O à 5° E de l'archive mondiale ; grille des pays, olivier et blé),
produit par tests/fixtures/extraire_cropgrids.py.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from src.chemins import Chemins, chemins_par_defaut
from src.data.cropgrids import (
    ErreurCropgrids,
    charger_config_cropgrids,
    decouper_archive,
    emprise,
    preparer_cropgrids,
)
from src.data.sources import Fichier, charger_sources, empreinte_sha256, enregistrer_sources
from tests.aides import copier_config

DEPOT = chemins_par_defaut()
EXTRAIT = DEPOT.racine / "tests/fixtures/SRC-04/CROPGRIDSv1.08_NC_maps_extrait.zip"
DOSSIER = "CROPGRIDSv1.08_NC_maps/"
DEMI_PIXEL = 0.025  # tolérance sur les coordonnées des centres de pixels (pas de 0,05°)


@pytest.fixture
def copie(tmp_path: Path) -> Chemins:
    """Racine temporaire : config/, manifeste, et l'extrait réel à la place de l'archive."""
    copier_config(DEPOT.config, tmp_path / "config")
    (tmp_path / "data").mkdir()
    shutil.copy(DEPOT.donnees / "sources.yaml", tmp_path / "data" / "sources.yaml")
    chemins = Chemins(tmp_path)
    config = charger_config_cropgrids(chemins)
    archive = chemins.brutes / "SRC-04" / config.archive
    archive.parent.mkdir(parents=True)
    shutil.copy(EXTRAIT, archive)
    manifeste = charger_sources(chemins)
    source = manifeste.sources["SRC-04"]
    fichier = Fichier(taille_octets=archive.stat().st_size, sha256=empreinte_sha256(archive))
    source = source.model_copy(update={"fichiers": {**source.fichiers, config.archive: fichier}})
    enregistrer_sources(chemins, manifeste.avec(source))
    return chemins


def _grille(nom: str) -> xr.Dataset:
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(EXTRAIT) as z:
        chemin = z.extract(DOSSIER + nom, tmp)
        with xr.open_dataset(chemin) as ds:
            return ds.load()


def test_config() -> None:
    config = charger_config_cropgrids(DEPOT)
    assert config.codes_pays == [137, 218]
    assert config.marge_pixels == 4


def test_emprise_des_codes_du_maroc_avec_marge() -> None:
    pays = _grille("Countries_2018.nc")["country"]
    lat, lon = emprise(pays, [137, 218], 4)
    decoupe = pays.isel(lat=lat, lon=lon)
    # Pixels extrêmes des codes 137 et 218 (20,825° à 35,925° N ; 17,075° à 0,975° O), ± 4 pixels.
    assert float(decoupe.lat.min()) == pytest.approx(20.625, abs=DEMI_PIXEL)
    assert float(decoupe.lat.max()) == pytest.approx(36.125, abs=DEMI_PIXEL)
    assert float(decoupe.lon.min()) == pytest.approx(-17.275, abs=DEMI_PIXEL)
    assert float(decoupe.lon.max()) == pytest.approx(-0.775, abs=DEMI_PIXEL)


def test_emprise_sans_pixel_refusee() -> None:
    pays = _grille("Countries_2018.nc")["country"]
    with pytest.raises(ErreurCropgrids, match="999"):
        emprise(pays, [999], 4)


def test_decoupage_sans_perte_sur_le_maroc(tmp_path: Path) -> None:
    config = charger_config_cropgrids(DEPOT)
    sortie = tmp_path / "cropgrids_maroc.nc"
    decouper_archive(EXTRAIT, config, sortie, {"sha256_archive": "test"})
    with xr.open_dataset(sortie) as ds:
        assert list(ds["culture"].values) == ["olive", "wheat"]
        assert set(ds.data_vars) == {*config.variables, "pays"}
        assert ds.attrs["sha256_archive"] == "test"
        assert ds.attrs["source_id"] == "SRC-04"
        sortie_olive = ds["harvarea"].sel(culture="olive")
        masque_sortie = ds["pays"].isin(config.codes_pays)
        total_sortie = float(sortie_olive.where(masque_sortie).sum())
    complet = _grille("CROPGRIDSv1.08_olive.nc")["harvarea"]
    masque = _grille("Countries_2018.nc")["country"].isin(config.codes_pays)
    total_complet = float(complet.where(masque & (complet > 0)).sum())
    assert total_complet > 0
    assert total_sortie == pytest.approx(total_complet)


def test_decoupage_reproduit_les_valeurs(tmp_path: Path) -> None:
    config = charger_config_cropgrids(DEPOT)
    sortie = tmp_path / "cropgrids_maroc.nc"
    decouper_archive(EXTRAIT, config, sortie, {})
    complet = _grille("CROPGRIDSv1.08_wheat.nc")["croparea"]
    with xr.open_dataset(sortie) as ds:
        decoupe = ds["croparea"].sel(culture="wheat")
        reference = complet.sel(lat=decoupe.lat, lon=decoupe.lon)
        np.testing.assert_array_equal(decoupe.values, reference.values)


def test_preparer_ecrit_puis_ne_refait_pas(copie: Chemins) -> None:
    appels: list[str] = []
    bilan = preparer_cropgrids(copie, lambda: appels.append("téléchargement"))
    assert bilan.ecrit
    assert appels == []
    sortie = copie.preparees / charger_config_cropgrids(copie).sortie
    date_modification = sortie.stat().st_mtime_ns
    bilan = preparer_cropgrids(copie, lambda: appels.append("téléchargement"))
    assert not bilan.ecrit
    assert sortie.stat().st_mtime_ns == date_modification


def test_archive_supprimee_mais_decoupage_a_jour(copie: Chemins) -> None:
    preparer_cropgrids(copie, lambda: None)
    config = charger_config_cropgrids(copie)
    (copie.brutes / "SRC-04" / config.archive).unlink()
    appels: list[str] = []
    bilan = preparer_cropgrids(copie, lambda: appels.append("téléchargement"))
    assert not bilan.ecrit
    assert appels == []


def test_archive_absente_retelechargee(copie: Chemins) -> None:
    config = charger_config_cropgrids(copie)
    archive = copie.brutes / "SRC-04" / config.archive
    archive.unlink()

    def retelecharger() -> None:  # rejoue le téléchargement avec l'extrait réel
        shutil.copy(EXTRAIT, archive)

    bilan = preparer_cropgrids(copie, retelecharger)
    assert bilan.retelecharge
    assert bilan.ecrit


def test_archive_absente_et_telechargement_impossible(copie: Chemins) -> None:
    (copie.brutes / "SRC-04" / charger_config_cropgrids(copie).archive).unlink()
    with pytest.raises(ErreurCropgrids, match="donnees_manuelles"):
        preparer_cropgrids(copie, lambda: None)


def test_archive_differente_du_manifeste(copie: Chemins) -> None:
    archive = copie.brutes / "SRC-04" / charger_config_cropgrids(copie).archive
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("ajout.txt", "modifié")
    with pytest.raises(ErreurCropgrids, match="empreinte"):
        preparer_cropgrids(copie, lambda: None)
