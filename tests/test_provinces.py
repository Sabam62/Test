"""Référentiel des régions et provinces (RG-02, UC-DAT-03).

Les tests unitaires utilisent tests/fixtures/referentiel/ : attributs réels des cartes du HCP
(SRC-19, sans géométrie) et lignes réelles du RGPH 2024 (SRC-09). Les tests marqués
« donnees_reelles » lisent les polygones de data/raw/SRC-19/ et sont ignorés s'ils sont absents.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.chemins import Chemins, chemins_par_defaut
from src.data.lecteurs.rgph2024 import unites_rgph2024
from src.data.provinces import (
    ErreurRattachement,
    ErreurReferentiel,
    Referentiel,
    charger_config_referentiel,
    charger_variantes,
    code_province,
    construire_referentiel,
    normaliser_nom,
)
from src.data.sources import charger_sources

DEPOT = chemins_par_defaut()
FIXTURES = DEPOT.racine / "tests" / "fixtures" / "referentiel"
CONFIG = charger_config_referentiel(DEPOT)
# Production d'olives 2017-2018 de la DRA Fès-Meknès citée au §14.2 du cahier (Infomédiaire).
PROVINCES_DRA_FES_MEKNES = ["Taounate", "Taza", "El Hajeb", "Fès", "Meknès", "Sefrou", "Boulemane"]


def _lignes_rgph() -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "rgph2024_lignes.csv", sep=";", dtype=str)


def _hcp(nom: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / f"hcp_{nom}.csv", sep=";")


def _referentiel() -> Referentiel:
    referentiel = construire_referentiel(
        unites_rgph2024(_lignes_rgph()), _hcp("regions"), _hcp("provinces"), CONFIG
    )
    return referentiel.avec_variantes(charger_variantes(DEPOT.saisies / CONFIG.fichier_variantes))


# --- Normalisation des noms ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("variantes", "attendu"),
    [
        (
            [
                "Préfecture d'Agadir-Ida-Ou-Tanane",
                "Agadir Ida Ou Tanane",
                "Agadir Ida Outanane Prefecture",
            ],
            "agadiridaoutanane",
        ),
        (["Province de Laâyoune", "Laayoune", "Laayoune Province"], "laayoune"),
        (["Région de l'Oriental", "Oriental"], "oriental"),
        (["Préfecture de M'diq-Fnideq", "Mdiq-Fnideq"], "mdiqfnideq"),
        (["Province d'Oued Ed-Dahab", "Oued-Ed-Dahab"], "ouededdahab"),
        (["إقليم تاونات", "تاونات"], "تاونات"),
    ],
)
def test_normalisation_des_variantes_reelles(variantes: list[str], attendu: str) -> None:
    assert {normaliser_nom(v) for v in variantes} == {attendu}


def test_code_province_du_rgph_2024() -> None:
    assert code_province(12, 66, CONFIG.chiffres_code_province) == "12066"
    assert code_province(1, 51, CONFIG.chiffres_code_province) == "1051"


# --- Unités du RGPH 2024 ------------------------------------------------------------------


def test_unites_rgph2024() -> None:
    unites = unites_rgph2024(_lignes_rgph())
    assert (unites["niveau"] == "region").sum() == CONFIG.nb_regions
    assert (unites["niveau"] == "province").sum() == CONFIG.nb_provinces
    aousserd = unites.set_index("code").loc["12066"]
    assert aousserd["nom_fr"] == "Aousserd"
    assert aousserd["nom_officiel"] == "Province d'Aousserd"
    assert unites.set_index("code").loc["3"]["nom_fr"] == "Fès-Meknès"


# --- Construction du référentiel ----------------------------------------------------------


def test_douze_regions_et_soixante_quinze_provinces() -> None:
    referentiel = _referentiel()
    assert len(referentiel.regions) == CONFIG.nb_regions
    assert len(referentiel.provinces) == CONFIG.nb_provinces
    assert referentiel.provinces["code_province"].is_unique
    assert referentiel.regions["code_region"].is_unique


def test_chaque_province_dans_une_seule_region() -> None:
    provinces = _referentiel().provinces
    regions = set(_referentiel().regions["code_region"])
    assert provinces["code_region"].notna().all()
    assert set(provinces["code_region"]) <= regions
    assert provinces.groupby("code_province")["code_region"].nunique().eq(1).all()
    for code, region in zip(provinces["code_province"], provinces["code_region"], strict=True):
        assert code.startswith(region)


def test_provinces_du_sud_presentes() -> None:
    provinces = _referentiel().provinces.set_index("code_province")
    sud = provinces[provinces["code_region"].isin(["11", "12"])]
    assert sorted(sud["nom_fr"]) == [
        "Aousserd",
        "Boujdour",
        "Es-Semara",
        "Laâyoune",
        "Oued Ed-Dahab",
        "Tarfaya",
    ]


def test_province_absente_des_cartes_bloque(tmp_path: Path) -> None:
    provinces = _hcp("provinces")
    provinces = provinces[~((provinces["code_reg"] == 12) & (provinces["code_prov"] == 66))]
    with pytest.raises(ErreurReferentiel, match="12066"):
        construire_referentiel(unites_rgph2024(_lignes_rgph()), _hcp("regions"), provinces, CONFIG)


def test_nombre_de_provinces_controle() -> None:
    config = CONFIG.model_copy(update={"nb_provinces": CONFIG.nb_provinces + 1})
    with pytest.raises(ErreurReferentiel, match="provinces"):
        construire_referentiel(
            unites_rgph2024(_lignes_rgph()), _hcp("regions"), _hcp("provinces"), config
        )


# --- Variantes de noms (RG-02) ------------------------------------------------------------


def test_variantes_sourcees() -> None:
    variantes = charger_variantes(DEPOT.saisies / CONFIG.fichier_variantes)
    assert variantes["source_id"].str.strip().ne("").all()
    assert charger_sources(DEPOT).inconnues(variantes["source_id"]) == []
    assert set(variantes["niveau"]) == {"region", "province"}


def test_variante_sans_source_refusee(tmp_path: Path) -> None:
    fichier = tmp_path / "variantes.csv"
    lignes = (DEPOT.saisies / CONFIG.fichier_variantes).read_text(encoding="utf-8").splitlines()
    entete, premiere = lignes[0], lignes[1].split(";")
    premiere[entete.split(";").index("source_id")] = ""
    fichier.write_text("\n".join([entete, ";".join(premiere)]) + "\n", encoding="utf-8")
    with pytest.raises(ErreurReferentiel, match="RG-18"):
        charger_variantes(fichier)


def test_variante_ambigue_refusee() -> None:
    variantes = charger_variantes(DEPOT.saisies / CONFIG.fichier_variantes)
    conflit = variantes.iloc[[0]].assign(code="9001", source_id="SRC-19")
    referentiel = construire_referentiel(
        unites_rgph2024(_lignes_rgph()), _hcp("regions"), _hcp("provinces"), CONFIG
    )
    with pytest.raises(ErreurReferentiel, match="deux codes"):
        referentiel.avec_variantes(pd.concat([variantes, conflit]))


@pytest.mark.parametrize("colonne", ["nom_officiel", "nom_fr", "nom_ar"])
def test_noms_du_rgph_2024_tous_rattaches(colonne: str) -> None:
    unites = unites_rgph2024(_lignes_rgph())
    referentiel = _referentiel()
    for niveau in ("region", "province"):
        sous = unites[unites["niveau"] == niveau]
        assert referentiel.rattacher(sous[colonne], niveau) == list(sous["code"])


@pytest.mark.parametrize("colonne", ["libelle_fr", "libelle_ar"])
def test_noms_des_cartes_hcp_tous_rattaches(colonne: str) -> None:
    referentiel = _referentiel()
    provinces = _hcp("provinces")
    attendus = [
        code_province(r, p, CONFIG.chiffres_code_province)
        for r, p in zip(provinces["code_reg"], provinces["code_prov"], strict=True)
    ]
    assert referentiel.rattacher(provinces[colonne], "province") == attendus
    regions = _hcp("regions")
    assert referentiel.rattacher(regions[colonne], "region") == [
        str(c) for c in regions["code_reg"]
    ]


def test_variantes_hcp_sourcees_sans_indicateur() -> None:
    from src.data.variantes import METHODE_NOMS

    variantes = charger_variantes(DEPOT.saisies / CONFIG.fichier_variantes)
    hcp = variantes[variantes["source_id"] == CONFIG.source_polygones]
    assert len(hcp) > 0
    assert set(hcp["methode"]) == {METHODE_NOMS}


def test_noms_hdx_tous_rattaches() -> None:
    hdx = pd.read_excel(
        DEPOT.racine / "tests/fixtures/SRC-05/mar_admin_boundaries.xlsx", sheet_name=None
    )
    referentiel = _referentiel()
    assert len(referentiel.rattacher(hdx["mar_admin2"]["adm2_name"], "province")) == len(
        hdx["mar_admin2"]
    )
    assert len(referentiel.rattacher(hdx["mar_admin1"]["adm1_name"], "region")) == len(
        hdx["mar_admin1"]
    )


def test_import_dra_rattache_a_cent_pour_cent() -> None:
    codes = _referentiel().rattacher(pd.Series(PROVINCES_DRA_FES_MEKNES), "province")
    provinces = _referentiel().provinces.set_index("code_province")
    assert set(provinces.loc[codes, "code_region"]) == {"3"}
    assert len(set(codes)) == len(PROVINCES_DRA_FES_MEKNES)


def test_code_accepte_tel_quel() -> None:
    assert _referentiel().rattacher(pd.Series(["12066", "Taza"]), "province")[0] == "12066"
    assert _referentiel().rattacher(pd.Series(["3"]), "region") == ["3"]
    with pytest.raises(ErreurRattachement):
        _referentiel().rattacher(pd.Series(["3"]), "province")


def test_variante_inconnue_bloque_l_import_et_nomme_la_ligne() -> None:
    # Une préfecture d'arrondissements du RGPH 2024 n'est pas une province : elle doit bloquer.
    noms = pd.Series(["Taounate", "Préfecture d'arrondissements de Ben M'sick", "Taza", ""])
    with pytest.raises(ErreurRattachement) as erreur:
        _referentiel().rattacher(noms, "province")
    message = str(erreur.value)
    assert "ligne 2" in message
    assert "Ben M'sick" in message
    assert "ligne 4" in message
    assert "RG-02" in message
    assert erreur.value.lignes == [2, 4]


# --- Polygones réels (data/raw/SRC-19) ----------------------------------------------------


def _donnees_reelles() -> Chemins:
    chemins = DEPOT
    for nom in (CONFIG.fichier_regions, CONFIG.fichier_provinces):
        if not (chemins.brutes / CONFIG.source_polygones / nom).is_file():
            pytest.skip("polygones du HCP absents de data/raw/SRC-19/")
    return chemins


@pytest.mark.donnees_reelles
def test_referentiel_complet_sur_les_polygones_reels() -> None:
    from src.data.provinces import charger_referentiel, geodonnees_referentiel

    chemins = _donnees_reelles()
    regions, provinces = geodonnees_referentiel(chemins, charger_referentiel(chemins))
    assert len(regions) == CONFIG.nb_regions
    assert len(provinces) == CONFIG.nb_provinces
    assert provinces.is_valid.all() and regions.is_valid.all()
    assert set(provinces["source_id"]) == {CONFIG.source_polygones}
    # Plausibilité : la surface calculée concorde avec celle de HDX (SRC-05, source indépendante)
    # pour les 69 provinces communes ; les écarts les plus forts sont à la limite sud de
    # Guelmim-Oued Noun (Assa-Zag, Tan-Tan), où HDX coupe le territoire.
    hdx = pd.read_excel(
        DEPOT.racine / "tests/fixtures/SRC-05/mar_admin_boundaries.xlsx", sheet_name="mar_admin2"
    )
    hdx["code_province"] = charger_referentiel(chemins).rattacher(hdx["adm2_name"], "province")
    comparaison = provinces.merge(hdx[["code_province", "area_sqkm"]], on="code_province")
    assert len(comparaison) == len(hdx)
    ecarts = (comparaison["superficie_km2"] / comparaison["area_sqkm"] - 1).abs()
    assert ecarts.median() < 0.02
    assert comparaison["superficie_km2"].sum() == pytest.approx(
        comparaison["area_sqkm"].sum(), rel=0.03
    )
    # Chaque province est contenue dans le polygone de sa région.
    points = provinces.set_geometry(provinces.representative_point())
    jointure = points.sjoin(regions[["code_region", "geometry"]], predicate="within")
    assert len(jointure) == CONFIG.nb_provinces
    assert (jointure["code_region_left"] == jointure["code_region_right"]).all()


@pytest.mark.donnees_reelles
def test_enregistrement_geopackage(tmp_path: Path) -> None:
    import geopandas as gpd

    from src.data.provinces import enregistrer_referentiel

    chemins = _donnees_reelles()
    sorties = enregistrer_referentiel(chemins, tmp_path)
    assert [s.name for s in sorties] == ["regions.gpkg", "provinces.gpkg"]
    provinces = gpd.read_file(sorties[1])
    assert len(provinces) == CONFIG.nb_provinces
    colonnes = {"code_province", "code_region", "nom_fr", "nom_ar", "superficie_km2", "source_id"}
    assert colonnes <= set(provinces.columns)
    assert len(gpd.read_file(sorties[0])) == CONFIG.nb_regions


# --- Génération des variantes -------------------------------------------------------------


def test_fusion_conserve_les_saisies_et_remplace_les_generees() -> None:
    from src.data.variantes import METHODE_SAISIE, fusionner

    actuelles = charger_variantes(DEPOT.saisies / CONFIG.fichier_variantes)
    saisies = actuelles[actuelles["methode"] == METHODE_SAISIE]
    assert len(saisies) == len(PROVINCES_DRA_FES_MEKNES)
    fusion = fusionner(actuelles, [])
    assert set(fusion["methode"]) == {METHODE_SAISIE}
    assert len(fusion) == len(saisies)
    assert list(fusion.columns) == list(actuelles.columns)


@pytest.mark.donnees_reelles
def test_rapprochement_hdx_un_a_un_sur_les_polygones_corriges() -> None:
    import geopandas as gpd

    from src.data.provinces import charger_referentiel, geodonnees_referentiel
    from src.data.variantes import rapprocher

    chemins = _donnees_reelles()
    _, provinces = geodonnees_referentiel(chemins, charger_referentiel(chemins))
    hdx = gpd.read_file(
        f"zip://{chemins.brutes}/SRC-05/mar_admin_boundaries.shp.zip!mar_admin2.shp"
    )
    jointure = rapprocher(hdx, "adm2_name", "adm2_pcode", provinces, "code_province")
    # 69 unités HDX (les 6 provinces du Sud n'y figurent pas), chacune dans une province distincte.
    assert len(jointure) == len(hdx)
    assert jointure["code_province"].is_unique
    referentiel = charger_referentiel(chemins)
    assert referentiel.rattacher(jointure["adm2_name"], "province") == list(
        jointure["code_province"]
    )
