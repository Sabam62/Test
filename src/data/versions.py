"""Versions des données mises à jour par l'entreprise (RG-17, UC-DAT-08).

Chaque modification crée une version : les tables modifiées sont copiées dans
``data/versions/<id>/`` et une entrée est ajoutée au journal ``data/versions.yaml`` (auteur,
date, commentaire, tables, lignes ajoutées, modifiées, supprimées). Rien n'est écrasé : une
restauration crée elle aussi une version, qui recopie à l'octet près les fichiers de la version
restaurée. La table active est celle de la dernière version qui la contient, sinon son fichier
de base (``config/versions.yaml``).
"""

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.lecture_yaml import lire_modele, lire_yaml, valider

FICHIER_CONFIG = "versions.yaml"
SEPARATEUR_CSV = ";"
EXTENSIONS = {"csv": ".csv", "parquet": ".parquet"}


class ErreurVersion(Exception):
    """Opération sur les versions impossible ; message en français."""


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ColonneProvince(_Strict):
    """Colonne rattachée au référentiel des provinces (RG-02)."""

    colonne: str
    codes_admis: list[str] = []


class ControleValeurs(_Strict):
    """Colonnes numériques contrôlées par les fourchettes de ``controles.yaml`` (RG-19)."""

    colonnes: list[str] = Field(min_length=1)
    table_fourchettes: str
    fourchette: str | None = None
    fourchette_selon: str | None = None


class ControleVariation(_Strict):
    """Variation par rapport à la campagne précédente (RG-19)."""

    colonne_campagne: str
    groupe: list[str] = Field(min_length=1)


class DefinitionTable(_Strict):
    """Une table versionnée."""

    libelle: str
    fichier: str
    format: Literal["csv", "parquet"]
    cle: list[str] = Field(min_length=1)
    province: ColonneProvince | None = None
    valeurs: ControleValeurs | None = None
    source: str
    date: str
    format_date: Literal["annee", "iso"]
    variation: ControleVariation | None = None


class ConfigVersions(_Strict):
    """Contenu de ``config/versions.yaml``."""

    journal: str
    dossier: str
    prefixe_version: str
    chiffres_version: int = Field(gt=0)
    tolerance_relative_excel: float = Field(ge=0)
    tables: dict[str, DefinitionTable] = Field(min_length=1)


class Version(_Strict):
    """Entrée du journal des versions (section 13, table ``versions``)."""

    id_version: str
    date: str
    auteur: str = Field(min_length=1)
    commentaire: str = Field(min_length=1)
    tables_modifiees: list[str]
    nb_lignes_ajoutees: int
    nb_lignes_modifiees: int
    nb_lignes_supprimees: int
    restauration_de: str | None = None


class Journal(_Strict):
    """Contenu de ``data/versions.yaml``."""

    versions: list[Version] = []


@dataclass(frozen=True)
class Difference:
    """Lignes ajoutées, modifiées et supprimées d'une table entre deux états."""

    ajoutees: pd.DataFrame
    modifiees: pd.DataFrame
    supprimees: pd.DataFrame
    avant: pd.DataFrame

    @property
    def vide(self) -> bool:
        """Vrai si les deux états sont identiques."""
        return self.ajoutees.empty and self.modifiees.empty and self.supprimees.empty


def charger_config_versions(chemins: Chemins) -> ConfigVersions:
    """Lit et valide ``config/versions.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigVersions)


def lire_fichier(chemin: Path, format_: str) -> pd.DataFrame:
    """Lit une table : CSV en texte (séparateur « ; »), Parquet avec ses types."""
    if format_ == "csv":
        return pd.read_csv(
            chemin, sep=SEPARATEUR_CSV, dtype=str, keep_default_na=False, encoding="utf-8"
        )
    return pd.read_parquet(chemin)


def ecrire_fichier(table: pd.DataFrame, chemin: Path, format_: str) -> None:
    """Écrit une table au format de sa définition, sans jamais remplacer un fichier existant."""
    if chemin.exists():
        raise ErreurVersion(f"{chemin} existe déjà : une version n'est jamais réécrite (RG-17)")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if format_ == "csv":
        table.to_csv(chemin, sep=SEPARATEUR_CSV, index=False, encoding="utf-8", lineterminator="\n")
    else:
        table.to_parquet(chemin, index=False)


def _textes(table: pd.DataFrame) -> pd.DataFrame:
    """Valeurs comparables : texte, vide pour une valeur absente."""
    return table.astype(object).where(table.notna(), "").astype(str)


def comparer_tables(avant: pd.DataFrame, apres: pd.DataFrame, cle: list[str]) -> Difference:
    """Différence ligne à ligne entre deux états d'une table, par sa clé."""
    for nom, table in (("avant", avant), ("après", apres)):
        absentes = [c for c in cle if c not in table.columns]
        if absentes:
            raise ErreurVersion(f"table {nom} : colonnes de clé absentes {', '.join(absentes)}")
        doublons = table[table.duplicated(cle, keep=False)]
        if not doublons.empty:
            exemple = ", ".join(_textes(doublons[cle]).iloc[0])
            raise ErreurVersion(f"table {nom} : clé en double ({exemple})")
    a, b = _textes(avant).set_index(cle), _textes(apres).set_index(cle)
    communes = a.index.intersection(b.index)
    colonnes = [c for c in b.columns if c in a.columns]
    differentes = (a.loc[communes, colonnes] != b.loc[communes, colonnes]).any(axis=1)
    if set(a.columns) != set(b.columns):
        differentes[:] = True
    modifiees = differentes[differentes].index
    return Difference(
        ajoutees=apres[b.index.isin(b.index.difference(a.index))].reset_index(drop=True),
        modifiees=apres[b.index.isin(modifiees)].reset_index(drop=True),
        supprimees=avant[a.index.isin(a.index.difference(b.index))].reset_index(drop=True),
        avant=avant[a.index.isin(modifiees)].reset_index(drop=True),
    )


class Versions:
    """Journal et copies des versions de ``data/``."""

    def __init__(self, chemins: Chemins) -> None:
        """Ouvre les versions de ``chemins`` (le journal peut ne pas encore exister)."""
        self.chemins = chemins
        self.config = charger_config_versions(chemins)

    # --- Lecture ---------------------------------------------------------------------------

    @property
    def chemin_journal(self) -> Path:
        """``data/versions.yaml``."""
        return self.chemins.donnees / self.config.journal

    def journal(self) -> list[Version]:
        """Versions, de la plus ancienne à la plus récente."""
        if not self.chemin_journal.is_file():
            return []
        donnees = lire_yaml(self.chemin_journal) or {}
        return valider(donnees, Journal, self.config.journal).versions

    def version(self, id_version: str) -> Version:
        """Entrée du journal ; erreur si la version est inconnue."""
        for version in self.journal():
            if version.id_version == id_version:
                return version
        raise ErreurVersion(f"version « {id_version} » inconnue")

    def definition(self, table: str) -> DefinitionTable:
        """Définition d'une table versionnée."""
        try:
            return self.config.tables[table]
        except KeyError:
            connues = ", ".join(self.config.tables)
            raise ErreurVersion(f"table « {table} » inconnue ; tables : {connues}") from None

    def _dossier(self, id_version: str) -> Path:
        return self.chemins.donnees / self.config.dossier / id_version

    def _copie(self, table: str, id_version: str) -> Path:
        definition = self.definition(table)
        return self._dossier(id_version) / f"{table}{EXTENSIONS[definition.format]}"

    def fichier(self, table: str, id_version: str | None = None) -> Path:
        """Fichier de ``table`` à ``id_version`` (par défaut, l'état actif)."""
        definition = self.definition(table)
        versions = self.journal()
        if id_version is not None:
            self.version(id_version)
            rang = [v.id_version for v in versions].index(id_version)
            versions = versions[: rang + 1]
        for version in reversed(versions):
            if table in version.tables_modifiees:
                return self._copie(table, version.id_version)
        return self.chemins.donnees / definition.fichier

    def lire(self, table: str, id_version: str | None = None) -> pd.DataFrame:
        """Table à ``id_version`` (par défaut, l'état actif)."""
        chemin = self.fichier(table, id_version)
        if not chemin.is_file():
            raise ErreurVersion(
                f"{chemin.relative_to(self.chemins.racine)} absent : lancez "
                "« python -m scripts.prepare »"
            )
        return lire_fichier(chemin, self.definition(table).format)

    def comparer(self, table: str, id_avant: str | None, id_apres: str | None) -> Difference:
        """Différence de ``table`` entre deux versions (None : état de base pour id_avant)."""
        avant_chemin = (
            self.chemins.donnees / self.definition(table).fichier
            if id_avant is None
            else self.fichier(table, id_avant)
        )
        avant = lire_fichier(avant_chemin, self.definition(table).format)
        return comparer_tables(avant, self.lire(table, id_apres), self.definition(table).cle)

    # --- Écriture --------------------------------------------------------------------------

    def prochain_identifiant(self) -> str:
        """Identifiant de la prochaine version (v0001, v0002…)."""
        numero = len(self.journal()) + 1
        return f"{self.config.prefixe_version}{numero:0{self.config.chiffres_version}d}"

    def _inscrire(self, version: Version) -> None:
        journal = Journal(versions=[*self.journal(), version])
        texte = yaml.safe_dump(journal.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
        provisoire = self.chemin_journal.with_name(f".{self.chemin_journal.name}.provisoire")
        provisoire.write_text(texte, encoding="utf-8")
        os.replace(provisoire, self.chemin_journal)

    @staticmethod
    def _verifier_signature(auteur: str, commentaire: str) -> None:
        if not auteur.strip():
            raise ErreurVersion("indiquez l'auteur de la modification (UC-DAT-08)")
        if not commentaire.strip():
            raise ErreurVersion("indiquez un commentaire décrivant la modification (UC-DAT-08)")

    def integrer_livraisons(self, auteur: str) -> list[Version]:
        """Nouvelle version pour chaque fichier livré de ``data/input/`` qui a changé (RG-17).

        Un fichier de base mis à jour avec l'outil (nouvelles valeurs sourcées) ne serait jamais
        lu, la table active étant celle de la dernière version : il devient donc une version
        « nouvelle livraison », restaurable comme les autres. L'empreinte de la dernière
        livraison intégrée est gardée dans ``data/versions/livraisons.yaml`` ; sans elle, la
        référence est la copie de la première version.
        """
        registre = self.chemins.donnees / self.config.dossier / "livraisons.yaml"
        connues: dict[str, str] = {}
        if registre.is_file():
            connues = dict(yaml.safe_load(registre.read_text(encoding="utf-8")) or {})
        journal = self.journal()
        nouvelles = []
        for nom, definition in self.config.tables.items():
            base = self.chemins.donnees / definition.fichier
            if not definition.fichier.startswith("input/") or not base.is_file():
                continue
            empreinte = hashlib.sha256(base.read_bytes()).hexdigest()
            reference = connues.get(nom)
            if reference is None and journal and nom in journal[0].tables_modifiees:
                copie = self._copie(nom, journal[0].id_version)
                reference = hashlib.sha256(copie.read_bytes()).hexdigest()
            if reference is not None and reference != empreinte:
                version = self.enregistrer(
                    {nom: lire_fichier(base, definition.format)},
                    auteur,
                    f"nouvelle livraison de {definition.fichier}",
                )
                if version is not None:
                    nouvelles.append(version)
            connues[nom] = empreinte
        registre.parent.mkdir(parents=True, exist_ok=True)
        registre.write_text(yaml.safe_dump(connues, sort_keys=True), encoding="utf-8")
        return nouvelles

    def initialiser(self, auteur: str, commentaire: str) -> Version | None:
        """Première version : copie, à l'octet près, des fichiers de base existants.

        Sans effet si le journal contient déjà une version. Elle permet de restaurer l'état livré
        après une première modification.
        """
        self._verifier_signature(auteur, commentaire)
        if self.journal():
            return None
        presentes = {
            nom: self.chemins.donnees / d.fichier
            for nom, d in self.config.tables.items()
            if (self.chemins.donnees / d.fichier).is_file()
        }
        if not presentes:
            return None
        id_version = self.prochain_identifiant()
        lignes = 0
        for nom, source in presentes.items():
            copie = self._copie(nom, id_version)
            if copie.exists():
                raise ErreurVersion(f"{copie} existe déjà (RG-17)")
            copie.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copie)
            lignes += len(lire_fichier(copie, self.config.tables[nom].format))
        version = Version(
            id_version=id_version,
            date=datetime.now().isoformat(timespec="seconds"),
            auteur=auteur.strip(),
            commentaire=commentaire.strip(),
            tables_modifiees=sorted(presentes),
            nb_lignes_ajoutees=lignes,
            nb_lignes_modifiees=0,
            nb_lignes_supprimees=0,
        )
        self._inscrire(version)
        return version

    def enregistrer(
        self, tables: dict[str, pd.DataFrame], auteur: str, commentaire: str
    ) -> Version | None:
        """Crée une version avec les tables qui diffèrent de l'état actif ; None si aucune."""
        self._verifier_signature(auteur, commentaire)
        differences = {}
        for nom, table in tables.items():
            definition = self.definition(nom)
            actif = self.fichier(nom)
            avant = lire_fichier(actif, definition.format) if actif.is_file() else table.iloc[0:0]
            difference = comparer_tables(avant, table, definition.cle)
            if not difference.vide:
                differences[nom] = (table, difference)
        if not differences:
            return None
        id_version = self.prochain_identifiant()
        for nom, (table, _) in differences.items():
            ecrire_fichier(table, self._copie(nom, id_version), self.definition(nom).format)
        version = Version(
            id_version=id_version,
            date=datetime.now().isoformat(timespec="seconds"),
            auteur=auteur.strip(),
            commentaire=commentaire.strip(),
            tables_modifiees=sorted(differences),
            nb_lignes_ajoutees=sum(len(d.ajoutees) for _, d in differences.values()),
            nb_lignes_modifiees=sum(len(d.modifiees) for _, d in differences.values()),
            nb_lignes_supprimees=sum(len(d.supprimees) for _, d in differences.values()),
        )
        self._inscrire(version)
        return version

    def restaurer(self, id_version: str, auteur: str, commentaire: str) -> Version | None:
        """Nouvelle version qui recopie, à l'octet près, les tables de ``id_version``."""
        self._verifier_signature(auteur, commentaire)
        self.version(id_version)
        a_copier = {}
        ajoutees = modifiees = supprimees = 0
        for nom, definition in self.config.tables.items():
            cible, actif = self.fichier(nom, id_version), self.fichier(nom)
            if not cible.is_file() or cible == actif:
                continue
            if actif.is_file() and cible.read_bytes() == actif.read_bytes():
                continue
            restauree = lire_fichier(cible, definition.format)
            courante = (
                lire_fichier(actif, definition.format) if actif.is_file() else restauree.iloc[0:0]
            )
            difference = comparer_tables(courante, restauree, definition.cle)
            ajoutees += len(difference.ajoutees)
            modifiees += len(difference.modifiees)
            supprimees += len(difference.supprimees)
            a_copier[nom] = cible
        if not a_copier:
            return None
        nouvelle = self.prochain_identifiant()
        for nom, source in a_copier.items():
            copie = self._copie(nom, nouvelle)
            if copie.exists():
                raise ErreurVersion(f"{copie} existe déjà (RG-17)")
            copie.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copie)
        version = Version(
            id_version=nouvelle,
            date=datetime.now().isoformat(timespec="seconds"),
            auteur=auteur.strip(),
            commentaire=commentaire.strip(),
            tables_modifiees=sorted(a_copier),
            nb_lignes_ajoutees=ajoutees,
            nb_lignes_modifiees=modifiees,
            nb_lignes_supprimees=supprimees,
            restauration_de=id_version,
        )
        self._inscrire(version)
        return version
