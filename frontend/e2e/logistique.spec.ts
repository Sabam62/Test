import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Écran Sites et logistique (lot 3, UC-LOG-01 à 04) sur la copie d'essai des données réelles.
 *
 * Condition de fin du lot 3 : la courbe d'approvisionnement de Meknès s'affiche. Dans les
 * données livrées, elle attend des valeurs « À compléter » (coût fixe, volume du camion,
 * densité, coûts de collecte et de prétraitement, part utilisée, paramètres de l'entreprise) :
 * elles sont saisies ici par l'API comme des « saisies simulées pour le test », sur la copie
 * d'essai seulement, puis tout est remis dans l'état livré à la fin.
 */

const SIMULE = "saisie simulée pour le test";
const AUTEUR = "test de bout en bout";
const RESIDUS_TAILLE = ["R01", "R02", "R03", "R04"];

async function saisir(
  requete: APIRequestContext,
  table: string,
  cle: Record<string, string>,
  valeur: string,
) {
  const reponse = await requete.put(`/api/donnees/tables/${table}/valeur`, {
    data: { auteur: AUTEUR, commentaire: SIMULE, cle, valeur, source: SIMULE, date: "2026-11-22" },
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
  for (const identifiant of ["PAR-61", "PAR-32"])
    await request.delete(`/api/parametres/${identifiant}`);
  await request.put("/api/entreprise", {
    data: {
      auteur: AUTEUR,
      valeurs: { "PAR-01": null, "PAR-21": null, "PAR-34": null, "PAR-37": null },
    },
  });
});

test("sans saisies, la courbe de Meknès liste les valeurs à saisir", async ({ page }) => {
  await page.goto("/sites");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/sites candidats placés/);
  await expect(
    page.getByRole("heading", { level: 2, name: "Agropolis de Meknès", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Valeurs à saisir pour tracer la courbe d'approvisionnement"),
  ).toBeVisible();
  await expect(page.getByText(/PAR-61/).first()).toBeVisible();
});

test("courbe d'approvisionnement de Meknès affichée", async ({ page, request }) => {
  for (const residu of RESIDUS_TAILLE) {
    const valeurs: [string, string][] = [
      ["densite_apparente", "150"],
      ["k_col", "80"],
      ["k_pre", "60"],
    ];
    if (residu !== "R03") valeurs.push(["humidite", "30"]);
    for (const [parametre, valeur] of valeurs)
      await saisir(request, "residus", { code_residu: residu, parametre, precision: "" }, valeur);
    for (const [parametre, valeur] of [
      ["part_utilisee", "0.2"],
      ["prix_achat_dh_t", "0"],
    ] as const)
      await saisir(
        request,
        "concurrence",
        { code_province: "NATIONAL", code_residu: residu, parametre, precision: "" },
        valeur,
      );
  }
  for (const [identifiant, valeur] of [
    ["PAR-61", 300],
    ["PAR-32", 90],
  ] as const) {
    const reponse = await request.put(`/api/parametres/${identifiant}`, {
      data: { valeur, source: SIMULE, auteur: AUTEUR },
    });
    expect(reponse.ok()).toBeTruthy();
  }
  const entreprise = await request.put("/api/entreprise", {
    data: {
      auteur: AUTEUR,
      valeurs: { "PAR-01": 20000, "PAR-21": "moyenne", "PAR-34": 900, "PAR-37": 12 },
    },
  });
  expect(entreprise.ok(), await entreprise.text()).toBeTruthy();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/sites");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Agropolis de Meknès/);
  await expect(page.getByText(/Courbe d'approvisionnement : coût livré/)).toBeVisible({
    timeout: 30_000,
  });
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: "test-results/captures/sites-courbe-meknes.png", fullPage: true });
});
