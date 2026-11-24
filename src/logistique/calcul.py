"""Enchaînement du module logistique (M2) : sites, distances, coûts et courbes par site.

Fonction principale : :func:`calculer_logistique`, qui prend les gisements du module M1 et
renvoie la matrice des distances, les paramètres du camion (ou les valeurs à saisir) et, pour
un site, sa courbe d'approvisionnement (:meth:`ResultatLogistique.courbe`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import geopandas as gpd
import pandas as pd

from src.chemins import Chemins
from src.data.provenance import Provenance, Statut, ValeurACompleter, ValeurSourcee
from src.data.tables_reference import TableLongue
from src.logistique.config import ConfigLogistique, charger_config_logistique
from src.logistique.couts import (
    SEPARATEUR_BLOCAGES,
    Blocage,
    Courbe,
    Terme,
    Transport,
    courbe_approvisionnement,
    couts_livres,
    prix_observe,
    tonnage_dans_rayon,
    transport,
)
from src.logistique.distances import Matrice, matrice_distances
from src.logistique.sites import SitesCandidats, charger_sites
from src.scenarios.config import charger_entreprise
from src.scenarios.parametres import valeur_courante

SOURCE_ENTREPRISE = "Atlantic Biochar (paramètres de l'entreprise)"


def lecteur_parametres(chemins: Chemins) -> Callable[[str], ValeurSourcee]:
    """Valeur d'un paramètre : saisie de l'entreprise (14.1), sinon paramètre technique (14.3).

    Un paramètre de l'entreprise non renseigné est « À compléter » et renvoie à l'onglet
    Paramètres (RG-15) : il n'est jamais remplacé par le repère de ``parametres.yaml``.
    """
    entreprise = charger_entreprise(chemins).parametres

    def lire(identifiant: str) -> ValeurSourcee:
        parametre = entreprise.get(identifiant)
        if parametre is None:
            return valeur_courante(chemins, identifiant)
        nom = f"{identifiant} ({parametre.libelle})"
        if parametre.valeur is None or not isinstance(parametre.valeur, int | float):
            return ValeurSourcee(
                nom=nom,
                valeur=None,
                unite=parametre.unite,
                ou_trouver="onglet Paramètres, section Entreprise",
            )
        return ValeurSourcee(
            nom=nom,
            valeur=float(parametre.valeur),
            unite=parametre.unite,
            provenance=Provenance(
                source_id=SOURCE_ENTREPRISE, annee=date.today().year, statut=Statut.TERRAIN
            ),
        )

    return lire


@dataclass(frozen=True)
class ResultatLogistique:
    """Distances et paramètres communs ; courbes calculées à la demande, site par site."""

    config: ConfigLogistique
    sites: SitesCandidats
    rattachements: pd.DataFrame
    matrice: Matrice
    gisements: pd.DataFrame
    camion: Transport | None
    blocage_camion: str | None
    residus: TableLongue
    concurrence: TableLongue
    national: str
    moins_fiable: Callable
    lire: Callable[[str], ValeurSourcee]
    prix_observes: pd.DataFrame | None = None
    noms_residus: dict[str, str] | None = None

    def distances_site(self, id_site: str) -> pd.DataFrame:
        """Lignes de la matrice pour un site."""
        d = self.matrice.distances
        return d[d["id_site"] == id_site]

    def couts(self, id_site: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Coûts livrés vers un site et couples exclus ; Blocage si le camion est incomplet."""
        if self.camion is None:
            raise Blocage(self.blocage_camion or "paramètres du transport à compléter")
        return couts_livres(
            self.gisements,
            self.distances_site(id_site),
            self.residus,
            self.concurrence,
            self.camion,
            self.config,
            self.national,
            self.moins_fiable,
            self._observe,
        )

    def _observe(self, residu: str, zone: str) -> Terme | None:
        return prix_observe(
            self.prix_observes,
            residu,
            zone,
            self.noms_residus or {},
            self.config.concurrence.unite_prix,
        )

    def courbe(self, id_site: str) -> tuple[Courbe, pd.DataFrame]:
        """Courbe d'approvisionnement du site pour K et le prix plafond (UC-LOG-03)."""
        p = self.config.parametres
        manquants = []
        valeurs: dict[str, float] = {}
        for nom, identifiant in (("K", p.capacite), ("plafond", p.prix_plafond)):
            try:
                valeurs[nom] = self.lire(identifiant).lire_nombre()
            except ValeurACompleter as erreur:
                manquants.append(f"{erreur.nom} à renseigner ; où : {erreur.ou_trouver}")
        couts, exclus = self.couts(id_site) if self.camion is not None else (None, None)
        if self.camion is None:
            manquants.append(self.blocage_camion or "")
        if self.gisements.empty:
            manquants.append(
                "gisement mobilisable M : aucun couple calculé (f_col, f_eco ou part utilisée u "
                "à compléter) ; où les trouver : écran Gisements, liste des couples exclus"
            )
        if manquants:
            raise Blocage(SEPARATEUR_BLOCAGES.join(m for m in manquants if m))
        distance_max = self.lire(p.distance_maximale).valeur
        dmax = float(distance_max) if isinstance(distance_max, int | float) else None
        assert couts is not None and exclus is not None
        return courbe_approvisionnement(couts, valeurs["K"], valeurs["plafond"], dmax), exclus

    def tonnage_rayon(self, id_site: str) -> float | None:
        """Critère C3 : tonnage à moins de R km (PAR-35) ; None si R ou les gisements manquent.

        Sans aucun gisement mobilisable calculé, le tonnage n'est pas zéro mais inconnu (RG-06).
        """
        if self.gisements.empty:
            return None
        try:
            rayon = self.lire(self.config.parametres.rayon_c3).lire_nombre()
        except ValeurACompleter:
            return None
        return tonnage_dans_rayon(self.gisements, self.distances_site(id_site), rayon)


def calculer_logistique(
    chemins: Chemins,
    gisements_m: pd.DataFrame,
    residus: TableLongue,
    concurrence: TableLongue,
    national: str,
    moins_fiable: Callable,
    provinces: gpd.GeoDataFrame,
    forcer_repli: bool = False,
    prix_observes: pd.DataFrame | None = None,
    noms_residus: dict[str, str] | None = None,
) -> ResultatLogistique:
    """Sites, points de rattachement, matrice des distances et paramètres du camion.

    Args:
        chemins: dossiers de l'outil.
        gisements_m: M de la campagne de référence (module M1).
        residus: ``residus.csv`` actif.
        concurrence: ``concurrence.csv`` actif.
        national: code des valeurs nationales de ``concurrence.csv``.
        moins_fiable: statut le moins fiable d'une liste (``config/potentiel.yaml``).
        provinces: polygones du référentiel (rattachement des sites à une province).
        forcer_repli: True pour calculer sans OSRM (repli à vol d'oiseau, tests).
        prix_observes: historique des prix observés (UC-DAT-07), le plus récent prime.
        noms_residus: nom de chaque résidu (produit d'un prix observé).
    """
    config = charger_config_logistique(chemins)
    sites = charger_sites(chemins, config, provinces)
    fichier = chemins.preparees / config.rattachement.sortie
    if not fichier.is_file():
        raise Blocage("points de rattachement absents : lancez « python -m scripts.prepare »")
    rattachements = pd.read_parquet(fichier)
    matrice = matrice_distances(
        chemins, config, rattachements, sites.sites, date.today().isoformat(), forcer_repli
    )
    lire = lecteur_parametres(chemins)
    try:
        camion: Transport | None = transport(lire, config, moins_fiable)
        blocage = None
    except Blocage as erreur:
        camion, blocage = None, str(erreur)
    return ResultatLogistique(
        config,
        sites,
        rattachements,
        matrice,
        gisements_m,
        camion,
        blocage,
        residus,
        concurrence,
        national,
        moins_fiable,
        lire,
        prix_observes,
        noms_residus,
    )
