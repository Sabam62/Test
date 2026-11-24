"""Exports CSV et Excel de tout tableau affiché (UC-RES-02, ENF-05, ENF-14).

Le classeur Excel contient le tableau, une feuille « paramètres » (paramètres de l'entreprise,
paramètres techniques, réglages de la décision) et une feuille « sources » (manifeste avec
licence et attribution). Un classement partiel porte en tête le bandeau « Classement partiel :
n critères sur N » et la liste des critères retirés avec leur motif (décision du 23/11/2026).
Pendant une démonstration, le bandeau « Démonstration — paramètres d'hypothèse, pas un résultat
réel » est la première ligne sous le titre (CSV : première ligne de commentaire).
Le CSV (séparateur « ; », virgule décimale, UTF-8 avec BOM, lisible par Excel en français)
reprend le bandeau en lignes de commentaire.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.lecture_yaml import lire_modele

NOM_PARAMETRES, NOM_SOURCES = "paramètres", "sources"


class ConfigExcel(BaseModel):
    """Mise en forme du classeur."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    longueur_nom_feuille: int = Field(gt=0)
    largeur_min: int = Field(gt=0)
    largeur_max: int = Field(gt=0)
    marge: int = Field(ge=0)
    taille_titre: int = Field(gt=0)


class ConfigCsv(BaseModel):
    """Format du CSV."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    separateur: str = Field(min_length=1)
    chiffres_significatifs: int = Field(gt=0)


class ConfigRestitution(BaseModel):
    """Contenu de ``config/restitution.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    excel: ConfigExcel
    csv: ConfigCsv
    lignes_gisements: int = Field(gt=0)


def charger_config_restitution(chemins: Chemins) -> ConfigRestitution:
    """Lit et valide ``config/restitution.yaml``."""
    return lire_modele(chemins.config / "restitution.yaml", ConfigRestitution)


@dataclass(frozen=True)
class Colonne:
    """Colonne exportée : clé dans les lignes, libellé et unité (dans l'en-tête)."""

    cle: str
    libelle: str
    unite: str | None = None

    @property
    def entete(self) -> str:
        """« Libellé (unité) »."""
        return f"{self.libelle} ({self.unite})" if self.unite else self.libelle


@dataclass(frozen=True)
class Partiel:
    """Bandeau d'un classement partiel."""

    utilises: int
    actifs: int
    retires: dict[str, str] = field(default_factory=dict)
    libelles: dict[str, str] = field(default_factory=dict)

    def lignes(self) -> list[str]:
        """Texte du bandeau, une ligne par critère retiré."""
        if not self.retires:
            return []
        tete = f"Classement partiel : {self.utilises} critères sur {self.actifs}"
        return [tete] + [
            f"{code} · {self.libelles.get(code, code)} : {motif}"
            for code, motif in self.retires.items()
        ]


@dataclass(frozen=True)
class Export:
    """Un tableau à exporter et ses annexes."""

    titre: str
    colonnes: list[Colonne]
    lignes: list[dict[str, object]]
    parametres: pd.DataFrame  # rubrique, identifiant, libelle, valeur, unite, source, statut
    sources: pd.DataFrame  # source_id, titre, url, licence, attribution, parent
    partiel: Partiel | None = None
    notes: list[str] = field(default_factory=list)
    demo: str | None = None  # bandeau de démonstration, en tête (src.scenarios.demo)


def _valeur(v: object) -> object:
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, list | dict):
        return ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    return v


def _nom_feuille(titre: str, config: ConfigExcel) -> str:
    interdits = str.maketrans({c: " " for c in "[]:*?/\\"})
    return titre.translate(interdits).strip()[: config.longueur_nom_feuille] or "tableau"


def _ajuster(feuille, config: ConfigExcel) -> None:  # noqa: ANN001
    for rang, colonne in enumerate(feuille.columns, start=1):
        largeur = max(
            (len(str(c.value)) for c in colonne if c.value is not None), default=config.largeur_min
        )
        feuille.column_dimensions[get_column_letter(rang)].width = min(
            max(largeur + config.marge, config.largeur_min), config.largeur_max
        )


def classeur_excel(export: Export, config: ConfigExcel) -> bytes:
    """Classeur Excel : tableau (avec bandeau éventuel), « paramètres », « sources »."""
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = _nom_feuille(export.titre, config)
    feuille.append([export.titre])
    feuille["A1"].font = Font(bold=True, size=config.taille_titre)
    if export.demo:
        feuille.append([export.demo])
        feuille.cell(row=feuille.max_row, column=1).font = Font(bold=True)
    feuille.append([f"Exporté le {datetime.now():%d/%m/%Y à %H:%M} · Atlantic Biochar"])
    bandeau = export.partiel.lignes() if export.partiel else []
    for rang, texte in enumerate(bandeau):
        feuille.append([texte])
        if rang == 0:
            feuille.cell(row=feuille.max_row, column=1).font = Font(bold=True)
    for note in export.notes:
        feuille.append([note])
    feuille.append([])
    feuille.append([c.entete for c in export.colonnes])
    for cellule in feuille[feuille.max_row]:
        cellule.font = Font(bold=True)
    feuille.freeze_panes = feuille.cell(row=feuille.max_row + 1, column=1)
    for ligne in export.lignes:
        feuille.append([_valeur(ligne.get(c.cle)) for c in export.colonnes])
    _ajuster(feuille, config)
    for nom, table in ((NOM_PARAMETRES, export.parametres), (NOM_SOURCES, export.sources)):
        annexe = classeur.create_sheet(nom)
        annexe.append(list(table.columns))
        for cellule in annexe[1]:
            cellule.font = Font(bold=True)
        for valeurs in table.itertuples(index=False):
            annexe.append([_valeur(v) for v in valeurs])
        _ajuster(annexe, config)
    sortie = io.BytesIO()
    classeur.save(sortie)
    return sortie.getvalue()


def _texte_csv(v: object, chiffres: int) -> str:
    v = _valeur(v)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, float):
        return f"{v:.{chiffres}g}".replace(".", ",")
    return str(v)


def fichier_csv(export: Export, config: ConfigCsv) -> bytes:
    """CSV du tableau, bandeau éventuel en lignes de commentaire « # »."""
    tampon = io.StringIO()
    demo = [export.demo] if export.demo else []
    for texte in [*demo, *(export.partiel.lignes() if export.partiel else []), *export.notes]:
        tampon.write(f"# {texte}\n")
    ecrivain = csv.writer(tampon, delimiter=config.separateur, lineterminator="\n")
    ecrivain.writerow([c.entete for c in export.colonnes])
    for ligne in export.lignes:
        ecrivain.writerow(
            [_texte_csv(ligne.get(c.cle), config.chiffres_significatifs) for c in export.colonnes]
        )
    return ("﻿" + tampon.getvalue()).encode("utf-8")
