import { test } from "@playwright/test";

/**
 * Captures de chaque écran à 1280 et 1920 px, comparées à la section 12 du cahier avant de
 * passer à l'écran suivant (CLAUDE.md). Écrites dans test-results/captures/ (non versionné).
 */
const ECRANS = [
  ["accueil", "/"],
  ["gisements", "/gisements"],
  ["sites", "/sites"],
  ["bilan-climat", "/bilan-climat"],
  ["decision", "/decision"],
  ["melange", "/melange"],
  ["fiche-site", "/fiche-site"],
  ["parametres", "/parametres"],
  ["donnees", "/donnees"],
] as const;
const LARGEURS = [1280, 1920] as const;
const filtre = process.env.ECRAN;

for (const [nom, chemin] of ECRANS) {
  if (filtre && filtre !== nom) continue;
  for (const largeur of LARGEURS) {
    test(`capture ${nom} ${String(largeur)} px`, async ({ page }) => {
      const erreurs: string[] = [];
      page.on("pageerror", (e) => erreurs.push(e.message));
      page.on("console", (m) => {
        if (m.type() === "error" || m.type() === "warning") erreurs.push(m.text());
      });
      await page.setViewportSize({ width: largeur, height: 900 });
      await page.goto(chemin);
      await page.getByRole("heading", { level: 1 }).waitFor();
      // Attend les réponses de l'API (premier calcul à froid), puis les tuiles satellite.
      await page.waitForLoadState("networkidle", { timeout: 60_000 });
      await page.waitForTimeout(2500);
      await page.screenshot({
        path: `test-results/captures/${nom}-${String(largeur)}.png`,
        fullPage: true,
      });
      // Les erreurs de la page sont affichées dans le compte rendu du test.
      for (const erreur of erreurs) console.log(`[${nom}] ${erreur.slice(0, 300)}`);
    });
  }
}
