"""Chargement et validation des fichiers YAML de config/ et de data/sources.yaml."""

import shutil
from pathlib import Path

import pytest
import yaml

from src.chemins import Chemins, chemins_par_defaut
from src.data.provenance import Statut, ValeurACompleter
from src.data.sources import charger_sources
from src.lecture_yaml import ErreurConfiguration
from src.scenarios.config import (
    charger_controles,
    charger_entreprise,
    charger_parametres,
)
from tests.aides import copier_config

DEPOT = chemins_par_defaut()

# Identifiants des tableaux 14.1 et 14.3 du cahier des charges.
PARAMETRES_14_1 = {
    "PAR-01",
    "PAR-21",
    "PAR-34",
    "PAR-59",
    "PAR-52",
    "PAR-53",
    "PAR-51",
    "PAR-55",
    "PAR-56",
    "PAR-57",
    "PAR-37",
}
PARAMETRES_14_3 = {
    "PAR-02",
    "PAR-03",
    "PAR-04",
    "PAR-14",
    "PAR-20",
    "PAR-24",
    "PAR-27",
    "PAR-31",
    "PAR-38",
    "PAR-37",
    "PAR-39",
    "PAR-33",
    "PAR-61",
    "PAR-62",
    "PAR-63",
    "PAR-30",
    "PAR-32",
    "PAR-35",
    "PAR-36",
    "PAR-40",
    "PAR-41",
    "PAR-42",
    "PAR-43",
    "PAR-44",
    "PAR-45",
    "PAR-54",
}


@pytest.fixture
def copie(tmp_path: Path) -> Chemins:
    """Copie de config/ et de data/sources.yaml, modifiable par le test."""
    copier_config(DEPOT.config, tmp_path / "config")
    (tmp_path / "data").mkdir()
    shutil.copy(DEPOT.donnees / "sources.yaml", tmp_path / "data" / "sources.yaml")
    return Chemins(tmp_path)


# --- Paramètres techniques (14.3) ---------------------------------------------------------


def test_parametres_charges() -> None:
    parametres = charger_parametres(DEPOT)
    assert set(parametres.parametres) == PARAMETRES_14_3


def test_parametres_valeurs_du_cahier() -> None:
    parametres = charger_parametres(DEPOT)
    assert parametres["PAR-03"].lire() == 1000
    assert parametres["PAR-04"].lire() == 42
    assert parametres["PAR-31"].lire() == 25
    assert parametres["PAR-38"].lire() == 35
    assert parametres["PAR-39"].lire() == 39
    assert parametres["PAR-44"].lire() == pytest.approx(0.10)
    gwp = parametres["PAR-27"]
    assert [gwp.composante(c).lire() for c in ["co2", "ch4_fossile", "ch4_biogenique", "n2o"]] == [
        1,
        29.8,
        27.0,
        273,
    ]
    fperm = parametres["PAR-20"]
    assert [fperm.composante(c).lire() for c in ["basse", "moyenne", "haute"]] == [0.65, 0.80, 0.89]


def test_parametres_a_completer_rg14() -> None:
    parametres = charger_parametres(DEPOT)
    for identifiant in ["PAR-32", "PAR-61"]:
        with pytest.raises(ValeurACompleter, match=identifiant):
            parametres[identifiant].lire()
        assert parametres[identifiant].valeur.statut_attendu is Statut.TERRAIN  # type: ignore[union-attr]


def test_fourchettes_en_loi_uniforme_hypothese() -> None:
    parametres = charger_parametres(DEPOT)
    gazole = parametres["PAR-37"].valeur
    assert gazole is not None and gazole.provenance is not None
    assert (gazole.min, gazole.max) == (10.80, 15.50)
    assert gazole.provenance.statut is Statut.HYPOTHESE
    assert gazole.provenance.note is not None
    assert "milieu de fourchette" in gazole.provenance.note


def test_parametres_calcules() -> None:
    parametres = charger_parametres(DEPOT)
    assert set(parametres["PAR-33"].calcul.entrees) == {"PAR-37", "PAR-38", "PAR-39"}  # type: ignore[union-attr]
    with pytest.raises(TypeError, match="calculé"):
        parametres["PAR-30"].lire()


def test_parametre_inconnu() -> None:
    with pytest.raises(KeyError, match="PAR-99"):
        charger_parametres(DEPOT)["PAR-99"]


def test_parametres_sans_source_refuses(copie: Chemins) -> None:
    fichier = copie.config / "parametres.yaml"
    texte = fichier.read_text(encoding="utf-8")
    retrait = "    source_id: SRC-16-MEDIAS24-2026\n"  # PAR-31, première occurrence
    fichier.write_text(texte.replace(retrait, "", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="RG-18") as erreur:
        charger_parametres(copie)
    assert "parametres.yaml" in str(erreur.value)


def test_calcul_avec_entree_inconnue(copie: Chemins) -> None:
    fichier = copie.config / "parametres.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("- PAR-39", "- PAR-99", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="PAR-99"):
        charger_parametres(copie)


# --- Paramètres de l'entreprise (14.1, RG-15) ---------------------------------------------


def test_entreprise_livre_vide() -> None:
    entreprise = charger_entreprise(DEPOT, avec_saisies=False)
    assert set(entreprise.parametres) == PARAMETRES_14_1
    assert all(p.valeur is None for p in entreprise.parametres.values())
    assert entreprise.date_modification is None
    assert entreprise.auteur is None


def test_entreprise_vide_renseignement_requis_rg15() -> None:
    entreprise = charger_entreprise(DEPOT, avec_saisies=False)
    assert entreprise.renseignement_requis is True
    assert entreprise.a_renseigner == list(PARAMETRES_OBLIGATOIRES)
    assert entreprise.obligatoires == list(PARAMETRES_OBLIGATOIRES)
    with pytest.raises(ValeurACompleter, match="PAR-01"):
        entreprise.lire("PAR-01")


# Saisie simulée pour le test : le cahier ne cite aucune capacité K. Cette valeur n'existe que
# dans tests/, écrite dans une copie temporaire de config/ ; elle n'est jamais une donnée livrée.
K_SAISIE_SIMULEE_POUR_LE_TEST = 1000
# RG-15 (décision du 22/11/2026 : PAR-37 ajouté aux trois paramètres d'origine).
PARAMETRES_OBLIGATOIRES = ("PAR-01", "PAR-21", "PAR-34", "PAR-37")


def _saisir(copie: Chemins, saisies: dict[str, float]) -> None:
    """Simule une saisie de l'utilisateur dans le fichier local de la copie temporaire."""
    fichier = copie.config / "entreprise.local.yaml"
    fichier.write_text(yaml.safe_dump({"valeurs": saisies}, allow_unicode=True), encoding="utf-8")


def test_saisies_lues_par_dessus_le_modele_livre(copie: Chemins) -> None:
    _saisir(copie, {"PAR-34": 300})
    assert charger_entreprise(copie).lire("PAR-34") == 300
    assert not charger_entreprise(copie, avec_saisies=False).parametres["PAR-34"].renseigne


def test_modele_livre_contenant_une_valeur_refuse(copie: Chemins) -> None:
    fichier = copie.config / "entreprise.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("valeur: null", "valeur: 300", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match=r"entreprise\.local\.yaml"):
        charger_entreprise(copie)


def test_saisie_d_un_parametre_retire_du_modele_ignoree(copie: Chemins) -> None:
    """Une saisie locale d'un paramètre retiré (PAR-58, 23/11/2026) n'empêche pas le chargement."""
    _saisir(copie, {"PAR-58": "VM0044", "PAR-21": 450})
    entreprise = charger_entreprise(copie)
    assert "PAR-58" not in entreprise.parametres
    assert entreprise.lire("PAR-21") == 450


def test_renseignement_requis_tant_qu_un_parametre_manque(copie: Chemins) -> None:
    # Valeurs citées par le cahier : 450 °C (§14.2, Alburquerque et al., 2016) et
    # 300 DH/t (exemple du cahier, prix plafond). PAR-01 et PAR-37 restent vides.
    _saisir(copie, {"PAR-21": 450, "PAR-34": 300})
    entreprise = charger_entreprise(copie)
    assert entreprise.lire("PAR-21") == 450
    assert entreprise.parametres["PAR-34"].renseigne
    assert entreprise.renseignement_requis is True
    assert entreprise.a_renseigner == ["PAR-01", "PAR-37"]


def test_renseignement_non_requis_une_fois_tout_saisi(copie: Chemins) -> None:
    _saisir(
        copie,
        {
            "PAR-01": K_SAISIE_SIMULEE_POUR_LE_TEST,
            "PAR-21": 450,
            "PAR-34": 300,
            # Gazole à 12 DH/L : exemple du calcul de PAR-33 au §14.3.
            "PAR-37": 12,
        },
    )
    entreprise = charger_entreprise(copie)
    assert entreprise.renseignement_requis is False
    assert entreprise.a_renseigner == []
    assert entreprise.lire("PAR-01") == K_SAISIE_SIMULEE_POUR_LE_TEST


def test_gazole_non_saisi_bloque_le_calcul_rg14() -> None:
    # PAR-37 : seule la valeur saisie par l'entreprise compte ; la fourchette 14.3 est un repère.
    with pytest.raises(ValeurACompleter, match="PAR-37"):
        charger_entreprise(DEPOT, avec_saisies=False).lire("PAR-37")


def test_config_livree_sans_saisie_simulee() -> None:
    texte = (DEPOT.config / "entreprise.yaml").read_text(encoding="utf-8")
    assert "valeur: null" in texte
    modele = charger_entreprise(DEPOT, avec_saisies=False)
    assert all(p.valeur is None for p in modele.parametres.values())


def test_entreprise_sans_parametre_obligatoire(copie: Chemins) -> None:
    fichier = copie.config / "entreprise.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("    obligatoire: true\n", ""), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="obligatoire"):
        charger_entreprise(copie)


# --- Contrôles avant import (RG-19) -------------------------------------------------------


def test_controles_charges() -> None:
    controles = charger_controles(DEPOT)
    humidite = controles.fourchette("residus", "humidite")
    assert humidite.contient(45)
    assert not humidite.contient(101)
    assert controles.fourchette("production", "production_t").contient(370028)
    assert not controles.fourchette("production", "production_t").contient(-1)
    variation = controles.variation("production", "production_t")
    assert variation is not None and variation.facteur_max == 10


def test_controles_colonne_inconnue() -> None:
    with pytest.raises(KeyError, match="inexistante"):
        charger_controles(DEPOT).fourchette("residus", "inexistante")


def test_controles_bornes_inversees(copie: Chemins) -> None:
    fichier = copie.config / "controles.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("max: 100", "max: -5", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="minimum"):
        charger_controles(copie)


# --- Manifeste des sources (RG-05) --------------------------------------------------------


def test_sources_du_catalogue_7_1() -> None:
    manifeste = charger_sources(DEPOT)
    attendues = {f"SRC-{n:02d}" for n in range(1, 20)}
    assert attendues <= set(manifeste.sources)
    for identifiant in attendues:
        assert manifeste.sources[identifiant].parent is None


def test_publications_rattachees_a_un_src() -> None:
    manifeste = charger_sources(DEPOT)
    for identifiant, source in manifeste.sources.items():
        if not identifiant.startswith("SRC-") or source.parent is None:
            continue
        assert source.parent in manifeste.sources
        assert manifeste.sources[source.parent].parent is None
        assert identifiant.startswith(f"{source.parent}-"), identifiant


def test_toutes_les_sources_citees_existent() -> None:
    manifeste = charger_sources(DEPOT)
    citees: set[str] = set()
    for valeur in charger_parametres(DEPOT).valeurs():
        if valeur.provenance is not None:
            citees.add(valeur.provenance.source_id)
            citees.update(valeur.provenance.autres_sources)
    assert citees
    assert manifeste.inconnues(citees) == []


def test_parent_inconnu_refuse(copie: Chemins) -> None:
    fichier = copie.donnees / "sources.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("parent: SRC-16", "parent: SRC-99", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="SRC-99"):
        charger_sources(copie)


# --- Lecture des YAML : messages en français (ENF-12) -------------------------------------


def test_fichier_absent(tmp_path: Path) -> None:
    with pytest.raises(ErreurConfiguration, match="introuvable"):
        charger_parametres(Chemins(tmp_path))


def test_yaml_mal_forme(copie: Chemins) -> None:
    (copie.config / "controles.yaml").write_text("fourchettes: [\n", encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="ligne"):
        charger_controles(copie)


def test_cle_en_double(copie: Chemins) -> None:
    fichier = copie.config / "entreprise.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("  PAR-21:", "  PAR-01:", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="en double"):
        charger_entreprise(copie)


def test_type_invalide_message_francais(copie: Chemins) -> None:
    fichier = copie.config / "parametres.yaml"
    texte = fichier.read_text(encoding="utf-8")
    fichier.write_text(texte.replace("valeur: 1000", "valeur: [1000]", 1), encoding="utf-8")
    with pytest.raises(ErreurConfiguration) as erreur:
        charger_parametres(copie)
    message = str(erreur.value)
    assert "PAR-03" in message
    assert "Input should" not in message
