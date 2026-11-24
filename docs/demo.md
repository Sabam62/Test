# Scénarios de démonstration (soutenance)

Cinq scénarios montrent l'outil de bout en bout pendant la soutenance, alors que plusieurs
valeurs réelles restent « À compléter ». Ils ne sont **pas** des résultats : chaque écran,
chaque export et la fiche site imprimée portent alors le bandeau
« Démonstration — paramètres d'hypothèse, pas un résultat réel ».

## Règle

- Aucune donnée n'est modifiée : productions, surfaces, propriétés connues des résidus et
  facteurs connus restent ceux des sources. Seules les valeurs « À compléter » sont complétées,
  et seulement dans une copie de travail (`data/cache/demo/<scénario>/`). Une valeur connue
  n'est jamais remplacée : le chargement l'ignore et la signale.
- Les saisies réelles de l'entreprise (`config/entreprise.local.yaml`), les réglages
  (`config/parametres_modifies.yaml`, `config/decision.local.yaml`), les versions de `data/`
  et le projet Brightway `atlantic_biochar` ne sont jamais écrits. La copie de travail a son
  propre projet, `atlantic_biochar_demo`.
- Statut « Littérature » : valeur publiée appliquée telle quelle, source citée. Statut
  « Hypothèse » : valeur plausible ou valeur publiée transposée ; la note porte la mention
  « valeur de démonstration ».
- Résidus complétés : R01 à R06, R08 et R11. R07, R09, R10, R12 et R13 restent bloqués (humidité,
  ratio ou production manquants) : la démonstration ne crée aucun gisement.

## Utilisation

Paramètres › Scénarios › Démonstration : « Charger » sur un scénario (un clic). Le bandeau
apparaît en haut de tous les écrans, avec le bouton « Quitter la démonstration », qui revient
aux paramètres et aux données réels, tels qu'ils étaient. Toute saisie faite pendant la
démonstration reste dans la copie de travail et disparaît au prochain chargement.

Fichiers : `scenarios/demo/demo-1.yaml` à `demo-5.yaml` (paramètres de chaque scénario,
héritage par `base`), `scenarios/demo/hypotheses.yaml` (valeurs manquantes communes),
`config/demo.yaml` (dossiers, bandeau). Code : `src/scenarios/demo.py`, routes `/api/demo`.

## Les cinq scénarios

| Scénario | PAR-01 (t MS/an) | PAR-21 (°C) | PAR-34 (DH/t MS) | PAR-37 (DH/L) | PAR-59 (km) | Poids de la décision |
|---|---|---|---|---|---|---|
| demo-1 · Unité de référence à Meknès | 10 000 | 450 | 1 200 | 12 | — | égaux |
| demo-2 · Petite unité locale | 3 000 | 450 | 1 200 | 12 | 50 | égaux |
| demo-3 · Grande unité | 40 000 | 450 | 1 500 | 12 | — | égaux |
| demo-4 · Priorité climat | 10 000 | 600 | 1 200 | 12 | — | D1 = 5 |
| demo-5 · Gazole cher | 10 000 | 450 | 1 200 | 15,5 | — | égaux |

Les paramètres de l'entreprise des scénarios sont des hypothèses de démonstration (RG-15 : hors
démonstration, l'outil ne les suppose jamais). demo-2, demo-4 et demo-5 héritent de demo-1
(`base: demo-1`) et n'en changent que les valeurs indiquées. Repères cités :

- **PAR-34 = 1 200 DH/t MS** (demo-1, et donc demo-2, demo-4 et demo-5) : prix des grignons
  ramené à la matière sèche. La source donne un prix par tonne brute : 650 DH/t brute, borne
  basse de 2013 (PAR-14, [SRC-16-LAVIEECO](https://www.lavieeco.com/affaires/grignon-dolive-un-combustible-a-pouvoir-calorifique-eleve-peu-exploite-24954/)).
  Avec l'humidité des grignons trois phases (45 % de la masse brute, SRC-16-PROCESSES,
  procédé retenu par PAR-62) :
  650 ÷ (1 − 0,45) = 650 ÷ 0,55 = 1 182 DH/t MS, arrondi à **1 200 DH/t MS**.
- **PAR-34 = 1 500 DH/t MS** (demo-3) : relevé au-dessus de demo-1, hypothèse.
- **PAR-37 = 15,50 DH/L** (demo-5) : prix du gazole cité par Médias24 en 2026
  ([SRC-16-MEDIAS24-2026](https://medias24.com/2026/04/21/flambee-des-fruits-et-legumes-limpact-du-gazole-reste-marginal-1663489/)) ;
  12 DH/L dans les autres scénarios : hypothèse.
- **PAR-21 = 450 °C et 600 °C** : classes moyenne et haute de la permanence du GIEC 2019
  (config/acv.yaml).
- **demo-4** : poids 5 sur D1 · Bilan carbone net, 1 sur les autres critères.

## Valeurs manquantes complétées (communes aux cinq scénarios)

Taux de conversion supposé pour les coûts publiés en euros : 10,8 DH/€ (hypothèse).

Scénario de référence (décision de l'équipe du 23/11/2026) : la substitution par le fioul
(« usage concurrent ») n'est retenue que si une source documente l'usage actuel du résidu
comme combustible. C'est le cas des grignons (R05) : hammams, chaudières et briqueteries
(cahier des charges, section 2). Sinon le scénario est « sans substitution » : E_ref = 0,
statut « Hypothèse » (R08, R11).

### Paramètres techniques (config/parametres.yaml)

| Paramètre | Valeur | Statut | Source | Justification |
|---|---|---|---|---|
| PAR-61 | 300 | Hypothèse | — | chargement et déchargement d'un camion, environ 2 h de chauffeur et d'engin ; aucun devis publié trouvé |
| PAR-32 | 70 | Littérature | [DEMO-LEGRAS-FMA](https://www.reussir.fr/legras-la-benne-fond-mouvant-fma-emporte-70-metres-cubes) | semi-remorque à fond mouvant Legras FMA, version 70 m³ (gamme 52, 62 et 70 m³) |
| PAR-62 | trois phases | Hypothèse | — | procédé de trituration retenu pour la démonstration (R05) |

### Propriétés des résidus (data/input/residus.csv)

| Code | Paramètre | Valeur | Unité | Statut | Source | Justification |
|---|---|---|---|---|---|---|
| R01 | humidite | 40 | % masse brute | Hypothèse | — | taille fraîche d'olivier au ramassage |
| R01 | densite_apparente | 200 | kg/m³ | Hypothèse | — | taille broyée en plaquettes ; densité mesurée selon UNI-EN 15103 dans la littérature, valeur non lue |
| R01 | k_col | 432 | DH/t MS | Hypothèse | [DEMO-SPINELLI-2010](https://research.usc.edu.au/esploro/outputs/journalArticle/Industrial-harvesting-of-olive-tree-pruning/99448839902621) | récolte et broyage industriels de la taille d'olivier : 40 €/t anhydre en moyenne (22 à 70), converti à 10,8 DH/€ (taux supposé) |
| R01 | k_pre | 0 | DH/t MS | Hypothèse | — | broyage compris dans la récolte (k_col) |
| R01 | eligible_ebc | oui | — | Hypothèse | — | résidu de taille agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R01 | scenario_reference | brûlage à l'air libre | — | Hypothèse | — | devenir supposé de la taille non valorisée |
| R02 | humidite | 45 | % masse brute | Hypothèse | — | taille fraîche d'agrumes au ramassage |
| R02 | carbone | 47 | % MS | Hypothèse | — | bois de taille, ordre de grandeur des autres tailles de la table (47 à 51 % MS) |
| R02 | cendres | 4 | % MS | Hypothèse | — | bois de taille avec feuilles |
| R02 | pci | 17,5 | MJ/kg | Hypothèse | — | bois de taille, ordre de grandeur des autres tailles de la table (17,5 à 18,5 MJ/kg) |
| R02 | densite_apparente | 200 | kg/m³ | Hypothèse | — | taille broyée en plaquettes, comme R01 |
| R02 | k_col | 432 | DH/t MS | Hypothèse | [DEMO-SPINELLI-2010](https://research.usc.edu.au/esploro/outputs/journalArticle/Industrial-harvesting-of-olive-tree-pruning/99448839902621) | coût de la taille d'olivier (R01) transposé aux agrumes |
| R02 | k_pre | 0 | DH/t MS | Hypothèse | — | broyage compris dans la récolte (k_col) |
| R02 | eligible_ebc | oui | — | Hypothèse | — | résidu de taille agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R02 | scenario_reference | brûlage à l'air libre | — | Hypothèse | — | devenir supposé de la taille non valorisée |
| R03 | pci | 17,8 | MJ/kg | Hypothèse | — | sarments, ordre de grandeur des autres tailles de la table |
| R03 | densite_apparente | 200 | kg/m³ | Hypothèse | — | sarments broyés en plaquettes, comme R01 |
| R03 | k_col | 432 | DH/t MS | Hypothèse | [DEMO-SPINELLI-2010](https://research.usc.edu.au/esploro/outputs/journalArticle/Industrial-harvesting-of-olive-tree-pruning/99448839902621) | coût de la taille d'olivier (R01) transposé aux sarments |
| R03 | k_pre | 0 | DH/t MS | Hypothèse | — | broyage compris dans la récolte (k_col) |
| R03 | eligible_ebc | oui | — | Hypothèse | — | résidu de taille agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R03 | scenario_reference | brûlage à l'air libre | — | Hypothèse | — | devenir supposé des sarments non valorisés |
| R04 | humidite | 40 | % masse brute | Hypothèse | — | taille fraîche d'amandier au ramassage |
| R04 | pci | 18 | MJ/kg | Hypothèse | — | bois de taille, ordre de grandeur des autres tailles de la table |
| R04 | densite_apparente | 200 | kg/m³ | Hypothèse | — | taille broyée en plaquettes, comme R01 |
| R04 | k_col | 432 | DH/t MS | Hypothèse | [DEMO-SPINELLI-2010](https://research.usc.edu.au/esploro/outputs/journalArticle/Industrial-harvesting-of-olive-tree-pruning/99448839902621) | coût de la taille d'olivier (R01) transposé à l'amandier |
| R04 | k_pre | 0 | DH/t MS | Hypothèse | — | broyage compris dans la récolte (k_col) |
| R04 | eligible_ebc | oui | — | Hypothèse | — | résidu de taille agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R04 | scenario_reference | brûlage à l'air libre | — | Hypothèse | — | devenir supposé de la taille non valorisée |
| R05 | carbone_biochar | 74 | % biochar | Hypothèse | [SRC-15-GIEC-2019](https://www.ipcc-nggip.iges.or.jp/public/2019rf/vol4.html) | GIEC 2019, vol. 4, ch. 2, appendice 4, tableau 4AP.1, classe « Nut shells, pits and stones » ; rattachement des grignons (noyaux) à cette classe supposé |
| R05 | f_col | 0,95 | fraction | Hypothèse | — | grignons produits à l'huilerie, pertes de manutention faibles |
| R05 | f_eco | 1 | fraction | Hypothèse | — | coproduit industriel : aucun retour au sol requis |
| R05 | densite_apparente | 675 | kg/m³ | Hypothèse | [DEMO-CMBIOMASS](https://cmbiomass.com/products/olive-cake) | milieu des densités annoncées par des fournisseurs de grignons (650 et 700 kg/m³), non mesurées |
| R05 | k_col | 20 | DH/t MS | Hypothèse | — | chargement à l'huilerie |
| R05 | k_pre | 100 | DH/t MS | Hypothèse | — | séchage partiel des grignons trois phases |
| R05 | eligible_ebc | oui | — | Hypothèse | — | coproduit de transformation agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R05 | scenario_reference | usage concurrent | — | Hypothèse | CDC | usage documenté : grignons achetés par les hammams, les chaudières et les briqueteries (cahier des charges, section 2) ; substitution par le fioul |
| R06 | carbone | 41,65 | % MS | Hypothèse | [SRC-16-LAHBOUBI-2023](https://academic.oup.com/ce/article/7/4/747/7234273) | valeur « contrôle » de la même source (ligne carbone · contrôle), reprise pour la ligne principale |
| R06 | cendres | 8 | % MS | Hypothèse | — | palmes de palmier, résidu herbacé riche en minéraux |
| R06 | pci | 16,5 | MJ/kg | Hypothèse | — | palmes de palmier |
| R06 | f_col | 0,7 | fraction | Hypothèse | — | palmes dispersées dans les palmeraies |
| R06 | f_eco | 0,5 | fraction | Hypothèse | — | moitié laissée sur place (paillage, usages locaux) |
| R06 | densite_apparente | 150 | kg/m³ | Hypothèse | — | palmes broyées |
| R06 | k_col | 250 | DH/t MS | Hypothèse | — | ramassage manuel dans les palmeraies |
| R06 | k_pre | 100 | DH/t MS | Hypothèse | — | broyage des palmes |
| R06 | eligible_ebc | oui | — | Hypothèse | — | résidu agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R06 | scenario_reference | brûlage à l'air libre | — | Hypothèse | — | devenir supposé des palmes non valorisées |
| R08 | f_col | 0,9 | fraction | Hypothèse | — | coques produites aux unités de cassage |
| R08 | f_eco | 1 | fraction | Hypothèse | — | coproduit industriel : aucun retour au sol requis |
| R08 | densite_apparente | 350 | kg/m³ | Hypothèse | — | coques en vrac ; aucune densité de coques seules trouvée |
| R08 | k_col | 20 | DH/t MS | Hypothèse | — | chargement à l'unité de cassage |
| R08 | k_pre | 0 | DH/t MS | Hypothèse | — | coques sèches, sans prétraitement |
| R08 | eligible_ebc | oui | — | Hypothèse | — | coproduit de transformation agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R08 | scenario_reference | sans substitution | — | Hypothèse | — | usage actuel comme combustible documenté par aucune source : E_ref = 0 |
| R11 | pci | 14,5 | MJ/kg | Hypothèse | — | balles de riz, riches en silice |
| R11 | f_col | 0,9 | fraction | Hypothèse | — | balles produites aux rizeries |
| R11 | f_eco | 1 | fraction | Hypothèse | — | coproduit industriel : aucun retour au sol requis |
| R11 | densite_apparente | 102,25 | kg/m³ | Hypothèse | [DEMO-JHA-SINGH-2007](https://agris.fao.org/search/en/records/6474734ebf943c8c798305f1) | milieu de 98 à 106,5 kg/m³ (balles non traitées, humidité 5 à 35 %) |
| R11 | k_col | 20 | DH/t MS | Hypothèse | — | chargement à la rizerie |
| R11 | k_pre | 0 | DH/t MS | Hypothèse | — | balles sèches, sans prétraitement |
| R11 | eligible_ebc | oui | — | Hypothèse | — | coproduit de transformation agricole, supposé sur la liste positive EBC (à vérifier, SRC-14) |
| R11 | scenario_reference | sans substitution | — | Hypothèse | — | usage actuel comme combustible documenté par aucune source : E_ref = 0 |

### Concurrence d'usage et prix d'achat, niveau national (data/input/concurrence.csv)

| Code | Paramètre | Valeur | Unité | Statut | Source | Justification |
|---|---|---|---|---|---|---|
| R01 | part_utilisee | 0,3 | fraction | Hypothèse | — | part supposée déjà utilisée (bois de feu) |
| R01 | prix_achat_dh_t | 0 | DH/t | Hypothèse | — | taille aujourd'hui sans valeur marchande (section 8.2) |
| R02 | part_utilisee | 0,2 | fraction | Hypothèse | — | part supposée déjà utilisée (bois de feu) |
| R02 | prix_achat_dh_t | 0 | DH/t | Hypothèse | — | taille aujourd'hui sans valeur marchande (section 8.2) |
| R03 | part_utilisee | 0,3 | fraction | Hypothèse | — | part supposée déjà utilisée (bois de feu) |
| R03 | prix_achat_dh_t | 0 | DH/t | Hypothèse | — | sarments aujourd'hui sans valeur marchande (section 8.2) |
| R04 | part_utilisee | 0,3 | fraction | Hypothèse | — | part supposée déjà utilisée (bois de feu) |
| R04 | prix_achat_dh_t | 0 | DH/t | Hypothèse | — | taille aujourd'hui sans valeur marchande (section 8.2) |
| R05 | part_utilisee | 0,6 | fraction | Hypothèse | — | grignons largement vendus comme combustible |
| R06 | part_utilisee | 0,3 | fraction | Hypothèse | — | part supposée déjà utilisée (artisanat, bois de feu) |
| R06 | prix_achat_dh_t | 0 | DH/t | Hypothèse | — | palmes aujourd'hui sans valeur marchande (section 8.2) |
| R08 | part_utilisee | 0,5 | fraction | Hypothèse | — | coques vendues comme combustible |
| R08 | prix_achat_dh_t | 300 | DH/t | Hypothèse | — | prix supposé du combustible de coques, en vrac |
| R11 | part_utilisee | 0,3 | fraction | Hypothèse | — | part supposée déjà utilisée (litière, combustible) |
| R11 | prix_achat_dh_t | 150 | DH/t | Hypothèse | — | prix supposé des balles en vrac |

### Facteurs d'émission et données d'activité (data/input/facteurs_emission.csv)

| Code | Paramètre | Valeur | Unité | Statut | Source | Justification |
|---|---|---|---|---|---|---|
| gazole_amont | kg_co2e | 0,609 | kg CO₂e/L | Littérature | [DEMO-ADEME-BC-23-5](https://www.banque-france.fr/system/files/2026-06/Methodologie_fret.pdf) | Base Carbone ADEME v23.5, gazole routier, production du carburant en amont (cité par la méthodologie fret de la Banque de France) |
| broyage | consommation_electricite | 30 | kWh/t MS | Hypothèse | — | broyeur électrique fixe |
| pyrolyse | kg_ch4_bio | 0,5 | kg/t biochar | Hypothèse | — | pyrolyse avec combustion des gaz, émissions résiduelles faibles |
| pyrolyse | kg_n2o | 0,05 | kg/t biochar | Hypothèse | — | pyrolyse avec combustion des gaz, émissions résiduelles faibles |
| pyrolyse | consommation_electricite | 150 | kWh/t biochar | Hypothèse | — | auxiliaires du réacteur (alimentation, ventilation) |
| collecte | consommation_gazole | 3 | L/t MS | Hypothèse | — | tracteur et broyeur de ramassage |
| epandage | consommation_gazole | 2 | L/t biochar | Hypothèse | — | épandeur agricole |
| transport_biochar | distance_km | 50 | km | Hypothèse | — | distance moyenne supposée de l'usine aux parcelles des clients |

### Mois de disponibilité (data/input/calendrier.csv, table vide)

| Résidu | Jan | Fév | Mar | Avr | Mai | Juin | Juil | Août | Sep | Oct | Nov | Déc | Statut | Justification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R01 | 0,25 | 0,25 | 0,25 | 0,25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Hypothèse | taille après la récolte des olives, janvier à avril |
| R02 | 0 | 0,25 | 0,25 | 0,25 | 0,25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Hypothèse | taille des agrumes, février à mai |
| R03 | 0,34 | 0,33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,33 | Hypothèse | taille de la vigne, décembre à février |
| R04 | 0,25 | 0,25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,25 | 0,25 | Hypothèse | taille de l'amandier, novembre à février |
| R05 | 0,3 | 0,2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,2 | 0,3 | Hypothèse | campagne de trituration, novembre à février |
| R06 | 0,09 | 0,09 | 0,09 | 0,09 | 0,08 | 0,08 | 0,08 | 0,08 | 0,08 | 0,08 | 0,08 | 0,08 | Hypothèse | palmes taillées toute l'année |
| R08 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,2 | 0,2 | 0,2 | 0,2 | 0,2 | Hypothèse | cassage après la récolte, août à décembre |
| R11 | 0,25 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,25 | 0,25 | 0,25 | Hypothèse | usinage du riz, octobre à janvier |

## Limites connues

- R07, R09, R10, R12 et R13 restent bloqués (humidité, ratio ou production manquants).
- Les parts déjà utilisées (u), les coûts de collecte hors taille d'olivier et le calendrier
  sont des hypothèses sans source : ils pèsent sur le gisement mobilisable, le coût livré et le
  critère A4.
