"""Coût livré, courbe et bassin d'approvisionnement d'un site (section 8.2, UC-LOG-03, 04).

CL(p, r, j) = a + k_col + k_pre + (F + v · 2 d) / q, en DH/t MS, avec :

- a : prix d'achat par t brute de ``concurrence.csv`` (province, sinon valeur nationale du
  résidu), ramené à la t MS : a / (1 − h) (décision du 23/11/2026) ;
- k_col, k_pre : coûts de collecte et de prétraitement de ``residus.csv`` ;
- F : coût fixe par rotation (PAR-61) ; v = consommation (PAR-38) × prix du gazole saisi par
  l'entreprise (PAR-37) ÷ part du carburant (PAR-39) ;
- q = min(charge maximale PAR-31, densité apparente × volume utile PAR-32) × (1 − h).

Une entrée « À compléter » bloque les seuls couples qui en dépendent, avec le motif (RG-14) ;
un paramètre commun à tous les couples (F, v, volume) bloque toute la courbe et figure dans la
liste des valeurs à saisir.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from src.data.provenance import Statut, ValeurACompleter, ValeurSourcee
from src.data.tables_reference import TableLongue
from src.logistique.config import ConfigLogistique

COLONNES_COUTS = [
    "code_province",
    "code_residu",
    "id_site",
    "tonnage",
    "distance_km",
    "methode",
    "prix_achat",
    "cout_collecte",
    "cout_pretraitement",
    "cout_transport",
    "charge_utile",
    "cout_livre",
    "statut",
    "sources",
]
COLONNES_EXCLUS = ["code_province", "code_residu", "motif"]


SEPARATEUR_BLOCAGES = "\n"


class Blocage(Exception):
    """Valeur manquante qui empêche un calcul (RG-14) ; message en français.

    Plusieurs valeurs manquantes sont séparées par ``SEPARATEUR_BLOCAGES`` (une par ligne).
    """


@dataclass(frozen=True)
class Terme:
    """Nombre utilisé par le calcul, avec son statut et sa source."""

    valeur: float
    statut: Statut
    source: str


def terme(valeur: ValeurSourcee, facteur: float = 1) -> Terme:
    """Lit une valeur sourcée ; lève :class:`Blocage` si elle est à compléter."""
    try:
        nombre = valeur.lire_nombre()
    except ValeurACompleter as erreur:
        raise Blocage(f"{erreur.nom} à compléter ; où la trouver : {erreur.ou_trouver}") from None
    source = valeur.provenance.source_id if valeur.provenance else ""
    statut = valeur.provenance.statut if valeur.provenance else Statut.HYPOTHESE
    return Terme(nombre * facteur, statut, source)


@dataclass(frozen=True)
class Transport:
    """Paramètres communs à tous les couples : coûts du camion (section 8.2)."""

    cout_variable: Terme  # v, DH/km
    cout_fixe: Terme  # F, DH/rotation
    charge_maximale: Terme  # t
    volume_utile: Terme  # m³


def transport(
    lire: Callable[[str], ValeurSourcee], config: ConfigLogistique, moins_fiable: Callable
) -> Transport:
    """Paramètres du camion ; lève :class:`Blocage` avec toutes les valeurs manquantes."""
    p, conv = config.parametres, config.conversions
    manquants, termes = [], {}
    for nom, identifiant in (
        ("consommation", p.consommation),
        ("gazole", p.prix_gazole),
        ("part", p.part_carburant),
        ("fixe", p.cout_fixe),
        ("charge", p.charge_maximale),
        ("volume", p.volume_utile),
    ):
        valeur = lire(identifiant)
        try:
            termes[nom] = terme(valeur, conv.get(valeur.unite, 1))
        except Blocage as blocage:
            manquants.append(str(blocage))
    if manquants:
        raise Blocage(SEPARATEUR_BLOCAGES.join(manquants))
    c, g, part = termes["consommation"], termes["gazole"], termes["part"]
    if part.valeur <= 0:
        raise Blocage(f"{p.part_carburant} doit être positif")
    v = Terme(
        c.valeur * g.valeur / part.valeur,
        moins_fiable([c.statut, g.statut, part.statut]),
        ", ".join(sorted({c.source, g.source, part.source})),
    )
    return Transport(v, termes["fixe"], termes["charge"], termes["volume"])


def _parametre_residu(residus: TableLongue, residu: str, parametre: str, facteur: float) -> Terme:
    try:
        return terme(residus.valeur(residu, parametre), facteur)
    except KeyError:
        raise Blocage(f"{residu} · {parametre} absent de residus.csv") from None


def prix_observe(
    prix: pd.DataFrame | None, residu: str, zone: str, produits: dict[str, str], unite: str
) -> Terme | None:
    """Prix observé le plus récent d'un résidu dans une zone (UC-DAT-07, section 13).

    Le produit est désigné par le code du résidu ou par son nom ; seuls les prix dans l'unité
    ``unite`` (celle de ``concurrence.csv``) sont retenus.
    """
    if prix is None or prix.empty:
        return None
    noms = {residu.lower(), produits.get(residu, residu).lower()}
    choix = prix[
        prix["produit"].astype(str).str.strip().str.lower().isin(noms)
        & (prix["code_province"].astype(str) == zone)
        & (prix["unite"].astype(str).str.strip() == unite)
    ]
    if choix.empty:
        return None
    dernier = choix.assign(_rang=range(len(choix))).sort_values(["date", "_rang"]).iloc[-1]
    return Terme(
        float(str(dernier["prix"]).replace(",", ".")),
        Statut.TERRAIN,
        f"prix observé du {dernier['date']} ({dernier['source']})",
    )


def _prix_achat(
    concurrence: TableLongue,
    province: str,
    residu: str,
    parametre: str,
    national: str,
    observes: Callable[[str, str], Terme | None] | None = None,
) -> Terme:
    """Prix de la province, sinon valeur nationale du résidu (UC-POT-01, scénario alternatif).

    À chaque niveau, un prix observé (le plus récent) prime sur la valeur de concurrence.csv.
    """
    for cle in ((province, residu), (national, residu)):
        if observes is not None:
            observe = observes(residu, cle[0])
            if observe is not None:
                return observe
        try:
            valeur = concurrence.valeur(cle, parametre)
        except KeyError:
            continue
        if valeur.est_a_completer and cle[0] != national:
            continue
        return terme(valeur)
    raise Blocage(f"{residu} · {parametre} absent de concurrence.csv")


def couts_livres(
    gisements: pd.DataFrame,
    distances: pd.DataFrame,
    residus: TableLongue,
    concurrence: TableLongue,
    camion: Transport,
    config: ConfigLogistique,
    national: str,
    moins_fiable: Callable,
    observes: Callable[[str, str], Terme | None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Coût livré de chaque couple de ``gisements`` vers le site de ``distances``.

    Args:
        gisements: M de la campagne de référence (``code_province``, ``code_residu``,
            ``valeur``, ``statut``).
        distances: lignes de la table ``distances`` pour un site.
        residus: ``residus.csv`` actif (humidité, densité, k_col, k_pre).
        concurrence: ``concurrence.csv`` actif (prix d'achat a).
        camion: paramètres du transport.
        config: ``config/logistique.yaml``.
        national: code des valeurs nationales de ``concurrence.csv``.
        moins_fiable: statut le moins fiable d'une liste.
        observes: prix observé le plus récent d'un résidu dans une zone, s'il existe.

    Returns:
        Table des coûts (``COLONNES_COUTS``) et couples exclus avec leur motif (RG-06).
    """
    pr, conv = config.residus, config.conversions
    tous = gisements.merge(distances, on=["code_province", "code_residu"], how="inner")
    lignes, exclus = [], []
    par_residu: dict[str, dict[str, Terme] | str] = {}
    for residu in sorted(tous["code_residu"].unique()):
        try:
            humidite = residus.valeur(residu, pr.humidite)
            par_residu[residu] = {
                "h": terme(humidite, conv.get("%", 1)),
                "densite": _parametre_residu(
                    residus, residu, pr.densite_apparente, conv.get("kg/m³", 1)
                ),
                "k_col": _parametre_residu(residus, residu, pr.cout_collecte, 1),
                "k_pre": _parametre_residu(residus, residu, pr.cout_pretraitement, 1),
            }
        except (Blocage, KeyError) as blocage:
            par_residu[residu] = str(blocage)
    for ligne in tous.itertuples():
        proprietes = par_residu[ligne.code_residu]
        if isinstance(proprietes, str):
            exclus.append((ligne.code_province, ligne.code_residu, proprietes))
            continue
        if pd.isna(ligne.distance_km):
            exclus.append(
                (ligne.code_province, ligne.code_residu, "aucun itinéraire routier vers le site")
            )
            continue
        try:
            a = _prix_achat(
                concurrence,
                ligne.code_province,
                ligne.code_residu,
                config.concurrence.prix_achat,
                national,
                observes,
            )
        except Blocage as blocage:
            exclus.append((ligne.code_province, ligne.code_residu, str(blocage)))
            continue
        h, densite = proprietes["h"], proprietes["densite"]
        q = min(camion.charge_maximale.valeur, densite.valeur * camion.volume_utile.valeur)
        q *= 1 - h.valeur
        if q <= 0:
            exclus.append((ligne.code_province, ligne.code_residu, "charge utile nulle"))
            continue
        rotation = camion.cout_fixe.valeur + camion.cout_variable.valeur * (
            config.trajets_par_rotation * ligne.distance_km
        )
        transport_t = rotation / q
        k_col, k_pre = proprietes["k_col"], proprietes["k_pre"]
        # a est un prix par t brute (concurrence.csv) : ramené à la t MS par (1 − h).
        prix_ms = a.valeur / (1 - h.valeur)
        cl = prix_ms + k_col.valeur + k_pre.valeur + transport_t
        entrees = [a, k_col, k_pre, h, densite, camion.cout_fixe, camion.cout_variable]
        entrees += [camion.charge_maximale, camion.volume_utile]
        statuts = [t.statut for t in entrees] + [Statut(ligne.statut)]
        lignes.append(
            {
                "code_province": ligne.code_province,
                "code_residu": ligne.code_residu,
                "id_site": ligne.id_site,
                "tonnage": float(ligne.valeur),
                "distance_km": float(ligne.distance_km),
                "methode": ligne.methode,
                "prix_achat": prix_ms,
                "cout_collecte": k_col.valeur,
                "cout_pretraitement": k_pre.valeur,
                "cout_transport": transport_t,
                "charge_utile": q,
                "cout_livre": cl,
                "statut": moins_fiable(statuts).value,
                "sources": ", ".join(sorted({t.source for t in entrees if t.source})),
            }
        )
    return (
        pd.DataFrame(lignes, columns=COLONNES_COUTS),
        pd.DataFrame(exclus, columns=COLONNES_EXCLUS),
    )


@dataclass(frozen=True)
class Courbe:
    """Courbe d'approvisionnement d'un site et indicateurs pour la capacité K (UC-LOG-03)."""

    points: pd.DataFrame  # couples triés par coût, avec tonnage cumulé
    capacite: float
    plafond: float
    tonnage_total: float
    tonnage_sous_plafond: float
    atteignable: bool
    manque: float
    cout_moyen_k: float | None
    cout_marginal_k: float | None
    retenus: pd.DataFrame = field(repr=False)  # tonnage retenu par couple pour atteindre K
    bassin: pd.DataFrame = field(repr=False)  # couples sous le prix plafond


def courbe_approvisionnement(
    couts: pd.DataFrame, capacite: float, plafond: float, distance_max: float | None
) -> Courbe:
    """Tri des couples par coût livré croissant et cumul des tonnages (section 8.2).

    Les couples au-delà de la distance maximale PAR-59 (si elle est saisie) sont écartés. Le
    coût moyen et le coût marginal à K portent sur les couples sous le prix plafond ; si leur
    tonnage n'atteint pas K, le site est « non atteignable » (RG-10) et le manque est donné.
    """
    points = couts.copy()
    if distance_max is not None:
        points = points[points["distance_km"] <= distance_max]
    points = points.sort_values(["cout_livre", "distance_km", "code_province", "code_residu"])
    points = points.reset_index(drop=True)
    points["cumul"] = points["tonnage"].cumsum()
    bassin = points[points["cout_livre"] <= plafond].copy()
    sous_plafond = float(bassin["tonnage"].sum())
    precedent = bassin["cumul"] - bassin["tonnage"]
    bassin["tonnage_retenu"] = (capacite - precedent).clip(lower=0).clip(upper=bassin["tonnage"])
    retenus = bassin[bassin["tonnage_retenu"] > 0]
    atteignable = sous_plafond >= capacite and capacite > 0
    cout_moyen = cout_marginal = None
    if not retenus.empty and atteignable:
        poids = retenus["tonnage_retenu"]
        cout_moyen = float((retenus["cout_livre"] * poids).sum() / poids.sum())
        cout_marginal = float(retenus["cout_livre"].iloc[-1])
    return Courbe(
        points=points,
        capacite=capacite,
        plafond=plafond,
        tonnage_total=float(points["tonnage"].sum()),
        tonnage_sous_plafond=sous_plafond,
        atteignable=atteignable,
        manque=max(capacite - sous_plafond, 0.0),
        cout_moyen_k=cout_moyen,
        cout_marginal_k=cout_marginal,
        retenus=retenus,
        bassin=bassin,
    )


def tonnage_dans_rayon(gisements: pd.DataFrame, distances: pd.DataFrame, rayon_km: float) -> float:
    """Tonnage mobilisable à moins de ``rayon_km`` par la route (critère C3, PAR-35)."""
    tous = gisements.merge(distances, on=["code_province", "code_residu"], how="inner")
    return float(tous.loc[tous["distance_km"] <= rayon_km, "valeur"].sum())
