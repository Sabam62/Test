"""Bilan net de chaque chaîne province × résidu × site (section 8.3, UC-ACV-01 à 03).

BN = C_bc · F_perm · 44/12 − (E_col + E_pre + E_tr + E_pyr + E_ep) + E_ref, en t CO₂e par t de
biochar (positif = retrait net), avec, pour m = 1 / y t MS par t de biochar :

- E_col = m · gazole de collecte · s_gazole ; E_pre = m · électricité de broyage · s_élec ;
- E_tr = m · consommation du camion · 2 d / q · s_gazole ;
- E_pyr = électricité de la pyrolyse · s_élec + s_pyrolyse (CH₄ et N₂O) ;
- E_ep = (gazole d'épandage + consommation · 2 d_biochar / charge) · s_gazole ;
- E_ref = m · s_référence (brûlage, décomposition : émissions évitées) ; pour un usage
  concurrent, − m · PCI du résidu · s_fioul (charge du fioul qui remplace sa chaleur, par MJ).

s_x est le score PRG100 d'une unité de l'activité agrégée x, calculé par Brightway
(:func:`src.acv.modele.scores_unitaires`) ; s_gazole = combustion + amont. Le même modèle,
paramétré chaîne par chaîne, est évalué par :func:`src.acv.modele.bilan_brightway`.
"""

import pandas as pd

from src.acv.config import ConfigAcv
from src.acv.entrees import Entree, EntreesAcv
from src.acv.modele import ScoresUnitaires
from src.logistique.couts import Terme

COLONNES_BILANS = [
    "code_province",
    "code_residu",
    "id_site",
    "distance_km",
    "E_col",
    "E_pre",
    "E_tr",
    "E_pyr",
    "E_ep",
    "E_ref",
    "stock",
    "BN",
    "statut",
    "sources",
    "motif",
]


class _Calcul:
    """Termes d'un résidu ; chaque terme est un nombre ou la liste des valeurs qui manquent."""

    def __init__(self, moins_fiable) -> None:  # noqa: ANN001
        self.manques: list[str] = []
        self.termes: list[Terme] = []
        self.moins_fiable = moins_fiable

    def valeur(self, entree: Entree) -> float | None:
        if isinstance(entree, Terme):
            self.termes.append(entree)
            return entree.valeur
        if entree not in self.manques:
            self.manques.append(entree)
        return None


def _facteurs_manquants(entrees: EntreesAcv, activite: str) -> list[str]:
    return [v for v in entrees.facteurs[activite].values() if not isinstance(v, Terme)]


def charge_utile(entrees: EntreesAcv, residu: str, calcul: _Calcul) -> float | None:
    """Charge utile q = min(charge, densité × volume utile) × (1 − h), en t MS (§8.2)."""
    p = entrees.residus[residu]
    charge, volume = calcul.valeur(entrees.charge_camion), calcul.valeur(entrees.volume_camion)
    densite, h = calcul.valeur(p.densite), calcul.valeur(p.humidite)
    if None in (charge, volume, densite, h):
        return None
    return min(charge, densite * volume) * (1 - h)


def bilans(
    entrees: EntreesAcv,
    scores: ScoresUnitaires,
    distances: pd.DataFrame,
    config: ConfigAcv,
    moins_fiable,  # noqa: ANN001
) -> pd.DataFrame:
    """Bilan de chaque ligne de ``distances``, en t CO₂e/t biochar.

    Une ligne bloquée porte ses motifs (RG-14) ; ``distances`` a les colonnes
    ``code_province``, ``code_residu``, ``id_site`` et ``distance_km``.

    Args:
        entrees: entrées du bilan.
        scores: scores unitaires Brightway des activités agrégées (kg CO₂e/unité).
        distances: lignes de la table ``distances``.
        config: ``config/acv.yaml``.
        moins_fiable: statut le moins fiable d'une liste.
    """
    s = scores.scores
    kg = config.kg_par_tonne
    lignes = []
    manques_fond = {a: _facteurs_manquants(entrees, a) for a in config.arriere_plan}
    for residu, groupe in distances.groupby("code_residu", sort=True):
        c = _Calcul(moins_fiable)
        p = entrees.residus[str(residu)]

        def score(activite: str, calcul: _Calcul = c) -> float | None:
            for motif in manques_fond[activite]:
                if motif not in calcul.manques:
                    calcul.manques.append(motif)
            return None if manques_fond[activite] else s[activite]

        y = c.valeur(p.rendement)
        m = 1 / y if y else None
        s_gaz = [score("gazole_combustion"), score("gazole_amont")]
        gazole = None if None in s_gaz else sum(s_gaz)  # type: ignore[arg-type]
        elec = score("electricite_reseau")
        a = {nom: c.valeur(entree) for nom, entree in entrees.activites.items()}
        conso = c.valeur(entrees.consommation_camion)
        charge = c.valeur(entrees.charge_camion)
        q = charge_utile(entrees, str(residu), c)
        c_bc, f_perm = c.valeur(p.carbone_biochar), c.valeur(entrees.permanence)
        stock = (
            c_bc * f_perm * config.masse_molaire_co2 / config.masse_molaire_c
            if None not in (c_bc, f_perm)
            else None
        )
        if p.scenario is None:
            c.manques.append(p.motif_scenario or f"{residu} · scenario_reference à compléter")
            e_ref_unitaire = None
        else:
            activite_ref = config.scenarios_reference[p.scenario]
            s_ref = score(activite_ref) if activite_ref else None
            if activite_ref is None:
                e_ref_unitaire = 0.0  # « sans substitution » : aucun devenir évité ni ajouté
            elif activite_ref == "fioul_substitution":
                # Chaleur du résidu (MJ par t MS) remplacée par du fioul : une charge (§8.3).
                pci = c.valeur(p.pci)
                e_ref_unitaire = -pci * kg * s_ref if None not in (pci, s_ref) else None
            else:
                e_ref_unitaire = s_ref
        s_pyr = score("pyrolyse")
        statut = moins_fiable([t.statut for t in c.termes]).value if c.termes else None
        sources = ", ".join(sorted({t.source for t in c.termes if t.source}))
        for ligne in groupe.itertuples():

            def prod(*facteurs: float | None) -> float | None:
                if any(f is None for f in facteurs):
                    return None
                resultat = 1.0
                for f in facteurs:
                    resultat *= f  # type: ignore[operator]
                return resultat / kg

            d = float(ligne.distance_km)
            e_col = prod(m, a["gazole_collecte"], gazole)
            e_pre = prod(m, a["electricite_broyage"], elec)
            e_tr = (
                prod(m, conso, config.trajets_par_rotation, d, gazole) / q
                if q and None not in (m, conso, gazole)
                else None
            )
            e_pyr = (
                (a["electricite_pyrolyse"] * elec + s_pyr) / kg
                if None not in (a["electricite_pyrolyse"], elec, s_pyr)
                else None
            )
            e_ep = (
                (
                    a["gazole_epandage"]
                    + conso * config.trajets_par_rotation * a["distance_biochar"] / charge
                )
                * gazole
                / kg
                if None not in (a["gazole_epandage"], conso, a["distance_biochar"], charge, gazole)
                and charge
                else None
            )
            e_ref = prod(m, e_ref_unitaire)
            termes = [e_col, e_pre, e_tr, e_pyr, e_ep, e_ref, stock]
            bn = (
                stock - (e_col + e_pre + e_tr + e_pyr + e_ep) + e_ref  # type: ignore[operator]
                if None not in termes
                else None
            )
            manques = list(c.manques)
            if q is None and not any(
                "charge" in x or "densite" in x or "PAR-32" in x for x in manques
            ):
                manques.append("charge utile du camion à compléter")
            lignes.append(
                {
                    "code_province": ligne.code_province,
                    "code_residu": residu,
                    "id_site": ligne.id_site,
                    "distance_km": d,
                    "E_col": e_col,
                    "E_pre": e_pre,
                    "E_tr": e_tr,
                    "E_pyr": e_pyr,
                    "E_ep": e_ep,
                    "E_ref": e_ref,
                    "stock": stock,
                    "BN": bn,
                    "statut": statut,
                    "sources": sources,
                    "motif": " | ".join(manques) if bn is None else "",
                }
            )
    return pd.DataFrame(lignes, columns=COLONNES_BILANS)


def facteur_reference(entrees: EntreesAcv, residu: str, config: ConfigAcv) -> float:
    """Unités de l'activité de référence par t MS (1, ou MJ de fioul pour l'usage concurrent)."""
    p = entrees.residus[residu]
    usage = bool(p.scenario) and config.scenarios_reference[p.scenario] == "fioul_substitution"
    if usage and isinstance(p.pci, Terme):
        return p.pci.valeur * config.kg_par_tonne
    return 1.0
