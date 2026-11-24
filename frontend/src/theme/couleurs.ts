/**
 * Jetons de couleur de la section 12.3 du cahier des charges.
 * Seul endroit de l'interface où une couleur est écrite en valeur hexadécimale.
 */
export const couleurs = {
  ink: "#121212",
  charcoal: "#1E1E1C",
  paper: "#F6F5F1",
  card: "#FFFFFF",
  line: "#E7E5DF",
  muted: "#6E6B64",
  green: {
    900: "#234A2A",
    700: "#2F6B33",
    500: "#4F9A3C",
    200: "#D3E8A4",
  },
  ember: "#E2622B",
  up: "#2F6B33",
} as const;

/**
 * Couleurs de la marque, relevées sur le logo d'Atlantic Biochar (section 12.3).
 * Contrastes WCAG vérifiés par src/test/contrastes.test.ts :
 * - principal (#02A855) : couleur principale ; surfaces, icônes, traits et repères sur fond
 *   blanc (3,1:1, seuil des éléments graphiques) ; texte en mode sombre (5,4:1 sur charcoal) ;
 *   fond d'un texte ink (6,0:1). Jamais en texte courant sur fond clair.
 * - fonce (#02865B) : seul vert lisible en texte sur carte blanche (4,6:1, AA) ; fond des
 *   boutons primaires, texte blanc (4,6:1).
 * - clair (#1ECD64) : accent du mode sombre (7,9:1 sur charcoal) ; décoratif sur fond clair.
 * - gris (#7A7A7C) : gris du logotype ; le texte secondaire reste en muted.
 */
export const marque = {
  principal: "#02A855",
  clair: "#1ECD64",
  fonce: "#02865B",
  gris: "#7A7A7C",
} as const;

/** Une couleur par axe de critères (A à G), identique dans tous les graphiques. */
export const couleursAxes = {
  A: "#2F6B33",
  B: "#8A6D3B",
  C: "#3D7DCA",
  D: "#1F8A70",
  E: "#D9A21B",
  F: "#5E6A75",
  G: "#7A5BA6",
} as const;

export type Axe = keyof typeof couleursAxes;

/**
 * Classes de la carte des gisements (choroplèthe), de la plus faible à la plus forte : nuances
 * de vert de la section 12.3 et vert de la marque. Une province sans valeur reste en paper.
 */
export const classesGisement = [
  couleurs.green[200],
  couleurs.green[500],
  marque.principal,
  couleurs.green[700],
  couleurs.green[900],
] as const;

/**
 * Classes de rang de la carte des sites (section 11.2.3), du meilleur rang au moins bon : du vert
 * foncé de la marque au vert très clair, interpolés à pas égal dans l'espace CIELAB (écart
 * ΔE76 ≈ 14,5 entre deux classes voisines, vérifié par src/test/contrastes.test.ts). Un site
 * exclu reste en muted.
 */
export const classesRang = [marque.fonce, "#52A17C", "#84BD9F", "#B3D9C4", "#E3F5E9"] as const;

/** Couleur du numéro de rang posé sur une épingle de chaque classe (contraste AA, 4,5:1). */
export const texteClassesRang = [
  couleurs.card,
  couleurs.ink,
  couleurs.ink,
  couleurs.ink,
  couleurs.ink,
] as const;
