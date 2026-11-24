import { expect, test } from "@playwright/test";

/**
 * Écrans Décision et Mélange (lot 5, UC-DEC-01, 02, 04, 06, UC-MIX-01) sur la copie d'essai.
 *
 * Les quatre paramètres obligatoires de l'entreprise sont saisis par l'API comme des « saisies
 * simulées pour le test » (RG-15 : l'outil ne les suppose jamais), puis remis à vide.
 */

const AUTEUR = "test de bout en bout";
const OBLIGATOIRES = { "PAR-01": 20000, "PAR-21": 600, "PAR-34": 900, "PAR-37": 12 };

test.afterAll(async ({ request }) => {
  await request.delete("/api/decision/reglages");
  await request.put("/api/entreprise", {
    data: {
      auteur: AUTEUR,
      valeurs: { "PAR-01": null, "PAR-21": null, "PAR-34": null, "PAR-37": null },
    },
  });
});

test("sans paramètres obligatoires, la décision renvoie à Paramètres", async ({ page }) => {
  await page.goto("/decision");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    /attend 4 paramètres obligatoires/,
    { timeout: 60_000 }, // premier calcul à froid des gisements, distances et bilans
  );
});

test("classement, robustesse et mise à jour après un changement de prix plafond", async ({
  page,
  request,
}) => {
  expect(
    (
      await request.put("/api/entreprise", { data: { auteur: AUTEUR, valeurs: OBLIGATOIRES } })
    ).ok(),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/decision");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/est 1er sur/, {
    timeout: 60_000,
  });
  await expect(page.getByText(/Classement partiel : \d+ critères sur \d+/).first()).toBeVisible();
  // Carte des sites colorée par rang (§11.2.3) : bandeau sur la carte, info-bulle, fiche au clic.
  const carte = page.getByRole("img", { name: "Carte des sites candidats colorés par rang" });
  await expect(carte).toBeVisible();
  await expect(page.getByRole("status", { name: "Classement partiel" })).toHaveCount(2);
  await expect(page.getByRole("list", { name: "Légende des rangs" })).toContainText("rangs 1 à");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "test-results/captures/decision-carte.png", fullPage: true });
  const premier = page.getByRole("button", { name: /· rang 1 · score/ });
  await expect(premier).toHaveCount(1);
  await expect(premier).toHaveText("1"); // les 5 premiers portent leur numéro de rang
  await expect(page.getByRole("button", { name: /· rang 5 · score/ })).toHaveText("5");
  await expect(page.getByRole("button", { name: /· rang 6 · score/ })).toHaveText("");
  await premier.click();
  await expect(page).toHaveURL(/\/fiche-site\?site=/);
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/est 1er sur/, {
    timeout: 30_000,
  });
  const debut = Date.now();
  await page.getByRole("button", { name: "TOPSIS" }).click();
  await expect(page.getByRole("button", { name: "TOPSIS" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/est 1er sur/);
  expect(Date.now() - debut).toBeLessThan(2000 + 1500); // classement < 2 s, plus le rendu
  await page.getByRole("button", { name: "Lancer l'analyse de robustesse" }).click();
  await expect(page.getByRole("table", { name: "Robustesse du classement" })).toBeVisible({
    timeout: 30_000,
  });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "test-results/captures/decision-classement.png", fullPage: true });

  await page.getByRole("tab", { name: "Classement des gisements" }).click();
  await expect(page.getByRole("heading", { name: /gisements/ }).first()).toBeVisible();
  await expect(page.getByText(/Classement partiel : \d+ critères sur \d+/).first()).toBeVisible({
    timeout: 30_000,
  });
  await page.screenshot({ path: "test-results/captures/decision-gisements.png", fullPage: true });

  // Prix plafond modifié : le classement est recalculé et garde la variation de rang (RG-16).
  expect(
    (
      await request.put("/api/entreprise", { data: { auteur: AUTEUR, valeurs: { "PAR-34": 600 } } })
    ).ok(),
  ).toBeTruthy();
  const apres = (await (await request.get("/api/decision/classement")).json()) as {
    bloque: boolean;
    classement: { variation: number | null }[];
  };
  expect(apres.bloque).toBe(false);
  expect(apres.classement.every((s) => s.variation !== null)).toBe(true);

  await page.goto("/");
  await expect(page.getByText(/est 1er sur \d+ sites/).first()).toBeVisible({ timeout: 30_000 });

  await page.goto("/melange");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Mélange|mélange/);
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: "test-results/captures/melange-bloque.png", fullPage: true });
});
