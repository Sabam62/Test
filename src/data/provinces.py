"""Référentiel unique des régions et provinces (RG-02, UC-DAT-03).

- Découpage : 12 régions et 75 provinces ou préfectures du RGPH 2024 (nombres contrôlés,
  ``config/referentiel.yaml``).
- Codes : code géographique du RGPH 2024 (région « 3 », province « 3061 ») ; les cartes du HCP
  (SRC-19) donnent les mêmes codes, sans zéro initial pour la province.
- Noms officiels : RGPH 2024 (SRC-09), en français et en arabe.
- Géométries et variantes de graphie des noms : cartes du HCP (SRC-19) ; leurs indicateurs
  (RGPH 2014) ne sont pas utilisés.
- Variantes : ``data/input/variantes_provinces.csv``, une ligne par variante avec sa source.

Toute ligne d'un import dont le nom n'est pas reconnu bloque l'import, avec le numéro de la
ligne et le nom fautif (RG-02).
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import geopandas as gpd
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.chemins import Chemins
from src.data.lecteurs.hcp_cartes import CODE_PROVINCE, CODE_REGION, lire_couche_hcp
from src.data.lecteurs.rgph2024 import lire_lignes_rgph2024, unites_rgph2024
from src.data.provenance import Statut
from src.lecture_yaml import lire_modele

FICHIER_CONFIG = "referentiel.yaml"
Niveau = Literal["region", "province"]
NIVEAUX: tuple[Niveau, ...] = ("region", "province")
LIBELLE_NIVEAU = {"region": "région", "province": "province"}
COLONNES_VARIANTES = ["niveau", "variante", "code", "source_id", "methode", "note"]
COLONNES_NOMS = ["nom_officiel", "nom_fr", "nom_ar_officiel", "nom_ar"]

# Normalisation : préfixes et suffixes administratifs (après suppression des accents).
_PREFIXE = re.compile(
    r"^(?:region|province|prefecture)(?: d'arrondissements?)?\s+"
    r"(?:de la |de l'|de |d'|d |des |du )?"
)
_PREFIXE_ANGLAIS = re.compile(r"^(?:prefecture|province) of\s+")
_SUFFIXE = re.compile(r"\s+(?:province|prefecture|region)$")
_PREFIXE_ARABE = re.compile(r"^(?:جهه|اقليم|عماله(?: مقاطعات)?)\s+")
_LETTRES_ARABES = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": None})


class ErreurReferentiel(Exception):
    """Référentiel incohérent (sources, nombres d'unités, variantes) ; message en français."""


class ErreurRattachement(Exception):
    """Lignes d'un import sans région ou province reconnue : l'import est bloqué (RG-02)."""

    def __init__(self, niveau: Niveau, lignes: list[int], valeurs: list[str]) -> None:
        """Construit le message qui nomme chaque ligne et chaque nom fautif."""
        self.niveau = niveau
        self.lignes = lignes
        self.valeurs = valeurs
        detail = " ; ".join(
            f"ligne {ligne} « {valeur} »" if valeur else f"ligne {ligne} (vide)"
            for ligne, valeur in zip(lignes, valeurs, strict=True)
        )
        super().__init__(
            f"Import bloqué (RG-02) : {len(lignes)} ligne(s) sans {LIBELLE_NIVEAU[niveau]} "
            f"reconnue : {detail}. Corrigez le nom, ou ajoutez la variante avec sa source dans "
            "data/input/variantes_provinces.csv (lignes numérotées à partir de la première ligne "
            "de données)."
        )


class ConfigReferentiel(BaseModel):
    """Contenu de ``config/referentiel.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_polygones: str = Field(min_length=1)
    fichier_regions: str = Field(min_length=1)
    fichier_provinces: str = Field(min_length=1)
    crs_natif_polygones: str = Field(min_length=1)
    fichier_noms_regions: str = Field(min_length=1)
    fichier_noms_provinces: str = Field(min_length=1)
    source_noms: str = Field(min_length=1)
    fichier_rgph: str = Field(min_length=1)
    nb_regions: int = Field(gt=0)
    nb_provinces: int = Field(gt=0)
    chiffres_code_province: int = Field(gt=0)
    crs_surface: str = Field(min_length=1)
    fichier_variantes: str = Field(min_length=1)


def charger_config_referentiel(chemins: Chemins) -> ConfigReferentiel:
    """Lit et valide ``config/referentiel.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONFIG, ConfigReferentiel)


def normaliser_nom(nom: object) -> str:
    """Clé de comparaison d'un nom : sans accents, casse, ponctuation ni préfixe administratif.

    « Préfecture d'Agadir-Ida-Ou-Tanane », « Agadir Ida Ou Tanane » et « Agadir Ida Outanane
    Prefecture » donnent la même clé ; de même « إقليم تاونات » et « تاونات ».
    """
    texte = unicodedata.normalize("NFKD", str(nom).strip())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = texte.lower().translate(_LETTRES_ARABES).replace("’", "'")
    texte = re.sub(r"\s+", " ", texte)
    for motif in (_PREFIXE_ANGLAIS, _PREFIXE, _SUFFIXE, _PREFIXE_ARABE):
        texte = motif.sub("", texte)
    return "".join(c for c in texte if c.isalnum())


def code_province(code_region: int, code_dans_region: int, chiffres: int) -> str:
    """Code géographique du RGPH 2024 : région suivie de la province sur ``chiffres`` chiffres."""
    return f"{int(code_region)}{int(code_dans_region):0{chiffres}d}"


@dataclass(frozen=True)
class Referentiel:
    """Régions, provinces et index des noms reconnus."""

    regions: pd.DataFrame
    provinces: pd.DataFrame
    index: dict[Niveau, dict[str, str]] = field(default_factory=dict)

    def codes(self, niveau: Niveau) -> set[str]:
        """Codes connus d'un niveau."""
        table = self.regions if niveau == "region" else self.provinces
        return set(table[f"code_{niveau}"])

    def avec_variantes(self, variantes: pd.DataFrame) -> "Referentiel":
        """Index des noms officiels du RGPH 2024 et des variantes ; refuse toute ambiguïté."""
        index: dict[Niveau, dict[str, str]] = {n: {} for n in NIVEAUX}
        origines: dict[tuple[Niveau, str], str] = {}
        conflits: list[str] = []

        def ajouter(niveau: Niveau, nom: str, code: str, origine: str) -> None:
            cle = normaliser_nom(nom)
            if not cle:
                return
            deja = index[niveau].get(cle)
            if deja is not None and deja != code:
                conflits.append(
                    f"« {nom} » ({origine}) désigne {code}, mais {origines[(niveau, cle)]} "
                    f"la rattache à {deja}"
                )
                return
            index[niveau][cle] = code
            origines.setdefault((niveau, cle), origine)

        for niveau, table in (("region", self.regions), ("province", self.provinces)):
            for _, ligne in table.iterrows():
                for colonne in COLONNES_NOMS:
                    ajouter(niveau, ligne[colonne], ligne[f"code_{niveau}"], "RGPH 2024")
        inconnus = []
        for numero, ligne in enumerate(variantes.itertuples(index=False), start=1):
            if ligne.code not in self.codes(ligne.niveau):
                inconnus.append(f"ligne {numero} : code {ligne.code} inconnu ({ligne.niveau})")
                continue
            ajouter(ligne.niveau, ligne.variante, ligne.code, f"la variante de {ligne.source_id}")
        if inconnus:
            raise ErreurReferentiel("variantes : " + " ; ".join(inconnus) + ".")
        if conflits:
            raise ErreurReferentiel(
                "variantes ambiguës, un même nom pour deux codes : " + " ; ".join(conflits) + "."
            )
        return Referentiel(self.regions, self.provinces, index)

    def rattacher(self, valeurs: pd.Series, niveau: Niveau) -> list[str]:
        """Code de chaque valeur (nom, variante ou code) ; bloque l'import si une seule manque."""
        codes = self.codes(niveau)
        trouves, lignes, fautives = [], [], []
        for numero, valeur in enumerate(valeurs.tolist(), start=1):
            texte = "" if pd.isna(valeur) else str(valeur).strip()
            code = (
                texte if texte in codes else self.index.get(niveau, {}).get(normaliser_nom(texte))
            )
            if code is None:
                lignes.append(numero)
                fautives.append(texte)
            trouves.append(code)
        if lignes:
            raise ErreurRattachement(niveau, lignes, fautives)
        return trouves


def charger_variantes(chemin: Path) -> pd.DataFrame:
    """Lit ``variantes_provinces.csv`` (séparateur « ; ») et vérifie chaque ligne (RG-18)."""
    if not chemin.is_file():
        raise ErreurReferentiel(f"fichier des variantes introuvable : {chemin}.")
    table = pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
    absentes = [c for c in COLONNES_VARIANTES if c not in table.columns]
    if absentes:
        raise ErreurReferentiel(f"{chemin.name} : colonnes absentes {absentes}.")
    table = table[COLONNES_VARIANTES].apply(lambda colonne: colonne.str.strip())
    erreurs = []
    for numero, ligne in enumerate(table.itertuples(index=False), start=1):
        if ligne.niveau not in NIVEAUX:
            erreurs.append(f"ligne {numero} : niveau « {ligne.niveau} » (region ou province)")
        if not ligne.variante or not ligne.code:
            erreurs.append(f"ligne {numero} : variante ou code vide")
        if not ligne.source_id:
            erreurs.append(f"ligne {numero} : source obligatoire (RG-18)")
    if erreurs:
        raise ErreurReferentiel(f"{chemin.name} : " + " ; ".join(erreurs) + ".")
    return table


def _codes_hcp(regions: pd.DataFrame, provinces: pd.DataFrame, chiffres: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code_province": [
                code_province(r, p, chiffres)
                for r, p in zip(provinces[CODE_REGION], provinces[CODE_PROVINCE], strict=True)
            ],
            "code_region": provinces[CODE_REGION].astype(int).astype(str).to_numpy(),
        }
    )


def construire_referentiel(
    unites: pd.DataFrame,
    regions_hcp: pd.DataFrame,
    provinces_hcp: pd.DataFrame,
    config: ConfigReferentiel,
) -> Referentiel:
    """Croise les unités du RGPH 2024 et les codes des cartes du HCP, et contrôle le découpage.

    Args:
        unites: sortie de :func:`unites_rgph2024`.
        regions_hcp: au moins la colonne ``code_reg`` de la couche RGPH:regions.
        provinces_hcp: au moins ``code_reg`` et ``code_prov`` de la couche RGPH:provinces.
        config: nombres attendus et format des codes.
    """
    erreurs: list[str] = []
    rgph = {n: unites[unites["niveau"] == n].set_index("code") for n in NIVEAUX}
    hcp = _codes_hcp(regions_hcp, provinces_hcp, config.chiffres_code_province)
    codes_cartes = {
        "region": set(regions_hcp[CODE_REGION].astype(int).astype(str)),
        "province": set(hcp["code_province"]),
    }
    for niveau, attendu in (("region", config.nb_regions), ("province", config.nb_provinces)):
        pluriel = f"{LIBELLE_NIVEAU[niveau]}s"
        for origine, codes in (
            ("RGPH 2024", set(rgph[niveau].index)),
            ("cartes HCP", codes_cartes[niveau]),
        ):
            if len(codes) != attendu:
                erreurs.append(f"{attendu} {pluriel} attendues, {len(codes)} dans {origine}")
        for code in sorted(set(rgph[niveau].index) - codes_cartes[niveau]):
            erreurs.append(
                f"{code} ({rgph[niveau].loc[code, 'nom_officiel']}) absent des cartes du HCP"
            )
        for code in sorted(codes_cartes[niveau] - set(rgph[niveau].index)):
            erreurs.append(
                f"{LIBELLE_NIVEAU[niveau]} {code} des cartes du HCP absente du RGPH 2024"
            )
    if hcp["code_province"].duplicated().any():
        erreurs.append("code de province en double dans les cartes du HCP")
    incoherentes = hcp[
        ~hcp.apply(lambda ligne: ligne["code_province"].startswith(ligne["code_region"]), axis=1)
    ]
    erreurs += [f"province {c} hors de sa région" for c in incoherentes["code_province"]]
    if erreurs:
        raise ErreurReferentiel("référentiel incohérent : " + " ; ".join(erreurs) + ".")
    regions = rgph["region"][COLONNES_NOMS].rename_axis("code_region").reset_index()
    provinces = (
        rgph["province"][COLONNES_NOMS]
        .rename_axis("code_province")
        .reset_index()
        .merge(hcp, on="code_province", validate="one_to_one")
    )
    provinces = provinces[["code_province", "code_region", *COLONNES_NOMS]]
    return Referentiel(regions, provinces).avec_variantes(pd.DataFrame(columns=COLONNES_VARIANTES))


def _couches(
    chemins: Chemins, config: ConfigReferentiel
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    dossier = chemins.brutes / config.source_polygones
    for nom in (config.fichier_regions, config.fichier_provinces):
        if not (dossier / nom).is_file():
            raise ErreurReferentiel(
                f"{dossier / nom} absent : lancez « python -m scripts.download --source "
                f"{config.source_polygones} » (voir docs/donnees_manuelles.md)."
            )
    crs = config.crs_natif_polygones
    regions = lire_couche_hcp(dossier / config.fichier_regions, [CODE_REGION], crs)
    provinces = lire_couche_hcp(
        dossier / config.fichier_provinces, [CODE_REGION, CODE_PROVINCE], crs
    )
    return regions, provinces


def charger_referentiel(chemins: Chemins) -> Referentiel:
    """Référentiel complet depuis ``data/raw/`` (SRC-09, SRC-19) et les variantes saisies."""
    config = charger_config_referentiel(chemins)
    fichier_rgph = chemins.brutes / config.source_noms / config.fichier_rgph
    if not fichier_rgph.is_file():
        raise ErreurReferentiel(
            f"{fichier_rgph} absent : lancez « python -m scripts.download --source "
            f"{config.source_noms} »."
        )
    regions, provinces = _couches(chemins, config)
    unites = unites_rgph2024(lire_lignes_rgph2024(fichier_rgph))
    referentiel = construire_referentiel(unites, regions, provinces, config)
    return referentiel.avec_variantes(charger_variantes(chemins.saisies / config.fichier_variantes))


def geodonnees_referentiel(
    chemins: Chemins, referentiel: Referentiel
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Polygones des régions et provinces avec noms, superficie (km²) et provenance."""
    config = charger_config_referentiel(chemins)
    regions_hcp, provinces_hcp = _couches(chemins, config)
    regions_hcp["code_region"] = regions_hcp[CODE_REGION].astype(str)
    provinces_hcp["code_province"] = _codes_hcp(
        regions_hcp, provinces_hcp, config.chiffres_code_province
    )["code_province"].to_numpy()
    regions = regions_hcp[["code_region", "geometry"]].merge(
        referentiel.regions, on="code_region", validate="one_to_one"
    )
    provinces = provinces_hcp[["code_province", "geometry"]].merge(
        referentiel.provinces, on="code_province", validate="one_to_one"
    )
    sorties = []
    for table in (regions, provinces):
        table = gpd.GeoDataFrame(table, geometry="geometry", crs=regions_hcp.crs)
        table["superficie_km2"] = table.to_crs(config.crs_surface).area
        table["source_id"] = config.source_polygones
        table["statut_superficie"] = Statut.ESTIMEE.value
        table["source_noms"] = config.source_noms
        sorties.append(table)
    return sorties[0], sorties[1]


def enregistrer_referentiel(chemins: Chemins, dossier: Path | None = None) -> list[Path]:
    """Écrit ``regions.gpkg`` et ``provinces.gpkg`` (section 13) dans ``data/processed/``."""
    dossier = dossier or chemins.preparees
    dossier.mkdir(parents=True, exist_ok=True)
    regions, provinces = geodonnees_referentiel(chemins, charger_referentiel(chemins))
    sorties = []
    for nom, table in (("regions", regions), ("provinces", provinces)):
        cible = dossier / f"{nom}.gpkg"
        provisoire = dossier / f".{nom}.provisoire.gpkg"
        table.to_file(provisoire, layer=nom, driver="GPKG")
        os.replace(provisoire, cible)
        sorties.append(cible)
    return sorties
