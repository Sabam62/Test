"""Entrées du bilan climat (section 8.3) : facteurs, données d'activité, propriétés des résidus.

Chaque entrée est un :class:`Terme` (nombre, statut, source) ou, si elle manque, le motif qui dit
quelle valeur saisir et où (RG-14) ; un bilan qui en dépend est bloqué, jamais calculé avec zéro.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from src.acv.config import ConfigAcv
from src.data.provenance import ValeurACompleter, ValeurSourcee
from src.data.tables_reference import TableLongue
from src.logistique.couts import Blocage, Terme, terme

Entree = Terme | str  # nombre sourcé, ou motif de blocage


def _lire(lecture: Callable[[], ValeurSourcee], facteur: float = 1) -> Entree:
    try:
        return terme(lecture(), facteur)
    except (Blocage, ValeurACompleter) as erreur:
        return str(erreur)
    except KeyError as erreur:
        return f"{erreur.args[0] if erreur.args else erreur} absent"


@dataclass(frozen=True)
class ProprietesResidu:
    """Propriétés d'un résidu utiles au bilan."""

    rendement: Entree  # y, t biochar / t MS
    carbone_biochar: Entree  # C_bc, fraction
    scenario: str | None  # scénario de référence (choix de residus.csv), None si à compléter
    motif_scenario: str | None
    pci: Entree  # MJ/kg, pour l'usage concurrent
    humidite: Entree  # fraction de la masse brute
    densite: Entree  # t/m³


@dataclass(frozen=True)
class EntreesAcv:
    """Toutes les entrées du bilan, lues dans leur version active et dans config/."""

    facteurs: dict[str, dict[str, Entree]]  # activité d'arrière-plan → paramètre → valeur
    activites: dict[str, Entree]  # données d'activité de config/acv.yaml
    prg: dict[str, Entree]  # flux → PRG100 (kg CO₂e/kg)
    classe: str | None
    permanence: Entree  # F_perm
    consommation_camion: Entree  # L/km
    charge_camion: Entree  # t
    volume_camion: Entree  # m³
    residus: dict[str, ProprietesResidu] = field(default_factory=dict)


def _precision_unique(residus: TableLongue, code: str) -> str:
    """Précision de l'humidité : la valeur générale, sinon la seule valeur disponible (état)."""
    precisions = residus.precisions(code, "humidite")
    return "" if "" in precisions or len(precisions) != 1 else precisions[0]


def classe_temperature(valeur: object, config: ConfigAcv) -> str | None:
    """Classe de température du GIEC pour PAR-21 (°C ou nom de classe) ; None hors classes."""
    if isinstance(valeur, str):
        return valeur if valeur in config.classes_temperature else None
    if not isinstance(valeur, int | float):
        return None
    retenue = None
    for nom, minimum in sorted(config.classes_temperature.items(), key=lambda x: x[1]):
        if valeur >= minimum:
            retenue = nom
    return retenue


def _carbone_biochar(
    residus: TableLongue, code: str, classe: str | None, config: ConfigAcv, facteur: float
) -> Entree:
    """C_bc : valeur mesurée à la température de la classe choisie, sinon valeur générale."""
    precisions = residus.precisions(code, "carbone_biochar")
    if not precisions:
        return f"{code} · carbone_biochar absent de residus.csv"
    for precision in precisions:
        if precision and config.precisions_carbone_biochar.get(precision) == classe:
            return _lire(lambda p=precision: residus.valeur(code, "carbone_biochar", p), facteur)
    if "" in precisions:
        generale = _lire(lambda: residus.valeur(code, "carbone_biochar"), facteur)
        if isinstance(generale, Terme):
            return generale
    mesurees = [p for p in precisions if p]
    detail = f" (mesurée seulement : {', '.join(mesurees)})" if mesurees else ""
    return (
        f"{code} · carbone_biochar à compléter pour la classe de température "
        f"« {classe or 'non choisie'} »{detail} ; où la trouver : littérature (SRC-16) ou "
        "analyse du biochar produit"
    )


def charger_entrees_acv(
    residus: TableLongue,
    facteurs: TableLongue,
    codes_residus: list[str],
    lire: Callable[[str], ValeurSourcee],
    config: ConfigAcv,
    unites_fraction: dict[str, float],
) -> EntreesAcv:
    """Lit les entrées du bilan.

    Args:
        residus: ``residus.csv`` actif.
        facteurs: ``facteurs_emission.csv`` actif.
        codes_residus: codes des résidus du catalogue.
        lire: valeur d'un paramètre (entreprise, sinon technique), voir
            :func:`src.logistique.calcul.lecteur_parametres`.
        config: ``config/acv.yaml``.
        unites_fraction: conversions des unités en fraction (``config/potentiel.yaml``).
    """
    libelles = {cle[0]: cle for cle in (ligne.cle for ligne in facteurs.lignes)}

    def facteur(activite: str, parametre: str) -> Entree:
        cle = libelles.get(activite)
        if cle is None:
            return f"{activite} absent de facteurs_emission.csv"
        return _lire(lambda: facteurs.valeur(cle, parametre))

    tableau = {
        activite: {
            p: facteur(activite, p) for p in [*definition.echanges, *definition.multiplicateurs]
        }
        for activite, definition in config.arriere_plan.items()
    }
    activites = {nom: facteur(a, p) for nom, (a, p) in config.activites.items()}
    prg = {nom: _lire(lambda f=flux: lire(f.prg)) for nom, flux in config.flux.items()}
    p = config.parametres
    temperature = lire(p.temperature)
    classe = (
        classe_temperature(temperature.valeur, config) if temperature.valeur is not None else None
    )
    if temperature.valeur is None:
        permanence: Entree = f"{temperature.nom} à renseigner ; où : {temperature.ou_trouver}"
    elif classe is None:
        permanence = (
            f"{temperature.nom} = {temperature.valeur} : hors des classes de température du GIEC "
            f"(à partir de {min(config.classes_temperature.values()):g} °C)"
        )
    else:
        permanence = _lire(lambda: lire(f"{p.permanence}:{classe}"))
    proprietes = {}
    for code in codes_residus:
        scenario_valeur = residus.valeur(code, "scenario_reference")
        scenario = str(scenario_valeur.valeur) if scenario_valeur.valeur is not None else None
        proprietes[code] = ProprietesResidu(
            rendement=_lire(lambda c=code: residus.valeur(c, "rendement_pyrolyse")),
            carbone_biochar=_carbone_biochar(
                residus, code, classe, config, unites_fraction.get("% biochar", 1)
            ),
            scenario=scenario,
            motif_scenario=(
                None
                if scenario
                else f"{code} · scenario_reference à compléter ; où : "
                f"{scenario_valeur.ou_trouver or 'residus.csv'}"
            ),
            pci=_lire(lambda c=code: residus.valeur(c, "pci")),
            humidite=_lire(
                lambda c=code: residus.valeur(c, "humidite", _precision_unique(residus, c)),
                unites_fraction.get("% masse brute", 1),
            ),
            densite=_lire(
                lambda c=code: residus.valeur(c, "densite_apparente"), 1 / config.kg_par_tonne
            ),
        )
    return EntreesAcv(
        facteurs=tableau,
        activites=activites,
        prg=prg,
        classe=classe,
        permanence=permanence,
        consommation_camion=_lire(
            lambda: lire(p.consommation_camion), 1 / config.litres_par_100_km
        ),
        charge_camion=_lire(lambda: lire(p.charge_camion)),
        volume_camion=_lire(lambda: lire(p.volume_camion)),
        residus=proprietes,
    )
