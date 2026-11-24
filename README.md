# Atlantic Biochar · Outil d'aide à la décision

Outil local qui classe les gisements de biomasse et les sites d'implantation d'unités de biochar
au Maroc. La spécification de référence est [docs/cahier_des_charges.md](docs/cahier_des_charges.md).

> Outil complet (MVP, lots 1 à 6 du cahier des charges) : données réelles des 75 provinces,
> gisements, logistique (OSRM), bilan climat (Brightway), décision multicritère, mélange optimal,
> fiche site et exports. Plusieurs valeurs restent à saisir par l'entreprise pour que tous les
> critères soient calculés : voir « Données à saisir par l'entreprise » ci-dessous.

## Installation (macOS, Linux)

Sous Windows, suivez plutôt « Installation sous Windows » ci-dessous.

Prérequis : [Miniforge](https://github.com/conda-forge/miniforge), recommandé pour toute l'équipe.
Node.js n'est nécessaire que pour modifier l'interface.

```bash
brew install --cask miniforge     # macOS ; autres systèmes : voir le lien ci-dessus
conda init "$(basename "$SHELL")" # puis ouvrir un nouveau terminal
```

Miniforge n'utilise que le canal conda-forge, comme `environment.yml` (`nodefaults`) : aucune
condition d'utilisation d'Anaconda n'est à accepter. Pour créer l'environnement et le vérifier :

```bash
conda env create -f environment.yml
conda activate ab-dss
python -c "import bw2data, bw2calc, geopandas, fastapi; print('OK')"
```

**Dernier recours, si vous gardez Miniconda ou Anaconda.** Leur greffon `conda-anaconda-tos`
vérifie les canaux de votre configuration *avant* de lire `environment.yml`. Si votre `.condarc`
contient le canal `defaults` sans que ses conditions soient acceptées, la commande échoue avec
`CondaToSNonInteractiveError`, même si le projet n'utilise pas ce canal. Redirigez alors
`defaults` vers conda-forge pour cette seule commande :

```bash
CONDA_DEFAULT_CHANNELS=https://conda.anaconda.org/conda-forge conda env create -f environment.yml
```

## Démarrage en un clic (Windows)

Prérequis : installez [Miniforge](https://github.com/conda-forge/miniforge) une seule fois. Une fois ce dépôt présent sur l’ordinateur, double-cliquez sur **`Lancer Atlantic Biochar.bat`**.

Au premier lancement, ce bouton crée l’environnement Python, télécharge les données nécessaires (environ 1,1 Go), prépare les fichiers, puis démarre l’application et ouvre le navigateur sur <http://127.0.0.1:8000>. Laissez la fenêtre ouverte pendant cette préparation. Les lancements suivants ouvrent directement l’application. Une connexion Internet est nécessaire pour la première préparation.

Les distances routières OSRM et Docker sont facultatifs : sans eux, l’outil utilise les distances en cache ou une estimation à vol d’oiseau et l’indique dans l’écran Sites. Pour utiliser OSRM, suivez `scripts/osrm_setup.ps1`.
## Utilisation

```bash
python -m scripts.download          # télécharge les sources ouvertes dans data/raw/
python -m scripts.prepare           # prépare data/processed/ et le rapport de contrôle
bash scripts/osrm_setup.sh          # une seule fois : graphe routier du Maroc (Docker)
```

À chaque démarrage :

```bash
bash scripts/osrm_setup.sh --serveur   # routage OSRM sur http://localhost:5001
python -m ab_dss                       # démarre l'API locale et ouvre le navigateur
```

Le port 5001 est celui de `config/logistique.yaml` (`osrm.url`) ; le port 5000 est évité car
macOS le réserve à AirPlay. Un autre port : `AB_DSS_OSRM_PORT=5002 bash scripts/osrm_setup.sh
--serveur`, et la même valeur dans `osrm.url`.

Option : `python -m ab_dss --sans-navigateur --port 8000`.

Distances routières (écran Sites ; sous Windows, `scripts\osrm_setup.ps1`, voir « Installation
sous Windows ») : Docker Desktop, puis une seule fois
`bash scripts/osrm_setup.sh` (graphe du Maroc, environ 2 min), et à chaque session
`bash scripts/osrm_setup.sh --serveur` (port 5001). Sans OSRM, l'outil utilise les distances
déjà en cache, sinon la distance à vol d'oiseau × le coefficient de détour calibré, et le
signale par un bandeau.

Les fichiers à déposer à la main (communiqués des DRA, Phyllis, enquête de terrain…) sont décrits
dans [docs/donnees_manuelles.md](docs/donnees_manuelles.md). `scripts.prepare` s'arrête avec la
liste des fichiers manquants et écrit `data/processed/rapport_controle.html` (lignes valides,
rejetées, doublons, aberrantes et non utilisées par source ; contrôles de la désagrégation).

Au premier lancement, l'onglet **Paramètres** porte un badge « 4 à renseigner » : la capacité
visée, la température de pyrolyse, le prix plafond et le prix du gazole se saisissent dans sa
section Entreprise, et chaque écran qui en a besoin renvoie directement au champ. L'outil ne
suppose jamais ces valeurs (RG-15). Les saisies sont écrites dans `config/entreprise.local.yaml`
(et les réglages techniques dans `config/parametres_modifies.yaml`), fichiers locaux ignorés par
Git : `config/entreprise.yaml` reste le modèle livré vide.

## Obtenir un classement

1. Onglet **Paramètres**, section Entreprise : capacité visée, température de pyrolyse, prix
   plafond et prix du gazole (badge « 4 à renseigner » tant qu'ils manquent).
2. **Accueil** › « Voir le classement » : écran **Décision**. Le bandeau « Classement partiel :
   n critères sur N » liste les critères actifs encore incalculables et ce qu'il faut saisir.
3. **Décision** : critères et seuils, poids (curseurs ou AHP), classement des sites (WSM ou
   TOPSIS), classement des gisements, analyse de robustesse ; un clic sur un site ouvre sa
   **Fiche site** (rang, critères, bassin, mélange, bilan, robustesse), imprimable en PDF.
4. Chaque tableau s'exporte en **Excel** (feuilles « paramètres » et « sources ») ou en **CSV**.
5. Contexte du scénario (navigation) › « Enregistrer le scénario » : paramètres, réglages de la
   décision et version des données sont enregistrés dans `scenarios/` et se rechargent à
   l'identique.

Un prix observé (Données › Prix et coûts) d'un résidu, désigné par son code (R05…) et exprimé
en DH/t, remplace le prix d'achat de `concurrence.csv` dans le coût livré.

## Données à saisir par l'entreprise

Ces valeurs sont livrées « À compléter » : l'outil ne les suppose jamais (RG-14, RG-15). Tant
qu'elles manquent, les calculs qui en dépendent sont bloqués et chaque écran dit ce qui manque ;
le classement reste « partiel » (bandeau en tête). Les saisies demandent une source et une date.

| Valeur | Résidus ou activité | Où la saisir | Débloque |
| --- | --- | --- | --- |
| Coût fixe F par rotation de camion (PAR-61) | — | Paramètres › réglages techniques | coût livré, bassins, mélange |
| Volume utile du camion (PAR-32) | — | Paramètres › réglages techniques | charge utile, coût livré, transport de l'ACV |
| Procédé de trituration (PAR-62), forme des pulpes (PAR-63) | R05, R12 | Paramètres › réglages techniques | gisement des grignons et des pulpes |
| Prix de vente du biochar (PAR-55) et du crédit carbone (PAR-56) | — | Paramètres › Entreprise (facultatifs) | critère C6 (marge) |
| Part déjà utilisée u (`part_utilisee`) | les 13 résidus (valeur nationale) ; R06 connu à Errachidia | Données › saisie directe, table `concurrence` | gisement mobilisable M, critère A3 |
| Prix d'achat au producteur (`prix_achat_dh_t`) | tous sauf R05 | Données › `concurrence`, ou Données › Prix et coûts (prix observé en DH/t) | coût livré, critère C1 |
| Coûts de collecte `k_col` et de prétraitement `k_pre` | les 13 résidus | Données › `residus` | coût livré |
| Densité apparente | les 13 résidus | Données › `residus` | charge utile du camion |
| Taux de collecte `f_col`, part prélevable `f_eco` | R05 à R13 | Données › `residus` | gisement mobilisable M |
| Humidité | R01, R02, R04, R07, R10 | Données › `residus` | coût livré, gisement de R07 et R10 |
| Carbone, cendres | carbone : R02, R06, R07, R10, R12 ; cendres : R02, R06 | Données › `residus` | critères B1, B2, mélange |
| PCI | R02, R03, R04, R06, R10 à R13 | Données › `residus` | bilan d'un usage concurrent |
| Carbone du biochar | R05, R12 | Données › `residus` | bilan climat |
| Ratio des coques d'argan (`rpr`) | R09 | Données › `residus` | gisement de R09 |
| Éligibilité à la liste positive EBC | les 13 résidus | Données › `residus` | filtre B5 |
| Scénario de référence (brûlage, décomposition, usage concurrent) | les 13 résidus | Données › `residus` | bilan climat (émissions évitées) |
| Données d'activité de l'ACV : gazole de collecte (L/t MS) et d'épandage (L/t biochar), électricité de broyage (kWh/t MS) et de pyrolyse (kWh/t biochar), distance du biochar aux parcelles (km) | — | Données › `facteurs_emission` | bilan climat |
| Facteurs sans valeur par défaut du GIEC : amont du gazole (kg CO₂e/L), CH₄ et N₂O de la pyrolyse, CH₄ et N₂O de la décomposition au champ | — | Données › `facteurs_emission` | bilan climat |
| Profil mensuel de disponibilité | les 13 résidus | Données › `calendrier` (import Excel) | critère A4 |
| Coordonnées des agropoles de Berkane, Tadla, Souss et Loukkos | — | Sites › Ajouter un site (par coordonnées) | évaluation de ces agropoles |

Les sources possibles de chaque valeur sont dans la colonne « où la trouver » des tables
(`data/input/`) et dans [docs/donnees_manuelles.md](docs/donnees_manuelles.md).

## Démonstration

Pour la soutenance, Paramètres › Scénarios › Démonstration charge en un clic l'un des cinq
scénarios de `scenarios/demo/`. Ils complètent les valeurs ci-dessus par des hypothèses
(liste et sources : [docs/demo.md](docs/demo.md)), dans une copie de travail. Le bandeau
« Démonstration — paramètres d'hypothèse, pas un résultat réel » est alors affiché sur tous les
écrans et repris en tête des exports et de la fiche site. « Quitter la démonstration » revient
aux paramètres et aux données réels : la démonstration ne les modifie jamais.

## Mettre à jour les données sans écrire de code

Tout se fait depuis la page **Données** ; chaque modification crée une version (RG-17) :

- **Import par modèle Excel** : téléchargez le modèle d'une table (déjà rempli), modifiez-le,
  déposez-le ; l'outil affiche les lignes ajoutées, modifiées, rejetées (avec le motif) et à
  confirmer, puis enregistre une version après validation. Une valeur hors du domaine physique
  est rejetée ; une valeur peu plausible (par exemple une production 10 fois supérieure à la
  campagne précédente) doit être confirmée (RG-19).
- **Saisie directe** : le crayon d'un tableau corrige une valeur ; la source et la date sont
  obligatoires (RG-18).
- **Prix et coûts** : un prix observé s'ajoute à l'historique ; le plus récent est utilisé.
- **Versions** : comparez deux versions, restaurez-en une (la restauration crée une nouvelle
  version, rien n'est écrasé).
- **Statut et contrôle** : carte du statut de la production par province (publiée ou estimée)
  et rapport de contrôle. **Sources** : manifeste `data/sources.yaml`.

Après le dépôt de nouveaux fichiers bruts, relancez `python -m scripts.prepare`. La méthode
(provenance, statuts, désagrégation RG-04) est décrite dans [docs/methode.md](docs/methode.md).

Les paramètres de l'entreprise se règlent sur la page **Paramètres**, qui présente aussi les
paramètres techniques avec leur source et le retour à la valeur par défaut ; le bouton
« Enregistrer » de la barre de contexte enregistre un scénario dans `scenarios/`.

## Développement de l'interface

```bash
cd frontend
npm install
npm run dev      # interface sur http://localhost:5173, API attendue sur le port 8000
npm run build    # compile dans frontend/dist/, servi par python -m ab_dss
```

## Tests et qualité

```bash
pytest --cov=src
ruff format --check . && ruff check .
cd frontend && npm test && npm run lint && npm run format:check && npm run typecheck
cd frontend && npx playwright test   # parcours, captures 1280 et 1920 px, accessibilité
```

Les tests Python utilisent `tests/fixtures/`, extrait figé des données réelles ; les tests
marqués `donnees_reelles` lisent `data/processed/` et sont ignorés si les données ne sont pas
préparées. Les essais Playwright lancent l'outil sur une copie des données
(`python -m scripts.racine_essai`), sans toucher `data/` ni `config/` ; les captures d'écran
sont écrites dans `frontend/test-results/captures/`.

## Activity Browser 3

Activity Browser s'installe dans un environnement conda séparé pour éviter les conflits de versions
avec l'outil ; il ouvre le même répertoire de projets Brightway (variable `BRIGHTWAY2_DIR`).

1. Ouvrir une fois l'écran **Bilan climat** de l'outil : il crée ou met à jour le projet
   `atlantic_biochar` (biosphère, méthode « Atlantic Biochar · PRG100 AR6 », base
   `ab_foreground`) dans le répertoire Brightway par défaut
   (macOS : `~/Library/Application Support/Brightway3` ; Windows :
   `C:\Users\<nom>\AppData\Local\pylca\Brightway3`).
2. Installer Activity Browser 3 dans son propre environnement :
   `conda create -n ab-activity-browser -c conda-forge activity-browser`, puis
   `conda activate ab-activity-browser && activity-browser`.
3. Choisir le projet `atlantic_biochar` : chaque résidu a ses activités « Collecte »,
   « Prétraitement », « Transport vers l'usine », « Pyrolyse », « Transport et épandage », la chaîne
   « Biochar produit et épandu » (1 t) et son « Scénario de référence ». Les quantités qui dépendent
   du couple et du site sont des paramètres (groupe `chaine_Rxx` : `m`, `distance`, `q`,
   `facteur_ref`) ; une valeur « À compléter » y vaut 0 avec ce commentaire.

L'outil reconstruit `ab_foreground` à chaque changement de données : une modification faite à la
main dans Activity Browser serait remplacée ; modifiez les valeurs dans l'écran **Données**.

## Arborescence

Voir la section 16 du cahier des charges.
