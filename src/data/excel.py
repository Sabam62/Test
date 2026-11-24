"""Import par modèle Excel (UC-DAT-06, RG-17 à RG-19).

1. :func:`modele_excel` : classeur pré-rempli avec la table active, et deux feuilles d'aide
   (« mode d'emploi », « unités et fourchettes »).
2. :func:`analyser_import` : le classeur déposé est comparé à la table active. Lignes
   ajoutées, modifiées, rejetées (avec le motif) et à confirmer (hors fourchette ou variation
   excessive, RG-19). Une province non reconnue bloque l'import (RG-02). Une ligne absente du
   classeur n'est pas supprimée.
3. :func:`valider_import` : enregistre une nouvelle version avec les lignes acceptées et les
   lignes à confirmer que l'utilisateur a confirmées (RG-17).

Les lignes sont numérotées comme dans Excel (la ligne 1 porte les en-têtes).
"""

import io
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.data.observations import campagne_precedente, campagne_valide
from src.data.provenance import A_COMPLETER
from src.data.provinces import ErreurRattachement, Referentiel
from src.data.versions import DefinitionTable, Version, Versions
from src.scenarios.config import Controles

FEUILLE_DONNEES = "données"
FEUILLE_MODE = "mode d'emploi"
FEUILLE_UNITES = "unités et fourchettes"
COLONNE_LIGNE = "_ligne_excel"
# Numérotation Excel : en-têtes sur la ligne 1, données à partir de la ligne suivante.
LIGNE_EN_TETES = 1
PREMIERE_LIGNE_EXCEL = LIGNE_EN_TETES + 1
VRAI = {"true", "vrai", "oui", "1"}
SEPARATEUR_CLE = "\x1f"
COLONNE_VERSION = "version"


class ErreurImport(Exception):
    """Classeur illisible ou incomplet ; message en français."""


@dataclass
class AnalyseImport:
    """Résultat de l'analyse d'un classeur déposé, avant validation."""

    table: str
    actuelle: pd.DataFrame
    acceptees: pd.DataFrame
    ajoutees: list[int] = field(default_factory=list)
    modifiees: list[int] = field(default_factory=list)
    rejetees: dict[int, str] = field(default_factory=dict)
    a_confirmer: dict[int, str] = field(default_factory=dict)


def _mode_d_emploi(definition: DefinitionTable) -> list[str]:
    return [
        f"Table : {definition.libelle}.",
        "1. Modifiez ou ajoutez des lignes dans la feuille « données » ; ne renommez pas les "
        "colonnes.",
        f"2. Chaque ligne modifiée ou ajoutée indique sa source (colonne « {definition.source} ») "
        f"et sa date (colonne « {definition.date} ») ; sinon elle est rejetée (RG-18).",
        "3. Une valeur hors du domaine physique (feuille « unités et fourchettes », colonnes "
        "minimum et maximum) est rejetée ; une valeur hors de la fourchette plausible (colonnes "
        "plausible min et plausible max) ou 10 fois supérieure à la campagne précédente est "
        "signalée et doit être confirmée (RG-19).",
        "4. Une province s'écrit par son code ou son nom ; un nom inconnu bloque l'import (RG-02).",
        "5. Une ligne supprimée du classeur n'est pas supprimée de la table.",
        "6. Déposez le fichier sur la page Données : l'outil affiche les lignes ajoutées, "
        "modifiées et rejetées, puis enregistre une nouvelle version après validation (RG-17).",
        f"Colonnes de la clé d'une ligne : {', '.join(definition.cle)}.",
    ]


def _fourchettes(definition: DefinitionTable, controles: Controles) -> pd.DataFrame:
    lignes = []
    if definition.valeurs is not None:
        table = controles.fourchettes.get(definition.valeurs.table_fourchettes, {})
        for nom, fourchette in table.items():
            lignes.append(
                {
                    "grandeur": nom,
                    "unité": fourchette.unite,
                    "minimum": fourchette.min,
                    "maximum": fourchette.max,
                    "plausible min": fourchette.plausible.min if fourchette.plausible else None,
                    "plausible max": fourchette.plausible.max if fourchette.plausible else None,
                    "motif": fourchette.motif,
                }
            )
    return pd.DataFrame(
        lignes,
        columns=[
            "grandeur",
            "unité",
            "minimum",
            "maximum",
            "plausible min",
            "plausible max",
            "motif",
        ],
    )


def modele_excel(versions: Versions, table: str, controles: Controles) -> bytes:
    """Classeur Excel pré-rempli avec l'état actif de ``table``."""
    definition = versions.definition(table)
    donnees = versions.lire(table)
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as classeur:
        donnees.to_excel(classeur, sheet_name=FEUILLE_DONNEES, index=False)
        pd.DataFrame({"mode d'emploi": _mode_d_emploi(definition)}).to_excel(
            classeur, sheet_name=FEUILLE_MODE, index=False
        )
        _fourchettes(definition, controles).to_excel(
            classeur, sheet_name=FEUILLE_UNITES, index=False
        )
    return tampon.getvalue()


def _lire_classeur(contenu: bytes, actuelle: pd.DataFrame) -> pd.DataFrame:
    try:
        lu = pd.read_excel(io.BytesIO(contenu), sheet_name=FEUILLE_DONNEES, dtype=object)
    except ValueError as erreur:
        raise ErreurImport(
            f"feuille « {FEUILLE_DONNEES} » introuvable : partez du modèle téléchargé ({erreur})"
        ) from None
    except Exception:
        raise ErreurImport("fichier illisible : déposez un classeur Excel (.xlsx)") from None
    absentes = [c for c in actuelle.columns if c not in lu.columns]
    if absentes:
        raise ErreurImport(f"colonnes absentes de la feuille « données » : {', '.join(absentes)}")
    lu = lu[list(actuelle.columns)]
    lu[COLONNE_LIGNE] = range(PREMIERE_LIGNE_EXCEL, PREMIERE_LIGNE_EXCEL + len(lu))
    return lu.dropna(how="all", subset=list(actuelle.columns))


def _vide(valeur: object) -> bool:
    return (
        valeur is None
        or (isinstance(valeur, float) and math.isnan(valeur))
        or (isinstance(valeur, str) and not valeur.strip())
    )


def _typer(
    lu: pd.DataFrame, actuelle: pd.DataFrame, format_: str, rejetees: dict[int, str]
) -> pd.DataFrame:
    """Ramène chaque colonne au type de la table active ; une cellule illisible rejette la ligne.

    Table CSV : tout est texte, une cellule vide devient « ». Table Parquet : nombres, booléens
    et textes, une cellule vide devient une valeur absente.
    """
    typee = lu.copy()
    vide = "" if format_ == "csv" else None
    for colonne, type_ in actuelle.dtypes.items():
        valeurs = lu[colonne]
        if format_ == "csv" or not (
            pd.api.types.is_numeric_dtype(type_) or pd.api.types.is_bool_dtype(type_)
        ):
            typee[colonne] = valeurs.map(lambda v: vide if _vide(v) else str(v).strip())
        elif pd.api.types.is_bool_dtype(type_):
            typee[colonne] = valeurs.map(
                lambda v: v if isinstance(v, bool) else str(v).strip().lower() in VRAI
            ).astype(bool)
        else:
            texte = valeurs.map(lambda v: None if _vide(v) else str(v).strip().replace(",", "."))
            nombres = pd.to_numeric(texte, errors="coerce")
            illisibles = nombres.isna() & texte.notna()
            for ligne in lu.loc[illisibles, COLONNE_LIGNE]:
                rejetees.setdefault(int(ligne), f"colonne « {colonne} » : nombre illisible")
            nombres = nombres.where(~illisibles)
            if pd.api.types.is_integer_dtype(type_):
                nombres = nombres.round()
            typee[colonne] = nombres.astype(type_)
    return typee


def _texte_vide(valeur: object) -> bool:
    return _vide(valeur) or str(valeur).strip() == A_COMPLETER


def _nombre(valeur: object) -> float | None:
    if _texte_vide(valeur):
        return None
    try:
        return float(str(valeur).replace(",", "."))
    except ValueError:
        return None


class _Analyse:
    def __init__(
        self,
        definition: DefinitionTable,
        controles: Controles,
        table: str,
    ) -> None:
        self.definition = definition
        self.controles = controles
        self.table = table

    def controler_ligne(self, ligne: pd.Series) -> tuple[str | None, str | None]:
        """(motif de rejet, motif à confirmer) d'une ligne ajoutée ou modifiée."""
        d = self.definition
        valeurs = d.valeurs.colonnes if d.valeurs else []
        renseignee = any(not _texte_vide(ligne[c]) for c in valeurs) if valeurs else True
        if renseignee and _vide(ligne[d.source]):
            return f"source obligatoire (RG-18) : colonne « {d.source} » vide", None
        if renseignee and _vide(ligne[d.date]):
            return f"date obligatoire (RG-18) : colonne « {d.date} » vide", None
        if d.valeurs is None:
            return None, None
        fourchettes = self.controles.fourchettes.get(d.valeurs.table_fourchettes, {})
        nom = d.valeurs.fourchette or str(ligne[d.valeurs.fourchette_selon or ""])
        for colonne in valeurs:
            if _texte_vide(ligne[colonne]):
                continue
            nombre = _nombre(ligne[colonne])
            if nombre is None:
                return f"colonne « {colonne} » : nombre illisible", None
            fourchette = fourchettes.get(nom)
            if fourchette is not None:
                rejet, a_confirmer = fourchette.controler(nom, nombre)
                if rejet or a_confirmer:
                    return rejet, a_confirmer
        return None, None

    def variation(self, proposee: pd.DataFrame, ligne: pd.Series) -> str | None:
        """Motif « à confirmer » si la valeur dépasse ``facteur_max`` × campagne précédente."""
        d = self.definition
        if d.variation is None or d.valeurs is None:
            return None
        nom = d.valeurs.fourchette or str(ligne[d.valeurs.fourchette_selon or ""])
        regle = self.controles.variation(self.table, nom)
        campagne = str(ligne[d.variation.colonne_campagne])
        if regle is None or not campagne_valide(campagne):
            return None
        masque = proposee[d.variation.colonne_campagne] == campagne_precedente(campagne)
        for colonne in d.variation.groupe:
            masque &= proposee[colonne].astype(str) == str(ligne[colonne])
        precedentes = proposee.loc[masque, d.valeurs.colonnes[0]].map(_nombre).dropna()
        valeur = _nombre(ligne[d.valeurs.colonnes[0]])
        if precedentes.empty or valeur is None:
            return None
        precedente = float(precedentes.iloc[0])
        if precedente > 0 and valeur > regle.facteur_max * precedente:
            return (
                f"{nom} = {valeur:g}, plus de {regle.facteur_max:g} fois la campagne précédente "
                f"({precedente:g}) : {regle.motif}"
            )
        return None


def _rattacher(
    lu: pd.DataFrame, definition: DefinitionTable, referentiel: Referentiel
) -> pd.DataFrame:
    """Codes de province du référentiel (RG-02) ; un nom inconnu bloque l'import."""
    if definition.province is None:
        return lu
    colonne = definition.province.colonne
    admis = set(definition.province.codes_admis)
    a_rattacher = ~lu[colonne].astype(str).isin(admis)
    sous = lu.loc[a_rattacher]
    try:
        codes = referentiel.rattacher(sous[colonne], "province")
    except ErreurRattachement as erreur:
        lignes = [int(sous[COLONNE_LIGNE].iloc[n - 1]) for n in erreur.lignes]
        raise ErreurRattachement("province", lignes, erreur.valeurs) from None
    lu = lu.copy()
    lu.loc[a_rattacher, colonne] = codes
    return lu


def analyser_import(
    contenu: bytes,
    table: str,
    versions: Versions,
    controles: Controles,
    referentiel: Referentiel,
) -> AnalyseImport:
    """Compare le classeur déposé à la table active, sans rien enregistrer."""
    definition = versions.definition(table)
    actuelle = versions.lire(table)
    rejetees: dict[int, str] = {}
    lu = _rattacher(_lire_classeur(contenu, actuelle), definition, referentiel)
    lu = _typer(lu, actuelle, definition.format, rejetees)
    analyse = _Analyse(definition, controles, table)
    cle = definition.cle
    obligatoires = [c for c in cle if not actuelle[c].map(_vide).any()]
    cles_lues = _cles(lu, cle)
    doublons = cles_lues.duplicated(keep="first")
    for numero in lu.loc[doublons.to_numpy(), COLONNE_LIGNE]:
        rejetees.setdefault(int(numero), "clé en double dans le classeur")
    position_de = pd.Series(actuelle.index, index=_cles(actuelle, cle))
    positions = cles_lues.map(position_de)
    inchangees = _inchangees(lu, actuelle, positions, versions.config.tolerance_relative_excel)
    resultat = AnalyseImport(table, actuelle, lu.iloc[0:0])
    candidates = []
    for (_, ligne), position, inchangee in zip(lu.iterrows(), positions, inchangees, strict=True):
        numero = int(ligne[COLONNE_LIGNE])
        if numero in rejetees or inchangee:
            continue
        if any(_vide(ligne[c]) for c in obligatoires):
            rejetees[numero] = f"clé incomplète ({', '.join(obligatoires)})"
            continue
        rejet, a_confirmer = analyse.controler_ligne(ligne)
        if rejet:
            rejetees[numero] = rejet
            continue
        candidates.append((numero, ligne, pd.isna(position), a_confirmer))
    proposee = _appliquer(actuelle, [c[1] for c in candidates], cle)
    for numero, ligne, nouvelle, a_confirmer in candidates:
        a_confirmer = a_confirmer or analyse.variation(proposee, ligne)
        if a_confirmer:
            resultat.a_confirmer[numero] = a_confirmer
        (resultat.ajoutees if nouvelle else resultat.modifiees).append(numero)
    resultat.rejetees = rejetees
    resultat.acceptees = pd.DataFrame([c[1] for c in candidates], columns=lu.columns)
    return resultat


def _cles(table: pd.DataFrame, cle: list[str]) -> pd.Series:
    """Clé texte de chaque ligne (colonnes de la clé jointes)."""
    textes = table[cle].astype(object).where(table[cle].notna(), "").astype(str)
    return textes.agg(SEPARATEUR_CLE.join, axis=1)


def _inchangees(
    lu: pd.DataFrame, actuelle: pd.DataFrame, positions: pd.Series, tolerance: float
) -> list[bool]:
    """Vrai pour chaque ligne lue identique à la ligne active de même clé."""
    connues = positions.notna().to_numpy()
    egales = connues.copy()
    if not connues.any():
        return egales.tolist()
    avant = actuelle.loc[positions[connues].astype(int)].reset_index(drop=True)
    apres = lu.loc[connues, list(actuelle.columns)].reset_index(drop=True)
    identiques = pd.Series(True, index=avant.index)
    for colonne in actuelle.columns:
        a, b = avant[colonne], apres[colonne]
        absents = a.isna() & b.isna()
        if pd.api.types.is_numeric_dtype(
            actuelle[colonne].dtype
        ) and not pd.api.types.is_bool_dtype(actuelle[colonne].dtype):
            x = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
            proches = np.isclose(x, y, rtol=tolerance, atol=0)
            identiques &= absents | pd.Series(proches, index=avant.index)
        else:
            ta = a.astype(object).where(a.notna(), "").astype(str)
            tb = b.astype(object).where(b.notna(), "").astype(str)
            identiques &= absents | (ta == tb)
    egales[connues] = identiques.to_numpy()
    return egales.tolist()


def _appliquer(actuelle: pd.DataFrame, lignes: list[pd.Series], cle: list[str]) -> pd.DataFrame:
    """Table active où chaque ligne remplace celle de même clé, ou s'ajoute à la fin."""
    if not lignes:
        return actuelle.copy()
    nouvelles = pd.DataFrame(lignes)[list(actuelle.columns)].reset_index(drop=True)
    cles_nouvelles = _cles(nouvelles, cle)
    position_de = pd.Series(actuelle.index, index=_cles(actuelle, cle))
    remplacantes = cles_nouvelles.isin(position_de.index)
    resultat = actuelle.astype(object)
    for i in nouvelles.index[remplacantes.to_numpy()]:
        resultat.loc[position_de[cles_nouvelles[i]]] = nouvelles.loc[i].to_numpy()
    resultat = pd.concat(
        [resultat, nouvelles[~remplacantes.to_numpy()].astype(object)], ignore_index=True
    )
    for colonne, type_ in actuelle.dtypes.items():
        try:
            resultat[colonne] = resultat[colonne].astype(type_)
        except (TypeError, ValueError):
            continue
    return resultat


def valider_import(
    analyse: AnalyseImport,
    versions: Versions,
    confirmees: set[int],
    auteur: str,
    commentaire: str,
) -> Version | None:
    """Enregistre une version avec les lignes acceptées et celles confirmées (RG-17, RG-19).

    Une ligne à confirmer que l'utilisateur n'a pas confirmée n'est pas importée.
    """
    definition = versions.definition(analyse.table)
    lignes = analyse.acceptees[
        ~analyse.acceptees[COLONNE_LIGNE].isin(set(analyse.a_confirmer) - confirmees)
    ]
    lignes = lignes.drop(columns=[COLONNE_LIGNE])
    if COLONNE_VERSION in lignes.columns:
        lignes[COLONNE_VERSION] = versions.prochain_identifiant()
    nouvelle = _appliquer(
        versions.lire(analyse.table), [ligne for _, ligne in lignes.iterrows()], definition.cle
    )
    return versions.enregistrer({analyse.table: nouvelle}, auteur, commentaire)
