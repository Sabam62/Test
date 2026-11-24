"""Désagrégation hiérarchique des statistiques vers les provinces (RG-04, UC-DAT-04).

Pour chaque grandeur (production, superficie), chaque culture et chaque campagne :

1. valeur provinciale réelle : gardée avec le statut de sa source. Une valeur publiée pour un
   groupe de provinces (« Fès » comptant Moulay Yacoub) est répartie entre ses membres non
   connus au prorata de leur surface CROPGRIDS (statut « Estimée ») ;
2. sinon, total régional réel moins les provinces de la région déjà connues, réparti entre les
   provinces manquantes au prorata de leur surface CROPGRIDS (statut « Estimée ») ;
3. sinon, total national moins toutes les provinces déjà attribuées (réelles ou estimées à
   l'étape 2), avec la même répartition (statut « Estimée »).

Une valeur prévisionnelle n'est retenue que s'il n'existe pas de valeur réalisée pour la même
zone et la même campagne ; elle est signalée (``previsionnel``) et les valeurs estimées à partir
d'elle le sont aussi. Chaque valeur estimée garde la source du total, la part CROPGRIDS et la
campagne. Contrôle : la somme des provinces égale le total parent, à la tolérance de
``config/controles.yaml``.

Un total qui ne peut pas être réparti (provinces connues supérieures au total, surface
CROPGRIDS nulle pour un reste positif, culture absente de CROPGRIDS) est signalé comme
incohérence ; ses provinces restent sans valeur, jamais à zéro par défaut (RG-06).
"""

from dataclasses import dataclass, field

import pandas as pd

from src.data.observations import SEPARATEUR_CODES, Niveau, annee_campagne
from src.data.provenance import Statut

COLONNES_PRODUCTION = [
    "code_province",
    "code_culture",
    "campagne",
    "periode",
    "variable",
    "valeur",
    "unite",
    "source_id",
    "document",
    "url",
    "annee",
    "statut",
    "version",
    "niveau_source",
    "source_total",
    "part_cropgrids",
    "soustraites",
    "ecart_campagne",
    "previsionnel",
    "methode",
    "note",
]
COLONNES_CONTROLES = [
    "niveau",
    "code_zone",
    "code_culture",
    "campagne",
    "variable",
    "total",
    "somme_provinces",
    "ecart_relatif",
    "conforme",
]
# Étape de la RG-04 de chaque maille, dans l'ordre de Niveau : province, région, pays.
ETAPES = {niveau: numero for numero, niveau in enumerate(Niveau, start=1)}


@dataclass
class ResultatDesagregation:
    """Valeurs provinciales, contrôles des sommes et signalements."""

    production: pd.DataFrame
    controles: pd.DataFrame
    incoherences: list[str] = field(default_factory=list)
    previsions_ecartees: list[str] = field(default_factory=list)
    ecarts_campagne: list[str] = field(default_factory=list)


@dataclass
class _Calcul:
    """Désagrégation d'une grandeur, d'une culture et d'une campagne."""

    variable: str
    culture: str
    campagne: str
    surfaces: pd.Series  # surface CROPGRIDS (ha) par province ; vide si la culture n'y est pas
    region_de: pd.Series
    tolerance: float
    attribuees: dict[str, dict[str, object]] = field(default_factory=dict)
    controles: list[dict[str, object]] = field(default_factory=list)
    incoherences: list[str] = field(default_factory=list)
    ecarts_campagne: list[str] = field(default_factory=list)

    @property
    def contexte(self) -> str:
        return f"{self.culture}, {self.campagne}, {self.variable}"

    def connue(self, province: str, total: pd.Series) -> None:
        self.attribuees[province] = {
            **self._provenance(total),
            "code_province": province,
            "valeur": float(total["valeur"]),
            "statut": total["statut"],
            "niveau_source": Niveau.PROVINCE.value,
            "source_total": None,
            "part_cropgrids": None,
            "soustraites": None,
            "ecart_campagne": False,
            "campagne_valeur": total["campagne"],
            "methode": total["methode"],
            "note": total["note"],
        }

    def _provenance(self, total: pd.Series) -> dict[str, object]:
        return {
            "code_culture": self.culture,
            "campagne": self.campagne,
            "variable": self.variable,
            "unite": total["unite"],
            "source_id": total["source_id"],
            "document": total["document"],
            "url": total["url"],
            "periode": total["periode"],
            "annee": annee_campagne(self.campagne),
            "version": total["version"],
            "previsionnel": bool(total["previsionnel"]),
        }

    def repartir(self, total: pd.Series, membres: list[str]) -> bool:
        """Répartit ``total`` entre les ``membres`` non encore attribués ; False si impossible."""
        valeur = float(total["valeur"])
        connus = [p for p in membres if p in self.attribuees]
        manquants = [p for p in membres if p not in self.attribuees]
        somme_connus = sum(float(self.attribuees[p]["valeur"]) for p in connus)  # type: ignore[arg-type]
        reste = valeur - somme_connus
        seuil = self.tolerance * valeur
        zone = f"{total['niveau']} {total['code_zone']} ({self.contexte})"
        if reste < -seuil:
            self.incoherences.append(
                f"{zone} : les provinces connues ({somme_connus:.0f}) dépassent le total "
                f"({valeur:.0f}) ; total non réparti"
            )
            return False
        reste = max(reste, 0)
        if not manquants:
            self._controler(total, membres)
            return True
        if self.surfaces.empty:
            self.incoherences.append(f"{zone} : culture sans surface CROPGRIDS ; total non réparti")
            return False
        parts = self.surfaces.reindex(manquants).fillna(0)
        somme_parts = float(parts.sum())
        if somme_parts <= 0 and reste > seuil:
            self.incoherences.append(
                f"{zone} : reste de {reste:.0f} pour des provinces sans surface CROPGRIDS "
                f"({', '.join(manquants)}) ; total non réparti"
            )
            return False
        etape = ETAPES[Niveau(total["niveau"])]
        soustraites, ecarts = self._soustraites(total, connus)
        note = (
            f"total {total['niveau']} {total['code_zone']} de {valeur:.0f} moins "
            f"{len(connus)} province(s) connue(s) ({somme_connus:.0f}), réparti au prorata "
            "des surfaces CROPGRIDS"
        )
        if ecarts:
            note += f" ; campagne différente du total pour : {', '.join(ecarts)}"
            self.ecarts_campagne.append(f"{zone} : {', '.join(ecarts)}")
        for province in manquants:
            part = float(parts[province]) / somme_parts if somme_parts > 0 else 0.0
            self.attribuees[province] = {
                **self._provenance(total),
                "code_province": province,
                "valeur": reste * part,
                "statut": Statut.ESTIMEE.value,
                "niveau_source": total["niveau"],
                "source_total": f"{total['source_id']} · {total['document']}",
                "part_cropgrids": part,
                "soustraites": soustraites,
                "ecart_campagne": bool(ecarts),
                "campagne_valeur": total["campagne"],
                "methode": f"RG-04 étape {etape}",
                "note": note,
            }
        self._controler(total, membres)
        return True

    def _soustraites(self, total: pd.Series, connus: list[str]) -> tuple[str | None, list[str]]:
        """Valeurs soustraites du total (province, campagne, période) et celles en écart.

        Une valeur soustraite est en écart si sa campagne diffère de celle du total, ou si l'une
        des deux campagnes a été déduite d'une année civile par la règle de campagne (RG-04).
        """
        if not connus:
            return None, []
        detail, ecarts = [], []
        for province in connus:
            valeur = self.attribuees[province]
            campagne, periode = valeur["campagne_valeur"], valeur["periode"]
            detail.append(f"{province} {campagne} ({periode})")
            if campagne != total["campagne"] or periode != total["periode"]:
                ecarts.append(
                    f"{province} {campagne} ({periode}) pour un total {total['campagne']} "
                    f"({total['periode']})"
                )
        return "; ".join(detail), ecarts

    def _controler(self, total: pd.Series, membres: list[str]) -> None:
        valeur = float(total["valeur"])
        somme = sum(float(self.attribuees[p]["valeur"]) for p in membres if p in self.attribuees)  # type: ignore[arg-type]
        ecart = abs(somme - valeur) / valeur if valeur else abs(somme)
        self.controles.append(
            {
                "niveau": total["niveau"],
                "code_zone": total["code_zone"],
                "code_culture": self.culture,
                "campagne": self.campagne,
                "variable": self.variable,
                "total": valeur,
                "somme_provinces": somme,
                "ecart_relatif": ecart,
                "conforme": ecart <= self.tolerance,
            }
        )
        if ecart > self.tolerance:
            self.incoherences.append(
                f"{total['niveau']} {total['code_zone']} ({self.contexte}) : somme des provinces "
                f"{somme:.0f} pour un total de {valeur:.0f}"
            )


def _retenir(observations: pd.DataFrame, ecartees: list[str]) -> pd.DataFrame:
    """Une observation par zone : la réalisée si elle existe, sinon la prévisionnelle."""
    cle = ["variable", "code_culture", "campagne", "niveau", "code_zone", "codes_provinces"]
    triees = observations.sort_values([*cle, "previsionnel", "ligne"], kind="stable")
    retenues = triees.drop_duplicates(cle, keep="first")
    for _, ligne in triees.drop(retenues.index).iterrows():
        if ligne["previsionnel"]:
            ecartees.append(
                f"{ligne['source_id']} · {ligne['document']} ligne {ligne['ligne']} : prévision "
                f"écartée, une valeur réalisée existe ({ligne['niveau']} {ligne['code_zone']}, "
                f"{ligne['code_culture']}, {ligne['campagne']})"
            )
    return retenues


def desagreger(
    observations: pd.DataFrame,
    surfaces: pd.DataFrame,
    provinces: pd.DataFrame,
    tolerance: float,
) -> ResultatDesagregation:
    """Valeurs provinciales de chaque grandeur, culture et campagne selon la RG-04.

    Args:
        observations: observations au format de :mod:`src.data.observations` (sans doublon).
        surfaces: ``code_province``, ``code_culture``, ``surface_ha`` (CROPGRIDS).
        provinces: ``code_province`` et ``code_region`` des 75 provinces.
        tolerance: écart relatif admis entre la somme des provinces et le total parent.
    """
    ecartees: list[str] = []
    retenues = _retenir(observations, ecartees)
    region_de = provinces.set_index("code_province")["code_region"].astype(str)
    toutes = list(region_de.index)
    lignes: list[dict[str, object]] = []
    controles: list[dict[str, object]] = []
    incoherences: list[str] = []
    ecarts_campagne: list[str] = []
    for (variable, culture, campagne), groupe in retenues.groupby(
        ["variable", "code_culture", "campagne"], sort=True
    ):
        surfaces_culture = surfaces[surfaces["code_culture"] == culture].set_index("code_province")[
            "surface_ha"
        ]
        calcul = _Calcul(
            str(variable), str(culture), str(campagne), surfaces_culture, region_de, tolerance
        )
        provinciales = groupe[groupe["niveau"] == Niveau.PROVINCE]
        simples = provinciales[~provinciales["codes_provinces"].str.contains(SEPARATEUR_CODES)]
        for _, ligne in simples.iterrows():
            calcul.connue(str(ligne["codes_provinces"] or ligne["code_zone"]), ligne)
        for _, ligne in provinciales.drop(simples.index).iterrows():
            calcul.repartir(ligne, str(ligne["codes_provinces"]).split(SEPARATEUR_CODES))
        for _, ligne in groupe[groupe["niveau"] == Niveau.REGION].iterrows():
            membres = [p for p in toutes if region_de[p] == str(ligne["code_zone"])]
            calcul.repartir(ligne, membres)
        for _, ligne in groupe[groupe["niveau"] == Niveau.NATIONAL].iterrows():
            calcul.repartir(ligne, toutes)
        lignes += calcul.attribuees.values()
        controles += calcul.controles
        incoherences += calcul.incoherences
        ecarts_campagne += calcul.ecarts_campagne
    production = pd.DataFrame(lignes, columns=COLONNES_PRODUCTION)
    production = production.sort_values(
        ["variable", "code_culture", "campagne", "code_province"], ignore_index=True
    )
    return ResultatDesagregation(
        production,
        pd.DataFrame(controles, columns=COLONNES_CONTROLES),
        incoherences,
        ecartees,
        ecarts_campagne,
    )
