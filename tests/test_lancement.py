"""UC-00 : `python -m ab_dss` ouvre l'accueil en moins de 10 s."""

import socket
import subprocess
import sys
import time

import httpx
import pytest

DELAI_MAX_S = 10


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.lent
def test_lancement_sert_l_accueil_en_moins_de_10_s() -> None:
    port = _port_libre()
    debut = time.monotonic()
    processus = subprocess.Popen(
        [sys.executable, "-m", "ab_dss", "--sans-navigateur", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        reponse = None
        while time.monotonic() - debut < DELAI_MAX_S:
            try:
                reponse = httpx.get(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except httpx.TransportError:
                time.sleep(0.1)
        assert reponse is not None, "l'accueil n'a pas répondu en moins de 10 s"
        assert reponse.status_code == 200
        assert 'id="root"' in reponse.text
    finally:
        processus.terminate()
        processus.wait(timeout=10)


def test_port_occupe_message_francais() -> None:
    with socket.socket() as occupe:
        occupe.bind(("127.0.0.1", 0))
        occupe.listen()
        port = occupe.getsockname()[1]
        resultat = subprocess.run(
            [sys.executable, "-m", "ab_dss", "--sans-navigateur", "--port", str(port)],
            capture_output=True,
            text=True,
            timeout=20,
        )
    assert resultat.returncode != 0
    assert "déjà utilisé" in resultat.stderr
    assert "Traceback" not in resultat.stderr
