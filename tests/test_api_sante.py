"""Tests du squelette de l'API : santé, erreurs en français (ENF-12), service de l'interface."""

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import creer_app


def test_sante_repond() -> None:
    client = TestClient(creer_app())
    reponse = client.get("/api/sante")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["statut"] == "ok"
    assert corps["version_outil"]
    assert isinstance(corps["donnees_preparees"], bool)


def test_route_api_inconnue_message_francais() -> None:
    client = TestClient(creer_app())
    reponse = client.get("/api/route-qui-n-existe-pas")
    assert reponse.status_code == 404
    assert "introuvable" in reponse.json()["erreur"]


def test_exception_interne_sans_trace_python() -> None:
    app = creer_app()

    @app.get("/api/test-panne")
    def panne() -> None:
        raise RuntimeError("détail interne à ne pas montrer")

    client = TestClient(app, raise_server_exceptions=False)
    reponse = client.get("/api/test-panne")
    assert reponse.status_code == 500
    texte = reponse.text
    assert "Traceback" not in texte
    assert "RuntimeError" not in texte
    assert "détail interne" not in texte
    assert "erreur interne" in reponse.json()["erreur"]


def test_validation_message_francais() -> None:
    app = creer_app()

    @app.get("/api/test-entier")
    def entier(n: int) -> dict[str, int]:
        return {"n": n}

    client = TestClient(app)
    reponse = client.get("/api/test-entier", params={"n": "abc"})
    assert reponse.status_code == 422
    assert "invalide" in reponse.json()["erreur"]


def test_interface_servie_avec_repli_spa(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    client = TestClient(creer_app(dossier_interface=tmp_path))

    assert 'id="root"' in client.get("/").text
    # Une route de l'interface (React Router) renvoie index.html
    assert 'id="root"' in client.get("/donnees").text
    assert client.get("/assets/app.js").status_code == 200


def test_interface_absente_message_explicite(tmp_path: Path) -> None:
    client = TestClient(creer_app(dossier_interface=tmp_path / "absent"))
    reponse = client.get("/")
    assert reponse.status_code == 503
    assert "npm run build" in reponse.text
