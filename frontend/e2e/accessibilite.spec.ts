import { chromium, expect, test } from "@playwright/test";
import lighthouse from "lighthouse";

/** Score d'accessibilité Lighthouse ≥ 90 sur chaque écran (ENF-16). */
const PORT_DEBOGAGE = 9333;
const SCORE_MINIMAL = 0.9;

for (const chemin of [
  "/",
  "/donnees",
  "/gisements",
  "/sites",
  "/bilan-climat",
  "/decision",
  "/melange",
  "/fiche-site",
  "/parametres",
]) {
  test(`accessibilité Lighthouse de ${chemin}`, async ({ baseURL }) => {
    test.setTimeout(120_000);
    const navigateur = await chromium.launch({
      args: [`--remote-debugging-port=${String(PORT_DEBOGAGE)}`],
    });
    try {
      const resultat = await lighthouse(`${baseURL ?? ""}${chemin}`, {
        port: PORT_DEBOGAGE,
        onlyCategories: ["accessibility"],
        output: "json",
        logLevel: "error",
      });
      const categorie = resultat?.lhr.categories.accessibility;
      const echecs = Object.values(resultat?.lhr.audits ?? {})
        .filter((a) => a.score !== null && a.score < 1 && a.scoreDisplayMode === "binary")
        .map((a) => a.id);
      console.log(
        `${chemin} : accessibilité ${String(categorie?.score)} ; à revoir : ${echecs.join(", ")}`,
      );
      expect(categorie?.score ?? 0).toBeGreaterThanOrEqual(SCORE_MINIMAL);
    } finally {
      await navigateur.close();
    }
  });
}
