"""Lot 3 : logistique (section 8.2, UC-LOG-01 à 04).

Données : extraits figés réels (CROPGRIDS, régions HDX, villes OpenStreetMap, matrice OSRM
réelle dans tests/fixtures/logistique/). Les valeurs encore « À compléter » dans les données
livrées (F, volume du camion, densité apparente, k_col, k_pre, prix du gazole) sont des
« saisies simulées pour le test », jamais écrites dans config/ ni data/.
"""

import json
import statistics
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
import yaml

from src.chemins import Chemins, chemins_par_defaut
from src.data.provenance import Provenance, Statut, ValeurSourcee
from src.data.tables_reference import charger_catalogue, lire_table_longue
from src.logistique.calcul import lecteur_parametres
from src.logistique.config import charger_config_logistique
from src.logistique.couts import (
    Blocage,
    courbe_approvisionnement,
    couts_livres,
    tonnage_dans_rayon,
    transport,
)
from src.logistique.distances import (
    FICHIER_CALIBRATION,
    OSRM,
    VOL_OISEAU,
    ErreurDistances,
    calibrer,
    matrice_distances,
    osrm_disponible,
    vol_oiseau_km,
)
from src.logistique.rattachement import BARYCENTRE, CENTROIDE, points_de_rattachement
from src.logistique.sites import ErreurSite, ajouter_site, chefs_lieux, supprimer_site
from src.potentiel.config import charger_config_potentiel
from src.scenarios.config import charger_controles
from src.scenarios.parametres import valeur_courante
from tests.aides import copier_config

DEPOT = chemins_par_defaut()
FIXTURES = DEPOT.racine / "tests" / "fixtures"
LOGISTIQUE = FIXTURES / "logistique"
CONFIG = charger_config_logistique(DEPOT)
MOINS_FIABLE = charger_config_potentiel(DEPOT).moins_fiable
PRECISION = 1e-3  # 0,1 %
SIMULE = "saisie simulée pour le test"
# Saisies simulées pour le test (valeurs « À compléter » dans les données livrées).
GAZOLE, COUT_FIXE, VOLUME = 12.0, 300.0, 90.0  # DH/L, DH/rotation, m³
DENSITE, K_COL, K_PRE, PRIX = 150.0, 80.0, 60.0, 200.0  # kg/m³, DH/t MS, DH/t MS, DH/t brute


def _regions() -> gpd.GeoDataFrame:
    """Deux régions réelles (HDX) utilisées comme zones de rattachement."""
    regions = gpd.read_file(FIXTURES / "production" / "hdx_regions.geojson")
    return regions.rename(columns={"adm1_pcode": "code_province", "adm1_name": "nom_fr"})


def _lieux() -> gpd.GeoDataFrame:
    table = pd.read_csv(LOGISTIQUE / "lieux_osm.csv", sep=";")
    return gpd.GeoDataFrame(
        table, geometry=gpd.points_from_xy(table["lon"], table["lat"]), crs="EPSG:4326"
    )


def _osrm() -> dict:
    return json.loads((LOGISTIQUE / "osrm_table.json").read_text(encoding="utf-8"))


def _cropgrids_olivier() -> xr.Dataset:
    archive = FIXTURES / "SRC-04" / "CROPGRIDSv1.08_NC_maps_extrait.zip"
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(archive) as z:
        chemin = z.extract("CROPGRIDSv1.08_NC_maps/CROPGRIDSv1.08_olive.nc", tmp)
        with xr.open_dataset(chemin) as ds:
            grille = ds[["croparea"]].load().expand_dims(culture=["olive"])
    grille.attrs["source_id"] = "SRC-04"
    return grille


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    copier_config(DEPOT.config, tmp_path / "config")
    (tmp_path / "data" / "input").mkdir(parents=True)
    return Chemins(tmp_path)


# --- Distances (UC-LOG-02) ------------------------------------------------------------------


def test_vol_oiseau_un_degre_a_l_equateur() -> None:
    # 1° d'arc = 2πR/360 avec R = 6 371,0088 km : 111,195 km.
    d = vol_oiseau_km(np.array(0.0), np.array(0.0), np.array(1.0), np.array(0.0), 6371.0088)
    assert float(d) == pytest.approx(2 * np.pi * 6371.0088 / 360, rel=1e-9)


def test_calibration_du_detour_sur_une_matrice_osrm_reelle() -> None:
    reponse = _osrm()
    points = np.array(reponse["points"])
    routieres = np.array(reponse["distances"][0][1:]) / 1000
    oiseau = vol_oiseau_km(
        points[0, 0], points[0, 1], points[1:, 0], points[1:, 1], CONFIG.rayon_terre_km
    )
    attendu = statistics.median(r / o for r, o in zip(routieres, oiseau, strict=True) if o > 0)
    calibration = calibrer(routieres, oiseau, "2026-11-22")
    assert calibration.coefficient == pytest.approx(attendu)
    assert 1 < calibration.coefficient < 2  # une route est plus longue que le vol d'oiseau
    assert calibration.paires == len(routieres)


def _points_et_sites() -> tuple[pd.DataFrame, pd.DataFrame]:
    reponse = _osrm()
    (x0, y0), autres = reponse["points"][0], reponse["points"][1:4]
    points = pd.DataFrame(
        {
            "code_province": ["a", "b", "c"],
            "code_residu": "R01",
            "lon": [p[0] for p in autres],
            "lat": [p[1] for p in autres],
        }
    )
    sites = pd.DataFrame({"id_site": ["AGP-MEKNES"], "lon": [x0], "lat": [y0]})
    return points, sites


def _sans_osrm(chemins: Chemins) -> None:
    """OSRM « arrêté » : adresse d'un port fermé dans la configuration de la copie."""
    fichier = chemins.config / "logistique.yaml"
    contenu = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    contenu["osrm"]["url"] = "http://127.0.0.1:9"
    contenu["osrm"]["delai_secondes"] = 1
    fichier.write_text(yaml.safe_dump(contenu, allow_unicode=True), encoding="utf-8")


def test_repli_sans_calibration_bloque_avec_le_motif(chemins: Chemins) -> None:
    _sans_osrm(chemins)
    points, sites = _points_et_sites()
    with pytest.raises(ErreurDistances, match="PAR-30"):
        matrice_distances(chemins, charger_config_logistique(chemins), points, sites, "2026-11-22")


def test_repli_osrm_arrete_vol_oiseau_fois_detour_signale(chemins: Chemins) -> None:
    _sans_osrm(chemins)
    config = charger_config_logistique(chemins)
    cache = chemins.donnees / "cache" / config.dossier_cache
    cache.mkdir(parents=True)
    calibration = {"coefficient": 1.3, "paires": 72, "date": "2026-11-22"}  # saisie simulée
    (cache / FICHIER_CALIBRATION).write_text(json.dumps(calibration), encoding="utf-8")
    points, sites = _points_et_sites()
    matrice = matrice_distances(chemins, config, points, sites, "2026-11-22")
    assert matrice.methode == VOL_OISEAU
    assert matrice.message is not None and "OSRM ne répond pas" in matrice.message
    oiseau = vol_oiseau_km(
        points["lon"].to_numpy(),
        points["lat"].to_numpy(),
        sites["lon"].iloc[0],
        sites["lat"].iloc[0],
        config.rayon_terre_km,
    )
    assert matrice.distances["distance_km"].to_numpy() == pytest.approx(oiseau * 1.3)
    assert (matrice.distances["methode"] == VOL_OISEAU).all()
    assert not list(cache.glob("distances_*.parquet"))  # un repli n'est jamais mis en cache


@pytest.mark.skipif(not osrm_disponible(CONFIG), reason="OSRM local non démarré")
def test_osrm_reel_puis_cache(chemins: Chemins) -> None:
    config = charger_config_logistique(chemins)
    points, sites = _points_et_sites()
    matrice = matrice_distances(chemins, config, points, sites, "2026-11-22")
    assert matrice.methode == OSRM
    attendu = np.array(_osrm()["distances"][0][1:4]) / 1000
    assert matrice.distances["distance_km"].to_numpy() == pytest.approx(attendu, rel=5e-3)
    _sans_osrm(chemins)  # le cache suffit tant que points et sites sont les mêmes (RG-13)
    relue = matrice_distances(
        chemins, charger_config_logistique(chemins), points, sites, "2026-11-22"
    )
    assert relue.methode == OSRM
    pd.testing.assert_frame_equal(relue.distances, matrice.distances)


# --- Rattachement et sites (H1, UC-LOG-01) ---------------------------------------------------


def test_rattachement_au_barycentre_cropgrids_sinon_centroide() -> None:
    regions = _regions()
    points = points_de_rattachement(
        _cropgrids_olivier(),
        regions,
        pd.DataFrame({"code_culture": ["olivier", "arganier"], "code_cropgrids": ["olive", ""]}),
        {"R01": ["olivier"], "R09": ["arganier"]},
        "croparea",
        "EPSG:4326",
        "+proj=cea +lon_0=0 +lat_ts=30 +datum=WGS84 +units=km +no_defs",
        2020,
    )
    assert len(points) == 4
    olivier = points[points["code_residu"] == "R01"]
    assert (olivier["methode"] == BARYCENTRE).all()
    for ligne in olivier.itertuples():
        zone = regions.set_index("code_province").geometry[ligne.code_province]
        assert zone.contains(gpd.points_from_xy([ligne.lon], [ligne.lat])[0])
    argan = points[points["code_residu"] == "R09"]
    assert (argan["methode"] == CENTROIDE).all()
    assert (points["statut"] == Statut.ESTIMEE.value).all()


def test_chef_lieu_par_nom_sinon_ville_la_plus_peuplee() -> None:
    regions = _regions()
    regions.loc[regions["code_province"] == "MA004", "nom_fr"] = "Taza"  # nom à retrouver
    sites = chefs_lieux(_lieux(), regions, "+proj=cea +lat_ts=30 +units=km", 2026).set_index(
        "code_province"
    )
    assert sites.loc["MA004", "nom"] == "Taza"
    assert "même nom" in sites.loc["MA004", "note"]
    lieux = _lieux()
    oriental = gpd.sjoin(lieux, regions[regions["code_province"] == "MA007"])
    assert sites.loc["MA007", "nom"] == oriental.sort_values("population").iloc[-1]["nom"]
    assert "plus peuplée" in sites.loc["MA007", "note"]


def test_site_utilisateur_ajoute_puis_retire(chemins: Chemins) -> None:
    config = charger_config_logistique(chemins)
    regions = _regions()
    site = ajouter_site(chemins, config, regions, "Plateforme de Taza", -4.01, 34.21, "équipe")
    assert site["id_site"] == "UT-1" and site["code_province"] == "MA004"
    with pytest.raises(ErreurSite, match="hors des 75 provinces"):
        ajouter_site(chemins, config, regions, "Mer", -9.9, 34.0, "équipe")
    with pytest.raises(ErreurSite, match="nom"):
        ajouter_site(chemins, config, regions, " ", -4.01, 34.21, "équipe")
    supprimer_site(chemins, config, "UT-1")
    with pytest.raises(ErreurSite, match="inconnu"):
        supprimer_site(chemins, config, "UT-1")


# --- Coût livré, courbe et bassin (UC-LOG-03, 04) --------------------------------------------


def _simulee(nom: str, valeur: float, unite: str) -> ValeurSourcee:
    return ValeurSourcee(
        nom=nom,
        valeur=valeur,
        unite=unite,
        provenance=Provenance(source_id=SIMULE, annee=2026, statut=Statut.TERRAIN),
    )


def _lire_simule(identifiant: str) -> ValeurSourcee:
    p = CONFIG.parametres
    simules = {
        p.prix_gazole: _simulee(p.prix_gazole, GAZOLE, "DH/L"),
        p.cout_fixe: _simulee(p.cout_fixe, COUT_FIXE, "DH/rotation"),
        p.volume_utile: _simulee(p.volume_utile, VOLUME, "m³"),
    }
    return simules.get(identifiant) or valeur_courante(DEPOT, identifiant)


def _tables(tmp_path: Path) -> tuple:
    """residus.csv et concurrence.csv livrés, R03 complété par des saisies simulées."""
    residus = pd.read_csv(DEPOT.saisies / "residus.csv", sep=";", dtype=str, keep_default_na=False)
    for parametre, valeur in (
        ("densite_apparente", DENSITE),
        ("k_col", K_COL),
        ("k_pre", K_PRE),
    ):
        masque = (residus["code_residu"] == "R03") & (residus["parametre"] == parametre)
        residus.loc[masque, ["valeur", "source_id", "annee", "ou_trouver"]] = [
            str(valeur),
            SIMULE,
            "2026",
            "",
        ]
    concurrence = pd.read_csv(
        DEPOT.saisies / "concurrence.csv", sep=";", dtype=str, keep_default_na=False
    )
    masque = (concurrence["code_residu"] == "R03") & (concurrence["parametre"] == "prix_achat_dh_t")
    concurrence.loc[masque, ["valeur", "source_id", "annee", "ou_trouver"]] = [
        str(PRIX),
        SIMULE,
        "2026",
        "",
    ]
    residus.to_csv(tmp_path / "residus.csv", sep=";", index=False)
    concurrence.to_csv(tmp_path / "concurrence.csv", sep=";", index=False)
    catalogue, controles = charger_catalogue(DEPOT), charger_controles(DEPOT)
    return (
        lire_table_longue(
            tmp_path / "residus.csv", ["code_residu"], catalogue.residus, controles, "residus"
        ),
        lire_table_longue(
            tmp_path / "concurrence.csv",
            ["code_province", "code_residu"],
            catalogue.concurrence,
            controles,
            "concurrence",
        ),
    )


def _gisements_et_distances() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trois couples R03 aux distances OSRM réelles de l'extrait (tonnages : saisie simulée)."""
    distances = np.array(_osrm()["distances"][0][1:4]) / 1000
    gisements = pd.DataFrame(
        {
            "code_province": ["a", "b", "c"],
            "code_residu": "R03",
            "valeur": [4000.0, 3000.0, 5000.0],
            "statut": Statut.ESTIMEE.value,
        }
    )
    table = pd.DataFrame(
        {
            "code_province": ["a", "b", "c"],
            "code_residu": "R03",
            "id_site": "AGP-MEKNES",
            "distance_km": distances,
            "duree_min": np.nan,
            "methode": OSRM,
        }
    )
    return gisements, table


def test_un_trajet_recalcule_a_la_main(tmp_path: Path) -> None:
    residus, concurrence = _tables(tmp_path)
    camion = transport(_lire_simule, CONFIG, MOINS_FIABLE)
    gisements, distances = _gisements_et_distances()
    couts, exclus = couts_livres(
        gisements, distances, residus, concurrence, camion, CONFIG, "NATIONAL", MOINS_FIABLE
    )
    assert exclus.empty
    # Calcul indépendant : v = 0,35 L/km × 12 DH/L ÷ 0,39 ; q = min(25 t, 0,150 × 90) × (1 − h).
    h = float(residus.valeur("R03", "humidite").lire_nombre()) / 100
    v = (35 / 100) * GAZOLE / (39 / 100)
    q = min(25, DENSITE / 1000 * VOLUME) * (1 - h)
    for ligne in couts.itertuples():
        attendu = PRIX / (1 - h) + K_COL + K_PRE + (COUT_FIXE + v * 2 * ligne.distance_km) / q
        assert ligne.cout_livre == pytest.approx(attendu, rel=PRECISION)
    assert set(couts["statut"]) == {Statut.ESTIMEE.value}  # M estimé, le moins fiable


def test_courbe_cout_moyen_et_marginal_a_k(tmp_path: Path) -> None:
    residus, concurrence = _tables(tmp_path)
    camion = transport(_lire_simule, CONFIG, MOINS_FIABLE)
    gisements, distances = _gisements_et_distances()
    couts, _ = couts_livres(
        gisements, distances, residus, concurrence, camion, CONFIG, "NATIONAL", MOINS_FIABLE
    )
    tries = couts.sort_values("cout_livre").reset_index(drop=True)
    k = float(tries["tonnage"].iloc[0] + tries["tonnage"].iloc[1] / 2)  # saisie simulée
    plafond = float(tries["cout_livre"].max()) + 1
    courbe = courbe_approvisionnement(couts, k, plafond, None)
    assert courbe.points["cout_livre"].is_monotonic_increasing
    assert courbe.atteignable and courbe.manque == 0
    t0, t1 = tries["tonnage"].iloc[0], tries["tonnage"].iloc[1] / 2
    moyen = (tries["cout_livre"].iloc[0] * t0 + tries["cout_livre"].iloc[1] * t1) / (t0 + t1)
    assert courbe.cout_moyen_k == pytest.approx(moyen)
    assert courbe.cout_marginal_k == pytest.approx(tries["cout_livre"].iloc[1])
    assert courbe.retenus["tonnage_retenu"].sum() == pytest.approx(k)
    # Prix plafond sous le 2e couple : capacité non atteignable, manque donné (RG-10).
    bas = courbe_approvisionnement(couts, k, float(tries["cout_livre"].iloc[0]), None)
    assert not bas.atteignable
    assert bas.manque == pytest.approx(k - tries["tonnage"].iloc[0])
    assert bas.cout_moyen_k is None
    # Distance maximale PAR-59 : les couples plus lointains sont écartés.
    proche = courbe_approvisionnement(couts, k, plafond, float(couts["distance_km"].min()))
    assert len(proche.points) == 1


def test_c3_tonnage_dans_le_rayon() -> None:
    gisements, distances = _gisements_et_distances()
    rayon = float(np.sort(distances["distance_km"])[1])
    attendu = gisements.set_index("code_province").loc[
        distances.loc[distances["distance_km"] <= rayon, "code_province"], "valeur"
    ]
    assert tonnage_dans_rayon(gisements, distances, rayon) == pytest.approx(attendu.sum())


def test_transport_bloque_liste_toutes_les_valeurs_a_saisir(chemins: Chemins) -> None:
    with pytest.raises(Blocage) as erreur:
        transport(lecteur_parametres(chemins), CONFIG, MOINS_FIABLE)
    message = str(erreur.value)
    for identifiant in ("PAR-37", "PAR-61", "PAR-32"):
        assert identifiant in message
    assert "onglet Paramètres, section Entreprise" in message  # RG-15 : renvoi vers le champ


def test_couple_sans_donnee_exclu_avec_le_motif(tmp_path: Path) -> None:
    residus, concurrence = _tables(tmp_path)
    camion = transport(_lire_simule, CONFIG, MOINS_FIABLE)
    gisements, distances = _gisements_et_distances()
    gisements["code_residu"] = distances["code_residu"] = "R02"  # humidité à compléter
    couts, exclus = couts_livres(
        gisements, distances, residus, concurrence, camion, CONFIG, "NATIONAL", MOINS_FIABLE
    )
    assert couts.empty and len(exclus) == 3
    assert exclus["motif"].str.contains("R02 · humidite à compléter").all()


def test_chef_lieu_administratif_designe_prioritaire() -> None:
    regions = _regions()
    designations = {
        "MA007": {"chef_lieu": "Berkane (désigné)", "nom_osm": "Berkane", "note": SIMULE}
    }
    sites = chefs_lieux(
        _lieux(), regions, "+proj=cea +lat_ts=30 +units=km", 2026, designations
    ).set_index("code_province")
    assert sites.loc["MA007", "nom"] == "Berkane (désigné)"
    assert "chef-lieu administratif" in sites.loc["MA007", "note"]
    berkane = _lieux().set_index("nom").loc["Berkane"]
    assert sites.loc["MA007", "lon"] == pytest.approx(berkane["lon"])
