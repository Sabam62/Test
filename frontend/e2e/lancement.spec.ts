import { expect, test } from "@playwright/test";

test("l'outil lancé sert l'interface compilée et ses routes", async ({ page }) => {
  await page.goto("/");
  // Aucune fenêtre surgissante au premier lancement (RG-15) : un badge sur l'onglet Paramètres.
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Paramètres 4 à renseigner/ })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("provinces");
  await page.goto("/donnees");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Données du");
});
