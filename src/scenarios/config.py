"""Chargement et validation des fichiers de ``config/``.

- ``parametres.yaml`` : paramètres techniques de la section 14.3, chacun avec unité et source ;
- ``entreprise.yaml`` : paramètres de l'entreprise de la section 14.1, livrés vides (RG-15) ;
- ``controles.yaml`` : fourchettes plausibles par colonne et règles de variation (RG-19).
"""

from collections.abc import Iterator
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.chemins import Chemins
from src.data.provenance import ValeurACompleter, ValeurSourcee
from src.lecture_yaml import ErreurConfiguration, lire_modele, lire_yaml, valider

FICHIER_PARAMETRES = "parametres.yaml"
FICHIER_ENTREPRISE = "entreprise.yaml"
# Saisies de l'entreprise : fichier local, ignoré par Git, lu par-dessus le modèle livré vide.
FICHIER_ENTREPRISE_LOCAL = "entreprise.local.yaml"
FICHIER_CONTROLES = "controles.yaml"

PAGE_ENTREPRISE = "onglet « Paramètres », section Entreprise (RG-15)"


def _injecter_cles(donnees: object, champ: str, cle: str) -> object:
    """Copie la clé de chaque entrée de ``donnees[champ]`` dans son champ ``cle``."""
    if isinstance(donnees, dict) and isinstance(donnees.get(champ), dict):
        donnees = {
            **donnees,
            champ: {
                k: {cle: k, **v} if isinstance(v, dict) else v for k, v in donnees[champ].items()
            },
        }
    return donnees


# --- Paramètres techniques (14.3) ---------------------------------------------------------


class Calcul(BaseModel):
    """Paramètre calculé par l'outil à partir d'autres paramètres ou de données."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    methode: str = Field(min_length=1)
    unite: str = Field(min_length=1)
    entrees: tuple[str, ...] = ()


class Parametre(BaseModel):
    """Paramètre technique : une valeur, des composantes (par classe, par produit) ou un calcul."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifiant: str = Field(min_length=1)
    libelle: str = Field(min_length=1)
    valeur: ValeurSourcee | None = None
    composantes: dict[str, ValeurSourcee] | None = None
    calcul: Calcul | None = None
    choix: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _structurer(cls, donnees: object) -> object:
        """Accepte la valeur « à plat » (valeur, unite, source_id…) au niveau du paramètre."""
        if not isinstance(donnees, dict):
            return donnees
        donnees = dict(donnees)
        nom = f"{donnees.get('identifiant')} · {donnees.get('libelle')}"
        composantes = donnees.get("composantes")
        if isinstance(composantes, dict):
            donnees["composantes"] = {
                cle: {"nom": f"{nom} · {cle}", **val} if isinstance(val, dict) else val
                for cle, val in composantes.items()
            }
        propres = {"identifiant", "libelle", "valeur", "composantes", "calcul", "choix"}
        a_plat = {k: donnees.pop(k) for k in list(donnees) if k not in propres}
        if "valeur" in donnees or a_plat:
            donnees["valeur"] = {"nom": nom, "valeur": donnees.get("valeur"), **a_plat}
        return donnees

    @model_validator(mode="after")
    def _une_seule_forme(self) -> Self:
        formes = [f for f in (self.valeur, self.composantes, self.calcul) if f is not None]
        if len(formes) != 1:
            raise ValueError(
                f"{self.identifiant} : donnez soit une valeur, soit des composantes, "
                "soit un calcul."
            )
        return self

    def lire(self) -> float | str:
        """Valeur du paramètre ; lève :class:`ValeurACompleter` si elle manque (RG-14)."""
        if self.valeur is None:
            forme = "calculé par l'outil" if self.calcul else "décomposé : lisez une composante"
            raise TypeError(f"{self.identifiant} est {forme}.")
        return self.valeur.lire()

    def composante(self, cle: str) -> ValeurSourcee:
        """Composante ``cle`` d'un paramètre décomposé (par classe, par produit…)."""
        if not self.composantes or cle not in self.composantes:
            raise KeyError(f"{self.identifiant} n'a pas de composante « {cle} ».")
        return self.composantes[cle]


class ParametresTechniques(BaseModel):
    """Contenu de ``config/parametres.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parametres: dict[str, Parametre]

    @model_validator(mode="before")
    @classmethod
    def _identifiants(cls, donnees: object) -> object:
        return _injecter_cles(donnees, "parametres", "identifiant")

    @model_validator(mode="after")
    def _entrees_connues(self) -> Self:
        for parametre in self.parametres.values():
            if parametre.calcul is None:
                continue
            inconnues = [e for e in parametre.calcul.entrees if e not in self.parametres]
            if inconnues:
                raise ValueError(
                    f"{parametre.identifiant} : entrées du calcul inconnues : "
                    f"{', '.join(inconnues)}."
                )
        return self

    def __getitem__(self, identifiant: str) -> Parametre:
        """Paramètre ``identifiant`` ; lève ``KeyError`` avec un message français s'il manque."""
        if identifiant not in self.parametres:
            raise KeyError(f"Paramètre {identifiant} absent de {FICHIER_PARAMETRES}.")
        return self.parametres[identifiant]

    def valeurs(self) -> Iterator[ValeurSourcee]:
        """Toutes les valeurs sourcées, composantes comprises."""
        for parametre in self.parametres.values():
            if parametre.valeur is not None:
                yield parametre.valeur
            if parametre.composantes:
                yield from parametre.composantes.values()


# --- Paramètres de l'entreprise (14.1) ----------------------------------------------------


class ParametreEntreprise(BaseModel):
    """Paramètre réglé par Atlantic Biochar ; ``None`` tant qu'il n'est pas renseigné."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifiant: str = Field(min_length=1)
    libelle: str = Field(min_length=1)
    unite: str = Field(min_length=1)
    type: Literal["nombre", "choix", "nombre_ou_choix", "sites"] = "nombre"
    choix: list[str] = []
    obligatoire: bool = False
    valeur: float | str | list[str] | dict[str, list[str]] | None = None

    @property
    def renseigne(self) -> bool:
        """Vrai si l'entreprise a saisi une valeur."""
        return self.valeur is not None


class ParametresEntreprise(BaseModel):
    """Paramètres de l'entreprise : modèle ``config/entreprise.yaml`` et saisies locales."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date_modification: date | None = None
    auteur: str | None = None
    parametres: dict[str, ParametreEntreprise]

    @model_validator(mode="before")
    @classmethod
    def _identifiants(cls, donnees: object) -> object:
        return _injecter_cles(donnees, "parametres", "identifiant")

    @model_validator(mode="after")
    def _au_moins_un_obligatoire(self) -> Self:
        if not self.obligatoires:
            raise ValueError("aucun paramètre marqué « obligatoire: true » (RG-15).")
        return self

    @property
    def obligatoires(self) -> list[str]:
        """Paramètres obligatoires de la RG-15, dans l'ordre de entreprise.yaml."""
        return [i for i, p in self.parametres.items() if p.obligatoire]

    @property
    def a_renseigner(self) -> list[str]:
        """Paramètres obligatoires encore vides (RG-15)."""
        return [i for i in self.obligatoires if not self.parametres[i].renseigne]

    @property
    def renseignement_requis(self) -> bool:
        """Vrai tant qu'un paramètre obligatoire manque : aucune valeur n'est supposée."""
        return bool(self.a_renseigner)

    def lire(self, identifiant: str) -> float | str | list[str] | dict[str, list[str]]:
        """Valeur saisie ; lève :class:`ValeurACompleter` si l'entreprise ne l'a pas renseignée."""
        parametre = self.parametres.get(identifiant)
        if parametre is None:
            raise KeyError(f"Paramètre {identifiant} absent de {FICHIER_ENTREPRISE}.")
        if parametre.valeur is None:
            raise ValeurACompleter(f"{identifiant} · {parametre.libelle}", PAGE_ENTREPRISE)
        return parametre.valeur


# --- Contrôles avant import (RG-19) -------------------------------------------------------


def _bornes(bas: float | None, haut: float | None) -> str:
    """« [0 ; 100] », « [0 ; –] »."""
    return f"[{'–' if bas is None else f'{bas:g}'} ; {'–' if haut is None else f'{haut:g}'}]"


class Plage(BaseModel):
    """Fourchette des valeurs plausibles, à fixer par l'entreprise à partir d'une source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min: float | None = None
    max: float | None = None
    motif: str = Field(min_length=1)

    def contient(self, valeur: float) -> bool:
        """Vrai si ``valeur`` est dans la plage."""
        return (self.min is None or valeur >= self.min) and (self.max is None or valeur <= self.max)


class Fourchette(BaseModel):
    """Contrôles d'une colonne (RG-19).

    ``min`` et ``max`` : domaine physique ou de définition (humidité ≤ 100 %, valeur positive,
    part ≤ 1) ; une valeur hors du domaine est rejetée. ``plausible`` : plage des valeurs
    vraisemblables ; une valeur hors de cette plage est signalée et doit être confirmée.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    min: float | None = None
    max: float | None = None
    unite: str = Field(min_length=1)
    motif: str = Field(min_length=1)
    plausible: Plage | None = None

    @model_validator(mode="after")
    def _ordre(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"le minimum {self.min} dépasse le maximum {self.max}.")
        return self

    def contient(self, valeur: float) -> bool:
        """Vrai si ``valeur`` est dans le domaine physique."""
        if self.min is not None and valeur < self.min:
            return False
        return self.max is None or valeur <= self.max

    def bornes(self) -> str:
        """Domaine physique, « [0 ; 100] »."""
        return _bornes(self.min, self.max)

    def controler(self, nom: str, valeur: float) -> tuple[str | None, str | None]:
        """(motif de rejet, motif à confirmer) de ``valeur`` (RG-19)."""
        if not self.contient(valeur):
            return (
                f"{nom} = {valeur:g} hors du domaine physique {self.bornes()} : {self.motif} ; "
                "valeur refusée (RG-19)",
                None,
            )
        if self.plausible is not None and not self.plausible.contient(valeur):
            plage = _bornes(self.plausible.min, self.plausible.max)
            return None, (
                f"{nom} = {valeur:g} hors de la fourchette plausible {plage} : "
                f"{self.plausible.motif} ; à confirmer (RG-19)"
            )
        return None, None


class RegleVariation(BaseModel):
    """Variation maximale d'une colonne par rapport à la campagne précédente (RG-19)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    table: str = Field(min_length=1)
    colonne: str = Field(min_length=1)
    facteur_max: float = Field(gt=0)
    reference: str = Field(min_length=1)
    motif: str = Field(min_length=1)


class RegleAberrantes(BaseModel):
    """Seuil des valeurs aberrantes du rapport de contrôle (UC-DAT-02)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ecarts_types: float = Field(gt=0)
    effectif_minimal: int = Field(gt=1)
    motif: str = Field(min_length=1)


class RegleDesagregation(BaseModel):
    """Tolérance du contrôle des sommes de la désagrégation (RG-04, UC-DAT-04)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tolerance_somme: float = Field(ge=0)


class Controles(BaseModel):
    """Contenu de ``config/controles.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fourchettes: dict[str, dict[str, Fourchette]]
    variations: list[RegleVariation] = []
    aberrantes: RegleAberrantes
    desagregation: RegleDesagregation

    def fourchette(self, table: str, colonne: str) -> Fourchette:
        """Fourchette de ``table.colonne`` ; ``KeyError`` si elle n'est pas définie."""
        try:
            return self.fourchettes[table][colonne]
        except KeyError:
            raise KeyError(
                f"Aucune fourchette pour {table}.{colonne} dans {FICHIER_CONTROLES}."
            ) from None

    def variation(self, table: str, colonne: str) -> RegleVariation | None:
        """Règle de variation de ``table.colonne``, s'il y en a une."""
        return next((v for v in self.variations if (v.table, v.colonne) == (table, colonne)), None)


# --- Chargement ---------------------------------------------------------------------------


def charger_parametres(chemins: Chemins) -> ParametresTechniques:
    """Lit et valide ``config/parametres.yaml``."""
    return lire_modele(chemins.config / FICHIER_PARAMETRES, ParametresTechniques)


class SaisiesEntreprise(BaseModel):
    """Contenu de ``config/entreprise.local.yaml`` : valeurs saisies, datées et signées."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date_modification: date | None = None
    auteur: str | None = None
    valeurs: dict[str, float | str | list[str] | dict[str, list[str]] | None] = {}


def charger_modele_entreprise(chemins: Chemins) -> ParametresEntreprise:
    """Modèle livré ``config/entreprise.yaml`` ; il ne contient aucune valeur (RG-15)."""
    modele = lire_modele(chemins.config / FICHIER_ENTREPRISE, ParametresEntreprise)
    remplis = [i for i, p in modele.parametres.items() if p.renseigne]
    if remplis or modele.date_modification or modele.auteur:
        raise ErreurConfiguration(
            f"{FICHIER_ENTREPRISE} est le modèle livré vide (RG-15) : il ne doit contenir ni "
            f"valeur ({', '.join(remplis) or 'aucune'}), ni date, ni auteur. Les saisies de "
            f"l'entreprise vont dans {FICHIER_ENTREPRISE_LOCAL}, fichier local ignoré par Git."
        )
    return modele


def charger_saisies_entreprise(chemins: Chemins) -> SaisiesEntreprise:
    """Saisies locales de l'entreprise ; vides si le fichier n'existe pas encore."""
    chemin = chemins.config / FICHIER_ENTREPRISE_LOCAL
    if not chemin.is_file():
        return SaisiesEntreprise()
    return valider(lire_yaml(chemin) or {}, SaisiesEntreprise, FICHIER_ENTREPRISE_LOCAL)


def charger_entreprise(chemins: Chemins, avec_saisies: bool = True) -> ParametresEntreprise:
    """Paramètres de l'entreprise : modèle livré vide, et saisies locales par-dessus.

    Args:
        chemins: dossiers de l'outil.
        avec_saisies: False pour lire le seul modèle livré (état d'une installation neuve).
    """
    modele = charger_modele_entreprise(chemins)
    if not avec_saisies:
        return modele
    saisies = charger_saisies_entreprise(chemins)
    # Une saisie d'un paramètre retiré du modèle (PAR-58, standard carbone, retiré le
    # 23/11/2026) est ignorée : elle reste dans le fichier local, sans effet.
    parametres = {
        i: p.model_copy(update={"valeur": saisies.valeurs.get(i)})
        for i, p in modele.parametres.items()
    }
    return modele.model_copy(
        update={
            "parametres": parametres,
            "date_modification": saisies.date_modification,
            "auteur": saisies.auteur,
        }
    )


def charger_controles(chemins: Chemins) -> Controles:
    """Lit et valide ``config/controles.yaml``."""
    return lire_modele(chemins.config / FICHIER_CONTROLES, Controles)
