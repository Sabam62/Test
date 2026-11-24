import { execFileSync } from "node:child_process";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

/**
 * Recette du MVP (section 18.3) sur la copie d'essai des données réelles.
 *
 * Couvert ici : paramètres obligatoires puis classement en 3 clics au plus, changement de prix
 * plafond et de capacité avec variation de rang, Meknès dans le classement et sa fiche, poids
 * modifiés (moins de 2 s), robustesse, scénario enregistré puis rechargé à l'identique, export
 * Excel avec les feuilles « paramètres » et « sources ». Couverts ailleurs : import Excel et
 * restauration, provenance d'une valeur (parcours.spec.ts), prix des grignons et coût livré
 * (tests/test_api_logistique.py). Les paramètres de l'entreprise sont des « saisies simulées pour
 * le test » (RG-15 : l'outil ne les suppose jamais).
 */
test.describe.configure({ mode: "serial" });

const AUTEUR = "test de bout en bout";
const DEPOT = join(import.meta.dirname, "..", "..");

interface Classement {
  bloque: boolean;
  classement: { id_site: string; rang: number; variation: number | null }[];
  criteres: string[];
}

test.afterAll(async ({ request }) => {
  await request.delete("/api/decision/reglages");
});

test("recette 18.3 : du réglage des paramètres à l'export du classement", async ({
  page,
  request,
}, info) => {
  test.setTimeout(240_000); // premier calcul à froid de toute la chaîne
  // Paramètres obligatoires saisis dans l'onglet Paramètres (section Entreprise).
  await page.goto("/parametres#PAR-01");
  await page.locator("#PAR-01").fill("20000");
  await page.locator("#PAR-21").fill("600");
  await page.locator("#PAR-34").fill("900");
  await page.locator("#PAR-37").fill("12");
  await page.getByLabel("Auteur des modifications").fill(AUTEUR);
  await page
    .getByRole("form", { name: "Paramètres obligatoires" })
    .getByRole("button", { name: "Enregistrer" })
    .click();
  await expect(page.getByText(/^\d+ à renseigner$/)).toHaveCount(0);

  // Classement en 3 clics au plus : Accueil (1), « Voir le classement » (2).
  await page.getByRole("navigation").getByRole("link", { name: "Accueil", exact: true }).click();
  await page.getByRole("link", { name: "Voir le classement" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/est 1er sur \d+ sites/, {
    timeout: 60_000,
  });
  await expect(page.getByText(/Classement partiel : \d+ critères sur \d+/).first()).toBeVisible();

  // Prix plafond et capacité modifiés : classement mis à jour, variation de rang (RG-16).
  const avant = (await (await request.get("/api/decision/classement")).json()) as Classement;
  for (const valeurs of [{ "PAR-34": 600 }, { "PAR-01": 15000 }]) {
    const reponse = await request.put("/api/entreprise", { data: { auteur: AUTEUR, valeurs } });
    expect(reponse.ok()).toBeTruthy();
  }
  const apres = (await (await request.get("/api/decision/classement")).json()) as Classement;
  expect(apres.bloque).toBe(false);
  expect(apres.classement.every((s) => s.variation !== null)).toBe(true);
  expect(avant.classement.length).toBeGreaterThan(1);

  // Meknès dans le classement, puis sa fiche (bassin, mélange, bilan, marge).
  await page.reload();
  await page.getByRole("button", { name: /Voir les \d+ sites/ }).click();
  await page.getByRole("link", { name: "Agropolis de Meknès" }).click();
  await expect(page).toHaveURL(/\/fiche-site\?site=AGP-MEKNES$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Agropolis de Meknès/, {
    timeout: 30_000,
  });
  for (const titre of ["Bassin d'approvisionnement", "Mélange de coût minimal", "Bilan climat"])
    await expect(page.getByRole("heading", { name: titre, exact: true })).toBeVisible();
  await expect(
    page.getByText("C6 · Marge estimée sur matière").or(page.getByText(/C1 ·/)).first(),
  ).toBeVisible();
  await page.waitForLoadState("networkidle");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: "test-results/captures/fiche-site-meknes.png", fullPage: true });

  // Poids modifiés : le classement est mis à jour en moins de 2 s (UC-DEC-04).
  const poids = Object.fromEntries(apres.criteres.map((c, i) => [c, i === 0 ? 5 : 1]));
  expect((await request.put("/api/decision/reglages", { data: { poids } })).ok()).toBeTruthy();
  const debut = Date.now();
  const pondere = (await (await request.get("/api/decision/classement")).json()) as Classement;
  expect(Date.now() - debut).toBeLessThan(2000);
  expect(pondere.bloque).toBe(false);

  // Robustesse : probabilité d'être 1er des 3 premiers sites.
  await page.goto("/decision");
  await page.getByRole("button", { name: "Lancer l'analyse de robustesse" }).click();
  const robustesse = page.getByRole("table", { name: "Robustesse du classement" });
  await expect(robustesse).toBeVisible({ timeout: 30_000 });
  await expect(robustesse.getByRole("row")).toHaveCount(11);

  // Scénario enregistré, réglages changés, scénario rechargé : même classement.
  const nom = "recette du MVP";
  const enregistre = await request.post("/api/scenarios", {
    data: { nom, auteur: AUTEUR, remplacer: true },
  });
  expect(enregistre.ok(), await enregistre.text()).toBeTruthy();
  await request.delete("/api/decision/reglages");
  await request.put("/api/entreprise", { data: { auteur: AUTEUR, valeurs: { "PAR-34": 900 } } });
  const applique = await request.post(`/api/scenarios/${encodeURIComponent(nom)}/appliquer`, {
    data: { auteur: AUTEUR },
  });
  expect(applique.ok(), await applique.text()).toBeTruthy();
  const recharge = (await (await request.get("/api/decision/classement")).json()) as Classement;
  expect(recharge.classement.map((s) => [s.id_site, s.rang])).toEqual(
    pondere.classement.map((s) => [s.id_site, s.rang]),
  );

  // Export Excel du classement : feuilles « paramètres » et « sources ».
  await page.reload();
  const attente = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter en Excel" }).first().click();
  const telechargement = await attente;
  const chemin = info.outputPath("classement.xlsx");
  await telechargement.saveAs(chemin);
  const feuilles = execFileSync(
    "python",
    [
      "-I",
      "-c",
      "import sys, openpyxl; print('|'.join(openpyxl.load_workbook(sys.argv[1]).sheetnames))",
      chemin,
    ],
    { cwd: DEPOT, encoding: "utf-8" },
  ).trim();
  expect(feuilles).toBe("Classement des sites|paramètres|sources");
});
