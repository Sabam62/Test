import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Écran Bilan climat (lot 4, UC-ACV-01 à 03) sur la copie d'essai des données réelles.
 *
 * Dans les données livrées, les facteurs du gazole, de la pyrolyse et du brûlage, les données
 * d'activité et le scénario de référence sont « À compléter » : ils sont saisis ici par l'API
 * comme des « saisies simulées pour le test », sur la copie d'essai seulement, puis tout est
 * remis dans l'état livré.
 */

const SIMULE = "saisie simulée pour le test";
const AUTEUR = "test de bout en bout";

async function saisir(
  requete: APIRequestContext,
  table: string,
  cle: Record<string, string>,
  valeur: string,
) {
  const reponse = await requete.put(`/api/donnees/tables/${table}/valeur`, {
    data: { auteur: AUTEUR, commentaire: SIMULE, cle, valeur, source: SIMULE, date: "2026-11-23" },
  });
  expect(reponse.ok(), await reponse.text()).toBeTruthy();
}

let versionInitiale = "";

test.beforeAll(async ({ request }) => {
  const journal = (await (await request.get("/api/donnees/versions")).json()) as {
    id_version: string;
  }[];
  versionInitiale = journal[0]?.id_version ?? "";
});

test.afterAll(async ({ request }) => {
  if (versionInitiale) {
    await request.post(`/api/donnees/versions/${versionInitiale}/restaurer`, {
      data: { auteur: AUTEUR, commentaire: "retour à l'état livré après le test" },
    });
  }
  await request.delete("/api/parametres/PAR-32");
  await request.put("/api/entreprise", { data: { auteur: AUTEUR, valeurs: { "PAR-21": null } } });
});

test("sans saisies, le bilan liste les valeurs à saisir", async ({ page }) => {
  await page.goto("/bilan-climat");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/attend/, {
    timeout: 30_000,
  });
  await expect(page.getByText(/valeurs à saisir pour calculer les bilans/)).toBeVisible();
  await expect(page.getByText(/Unité fonctionnelle : 1 t de biochar/)).toBeVisible();
});

test("bilan par résidu et contributions affichés", async ({ page, request }) => {
  for (const [activite, parametre, valeur] of [
    ["gazole_amont", "kg_co2e", "0.6"],
    ["pyrolyse", "kg_ch4_bio", "0.5"],
    ["pyrolyse", "kg_n2o", "0.01"],
    ["pyrolyse", "consommation_electricite", "150"],
    ["collecte", "consommation_gazole", "2"],
    ["broyage", "consommation_electricite", "30"],
    ["epandage", "consommation_gazole", "3"],
    ["transport_biochar", "distance_km", "40"],
  ] as const)
    await saisir(
      request,
      "facteurs_emission",
      { code_activite: activite, parametre, precision: "" },
      valeur,
    );
  for (const [parametre, valeur] of [
    ["humidite", "30"],
    ["densite_apparente", "150"],
    ["scenario_reference", "brûlage à l'air libre"],
  ] as const)
    await saisir(request, "residus", { code_residu: "R01", parametre, precision: "" }, valeur);
  expect(
    (
      await request.put("/api/parametres/PAR-32", {
        data: { valeur: 90, source: SIMULE, auteur: AUTEUR },
      })
    ).ok(),
  ).toBeTruthy();
  expect(
    (
      await request.put("/api/entreprise", { data: { auteur: AUTEUR, valeurs: { "PAR-21": 600 } } })
    ).ok(),
  ).toBeTruthy();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/bilan-climat");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/retirées par t de biochar/, {
    timeout: 30_000,
  });
  await expect(page.getByText(/Contributions au bilan net/)).toBeVisible();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "test-results/captures/bilan-climat-calcule.png", fullPage: true });
});
