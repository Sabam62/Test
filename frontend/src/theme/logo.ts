/**
 * Logo d'Atlantic Biochar (fonds transparents), déposé dans src/theme/logo/.
 *
 * Le SVG officiel sera fourni par l'entreprise sous les noms atlantic-biochar.svg (logo complet)
 * et atlantic-biochar-symbole.svg (symbole seul), au même endroit : il remplacera alors le PNG
 * sans modification du code. En attendant, les PNG sont utilisés.
 */
const fichiers = import.meta.glob<string>("./logo/*.{svg,png}", {
  eager: true,
  query: "?url",
  import: "default",
});

function choisir(nom: string): string {
  const svg = fichiers[`./logo/${nom}.svg`];
  const png = fichiers[`./logo/${nom}.png`];
  const url = svg ?? png;
  if (url === undefined) throw new Error(`Logo introuvable : src/theme/logo/${nom}.svg ou .png`);
  return url;
}

/** Logo complet (symbole et logotype « Atlantic Biochar ») : écran d'accueil. */
export const logo = choisir("atlantic-biochar");
/** Symbole seul : barre de navigation et icône de l'onglet du navigateur. */
export const symbole = choisir("atlantic-biochar-symbole");
