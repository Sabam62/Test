/** Rayons, ombre et durées de la section 12.5 et 12.6 du cahier des charges. */
export const rayons = {
  carte: "12px",
  bouton: "8px",
  barre: "6px",
  segment: "2px",
} as const;

/** Ombre maximale autorisée (boutons, cartes). */
export const ombre = "0 1px 2px rgba(0,0,0,0.06)";

/** Transitions de 150 à 200 ms, sans animation décorative. */
export const durees = { courte: "150ms", longue: "200ms" } as const;

/** Voile sombre du hero : seul dégradé autorisé (section 12.3), en transparence de charcoal. */
export const voileHero = "linear-gradient(to top, rgba(30,30,28,0.72), rgba(30,30,28,0) 60%)";
