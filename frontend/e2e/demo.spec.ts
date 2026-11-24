import { expect, test } from "@playwright/test";

/**
 * Scénarios de démonstration (scenarios/demo/, docs/demo.md) sur la copie d'essai : chargement en
 * un clic depuis Paramètres › Scénarios, bandeau sur tous les écrans et à l'impression, écrans
 * débloqués, puis retour aux paramètres réels (laissés vides par la copie d'essai, RG-15).
 */
test.describe.configure({ mode: "serial" });

const BANDEAU = "Démonstration — paramètres d'hypothèse, pas un résultat réel";

test.afterAll(async ({ request }) => {
  await request.delete("/api/demo");
});

test("une démonstration se charge en un clic et se quitte sans rien perdre", async ({ page }) => {
  test.setTimeout(240_000); // premier calcul à froid de toute la chaîne dans la copie de travail
  await page.goto("/parametres#section-scenarios");
  await expect(page.getByText(/^\d+ à renseigner$/)).toBeVisible();
  // Le chargement copie les données : on attend la réponse (serveur parfois occupé par un calcul).
  const charge = page.waitForResponse((r) => r.url().endsWith("/api/demo/demo-1"), {
    timeout: 120_000,
  });
  await page
    .getByRole("button", { name: "Charger la démonstration « Unité de référence à Meknès »" })
    .click();
  expect((await charge).ok()).toBeTruthy();
  const bandeau = page.getByRole("status", { name: "Démonstration" });
  await expect(bandeau).toContainText(`${BANDEAU} · Unité de référence à Meknès`);
  // Paramètres de l'entreprise fixés par le scénario : plus de badge « à renseigner ».
  await expect(page.getByText(/^\d+ à renseigner$/)).toHaveCount(0);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator("#titre-demonstration").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "test-results/captures/demo-parametres.png" });

  // Bandeau sur chaque écran ; résultats calculés.
  for (const [chemin, titre] of [
    ["/gisements", /8 résidus sur 13 ont un gisement théorique calculé/],
    ["/decision", /est 1er sur \d+ sites/],
    ["/melange", /t MS\/an à [\d\s\u202f]+ DH\/t MS en moyenne/],
    ["/bilan-climat", /t CO₂e retirées par t de biochar livré/],
  ] as const) {
    await page.goto(chemin);
    await expect(page.getByRole("status", { name: "Démonstration" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(titre, {
      timeout: 120_000,
    });
  }
  await page.goto("/decision");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/est 1er/);
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: "test-results/captures/demo-decision.png" });
  await expect(page.getByText(/Classement partiel/)).toHaveCount(0);

  // Fiche site imprimée : le bandeau est en tête de la page.
  await page.goto("/fiche-site?site=AGP-MEKNES");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Agropolis de Meknès/, {
    timeout: 60_000,
  });
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("status", { name: "Démonstration" })).toBeVisible();
  await page.emulateMedia({ media: "screen" });

  // Quitter : retour aux paramètres réels, intacts (vides dans la copie d'essai).
  await page
    .getByRole("status", { name: "Démonstration" })
    .first()
    .getByRole("button", { name: "Quitter la démonstration" })
    .click();
  await expect(page.getByRole("status", { name: "Démonstration" })).toHaveCount(0);
  await expect(page.getByText(/^\d+ à renseigner$/)).toBeVisible();
});

test("pendant un chargement, charger et quitter sont désactivés et un indicateur s'affiche", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await page.goto("/parametres#section-scenarios");
  const premier = page.waitForResponse((r) => r.url().endsWith("/api/demo/demo-1"), {
    timeout: 120_000,
  });
  await page
    .getByRole("button", { name: "Charger la démonstration « Unité de référence à Meknès »" })
    .click();
  expect((await premier).ok()).toBeTruthy();
  const bandeau = page.getByRole("status", { name: "Démonstration" });
  await expect(bandeau).toContainText("Unité de référence à Meknès");

  // Le chargement suivant est retenu tant que le test ne le libère pas.
  let liberer: () => void = () => undefined;
  const liberation = new Promise<void>((resolve) => {
    liberer = resolve;
  });
  await page.route("**/api/demo/demo-2", async (route) => {
    await liberation;
    await route.continue();
  });
  const second = page.waitForResponse((r) => r.url().endsWith("/api/demo/demo-2"), {
    timeout: 120_000,
  });
  await page
    .getByRole("button", { name: "Charger la démonstration « Petite unité locale »" })
    .click();

  const indicateurs = page.getByRole("status", { name: "Chargement de la démonstration" });
  await expect(indicateurs.first()).toContainText(
    "Chargement de la démonstration « Petite unité locale »…",
  );
  await expect(indicateurs).toHaveCount(2); // bandeau de chaque écran et section Démonstration
  await expect(page.getByRole("button", { name: "Quitter la démonstration" })).toHaveCount(2);
  for (const bouton of await page.getByRole("button", { name: "Quitter la démonstration" }).all())
    await expect(bouton).toBeDisabled();
  for (const bouton of await page.getByRole("button", { name: /^Charger la démonstration/ }).all())
    await expect(bouton).toBeDisabled();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: "test-results/captures/demo-chargement.png" });
  liberer();
  expect((await second).ok()).toBeTruthy();
  await expect(bandeau).toContainText("Petite unité locale");
  await expect(indicateurs).toHaveCount(0);
  const quitter = bandeau.getByRole("button", { name: "Quitter la démonstration" });
  await expect(quitter).toBeEnabled();
  await quitter.click();
  await expect(bandeau).toHaveCount(0);
});
