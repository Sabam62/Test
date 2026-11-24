/**
 * Typographie de la section 12.4 du cahier des charges.
 *
 * Titres : General Sans (Fontshare), graisse 500, interlettrage −2 %. Le fichier de la police
 * se télécharge à la main (licence Fontshare à accepter, docs/donnees_manuelles.md) : tant qu'il
 * n'est pas déposé dans src/theme/polices/, les titres utilisent Geist, embarquée.
 * Texte et chiffres : Geist (licence OFL), graisses 400 et 500, embarquée en woff2.
 */
export const polices = {
  titre: ['"General Sans"', "Geist", "system-ui", "sans-serif"],
  texte: ["Geist", "system-ui", "sans-serif"],
} as const;

/** Tailles en px : titres 56 / 40 / 28 / 20, texte 15, secondaire 13, sources 11. */
export const tailles = {
  "titre-1": ["56px", { lineHeight: "1.05", letterSpacing: "-0.02em", fontWeight: "500" }],
  "titre-2": ["40px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "500" }],
  "titre-3": ["28px", { lineHeight: "1.15", letterSpacing: "-0.02em", fontWeight: "500" }],
  "titre-4": ["20px", { lineHeight: "1.25", letterSpacing: "-0.02em", fontWeight: "500" }],
  indicateur: ["26px", { lineHeight: "1.1" }],
  valeur: ["20px", { lineHeight: "1.2" }],
  texte: ["15px", { lineHeight: "1.5" }],
  libelle: ["12px", { lineHeight: "1.4" }],
  secondaire: ["13px", { lineHeight: "1.45" }],
  source: ["11px", { lineHeight: "1.4" }],
} as const;
