# Préparation du graphe routier OSRM sur l'extrait OpenStreetMap du Maroc (SRC-06, SRC-07).
# Équivalent Windows (PowerShell) de scripts/osrm_setup.sh.
#
# Une seule fois, ou après un nouvel extrait : extraction (profil voiture), partition et
# personnalisation (algorithme MLD), dans data\osrm\. Image multi-architecture officielle
# ghcr.io/project-osrm/osrm-backend (arm64 et amd64). Docker Desktop doit être démarré.
#
# Utilisation (depuis le dossier du dépôt) :
#   powershell -ExecutionPolicy Bypass -File scripts\osrm_setup.ps1           préparer le graphe
#   powershell -ExecutionPolicy Bypass -File scripts\osrm_setup.ps1 -Serveur  démarrer le service
# Port : 5001 par défaut, ou la variable d'environnement AB_DSS_OSRM_PORT ; il doit égaler
# osrm.url de config\logistique.yaml.
param(
    [switch]$Serveur
)
$ErrorActionPreference = "Stop"

$Racine = Split-Path -Parent $PSScriptRoot
$Image = "ghcr.io/project-osrm/osrm-backend:v6.0.0"
# Join-Path imbriqués : séparateur natif du système (le chemin est passé tel quel à Docker).
$Donnees = Join-Path $Racine "data"
$Pbf = Join-Path (Join-Path (Join-Path $Donnees "raw") "SRC-06") "morocco-latest.osm.pbf"
$Dossier = Join-Path $Donnees "osrm"
$Nom = "morocco-latest"
$Conteneur = "ab-dss-osrm"
$Port = if ($env:AB_DSS_OSRM_PORT) { $env:AB_DSS_OSRM_PORT } else { "5001" }

function Arreter([string]$Message) {
    # Message lisible, sans la trace d'erreur de PowerShell, puis code de sortie 1.
    Write-Host $Message -ForegroundColor Red
    exit 1
}

function Lancer-Docker {
    # Arrête le script si une commande docker échoue ($ErrorActionPreference ne couvre pas
    # les programmes externes).
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        Arreter "La commande « docker $($args -join ' ') » a échoué (code $LASTEXITCODE)."
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Arreter "Docker est introuvable : installez Docker Desktop, ou utilisez le repli à vol d'oiseau."
}
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Arreter "Docker Desktop n'est pas démarré : lancez-le, attendez « Engine running », puis relancez."
}

if ($Serveur) {
    if (-not (Test-Path (Join-Path $Dossier "$Nom.osrm.mldgr"))) {
        Arreter "Graphe absent : lancez d'abord « powershell -ExecutionPolicy Bypass -File scripts\osrm_setup.ps1 »."
    }
    & docker rm -f $Conteneur *> $null
    Lancer-Docker run -d --name $Conteneur -p "${Port}:5000" -v "${Dossier}:/data" $Image `
        osrm-routed --algorithm mld --max-table-size 10000 "/data/$Nom.osrm"
    Write-Host "OSRM écoute sur http://localhost:$Port (conteneur $Conteneur)."
    exit 0
}

if (-not (Test-Path $Pbf)) {
    Arreter "Extrait absent : $Pbf. Lancez « python -m scripts.download »."
}
New-Item -ItemType Directory -Force -Path $Dossier | Out-Null
$Copie = Join-Path $Dossier "$Nom.osm.pbf"
if (-not (Test-Path $Copie)) {
    Copy-Item $Pbf $Copie
}
Lancer-Docker run --rm -t -v "${Dossier}:/data" $Image osrm-extract -p /opt/car.lua "/data/$Nom.osm.pbf"
Lancer-Docker run --rm -t -v "${Dossier}:/data" $Image osrm-partition "/data/$Nom.osrm"
Lancer-Docker run --rm -t -v "${Dossier}:/data" $Image osrm-customize "/data/$Nom.osrm"
Write-Host "Graphe prêt dans $Dossier. Démarrer le service : powershell -ExecutionPolicy Bypass -File scripts\osrm_setup.ps1 -Serveur"
