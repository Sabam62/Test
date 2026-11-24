"""SRC-18 : statistiques des communiqués des DRA et DPA, saisies puis vérifiées par l'équipe.

Trois fichiers de ``data/manuelles/SRC-18/`` (saisis par l'équipe, versionnés dans Git), lus
sans être modifiés (RG-01) :

- ``valeurs_saisies.csv`` : une ligne par valeur citée dans une page archivée ;
- ``valeurs_verifiees.csv`` : les mêmes lignes, avec l'extrait de la page et le résultat du
  contrôle ; seule une ligne dont le contrôle commence par « vérifiée » est utilisée ;
- ``references.csv`` : adresse, organisme, date et source parente de chaque page archivée
  (SRC-18, ou SRC-03 pour une monographie du HCP).

Chaque ligne utilisée devient une observation au format de :mod:`src.data.observations`,
statut « Mesurée » (statistique officielle réalisée, utilisée telle quelle) ; une valeur
prévisionnelle porte le statut « Estimée » et le signal ``previsionnel`` (RG-04). Une région
ou une province non reconnue bloque l'import (RG-02).
"""

from pathlib import Path

import pandas as pd

from src.data.config_preparation import ConfigSrc18
from src.data.observations import (
    NATIONAL,
    SEPARATEUR_CODES,
    BilanControle,
    Categorie,
    ErreurPreparation,
    Niveau,
    annee_campagne,
    campagne_valide,
)
from src.data.provenance import Statut
from src.data.provinces import ErreurRattachement, Referentiel
from src.data.provinces import Niveau as NiveauReferentiel

COLONNES_SAISIES = [
    "fichier",
    "niveau",
    "region",
    "province",
    "inclut",
    "culture",
    "campagne",
    "periode",
    "variable",
    "valeur",
    "unite",
    "nature",
    "methode",
    "indice",
    "remarque",
]
COLONNES_VERIFIEES = [*COLONNES_SAISIES, "extrait", "verification"]
COLONNES_REFERENCES = [
    "fichier",
    "url",
    "organisme",
    "date_publication",
    "date_consultation",
    "source_parente",
]
NATURES = {"realisee": False, "previsionnelle": True}


def _lire(chemin: Path, colonnes: list[str]) -> pd.DataFrame:
    if not chemin.is_file():
        raise ErreurPreparation(
            f"{chemin} est absent : déposez-le dans data/manuelles/SRC-18/ "
            "(voir docs/donnees_manuelles.md, section SRC-18)"
        )
    table = pd.read_csv(chemin, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
    table.columns = [c.strip() for c in table.columns]
    absentes = [c for c in colonnes if c not in table.columns]
    if absentes:
        raise ErreurPreparation(f"{chemin.name} : colonnes absentes {', '.join(absentes)}")
    return table[colonnes].apply(lambda colonne: colonne.str.strip())


def _nombre(texte: str) -> float | None:
    try:
        return float(texte.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _rattacher(
    referentiel: Referentiel, nom: str, niveau: NiveauReferentiel, numero: int
) -> tuple[str | None, tuple[int, str] | None]:
    """Code d'un nom, ou la ligne fautive (numéro, nom) pour le message RG-02."""
    try:
        return referentiel.rattacher(pd.Series([nom]), niveau)[0], None
    except ErreurRattachement:
        return None, (numero, nom)


class _Lecture:
    """Contrôle ligne à ligne des valeurs saisies."""

    def __init__(
        self,
        config: ConfigSrc18,
        referentiel: Referentiel,
        cultures: set[str],
        bilan: BilanControle,
        references: pd.DataFrame,
    ) -> None:
        self.config = config
        self.referentiel = referentiel
        self.cultures = cultures
        self.bilan = bilan
        self.references = references.set_index("fichier")
        self.fautives: dict[NiveauReferentiel, list[tuple[int, str]]] = {
            "region": [],
            "province": [],
        }
        self.region_de = referentiel.provinces.set_index("code_province")["code_region"]

    def signaler(self, numero: int, categorie: Categorie, motif: str) -> None:
        self.bilan.signaler(self._source(numero), self.config.saisies, numero, categorie, motif)

    def _source(self, numero: int) -> str:
        fichier = self._lignes.at[numero, "fichier"]
        if fichier in self.references.index:
            return str(self.references.at[fichier, "source_parente"]) or "SRC-18"
        return "SRC-18"

    def lire(self, saisies: pd.DataFrame, verifications: dict[tuple[str, ...], list[str]]) -> list:
        self._lignes = saisies.set_axis(range(1, len(saisies) + 1))
        observations = []
        for numero, ligne in self._lignes.iterrows():
            observation = self._ligne(int(numero), ligne, verifications)
            if observation is not None:
                observations.append(observation)
        for niveau, fautives in self.fautives.items():
            if fautives:
                raise ErreurRattachement(niveau, [n for n, _ in fautives], [v for _, v in fautives])
        return observations

    def _ligne(
        self, numero: int, ligne: pd.Series, verifications: dict[tuple[str, ...], list[str]]
    ) -> dict[str, object] | None:
        config = self.config
        controles = verifications.get(tuple(ligne[COLONNES_SAISIES]), [])
        if ligne["fichier"] not in self.references.index:
            return self._rejet(numero, f"page « {ligne['fichier']} » absente de references.csv")
        if not controles:
            return self._rejet(numero, f"ligne absente de {config.verifiees} (non contrôlée)")
        valides = [c for c in controles if c.startswith(config.verification_valide)]
        if not valides:
            return self._rejet(numero, f"contrôle : {controles[0]}")
        variable = ligne["variable"]
        if variable not in config.unites:
            return self._rejet(numero, f"variable « {variable} » inconnue")
        if ligne["unite"] != config.unites[variable]:
            return self._rejet(
                numero,
                f"unité « {ligne['unite']} » ; attendue « {config.unites[variable]} » "
                f"pour {variable}",
            )
        valeur = _nombre(ligne["valeur"])
        if valeur is None or valeur < 0:
            return self._rejet(numero, f"valeur « {ligne['valeur']} » illisible ou négative")
        if ligne["culture"] not in self.cultures:
            return self._rejet(numero, f"culture « {ligne['culture']} » absente de cultures.csv")
        if ligne["nature"] not in NATURES:
            return self._rejet(numero, f"nature « {ligne['nature']} » (realisee ou previsionnelle)")
        if ligne["niveau"] not in set(Niveau):
            return self._rejet(numero, f"niveau « {ligne['niveau']} » inconnu")
        zone = self._zone(numero, ligne)
        if zone is None:
            return None
        periode = ligne["periode"]
        if periode in config.periodes_sans_campagne:
            return self._non_utilisee(numero, config.periodes_sans_campagne[periode])
        if periode not in config.periodes_avec_campagne:
            return self._rejet(numero, f"période « {periode} » inconnue")
        if not campagne_valide(ligne["campagne"]):
            return self._rejet(numero, f"campagne « {ligne['campagne']} » illisible")
        if variable in config.non_utilisees:
            return self._non_utilisee(numero, config.non_utilisees[variable])
        if variable not in config.variables:
            return self._non_utilisee(numero, f"variable {variable} non utilisée par la RG-04")
        reference = self.references.loc[ligne["fichier"]]
        self.signaler(numero, Categorie.VALIDE, valides[0])
        niveau, code_zone, codes_provinces = zone
        note = ligne["remarque"]
        if periode != config.periodes_avec_campagne[0]:
            note = f"période {periode} ; {note}" if note else f"période {periode}"
        return {
            "source_id": str(reference["source_parente"]),
            "document": ligne["fichier"],
            "url": str(reference["url"]),
            "organisme": str(reference["organisme"]),
            "ligne": numero,
            "niveau": niveau,
            "code_zone": code_zone,
            "codes_provinces": codes_provinces,
            "code_culture": ligne["culture"],
            "campagne": ligne["campagne"],
            "periode": periode,
            "variable": config.variables[variable],
            "valeur": valeur,
            "unite": ligne["unite"],
            "previsionnel": NATURES[ligne["nature"]],
            # Une prévision n'est pas une statistique réalisée : « Estimée », avec le signal
            # « previsionnel » (décision du 22/11/2026).
            "statut": (Statut.ESTIMEE.value if NATURES[ligne["nature"]] else Statut.MESUREE.value),
            "annee": annee_campagne(ligne["campagne"]),
            "version": None,
            "methode": ligne["methode"],
            "note": note or None,
        }

    def _zone(self, numero: int, ligne: pd.Series) -> tuple[str, str, str] | None:
        """(niveau, code de la zone, codes des provinces couvertes) ; None si rejetée."""
        niveau = ligne["niveau"]
        if niveau == Niveau.NATIONAL:
            return niveau, NATIONAL, ""
        code_region, fautive = _rattacher(self.referentiel, ligne["region"], "region", numero)
        if fautive:
            self.fautives["region"].append(fautive)
            return None
        if niveau == Niveau.REGION:
            return niveau, str(code_region), ""
        noms = [n.strip() for n in ligne["inclut"].split(SEPARATEUR_CODES) if n.strip()]
        noms = noms or [ligne["province"]]
        codes = []
        for nom in noms:
            code, fautive = _rattacher(self.referentiel, nom, "province", numero)
            if fautive:
                self.fautives["province"].append(fautive)
                return None
            codes.append(str(code))
        hors_region = [c for c in codes if self.region_de[c] != code_region]
        if hors_region:
            self._rejet(numero, f"province(s) {', '.join(hors_region)} hors de la région indiquée")
            return None
        code_zone, _ = _rattacher(self.referentiel, ligne["province"], "province", numero)
        if code_zone is None:
            self.fautives["province"].append((numero, ligne["province"]))
            return None
        return niveau, str(code_zone), SEPARATEUR_CODES.join(sorted(codes))

    def _rejet(self, numero: int, motif: str) -> None:
        self.signaler(numero, Categorie.REJETEE, motif)
        return None

    def _non_utilisee(self, numero: int, motif: str) -> None:
        self.signaler(numero, Categorie.NON_UTILISEE, motif)
        return None


def lire_src18(
    dossier: Path,
    config: ConfigSrc18,
    referentiel: Referentiel,
    cultures: set[str],
    bilan: BilanControle,
) -> list[dict[str, object]]:
    """Observations utilisables de SRC-18 ; chaque ligne lue est classée dans ``bilan``.

    Args:
        dossier: ``data/manuelles/SRC-18/`` (ou son extrait figé dans ``tests/fixtures/``).
        config: section ``src18`` de ``config/preparation.yaml``.
        referentiel: régions, provinces et variantes de noms (RG-02).
        cultures: codes de ``cultures.csv``.
        bilan: bilan des contrôles, complété.

    Raises:
        ErreurPreparation: fichier ou colonne absent.
        ErreurRattachement: région ou province non reconnue (RG-02).
    """
    saisies = _lire(dossier / config.saisies, COLONNES_SAISIES)
    verifiees = _lire(dossier / config.verifiees, COLONNES_VERIFIEES)
    references = _lire(dossier / config.references, COLONNES_REFERENCES)
    verifications: dict[tuple[str, ...], list[str]] = {}
    for _, ligne in verifiees.iterrows():
        verifications.setdefault(tuple(ligne[COLONNES_SAISIES]), []).append(ligne["verification"])
    bilan.lire("SRC-18", config.saisies, len(saisies))
    lecture = _Lecture(config, referentiel, cultures, bilan, references)
    return lecture.lire(saisies, verifications)
