"""Fabrique de l'application FastAPI : routes sous ``/api`` et service de l'interface compilée."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from api.erreurs import ServiceInterface, installer_gestionnaires
from api.routes import (
    acv,
    decision,
    demo,
    donnees,
    entreprise,
    exports,
    logistique,
    parametres,
    potentiel,
    referentiel,
    sante,
    scenarios,
)

DOSSIER_INTERFACE = Path(__file__).resolve().parents[1] / "frontend" / "dist"

PAGE_INTERFACE_ABSENTE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Interface non compilée</title></head>
<body><h1>L'interface n'est pas compilée</h1>
<p>Le dossier <code>frontend/dist/</code> est introuvable. Compilez l'interface :</p>
<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p>puis relancez <code>python -m ab_dss</code>.</p></body></html>"""


def _service_interface(dossier: Path) -> ServiceInterface:
    """Construit la fonction qui sert l'interface pour tout chemin hors ``/api``."""
    racine = dossier.resolve()
    index = racine / "index.html"

    def servir(request: Request) -> Response | None:
        chemin = request.url.path
        if chemin == "/api" or chemin.startswith("/api/") or request.method not in {"GET", "HEAD"}:
            return None
        if not index.is_file():
            return HTMLResponse(PAGE_INTERFACE_ABSENTE, status_code=503)
        fichier = (racine / chemin.lstrip("/")).resolve()
        if fichier.is_file() and fichier.is_relative_to(racine):
            return FileResponse(fichier)
        # Repli SPA : les routes de l'interface sont gérées par React Router.
        return FileResponse(index)

    return servir


def creer_app(dossier_interface: Path = DOSSIER_INTERFACE) -> FastAPI:
    """Crée l'application : API locale sous ``/api`` et interface React à la racine.

    L'interface est servie par le gestionnaire des erreurs 404 : toute adresse hors ``/api``
    sans route renvoie un fichier de ``frontend/dist`` ou, à défaut, ``index.html``.
    """
    app = FastAPI(
        title="Atlantic Biochar · Outil d'aide à la décision",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    for module in (
        sante,
        entreprise,
        parametres,
        scenarios,
        demo,
        referentiel,
        donnees,
        potentiel,
        logistique,
        acv,
        decision,
        exports,
    ):
        app.include_router(module.routeur, prefix="/api")
    installer_gestionnaires(app, service_interface=_service_interface(dossier_interface))
    return app
