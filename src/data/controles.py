"""Contrôle et nettoyage des observations, et rapport ``rapport_controle.html`` (UC-DAT-02).

- Doublons : deux observations de même zone, culture, campagne, grandeur et nature. Même
  valeur : la première est gardée, les suivantes sont classées « doublon ». Valeurs différentes :
  aucune n'est retenue (rien n'est choisi à la place de la source), toutes sont classées
  « doublon » avec le motif.
- Aberrantes : valeur à plus de k écarts types de la moyenne de sa série (même source, grandeur,
  culture et maille) ; signalée et conservée.
- Couverture : pour chaque culture, campagne et grandeur, provinces avec une valeur réelle,
  estimée ou absente ; une province absente n'est jamais comptée zéro (RG-06).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from src.data.desagregation import ResultatDesagregation
from src.data.observations import BilanControle, Categorie
from src.data.provenance import Statut
from src.scenarios.config import RegleAberrantes

GABARITS = Path(__file__).resolve().parent / "gabarits"
GABARIT_RAPPORT = "rapport_controle.html.j2"
CLE_DOUBLON = [
    "variable",
    "code_culture",
    "campagne",
    "niveau",
    "code_zone",
    "codes_provinces",
    "previsionnel",
]


def dedoublonner(observations: pd.DataFrame, bilan: BilanControle) -> pd.DataFrame:
    """Observations sans doublon ; les doublons sont classés dans ``bilan``."""
    if observations.empty:
        return observations
    gardees = []
    for _, groupe in observations.groupby(CLE_DOUBLON, sort=False, dropna=False):
        if len(groupe) == 1:
            gardees.append(groupe.index[0])
            continue
        premiere = groupe.iloc[0]
        references = ", ".join(
            f"{d} ligne {n}" for d, n in zip(groupe["document"], groupe["ligne"], strict=True)
        )
        if groupe["valeur"].nunique() == 1:
            gardees.append(groupe.index[0])
            for _, ligne in groupe.iloc[1:].iterrows():
                bilan.signaler(
                    str(ligne["source_id"]),
                    str(ligne["document"]),
                    int(ligne["ligne"]),
                    Categorie.DOUBLON,
                    f"même valeur que {premiere['document']} ligne {premiere['ligne']}",
                )
            continue
        for _, ligne in groupe.iterrows():
            bilan.signaler(
                str(ligne["source_id"]),
                str(ligne["document"]),
                int(ligne["ligne"]),
                Categorie.DOUBLON,
                f"valeurs différentes pour la même zone et la même campagne ({references}) : "
                "aucune n'est retenue",
            )
    return observations.loc[sorted(gardees)].reset_index(drop=True)


def signaler_aberrantes(
    observations: pd.DataFrame, bilan: BilanControle, regle: RegleAberrantes
) -> pd.DataFrame:
    """Observations hors de moyenne ± k écarts types de leur série, signalées dans ``bilan``."""
    cle = ["source_id", "variable", "code_culture", "niveau"]
    trouvees = []
    for _, groupe in observations.groupby(cle, sort=True):
        if len(groupe) < regle.effectif_minimal:
            continue
        moyenne, ecart = groupe["valeur"].mean(), groupe["valeur"].std()
        if not ecart:
            continue
        hors = groupe[(groupe["valeur"] - moyenne).abs() > regle.ecarts_types * ecart]
        for _, ligne in hors.iterrows():
            bilan.signaler(
                str(ligne["source_id"]),
                str(ligne["document"]),
                int(ligne["ligne"]),
                Categorie.ABERRANTE,
                f"{regle.motif} : {ligne['valeur']:.0f} pour une moyenne de {moyenne:.0f}",
            )
        trouvees.append(hors)
    return pd.concat(trouvees) if trouvees else observations.iloc[0:0]


def couverture(production: pd.DataFrame, provinces: pd.DataFrame) -> pd.DataFrame:
    """Provinces couvertes par culture, campagne et grandeur : réelles, estimées, absentes."""
    toutes = set(provinces["code_province"])
    lignes = []
    for (variable, culture, campagne), groupe in production.groupby(
        ["variable", "code_culture", "campagne"], sort=True
    ):
        estimees = groupe["statut"] == Statut.ESTIMEE.value
        absentes = sorted(toutes - set(groupe["code_province"]))
        lignes.append(
            {
                "variable": variable,
                "code_culture": culture,
                "campagne": campagne,
                "reelles": int((~estimees).sum()),
                "estimees": int(estimees.sum()),
                "absentes": len(absentes),
                "provinces_absentes": ", ".join(absentes),
            }
        )
    return pd.DataFrame(
        lignes,
        columns=[
            "variable",
            "code_culture",
            "campagne",
            "reelles",
            "estimees",
            "absentes",
            "provinces_absentes",
        ],
    )


def provinces_sans_production(production: pd.DataFrame, provinces: pd.DataFrame) -> list[str]:
    """Provinces sans aucune production réelle ou estimée (condition de fin du lot 1)."""
    avec = set(production.loc[production["variable"] == "production_t", "code_province"])
    return sorted(set(provinces["code_province"]) - avec)


def format_fr(nombre: float, decimales: int = 0) -> str:
    """Nombre au format français : 1027573.5 → « 1 027 574 » ; 0.2 avec 1 décimale → « 0,2 »."""
    texte = f"{nombre:,.{decimales}f}"
    return texte.replace(",", "\u202f").replace(".", ",")


def _plages(numeros: list[int]) -> str:
    """[1, 2, 3, 7] → « 1-3, 7 »."""
    plages: list[str] = []
    debut = precedent = None
    for n in sorted(set(numeros)):
        if precedent is not None and n == precedent + 1:
            precedent = n
            continue
        if debut is not None:
            plages.append(str(debut) if debut == precedent else f"{debut}-{precedent}")
        debut = precedent = n
    if debut is not None:
        plages.append(str(debut) if debut == precedent else f"{debut}-{precedent}")
    return ", ".join(plages)


@dataclass(frozen=True)
class SectionSource:
    """Une source du rapport : nombres par catégorie et lignes regroupées par motif."""

    source_id: str
    fichier: str
    lues: int
    nombres: dict[str, int]
    details: list[dict[str, object]]


def sections_sources(bilan: BilanControle) -> list[SectionSource]:
    """Bilan regroupé par fichier lu, puis par catégorie et motif."""
    table = bilan.tableau()
    sections = []
    for (source_id, fichier), lues in sorted(bilan.lues.items()):
        sous = table[table["fichier"] == fichier]
        nombres = {c.value: int((sous["categorie"] == c).sum()) for c in Categorie}
        details = []
        for (categorie, source, motif), groupe in sous.groupby(
            ["categorie", "source_id", "motif"], sort=True
        ):
            details.append(
                {
                    "categorie": str(categorie),
                    "source_id": source,
                    "motif": motif,
                    "nombre": len(groupe),
                    "lignes": _plages([int(n) for n in groupe["ligne"]]),
                }
            )
        sections.append(SectionSource(source_id, fichier, lues, nombres, details))
    return sections


def rendre_rapport(
    bilan: BilanControle,
    resultat: ResultatDesagregation,
    provinces: pd.DataFrame,
    titre_sources: dict[str, str],
) -> str:
    """Rapport de contrôle HTML autonome (UC-DAT-02, UC-DAT-04)."""
    environnement = Environment(
        loader=FileSystemLoader(GABARITS),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
    )
    environnement.filters["fr"] = format_fr
    controles = resultat.controles
    sans = provinces_sans_production(resultat.production, provinces)
    noms = provinces.set_index("code_province")["nom_fr"].to_dict()
    return environnement.get_template(GABARIT_RAPPORT).render(
        date=datetime.now().strftime("%d/%m/%Y %H:%M"),
        sections=sections_sources(bilan),
        categories=[c.value for c in Categorie],
        titres=titre_sources,
        controles=controles.to_dict(orient="records"),
        nb_conformes=int(controles["conforme"].sum()) if not controles.empty else 0,
        incoherences=resultat.incoherences,
        previsions=resultat.previsions_ecartees,
        ecarts_campagne=resultat.ecarts_campagne,
        couverture=couverture(resultat.production, provinces).to_dict(orient="records"),
        nb_provinces=len(provinces),
        sans_production=[f"{c} {noms.get(c, '')}" for c in sans],
    )
