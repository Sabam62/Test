# CLAUDE.md — Outil d'aide à la décision Atlantic Biochar

## Rôle
Tu développes l'outil décrit dans le cahier des charges (docs/cahier_des_charges.md).
En cas de doute, ce document fait foi. Ne change pas une règle de gestion (RG-xx),
une formule (section 8) ou un critère (section 9) sans le signaler.

## Données : règle absolue
- Aucune donnée fictive, synthétique ou de démonstration, nulle part.
- Seule exception : le mode « Démonstration » isolé (section 7.2) : scénarios dans
  scenarios/demo/, copie de travail dans data/cache/demo/, paramètres d'hypothèse
  étiquetés et listés dans docs/demo.md, bandeau sur chaque écran et chaque export ;
  il ne modifie jamais les données réelles.
- Les valeurs de référence viennent de la section 14.2, avec leur source.
- Une valeur inconnue reste « À compléter » (RG-14) : ne l'invente jamais.
- Les tests utilisent tests/fixtures/, un extrait figé des données réelles.
- Les paramètres de l'entreprise (section 14.1) ne sont jamais supposés :
  l'onglet Paramètres les signale par un badge et les écrans y renvoient (RG-15).

## Design : règle absolue
- Suis la section 12 (direction artistique, jetons de couleur, typographie,
  composants, interdits) et la maquette docs/design/reference.png.
- Inspire-toi de la maquette sans la copier : nom, logo, textes et données
  sont ceux d'Atlantic Biochar.
- Jamais de dégradés violet-bleu, verre dépoli, émojis, titres creux,
  thème par défaut d'une bibliothèque, ni chiffres de démonstration.
- Chaque titre d'écran énonce un fait calculé sur les données réelles.
- Après chaque écran, fais une capture (Playwright) et compare-la à la
  section 12 avant de passer au suivant.

## Ordre de travail
1. Suis les lots de la section 17 dans l'ordre. Ne commence pas un lot avant que
   les tests du précédent passent.
2. Pour chaque lot : écris d'abord les tests des critères d'acceptation (section 11),
   puis le code de src/, puis la route de api/, puis l'écran de frontend/.
3. Les outils de mise à jour des données (section 7.3) font partie du lot 1 :
   l'entreprise doit pouvoir tout mettre à jour sans écrire de code.

## Règles de code
- Python 3.11, annotations de type, ruff (format + check) sans erreur.
- TypeScript strict, ESLint et Prettier sans erreur.
- src/ ne connaît ni api/ ni frontend/. frontend/ ne contient aucun calcul métier.
- Aucune constante métier en dur : tout vient de config/*.yaml ou de data/.
- Aucune couleur en dur dans un composant : jetons de frontend/src/theme/.
- Chaque valeur garde sa provenance (source_id, annee, statut, version).
- Toute mise à jour de données crée une version (RG-17) ; rien n'est écrasé.
- Interface, messages d'erreur, docstrings et commentaires en français.
- Nombres affichés au format français ; unités dans chaque en-tête.

## Brightway
- Brightway 2.5 sans ecoinvent : base d'avant-plan ab_foreground construite par code,
  flux élémentaires de la biosphère, méthode PRG100 AR6 créée par code (PAR-27).
- Le projet doit s'ouvrir dans Activity Browser 3.

## Commandes
- Installer : conda env create -f environment.yml && conda activate ab-dss
- Télécharger les sources : python -m scripts.download
- Préparer les données : python -m scripts.prepare
- Lancer : python -m ab_dss
- Développer l'interface : cd frontend && npm install && npm run dev
- Compiler l'interface : cd frontend && npm run build
- Tester : pytest --cov=src ; cd frontend && npm test
