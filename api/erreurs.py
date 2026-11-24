"""Traduction des erreurs en messages français, sans trace Python visible (ENF-12)."""

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

journal = logging.getLogger("ab_dss.api")

ServiceInterface = Callable[[Request], Response | None]
"""Renvoie la réponse de l'interface pour une adresse hors ``/api``, ou ``None``."""

MESSAGES_HTTP = {
    404: "Ressource introuvable : vérifiez l'adresse demandée.",
    405: "Méthode non autorisée pour cette adresse.",
}

MESSAGE_INTERNE = (
    "Une erreur interne est survenue. Relancez l'opération ; si le problème persiste, "
    "consultez le journal affiché dans le terminal où l'outil a été lancé."
)


def _corps(message: str) -> dict[str, str]:
    return {"erreur": message}


def _message_http(exc: StarletteHTTPException) -> str:
    detail = exc.detail if isinstance(exc.detail, str) else None
    # Les messages par défaut de Starlette sont en anglais (« Not Found ») : on les remplace.
    if detail is None or detail == HTTPStatus(exc.status_code).phrase:
        message = MESSAGES_HTTP.get(exc.status_code, "La requête n'a pas pu aboutir.")
    else:
        message = detail
    return message


async def _erreur_validation(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    champs = sorted({".".join(str(p) for p in e["loc"][1:]) or "requête" for e in exc.errors()})
    message = f"Donnée invalide pour : {', '.join(champs)}. Corrigez la saisie puis réessayez."
    return JSONResponse(_corps(message), status_code=422)


async def _erreur_interne(_: Request, exc: Exception) -> JSONResponse:
    journal.exception("Erreur interne", exc_info=exc)
    return JSONResponse(_corps(MESSAGE_INTERNE), status_code=500)


def _erreurs_metier() -> dict[type[Exception], int]:
    """Exceptions métier de ``src/`` et code HTTP de chacune ; leur message est déjà en français."""
    from src.data.cropgrids import ErreurCropgrids
    from src.data.excel import ErreurImport
    from src.data.observations import ErreurPreparation
    from src.data.provenance import ValeurACompleter
    from src.data.provinces import ErreurRattachement, ErreurReferentiel
    from src.data.saisie import ConfirmationRequise, ErreurSaisie
    from src.data.surfaces import ErreurSurfaces
    from src.data.tables_reference import ErreurTable
    from src.data.versions import ErreurVersion
    from src.lecture_yaml import ErreurConfiguration
    from src.scenarios.demo import ErreurDemo
    from src.scenarios.entreprise import ErreurEntreprise
    from src.scenarios.parametres import ErreurParametre
    from src.scenarios.scenarios import ErreurScenario

    return {
        ConfirmationRequise: HTTPStatus.CONFLICT,
        ErreurRattachement: HTTPStatus.UNPROCESSABLE_ENTITY,
        ValeurACompleter: HTTPStatus.CONFLICT,
        ErreurSaisie: HTTPStatus.BAD_REQUEST,
        ErreurImport: HTTPStatus.BAD_REQUEST,
        ErreurVersion: HTTPStatus.BAD_REQUEST,
        ErreurEntreprise: HTTPStatus.BAD_REQUEST,
        ErreurParametre: HTTPStatus.BAD_REQUEST,
        ErreurScenario: HTTPStatus.BAD_REQUEST,
        ErreurDemo: HTTPStatus.BAD_REQUEST,
        ErreurPreparation: HTTPStatus.SERVICE_UNAVAILABLE,
        ErreurReferentiel: HTTPStatus.SERVICE_UNAVAILABLE,
        ErreurCropgrids: HTTPStatus.SERVICE_UNAVAILABLE,
        ErreurSurfaces: HTTPStatus.SERVICE_UNAVAILABLE,
        ErreurTable: HTTPStatus.SERVICE_UNAVAILABLE,
        ErreurConfiguration: HTTPStatus.SERVICE_UNAVAILABLE,
    }


def _gestionnaire_metier(code: int) -> Callable[[Request, Exception], Awaitable[Response]]:
    async def gerer(_: Request, exc: Exception) -> Response:
        corps: dict[str, object] = dict(_corps(str(exc)))
        if code == HTTPStatus.CONFLICT and exc.__class__.__name__ == "ConfirmationRequise":
            corps["confirmation_requise"] = True
        return JSONResponse(corps, status_code=code)

    return gerer


def installer_gestionnaires(app: FastAPI, service_interface: ServiceInterface) -> None:
    """Branche les gestionnaires d'erreurs français sur l'application.

    Une adresse sans route hors ``/api`` est confiée à ``service_interface`` (interface React).
    """

    async def erreur_http(request: Request, exc: Exception) -> Response:
        assert isinstance(exc, StarletteHTTPException)
        if exc.status_code == HTTPStatus.NOT_FOUND:
            reponse = service_interface(request)
            if reponse is not None:
                return reponse
        return JSONResponse(_corps(_message_http(exc)), status_code=exc.status_code)

    app.add_exception_handler(StarletteHTTPException, erreur_http)
    app.add_exception_handler(RequestValidationError, _erreur_validation)
    for classe, code in _erreurs_metier().items():
        app.add_exception_handler(classe, _gestionnaire_metier(code))
    app.add_exception_handler(Exception, _erreur_interne)
