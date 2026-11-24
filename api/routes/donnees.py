"""Page « Données » : tables, modèles Excel, import, saisie, prix, versions, sources, rapport.

UC-DAT-06 à 08 et section 7.3 : l'entreprise met l'outil à jour sans écrire de code.
"""

import uuid
from datetime import datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from api.dependances import charger_config_api, obtenir_chemins, obtenir_referentiel
from api.schemas import PrixObserve, Saisie, Signature, ValidationImport
from api.serialisation import lignes
from src.chemins import Chemins
from src.data.config_preparation import charger_config_preparation
from src.data.excel import AnalyseImport, analyser_import, modele_excel, valider_import
from src.data.observations import Niveau
from src.data.prix import TABLE as TABLE_PRIX
from src.data.prix import ajouter_prix, prix_courant
from src.data.provenance import A_COMPLETER, Statut
from src.data.provinces import Referentiel
from src.data.saisie import corriger_valeur
from src.data.sources import charger_sources
from src.data.tables_reference import charger_catalogue
from src.data.versions import Version, Versions
from src.scenarios.config import charger_controles

routeur = APIRouter(prefix="/donnees", tags=["données"])
CheminsDep = Annotated[Chemins, Depends(obtenir_chemins)]
ReferentielDep = Annotated[Referentiel, Depends(obtenir_referentiel)]
TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _version(version: Version | None) -> dict[str, object] | None:
    return version.model_dump(mode="json") if version else None


def _analyses(request: Request) -> dict[str, AnalyseImport]:
    """Imports prévisualisés en attente de validation (en mémoire, par lancement)."""
    if not hasattr(request.app.state, "imports"):
        request.app.state.imports = {}
    return request.app.state.imports


def _mise_a_jour(versions: Versions, table: str) -> str | None:
    for version in reversed(versions.journal()):
        if table in version.tables_modifiees:
            return version.date
    chemin = versions.fichier(table)
    if chemin.is_file():
        return datetime.fromtimestamp(chemin.stat().st_mtime).isoformat(timespec="seconds")
    return None


# --- Tables ------------------------------------------------------------------------------


@routeur.get("/tables")
def tables(chemins: CheminsDep) -> list[dict[str, object]]:
    """Tables modifiables, avec leur date de mise à jour et leur nombre de lignes (UC-DAT-10)."""
    versions = Versions(chemins)
    resultat = []
    for nom, definition in versions.config.tables.items():
        present = versions.fichier(nom).is_file()
        resultat.append(
            {
                "table": nom,
                "libelle": definition.libelle,
                "cle": definition.cle,
                "mise_a_jour": _mise_a_jour(versions, nom),
                "lignes": len(versions.lire(nom)) if present else None,
                "disponible": present,
            }
        )
    return resultat


@routeur.get("/tables/{table}")
def table(
    table: str, chemins: CheminsDep, page: int = 0, filtre: str | None = None
) -> dict[str, object]:
    """Lignes d'une table avec la provenance de chaque valeur (UC-01), page par page."""
    taille = charger_config_api(chemins).lignes_par_page
    donnees = Versions(chemins).lire(table)
    if filtre:
        masque = donnees.astype(str).apply(
            lambda c: c.str.contains(filtre, case=False, regex=False)
        )
        donnees = donnees[masque.any(axis=1)]
    debut = page * taille
    return {
        "table": table,
        "total": len(donnees),
        "page": page,
        "lignes_par_page": taille,
        "colonnes": list(donnees.columns),
        "lignes": lignes(donnees.iloc[debut : debut + taille]),
    }


@routeur.get("/tables/{table}/modele.xlsx")
def modele(table: str, chemins: CheminsDep) -> Response:
    """Modèle Excel pré-rempli de la table (UC-DAT-06)."""
    contenu = modele_excel(Versions(chemins), table, charger_controles(chemins))
    return Response(
        contenu,
        media_type=TYPE_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{table}.xlsx"'},
    )


def _apercu(identifiant: str, analyse: AnalyseImport) -> dict[str, object]:
    return {
        "import": identifiant,
        "table": analyse.table,
        "ajoutees": analyse.ajoutees,
        "modifiees": analyse.modifiees,
        "rejetees": [{"ligne": n, "motif": m} for n, m in sorted(analyse.rejetees.items())],
        "a_confirmer": [{"ligne": n, "motif": m} for n, m in sorted(analyse.a_confirmer.items())],
    }


@routeur.post("/tables/{table}/import")
async def importer(
    table: str,
    fichier: UploadFile,
    request: Request,
    chemins: CheminsDep,
    referentiel: ReferentielDep,
) -> dict[str, object]:
    """Prévisualisation d'un classeur déposé : lignes ajoutées, modifiées, rejetées, à confirmer."""
    analyse = analyser_import(
        await fichier.read(), table, Versions(chemins), charger_controles(chemins), referentiel
    )
    identifiant = uuid.uuid4().hex
    _analyses(request)[identifiant] = analyse
    return _apercu(identifiant, analyse)


@routeur.post("/imports/{identifiant}/valider")
def valider(
    identifiant: str, requete: ValidationImport, request: Request, chemins: CheminsDep
) -> dict[str, object]:
    """Enregistre une nouvelle version avec les lignes acceptées et confirmées (RG-17)."""
    analyse = _analyses(request).pop(identifiant, None)
    if analyse is None:
        raise HTTPException(
            404, "import introuvable ou déjà validé : déposez de nouveau le fichier"
        )
    version = valider_import(
        analyse, Versions(chemins), set(requete.confirmees), requete.auteur, requete.commentaire
    )
    return {"version": _version(version)}


@routeur.put("/tables/{table}/valeur")
def saisir(table: str, requete: Saisie, chemins: CheminsDep) -> dict[str, object]:
    """Correction d'une valeur, avec source et date (UC-DAT-07) ; crée une version."""
    catalogue = charger_catalogue(chemins)
    tables_catalogue = {
        "residus": catalogue.residus,
        "concurrence": catalogue.concurrence,
        "facteurs_emission": catalogue.facteurs_emission,
    }
    textes = None
    if table in tables_catalogue:
        textes = {
            nom: list(d.choix)
            for nom, d in tables_catalogue[table].parametres.items()
            if d.type != "nombre"
        }
    version = corriger_valeur(
        Versions(chemins),
        charger_controles(chemins),
        table=table,
        cle=requete.cle,
        valeur=requete.valeur,
        source=requete.source,
        date_valeur=requete.date,
        auteur=requete.auteur,
        commentaire=requete.commentaire,
        confirmer=requete.confirmer,
        textes=textes,
    )
    return {"version": _version(version)}


# --- Prix et coûts -------------------------------------------------------------------------


@routeur.get("/prix")
def prix(chemins: CheminsDep, produit: str | None = None, code_province: str | None = None) -> dict:
    """Historique des prix observés et prix courant de chaque produit et zone."""
    historique = Versions(chemins).lire(TABLE_PRIX)
    if produit:
        historique = historique[historique["produit"] == produit]
    if code_province:
        historique = historique[historique["code_province"] == code_province]
    courants = []
    for (nom, zone), _ in historique.groupby(["produit", "code_province"], sort=True):
        courant = prix_courant(historique, str(nom), str(zone))
        if courant is not None:
            courants.append(courant.to_dict())
    return {"historique": lignes(historique), "courants": courants}


@routeur.post("/prix", status_code=201)
def ajouter(
    requete: PrixObserve, chemins: CheminsDep, referentiel: ReferentielDep
) -> dict[str, object]:
    """Ajoute un prix observé à l'historique (UC-DAT-07) ; l'ancien prix reste consultable."""
    version = ajouter_prix(
        Versions(chemins),
        charger_controles(chemins),
        referentiel,
        **requete.model_dump(exclude={"date"}),
        date_prix=requete.date,
    )
    return {"version": _version(version)}


# --- Versions (UC-DAT-08) ------------------------------------------------------------------


@routeur.get("/versions")
def versions(chemins: CheminsDep) -> list[dict[str, object]]:
    """Journal des versions, de la plus récente à la plus ancienne."""
    return [v.model_dump(mode="json") for v in reversed(Versions(chemins).journal())]


@routeur.get("/versions/{avant}/comparer/{apres}")
def comparer(avant: str, apres: str, table: str, chemins: CheminsDep) -> dict[str, object]:
    """Lignes ajoutées, modifiées (avant et après) et supprimées d'une table entre deux versions."""
    difference = Versions(chemins).comparer(table, avant, apres)
    return {
        "table": table,
        "ajoutees": lignes(difference.ajoutees),
        "modifiees": lignes(difference.modifiees),
        "avant": lignes(difference.avant),
        "supprimees": lignes(difference.supprimees),
    }


@routeur.post("/versions/{identifiant}/restaurer")
def restaurer(identifiant: str, requete: Signature, chemins: CheminsDep) -> dict[str, object]:
    """Restaure une version en créant une nouvelle version (rien n'est écrasé, RG-17)."""
    version = Versions(chemins).restaurer(identifiant, requete.auteur, requete.commentaire)
    return {"version": _version(version)}


# --- Synthèse pour les titres des écrans ---------------------------------------------------


def _a_completer(versions: Versions, table: str) -> int:
    """Lignes « À compléter » d'une table de référence (RG-14)."""
    donnees = versions.lire(table)
    if "valeur" not in donnees.columns:
        return 0
    return int((donnees["valeur"].astype(str).str.strip() == A_COMPLETER).sum())


@routeur.get("/resume")
def resume(chemins: CheminsDep, referentiel: ReferentielDep) -> dict[str, object]:
    """Faits calculés sur les données réelles, repris par les titres des écrans (section 12.7)."""
    versions = Versions(chemins)
    production = versions.lire("production")
    production = production[production["variable"] == "production_t"]
    reelles = production[production["statut"] != Statut.ESTIMEE.value]
    journal = versions.journal()
    campagnes = sorted(production["campagne"].dropna().unique())
    a_completer = {
        table: _a_completer(versions, table)
        for table in ("residus", "concurrence", "facteurs_emission")
    }
    avec_production = int(production["code_province"].nunique())
    avec_reelle = int(reelles["code_province"].nunique())
    return {
        "provinces_total": len(referentiel.provinces),
        "provinces_avec_production": avec_production,
        "provinces_avec_valeur_reelle": avec_reelle,
        "provinces_estimees_seulement": avec_production - avec_reelle,
        "cultures": sorted(production["code_culture"].dropna().unique()),
        "campagne_min": campagnes[0] if campagnes else None,
        "campagne_max": campagnes[-1] if campagnes else None,
        "valeurs_production": len(production),
        "valeurs_reelles": len(reelles),
        "a_completer": a_completer,
        "a_completer_total": sum(a_completer.values()),
        "derniere_version": _version(journal[-1] if journal else None),
        "sources": len(charger_sources(chemins).sources),
    }


# --- Sources, rapport, statut des provinces ------------------------------------------------


@routeur.get("/sources")
def sources(chemins: CheminsDep) -> list[dict[str, object]]:
    """Manifeste des sources (RG-05) : titre, adresse, licence, fichiers et empreintes."""
    manifeste = charger_sources(chemins)
    return [
        {"source_id": identifiant, **source.model_dump(mode="json", exclude_none=True)}
        for identifiant, source in manifeste.sources.items()
    ]


@routeur.get("/rapport")
def rapport(chemins: CheminsDep) -> FileResponse:
    """Rapport de contrôle de la dernière préparation (UC-DAT-02)."""
    chemin = chemins.preparees / charger_config_preparation(chemins).sorties.rapport
    if not chemin.is_file():
        raise HTTPException(503, "rapport absent : lancez « python -m scripts.prepare »")
    return FileResponse(chemin, media_type="text/html")


@routeur.get("/statut-provinces")
def statut_provinces(
    chemins: CheminsDep, referentiel: ReferentielDep, culture: str | None = None
) -> dict[str, object]:
    """Statut de la production de chaque province : réelle, estimée (RG-04) ou absente.

    Une province est « réelle » si au moins une de ses valeurs est une statistique publiée à sa
    maille, « estimée » si toutes ses valeurs viennent d'un total régional ou national réparti.
    """
    production = Versions(chemins).lire("production")
    production = production[production["variable"] == "production_t"]
    if culture:
        production = production[production["code_culture"] == culture]
    provinces = []
    for _, province in referentiel.provinces.iterrows():
        sienne = production[production["code_province"] == province["code_province"]]
        reelles = sienne[sienne["statut"] != Statut.ESTIMEE.value]
        statut = "absente" if sienne.empty else ("réelle" if not reelles.empty else "estimée")
        provinces.append(
            {
                "code_province": province["code_province"],
                "nom_fr": province["nom_fr"],
                "statut": statut,
                "valeurs": len(sienne),
                "valeurs_reelles": len(reelles),
                "sources": sorted(set(sienne["source_id"].dropna())),
                "niveaux_source": sorted(
                    set(sienne["niveau_source"].dropna()) & {n.value for n in Niveau}
                ),
            }
        )
    resume = pd.Series([p["statut"] for p in provinces]).value_counts().to_dict()
    return {"provinces": provinces, "resume": resume, "total": len(provinces)}
