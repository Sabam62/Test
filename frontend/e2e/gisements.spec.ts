import { expect, test } from "@playwright/test";

/** Écran Gisements (lot 2, UC-POT-02 et 03) sur la copie d'essai des données réelles. */

test("la carte des 75 provinces s'affiche avec ses filtres", async ({ page }) => {
  await page.goto("/gisements");
  await expect(
    page.getByRole("heading", { level: 2, name: /Gisement théorique : 75 provinces sur 75/ }),
  ).toBeVisible();
  await expect(page.getByRole("img", { name: /Carte des gisements/ })).toBeVisible();
  await expect(page.getByLabel("Légende")).toContainText("t MS/an");
  // Un résidu bloqué faute d'humidité : aucune province calculée, motif listé.
  await page.getByRole("combobox", { name: "Résidu" }).selectOption("R10");
  await expect(
    page.getByRole("heading", { level: 2, name: /0 provinces sur 75 calculées/ }),
  ).toBeVisible();
  await expect(page.getByText(/R10 · humidite à compléter/).first()).toBeVisible();
  // Gisement mobilisable : bloqué par f_col, f_eco et u dans les données livrées.
  await page.getByRole("combobox", { name: "Résidu" }).selectOption("R01");
  await page.getByRole("combobox", { name: "Indicateur" }).selectOption("M");
  await expect(
    page.getByRole("heading", { level: 2, name: /Gisement mobilisable : 0 provinces/ }),
  ).toBeVisible();
});

test("totaux nationaux, histogramme et provenance d'une cellule du tableau", async ({ page }) => {
  await page.goto("/gisements");
  const totaux = page.getByRole("region", { name: "Totaux nationaux" });
  await expect(totaux).toContainText("Gisement théorique (national)");
  await expect(totaux).toContainText("à compléter");
  await expect(
    page.getByRole("heading", { name: /Gisement théorique national par résidu/ }),
  ).toBeVisible();
  const tableau = page.getByRole("table", { name: /par province et par résidu/ });
  await tableau
    .getByRole("button", { name: /voir la provenance/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("SRC-16-ZARAGOZA");
});
