import type { Config } from "tailwindcss";

import { couleurs, couleursAxes, marque } from "./src/theme/couleurs";
import { durees, ombre, rayons } from "./src/theme/forme";
import { polices, tailles } from "./src/theme/typographie";

/**
 * Tailwind est restreint aux jetons de la section 12 : palette, polices, tailles, rayons et
 * ombre remplacent ceux de Tailwind, pour qu'aucune valeur hors charte ne soit disponible.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: couleurs.card,
      ink: couleurs.ink,
      charcoal: couleurs.charcoal,
      paper: couleurs.paper,
      card: couleurs.card,
      line: couleurs.line,
      muted: couleurs.muted,
      green: couleurs.green,
      ember: couleurs.ember,
      up: couleurs.up,
      axe: couleursAxes,
      marque,
    },
    fontFamily: {
      titre: [...polices.titre],
      texte: [...polices.texte],
    },
    fontSize: tailles as unknown as NonNullable<Config["theme"]>["fontSize"],
    borderRadius: { none: "0", ...rayons, full: "9999px" },
    boxShadow: { none: "none", douce: ombre },
    extend: {
      transitionDuration: { courte: durees.courte, longue: durees.longue },
    },
  },
  plugins: [],
} satisfies Config;
