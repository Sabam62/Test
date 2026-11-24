"""Téléchargement des sources ouvertes (RG-01, RG-05).

Le client HTTP est simulé (httpx.MockTransport) ; il ne sert que des extraits réels figés dans
tests/fixtures/ : le fichier mar_admin_boundaries.xlsx de HDX et les réponses des API HDX et
figshare, enregistrées le 22/11/2026. Aucune donnée n'est inventée.
"""

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import httpx
import pytest

from src.chemins import Chemins, chemins_par_defaut
from src.data.sources import (
    Fichier,
    ManifesteSources,
    Source,
    charger_sources,
    empreinte_sha256,
    enregistrer_sources,
)
from src.data.telechargement import (
    DOC_MANUELLE,
    ErreurTelechargement,
    inscrire_deposes,
    resoudre,
    telecharger_source,
    telecharger_tout,
)

DEPOT = chemins_par_defaut()
FIXTURES = DEPOT.racine / "tests" / "fixtures"
XLSX_HDX = FIXTURES / "SRC-05" / "mar_admin_boundaries.xlsx"
# Empreinte calculée indépendamment (shasum -a 256) sur le fichier téléchargé le 22/11/2026.
SHA256_XLSX_HDX = "3d26013673c4ae469be9a60148deec0b6bffa32caf4996e2160d1eab320095de"
API_HDX = json.loads((FIXTURES / "api" / "hdx_package_show_cod-ab-mar.json").read_text())
API_FIGSHARE = json.loads((FIXTURES / "api" / "figshare_article_22491997.json").read_text())
URL_XLSX_HDX = next(r["url"] for r in API_HDX["result"]["resources"] if r["name"] == XLSX_HDX.name)
JOUR = date(2026, 11, 22)


def _source_hdx_xlsx() -> Source:
    """SRC-05 du manifeste réel, réduite au seul fichier XLSX (21 ko), sans fichier inscrit.

    Les fichiers déjà inscrits par le téléchargement réel sont retirés : le test ne dépend
    pas de l'état de data/raw/ sur le poste.
    """
    source = charger_sources(DEPOT).sources["SRC-05"]
    assert source.telechargement is not None
    ressources = [r for r in source.telechargement.ressources if r.nom == XLSX_HDX.name]
    return source.model_copy(
        update={
            "telechargement": source.telechargement.model_copy(update={"ressources": ressources}),
            "fichiers": {},
        }
    )


def test_manifeste_sans_adresse_signee() -> None:
    # Les adresses signées (S3, R2) expirent et portent des jetons : jamais dans le manifeste.
    for source in charger_sources(DEPOT).sources.values():
        for nom, fichier in source.fichiers.items():
            url = fichier.url or ""
            for marque in ("Signature", "X-Amz-", "AWSAccessKeyId", "security-token"):
                assert marque not in url, f"{source.identifiant} · {nom}"


def test_redirection_signee_non_enregistree(copie: Chemins) -> None:
    signee = "https://stockage.example/mar_admin_boundaries.xlsx?Signature=abc&X-Amz-Expires=60"

    def serveur(requete: httpx.Request) -> httpx.Response:
        if requete.url.path.endswith("/package_show"):
            return httpx.Response(200, json=API_HDX)
        if str(requete.url) == URL_XLSX_HDX:
            return httpx.Response(302, headers={"Location": signee})
        if str(requete.url) == signee:
            return httpx.Response(200, content=XLSX_HDX.read_bytes())
        return httpx.Response(404)

    transport = httpx.MockTransport(serveur)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        resultat = telecharger_source(_source_hdx_xlsx(), copie, client, JOUR)
    assert resultat.erreur is None
    assert resultat.source.fichiers[XLSX_HDX.name].url == URL_XLSX_HDX


def _serveur_hdx(requete: httpx.Request) -> httpx.Response:
    """Rejoue l'API HDX et le fichier XLSX figés dans tests/fixtures/."""
    if requete.url.path.endswith("/package_show"):
        return httpx.Response(200, json=API_HDX)
    if str(requete.url) == URL_XLSX_HDX:
        return httpx.Response(200, content=XLSX_HDX.read_bytes())
    return httpx.Response(404)


def _aucun_appel(requete: httpx.Request) -> httpx.Response:
    raise AssertionError(f"appel réseau inattendu : {requete.url}")


def _hors_ligne(requete: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("hors ligne", request=requete)


@pytest.fixture
def copie(tmp_path: Path) -> Chemins:
    """Racine temporaire avec une copie de data/sources.yaml."""
    (tmp_path / "data").mkdir()
    shutil.copy(DEPOT.donnees / "sources.yaml", tmp_path / "data" / "sources.yaml")
    return Chemins(tmp_path)


# --- Empreintes et manifeste --------------------------------------------------------------


def test_empreinte_sha256_d_un_fichier_reel() -> None:
    assert empreinte_sha256(XLSX_HDX) == SHA256_XLSX_HDX


def test_manifeste_enregistre_puis_relu_a_l_identique(copie: Chemins) -> None:
    avant = charger_sources(copie)
    enregistrer_sources(copie, avant)
    assert charger_sources(copie) == avant


def test_sources_automatiques_ont_une_procedure_manuelle() -> None:
    texte = (DEPOT.racine / DOC_MANUELLE).read_text(encoding="utf-8")
    automatiques = [i for i, s in charger_sources(DEPOT).sources.items() if s.telechargement]
    assert set(automatiques) == {"SRC-01", "SRC-04", "SRC-05", "SRC-06", "SRC-09", "SRC-19"}
    for identifiant in automatiques:
        assert f"## {identifiant} " in texte, identifiant


# --- Résolution des adresses par les API --------------------------------------------------


def test_resolution_ckan_hdx() -> None:
    with httpx.Client(transport=httpx.MockTransport(_serveur_hdx)) as client:
        resolution = resoudre(_source_hdx_xlsx(), client)
    assert [c.url for c in resolution.cibles] == [URL_XLSX_HDX]
    assert resolution.cibles[0].taille == XLSX_HDX.stat().st_size
    assert resolution.licence == API_HDX["result"]["license_title"]


def test_resolution_figshare() -> None:
    source = charger_sources(DEPOT).sources["SRC-04"]

    def serveur(requete: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=API_FIGSHARE)

    with httpx.Client(transport=httpx.MockTransport(serveur)) as client:
        resolution = resoudre(source, client)
    attendus = {f["name"]: f for f in API_FIGSHARE["files"]}
    assert {c.nom for c in resolution.cibles} == {
        "CROPGRIDSv1.08_NC_maps.zip",
        "CODES.zip",
        "Table_CROPGRIDSv1.08_COU.xlsx",
    }
    for cible in resolution.cibles:
        assert cible.md5 == attendus[cible.nom]["computed_md5"]
        assert cible.url == attendus[cible.nom]["download_url"]
    assert resolution.licence == "CC BY 4.0"


def test_ressource_absente_de_l_api() -> None:
    source = _source_hdx_xlsx()
    assert source.telechargement is not None
    ressource = source.telechargement.ressources[0].model_copy(update={"nom": "absent.zip"})
    source = source.model_copy(
        update={
            "telechargement": source.telechargement.model_copy(update={"ressources": [ressource]})
        }
    )
    with (
        httpx.Client(transport=httpx.MockTransport(_serveur_hdx)) as client,
        pytest.raises(ErreurTelechargement, match=r"absent\.zip"),
    ):
        resoudre(source, client)


# --- Téléchargement (RG-01, RG-05) --------------------------------------------------------


def test_telechargement_ecrit_le_fichier_et_le_manifeste(copie: Chemins) -> None:
    with httpx.Client(transport=httpx.MockTransport(_serveur_hdx)) as client:
        resultat = telecharger_source(_source_hdx_xlsx(), copie, client, JOUR)
    assert resultat.erreur is None
    assert resultat.ecrits == [XLSX_HDX.name]
    cible = copie.brutes / "SRC-05" / XLSX_HDX.name
    assert cible.read_bytes() == XLSX_HDX.read_bytes()
    assert not list(cible.parent.glob("*.part"))
    fichier = resultat.source.fichiers[XLSX_HDX.name]
    assert fichier.sha256 == SHA256_XLSX_HDX
    assert fichier.taille_octets == XLSX_HDX.stat().st_size
    assert fichier.date_telechargement == JOUR
    assert fichier.url == URL_XLSX_HDX
    assert resultat.source.licence == API_HDX["result"]["license_title"]


def test_fichier_present_jamais_reecrit_rg01(copie: Chemins) -> None:
    dossier = copie.brutes / "SRC-05"
    dossier.mkdir(parents=True)
    present = dossier / XLSX_HDX.name
    shutil.copy(XLSX_HDX, present)
    date_modification = present.stat().st_mtime_ns
    with httpx.Client(transport=httpx.MockTransport(_aucun_appel)) as client:
        resultat = telecharger_source(_source_hdx_xlsx(), copie, client, JOUR)
    assert resultat.erreur is None
    assert resultat.ecrits == []
    assert resultat.deja_presents == [XLSX_HDX.name]
    assert present.stat().st_mtime_ns == date_modification
    # Un fichier déposé à la main est inscrit au manifeste avec son empreinte.
    assert resultat.source.fichiers[XLSX_HDX.name].sha256 == SHA256_XLSX_HDX


def test_echec_reseau_message_francais(copie: Chemins) -> None:
    with httpx.Client(transport=httpx.MockTransport(_hors_ligne)) as client:
        resultat = telecharger_source(_source_hdx_xlsx(), copie, client, JOUR)
    assert resultat.erreur is not None
    assert "SRC-05" in resultat.erreur
    assert "injoignable" in resultat.erreur
    assert DOC_MANUELLE in resultat.erreur
    assert resultat.source.fichiers == {}
    assert not (copie.brutes / "SRC-05").exists() or not any((copie.brutes / "SRC-05").iterdir())


def test_erreur_http_message_francais(copie: Chemins) -> None:
    def serveur(requete: httpx.Request) -> httpx.Response:
        if requete.url.path.endswith("/package_show"):
            return httpx.Response(200, json=API_HDX)
        return httpx.Response(403)

    with httpx.Client(transport=httpx.MockTransport(serveur)) as client:
        resultat = telecharger_source(_source_hdx_xlsx(), copie, client, JOUR)
    assert resultat.erreur is not None
    assert "403" in resultat.erreur
    assert not list((copie.brutes / "SRC-05").glob("*"))


def test_contenu_tronque_refuse(copie: Chemins) -> None:
    def serveur(requete: httpx.Request) -> httpx.Response:
        if requete.url.path.endswith("/package_show"):
            return httpx.Response(200, json=API_HDX)
        return httpx.Response(200, content=XLSX_HDX.read_bytes()[: XLSX_HDX.stat().st_size // 2])

    with httpx.Client(transport=httpx.MockTransport(serveur)) as client:
        resultat = telecharger_source(_source_hdx_xlsx(), copie, client, JOUR)
    assert resultat.erreur is not None
    assert "taille" in resultat.erreur
    assert not list((copie.brutes / "SRC-05").glob("*"))


def test_telecharger_tout_met_a_jour_sources_yaml(copie: Chemins) -> None:
    manifeste = charger_sources(copie)
    reduit = ManifesteSources(sources={**manifeste.sources, "SRC-05": _source_hdx_xlsx()})
    enregistrer_sources(copie, reduit)
    with httpx.Client(transport=httpx.MockTransport(_serveur_hdx)) as client:
        resultats = telecharger_tout(copie, client, JOUR, ["SRC-05"])
    assert [r.source.identifiant for r in resultats] == ["SRC-05"]
    relu = charger_sources(copie).sources["SRC-05"]
    assert relu.fichiers[XLSX_HDX.name].sha256 == SHA256_XLSX_HDX
    assert charger_sources(copie).sources["SRC-04"] == manifeste.sources["SRC-04"]


def _source_supprimee(remplace_par: str | None = None) -> Source:
    """SRC-05 réduite au XLSX, inscrit au manifeste puis supprimé volontairement."""
    source = _source_hdx_xlsx()
    fichier = Fichier(
        url=URL_XLSX_HDX,
        date_telechargement=JOUR,
        taille_octets=XLSX_HDX.stat().st_size,
        sha256=SHA256_XLSX_HDX,
        supprime_le=JOUR,
        remplace_par=remplace_par,
    )
    return source.model_copy(update={"fichiers": {XLSX_HDX.name: fichier}})


def test_fichier_supprime_volontairement_non_retelecharge(copie: Chemins) -> None:
    with httpx.Client(transport=httpx.MockTransport(_aucun_appel)) as client:
        resultat = telecharger_source(_source_supprimee(), copie, client, JOUR)
    assert resultat.erreur is None
    assert resultat.supprimes == [XLSX_HDX.name]
    assert resultat.ecrits == []
    assert not (copie.brutes / "SRC-05" / XLSX_HDX.name).exists()


def test_fichier_supprime_non_retelecharge_si_son_derive_existe(copie: Chemins) -> None:
    derive = copie.preparees / "derive.parquet"
    derive.parent.mkdir(parents=True, exist_ok=True)
    derive.write_bytes(b"")
    source = _source_supprimee(remplace_par="data/processed/derive.parquet")
    with httpx.Client(transport=httpx.MockTransport(_aucun_appel)) as client:
        resultat = telecharger_source(source, copie, client, JOUR)
    assert resultat.supprimes == [XLSX_HDX.name]
    assert resultat.ecrits == []


def test_installation_neuve_retelecharge_un_fichier_supprime_sans_derive(copie: Chemins) -> None:
    # Le manifeste versionné porte la suppression faite sur un autre poste : sans le fichier
    # dérivé, une installation neuve doit télécharger l'archive dès scripts.download.
    source = _source_supprimee(remplace_par="data/processed/derive.parquet")
    with httpx.Client(transport=httpx.MockTransport(_serveur_hdx)) as client:
        resultat = telecharger_source(source, copie, client, JOUR)
    assert resultat.erreur is None
    assert resultat.ecrits == [XLSX_HDX.name]
    assert resultat.source.fichiers[XLSX_HDX.name].supprime_le is None
    assert (copie.brutes / "SRC-05" / XLSX_HDX.name).read_bytes() == XLSX_HDX.read_bytes()


def test_manifeste_cropgrids_retelecharge_sur_installation_neuve() -> None:
    # L'archive mondiale supprimée sur le poste de l'équipe déclare son découpage du Maroc.
    archive = charger_sources(DEPOT).sources["SRC-04"].fichiers["CROPGRIDSv1.08_NC_maps.zip"]
    assert archive.supprime_le is not None
    assert archive.remplace_par == "data/processed/cropgrids_maroc.nc"


def test_fichier_supprime_retelecharge_sur_demande(copie: Chemins) -> None:
    with httpx.Client(transport=httpx.MockTransport(_serveur_hdx)) as client:
        resultat = telecharger_source(
            _source_supprimee(), copie, client, JOUR, retelecharger_supprimes=True
        )
    assert resultat.ecrits == [XLSX_HDX.name]
    assert resultat.source.fichiers[XLSX_HDX.name].supprime_le is None
    assert (copie.brutes / "SRC-05" / XLSX_HDX.name).read_bytes() == XLSX_HDX.read_bytes()


def test_fichier_depose_a_la_main_inscrit_au_manifeste(copie: Chemins) -> None:
    # Le fichier réel de HDX sert de dépôt manuel pour SRC-03 (source sans téléchargement).
    dossier = copie.brutes / "SRC-03"
    dossier.mkdir(parents=True)
    shutil.copy(XLSX_HDX, dossier / XLSX_HDX.name)
    (dossier / "inacheve.xlsx.part").write_bytes(b"")
    manifeste = inscrire_deposes(copie, charger_sources(copie))
    fichiers = manifeste.sources["SRC-03"].fichiers
    assert list(fichiers) == [XLSX_HDX.name]
    assert fichiers[XLSX_HDX.name].sha256 == SHA256_XLSX_HDX
    assert fichiers[XLSX_HDX.name].url is None


def test_table_saisie_par_l_equipe_inscrite_au_manifeste(copie: Chemins) -> None:
    # Les tables versionnées de data/manuelles/<source>/ sont inscrites comme les dépôts bruts.
    dossier = copie.manuelles / "SRC-03"
    dossier.mkdir(parents=True)
    shutil.copy(XLSX_HDX, dossier / XLSX_HDX.name)
    fichiers = inscrire_deposes(copie, charger_sources(copie)).sources["SRC-03"].fichiers
    assert list(fichiers) == [XLSX_HDX.name]
    assert fichiers[XLSX_HDX.name].sha256 == SHA256_XLSX_HDX


def test_source_inconnue(copie: Chemins) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(_aucun_appel)) as client,
        pytest.raises(ErreurTelechargement, match="SRC-99"),
    ):
        telecharger_tout(copie, client, JOUR, ["SRC-99"])


# --- Fichiers lourds hors de Git ----------------------------------------------------------


@pytest.mark.parametrize(
    "chemin",
    ["data/raw/SRC-04/CROPGRIDSv1.08_NC_maps.zip", "data/raw/SRC-06/morocco-latest.osm.pbf"],
)
def test_donnees_brutes_hors_de_git(chemin: str) -> None:
    resultat = subprocess.run(["git", "check-ignore", "-q", chemin], cwd=DEPOT.racine, check=False)
    assert resultat.returncode == 0, f"{chemin} n'est pas ignoré par Git"


def test_lisezmoi_de_data_raw_versionne() -> None:
    resultat = subprocess.run(
        ["git", "check-ignore", "-q", "data/raw/LISEZMOI.md"], cwd=DEPOT.racine, check=False
    )
    assert resultat.returncode == 1
    assert (DEPOT.brutes / "LISEZMOI.md").is_file()
