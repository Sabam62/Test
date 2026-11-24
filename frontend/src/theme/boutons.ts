/**
 * Styles des boutons (section 12.5), partagés par les boutons et les liens qui en ont l'aspect.
 * Primaire : fond vert foncé de la marque (#02865B), texte blanc, contraste 4,6:1 (AA, vérifié
 * par src/test/contrastes.test.ts) ; au survol, green-900. Secondaire : fond blanc bordé.
 */
export const STYLE_BOUTON_PRIMAIRE =
  "bg-marque-fonce text-white hover:bg-green-900 transition-colors duration-courte";

export const STYLE_BOUTON_SECONDAIRE = "border border-line bg-card text-ink hover:bg-paper";
