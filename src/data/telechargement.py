"""Téléchargement des sources ouvertes à adresse stable dans ``data/raw/<source>/``.

Règles appliquées :

- RG-01 : un fichier déjà présent n'est jamais réécrit ni modifié ; le téléchargement se fait
  dans un fichier provisoire, renommé seulement une fois complet et vérifié (taille, MD5) ;
- RG-05 : chaque fichier est inscrit au manifeste avec son adresse, sa date, sa taille et son
  empreinte SHA-256 ; la licence annoncée par l'API met à jour celle de la source ;
- un échec (réseau, refus du serveur, fichier tronqué) ne bloque pas les autres sources : il
  produit un message français qui renvoie à la procédure manuelle de ``docs/donnees_manuelles.md``.

Le client HTTP est fourni par l'appelant (``scripts.download``), ce qui permet de le simuler
dans les tests.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

from src.chemins import Chemins
from src.data.sources import (
    Fichier,
    ManifesteSources,
    Ressource,
    Source,
    charger_sources,
    empreinte_md5,
    empreinte_sha256,
    enregistrer_sources,
)

DOC_MANUELLE = "docs/donnees_manuelles.md"
SUFFIXE_PROVISOIRE = ".part"


class ErreurTelechargement(Exception):
    """Téléchargement impossible ; le message dit pourquoi, en français."""


@dataclass(frozen=True)
class Cible:
    """Fichier à télécharger, une fois son adresse résolue."""

    nom: str
    nom_local: str
    url: str
    taille: int | None = None
    md5: str | None = None


@dataclass(frozen=True)
class Resolution:
    """Adresses résolues d'une source et licence annoncée par l'API."""

    cibles: list[Cible]
    licence: str | None = None


@dataclass
class ResultatSource:
    """Bilan du téléchargement d'une source."""

    source: Source
    ecrits: list[str] = field(default_factory=list)
    deja_presents: list[str] = field(default_factory=list)
    supprimes: list[str] = field(default_factory=list)
    erreur: str | None = None


# --- Résolution des adresses --------------------------------------------------------------


def _json(client: httpx.Client, url: str, parametres: dict[str, str] | None = None) -> dict:
    reponse = client.get(url, params=parametres)
    reponse.raise_for_status()
    try:
        donnees = reponse.json()
    except ValueError:
        raise ErreurTelechargement(f"l'API {url} n'a pas renvoyé de JSON") from None
    if not isinstance(donnees, dict):
        raise ErreurTelechargement(f"réponse inattendue de l'API {url}")
    return donnees


def _introuvable(ressource: Ressource, disponibles: Iterable[str]) -> ErreurTelechargement:
    return ErreurTelechargement(
        f"le fichier « {ressource.nom} » n'est plus proposé par l'API "
        f"(fichiers disponibles : {', '.join(sorted(disponibles))})"
    )


def _resoudre_ckan(source: Source, client: httpx.Client) -> Resolution:
    procedure = source.telechargement
    assert procedure is not None and procedure.api and procedure.jeu
    donnees = _json(client, procedure.api, {"id": procedure.jeu})
    if not donnees.get("success") or not isinstance(donnees.get("result"), dict):
        raise ErreurTelechargement(f"le jeu de données « {procedure.jeu} » est introuvable")
    jeu = donnees["result"]
    par_nom = {r.get("name"): r for r in jeu.get("resources", [])}
    cibles = []
    for ressource in procedure.ressources:
        trouvee = par_nom.get(ressource.nom)
        if trouvee is None or not trouvee.get("url"):
            raise _introuvable(ressource, (str(n) for n in par_nom))
        taille = trouvee.get("size")
        cibles.append(
            Cible(
                nom=ressource.nom,
                nom_local=ressource.nom_local,
                url=trouvee["url"],
                taille=taille if isinstance(taille, int) else None,
            )
        )
    return Resolution(cibles, jeu.get("license_title"))


def _resoudre_figshare(source: Source, client: httpx.Client) -> Resolution:
    procedure = source.telechargement
    assert procedure is not None and procedure.api
    article = _json(client, procedure.api)
    par_nom = {f.get("name"): f for f in article.get("files", [])}
    cibles = []
    for ressource in procedure.ressources:
        trouve = par_nom.get(ressource.nom)
        if trouve is None or not trouve.get("download_url"):
            raise _introuvable(ressource, (str(n) for n in par_nom))
        cibles.append(
            Cible(
                nom=ressource.nom,
                nom_local=ressource.nom_local,
                url=trouve["download_url"],
                taille=trouve.get("size"),
                md5=trouve.get("computed_md5") or trouve.get("supplied_md5") or None,
            )
        )
    licence = article.get("license", {})
    return Resolution(cibles, licence.get("name") if isinstance(licence, dict) else None)


def resoudre(source: Source, client: httpx.Client) -> Resolution:
    """Résout les adresses des fichiers d'une source (appel aux API CKAN ou figshare)."""
    procedure = source.telechargement
    if procedure is None:
        raise ErreurTelechargement(f"{source.identifiant} n'a pas de téléchargement automatique")
    if procedure.methode == "ckan":
        return _resoudre_ckan(source, client)
    if procedure.methode == "figshare":
        return _resoudre_figshare(source, client)
    return Resolution(
        [Cible(r.nom, r.nom_local, r.url or "") for r in procedure.ressources], source.licence
    )


# --- Téléchargement -----------------------------------------------------------------------


def _verifier(provisoire: Path, cible: Cible) -> None:
    taille = provisoire.stat().st_size
    if cible.taille is not None and taille != cible.taille:
        raise ErreurTelechargement(
            f"« {cible.nom} » est incomplet : taille reçue {taille} octets, "
            f"taille annoncée {cible.taille} octets"
        )
    if cible.md5 is not None and empreinte_md5(provisoire) != cible.md5:
        raise ErreurTelechargement(f"« {cible.nom} » est corrompu : empreinte MD5 différente")


def telecharger_fichier(client: httpx.Client, cible: Cible, dossier: Path, jour: date) -> Fichier:
    """Télécharge ``cible`` dans ``dossier`` sans jamais écraser un fichier existant (RG-01)."""
    destination = dossier / cible.nom_local
    if destination.exists():
        raise ErreurTelechargement(f"{destination} existe déjà : il n'est jamais réécrit (RG-01)")
    dossier.mkdir(parents=True, exist_ok=True)
    provisoire = destination.with_name(destination.name + SUFFIXE_PROVISOIRE)
    try:
        with client.stream("GET", cible.url) as reponse:
            reponse.raise_for_status()
            with provisoire.open("wb") as flux:
                for morceau in reponse.iter_bytes():
                    flux.write(morceau)
        _verifier(provisoire, cible)
        provisoire.rename(destination)
    finally:
        provisoire.unlink(missing_ok=True)
    return Fichier(
        url=cible.url,  # adresse stable ; jamais celle de la redirection, souvent signée
        date_telechargement=jour,
        taille_octets=destination.stat().st_size,
        sha256=empreinte_sha256(destination),
    )


def _cause(erreur: Exception) -> str:
    if isinstance(erreur, httpx.HTTPStatusError):
        return f"le serveur a répondu {erreur.response.status_code} pour {erreur.request.url}"
    if isinstance(erreur, httpx.TimeoutException):
        return "le serveur n'a pas répondu à temps"
    if isinstance(erreur, httpx.TransportError):
        return "pas de connexion à Internet ou serveur injoignable"
    return str(erreur)


def _inscrire_present(source: Source, chemin: Path) -> Source:
    """Inscrit au manifeste un fichier déjà présent, sans le modifier."""
    connu = source.fichiers.get(chemin.name)
    if connu is not None and connu.taille_octets == chemin.stat().st_size:
        return source
    fichier = Fichier(taille_octets=chemin.stat().st_size, sha256=empreinte_sha256(chemin))
    return source.model_copy(update={"fichiers": {**source.fichiers, chemin.name: fichier}})


def telecharger_source(
    source: Source,
    chemins: Chemins,
    client: httpx.Client,
    jour: date,
    retelecharger_supprimes: bool = False,
) -> ResultatSource:
    """Télécharge les fichiers manquants d'une source et renvoie la source mise à jour.

    Un fichier supprimé volontairement (``supprime_le`` dans le manifeste) n'est retéléchargé
    que si ``retelecharger_supprimes`` est vrai, ou si le fichier dérivé qui le remplace
    (``remplace_par``) est absent du poste : le manifeste est versionné, la suppression faite
    sur un poste ne doit pas priver une installation neuve du fichier.
    """
    procedure = source.telechargement
    if procedure is None:
        raise ErreurTelechargement(f"{source.identifiant} n'a pas de téléchargement automatique")
    dossier = chemins.brutes / source.identifiant
    resultat = ResultatSource(source)
    manquants = []
    for ressource in procedure.ressources:
        chemin = dossier / ressource.nom_local
        if chemin.exists():
            resultat.deja_presents.append(ressource.nom_local)
            resultat.source = _inscrire_present(resultat.source, chemin)
            continue
        connu = source.fichiers.get(ressource.nom_local)
        if (
            connu is not None
            and connu.supprime_le is not None
            and not retelecharger_supprimes
            and (connu.remplace_par is None or (chemins.racine / connu.remplace_par).exists())
        ):
            resultat.supprimes.append(ressource.nom_local)
        else:
            manquants.append(ressource.nom_local)
    if not manquants:
        return resultat
    try:
        resolution = resoudre(source, client)
        for cible in resolution.cibles:
            if cible.nom_local not in manquants:
                continue
            fichier = telecharger_fichier(client, cible, dossier, jour)
            fichiers = {**resultat.source.fichiers, cible.nom_local: fichier}
            resultat.source = resultat.source.model_copy(update={"fichiers": fichiers})
            resultat.ecrits.append(cible.nom_local)
        if resolution.licence:
            resultat.source = resultat.source.model_copy(update={"licence": resolution.licence})
    except (httpx.HTTPError, ErreurTelechargement, OSError) as erreur:
        resultat.erreur = (
            f"{source.identifiant} ({source.titre}) : téléchargement impossible, "
            f"{_cause(erreur)}. Déposez le fichier à la main : voir {DOC_MANUELLE}, "
            f"section {source.identifiant}."
        )
    return resultat


def inscrire_deposes(chemins: Chemins, manifeste: ManifesteSources) -> ManifesteSources:
    """Inscrit au manifeste les fichiers déposés dans ``data/raw/<source>/`` (RG-05).

    Les saisies de l'équipe versionnées dans ``data/manuelles/<source>/`` sont inscrites de la
    même façon. Les fichiers ne sont ni déplacés ni modifiés ; les fichiers provisoires sont
    ignorés.
    """
    for identifiant, source in manifeste.sources.items():
        mise_a_jour = source
        for dossier in (chemins.brutes / identifiant, chemins.manuelles / identifiant):
            if not dossier.is_dir():
                continue
            for chemin in sorted(dossier.iterdir()):
                if chemin.is_file() and not chemin.name.endswith(SUFFIXE_PROVISOIRE):
                    mise_a_jour = _inscrire_present(mise_a_jour, chemin)
        if mise_a_jour != source:
            manifeste = manifeste.avec(mise_a_jour)
    return manifeste


def telecharger_tout(
    chemins: Chemins,
    client: httpx.Client,
    jour: date,
    identifiants: Iterable[str] | None = None,
    retelecharger_supprimes: bool = False,
) -> list[ResultatSource]:
    """Télécharge les sources demandées (toutes les sources automatiques par défaut).

    Le manifeste ``data/sources.yaml`` est réécrit après chaque source, pour ne rien perdre si
    le téléchargement est interrompu.
    """
    manifeste: ManifesteSources = charger_sources(chemins)
    automatiques = [i for i, s in manifeste.sources.items() if s.telechargement is not None]
    demandes = list(identifiants) if identifiants is not None else automatiques
    inconnues = [i for i in demandes if i not in automatiques]
    if inconnues:
        raise ErreurTelechargement(
            f"sources sans téléchargement automatique : {', '.join(inconnues)} "
            f"(sources possibles : {', '.join(automatiques)})"
        )
    resultats = []
    for identifiant in demandes:
        resultat = telecharger_source(
            manifeste.sources[identifiant], chemins, client, jour, retelecharger_supprimes
        )
        if resultat.source != manifeste.sources[identifiant]:
            manifeste = manifeste.avec(resultat.source)
            enregistrer_sources(chemins, manifeste)
        resultats.append(resultat)
    if identifiants is None:
        inscrit = inscrire_deposes(chemins, manifeste)
        if inscrit != manifeste:
            enregistrer_sources(chemins, inscrit)
    return resultats
