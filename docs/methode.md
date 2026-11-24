# Note méthodologique

Cette note reprend les formules de la section 8 du cahier des charges et documente les choix de mise
en œuvre. Elle est complétée au fil des lots.

1. Provenance des données et statuts (lot 1)
2. Désagrégation des statistiques régionales (lot 1)
3. Potentiel mobilisable (lot 2)
4. Logistique et coût livré (lot 3)
5. Bilan climat avec Brightway (lot 4)
6. Décision multicritère et robustesse (lot 5)
7. Mélange optimal (lot 5)

## 1. Provenance des données et statuts

Chaque valeur porte sa source (`source_id`, identifiant de `data/sources.yaml`), son année, son
statut et la version des données qui l'a introduite (RG-03). Les statuts suivent la section 3
du cahier :

| Statut | Valeurs concernées |
| --- | --- |
| Mesurée | Statistique officielle réalisée, publiée à la maille de la valeur (DRA, DPA, HCP, Open Data) |
| Estimée | Valeur issue d'une répartition (RG-04, groupe de provinces compris) ; valeur prévisionnelle publiée, avec le signal `previsionnel` ; surface CROPGRIDS par province |
| Littérature | Valeur de référence tirée d'une publication (section 14.2) |
| Terrain | Valeur saisie par l'équipe ou l'entreprise (enquête, réglage d'un paramètre) |
| Hypothèse | Valeur fixée par convention ; milieu d'une fourchette sans mode (loi uniforme) |

Une valeur inconnue reste « À compléter » (RG-14) : elle bloque seulement les calculs qui en
dépendent. L'année d'une valeur de campagne est l'année de fin de campagne (2017-2018 → 2018).

**Contrôles avant import (RG-19).** Les bornes de `config/controles.yaml` sont des bornes de
domaine physique (fraction entre 0 et 1, teneur entre 0 et 100 %, valeur positive) : une valeur
hors du domaine est rejetée. Une plage plausible facultative (`plausible`) peut être ajoutée par
l'entreprise à partir d'une source : une valeur hors de cette plage, comme une production
10 fois supérieure à la campagne précédente, est signalée et doit être confirmée.

**Versions (RG-17).** Chaque modification (préparation, import Excel, saisie, prix observé,
restauration) crée une version dans `data/versions/` et une entrée du journal
`data/versions.yaml`. La première préparation crée la version des données livrées. Une
restauration recopie à l'octet près les fichiers de la version restaurée dans une nouvelle
version.

## 2. Désagrégation des statistiques régionales

**Sources lues.**

- SRC-18 (communiqués des DRA et DPA, presse qui les reprend) et SRC-03 (monographie du HCP) :
  `valeurs_saisies.csv`, croisé avec `valeurs_verifiees.csv` ; seules les lignes vérifiées
  dans la page archivée sont utilisées. Les lignes sans campagne (superficies sans date, moyenne
  pluriannuelle) et les parts du total national ne sont pas utilisées.
- SRC-01 (Open Data Maroc, Production végétale 2010-2022) : total national par culture, somme des
  produits de chaque culture (`config/preparation.yaml`). Le total national d'une campagne est
  celui de la même campagne dans SRC-01, de 2010-2011 à 2019-2020, pour les 12 cultures
  présentes (agrumes, amandier, avoine, betterave, blé, olivier, orge, palmier dattier, riz,
  rosacées, tomate, vigne). Les campagnes 2020-2021 et 2021-2022 sont rejetées : le fichier y
  contient des centaines de lignes par produit sans colonne géographique, dont la somme n'est pas
  un total national vérifiable. Le seigle et l'arganier n'ont pas de produit dans SRC-01.
  Pour l'olivier 2023-2024, le total national est le communiqué du ministère (SRC-18, automne
  2023, prévisionnel).

**Clé de répartition.** Surface cultivée CROPGRIDS (`croparea`, 2020) de chaque culture dans
chaque province. Un pixel de 0,05° coupé par une limite est partagé au prorata de l'aire de son
intersection avec chaque province, calculée en projection équivalente. Trois provinces
sahariennes (Boujdour, Tarfaya, Aousserd) n'ont aucune surface CROPGRIDS : leur part est nulle,
ce qui donne une valeur estimée de 0, pas une donnée manquante.

**Algorithme (RG-04)**, pour chaque grandeur (production, superficie), culture et campagne :

1. valeur provinciale publiée : gardée avec son statut ; une valeur publiée pour un groupe de
   provinces est répartie entre ses membres au prorata CROPGRIDS (statut Estimée) ;
2. total régional réel moins les provinces connues de la région, réparti entre les provinces
   manquantes au prorata CROPGRIDS (Estimée) ;
3. total national moins toutes les provinces déjà attribuées, réelles ou estimées à l'étape 2,
   réparti de même (Estimée). La somme des 75 provinces égale ainsi le total national.

Une valeur prévisionnelle n'est retenue que s'il n'existe pas de valeur réalisée pour la même
zone et la même campagne. Chaque valeur estimée garde la source du total (`source_total`), la
part CROPGRIDS, la campagne, la période et la liste des valeurs soustraites (`soustraites`).

**Écarts de campagne.** Une valeur soustraite dont la campagne diffère de celle du total, ou
dont la campagne a été déduite d'une année civile par la règle de campagne, est signalée
(`ecart_campagne`, note de la valeur estimée, section dédiée du rapport de contrôle). Exemple :
le total national d'olives 2017-2018 (SRC-01, campagne) soustrait les provinces de
Tanger-Tétouan-Al Hoceima, estimées d'un total publié pour l'année civile 2017.

**Contrôles.** La somme des provinces égale le total parent à 0,1 % près
(`config/controles.yaml`) ; un total qui ne peut pas être réparti (provinces connues
supérieures au total, reste positif sans surface CROPGRIDS) est signalé et ses provinces restent
sans valeur, jamais à zéro (RG-06). Le rapport `data/processed/rapport_controle.html` liste, par
fichier source, les lignes valides, rejetées, doublons, aberrantes (au-delà de 3 écarts types de
leur série) et non utilisées, puis les contrôles des sommes et la couverture des provinces.

**Condition de fin du lot 1.** Sur les données préparées le 22/11/2026, les 75 provinces ont une
production réelle ou estimée selon la RG-04 à partir d'un total réel, avec sa source : 9 ont au
moins une statistique réalisée publiée à leur maille, 66 reposent sur des valeurs estimées.

## 3. Potentiel mobilisable

Calculs de `src/potentiel/` (section 8.1 du cahier), réglés par `config/potentiel.yaml`, sur les
tables de référence et la production dans leur **version active** (RG-17).

**Gisement théorique T** (t MS/an), pour chaque province × résidu :

- mode « produit » : Q × RPR ; mode « surface » : S × Y ; mode « nombre de pieds » :
  N × Y^pied, avec N = S × densité de plantation de secours (112,5 pieds/ha, statut Estimée)
  faute de nombre de pieds ;
- somme sur les cultures du résidu (R04 : amandier et rosacées, chacun avec son ratio ; R13 :
  blé, riz, avoine, seigle et orge, l'orge au coefficient du blé, statut Hypothèse) ;
- (1 − h) n'est appliqué qu'à un ratio exprimé en masse brute (δ_r = 1) ; un ratio en t MS
  (tailles R01 à R04, palmes R06) n'est jamais corrigé de l'humidité ;
- R05 (grignons) : ratio et humidité du procédé PAR-62 ; part des olives triturées (0,8)
  appliquée en Fès-Meknès seulement, seule région où elle est sourcée ; R12 (pulpes) : forme
  PAR-63. Ces deux paramètres sont livrés « À compléter » ;
- campagne de référence (PAR-02) : moyenne des 5 dernières campagnes disponibles de chaque
  province, culture et grandeur ; les prévisions sont incluses et signalées. T est aussi calculé
  pour chaque campagne.

**Gisement mobilisable et dérivés** : M = T × f_col × f_eco × (1 − u) ; C = M × c ; B = M × y.
La part concurrente u est celle de la province, sinon la valeur nationale du résidu (statut
Littérature au mieux). Tant que M est bloqué, C_T = T × c et B_T = T × y sont affichés comme
valeurs théoriques. Densité = gisement ÷ surface cultivée CROPGRIDS de toutes les cultures de
la province (km²) ; cv_M = écart type ÷ moyenne de M sur les campagnes calculables (A5).

**Provenance.** Chaque valeur garde ses sources, ses campagnes, le signal « previsionnel » et le
statut le moins fiable de ses entrées (ordre : Hypothèse, Estimée, Littérature, Terrain,
Mesurée). Un indicateur dont une entrée manque est exclu et listé avec le motif et l'endroit où
compléter la valeur (RG-06, RG-14) ; il n'est jamais compté zéro.

**État au 22/11/2026.** T est calculé pour R01 à R04 et R06 dans les 75 provinces ; R05 et R12
attendent PAR-62 et PAR-63, R07 et R10 leur humidité, R09 son ratio. Depuis l'intégration des
valeurs SRC-08 (Dyjakon 2019), f_col et f_eco sont connus pour R01 à R04 ; M, C et B attendent
encore la part concurrente u (enquête de terrain, section 7.3), sauf R06 à Errachidia.

**Plausibilité (§18.2).** La comparaison du gisement national mobilisable aux ordres de grandeur
publiés (environ 60 millions de t de déchets organiques par an, dont 92 % agricoles) est reportée
jusqu'au calcul de M : le gisement théorique partiel (5 résidus sur 13) n'est pas comparable à
ce total.

**Condition de fin du lot 2.** Le couple R01 × Taounate est recalculé à la main à 0,1 % près
(`tests/test_potentiel_gisements.py`, avec f_col, f_eco et u en saisies simulées pour le test) ;
la carte des 75 provinces est affichée sur l'écran Gisements (`frontend/e2e/gisements.spec.ts`).

## 4. Logistique

Calculs de `src/logistique/` (section 8.2), réglés par `config/logistique.yaml`.

**Points de rattachement (H1).** Barycentre des pixels CROPGRIDS (surface cultivée des cultures
d'origine du résidu, pixels partagés au prorata de l'aire) ; à défaut (arganier absent de
CROPGRIDS, surface nulle), centroïde géométrique de la province, signalé (`methode`).

**Sites candidats.** Chefs-lieux : chef-lieu administratif de la province, placé sur le lieu
OpenStreetMap (SRC-06) du même nom. Quand aucune ville ne porte le nom de la province, le
chef-lieu est désigné dans `data/input/chefs_lieux.csv` (9 provinces, par exemple Al Haouz →
Tahannaout, décision de l'équipe du 23/11/2026 ; le dahir 1-59-351 consolidé ne fixe que les
sièges des régions). Agropoles :
`data/input/sites.csv` ; seule l'Agropolis de Meknès est placée (arrêt « Agropolis » d'OSM), les
quatre autres sont « À compléter ». Sites de l'utilisateur : `config/sites.local.yaml`.

**Distances (SRC-07).** Matrice OSRM (profil voiture) mise en cache dans `data/cache/logistique/`
avec l'empreinte des points et des sites (RG-13). Sans OSRM, distance à vol d'oiseau (grand
cercle) × coefficient de détour PAR-30 = médiane du rapport route ÷ vol d'oiseau sur la dernière
matrice OSRM : 1,32 sur 74 100 trajets le 22/11/2026. Le repli est signalé par un bandeau et
n'est jamais mis en cache ; sans calibration préalable il est impossible et le message dit de
démarrer OSRM.

**Coût livré.** CL = a + k_col + k_pre + (F + v · 2 d) / q (DH/t MS), avec v = PAR-38 × PAR-37
(saisi par l'entreprise, jamais le repère de `parametres.yaml`) ÷ PAR-39 et q = min(PAR-31,
densité apparente × PAR-32) × (1 − h). a, prix par t brute de `concurrence.csv`, est ramené à
la t MS : a / (1 − h) (décision du 23/11/2026).
Courbe : couples triés par coût croissant, au-delà de PAR-59 écartés ; coût moyen et marginal à
K sur les couples sous le prix plafond ; sinon « capacité non atteignable » et tonnage manquant
(RG-10). Bassin = couples sous le prix plafond ; isodistance tracée comme un cercle de rayon
(distance routière maximale du bassin ÷ coefficient de détour). C3 = gisement M à moins de
PAR-35 km par la route.

**État au 22/11/2026.** Courbes bloquées sur les données livrées : PAR-61 (coût fixe), PAR-32
(volume du camion), densité apparente, k_col, k_pre et prix d'achat des résidus sont « À
compléter », comme M. L'écran Sites liste ces valeurs avec un lien vers leur champ.

**Condition de fin du lot 3.** La courbe de Meknès est affichée avec des saisies simulées sur la
copie d'essai (`frontend/e2e/logistique.spec.ts`) ; le repli à vol d'oiseau est testé avec OSRM
arrêté (`tests/test_logistique.py`, `tests/test_api_logistique.py`).

## 5. Bilan climat

Calculs de `src/acv/` (section 8.3), réglés par `config/acv.yaml`, avec Brightway 2.5 sans
ecoinvent : biosphère de bw2io (liste des flux élémentaires, sans inventaire), méthode PRG100 AR6
créée par code à partir de PAR-27 (CO₂ fossile 1, CH₄ fossile 29,8, CH₄ biogénique 27,0, N₂O 273),
base `ab_foreground` construite par code.

**Arrière-plan agrégé.** Une activité par ligne de `facteurs_emission.csv` (gazole brûlé et amont
par L, électricité du réseau par kWh, fioul par L, émissions de la pyrolyse par t de biochar,
brûlage et décomposition par t MS). Un facteur en kg CO₂e (électricité, amont du gazole) est porté
par le flux de CO₂ fossile.

**Bilan net** (t CO₂e/t biochar, unité fonctionnelle : 1 t de biochar produite et épandue), avec
m = 1/y t MS par t de biochar :
BN = C_bc · F_perm · 44/12 − (E_col + E_pre + E_tr + E_pyr + E_ep) + E_ref, où
E_col = m · gazole de collecte ; E_pre = m · électricité de broyage ;
E_tr = m · PAR-38 · 2 d / q (même charge utile q que le coût livré) ;
E_pyr = électricité de la pyrolyse + CH₄ et N₂O de la pyrolyse ;
E_ep = gazole d'épandage + PAR-38 · 2 d_biochar / PAR-31 ;
E_ref = m · émissions du brûlage ou de la décomposition évitées, ou, pour un usage concurrent,
− m · PCI du résidu / PCI du fioul · émissions du fioul de substitution.
F_perm = PAR-20 de la classe de température de PAR-21 (classes du GIEC 2019 : basse dès 350 °C,
moyenne dès 450 °C, haute dès 600 °C). C_bc vient de `residus.csv` (`carbone_biochar`) ; une
valeur mesurée à une température (R01 à 600 °C) ne vaut que pour sa classe.

**Mise en œuvre.** Les étapes de chaque résidu sont des activités Brightway dont les échanges
portent des formules (`m * gaz_col`, `m * conso * trajets * distance / q`…) sur des paramètres de
projet et du groupe `chaine_Rxx`. Pour une chaîne, les paramètres prennent les valeurs du couple
et Brightway recalcule (`/api/acv/chaine`). Pour tous les couples à la fois, le bilan est la même
combinaison linéaire des scores unitaires des activités agrégées, calculés par Brightway : moins
de 5 s pour plus de 8 000 chaînes (UC-ACV-02 : moins de 30 s). Bilan d'un site : moyenne des
couples retenus pour K, pondérée par leur tonnage (RG-08). Standard appliqué : neutre (RG-07).

**Données ajoutées au lot 4** (« À compléter », section 7.3) : gazole de collecte, électricité de
la pyrolyse, gazole d'épandage, distance du biochar aux parcelles, PCI du fioul
(`facteurs_emission.csv`), carbone du biochar de R02 à R13 (`residus.csv`). Le scénario de
référence et les facteurs se saisissent dans l'écran Données (saisie directe ouverte aux facteurs
d'émission et aux valeurs à choix).

**Facteurs officiels du GIEC intégrés le 23/11/2026** (documents archivés dans
`data/raw/SRC-15/`, statut Littérature, loi triangulaire quand le GIEC donne un intervalle) :

| Valeur | Défaut | Source |
| --- | --- | --- |
| Gazole, CO₂ | 74 100 kg/TJ | GIEC 2006, vol. 2, ch. 3, tableau 3.2.1, p. 3.16 |
| Gazole, CH₄ et N₂O (poids lourd) | 3,9 et 3,9 kg/TJ | vol. 2, ch. 3, tableau 3.2.2, p. 3.21 |
| Gazole, PCI | 43,0 MJ/kg | vol. 2, ch. 1, tableau 1.2, p. 1.18 |
| Fioul lourd, CO₂ | 77 400 kg/TJ | vol. 2, ch. 1, tableau 1.4, p. 1.23 |
| Fioul lourd, CH₄ et N₂O (commercial) | 10 et 0,6 kg/TJ | vol. 2, ch. 2, tableau 2.4, p. 2.20 |
| Fioul lourd, PCI | 40,4 MJ/kg | vol. 2, ch. 1, tableau 1.2, p. 1.18 |
| Brûlage des résidus, CH₄ et N₂O | 2,7 et 0,07 g/kg MS brûlée | raffinement 2019, vol. 4, ch. 2, tableau 2.5, p. 2.54 |
| Facteur de combustion « autres cultures » | 0,85 | raffinement 2019, vol. 4, ch. 2, tableau 2.6, p. 2.56 |
| Carbone organique du biochar | bois 0,77 ; herbacées 0,65 ; coques et noyaux 0,74 ; balles de riz 0,49 | raffinement 2019, vol. 4, appendice 4, tableau 4AP.1, p. Ap4.2 |
| F_perm (PAR-20) | 0,65 / 0,80 / 0,89 | raffinement 2019, vol. 4, appendice 4, tableau 4AP.2, p. Ap4.3 |

Le fioul de substitution (usage concurrent) est retenu au secteur commercial (hammams,
chaudières) ; l'industrie (tableau 2.3, briqueteries) donne CH₄ 3 kg/TJ, N₂O identique. Sa
substitution est calculée en énergie (PCI du résidu × facteur par MJ), le PCI du fioul est donc
une information. Le gazole est converti en kg/L par le PCI et la masse volumique, que le GIEC ne
donne pas.

Masse volumique du gazole : milieu de la plage de la norme EN 590 (820 à 845 kg/m³), loi uniforme, statut Hypothèse (décision du 23/11/2026). Sans valeur par défaut du GIEC, donc « À compléter » : amont du
gazole, CH₄ et N₂O de la pyrolyse, CH₄ de la décomposition (aérobie), N₂O de la décomposition
(EF1 = 0,01 kg N₂O-N/kg N, tableau 11.1, exige la teneur en azote du résidu), scénario de
référence de chaque résidu ; carbone du biochar de R05 et R12 (aucune classe du tableau 4AP.1
ne leur correspond). Dépendent de l'installation : gazole de collecte et d'épandage, électricité
de broyage et de pyrolyse, distance aux parcelles.

**État au 23/11/2026.** Les bilans restent bloqués sur les données livrées par ces valeurs et
par PAR-21 ; l'écran Bilan climat les liste.

**Plausibilité (§18.2).** Reportée tant qu'aucun bilan n'est calculé sur des données réelles ; la
chaîne de référence des tests (2,49 t CO₂e/t biochar) repose en partie sur des saisies simulées et ne vaut
pas comparaison avec la littérature.

**Condition de fin du lot 4.** Le bilan de la chaîne de référence (R03, Taounate → Meknès, OSRM
réel) calculé par l'outil et par le modèle Brightway paramétré est égal, terme à terme et à 1 %
près, au calcul tableur indépendant `tests/fixtures/acv/chaine_reference.xlsx` (formules Excel,
recalculées par Excel ; `tests/test_acv.py`).

**À vérifier par l'équipe (ENF-15).** L'ouverture du projet dans Activity Browser 3 n'a pas pu
être testée automatiquement (interface graphique) : procédure dans le README.

## 6. Décision et mélange

Calculs de `src/decision/` et `src/melange/` (sections 9, 10 et 11.2.4), réglés par
`config/criteres.yaml` (catalogue des 19 critères) et `config/decision.yaml`.

**Critères des sites.** Un critère de gisement est porté au site par la moyenne de ses couples
pondérée par le tonnage retenu pour atteindre K (RG-08) : A1 (tonnage sous le prix plafond), A3,
A4 (mois où l'apport couvre K/12, `calendrier.csv`), B1 à B4, C1 (coût moyen à K), C2, C3, C6
(prix du biochar × y + prix du crédit × BN × y − coût livré), D1, D2. B5 (éligibilité EBC) est un
filtre. Critères d'implantation préparés par `scripts.prepare` : F1, distance à l'autoroute ou à
la route nationale la plus proche (OSM `highway` = motorway, trunk, primary) ; F2, distance à la
zone industrielle OSM (`landuse=industrial`) ou à l'agropole placée la plus proche ; E1, surface
cultivée CROPGRIDS dans le rayon PAR-36 ; G1, population rurale de la province (lignes « milieu
rural » du RGPH 2024 ; deux préfectures sans milieu rural valent 0). Distances F1 et F2 en
UTM 29N.

**Classement.** Filtres et seuils de l'utilisateur, capacité atteignable (RG-10, non appliquée tant
que le bassin n'est pas calculé, et c'est signalé), sites exclus ou imposés (PAR-57) ; un critère
actif non calculable est retiré du calcul et listé avec son motif (RG-14 : jamais compté zéro),
un critère constant est neutralisé. Poids par défaut PAR-45, poids directs ou AHP hiérarchique
(vecteur propre principal, CR = CI / RI de Saaty, alerte au-delà de PAR-44). Normalisation
min-max, somme pondérée ou TOPSIS (normalisation vectorielle ; égal à pymcdm à 10⁻⁶). Contributions
par critère et score par axe pour les barres segmentées. Corrélations de Pearson au-delà de
PAR-43 signalées (RG-11). Robustesse : un poids à la fois de −50 % à +50 % par pas de 10 %,
1 000 tirages de Dirichlet (PAR-41, graine PAR-04), libellé « robuste » de la RG-12. Variation de
rang : comparaison au dernier réglage différent des paramètres de l'entreprise (RG-16, historique
dans `data/cache/decision/`). Les réglages de l'écran Décision sont dans
`config/decision.local.yaml` (local) et copiés dans chaque scénario.

**Classement partiel (décision du 23/11/2026).** Quand un critère actif est retiré, un bandeau
« Classement partiel : n critères sur N » est affiché en haut du classement (écran Décision,
accueil) avec la liste des critères retirés et leur motif ; il sera repris dans les exports.

**Classement des gisements (décision du 23/11/2026).** Les couples province × résidu dont le
gisement théorique T est calculé sont classés sur les critères actifs de niveau G : A1 (M), A2,
A3, B1 à B4, B5 (filtre) et, pour un site choisi, C1, C6 et D1. Règle propre aux gisements : un
couple à qui manque un critère calculé pour d'autres couples est exclu et compté ; un critère qui
manque pour tous les couples est retiré (bandeau). Sur les données livrées, les gisements ne
sont pas encore classables : A3 n'existe que pour R06 à Errachidia.

**Mélange.** Programme linéaire de la section 11.2.4 résolu par `linprog` (HiGHS) sur les couples
du bassin ; une contrainte dont le paramètre n'est pas saisi (PAR-51, 52, 53) n'est pas appliquée
et c'est affiché ; un problème infaisable est relancé en relâchant une contrainte à la fois.

**État au 23/11/2026.** Sur les données réelles, seuls E1, F1, F2 et G1 sont calculables : le
classement affiché repose sur ces 4 critères (Settat 1er, 1er dans 54 % des tirages en TOPSIS) ;
A1, A3, A4, B2, C1, C2 et D1 attendent les valeurs qui bloquent le bassin (PAR-61, PAR-32,
densité, coûts, u) et le bilan climat. Le mélange est bloqué pour la même raison.

**Condition de fin du lot 5.** Classement en moins de 2 s après un changement de poids
(`tests/test_api_decision.py`, `tests/test_decision_classement.py`) ; TOPSIS égal à pymcdm
(`tests/test_decision_methodes.py`) ; un changement de prix plafond met à jour le classement et
la variation de rang (`tests/test_api_decision.py`, `frontend/e2e/decision.spec.ts`).

## 7. Restitution et recette du MVP

**Exports (UC-RES-02).** Tout tableau affiché s'exporte en Excel (tableau, feuille
« paramètres » : paramètres de l'entreprise, techniques et réglages de la décision ; feuille
« sources » : manifeste avec licence et attribution, ENF-05 et ENF-14) ou en CSV (« ; », virgule
décimale). Le bandeau « Classement partiel : n critères sur N » et les critères retirés sont en
tête des exports de classement (décision du 23/11/2026). Mise en forme dans
`config/restitution.yaml`.

**Fiche site (UC-RES-01).** `/api/fiche/{site}` réunit rang, score, variation, robustesse, score
par axe, critères avec ce qui manque, bassin, mélange et bilan ; l'écran s'imprime en PDF.

**Prix observés.** Un prix observé de résidu en DH/t prime sur `concurrence.csv` pour sa zone (le
plus récent ; province puis national), ce qui rend visible son effet sur le coût livré.

**Recette 18.3 (23/11/2026)** — `frontend/e2e/recette.spec.ts` et tests cités :

| Étape | État |
| --- | --- |
| Poste neuf en moins de 15 min (README) | à faire par l'équipe sur un poste neuf |
| Paramètres obligatoires puis classement en 3 clics au plus | réussi (2 clics depuis Paramètres) |
| Prix plafond et capacité modifiés, variations de rang | réussi |
| Meknès dans le classement et sa fiche | réussi (bassin, mélange, bilan affichés ; bloqués par les données) |
| Poids modifiés, classement en moins de 2 s | réussi |
| Robustesse, probabilité d'être 1er | réussi |
| Excel des productions : import puis restauration | réussi (`parcours.spec.ts`) |
| Prix des grignons saisi et effet sur le coût livré | réussi avec saisies simulées (`test_api_logistique.py`) : sur les données livrées, le coût livré attend PAR-61, PAR-32, densité, k_col, k_pre |
| Clic sur une valeur : source, date, statut | réussi (`parcours.spec.ts`) |
| Scénario enregistré, rechargé, même classement | réussi |
| Export Excel avec « paramètres » et « sources » | réussi |

## Choix techniques à vérifier

### Installation de Brightway 2.5 (décision du 22/11/2026)

Le méta-paquet `brightway25` cité en section 16 n'est pas publié sur conda-forge (seulement sur le
canal personnel `cmutel`). L'environnement installe donc directement ses composants depuis
conda-forge : `bw2data` (≥ 4), `bw2calc` (≥ 2), `bw2io` et `bw2parameters`. Versions obtenues au
22/11/2026 sur macOS arm64 : bw2data 4.8, bw2calc 3.1.0, bw2io 0.9.17.

**À vérifier au lot 4** : qu'Activity Browser 3, installé dans un environnement conda séparé,
ouvre le projet `atlantic_biochar` produit avec ces versions (ENF-15), en particulier avec
bw2calc 3. Si ce n'est pas le cas, fixer les versions compatibles dans `environment.yml`.
