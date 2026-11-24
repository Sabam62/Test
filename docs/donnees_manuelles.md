# Données à déposer à la main

Certaines sources ne se téléchargent pas par script : consultation web, compte obligatoire,
documents dispersés, données internes. D'autres se téléchargent par script mais peuvent échouer
(site fermé aux robots, coupure réseau) : leur procédure de secours figure aussi ici.

**Règles communes**

- Déposez chaque fichier, tel quel et sans le modifier (RG-01), dans le dossier indiqué.
- Deux dossiers : `data/raw/<source>/` reçoit les documents téléchargés ou archivés (non
  versionnés, licences et tailles) ; `data/manuelles/<source>/` reçoit les tables saisies par
  l'équipe (CSV), versionnées dans Git pour qu'une installation neuve les ait d'emblée.
- Respectez le nom de fichier attendu : c'est lui que lit `python -m scripts.prepare`.
- Relancez ensuite `python -m scripts.download` : il inscrit chaque fichier déposé dans
  `data/sources.yaml` avec sa taille et son empreinte SHA-256 (RG-05), sans le modifier.
- Notez la source exacte (adresse, document, date de consultation) : elle sera demandée lors de
  la saisie ou de l'import (RG-18).

Adresses vérifiées le 22/11/2026.

---

## Sources téléchargées par le script (procédure de secours)

## SRC-01 · Open Data Maroc, Production végétale 2010-2022

- Page : <https://data.gov.ma/data/fr/dataset/production-vegetale-2010-2022>
- Fichier à prendre : « 20230714-Production végétale 2010-2022.xlsx »
- Déposer sous : `data/raw/SRC-01/production_vegetale_2010_2022.xlsx`

## SRC-04 · CROPGRIDS

- Page : <https://figshare.com/articles/dataset/CROPGRIDS/22491997>
- Fichiers à prendre, sous leur nom d'origine : `CROPGRIDSv1.08_NC_maps.zip` (environ 807 Mo),
  `CODES.zip`, `Table_CROPGRIDSv1.08_COU.xlsx`
- Déposer dans : `data/raw/SRC-04/`
- `python -m scripts.decouper_cropgrids` en extrait l'emprise du Maroc dans
  `data/processed/cropgrids_maroc.nc` ; l'archive mondiale n'est ensuite plus lue, et le script
  la retélécharge si elle a été supprimée alors que le découpage manque. Le manifeste lie
  l'archive supprimée à ce découpage (`remplace_par`) : sur une installation neuve, sans
  découpage, `python -m scripts.download` télécharge donc l'archive.

## SRC-05 · HDX, frontières administratives du Maroc (HCP)

- Page : <https://data.humdata.org/dataset/cod-ab-mar> (l'ancienne adresse du cahier,
  `morocco-administrative-boundaries-populated-places`, n'est plus servie par l'API)
- Fichiers à prendre, sous leur nom d'origine : `mar_admin_boundaries.shp.zip`,
  `mar_admin_boundaries.xlsx`
- Déposer dans : `data/raw/SRC-05/`

## SRC-06 · Geofabrik, extrait OpenStreetMap du Maroc

- Page : <https://download.geofabrik.de/africa/morocco.html>
- Fichier à prendre : `morocco-latest.osm.pbf` (environ 245 Mo ; utile au lot 3)
- Déposer sous : `data/raw/SRC-06/morocco-latest.osm.pbf`

## SRC-09 · HCP, RGPH 2024, population légale

- Page : <https://www.hcp.ma/Population-legale-du-Royaume-du-Maroc-repartie-par-regions-provinces-et-prefectures-et-communes-selon-les-resultats-du_a3974.html>
- Fichier à prendre : lien « format EXCEL » (<https://www.hcp.ma/file/242341/>)
- Déposer sous : `data/raw/SRC-09/rgph2024_population_legale.xlsx`

## SRC-19 · HCP, cartes du RGPH (12 régions, 75 provinces)

- Service : `http://rgphencartes.hcp.ma/geoserver/wfs` (couches `RGPH:regions` et
  `RGPH:provinces`, visionneuse <http://rgphencartes.hcp.ma/>). Le service ne répond qu'en `http`.
- Adresses exactes (GeoJSON, coordonnées natives, codes et géométrie seulement) :
  - `http://rgphencartes.hcp.ma/geoserver/wfs?service=WFS&version=1.0.0&request=GetFeature&outputFormat=application/json&typeName=RGPH:regions&propertyName=code_reg,the_geom`
  - `http://rgphencartes.hcp.ma/geoserver/wfs?service=WFS&version=1.0.0&request=GetFeature&outputFormat=application/json&typeName=RGPH:provinces&propertyName=code_reg,code_prov,the_geom`
- Déposer sous : `data/raw/SRC-19/hcp_regions_natif.geojson` et
  `data/raw/SRC-19/hcp_provinces_natif.geojson`
- **Ne pas demander `srsName=EPSG:4326`** : la reprojection du service décale les polygones de
  15 à 30 km vers le nord. Les coordonnées natives sont lues en EPSG:3857
  (`crs_natif_polygones` dans `config/referentiel.yaml`).
- Licence : non déclarée par le HCP ; usage interne et académique, source citée, sans
  redistribution publique des cartes. Attribution « © Haut-Commissariat au Plan » sous chaque
  carte. Les attributs datent du RGPH 2014 : seuls les géométries et les codes sont utilisés.

### Solution de secours en cas de diffusion publique : geoBoundaries (examinée, non intégrée)

Vérification du 22/11/2026, API <https://www.geoboundaries.org/api/current/gbOpen/MAR/ADM2/> :

- Licence ODbL 1.0 (source : OpenStreetMap, Wambacher), année représentée 2017.
- ADM1 : 12 régions, géométries valides ; correspondance un à un avec les 12 régions du HCP.
- ADM2 : 75 unités annoncées, dont les 6 provinces du Sud, mais **pas de correspondance un à un**
  avec les 75 provinces du HCP : 7 provinces du HCP (Casablanca, Fahs-Anjra, M'diq-Fnideq,
  Médiouna, Mohammadia, Nador, Rabat) ne tombent dans aucune unité, et des polygones débordent
  sur la province voisine (Sidi Kacem contient Meknès et Sidi Slimane, Kénitra contient Salé,
  Taounate contient Moulay Yacoub, Tiznit contient Sidi Ifni, Agadir contient Inezgane).
- Conclusion : utilisable pour les régions ; pour les provinces, les polygones seraient à
  reprendre avant toute diffusion publique.

---

## Sources à déposer à la main

## SRC-18 · Communiqués des DRA et DPA (production provinciale)

Indispensable à la condition de fin du lot 1 : production et superficie par culture et par
province, pour les 12 régions (olivier, agrumes, vigne, amandier et rosacées, palmier dattier,
tomate sous serre, riz, betterave, céréales, arganier).

- Où chercher : communiqués et monographies des directions régionales et provinciales de
  l'agriculture, articles de presse qui les reprennent (exemple réel : production d'olives
  2017-2018 de Fès-Meknès, <https://www.infomediaire.net/?p=80746>).
- Documents archivés, dans : `data/raw/SRC-18/` (hors de Git), un fichier par document, sous le nom
  `<region>_<campagne>_<culture>.<pdf|html>` en minuscules sans accents, par exemple
  `fes-meknes_2017-2018_olivier.html` (page web enregistrée au format HTML complet). Ces fichiers
  ne sont jamais modifiés (RG-01). Ils ne sont pas lus par la préparation : ce sont les pièces
  justificatives des valeurs saisies, et leur adresse d'origine figure dans `references.csv`.
- Tables saisies par l'équipe, dans `data/manuelles/SRC-18/` (versionnées dans Git ; c'est là
  que `python -m scripts.prepare` les lit) :
- `references.csv` (séparateur `;`), une ligne par document :
  `fichier;url;organisme;date_publication;date_consultation;source_parente`
  (`source_parente` : SRC-18, ou SRC-03 pour une monographie du HCP).
- `valeurs_saisies.csv`, une ligne par valeur citée :
  `fichier;niveau;region;province;inclut;culture;campagne;periode;variable;valeur;unite;nature;methode;indice;remarque`
  - `niveau` : province, region ou national ; `inclut` : provinces comptées ensemble, séparées
    par `;` (par exemple « Fès;Moulay Yacoub ») ;
  - `periode` : campagne, annee_civile (la récolte d'automne de l'année Y relève de la campagne
    Y-(Y+1), RG-04), non_precisee ou moyenne (ces deux dernières ne sont pas utilisées) ;
  - `variable` : production (t), superficie_totale (ha), superficie_productive (ha) ou
    part_production_nationale (%) ; `nature` : realisee ou previsionnelle ;
  - `indice` : le texte exact de la valeur dans la page, pour la vérification.
- `valeurs_verifiees.csv` : les mêmes colonnes, plus `extrait` (phrase de la page qui contient la
  valeur) et `verification`. Seules les lignes dont la vérification commence par « vérifiée »
  sont utilisées ; les autres sont rejetées et listées dans le rapport de contrôle.
- Puis lancer `python -m scripts.prepare` : le rapport `data/processed/rapport_controle.html`
  classe chaque ligne (valide, rejetée, doublon, aberrante, non utilisée) avec son motif.

## SRC-02 · Statagri (ministère de l'Agriculture)

- Adresse : <http://statagri.agriculture.gov.ma:9090/statistic> (lien du site du ministère ;
  le serveur n'a pas répondu au script le 22/11/2026).
- À vérifier d'abord : la maille (région ou province) et la possibilité d'export.
- Déposer dans : `data/raw/SRC-02/`, sous le nom `statagri_<culture>_<maille>.<xlsx|csv>`.

## SRC-03 · HCP, Annuaire statistique et Le Maroc en chiffres

- Annuaires (Excel) : <https://www.hcp.ma/downloads/?tag=Annuaires+statistiques+du+Maroc+%28Format+Excel%29>
- Le Maroc en chiffres : <https://www.hcp.ma/downloads/Maroc-en-chiffres_t13053.html>
- Déposer dans : `data/raw/SRC-03/`, sous les noms `annuaire_statistique_<annee>.xlsx` et
  `maroc_en_chiffres_<annee>.pdf` (dernières éditions).

## SRC-08 · Base Phyllis

- Adresse : <https://phyllis.nl/> (l'adresse du cahier, `ecn.nl/phyllis2`, y redirige).
- Pour R01 à R13 : humidité, carbone, cendres, PCI et numéro de l'échantillon Phyllis.
- Déposer sous : `data/raw/SRC-08/phyllis_echantillons.csv` (séparateur `;`), colonnes
  `code_residu;numero_phyllis;nom_echantillon;humidite;carbone;cendres;pci;base;date_consultation`
  (`base` : brute, sèche ou sèche sans cendres, telle qu'affichée par Phyllis).

### Valeurs de la littérature intégrées le 22/11/2026

`data/manuelles/SRC-08/litterature_residus.csv` (40 valeurs saisies par l'équipe) a été vérifié
contre les pages archivées dans `data/raw/SRC-08/pages/` (hors de Git) ; le résultat ligne par
ligne est dans `data/manuelles/SRC-08/valeurs_verifiees.csv`. Ces deux tables sont la trace de la
saisie : la préparation ne les lit pas, les valeurs retenues étant dans `data/input/`. 28 valeurs sont intégrées (dont 3 de contrôle) dans `residus.csv` et
`concurrence.csv` (sources `SRC-16-…` de `data/sources.yaml`). Règles appliquées :

- un PCS est stocké comme PCS (paramètre `pcs`), jamais converti en PCI ;
- deux valeurs pour la même grandeur : celle en base sèche est retenue, l'autre est gardée avec
  la précision « contrôle » et n'entre pas dans les calculs ;
- une page inaccessible (protection anti-robot de CORE, Cahiers Agricultures, WPI) laisse la
  valeur « À compléter » : Velázquez-Martí 2017 (humidité R01, R02, R04), Nasser 2016
  (carbone, cendres, PCS de R06 et R07), Reinoso Moreno 2019 (humidité R10), WPI 2018 (R09) ;
- la valeur de cendres TISTR des balles de riz (9,989 %) ne figure pas dans la page : non intégrée.

## SRC-14 · Liste positive EBC

- Adresse : <https://www.european-biochar.org/en/ct/2>
- Déposer sous : `data/raw/SRC-14/ebc_liste_positive_<version>.pdf` (version en vigueur).

## SRC-15 · Facteurs d'émission (ADEME, GIEC)

- Base Empreinte (compte gratuit obligatoire) : <https://base-empreinte.ademe.fr/> ; exporter
  les facteurs du gazole (combustion et amont) et des machines, sous
  `data/raw/SRC-15/base_empreinte_<date>.csv`.
- GIEC 2006, volume 2 (énergie) : <https://www.ipcc-nggip.iges.or.jp/public/2006gl/vol2.html> ;
  chapitre 3 (combustion mobile), sous `data/raw/SRC-15/giec2006_v2_ch3.pdf`.

## SRC-17 · Enquête de terrain

- Données internes de l'équipe : part déjà utilisée, prix d'achat et nombre d'acheteurs par
  province et par résidu.
- Déposer sous : `data/raw/SRC-17/enquete_<AAAA-MM>.csv` (séparateur `;`), colonnes
  `code_province;code_residu;part_utilisee;prix_achat_dh_t;date;enqueteur;note`.
  Sans enquête, ces valeurs restent « À compléter » (RG-14).

## Calendrier de disponibilité des résidus

- Aucune source n'est citée par le cahier : mois de collecte de chaque résidu, avec la
  publication ou l'enquête qui les donne.
- Déposer le document source dans `data/raw/calendrier/` ; les valeurs seront saisies dans
  `data/input/calendrier.csv` avec leur source (tâche 5).

## Polices et identité visuelle (tâche 10)

- General Sans (Fontshare, licence à accepter) : <https://www.fontshare.com/fonts/general-sans>.
  Déposer `GeneralSans-Medium.woff2` dans `frontend/src/theme/polices/`, puis ajouter sa règle
  `@font-face` en tête de `frontend/src/index.css` (sur le modèle de Geist) et recompiler
  l'interface. En attendant, les titres utilisent Geist, embarquée.
- Logo d'Atlantic Biochar : PNG déposés le 22/11/2026 dans `frontend/src/theme/logo/`
  (`atlantic-biochar.png`, `atlantic-biochar-symbole.png`). Le SVG officiel, demandé à
  l'entreprise, se dépose au même endroit sous `atlantic-biochar.svg` et
  `atlantic-biochar-symbole.svg` : il remplace alors le PNG sans modification du code (recompiler
  l'interface).

---

## À anticiper (hors lot 1)

- Devis de transporteurs : coût fixe par rotation (PAR-61).
- Fiche technique du camion retenu : volume utile (PAR-32).
- Coordonnées sourcées des agropoles (sites candidats, lot 3).
