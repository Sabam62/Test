#!/usr/bin/env bash
# Préparation du graphe routier OSRM sur l'extrait OpenStreetMap du Maroc (SRC-06, SRC-07).
#
# Une seule fois, ou après un nouvel extrait : extraction (profil voiture), partition et
# personnalisation (algorithme MLD), dans data/osrm/. Image multi-architecture officielle
# ghcr.io/project-osrm/osrm-backend (arm64 et amd64).
#
# Utilisation : bash scripts/osrm_setup.sh          préparer le graphe
#               bash scripts/osrm_setup.sh --serveur démarrer le service sur le port 5001 (AB_DSS_OSRM_PORT)
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="ghcr.io/project-osrm/osrm-backend:v6.0.0"
PBF="$RACINE/data/raw/SRC-06/morocco-latest.osm.pbf"
DOSSIER="$RACINE/data/osrm"
NOM="morocco-latest"
CONTENEUR="ab-dss-osrm"
# Port local (5000 est pris par AirPlay sous macOS) ; doit égaler osrm.url de config/logistique.yaml.
PORT="${AB_DSS_OSRM_PORT:-5001}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker est introuvable : installez Docker Desktop, ou utilisez le repli à vol d'oiseau." >&2
  exit 1
fi

if [[ "${1:-}" == "--serveur" ]]; then
  if [[ ! -f "$DOSSIER/$NOM.osrm.mldgr" ]]; then
    echo "Graphe absent : lancez d'abord « bash scripts/osrm_setup.sh »." >&2
    exit 1
  fi
  docker rm -f "$CONTENEUR" >/dev/null 2>&1 || true
  docker run -d --name "$CONTENEUR" -p "$PORT:5000" -v "$DOSSIER:/data" "$IMAGE" \
    osrm-routed --algorithm mld --max-table-size 10000 "/data/$NOM.osrm"
  echo "OSRM écoute sur http://localhost:$PORT (conteneur $CONTENEUR)."
  exit 0
fi

if [[ ! -f "$PBF" ]]; then
  echo "Extrait absent : $PBF. Lancez « python -m scripts.download »." >&2
  exit 1
fi
mkdir -p "$DOSSIER"
if [[ ! -f "$DOSSIER/$NOM.osm.pbf" ]]; then
  cp "$PBF" "$DOSSIER/$NOM.osm.pbf"
fi
docker run --rm -t -v "$DOSSIER:/data" "$IMAGE" \
  osrm-extract -p /opt/car.lua "/data/$NOM.osm.pbf"
docker run --rm -t -v "$DOSSIER:/data" "$IMAGE" osrm-partition "/data/$NOM.osrm"
docker run --rm -t -v "$DOSSIER:/data" "$IMAGE" osrm-customize "/data/$NOM.osrm"
echo "Graphe prêt dans $DOSSIER. Démarrer le service : bash scripts/osrm_setup.sh --serveur"
