"""Découpage de CROPGRIDS (SRC-04) sur l'emprise du Maroc.

L'archive mondiale ``data/raw/SRC-04/CROPGRIDSv1.08_NC_maps.zip`` est lue sans être modifiée
(RG-01). L'emprise est déduite des données, pas écrite en dur : ce sont les pixels de la grille
des pays de CROPGRIDS dont le numéro figure dans ``config/cropgrids.yaml``, plus une marge.
Le résultat, un seul NetCDF (dimensions culture × lat × lon), est écrit dans ``data/processed/``
avec sa provenance (source, empreinte de l'archive, version, réglages).

Si l'archive a été supprimée après un découpage à jour, rien n'est refait ; si le découpage
manque et l'archive aussi, l'archive est retéléchargée par la fonction fournie par l'appelant.
"""

import os
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import xarray as xr
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.data.sources import charger_sources, empreinte_sha256
from src.lecture_yaml import lire_modele

FICHIER_CONFIG = "cropgrids.yaml"
SOURCE_ID = "SRC-04"
SUFFIXE_NETCDF = ".nc"


class ErreurCropgrids(Exception):
    """Découpage impossible ; le message dit quoi faire, en français."""


class ConfigCropgrids(BaseModel):
    """Contenu de ``config/cropgrids.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    archive: str = Field(min_length=1)
    grille_pays: str = Field(min_length=1)
    codes_pays: list[int] = Field(min_length=1)
    marge_pixels: int = Field(ge=0)
    variables: list[str] = Field(min_length=1)
    compression: int = Field(ge=0)
    sortie: str = Field(min_length=1)


@dataclass(frozen=True)
class BilanCropgrids:
    """Résultat de :func:`preparer_cropgrids`."""

    sortie: Path
    ecrit: bool
    retelecharge: bool


def charger_config_cropgrids(chemins: Chemins) -> ConfigCropgrids:
    """Lit et valide ``config/cropgrids.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigCropgrids)


def emprise(pays: xr.DataArray, codes: list[int], marge: int) -> tuple[slice, slice]:
    """Tranches d'indices (lat, lon) des pixels portant ``codes``, élargies de ``marge`` pixels."""
    masque = pays.isin(codes)
    lignes = np.flatnonzero(masque.any("lon").values)
    colonnes = np.flatnonzero(masque.any("lat").values)
    if lignes.size == 0:
        raise ErreurCropgrids(
            f"aucun pixel de la grille des pays ne porte les numéros {codes} : "
            "vérifiez codes_pays dans config/cropgrids.yaml"
        )

    def tranche(indices: np.ndarray, taille: int) -> slice:
        return slice(
            max(0, int(indices.min()) - marge), min(taille, int(indices.max()) + marge + 1)
        )

    return tranche(lignes, pays.sizes["lat"]), tranche(colonnes, pays.sizes["lon"])


def _membres(archive: zipfile.ZipFile, config: ConfigCropgrids) -> tuple[str, list[str]]:
    noms = [n for n in archive.namelist() if n.endswith(SUFFIXE_NETCDF)]
    pays = [n for n in noms if Path(n).name == config.grille_pays]
    if not pays:
        raise ErreurCropgrids(f"{config.grille_pays} absent de l'archive {config.archive}")
    return pays[0], sorted(n for n in noms if n != pays[0])


def _culture(membre: str) -> str:
    """« CROPGRIDSv1.08_olive.nc » → « olive »."""
    return Path(membre).stem.split("_", 1)[-1]


def decouper_archive(
    archive: Path, config: ConfigCropgrids, sortie: Path, provenance: dict[str, str]
) -> None:
    """Écrit dans ``sortie`` l'emprise du Maroc de toutes les cultures de ``archive``."""
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(archive) as zip_:
        membre_pays, membres = _membres(zip_, config)
        with xr.open_dataset(zip_.extract(membre_pays, tmp)) as grille:
            pays_monde = grille["country"]
            lat, lon = emprise(pays_monde, config.codes_pays, config.marge_pixels)
            pays = pays_monde.isel(lat=lat, lon=lon).load()
        Path(tmp, membre_pays).unlink()
        cultures, attributs = [], {}
        for membre in membres:
            chemin = Path(zip_.extract(membre, tmp))
            with xr.open_dataset(chemin) as ds:
                manquantes = [v for v in config.variables if v not in ds]
                if manquantes:
                    raise ErreurCropgrids(f"{membre} : variables absentes {manquantes}")
                cultures.append(ds[config.variables].isel(lat=lat, lon=lon).load())
                attributs = dict(ds.attrs)
            chemin.unlink()
    donnees = xr.concat(cultures, dim="culture")
    donnees = donnees.assign_coords(culture=[_culture(m) for m in membres])
    donnees["pays"] = pays
    donnees.attrs = {
        "source_id": SOURCE_ID,
        "titre": "CROPGRIDS, emprise du Maroc (12 régions du RGPH 2024)",
        "archive": archive.name,
        "version_cropgrids": str(attributs.get("Version", "")),
        "auteurs_cropgrids": str(attributs.get("Authors", "")),
        "codes_pays": ", ".join(str(c) for c in config.codes_pays),
        "marge_pixels": str(config.marge_pixels),
        "date_decoupage": date.today().isoformat(),
        **provenance,
    }
    encodage = {
        v: {"zlib": True, "complevel": config.compression} for v in [*config.variables, "pays"]
    }
    sortie.parent.mkdir(parents=True, exist_ok=True)
    provisoire = sortie.with_name(sortie.name + ".part")
    try:
        donnees.to_netcdf(provisoire, encoding=encodage)
        os.replace(provisoire, sortie)
    finally:
        provisoire.unlink(missing_ok=True)


def _sha256_enregistre(chemins: Chemins, config: ConfigCropgrids) -> str | None:
    fichier = charger_sources(chemins).sources[SOURCE_ID].fichiers.get(config.archive)
    return fichier.sha256 if fichier else None


def _a_jour(sortie: Path, sha256: str | None) -> bool:
    if sha256 is None or not sortie.is_file():
        return False
    with xr.open_dataset(sortie) as ds:
        return ds.attrs.get("sha256_archive") == sha256


def preparer_cropgrids(chemins: Chemins, retelecharger: Callable[[], object]) -> BilanCropgrids:
    """Découpe l'archive CROPGRIDS si le découpage manque ou date d'une autre archive.

    Args:
        chemins: dossiers de l'outil.
        retelecharger: appelée si l'archive est absente ; doit la déposer dans
            ``data/raw/SRC-04/`` et mettre à jour le manifeste (``scripts.download``).
    """
    config = charger_config_cropgrids(chemins)
    sortie = chemins.preparees / config.sortie
    archive = chemins.brutes / SOURCE_ID / config.archive
    if _a_jour(sortie, _sha256_enregistre(chemins, config)):
        return BilanCropgrids(sortie, ecrit=False, retelecharge=False)
    retelecharge = False
    if not archive.is_file():
        retelecharger()
        retelecharge = True
        if not archive.is_file():
            raise ErreurCropgrids(
                f"l'archive {config.archive} est absente et n'a pas pu être retéléchargée : "
                "voir docs/donnees_manuelles.md, section SRC-04"
            )
    attendu = _sha256_enregistre(chemins, config)
    reelle = empreinte_sha256(archive)
    if attendu is not None and reelle != attendu:
        raise ErreurCropgrids(
            f"l'empreinte de {config.archive} ne correspond pas au manifeste data/sources.yaml : "
            "le fichier a été modifié ou remplacé (RG-01). Supprimez-le puis relancez "
            "« python -m scripts.download --source SRC-04 »"
        )
    decouper_archive(archive, config, sortie, {"sha256_archive": reelle})
    return BilanCropgrids(sortie, ecrit=True, retelecharge=retelecharge)
