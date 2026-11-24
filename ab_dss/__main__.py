"""Lance l'outil : ``python -m ab_dss`` démarre l'API locale et ouvre le navigateur."""

import argparse
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

HOTE = "127.0.0.1"
PORT_PAR_DEFAUT = 8000
DELAI_ATTENTE_S = 15


def _lire_arguments(arguments: list[str] | None) -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        prog="python -m ab_dss",
        description="Outil d'aide à la décision Atlantic Biochar : démarre l'interface locale.",
    )
    analyseur.add_argument("--port", type=int, default=PORT_PAR_DEFAUT, help="port local")
    analyseur.add_argument(
        "--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur"
    )
    return analyseur.parse_args(arguments)


def _port_disponible(port: int) -> bool:
    with socket.socket() as s:
        # Comme Uvicorn : un port en TIME_WAIT (connexions récemment fermées) reste utilisable.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOTE, port))
        except OSError:
            return False
    return True


def _ouvrir_quand_pret(adresse: str) -> None:
    debut = time.monotonic()
    while time.monotonic() - debut < DELAI_ATTENTE_S:
        try:
            with urllib.request.urlopen(f"{adresse}/api/sante", timeout=1):
                webbrowser.open(adresse)
                return
        except OSError:
            time.sleep(0.2)


def main(arguments: list[str] | None = None) -> int:
    """Démarre le serveur local ; renvoie le code de sortie."""
    options = _lire_arguments(arguments)
    if not _port_disponible(options.port):
        print(
            f"Le port {options.port} est déjà utilisé, peut-être par une autre instance de "
            f"l'outil. Fermez-la ou choisissez un autre port : python -m ab_dss --port "
            f"{options.port + 1}",
            file=sys.stderr,
        )
        return 1

    adresse = f"http://{HOTE}:{options.port}"
    print(f"Atlantic Biochar · outil disponible sur {adresse} (Ctrl+C pour arrêter)")
    if not options.sans_navigateur:
        threading.Thread(target=_ouvrir_quand_pret, args=(adresse,), daemon=True).start()

    uvicorn.run(
        "api.app:creer_app", factory=True, host=HOTE, port=options.port, log_level="warning"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
