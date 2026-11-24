"""Gisement théorique T de chaque province × résidu (section 8.1, UC-POT-01).

T = Σ sur les cultures du résidu de (Q × RPR, ou S × Y, ou N × Y^pied) × (1 − h)^δ_r :

- la grandeur de production (Q en t, S en ha) vient de la table ``production`` (RG-04) ;
- N = S × densité de plantation de secours, statut « Estimée », faute de nombre de pieds ;
- δ_r = 1 si le ratio est exprimé en masse brute, 0 s'il l'est en matière sèche : (1 − h)
  n'est jamais appliqué à une valeur déjà en t MS ;
- les précisions de ``residus.csv`` sont résolues selon leur rôle (``config/potentiel.yaml``) :
  culture, variante choisie par un paramètre (PAR-62, PAR-63), région, secours, état ;
- les multiplicateurs propres à un résidu (part des olives triturées pour R05) s'appliquent.

La campagne de référence est la moyenne des N dernières campagnes disponibles de chaque
province, culture et grandeur (PAR-02). T est aussi calculé pour chaque campagne (variabilité).
Un couple dont une entrée manque est exclu et listé avec le motif (RG-06, RG-14) ; il n'est
jamais compté zéro.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pandas as pd

from src.data.provenance import Statut, ValeurACompleter, ValeurSourcee
from src.data.tables_reference import TableLongue, liste
from src.potentiel.config import ConfigPotentiel

CAMPAGNE_REFERENCE = "référence"
UNITE_GISEMENT = "t MS/an"
SEPARATEUR = "; "
COLONNES_T = [
    "code_province",
    "code_residu",
    "campagne",
    "valeur",
    "unite",
    "statut",
    "sources",
    "previsionnel",
    "campagnes",
    "note",
]
COLONNES_EXCLUS = ["code_province", "code_residu", "motif"]

LireParametre = Callable[[str], ValeurSourcee]


class Blocage(Exception):
    """Entrée manquante : le couple est exclu (RG-06) avec ce motif."""


@dataclass
class ResultatTheorique:
    """Gisement théorique par couple et campagne, et couples exclus."""

    gisements: pd.DataFrame
    exclus: pd.DataFrame
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Terme:
    """Valeur numérique d'une entrée et sa provenance réduite."""

    valeur: float
    statut: Statut
    source: str


def _terme(valeur: ValeurSourcee, facteur: float = 1) -> Terme:
    """Valeur lue (RG-14 : bloque si elle est à compléter), statut et source."""
    try:
        nombre = valeur.lire_nombre()
    except ValeurACompleter as erreur:
        raise Blocage(f"{erreur.nom} à compléter ; où la trouver : {erreur.ou_trouver}") from None
    provenance = valeur.provenance
    if provenance is None:
        raise Blocage(f"{valeur.nom} sans provenance (RG-03)")
    return Terme(nombre * facteur, provenance.statut, provenance.source_id)


def campagnes_reference(production: pd.DataFrame, nombre: int) -> pd.DataFrame:
    """Moyenne des ``nombre`` dernières campagnes disponibles par province, culture et grandeur.

    Returns:
        ``code_province``, ``code_culture``, ``variable``, ``valeur`` (moyenne), ``campagnes``
        (retenues, séparées par « ; »), ``previsionnel`` (une au moins l'est), ``statuts`` et
        ``sources`` (listes).
    """
    triee = production.sort_values("campagne", ascending=False)
    lignes = []
    for (province, culture, variable), groupe in triee.groupby(
        ["code_province", "code_culture", "variable"], sort=True
    ):
        retenues = groupe.head(nombre)
        lignes.append(
            {
                "code_province": province,
                "code_culture": culture,
                "variable": variable,
                "valeur": float(retenues["valeur"].mean()),
                "campagnes": SEPARATEUR.join(sorted(retenues["campagne"])),
                "previsionnel": bool(retenues["previsionnel"].any()),
                "statuts": [Statut(s) for s in retenues["statut"]],
                "sources": sorted(set(retenues["source_id"].dropna())),
            }
        )
    return pd.DataFrame(lignes)


@dataclass
class _Residu:
    """Entrées d'un résidu résolues une fois pour toutes les provinces."""

    code: str
    grandeur: str
    cultures: list[str]
    ratios: dict[str, Terme]
    humidite: Terme | None
    densite: Terme | None
    multiplicateurs: dict[str, dict[str, Terme]]
    statuts_fixes: list[Statut]
    regions_nommees: dict[str, str] = field(default_factory=dict)


def resoudre_variantes(
    residus: TableLongue, config: ConfigPotentiel, parametre: LireParametre
) -> TableLongue:
    """Table des résidus où chaque variante choisie devient la valeur générale du paramètre.

    Pour un paramètre de rôle « variante » (humidité et ratio des grignons selon PAR-62, des
    pulpes selon PAR-63), la ligne de la précision choisie est reprise sans précision et les
    autres variantes sont retirées : la logistique, le bilan climat, le mélange et la décision
    lisent ainsi la même valeur que le calcul des gisements. Sans choix (paramètre « À
    compléter ») ou si le choix n'a pas de ligne, la table est laissée telle quelle : le gisement
    du résidu est déjà bloqué, avec son motif.
    """
    retenues: dict[tuple[tuple[str, ...], str], str] = {}
    for role in config.precisions:
        if role.role != "variante":
            continue
        try:
            choix = str(parametre(role.choix_par or "").lire())
        except ValeurACompleter:
            continue
        if choix in residus.precisions(role.residu, role.parametre):
            retenues[((role.residu,), role.parametre)] = choix
    if not retenues:
        return residus
    lignes = []
    for ligne in residus.lignes:
        choix = retenues.get((ligne.cle, ligne.parametre))
        if choix is None:
            lignes.append(ligne)
        elif ligne.precision == choix:
            lignes.append(replace(ligne, precision=""))
    return replace(residus, lignes=tuple(lignes))


class CalculTheorique:
    """Calcul de T pour tous les résidus du catalogue."""

    def __init__(
        self,
        residus: TableLongue,
        codes_residus: list[str],
        ratio_par_mode: dict[str, str],
        config: ConfigPotentiel,
        parametre: LireParametre,
        region_de: dict[str, str],
        code_region: Callable[[str], str | None],
    ) -> None:
        """Prépare le calcul.

        Args:
            residus: table ``residus`` (version active).
            codes_residus: R01 à R13 (catalogue).
            ratio_par_mode: paramètre du ratio de chaque mode (catalogue des tables).
            config: ``config/potentiel.yaml``.
            parametre: valeur courante d'un paramètre technique (PAR-02, PAR-62, PAR-63).
            region_de: code de région de chaque province.
            code_region: code de région d'un nom de région (référentiel RG-02), ou None.
        """
        self.residus = residus
        self.codes = codes_residus
        self.ratio_par_mode = ratio_par_mode
        self.config = config
        self.parametre = parametre
        self.region_de = region_de
        self.code_region = code_region

    # --- Résolution des précisions -----------------------------------------------------

    def _precision(self, residu: str, parametre: str, culture: str | None = None) -> str:
        """Précision à lire pour un paramètre, selon son rôle ; Blocage si le choix manque."""
        role = self.config.role(residu, parametre)
        disponibles = self.residus.precisions(residu, parametre)
        if role is None:
            return ""
        if role.role == "culture":
            return culture if culture in disponibles else ""
        if role.role == "variante":
            choix = self.parametre(role.choix_par or "")
            try:
                retenue = str(choix.lire())
            except ValeurACompleter as erreur:
                raise Blocage(
                    f"{erreur.nom} à compléter ; où la trouver : {erreur.ou_trouver}"
                ) from None
            if retenue not in disponibles:
                raise Blocage(f"{residu} · {parametre} : aucune valeur pour « {retenue} »")
            return retenue
        if role.role in ("secours", "etat"):
            return disponibles[0] if disponibles else ""
        raise Blocage(f"{residu} · {parametre} : précision « {role.role} » non utilisable ici")

    def _valeur(self, residu: str, parametre: str, culture: str | None = None) -> ValeurSourcee:
        try:
            return self.residus.valeur(
                residu, parametre, self._precision(residu, parametre, culture)
            )
        except KeyError:
            raise Blocage(f"{residu} · {parametre} absent de residus.csv") from None

    def _residu(self, code: str) -> _Residu:
        mode = str(self.residus.valeur(code, "mode_calcul").lire())
        cultures = liste(self.residus.valeur(code, "codes_culture"))
        parametre_ratio = self.ratio_par_mode[mode]
        ratios: dict[str, Terme] = {}
        base = None
        for culture in cultures:
            valeur = self._valeur(code, parametre_ratio, culture)
            unite = self.config.unites_ratio.get(valeur.unite)
            if unite is None:
                raise Blocage(f"{valeur.nom} : unité « {valeur.unite} » inconnue")
            base = unite.base
            ratios[culture] = _terme(valeur, unite.facteur_tonne)
        humidite = None
        if base == "brute":
            valeur = self._valeur(code, "humidite")
            humidite = _terme(valeur, self._fraction(valeur))
        densite = None
        if mode == "nombre de pieds":
            densite = _terme(self._valeur(code, "densite_plantation"))
        multiplicateurs: dict[str, dict[str, Terme]] = {}
        noms: dict[str, str] = {}
        for parametre in self.config.multiplicateurs.get(code, []):
            multiplicateurs[parametre] = self._par_region(code, parametre)
            noms |= {str(self.code_region(p)): p for p in self.residus.precisions(code, parametre)}
        statuts = [t.statut for t in ratios.values()]
        statuts += [t.statut for t in (humidite, densite) if t is not None]
        if densite is not None:
            # N = S × densité : nombre de pieds estimé (section 8.1).
            statuts.append(Statut.ESTIMEE)
        return _Residu(
            code,
            self.config.grandeurs_par_mode[mode],
            cultures,
            ratios,
            humidite,
            densite,
            multiplicateurs,
            statuts,
            noms,
        )

    def _fraction(self, valeur: ValeurSourcee) -> float:
        facteur = self.config.unites_fraction.get(valeur.unite)
        if facteur is None:
            raise Blocage(f"{valeur.nom} : unité « {valeur.unite} » inconnue")
        return facteur

    def _par_region(self, residu: str, parametre: str) -> dict[str, Terme]:
        """Valeur d'un multiplicateur par code de région (précision régionale)."""
        par_region: dict[str, Terme] = {}
        for precision in self.residus.precisions(residu, parametre):
            code = self.code_region(precision)
            if code is None:
                raise Blocage(f"{residu} · {parametre} : région « {precision} » inconnue (RG-02)")
            valeur = self.residus.valeur(residu, parametre, precision)
            par_region[code] = _terme(valeur, self._fraction(valeur))
        return par_region

    # --- Calcul ------------------------------------------------------------------------

    def calculer(self, production: pd.DataFrame) -> ResultatTheorique:
        """T de chaque province × résidu, pour la campagne de référence et chaque campagne."""
        nombre = int(self.parametre(self.config.parametre_campagnes).lire_nombre())
        reference = campagnes_reference(production, nombre)
        par_cle = {(r.code_province, r.code_culture, r.variable): r for r in reference.itertuples()}
        annuelles = production.set_index(["code_province", "code_culture", "variable"]).sort_index()
        lignes: list[dict[str, object]] = []
        exclus: list[dict[str, object]] = []
        provinces = sorted(self.region_de)
        for code in self.codes:
            try:
                residu = self._residu(code)
            except Blocage as blocage:
                exclus += [
                    {"code_province": p, "code_residu": code, "motif": str(blocage)}
                    for p in provinces
                ]
                continue
            for province in provinces:
                try:
                    lignes += self._couple(residu, province, par_cle, annuelles)
                except Blocage as blocage:
                    exclus.append(
                        {"code_province": province, "code_residu": code, "motif": str(blocage)}
                    )
        return ResultatTheorique(
            pd.DataFrame(lignes, columns=COLONNES_T), pd.DataFrame(exclus, columns=COLONNES_EXCLUS)
        )

    def _facteur(self, residu: _Residu, province: str) -> tuple[float, list[Terme]]:
        """Produit (1 − h)^δ × densité × multiplicateurs, et les termes utilisés."""
        facteur, termes = 1.0, []
        if residu.humidite is not None:
            facteur *= 1 - residu.humidite.valeur
            termes.append(residu.humidite)
        if residu.densite is not None:
            facteur *= residu.densite.valeur
            termes.append(residu.densite)
        for parametre, par_region in residu.multiplicateurs.items():
            terme = par_region.get(self.region_de[province])
            if terme is None:
                connues = ", ".join(sorted(residu.regions_nommees.values())) or "aucune région"
                raise Blocage(
                    f"{residu.code} · {parametre} à compléter pour cette région (valeur sourcée "
                    f"pour {connues} seulement)"
                )
            facteur *= terme.valeur
            termes.append(terme)
        return facteur, termes

    def _couple(
        self,
        residu: _Residu,
        province: str,
        par_cle: dict[tuple[str, str, str], object],
        annuelles: pd.DataFrame,
    ) -> list[dict[str, object]]:
        facteur, termes = self._facteur(residu, province)
        manquantes = [c for c in residu.cultures if (province, c, residu.grandeur) not in par_cle]
        if manquantes:
            raise Blocage(
                f"{residu.grandeur} absente pour {', '.join(manquantes)} dans cette province "
                "(table production)"
            )
        statuts = list(residu.statuts_fixes) + [t.statut for t in termes]
        sources = {t.source for t in residu.ratios.values()} | {t.source for t in termes}
        total, campagnes, previsionnel = 0.0, set(), False
        for culture in residu.cultures:
            ref = par_cle[(province, culture, residu.grandeur)]
            total += ref.valeur * residu.ratios[culture].valeur  # type: ignore[attr-defined]
            statuts += ref.statuts  # type: ignore[attr-defined]
            sources |= set(ref.sources)  # type: ignore[attr-defined]
            campagnes |= set(ref.campagnes.split(SEPARATEUR))  # type: ignore[attr-defined]
            previsionnel |= ref.previsionnel  # type: ignore[attr-defined]
        lignes = [
            self._ligne(
                residu, province, CAMPAGNE_REFERENCE, total * facteur, statuts, sources,
                previsionnel, SEPARATEUR.join(sorted(campagnes)),
            )
        ]  # fmt: skip
        lignes += self._par_campagne(residu, province, facteur, termes, annuelles)
        return lignes

    def _par_campagne(
        self,
        residu: _Residu,
        province: str,
        facteur: float,
        termes: list[Terme],
        annuelles: pd.DataFrame,
    ) -> list[dict[str, object]]:
        """T de chaque campagne où toutes les cultures du résidu ont une valeur."""
        series = []
        for culture in residu.cultures:
            cle = (province, culture, residu.grandeur)
            if cle not in annuelles.index:
                return []
            series.append(annuelles.loc[[cle]].set_index("campagne"))
        communes = sorted(set.intersection(*(set(s.index) for s in series)))
        lignes = []
        for campagne in communes:
            total, statuts, sources, previsionnel = 0.0, [], set(), False
            for culture, serie in zip(residu.cultures, series, strict=True):
                ligne = serie.loc[campagne]
                total += float(ligne["valeur"]) * residu.ratios[culture].valeur
                statuts.append(Statut(ligne["statut"]))
                sources.add(str(ligne["source_id"]))
                previsionnel |= bool(ligne["previsionnel"])
            statuts += list(residu.statuts_fixes) + [t.statut for t in termes]
            sources |= {t.source for t in residu.ratios.values()} | {t.source for t in termes}
            lignes.append(
                self._ligne(
                    residu, province, campagne, total * facteur, statuts, sources,
                    previsionnel, campagne,
                )
            )  # fmt: skip
        return lignes

    def _ligne(
        self,
        residu: _Residu,
        province: str,
        campagne: str,
        valeur: float,
        statuts: list[Statut],
        sources: set[str],
        previsionnel: bool,
        campagnes: str,
    ) -> dict[str, object]:
        note = f"{residu.grandeur} × ratio"
        if residu.humidite is not None:
            note += " × (1 − humidité), ratio en masse brute"
        if residu.densite is not None:
            note += " × densité de plantation de secours (nombre de pieds estimé)"
        if residu.multiplicateurs:
            note += " × " + " × ".join(residu.multiplicateurs)
        return {
            "code_province": province,
            "code_residu": residu.code,
            "campagne": campagne,
            "valeur": valeur,
            "unite": UNITE_GISEMENT,
            "statut": self.config.moins_fiable(statuts).value,
            "sources": SEPARATEUR.join(sorted(sources)),
            "previsionnel": previsionnel,
            "campagnes": campagnes,
            "note": note,
        }
