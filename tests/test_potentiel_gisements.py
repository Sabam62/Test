"""Lot 2, tâche 3 : M, C, B, valeurs théoriques, densité, variabilité (section 8.1).

Condition de fin du lot 2 : le couple de référence R01 × Taounate est recalculé à la main à
0,1 % près. f_col et f_eco viennent de residus.csv ; u est « À compléter » dans les données
livrées : la valeur utilisée ici est une « saisie simulée pour le test », enregistrée par une
version.
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest

from src.chemins import Chemins
from src.data.versions import Versions
from src.potentiel.entrees import EntreesPotentiel, charger_entrees
from src.potentiel.gisements import ResultatGisements, calculer_gisements, synthese_nationale
from src.potentiel.theorique import CAMPAGNE_REFERENCE
from tests.aides import copier_config
from tests.test_potentiel_theorique import PRECISION, _moyenne_a_la_main
from tests.test_preparation import DEPOT, FIXTURES, TAOUNATE, _referentiel, _statistiques

AUTEUR = "test automatique"
# f_col et f_eco de R01 livrés dans residus.csv (Dyjakon et García-Galindo 2019, SRC-08).
F_COL_R01, F_ECO_R01 = 0.96, 0.375
# Saisies simulées pour le test : part concurrente nationale et de Taounate.
U_NATIONAL_SIMULE, U_TAOUNATE_SIMULE = 0.25, 0.4
CARBONE_R01 = 0.483  # 48,3 % MS (§14.2)
RENDEMENT_PYROLYSE = 0.345  # milieu de 0,22 à 0,47 (§14.2)
BOUJDOUR = "11121"  # surface agricole CROPGRIDS nulle


@pytest.fixture
def chemins(tmp_path: Path) -> Chemins:
    chemins = Chemins(tmp_path)
    copier_config(DEPOT.config, chemins.config)
    shutil.copytree(DEPOT.saisies, chemins.saisies)
    chemins.preparees.mkdir(parents=True)
    _statistiques().resultat.production.to_parquet(
        chemins.preparees / "production.parquet", index=False
    )
    agricole = pd.read_csv(
        FIXTURES / "production" / "surface_agricole.csv",
        sep=";",
        dtype={"code_province": str},
    )
    agricole.to_parquet(chemins.preparees / "surface_agricole.parquet", index=False)
    Versions(chemins).initialiser(AUTEUR, "données livrées")
    return chemins


def _saisir(chemins: Chemins, table: str, cle: dict[str, str], valeur: float) -> None:
    """Saisie simulée pour le test, enregistrée comme une correction de l'entreprise."""
    versions = Versions(chemins)
    donnees = versions.lire(table)
    masque = pd.Series(True, index=donnees.index)
    for colonne, attendu in cle.items():
        masque &= donnees[colonne] == attendu
    assert masque.sum() == 1, cle
    donnees.loc[masque, ["valeur", "source_id", "annee", "statut"]] = [
        str(valeur),
        "saisie simulée pour le test",
        "2026",
        "Terrain",
    ]
    versions.enregistrer({table: donnees}, AUTEUR, "saisie simulée pour le test")


def _simuler_r01(chemins: Chemins) -> None:
    _saisir(
        chemins,
        "concurrence",
        {"code_province": "NATIONAL", "code_residu": "R01", "parametre": "part_utilisee"},
        U_NATIONAL_SIMULE,
    )


def _calculer(chemins: Chemins) -> tuple[EntreesPotentiel, ResultatGisements]:
    entrees = charger_entrees(chemins, _referentiel())
    theorique = entrees.calcul_theorique().calculer(entrees.production)
    return entrees, calculer_gisements(entrees, theorique)


def _valeur(resultat: ResultatGisements, province: str, residu: str, indicateur: str) -> pd.Series:
    choix = resultat.reference(indicateur)
    choix = choix[(choix["code_province"] == province) & (choix["code_residu"] == residu)]
    assert len(choix) == 1, f"{indicateur} {residu} × {province} absent"
    return choix.iloc[0]


def test_couple_de_reference_r01_taounate_a_la_main(chemins: Chemins) -> None:
    """Condition de fin du lot 2. À la main :
    T = superficie moyenne d'olivier de Taounate (5 dernières campagnes) × 1,23 t MS/ha/an
    M = T × f_col × f_eco × (1 − u) ; C = M × 0,483 ; B = M × 0,345."""
    _simuler_r01(chemins)
    entrees, resultat = _calculer(chemins)
    superficie, _ = _moyenne_a_la_main(entrees.production, TAOUNATE, "olivier", "superficie_ha")
    t = superficie * 1.23
    m = t * F_COL_R01 * F_ECO_R01 * (1 - U_NATIONAL_SIMULE)
    assert _valeur(resultat, TAOUNATE, "R01", "T")["valeur"] == pytest.approx(t, rel=PRECISION)
    ligne_m = _valeur(resultat, TAOUNATE, "R01", "M")
    assert ligne_m["valeur"] == pytest.approx(m, rel=PRECISION)
    assert ligne_m["unite"] == "t MS/an"
    assert "saisie simulée pour le test" in ligne_m["sources"]
    c = _valeur(resultat, TAOUNATE, "R01", "C")
    assert c["valeur"] == pytest.approx(m * CARBONE_R01, rel=PRECISION)
    b = _valeur(resultat, TAOUNATE, "R01", "B")
    assert b["valeur"] == pytest.approx(m * RENDEMENT_PYROLYSE, rel=PRECISION)


def test_m_bloque_avec_le_motif_dans_les_donnees_livrees(chemins: Chemins) -> None:
    _, resultat = _calculer(chemins)
    assert resultat.reference("M").empty
    motifs = resultat.exclus[
        (resultat.exclus["indicateur"] == "M") & (resultat.exclus["code_residu"] == "R01")
    ]["motif"]
    assert len(motifs) == len(_referentiel().provinces)
    assert motifs.str.contains("part_utilisee à compléter").all()


def test_valeurs_theoriques_calculees_sans_f_col(chemins: Chemins) -> None:
    _, resultat = _calculer(chemins)
    t = _valeur(resultat, TAOUNATE, "R01", "T")["valeur"]
    assert _valeur(resultat, TAOUNATE, "R01", "C_T")["valeur"] == pytest.approx(
        t * CARBONE_R01, rel=PRECISION
    )
    assert _valeur(resultat, TAOUNATE, "R01", "B_T")["valeur"] == pytest.approx(
        t * RENDEMENT_PYROLYSE, rel=PRECISION
    )
    # R06 (palmes, présent dans l'extrait) : carbone à compléter (Phyllis) → C_T exclu avec
    # le motif, B_T calculé.
    refus = resultat.exclus[
        (resultat.exclus["indicateur"] == "C_T") & (resultat.exclus["code_residu"] == "R06")
    ]
    assert len(refus) == len(_referentiel().provinces)
    assert refus["motif"].str.contains("carbone à compléter").all()
    assert not resultat.reference("B_T").query("code_residu == 'R06'").empty


def test_part_concurrente_de_la_province_prioritaire(chemins: Chemins) -> None:
    _simuler_r01(chemins)
    versions = Versions(chemins)
    concurrence = versions.lire("concurrence")
    nationale = concurrence[
        (concurrence["code_province"] == "NATIONAL")
        & (concurrence["code_residu"] == "R01")
        & (concurrence["parametre"] == "part_utilisee")
    ].copy()
    nationale["code_province"] = TAOUNATE
    nationale[["valeur", "source_id", "annee", "statut"]] = [
        str(U_TAOUNATE_SIMULE),
        "saisie simulée pour le test",
        "2026",
        "Terrain",
    ]
    versions.enregistrer(
        {"concurrence": pd.concat([concurrence, nationale], ignore_index=True)},
        AUTEUR,
        "saisie simulée pour le test",
    )
    _, resultat = _calculer(chemins)
    t = _valeur(resultat, TAOUNATE, "R01", "T")["valeur"]
    m = _valeur(resultat, TAOUNATE, "R01", "M")
    assert m["valeur"] == pytest.approx(
        t * F_COL_R01 * F_ECO_R01 * (1 - U_TAOUNATE_SIMULE), rel=PRECISION
    )
    assert m["statut"] == "Hypothèse"  # ratio R01 en milieu de fourchette


def test_u_national_au_statut_litterature_au_mieux(chemins: Chemins) -> None:
    _simuler_r01(chemins)
    entrees, _ = _calculer(chemins)
    from src.potentiel.gisements import _Facteurs

    facteurs = _Facteurs(
        entrees.tables.residus, entrees.tables.concurrence, entrees.config, "NATIONAL"
    )
    u = facteurs.part_utilisee(TAOUNATE, "R01")
    assert u.valeur == pytest.approx(U_NATIONAL_SIMULE)
    assert u.statut.value == "Littérature"  # la saisie nationale est « Terrain »


def test_proprietes_m_inferieur_a_t_et_sommes_nationales(chemins: Chemins) -> None:
    _simuler_r01(chemins)
    entrees, resultat = _calculer(chemins)
    t = resultat.reference("T").query("code_residu == 'R01'").set_index("code_province")["valeur"]
    m = resultat.reference("M").query("code_residu == 'R01'").set_index("code_province")["valeur"]
    assert (m <= t.reindex(m.index) + 1e-9).all()
    assert (resultat.gisements["valeur"] >= 0).all()
    synthese = synthese_nationale(resultat, entrees.config).set_index(["code_residu", "indicateur"])
    assert synthese.loc[("R01", "M"), "total"] == pytest.approx(m.sum())
    assert synthese.loc[("R01", "M"), "provinces_calculees"] == len(m)


def test_densite_et_surface_nulle(chemins: Chemins) -> None:
    _simuler_r01(chemins)
    _, resultat = _calculer(chemins)
    agricole = pd.read_csv(
        FIXTURES / "production" / "surface_agricole.csv",
        sep=";",
        dtype={"code_province": str},
    ).set_index("code_province")["surface_ha"]
    m = _valeur(resultat, TAOUNATE, "R01", "M")["valeur"]
    densite = _valeur(resultat, TAOUNATE, "R01", "densite_M")
    assert densite["valeur"] == pytest.approx(m / (agricole[TAOUNATE] / 100), rel=PRECISION)
    assert densite["unite"] == "t MS/km²/an"
    refus = resultat.exclus[
        (resultat.exclus["code_province"] == BOUJDOUR)
        & (resultat.exclus["code_residu"] == "R01")
        & (resultat.exclus["indicateur"] == "densite_M")
    ]
    assert len(refus) == 1
    assert refus["motif"].str.contains("surface agricole nulle").all()


def test_variabilite_interannuelle(chemins: Chemins) -> None:
    _simuler_r01(chemins)
    _, resultat = _calculer(chemins)
    g = resultat.gisements
    annuelles = g[
        (g["code_province"] == TAOUNATE)
        & (g["code_residu"] == "R01")
        & (g["indicateur"] == "M")
        & (g["campagne"] != CAMPAGNE_REFERENCE)
    ]["valeur"]
    attendu = annuelles.std() / annuelles.mean()
    assert _valeur(resultat, TAOUNATE, "R01", "cv_M")["valeur"] == pytest.approx(
        attendu, rel=PRECISION
    )


@pytest.mark.donnees_reelles
def test_gisements_sur_les_donnees_completes() -> None:
    """Données préparées : chaque couple est calculé ou exclu avec un motif ; R01 couvre les
    75 provinces ; M reste bloqué tant que f_col, f_eco et u sont à compléter."""
    if not (DEPOT.preparees / "production.parquet").is_file():
        pytest.skip("lancez python -m scripts.prepare")
    from src.data.provinces import charger_referentiel

    entrees = charger_entrees(DEPOT, charger_referentiel(DEPOT))
    theorique = entrees.calcul_theorique().calculer(entrees.production)
    resultat = calculer_gisements(entrees, theorique)
    t = resultat.reference("T")
    assert set(t[t["code_residu"] == "R01"]["code_province"]) == set(
        entrees.referentiel.provinces["code_province"]
    )
    couples = set(zip(t["code_province"], t["code_residu"], strict=True)) | set(
        zip(theorique.exclus["code_province"], theorique.exclus["code_residu"], strict=True)
    )
    assert len(couples) == 75 * 13
    synthese = synthese_nationale(resultat, entrees.config)
    assert synthese.query("indicateur == 'T'")["total"].dropna().sum() > 0
