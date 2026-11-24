"""Lot 5 : mélange optimal (section 11.2.4, UC-MIX-01).

Les propriétés des résidus sont les valeurs livrées de residus.csv (cendres et humidité de R03,
R11, R13 ; SRC-08) ; les tonnages disponibles, coûts livrés et contraintes sont des saisies
simulées pour le test.
"""

import pandas as pd
import pytest

from src.chemins import chemins_par_defaut
from src.data.tables_reference import charger_catalogue, lire_table_longue
from src.melange.programme import Contraintes, melange_optimal
from src.scenarios.config import charger_controles

DEPOT = chemins_par_defaut()
RESIDUS = lire_table_longue(
    DEPOT.saisies / "residus.csv",
    ["code_residu"],
    charger_catalogue(DEPOT).residus,
    charger_controles(DEPOT),
    "residus",
)


def _valeur(residu: str, parametre: str) -> float:
    return float(RESIDUS.valeur(residu, parametre).lire_nombre())


def _couples() -> pd.DataFrame:
    """Trois résidus réels (cendres, humidité livrées) ; disponibles et coûts simulés."""
    lignes = []
    for residu, disponible, cout in (("R03", 6000, 300), ("R11", 4000, 250), ("R13", 8000, 400)):
        lignes.append(
            {
                "code_province": "P",
                "code_residu": residu,
                "disponible": disponible,
                "cout_livre": cout,
                "cendres": _valeur(residu, "cendres"),
                "humidite": _valeur(residu, "humidite"),
            }
        )
    return pd.DataFrame(lignes)


def test_sans_contrainte_le_moins_cher_d_abord() -> None:
    m = melange_optimal(_couples(), Contraintes(capacite=7000))
    assert m.faisable
    tonnages = dict(zip(m.tableau["code_residu"], m.tableau["tonnage"], strict=True))
    assert tonnages == pytest.approx({"R11": 4000, "R03": 3000})  # 250 puis 300 DH/t MS
    assert m.cout_moyen == pytest.approx((4000 * 250 + 3000 * 300) / 7000)
    assert len(m.non_appliquees) == 3


def test_part_maximale_d_un_residu() -> None:
    m = melange_optimal(_couples(), Contraintes(capacite=7000, part_maximale=0.5))
    assert m.faisable
    assert (m.tableau["tonnage"] <= 3500 + 1e-6).all()
    assert m.tableau["tonnage"].sum() == pytest.approx(7000)


def test_contraintes_de_cendres_et_d_humidite_respectees() -> None:
    couples = _couples()
    h_max = float(couples["humidite"].median())
    m = melange_optimal(couples, Contraintes(capacite=7000, humidite_maximale=h_max))
    assert m.faisable and m.humidite_moyenne <= h_max + 1e-6
    a_max = float(couples["cendres"].mean())
    m = melange_optimal(couples, Contraintes(capacite=7000, cendres_maximales=a_max))
    assert m.faisable and m.cendres_moyennes <= a_max + 1e-6


def test_infaisable_indique_la_contrainte_bloquante() -> None:
    couples = _couples()
    trop_bas = float(couples["humidite"].min()) - 1
    m = melange_optimal(couples, Contraintes(capacite=7000, humidite_maximale=trop_bas))
    assert not m.faisable
    assert m.bloquantes == ["humidité moyenne maximale (PAR-53)"]
    assert "PAR-53" in m.message


def test_bassin_insuffisant() -> None:
    m = melange_optimal(_couples(), Contraintes(capacite=50000))
    assert not m.faisable and m.bloquantes == ["capacité K"]
    assert "18 000" in m.message


def test_poids_du_carbone_dans_l_objectif() -> None:
    couples = _couples().assign(carbone_t=[0.9, 0.1, 0.5])  # saisie simulée pour le test
    sans = melange_optimal(couples, Contraintes(capacite=4000))
    avec = melange_optimal(couples, Contraintes(capacite=4000, lambda_carbone=200))
    assert sans.tableau["code_residu"].iloc[0] == "R11"
    assert avec.tableau["code_residu"].iloc[0] == "R03"  # 300 − 180 < 250 − 20
    assert avec.bilan_moyen == pytest.approx(0.9)
