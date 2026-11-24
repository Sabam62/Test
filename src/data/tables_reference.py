"""Tables de référence de ``data/input/`` (sections 7.1, 13 et 14.2).

- ``residus.csv``, ``concurrence.csv``, ``facteurs_emission.csv`` : format long, une ligne par
  valeur avec sa provenance ; chaque ligne devient une :class:`ValeurSourcee` (RG-03, RG-14,
  RG-18, lois d'incertitude) et est contrôlée par le catalogue ``config/tables_reference.yaml``
  (paramètre connu, type, unité autorisée) et par les fourchettes de ``config/controles.yaml``
  (RG-19).
- ``cultures.csv`` : culture d'origine des résidus et codes CROPGRIDS (SRC-04).
- ``calendrier.csv`` : profil mensuel de chaque résidu (somme des 12 mois égale à 1).

Toutes les erreurs d'un fichier sont rassemblées dans un seul message, ligne par ligne.
"""

import calendar
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.chemins import Chemins
from src.data.provenance import ValeurSourcee
from src.data.versions import Versions
from src.lecture_yaml import lire_modele, traduire
from src.scenarios.config import Controles, charger_controles

FICHIER_CATALOGUE = "tables_reference.yaml"
COLONNES_VALEUR = [
    "parametre", "precision", "valeur", "min", "mode", "max", "loi", "unite",
    "source_id", "autres_sources", "annee", "statut", "note", "ou_trouver",
]  # fmt: skip
COLONNES_CULTURES = ["code_culture", "nom", "code_cropgrids", "source_id", "note"]
MOIS = [f"m{m:02d}" for m in range(1, len(calendar.month_name))]  # m01 … m12
COLONNES_CALENDRIER = ["code_residu", *MOIS, "source_id", "annee", "statut", "note"]


class ErreurTable(Exception):
    """Table de référence invalide ; le message liste chaque ligne fautive."""


class DefinitionParametre(BaseModel):
    """Entrée du catalogue : type, unités autorisées, choix possibles, présence obligatoire."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["nombre", "texte", "choix", "liste"]
    unites: list[str] = Field(min_length=1)
    choix: list[str] = []
    obligatoire: bool = False


class CatalogueTable(BaseModel):
    """Paramètres admis dans une table au format long."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    codes: list[str] = []
    parametres: dict[str, DefinitionParametre]


class Catalogue(BaseModel):
    """Contenu de ``config/tables_reference.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    residus: CatalogueTable
    concurrence: CatalogueTable
    facteurs_emission: CatalogueTable
    ratio_par_mode: dict[str, str]
    code_national: str = Field(min_length=1)


def charger_catalogue(chemins: Chemins) -> Catalogue:
    """Lit et valide ``config/tables_reference.yaml``."""
    return lire_modele(chemins.config / FICHIER_CATALOGUE, Catalogue)


@dataclass(frozen=True)
class Ligne:
    """Une valeur d'une table au format long, avec sa clé."""

    cle: tuple[str, ...]
    parametre: str
    precision: str
    valeur: ValeurSourcee


@dataclass(frozen=True)
class TableLongue:
    """Table au format long validée."""

    nom: str
    colonnes_cle: tuple[str, ...]
    lignes: tuple[Ligne, ...]

    def valeur(
        self, cle: str | tuple[str, ...], parametre: str, precision: str = ""
    ) -> ValeurSourcee:
        """Valeur d'un paramètre ; ``KeyError`` en français si elle n'existe pas."""
        cle = (cle,) if isinstance(cle, str) else cle
        for ligne in self.lignes:
            if (ligne.cle, ligne.parametre, ligne.precision) == (cle, parametre, precision):
                return ligne.valeur
        detail = f" ({precision})" if precision else ""
        raise KeyError(f"{self.nom} : aucune valeur {parametre}{detail} pour {' · '.join(cle)}.")

    def precisions(self, cle: str | tuple[str, ...], parametre: str) -> list[str]:
        """Précisions disponibles pour un paramètre (« trois phases », « déshydratée »…)."""
        cle = (cle,) if isinstance(cle, str) else cle
        return [x.precision for x in self.lignes if x.cle == cle and x.parametre == parametre]

    def a_completer(self) -> list[Ligne]:
        """Valeurs « À compléter » (RG-14), à saisir ou à importer."""
        return [ligne for ligne in self.lignes if ligne.valeur.est_a_completer]

    def tableau(self) -> pd.DataFrame:
        """Vue tabulaire : clé, paramètre, précision, valeur, unité, provenance."""
        enregistrements = []
        for ligne in self.lignes:
            v = ligne.valeur
            enregistrements.append(
                {
                    **dict(zip(self.colonnes_cle, ligne.cle, strict=True)),
                    "parametre": ligne.parametre,
                    "precision": ligne.precision,
                    "valeur": v.valeur,
                    "unite": v.unite,
                    "source_id": v.provenance.source_id if v.provenance else None,
                    "annee": v.provenance.annee if v.provenance else None,
                    "statut": v.provenance.statut.value if v.provenance else None,
                    "a_completer": v.est_a_completer,
                }
            )
        return pd.DataFrame(enregistrements)


def _lire_csv(chemin: Path, colonnes: list[str]) -> pd.DataFrame:
    if not chemin.is_file():
        raise ErreurTable(f"fichier introuvable : {chemin}.")
    table = pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
    absentes = [c for c in colonnes if c not in table.columns]
    if absentes:
        raise ErreurTable(f"{chemin.name} : colonnes absentes {absentes}.")
    return table[colonnes].apply(lambda colonne: colonne.str.strip())


def _nombre(texte: str) -> float | None:
    """Convertit « 0,69 » ou « 0.69 » ; chaîne vide → None."""
    return float(texte.replace(",", ".")) if texte else None


def _valeur(brute: dict[str, str], definition: DefinitionParametre, nom: str) -> ValeurSourcee:
    texte = brute["valeur"]
    if definition.type == "nombre" and texte and texte != "À compléter":
        valeur: object = _nombre(texte)
    else:
        valeur = texte
    donnees: dict[str, object] = {
        "nom": nom,
        "valeur": valeur,
        "unite": brute["unite"],
        "min": _nombre(brute["min"]),
        "mode": _nombre(brute["mode"]),
        "max": _nombre(brute["max"]),
        "loi": brute["loi"] or None,
    }
    for champ in ("source_id", "statut", "note", "ou_trouver"):
        if brute[champ]:
            donnees[champ] = brute[champ]
    if brute["annee"]:
        donnees["annee"] = int(brute["annee"])
    if brute["autres_sources"]:
        donnees["autres_sources"] = [s.strip() for s in brute["autres_sources"].split(",")]
    return ValeurSourcee.model_validate(donnees)


def _controler(
    valeur: ValeurSourcee, definition: DefinitionParametre, controles: Controles, table: str,
    parametre: str,
) -> list[str]:  # fmt: skip
    erreurs = []
    if valeur.unite not in definition.unites:
        erreurs.append(f"unité « {valeur.unite} » non autorisée ({', '.join(definition.unites)})")
    if valeur.est_a_completer:
        return erreurs
    if definition.type == "choix" and valeur.valeur not in definition.choix:
        erreurs.append(f"« {valeur.valeur} » hors des choix ({', '.join(definition.choix)})")
    if definition.type == "nombre":
        if not isinstance(valeur.valeur, float) or not math.isfinite(valeur.valeur):
            erreurs.append(f"« {valeur.valeur} » n'est pas un nombre")
            return erreurs
        fourchette = controles.fourchettes.get(table, {}).get(parametre)
        if fourchette is not None and fourchette.unite == valeur.unite:
            for borne in (valeur.valeur, valeur.min, valeur.mode, valeur.max):
                if borne is not None and not fourchette.contient(borne):
                    erreurs.append(
                        f"{borne} hors du domaine physique {fourchette.bornes()} : "
                        f"{fourchette.motif} (RG-19)"
                    )
                    break
    return erreurs


def lire_table_longue(
    chemin: Path,
    colonnes_cle: Iterable[str],
    catalogue: CatalogueTable,
    controles: Controles,
    nom_table: str,
) -> TableLongue:
    """Lit et valide une table au format long ; lève :class:`ErreurTable` au moindre défaut."""
    colonnes_cle = tuple(colonnes_cle)
    brutes = _lire_csv(chemin, [*colonnes_cle, *COLONNES_VALEUR])
    lignes, erreurs, vues = [], [], set()
    for numero, brute in enumerate(brutes.to_dict(orient="records"), start=1):
        cle = tuple(brute[c] for c in colonnes_cle)
        parametre, precision = brute["parametre"], brute["precision"]
        prefixe = f"ligne {numero} ({' · '.join(cle)} · {parametre})"
        definition = catalogue.parametres.get(parametre)
        if definition is None:
            erreurs.append(f"{prefixe} : paramètre inconnu du catalogue config/{FICHIER_CATALOGUE}")
            continue
        if (cle, parametre, precision) in vues:
            erreurs.append(f"{prefixe} : valeur en double")
            continue
        vues.add((cle, parametre, precision))
        nom = " · ".join([*cle, parametre, *([precision] if precision else [])])
        try:
            valeur = _valeur(brute, definition, nom)
        except ValidationError as erreur:
            erreurs.append(f"{prefixe} : " + " ; ".join(traduire(erreur)))
            continue
        except ValueError:
            erreurs.append(f"{prefixe} : nombre illisible")
            continue
        erreurs += [
            f"{prefixe} : {e}"
            for e in _controler(valeur, definition, controles, nom_table, parametre)
        ]
        lignes.append(Ligne(cle, parametre, precision, valeur))
    if erreurs:
        raise ErreurTable(
            f"{chemin.name} contient des erreurs :\n" + "\n".join(f"  - {e}" for e in erreurs)
        )
    return TableLongue(nom_table, colonnes_cle, tuple(lignes))


def verifier_obligatoires(
    table: TableLongue, catalogue: CatalogueTable, cles: Iterable[tuple[str, ...]]
) -> list[str]:
    """Paramètres obligatoires absents (ni valeur ni « À compléter ») pour chaque clé."""
    presents = {(ligne.cle, ligne.parametre) for ligne in table.lignes}
    obligatoires = [p for p, d in catalogue.parametres.items() if d.obligatoire]
    return [
        f"{' · '.join(cle)} : {parametre} absent"
        for cle in cles
        for parametre in obligatoires
        if (cle, parametre) not in presents
    ]


@dataclass(frozen=True)
class TablesReference:
    """Ensemble des tables de référence validées."""

    residus: TableLongue
    concurrence: TableLongue
    facteurs_emission: TableLongue
    cultures: pd.DataFrame
    calendrier: pd.DataFrame


def charger_cultures(chemin: Path) -> pd.DataFrame:
    """Lit ``cultures.csv`` : une ligne par culture et par code CROPGRIDS (vide si absent)."""
    table = _lire_csv(chemin, COLONNES_CULTURES)
    erreurs = [
        f"ligne {n} : source obligatoire (RG-18)"
        for n, s in enumerate(table["source_id"], 1)
        if not s
    ]
    erreurs += [
        f"ligne {n} : code_culture vide" for n, c in enumerate(table["code_culture"], 1) if not c
    ]
    if erreurs:
        raise ErreurTable(f"{chemin.name} : " + " ; ".join(erreurs) + ".")
    return table


def charger_calendrier(chemin: Path) -> pd.DataFrame:
    """Lit ``calendrier.csv`` ; chaque profil doit sommer à 1 et porter sa source (RG-18)."""
    table = _lire_csv(chemin, COLONNES_CALENDRIER)
    erreurs = []
    for numero, ligne in enumerate(table.to_dict(orient="records"), start=1):
        try:
            parts = [_nombre(ligne[m]) or 0.0 for m in MOIS]
        except ValueError:
            erreurs.append(f"ligne {numero} : nombre illisible")
            continue
        if not math.isclose(math.fsum(parts), 1):
            erreurs.append(
                f"ligne {numero} ({ligne['code_residu']}) : les mois somment à "
                f"{math.fsum(parts)}, pas à 1"
            )
        if any(p < 0 for p in parts):
            erreurs.append(f"ligne {numero} ({ligne['code_residu']}) : part mensuelle négative")
        if not ligne["source_id"]:
            erreurs.append(f"ligne {numero} ({ligne['code_residu']}) : source obligatoire (RG-18)")
    if erreurs:
        raise ErreurTable(f"{chemin.name} : " + " ; ".join(erreurs) + ".")
    return table


def liste(valeur: ValeurSourcee) -> list[str]:
    """Éléments d'une valeur de type liste (« ble, riz, orge » → ["ble", "riz", "orge"])."""
    texte = valeur.lire()
    return [x.strip() for x in str(texte).split(",") if x.strip()]


def _verifier_cultures_et_modes(
    residus: TableLongue, cultures: pd.DataFrame, catalogue: Catalogue
) -> list[str]:
    """Cultures connues, précisions de culture cohérentes, ratio exigé par le mode (§8.1)."""
    erreurs = []
    connues = set(cultures["code_culture"])
    for code in catalogue.residus.codes:
        try:
            listees = liste(residus.valeur(code, "codes_culture"))
            mode = str(residus.valeur(code, "mode_calcul").lire())
        except (KeyError, ValueError):
            continue  # absence déjà signalée par verifier_obligatoires
        erreurs += [
            f"{code} : culture « {c} » absente de cultures.csv" for c in listees if c not in connues
        ]
        for ligne in residus.lignes:
            if (
                ligne.cle == (code,)
                and ligne.precision in connues
                and ligne.precision not in listees
            ):
                erreurs.append(
                    f"{code} · {ligne.parametre} : précision « {ligne.precision} » "
                    "hors de codes_culture"
                )
        ratio = catalogue.ratio_par_mode.get(mode)
        if ratio is None:
            erreurs.append(f"{code} : mode « {mode} » sans ratio dans ratio_par_mode")
        elif not residus.precisions(code, ratio):
            erreurs.append(f"{code} : le mode « {mode} » exige {ratio} (valeur ou « À compléter »)")
    return erreurs


def charger_tables_reference(chemins: Chemins) -> TablesReference:
    """Lit et valide les tables de référence et leurs liens (résidus, cultures).

    Les tables que l'entreprise met à jour (résidus, concurrence, facteurs d'émission,
    calendrier) sont lues dans leur version active ; ``cultures.csv`` dans ``data/input/``.
    """
    catalogue = charger_catalogue(chemins)
    controles = charger_controles(chemins)
    dossier = chemins.saisies
    # Tables modifiables par l'entreprise : version active (RG-17), sinon fichier livré.
    versions = Versions(chemins)
    residus = lire_table_longue(
        versions.fichier("residus"), ["code_residu"], catalogue.residus, controles, "residus"
    )
    concurrence = lire_table_longue(
        versions.fichier("concurrence"),
        ["code_province", "code_residu"],
        catalogue.concurrence,
        controles,
        "concurrence",
    )
    facteurs = lire_table_longue(
        versions.fichier("facteurs_emission"),
        ["code_activite", "libelle"],
        catalogue.facteurs_emission,
        controles,
        "facteurs_emission",
    )  # fmt: skip
    cultures = charger_cultures(dossier / "cultures.csv")
    calendrier = charger_calendrier(versions.fichier("calendrier"))
    erreurs = []
    codes = catalogue.residus.codes
    trouves = {ligne.cle[0] for ligne in residus.lignes}
    erreurs += [f"résidu {c} absent de residus.csv" for c in codes if c not in trouves]
    erreurs += [
        f"résidu {c} de residus.csv absent du catalogue" for c in sorted(trouves - set(codes))
    ]
    erreurs += verifier_obligatoires(residus, catalogue.residus, [(c,) for c in codes])
    erreurs += _verifier_cultures_et_modes(residus, cultures, catalogue)
    nationales = [(catalogue.code_national, c) for c in codes]
    erreurs += verifier_obligatoires(concurrence, catalogue.concurrence, nationales)
    erreurs += [
        f"concurrence.csv : résidu {x.cle[1]} inconnu"
        for x in concurrence.lignes
        if x.cle[1] not in codes
    ]
    erreurs += [
        f"calendrier.csv : résidu {c} inconnu" for c in calendrier["code_residu"] if c not in codes
    ]
    if erreurs:
        raise ErreurTable(
            "tables de référence incohérentes :\n" + "\n".join(f"  - {e}" for e in erreurs)
        )
    return TablesReference(residus, concurrence, facteurs, cultures, calendrier)
