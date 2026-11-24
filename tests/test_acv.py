"""Lot 4 : ACV et bilan climat (section 8.3, UC-ACV-01 à 03).

Condition de fin du lot 4 : le bilan d'une chaîne de référence est identique, à 1 % près, au
calcul tableur indépendant ``tests/fixtures/acv/chaine_reference.xlsx`` (formules Excel,
recalculées par Excel ; voir tests/fixtures/extraire_acv.py). Les entrées encore « À compléter »
dans les données livrées y sont des « saisies simulées pour le test ». Brightway travaille dans
un dossier temporaire (tests/conftest.py).
"""

import time
from pathlib import Path

import bw2data as bd
import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from src.acv.calcul import ResultatAcv, preparer_acv
from src.acv.config import charger_config_acv
from src.acv.entrees import classe_temperature
from src.chemins import Chemins, chemins_par_defaut
from src.data.provenance import Provenance, Statut, ValeurSourcee
from src.data.tables_reference import charger_catalogue, lire_table_longue
from src.logistique.calcul import lecteur_parametres
from src.logistique.distances import vol_oiseau_km
from src.potentiel.config import charger_config_potentiel
from src.scenarios.config import charger_controles
from src.scenarios.parametres import valeur_courante
from tests.aides import copier_config

DEPOT = chemins_par_defaut()
FIXTURES = DEPOT.racine / "tests" / "fixtures"
CLASSEUR = FIXTURES / "acv" / "chaine_reference.xlsx"
CONFIG = charger_config_acv(DEPOT)
POTENTIEL = charger_config_potentiel(DEPOT)
CODES = charger_catalogue(DEPOT).residus.codes
SIMULE = "saisie simulée pour le test"
TOLERANCE = 0.01  # 1 %, condition de fin du lot 4


def _feuille(nom: str) -> dict[str, object]:
    feuille = load_workbook(CLASSEUR, data_only=True)[nom]
    return {ligne[0]: ligne[1] for ligne in feuille.iter_rows(min_row=2, values_only=True)}


ENTREES = _feuille("Entrées")
TABLEUR = _feuille("Bilan")


def _simulee(nom: str, valeur: object, unite: str) -> ValeurSourcee:
    return ValeurSourcee(
        nom=nom,
        valeur=valeur,
        unite=unite,
        provenance=Provenance(source_id=SIMULE, annee=2026, statut=Statut.TERRAIN),
    )


def _lire_reference(identifiant: str) -> ValeurSourcee:
    simules = {
        "PAR-21": _simulee("PAR-21", 600.0, "°C ou classe"),
        "PAR-32": _simulee("PAR-32", float(ENTREES["volume_camion"]), "m³"),
    }
    return simules.get(identifiant) or valeur_courante(DEPOT, identifiant)


def _remplacer(table: pd.DataFrame, filtre: dict[str, str], valeur: object) -> None:
    masque = pd.Series(True, index=table.index)
    for colonne, attendu in filtre.items():
        masque &= table[colonne] == attendu
    assert masque.sum() == 1, filtre
    table.loc[masque, ["valeur", "source_id", "annee", "ou_trouver"]] = [
        str(valeur),
        SIMULE,
        "2026",
        "",
    ]


def _tables_reference(tmp: Path, completer: bool) -> tuple:
    residus = pd.read_csv(DEPOT.saisies / "residus.csv", sep=";", dtype=str, keep_default_na=False)
    facteurs = pd.read_csv(
        DEPOT.saisies / "facteurs_emission.csv", sep=";", dtype=str, keep_default_na=False
    )
    if completer:
        e = ENTREES
        for parametre, valeur in (
            ("densite_apparente", float(e["densite"]) * 1000),
            ("scenario_reference", "brûlage à l'air libre"),
        ):
            _remplacer(residus, {"code_residu": "R03", "parametre": parametre}, valeur)
        for activite, parametre, valeur in (
            ("gazole_amont", "kg_co2e", e["gazole_amont"]),
            ("pyrolyse", "kg_ch4_bio", e["pyr_ch4"]),
            ("pyrolyse", "kg_n2o", e["pyr_n2o"]),
            ("pyrolyse", "consommation_electricite", e["elec_pyr"]),
            ("collecte", "consommation_gazole", e["gaz_col"]),
            ("broyage", "consommation_electricite", e["elec_broy"]),
            ("epandage", "consommation_gazole", e["gaz_ep"]),
            ("transport_biochar", "distance_km", e["d_bc"]),
        ):
            _remplacer(facteurs, {"code_activite": activite, "parametre": parametre}, valeur)
    residus.to_csv(tmp / "residus.csv", sep=";", index=False)
    facteurs.to_csv(tmp / "facteurs.csv", sep=";", index=False)
    catalogue, controles = charger_catalogue(DEPOT), charger_controles(DEPOT)
    return (
        lire_table_longue(tmp / "residus.csv", ["code_residu"], catalogue.residus, controles, "r"),
        lire_table_longue(
            tmp / "facteurs.csv",
            ["code_activite", "libelle"],
            catalogue.facteurs_emission,
            controles,
            "f",
        ),
    )


def _preparer(tmp: Path, completer: bool = True) -> ResultatAcv:
    residus, facteurs = _tables_reference(tmp, completer)
    if completer:
        lire = _lire_reference
    else:  # installation neuve : modèle de l'entreprise livré vide (RG-15)
        copier_config(DEPOT.config, tmp / "config")
        lire = lecteur_parametres(Chemins(tmp))
    return preparer_acv(
        CONFIG,
        residus,
        facteurs,
        CODES,
        lire,
        POTENTIEL.unites_fraction,
        POTENTIEL.moins_fiable,
    )


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> ResultatAcv:
    return _preparer(tmp_path_factory.mktemp("acv"))


def _chaine(distance: float | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code_province": ["reference"],
            "code_residu": [ENTREES["residu"]],
            "id_site": ["AGP-MEKNES"],
            "distance_km": [distance if distance is not None else ENTREES["distance_km"]],
        }
    )


def test_bilan_identique_au_calcul_tableur(reference: ResultatAcv) -> None:
    ligne = reference.bilans(_chaine()).iloc[0]
    assert ligne["motif"] == ""
    for terme in ("E_col", "E_pre", "E_tr", "E_pyr", "E_ep", "E_ref", "stock", "BN"):
        assert ligne[terme] == pytest.approx(TABLEUR[terme], rel=TOLERANCE), terme


def test_chaine_parametree_dans_brightway_identique(reference: ResultatAcv) -> None:
    etapes = reference.chaine_brightway(str(ENTREES["residu"]), float(ENTREES["distance_km"]))
    kg = CONFIG.kg_par_tonne
    for etape, terme in (
        ("collecte", "E_col"),
        ("pretraitement", "E_pre"),
        ("transport", "E_tr"),
        ("pyrolyse", "E_pyr"),
        ("epandage", "E_ep"),
    ):
        assert etapes[etape] / kg == pytest.approx(TABLEUR[terme], rel=TOLERANCE), etape
    # Le scénario de référence est un brûlage : émissions évitées par t de biochar (m t MS).
    assert etapes["reference"] / kg == pytest.approx(TABLEUR["E_ref"], rel=TOLERANCE)
    # Une autre distance : seuls les paramètres de la chaîne changent (paramètres Brightway).
    loin = reference.chaine_brightway(str(ENTREES["residu"]), 2 * float(ENTREES["distance_km"]))
    assert loin["transport"] == pytest.approx(2 * etapes["transport"], rel=1e-9)


def test_methode_prg100_ar6_creee_par_code(reference: ResultatAcv) -> None:
    methode = bd.Method(tuple(CONFIG.methode))
    facteurs = {bd.get_activity(cle)["name"]: valeur for cle, valeur in methode.load()}
    assert facteurs == {
        "Carbon dioxide, fossil": 1,
        "Methane, fossil": 29.8,
        "Methane, non-fossil": 27.0,
        "Dinitrogen monoxide": 273,
    }
    assert bd.projects.current == CONFIG.projet
    assert CONFIG.base_avant_plan in bd.databases
    assert "ecoinvent" not in " ".join(bd.databases).lower()


def test_proprietes_du_bilan(reference: ResultatAcv) -> None:
    proche, loin = reference.bilans(pd.concat([_chaine(10), _chaine(300)])).itertuples()
    assert loin.E_tr > proche.E_tr and loin.BN < proche.BN  # plus loin, moins de retrait
    emissions = proche.E_col + proche.E_pre + proche.E_tr + proche.E_pyr + proche.E_ep
    attendu = proche.stock - emissions + proche.E_ref
    assert abs(proche.BN - attendu) < 1e-12


def test_donnees_livrees_bilan_bloque_avec_les_motifs(tmp_path: Path) -> None:
    livree = _preparer(tmp_path, completer=False)
    ligne = livree.bilans(_chaine()).iloc[0]
    assert pd.isna(ligne["BN"])
    for attendu in ("gazole_amont", "scenario_reference", "PAR-21"):
        assert attendu in ligne["motif"]


def test_classes_de_temperature_du_giec() -> None:
    assert classe_temperature(300.0, CONFIG) is None
    assert classe_temperature(400.0, CONFIG) == "basse"
    assert classe_temperature(500.0, CONFIG) == "moyenne"
    assert classe_temperature(600.0, CONFIG) == "haute"
    assert classe_temperature("moyenne", CONFIG) == "moyenne"


def test_carbone_du_biochar_r01_seulement_a_haute_temperature(reference: ResultatAcv) -> None:
    from src.logistique.couts import Terme

    assert isinstance(reference.entrees.residus["R01"].carbone_biochar, Terme)  # 600 °C
    assert reference.entrees.residus["R01"].carbone_biochar.valeur == pytest.approx(0.709)


def test_recalcul_complet_en_moins_de_30_secondes(tmp_path: Path) -> None:
    """UC-ACV-02 : nouveau projet et bilans de tous les couples d'un extrait réel."""
    rattachements = pd.read_csv(
        FIXTURES / "logistique" / "rattachements_fes_meknes.csv", sep=";", dtype=str
    )
    lieux = pd.read_csv(FIXTURES / "logistique" / "lieux_osm.csv", sep=";")
    points = rattachements.assign(lon=rattachements["lon"].astype(float))
    points["lat"] = rattachements["lat"].astype(float)
    d = vol_oiseau_km(
        points["lon"].to_numpy()[:, None],
        points["lat"].to_numpy()[:, None],
        lieux["lon"].to_numpy()[None, :],
        lieux["lat"].to_numpy()[None, :],
        6371.0088,
    )
    distances = pd.DataFrame(
        {
            "code_province": np.repeat(points["code_province"], len(lieux)),
            "code_residu": np.repeat(points["code_residu"], len(lieux)),
            "id_site": np.tile(lieux["nom"], len(points)),
            "distance_km": d.ravel(),
        }
    )
    debut = time.perf_counter()
    resultat = _preparer(tmp_path)
    table = resultat.bilans(distances)
    assert time.perf_counter() - debut < 30
    assert len(table) == len(distances)
    assert table.loc[table["code_residu"] == "R03", "BN"].notna().all()
