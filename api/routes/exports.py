"""Exports CSV et Excel (UC-RES-02) : tout tableau affiché, et le classement des sites.

Chaque export Excel a une feuille « paramètres » et une feuille « sources » ; un classement
partiel porte le bandeau « Classement partiel : n critères sur N » (décision du 23/11/2026).
"""

import re
import unicodedata
from dataclasses import replace
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.dependances import obtenir_chemins
from api.routes.decision import DonneesDep, classement, classement_gisements
from api.routes.logistique import LogistiqueDep
from api.routes.potentiel import CalculDep
from src.chemins import Chemins
from src.restitution.annexes import table_parametres, table_sources
from src.restitution.exports import (
    Colonne,
    Export,
    Partiel,
    charger_config_restitution,
    classeur_excel,
    fichier_csv,
)
from src.scenarios.demo import bandeau_demo

routeur = APIRouter(prefix="/exports", tags=["exports"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
Format = Literal["csv", "xlsx"]
TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ColonneExport(BaseModel):
    """Colonne d'un tableau affiché."""

    cle: str = Field(min_length=1)
    libelle: str = Field(min_length=1)
    unite: str | None = None


class PartielExport(BaseModel):
    """Bandeau d'un classement partiel, tel qu'affiché."""

    utilises: int
    actifs: int
    retires: dict[str, str] = {}
    libelles: dict[str, str] = {}


class DemandeExport(BaseModel):
    """Tableau affiché à exporter (les valeurs viennent de l'API, sans calcul de l'interface)."""

    titre: str = Field(min_length=1)
    colonnes: list[ColonneExport] = Field(min_length=1)
    lignes: list[dict[str, object]]
    partiel: PartielExport | None = None
    notes: list[str] = []


def _nom_fichier(titre: str, extension: str) -> str:
    texte = unicodedata.normalize("NFKD", titre)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", texte).strip("-") + f".{extension}"


def _reponse(chemins: Chemins, export: Export, format: Format) -> Response:
    config = charger_config_restitution(chemins)
    export = replace(export, demo=bandeau_demo(chemins))
    contenu = (
        classeur_excel(export, config.excel)
        if format == "xlsx"
        else fichier_csv(export, config.csv)
    )
    return Response(
        contenu,
        media_type=TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{_nom_fichier(export.titre, format)}"'
        },
    )


@routeur.post("/{format}")
def exporter(format: Format, corps: DemandeExport, chemins: CheminsDep) -> Response:
    """Exporte un tableau affiché, avec ses annexes « paramètres » et « sources »."""
    export = Export(
        titre=corps.titre,
        colonnes=[Colonne(c.cle, c.libelle, c.unite) for c in corps.colonnes],
        lignes=corps.lignes,
        parametres=table_parametres(chemins),
        sources=table_sources(chemins),
        partiel=Partiel(**corps.partiel.model_dump()) if corps.partiel else None,
        notes=corps.notes,
    )
    return _reponse(chemins, export, format)


@routeur.get("/classement.{format}")
def exporter_classement(
    format: Format, chemins: CheminsDep, donnees: DonneesDep, methode: str | None = None
) -> Response:
    """Classement des sites : rang, score, variation, valeur de chaque critère, exclus."""
    c = classement(chemins, donnees, methode)
    if c.get("bloque"):
        raise HTTPException(
            409,
            "classement indisponible : renseignez " + ", ".join(c["a_renseigner"]),  # type: ignore[arg-type]
        )
    catalogue = donnees.catalogue
    criteres: list[str] = c["criteres"]  # type: ignore[assignment]
    colonnes = [
        Colonne("rang", "Rang"),
        Colonne("nom", "Site"),
        Colonne("type", "Type"),
        Colonne("score", "Score", "0 à 1"),
        Colonne("variation", "Variation de rang", "places"),
        *[
            Colonne(
                f"valeur_{k}", f"{k} · {catalogue.criteres[k].libelle}", catalogue.criteres[k].unite
            )
            for k in criteres
        ],
    ]
    valeurs: dict[str, dict[str, float]] = c["valeurs"]  # type: ignore[assignment]
    lignes = [
        {**ligne, **{f"valeur_{k}": valeurs[ligne["id_site"]][k] for k in criteres}}
        for ligne in c["classement"]  # type: ignore[union-attr]
    ]
    exclus = c["exclus"]
    lignes += [
        {"rang": "exclu", "nom": e["nom"], "type": e["motif"]}
        for e in exclus  # type: ignore[union-attr]
    ]
    partiel = c["partiel"]
    poids = c["poids"]
    export = Export(
        titre="Classement des sites",
        colonnes=colonnes,
        lignes=lignes,
        parametres=table_parametres(chemins),
        sources=table_sources(chemins),
        partiel=Partiel(
            partiel["utilises"],  # type: ignore[index]
            partiel["actifs"],  # type: ignore[index]
            c["retires"],  # type: ignore[arg-type]
            c["libelles_retires"],  # type: ignore[arg-type]
        ),
        notes=[
            f"Méthode : {donnees.config.methodes.get(str(c['methode']), c['methode'])} ; poids : "
            + ", ".join(f"{k} {v * 100:.1f} %" for k, v in poids.items())  # type: ignore[union-attr]
        ],
    )
    return _reponse(chemins, export, format)


@routeur.get("/gisements.{format}")
def exporter_gisements(
    format: Format,
    chemins: CheminsDep,
    donnees: DonneesDep,
    calcul: CalculDep,
    logistique: LogistiqueDep,
    site: str = "AGP-MEKNES",
    methode: str | None = None,
) -> Response:
    """Classement des gisements pour un site, avec son bandeau de classement partiel."""
    g = classement_gisements(chemins, donnees, calcul, logistique, site, methode)
    if g.get("bloque") or not g.get("classable"):
        raise HTTPException(409, str(g.get("message") or "classement des gisements indisponible"))
    criteres: list[str] = g["criteres"]  # type: ignore[assignment]
    colonnes = [
        Colonne("rang", "Rang"),
        Colonne("nom_residu", "Résidu"),
        Colonne("nom_province", "Province"),
        Colonne("score", "Score", "0 à 1"),
        *[
            Colonne(f"valeur_{k}", f"{k} · {g['libelles_criteres'][k]}", g["unites"][k])
            for k in criteres
        ],  # type: ignore[index]
    ]
    limite = charger_config_restitution(chemins).lignes_gisements
    lignes = [
        {**l, **{f"valeur_{k}": l["valeurs"][k] for k in criteres}}
        for l in g["classement"][:limite]  # type: ignore[index]  # noqa: E741
    ]
    partiel = g["partiel"]
    export = Export(
        titre=f"Classement des gisements · {site}",
        colonnes=colonnes,
        lignes=lignes,
        parametres=table_parametres(chemins),
        sources=table_sources(chemins),
        partiel=Partiel(
            partiel["utilises"], partiel["actifs"], g["retires"], g["libelles_retires"]
        ),  # type: ignore[index, arg-type]
        notes=[f"{g['exclus']['total']} couples exclus faute de valeur : voir l'écran Décision"],  # type: ignore[index]
    )
    return _reponse(chemins, export, format)
