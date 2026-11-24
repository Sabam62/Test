"""Produit l'extrait figé de CROPGRIDS (SRC-04) utilisé par les tests.

Fenêtre réelle de l'archive mondiale, plus large que le Maroc (15° à 40° N, 20° O à 5° E) pour
que le découpage soit vraiment testé : grille des pays et deux cultures (olivier, blé).
Utilisation : python -m tests.fixtures.extraire_cropgrids
"""

import tempfile
import zipfile
from pathlib import Path

import xarray as xr

RACINE = Path(__file__).resolve().parents[2]
ARCHIVE = RACINE / "data/raw/SRC-04/CROPGRIDSv1.08_NC_maps.zip"
SORTIE = Path(__file__).resolve().parent / "SRC-04" / "CROPGRIDSv1.08_NC_maps_extrait.zip"
DOSSIER = "CROPGRIDSv1.08_NC_maps/"
MEMBRES = ["Countries_2018.nc", "CROPGRIDSv1.08_olive.nc", "CROPGRIDSv1.08_wheat.nc"]
FENETRE = {"lat": slice(15, 40), "lon": slice(-20, 5)}


def main() -> None:
    """Écrit l'archive extraite dans tests/fixtures/SRC-04/."""
    with (
        tempfile.TemporaryDirectory() as tmp,
        zipfile.ZipFile(ARCHIVE) as source,
        zipfile.ZipFile(SORTIE, "w", zipfile.ZIP_DEFLATED) as cible,
    ):
        for membre in MEMBRES:
            chemin = Path(source.extract(DOSSIER + membre, tmp))
            with xr.open_dataset(chemin) as ds:
                extrait = ds.sel(**FENETRE).load()
            encodage = {v: {"zlib": True, "complevel": 9} for v in extrait.data_vars}
            sortie = Path(tmp) / membre
            extrait.to_netcdf(sortie, encoding=encodage)
            cible.write(sortie, DOSSIER + membre)
    print(SORTIE, SORTIE.stat().st_size, "octets")


if __name__ == "__main__":
    main()
