"""Provenance des valeurs (RG-03), source obligatoire (RG-18), marqueur « À compléter » (RG-14)."""

import pytest
from pydantic import ValidationError

from src.data.provenance import (
    A_COMPLETER,
    Loi,
    Provenance,
    Statut,
    ValeurACompleter,
    ValeurSourcee,
)

# Valeurs reprises de la section 14.3 du cahier des charges.
PAR_31 = {
    "nom": "PAR-31 · Charge d'un camion lourd",
    "valeur": 25,
    "unite": "t",
    "source_id": "SRC-16-MEDIAS24-2026",
    "annee": 2026,
    "statut": "Littérature",
}
PAR_37 = {
    "nom": "PAR-37 · Prix du gazole",
    "valeur": 13.15,
    "min": 10.80,
    "max": 15.50,
    "loi": "uniforme",
    "unite": "DH/L",
    "source_id": "SRC-16-MEDIAS24-2026",
    "annee": 2026,
    "statut": "Hypothèse",
    "note": "milieu de fourchette",
}
PAR_24 = {
    "nom": "PAR-24 · Émissions de l'électricité du réseau marocain",
    "valeur": 0.69,
    "min": 0.68,
    "mode": 0.69,
    "max": 0.75,
    "loi": "triangulaire",
    "unite": "kg CO₂e/kWh",
    "source_id": "SRC-15-ECOACTU",
    "annee": 2023,
    "statut": "Littérature",
}
PAR_32 = {
    "nom": "PAR-32 · Volume utile d'un camion",
    "valeur": A_COMPLETER,
    "unite": "m³",
    "ou_trouver": "fiche technique du camion retenu",
}


def test_statuts_de_la_section_3() -> None:
    assert [s.value for s in Statut] == [
        "Mesurée",
        "Estimée",
        "Littérature",
        "Terrain",
        "Hypothèse",
    ]


def test_a_completer_n_est_pas_un_statut() -> None:
    assert A_COMPLETER not in {s.value for s in Statut}
    with pytest.raises(ValidationError):
        Provenance(source_id="CDC", annee=2026, statut=A_COMPLETER)


def test_provenance_regroupee() -> None:
    valeur = ValeurSourcee.model_validate(PAR_31)
    assert valeur.lire() == 25
    assert valeur.provenance == Provenance(
        source_id="SRC-16-MEDIAS24-2026", annee=2026, statut=Statut.LITTERATURE
    )
    assert valeur.provenance.version is None
    assert not valeur.est_a_completer


@pytest.mark.parametrize("retrait", ["source_id", "statut"])
def test_valeur_sans_source_refusee_rg18(retrait: str) -> None:
    donnees = {k: v for k, v in PAR_31.items() if k != retrait}
    with pytest.raises(ValidationError, match="RG-18"):
        ValeurSourcee.model_validate(donnees)


def test_source_vide_refusee_rg18() -> None:
    with pytest.raises(ValidationError, match="RG-18"):
        ValeurSourcee.model_validate({**PAR_31, "source_id": "  "})


def test_a_completer_bloque_la_lecture_rg14() -> None:
    valeur = ValeurSourcee.model_validate(PAR_32)
    assert valeur.est_a_completer
    with pytest.raises(ValeurACompleter) as erreur:
        valeur.lire()
    message = str(erreur.value)
    assert "PAR-32 · Volume utile d'un camion" in message
    assert "fiche technique du camion retenu" in message
    assert "RG-14" in message


def test_a_completer_porte_un_statut_attendu() -> None:
    valeur = ValeurSourcee.model_validate({**PAR_32, "statut": "Terrain"})
    assert valeur.statut_attendu is Statut.TERRAIN
    assert valeur.provenance is None


def test_a_completer_sans_source_refuse_une_annee() -> None:
    with pytest.raises(ValidationError, match="annee"):
        ValeurSourcee.model_validate({**PAR_32, "annee": 2026})


def test_statut_attendu_reserve_aux_valeurs_a_completer() -> None:
    with pytest.raises(ValidationError, match="statut_attendu"):
        ValeurSourcee.model_validate({**PAR_31, "statut_attendu": "Terrain"})


def test_a_completer_exige_ou_trouver() -> None:
    donnees = {k: v for k, v in PAR_32.items() if k != "ou_trouver"}
    with pytest.raises(ValidationError, match="où trouver"):
        ValeurSourcee.model_validate(donnees)


def test_loi_uniforme_milieu_et_hypothese() -> None:
    valeur = ValeurSourcee.model_validate(PAR_37)
    assert valeur.loi is Loi.UNIFORME
    assert valeur.lire_nombre() == pytest.approx(13.15)


def test_loi_uniforme_hors_milieu_refusee() -> None:
    with pytest.raises(ValidationError, match="milieu"):
        ValeurSourcee.model_validate({**PAR_37, "valeur": 12})


def test_loi_uniforme_exige_le_statut_hypothese() -> None:
    with pytest.raises(ValidationError, match="Hypothèse"):
        ValeurSourcee.model_validate({**PAR_37, "statut": "Littérature"})


def test_loi_uniforme_sans_mode() -> None:
    with pytest.raises(ValidationError, match="triangulaire"):
        ValeurSourcee.model_validate({**PAR_37, "mode": 13})


def test_loi_triangulaire_avec_mode() -> None:
    valeur = ValeurSourcee.model_validate(PAR_24)
    assert valeur.loi is Loi.TRIANGULAIRE
    assert valeur.mode == pytest.approx(0.69)


def test_loi_triangulaire_sans_mode_refusee() -> None:
    donnees = {k: v for k, v in PAR_24.items() if k != "mode"}
    with pytest.raises(ValidationError, match="mode"):
        ValeurSourcee.model_validate(donnees)


def test_loi_triangulaire_valeur_egale_au_mode() -> None:
    with pytest.raises(ValidationError, match="mode"):
        ValeurSourcee.model_validate({**PAR_24, "valeur": 0.70})


def test_valeur_hors_fourchette_refusee() -> None:
    with pytest.raises(ValidationError, match="fourchette"):
        ValeurSourcee.model_validate({**PAR_24, "mode": 0.80, "valeur": 0.80})


def test_fourchette_sans_loi_refusee() -> None:
    donnees = {k: v for k, v in PAR_24.items() if k != "loi"}
    with pytest.raises(ValidationError, match="loi"):
        ValeurSourcee.model_validate(donnees)


def test_valeur_textuelle() -> None:
    valeur = ValeurSourcee.model_validate(
        {
            "nom": "PAR-40 · Méthode de classement par défaut",
            "valeur": "somme_ponderee",
            "unite": "—",
            "source_id": "CDC",
            "annee": 2026,
            "statut": "Hypothèse",
        }
    )
    assert valeur.lire() == "somme_ponderee"
    with pytest.raises(TypeError, match="n'est pas un nombre"):
        valeur.lire_nombre()


def test_champ_inconnu_refuse() -> None:
    with pytest.raises(ValidationError):
        ValeurSourcee.model_validate({**PAR_31, "valuer": 3})


def test_valeur_figee() -> None:
    valeur = ValeurSourcee.model_validate(PAR_31)
    with pytest.raises(ValidationError):
        valeur.valeur = 30  # type: ignore[misc]
