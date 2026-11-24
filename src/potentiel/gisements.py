"""Gisement mobilisable, carbone, biochar, densité et variabilité (section 8.1, UC-POT-01 à 03).

À partir du gisement théorique T (:mod:`src.potentiel.theorique`) :

- M = T × f_col × f_eco × (1 − u) ; u est la part déjà utilisée de la province, sinon la
  valeur nationale du résidu (statut « Littérature » au mieux), sinon le couple est bloqué ;
- C = M × c et B = M × y ; C_T = T × c et B_T = T × y sont les valeurs « théoriques » ;
- densité = gisement ÷ surface agricole de la province (km², surface cultivée CROPGRIDS) ;
- cv_M = coefficient de variation de M sur les campagnes calculables (critère A5).

Chaque valeur garde sa provenance ; un indicateur dont une entrée manque est exclu et listé
avec le motif (RG-06, RG-14), jamais compté zéro.
"""

import statistics
from dataclasses import dataclass

import pandas as pd

from src.data.config_preparation import charger_config_preparation
from src.data.provenance import Statut, ValeurACompleter
from src.data.tables_reference import TableLongue
from src.potentiel.config import ConfigPotentiel
from src.potentiel.entrees import EntreesPotentiel
from src.potentiel.theorique import (
    CAMPAGNE_REFERENCE,
    SEPARATEUR,
    Blocage,
    ResultatTheorique,
    Terme,
    _terme,
)

COLONNES_GISEMENTS = [
    "code_province",
    "code_residu",
    "campagne",
    "indicateur",
    "valeur",
    "unite",
    "statut",
    "sources",
    "previsionnel",
    "campagnes",
    "note",
]
COLONNES_EXCLUS = ["code_province", "code_residu", "indicateur", "motif"]
COLONNES_SYNTHESE = [
    "code_residu",
    "indicateur",
    "total",
    "unite",
    "provinces_calculees",
    "provinces_exclues",
    "statut",
]


@dataclass(frozen=True)
class ResultatGisements:
    """Table ``gisements`` (format long, section 13) et indicateurs exclus (RG-06)."""

    gisements: pd.DataFrame
    exclus: pd.DataFrame

    def reference(self, indicateur: str) -> pd.DataFrame:
        """Valeurs de la campagne de référence pour un indicateur."""
        g = self.gisements
        return g[(g["campagne"] == CAMPAGNE_REFERENCE) & (g["indicateur"] == indicateur)]


class _Facteurs:
    """Coefficients d'un résidu (f_col, f_eco, c, y) et part concurrente par province."""

    def __init__(
        self, residus: TableLongue, concurrence: TableLongue, config: ConfigPotentiel, national: str
    ) -> None:
        self.residus = residus
        self.concurrence = concurrence
        self.config = config
        self.national = national

    def coefficient(self, residu: str, parametre: str) -> Terme:
        try:
            valeur = self.residus.valeur(residu, parametre)
        except KeyError:
            raise Blocage(f"{residu} · {parametre} absent de residus.csv") from None
        facteur = self.config.unites_fraction.get(valeur.unite)
        if facteur is None:
            raise Blocage(f"{valeur.nom} : unité « {valeur.unite} » inconnue")
        return _terme(valeur, facteur)

    def part_utilisee(self, province: str, residu: str) -> Terme:
        """Part utilisée u de la province, sinon nationale (Littérature au mieux, UC-POT-01)."""
        for cle, nationale in (((province, residu), False), ((self.national, residu), True)):
            try:
                valeur = self.concurrence.valeur(cle, "part_utilisee")
            except KeyError:
                continue
            if valeur.est_a_completer and not nationale:
                continue
            facteur = self.config.unites_fraction.get(valeur.unite)
            if facteur is None:
                raise Blocage(f"{valeur.nom} : unité « {valeur.unite} » inconnue")
            terme = _terme(valeur, facteur)
            if nationale:
                statut = self.config.moins_fiable([terme.statut, self.config.statut_u_national])
                return Terme(terme.valeur, statut, terme.source)
            return terme
        raise Blocage(f"{residu} · part_utilisee absente de concurrence.csv")


def _essayer(fonction, *args):  # noqa: ANN001, ANN002, ANN202 — capture d'un blocage
    try:
        return fonction(*args), None
    except (Blocage, ValeurACompleter) as blocage:
        return None, str(blocage)


def calculer_gisements(
    entrees: EntreesPotentiel, theorique: ResultatTheorique
) -> ResultatGisements:
    """Indicateurs des gisements de chaque province × résidu × campagne (section 8.1).

    Args:
        entrees: tables actives, configuration et référentiel.
        theorique: gisement théorique T et couples exclus.
    """
    config = entrees.config
    facteurs = _Facteurs(
        entrees.tables.residus,
        entrees.tables.concurrence,
        config,
        entrees.catalogue.code_national,
    )
    surfaces = _surfaces_agricoles(entrees)
    lignes: list[dict[str, object]] = []
    exclus: list[dict[str, object]] = []
    derives = [i for i in config.indicateurs if i != "T"]
    for _, couple in theorique.exclus.iterrows():
        exclus += [
            {
                **couple[["code_province", "code_residu"]].to_dict(),
                "indicateur": i,
                "motif": couple["motif"],
            }
            for i in config.indicateurs
        ]
    for residu, groupe in theorique.gisements.groupby("code_residu", sort=True):
        coefficients = {
            p: _essayer(facteurs.coefficient, residu, p)
            for p in ("f_col", "f_eco", "carbone", "rendement_pyrolyse")
        }
        for province, lignes_couple in groupe.groupby("code_province", sort=True):
            u, motif_u = _essayer(facteurs.part_utilisee, province, residu)
            calcul = _Couple(
                str(residu), str(province), lignes_couple, coefficients, (u, motif_u), config,
                surfaces.get(str(province)),
            )  # fmt: skip
            nouvelles, refus = calcul.indicateurs(derives)
            lignes += nouvelles
            exclus += refus
    gisements = pd.DataFrame(lignes, columns=COLONNES_GISEMENTS)
    return ResultatGisements(
        gisements.sort_values(
            ["code_residu", "code_province", "campagne", "indicateur"]
        ).reset_index(drop=True),
        pd.DataFrame(exclus, columns=COLONNES_EXCLUS),
    )


def _surfaces_agricoles(entrees: EntreesPotentiel) -> dict[str, tuple[float, Statut, str]]:
    """Surface agricole (km²) de chaque province, avec statut et source."""
    chemin = (
        entrees.chemins.preparees
        / charger_config_preparation(entrees.chemins).cropgrids.sortie_agricole
    )
    if not chemin.is_file():
        return {}
    table = pd.read_parquet(chemin)
    return {
        str(ligne.code_province): (
            float(ligne.surface_ha) / entrees.config.hectares_par_km2,
            Statut(ligne.statut),
            str(ligne.source_id),
        )
        for ligne in table.itertuples()
    }


class _Couple:
    """Indicateurs dérivés d'un couple province × résidu, pour chaque campagne."""

    def __init__(
        self,
        residu: str,
        province: str,
        lignes_t: pd.DataFrame,
        coefficients: dict[str, tuple[Terme | None, str | None]],
        u: tuple[Terme | None, str | None],
        config: ConfigPotentiel,
        surface: tuple[float, Statut, str] | None,
    ) -> None:
        self.residu = residu
        self.province = province
        self.lignes_t = lignes_t
        self.coefficients = coefficients
        self.u = u
        self.config = config
        self.surface = surface

    def _refus(self, indicateur: str, motif: str) -> dict[str, object]:
        return {
            "code_province": self.province,
            "code_residu": self.residu,
            "indicateur": indicateur,
            "motif": motif,
        }

    def _ligne(
        self, t: pd.Series, indicateur: str, valeur: float, termes: list[Terme], note: str
    ) -> dict[str, object]:
        statuts = [Statut(t["statut"]), *(x.statut for x in termes)]
        sources = set(str(t["sources"]).split(SEPARATEUR)) | {x.source for x in termes}
        return {
            "code_province": self.province,
            "code_residu": self.residu,
            "campagne": t["campagne"],
            "indicateur": indicateur,
            "valeur": valeur,
            "unite": self.config.indicateurs[indicateur].unite,
            "statut": self.config.moins_fiable(statuts).value,
            "sources": SEPARATEUR.join(sorted(s for s in sources if s)),
            "previsionnel": bool(t["previsionnel"]),
            "campagnes": t["campagnes"],
            "note": note,
        }

    def indicateurs(
        self, derives: list[str]
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        lignes: list[dict[str, object]] = []
        refus: list[dict[str, object]] = []
        f_col, motif_col = self.coefficients["f_col"]
        f_eco, motif_eco = self.coefficients["f_eco"]
        carbone, motif_c = self.coefficients["carbone"]
        rendement, motif_y = self.coefficients["rendement_pyrolyse"]
        u, motif_u = self.u
        motif_m = motif_col or motif_eco or motif_u
        valeurs_m: list[float] = []
        reference_m: pd.Series | None = None
        for _, t in self.lignes_t.iterrows():
            valeur_t = float(t["valeur"])
            reference = t["campagne"] == CAMPAGNE_REFERENCE
            lignes.append(self._ligne(t, "T", valeur_t, [], str(t["note"])))
            if carbone is not None:
                lignes.append(
                    self._ligne(t, "C_T", valeur_t * carbone.valeur, [carbone], "T × carbone")
                )
            elif reference:
                refus.append(self._refus("C_T", str(motif_c)))
            if rendement is not None:
                lignes.append(
                    self._ligne(
                        t,
                        "B_T",
                        valeur_t * rendement.valeur,
                        [rendement],
                        "T × rendement de pyrolyse",
                    )
                )
            elif reference:
                refus.append(self._refus("B_T", str(motif_y)))
            self._densite(t, "densite_T", valeur_t, [], lignes, refus, reference)
            if motif_m is not None or f_col is None or f_eco is None or u is None:
                if reference:
                    refus += [
                        self._refus(i, str(motif_m)) for i in ("M", "C", "B", "densite_M", "cv_M")
                    ]
                continue
            termes_m = [f_col, f_eco, u]
            valeur_m = valeur_t * f_col.valeur * f_eco.valeur * (1 - u.valeur)
            lignes.append(self._ligne(t, "M", valeur_m, termes_m, "T × f_col × f_eco × (1 − u)"))
            if carbone is not None:
                lignes.append(
                    self._ligne(
                        t, "C", valeur_m * carbone.valeur, [*termes_m, carbone], "M × carbone"
                    )
                )
            elif reference:
                refus.append(self._refus("C", str(motif_c)))
            if rendement is not None:
                lignes.append(
                    self._ligne(
                        t,
                        "B",
                        valeur_m * rendement.valeur,
                        [*termes_m, rendement],
                        "M × rendement de pyrolyse",
                    )
                )
            elif reference:
                refus.append(self._refus("B", str(motif_y)))
            self._densite(t, "densite_M", valeur_m, termes_m, lignes, refus, reference)
            if reference:
                reference_m = t
            else:
                valeurs_m.append(valeur_m)
        if reference_m is not None and f_col is not None and f_eco is not None and u is not None:
            if len(valeurs_m) > 1 and statistics.fmean(valeurs_m) > 0:
                cv = statistics.stdev(valeurs_m) / statistics.fmean(valeurs_m)
                ligne = self._ligne(
                    reference_m,
                    "cv_M",
                    cv,
                    [f_col, f_eco, u],
                    f"écart type ÷ moyenne de M sur {len(valeurs_m)} campagnes",
                )
                lignes.append(ligne)
            else:
                refus.append(self._refus("cv_M", "moins de deux campagnes calculables"))
        return [x for x in lignes if x["indicateur"] in {"T", *derives}], refus

    def _densite(
        self,
        t: pd.Series,
        indicateur: str,
        valeur: float,
        termes: list[Terme],
        lignes: list[dict[str, object]],
        refus: list[dict[str, object]],
        reference: bool,
    ) -> None:
        if self.surface is None or self.surface[0] <= 0:
            if reference:
                refus.append(
                    self._refus(indicateur, "surface agricole nulle ou absente (CROPGRIDS)")
                )
            return
        km2, statut, source = self.surface
        terme = Terme(km2, statut, source)
        lignes.append(
            self._ligne(
                t, indicateur, valeur / km2, [*termes, terme], "gisement ÷ surface agricole (km²)"
            )
        )


def synthese_nationale(resultat: ResultatGisements, config: ConfigPotentiel) -> pd.DataFrame:
    """Total national de chaque indicateur additif par résidu (campagne de référence)."""
    lignes = []
    exclus = resultat.exclus
    for indicateur, definition in config.indicateurs.items():
        if not definition.additif:
            continue
        valeurs = resultat.reference(indicateur)
        residus = sorted(
            set(valeurs["code_residu"])
            | set(exclus[exclus["indicateur"] == indicateur]["code_residu"])
        )
        for residu in residus:
            sous = valeurs[valeurs["code_residu"] == residu]
            refus = exclus[(exclus["indicateur"] == indicateur) & (exclus["code_residu"] == residu)]
            lignes.append(
                {
                    "code_residu": residu,
                    "indicateur": indicateur,
                    "total": float(sous["valeur"].sum()) if not sous.empty else None,
                    "unite": definition.unite,
                    "provinces_calculees": len(sous),
                    "provinces_exclues": len(refus),
                    "statut": config.moins_fiable([Statut(s) for s in sous["statut"]]).value
                    if not sous.empty
                    else None,
                }
            )
    return pd.DataFrame(lignes, columns=COLONNES_SYNTHESE)
