"""Préparation des données : lecture, contrôles, désagrégation RG-04 (UC-DAT-01, 02, 04).

Les tests unitaires utilisent tests/fixtures/production/ (extrait figé des données réelles,
produit par tests/fixtures/extraire_production.py) et le référentiel de tests/fixtures/
referentiel/. Les tests « donnees_reelles » lisent data/ et sont ignorés s'il manque.
"""

import shutil
from functools import cache
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
import xarray as xr

from src.chemins import Chemins, chemins_par_defaut
from src.data.config_preparation import charger_config_preparation
from src.data.controles import (
    _plages,
    couverture,
    format_fr,
    provinces_sans_production,
    rendre_rapport,
    signaler_aberrantes,
)
from src.data.lecteurs.rgph2024 import unites_rgph2024
from src.data.lecteurs.src18 import lire_src18
from src.data.observations import (
    BilanControle,
    Categorie,
    ErreurPreparation,
    annee_campagne,
    campagne_precedente,
    campagne_valide,
)
from src.data.preparation import (
    Statistiques,
    fichiers_requis,
    statistiques,
    verifier_fichiers,
)
from src.data.provenance import Statut
from src.data.provinces import (
    ErreurRattachement,
    Referentiel,
    charger_config_referentiel,
    charger_variantes,
    construire_referentiel,
)
from src.data.surfaces import fractions_pixels
from src.scenarios.config import RegleAberrantes, charger_controles
from tests.aides import copier_config

DEPOT = chemins_par_defaut()
FIXTURES = DEPOT.racine / "tests" / "fixtures"
PRODUCTION = FIXTURES / "production"
CONFIG = charger_config_preparation(DEPOT)
CONTROLES = charger_controles(DEPOT)
TOLERANCE = CONTROLES.desagregation.tolerance_somme
CULTURES = set(pd.read_csv(DEPOT.saisies / "cultures.csv", sep=";")["code_culture"])
FES_MEKNES = "3"
FES, MOULAY_YACOUB = "3231", "3591"
ORIENTAL, FIGUIG = "2", "2251"
# Production d'olives 2017-2018 de la DRA Fès-Meknès (§14.2, Infomédiaire).
TOTAL_FES_MEKNES_2017_2018 = 1027573
VALEUR_FES_ET_MOULAY_YACOUB = 99528
TAOUNATE, VALEUR_TAOUNATE = "3531", 370028
# Total national d'olives 2017/2018 de SRC-01 (ligne du fichier Open Data).
NATIONAL_OLIVIER_2017_2018 = 1561465.0


@cache
def _referentiel() -> Referentiel:
    config = charger_config_referentiel(DEPOT)
    dossier = FIXTURES / "referentiel"
    lignes = pd.read_csv(dossier / "rgph2024_lignes.csv", sep=";", dtype=str)
    referentiel = construire_referentiel(
        unites_rgph2024(lignes),
        pd.read_csv(dossier / "hcp_regions.csv", sep=";"),
        pd.read_csv(dossier / "hcp_provinces.csv", sep=";"),
        config,
    )
    return referentiel.avec_variantes(charger_variantes(DEPOT.saisies / config.fichier_variantes))


def _surfaces() -> pd.DataFrame:
    return pd.read_csv(PRODUCTION / "surfaces_cropgrids.csv", sep=";", dtype={"code_province": str})


def _statistiques(dossier_src18: Path = PRODUCTION / "SRC-18") -> Statistiques:
    return statistiques(
        dossier_src18,
        PRODUCTION / "SRC-01",
        CONFIG,
        CONTROLES,
        _referentiel(),
        CULTURES,
        _surfaces(),
    )


@pytest.fixture(scope="module")
def stats() -> Statistiques:
    return _statistiques()


def _production(stats: Statistiques, culture: str, campagne: str) -> pd.DataFrame:
    p = stats.resultat.production
    return p[
        (p["variable"] == "production_t")
        & (p["code_culture"] == culture)
        & (p["campagne"] == campagne)
    ].set_index("code_province")


def _copie_src18(tmp_path: Path) -> Path:
    cible = tmp_path / "SRC-18"
    shutil.copytree(PRODUCTION / "SRC-18", cible)
    return cible


# --- Campagnes ----------------------------------------------------------------------------


def test_campagnes() -> None:
    assert campagne_valide("2017-2018")
    assert not campagne_valide("2017-2019")
    assert not campagne_valide("2017/2018")
    assert annee_campagne("2017-2018") == 2018
    assert campagne_precedente("2018-2019") == "2017-2018"


# --- UC-DAT-01 : fichier manquant -----------------------------------------------------------


def test_fichier_src18_manquant_message_clair(tmp_path: Path) -> None:
    dossier = _copie_src18(tmp_path)
    (dossier / CONFIG.src18.verifiees).unlink()
    with pytest.raises(ErreurPreparation, match=r"valeurs_verifiees\.csv est absent"):
        _statistiques(dossier)


def test_preparation_arretee_si_fichiers_bruts_manquent(tmp_path: Path) -> None:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    with pytest.raises(ErreurPreparation, match="fichiers bruts manquants") as erreur:
        verifier_fichiers(chemins, CONFIG)
    assert "valeurs_saisies.csv" in str(erreur.value)
    assert str(Path("data/manuelles/SRC-18/valeurs_saisies.csv")) in str(erreur.value)
    assert "docs/donnees_manuelles.md" in str(erreur.value)


def test_tables_saisies_par_l_equipe_versionnees_dans_le_depot() -> None:
    # Une installation neuve (clone du dépôt) doit trouver les tables SRC-18 sans dépôt manuel.
    manuelles = [f for f in fichiers_requis(DEPOT, CONFIG) if DEPOT.manuelles in f.parents]
    assert {f.name for f in manuelles} == {
        CONFIG.src18.saisies,
        CONFIG.src18.verifiees,
        CONFIG.src18.references,
    }
    assert all(f.is_file() for f in manuelles)


def test_colonne_absente_message_clair(tmp_path: Path) -> None:
    dossier = _copie_src18(tmp_path)
    chemin = dossier / CONFIG.src18.references
    table = pd.read_csv(chemin, sep=";", dtype=str).drop(columns=["source_parente"])
    table.to_csv(chemin, sep=";", index=False)
    with pytest.raises(ErreurPreparation, match="colonnes absentes source_parente"):
        _statistiques(dossier)


# --- UC-DAT-02 : contrôles -----------------------------------------------------------------


def test_lignes_non_verifiees_rejetees(stats: Statistiques) -> None:
    table = stats.bilan.tableau()
    medias24 = table[(table["fichier"] == CONFIG.src18.saisies) & table["ligne"].between(36, 40)]
    assert set(medias24["categorie"]) == {Categorie.REJETEE}
    assert medias24["motif"].str.contains("non vérifiée").all()
    assert not (stats.observations["document"] == "national_2023-2024_palmier.html").any()


def test_lignes_sans_campagne_non_utilisees(stats: Statistiques) -> None:
    table = stats.bilan.tableau()
    taounate = table[(table["fichier"] == CONFIG.src18.saisies) & (table["ligne"] == 46)]
    assert taounate["categorie"].tolist() == [Categorie.NON_UTILISEE]
    assert "moyenne" in taounate["motif"].iloc[0]


def test_src01_campagnes_sans_maille_rejetees(stats: Statistiques) -> None:
    obs = stats.observations
    src01 = obs[obs["source_id"] == "SRC-01"]
    assert not src01["campagne"].isin(["2020-2021", "2021-2022"]).any()
    table = stats.bilan.tableau()
    rejets = table[(table["source_id"] == "SRC-01") & (table["categorie"] == Categorie.REJETEE)]
    assert rejets["motif"].str.contains("sans colonne géographique").all()
    assert (table["motif"] == "produit hors des cultures de cultures.csv").any()


def test_src01_total_national_et_somme_des_produits(stats: Statistiques) -> None:
    obs = stats.observations

    def national(culture: str) -> float:
        choix = obs[
            (obs["source_id"] == "SRC-01")
            & (obs["code_culture"] == culture)
            & (obs["campagne"] == "2017-2018")
            & (obs["variable"] == "production_t")
        ]
        assert len(choix) == 1
        return float(choix["valeur"].iloc[0])

    assert national("olivier") == pytest.approx(NATIONAL_OLIVIER_2017_2018, rel=1e-6)
    brut = pd.read_excel(PRODUCTION / "SRC-01" / CONFIG.src01.fichier)
    brut.columns = [c.strip() for c in brut.columns]
    attendu = brut[
        brut["Produit"].isin(["Blé dur", "Blé tendre"])
        & (brut["Occurrence"] == "2017/2018")
        & (brut["Indicateur"] == "Production-T (Tonnes)")
    ]["Valeur"].sum()
    assert national("ble") == pytest.approx(attendu)


def test_doublon_de_meme_valeur_garde_une_seule_ligne(tmp_path: Path) -> None:
    dossier = _copie_src18(tmp_path)
    for nom in (CONFIG.src18.saisies, CONFIG.src18.verifiees):
        chemin = dossier / nom
        table = pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False)
        pd.concat([table, table.iloc[[0]]]).to_csv(chemin, sep=";", index=False)
    stats = _statistiques(dossier)
    assert stats.bilan.compter(Categorie.DOUBLON, "SRC-18") == 1
    taounate = _production(stats, "olivier", "2017-2018").loc[TAOUNATE]
    assert taounate["valeur"] == VALEUR_TAOUNATE


def test_aberrantes_signalees_au_seuil_de_la_configuration(stats: Statistiques) -> None:
    bilan = BilanControle()
    assert signaler_aberrantes(stats.observations, bilan, CONTROLES.aberrantes).empty
    # Seuil abaissé à un écart type : la campagne record 2018-2019 de SRC-01 sort de la série.
    regle = RegleAberrantes(ecarts_types=1, effectif_minimal=3, motif="test du seuil")
    hors = signaler_aberrantes(stats.observations, bilan, regle)
    olivier = hors[(hors["code_culture"] == "olivier") & (hors["variable"] == "production_t")]
    assert "2018-2019" in set(olivier["campagne"])
    assert bilan.compter(Categorie.ABERRANTE) == len(hors)


def test_province_inconnue_bloque_l_import(tmp_path: Path) -> None:
    dossier = _copie_src18(tmp_path)
    for nom in (CONFIG.src18.saisies, CONFIG.src18.verifiees):
        chemin = dossier / nom
        table = pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False)
        table.loc[0, "province"] = "Taounat"  # faute de frappe : variante inconnue
        table.to_csv(chemin, sep=";", index=False)
    with pytest.raises(ErreurRattachement, match="ligne 1 « Taounat »"):
        lire_src18(dossier, CONFIG.src18, _referentiel(), CULTURES, BilanControle())


def test_rapport_contient_les_categories_par_source(stats: Statistiques) -> None:
    provinces = _referentiel().provinces
    html = rendre_rapport(stats.bilan, stats.resultat, provinces, {"SRC-18": "Communiqués DRA"})
    for categorie in Categorie:
        assert categorie.value.capitalize() in html
    for fichier in (CONFIG.src18.saisies, CONFIG.src01.fichier):
        assert fichier in html
    assert "75 provinces sur 75" in html


# --- UC-DAT-04 : désagrégation RG-04 --------------------------------------------------------


def test_valeurs_provinciales_reelles_gardees(stats: Statistiques) -> None:
    fm = _production(stats, "olivier", "2017-2018")
    taounate = fm.loc[TAOUNATE]
    assert taounate["valeur"] == VALEUR_TAOUNATE
    assert taounate["statut"] == Statut.MESUREE
    assert taounate["source_id"] == "SRC-18"


def test_groupe_fes_moulay_yacoub_reparti(stats: Statistiques) -> None:
    fm = _production(stats, "olivier", "2017-2018")
    groupe = fm.loc[[FES, MOULAY_YACOUB]]
    assert groupe["valeur"].sum() == pytest.approx(VALEUR_FES_ET_MOULAY_YACOUB)
    assert set(groupe["statut"]) == {Statut.ESTIMEE}
    assert groupe["part_cropgrids"].sum() == pytest.approx(1)


def test_somme_provinciale_egale_total_regional(stats: Statistiques) -> None:
    controles = stats.resultat.controles
    regionaux = controles[controles["niveau"] == "region"]
    assert not regionaux.empty
    assert regionaux["conforme"].all()
    production = stats.resultat.production
    region_de = _referentiel().provinces.set_index("code_province")["code_region"]
    for _, total in regionaux.iterrows():
        sous = production[
            (production["variable"] == total["variable"])
            & (production["code_culture"] == total["code_culture"])
            & (production["campagne"] == total["campagne"])
            & (production["code_province"].map(region_de) == total["code_zone"])
        ]
        assert sous["valeur"].sum() == pytest.approx(total["total"], rel=TOLERANCE)


def test_fes_meknes_2017_2018_egale_le_total_de_la_dra(stats: Statistiques) -> None:
    fm = _production(stats, "olivier", "2017-2018")
    region_de = _referentiel().provinces.set_index("code_province")["code_region"]
    somme = fm[fm.index.map(region_de) == FES_MEKNES]["valeur"].sum()
    assert somme == pytest.approx(TOTAL_FES_MEKNES_2017_2018, rel=TOLERANCE)


def test_somme_nationale_et_estimees_tracees(stats: Statistiques) -> None:
    olivier = _production(stats, "olivier", "2017-2018")
    assert len(olivier) == len(_referentiel().provinces)
    assert olivier["valeur"].sum() == pytest.approx(NATIONAL_OLIVIER_2017_2018, rel=TOLERANCE)
    estimees = stats.resultat.production
    estimees = estimees[estimees["statut"] == Statut.ESTIMEE]
    reparties = estimees["part_cropgrids"].notna()
    assert estimees.loc[reparties, "source_total"].notna().all()
    # Les autres valeurs « Estimée » sont des prévisions publiées à la maille provinciale.
    assert estimees.loc[~reparties, "previsionnel"].all()
    assert estimees.loc[reparties, "part_cropgrids"].between(0, 1).all()
    assert estimees["campagne"].notna().all()
    nationales = olivier[olivier["niveau_source"] == "national"]
    assert set(nationales["source_id"]) == {"SRC-01"}


def test_prevision_signalee_sur_les_estimees(stats: Statistiques) -> None:
    # Oriental 2023-2024 : total régional prévisionnel de la DRA (208 000 t).
    oriental = _production(stats, "olivier", "2023-2024")
    region_de = _referentiel().provinces.set_index("code_province")["code_region"]
    oriental = oriental[
        (oriental["niveau_source"] == "region") & (oriental.index.map(region_de) == ORIENTAL)
    ]
    assert not oriental.empty
    assert oriental["previsionnel"].all()


def test_toute_valeur_repartie_est_estimee(stats: Statistiques) -> None:
    production = stats.resultat.production
    reparties = production[production["part_cropgrids"].notna()]
    assert not reparties.empty
    assert set(reparties["statut"]) == {Statut.ESTIMEE}
    assert set(_production(stats, "olivier", "2017-2018").loc[[FES, MOULAY_YACOUB], "statut"]) == {
        Statut.ESTIMEE
    }


def test_prevision_au_statut_estimee(stats: Statistiques) -> None:
    obs = stats.observations
    previsions = obs[obs["previsionnel"]]
    assert not previsions.empty
    assert set(previsions["statut"]) == {Statut.ESTIMEE}
    assert set(obs.loc[~obs["previsionnel"], "statut"]) == {Statut.MESUREE}
    # Taounate 2018-2019 : prévision de la DRA, gardée à la maille provinciale.
    taounate = _production(stats, "olivier", "2018-2019").loc[TAOUNATE]
    assert taounate["statut"] == Statut.ESTIMEE and taounate["previsionnel"]
    assert taounate["niveau_source"] == "province"


def test_ecart_de_campagne_des_valeurs_soustraites(stats: Statistiques) -> None:
    """Olivier 2017-2018 : le total national (campagne) soustrait les provinces de
    Tanger-Tétouan-Al Hoceima, estimées d'un total publié pour l'année civile 2017."""
    olivier = _production(stats, "olivier", "2017-2018")
    nationales = olivier[olivier["niveau_source"] == "national"]
    assert nationales["ecart_campagne"].all()
    assert "annee_civile" in nationales["soustraites"].iloc[0]
    assert "campagne différente du total" in nationales["note"].iloc[0]
    assert any("2017-2018 (annee_civile)" in e for e in stats.resultat.ecarts_campagne)
    regionales = olivier[olivier["niveau_source"] == "region"]
    assert not regionales["ecart_campagne"].any()


def test_valeur_manquante_exclut_le_couple_sans_zero(stats: Statistiques) -> None:
    # Palmier dattier 2023-2024 : seule Figuig est connue (les lignes Médias24 sont rejetées).
    palmier = _production(stats, "palmier_dattier", "2023-2024")
    assert list(palmier.index) == [FIGUIG]
    table = couverture(stats.resultat.production, _referentiel().provinces)
    ligne = table[
        (table["code_culture"] == "palmier_dattier")
        & (table["campagne"] == "2023-2024")
        & (table["variable"] == "production_t")
    ].iloc[0]
    assert ligne["absentes"] == len(_referentiel().provinces) - 1
    assert TAOUNATE in ligne["provinces_absentes"]


def test_condition_de_fin_sur_l_extrait(stats: Statistiques) -> None:
    assert provinces_sans_production(stats.resultat.production, _referentiel().provinces) == []


# --- Statistique zonale CROPGRIDS -----------------------------------------------------------


def test_fractions_de_pixels_partitionnees() -> None:
    """Deux régions réelles (HDX) et leur union : un pixel est partagé, jamais compté deux fois."""
    import tempfile
    import zipfile

    regions = gpd.read_file(PRODUCTION / "hdx_regions.geojson").rename(
        columns={"adm1_pcode": "code_province"}
    )
    union = gpd.GeoDataFrame(
        {"code_province": ["union"]}, geometry=[regions.union_all()], crs=regions.crs
    )
    crs = charger_config_referentiel(DEPOT).crs_surface
    archive = FIXTURES / "SRC-04" / "CROPGRIDSv1.08_NC_maps_extrait.zip"
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(archive) as zip_:
        chemin = zip_.extract("CROPGRIDSv1.08_NC_maps/CROPGRIDSv1.08_olive.nc", tmp)
        with xr.open_dataset(chemin) as ds:
            grille = ds["croparea"].load()

    def surface(zones: gpd.GeoDataFrame) -> pd.Series:
        f = fractions_pixels(grille, zones, crs)
        valeurs = grille.to_numpy()[f["i_lat"].to_numpy(), f["i_lon"].to_numpy()]
        return (f["fraction"] * valeurs).groupby(f["code_province"]).sum()

    par_region = surface(regions)
    assert (par_region > 0).all()
    assert par_region.sum() == pytest.approx(surface(union)["union"], rel=TOLERANCE)
    fractions = fractions_pixels(grille, regions, crs)
    assert fractions["fraction"].between(0, 1 + TOLERANCE).all()


# --- Format du rapport ------------------------------------------------------------------------


def test_format_fr_et_plages() -> None:
    assert format_fr(1027573.5) == "1 027 574"
    assert format_fr(0.25, 2) == "0,25"
    assert _plages([7, 1, 2, 3]) == "1-3, 7"
    assert _plages([]) == ""


# --- Données complètes ----------------------------------------------------------------------


@pytest.mark.donnees_reelles
def test_condition_de_fin_du_lot_sur_les_donnees_completes() -> None:
    """Les 75 provinces ont une production réelle ou estimée selon RG-04, avec sa source."""
    production_parquet = DEPOT.preparees / CONFIG.sorties.production
    provinces_gpkg = DEPOT.preparees / "provinces.gpkg"
    if not production_parquet.is_file() or not provinces_gpkg.is_file():
        pytest.skip("lancez python -m scripts.prepare")
    production = pd.read_parquet(production_parquet)
    provinces = gpd.read_file(provinces_gpkg)
    assert len(provinces) == 75
    assert provinces_sans_production(production, provinces) == []
    production = production[production["variable"] == "production_t"]
    assert production["source_id"].str.len().gt(0).all()
    estimees = production[production["statut"] == Statut.ESTIMEE]
    reparties = estimees["part_cropgrids"].notna()
    assert estimees.loc[reparties, "source_total"].notna().all()
    assert estimees.loc[~reparties, "previsionnel"].all()
    assert set(production["statut"]) <= {Statut.MESUREE, Statut.ESTIMEE}
