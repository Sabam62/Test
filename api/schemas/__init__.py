"""Schémas pydantic des requêtes et réponses de l'API (validation des entrées)."""

from pydantic import BaseModel, ConfigDict, Field

from src.scenarios.scenarios import Site


class _Requete(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Signature(_Requete):
    """Auteur et commentaire d'une modification (UC-DAT-08)."""

    auteur: str = Field(min_length=1)
    commentaire: str = Field(min_length=1)


class MiseAJourEntreprise(_Requete):
    """Valeurs saisies sur la page « Paramètres de l'entreprise »."""

    auteur: str = Field(min_length=1)
    valeurs: dict[str, float | str | dict[str, list[str]] | None]


class ReglageParametre(_Requete):
    """Réglage d'un paramètre technique (UC-SCN-01)."""

    valeur: float | str
    source: str
    auteur: str


class NouveauScenario(_Requete):
    """Enregistrement de l'état courant comme scénario (UC-SCN-02)."""

    nom: str = Field(min_length=1)
    auteur: str = Field(min_length=1)
    criteres_actifs: list[str] = []
    seuils: dict[str, float] = {}
    poids: dict[str, float] = {}
    methode: str | None = None
    sites: list[Site] = []
    remplacer: bool = False


class Auteur(_Requete):
    """Auteur d'une opération sans commentaire."""

    auteur: str = Field(min_length=1)


class ValidationImport(Signature):
    """Validation d'un import Excel prévisualisé (UC-DAT-06)."""

    confirmees: list[int] = []


class Saisie(Signature):
    """Correction d'une valeur dans un tableau éditable (UC-DAT-07)."""

    cle: dict[str, str]
    valeur: str
    source: str
    date: str
    confirmer: bool = False


class PrixObserve(_Requete):
    """Prix observé saisi sur l'écran « Prix et coûts » (UC-DAT-07)."""

    date: str
    produit: str
    code_province: str
    prix: str
    unite: str
    source: str
    auteur: str = Field(min_length=1)
    note: str = ""
    confirmer: bool = False
