import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * Parcours du lot 1 sur la copie d'essai des données réelles (scripts.racine_essai) :
 * paramètres obligatoires (RG-15), import Excel puis restauration, provenance d'une valeur.
 * Les valeurs saisies sont des « saisies simulées pour le test ».
 */
test.describe.configure({ mode: "serial" });

const DEPOT = join(import.meta.dirname, "..", "..");
// Saisies simulées pour le test (UC-ENT-02 cite un prix plafond de 300 à 900 DH/t).
// Gazole à 12 DH/L : exemple du calcul de PAR-33 au §14.3.
const SAISIE_SIMULEE = { capacite: "20000", temperature: "moyenne", prix: "600", gazole: "12" };

async function ouvrirOnglet(page: Page, nom: string) {
  await page.goto("/donnees");
  await page.getByRole("tab", { name: nom }).click();
}

test("premier lancement : badge, lien vers le champ, puis paramètres obligatoires enregistrés", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const onglet = page.getByRole("link", { name: /Paramètres 4 à renseigner/ });
  await expect(onglet).toBeVisible();
  // L'état vide de l'accueil renvoie directement au champ de la capacité.
  await page.getByRole("link", { name: "capacité visée K d'une unité" }).click();
  await expect(page).toHaveURL(/\/parametres#PAR-01$/);
  await expect(page.locator("#PAR-01")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Entreprise", level: 2 })).toBeVisible();
  await page.locator("#PAR-01").fill(SAISIE_SIMULEE.capacite);
  await page.locator("#PAR-21").fill(SAISIE_SIMULEE.temperature);
  await page.locator("#PAR-34").fill(SAISIE_SIMULEE.prix);
  await page.locator("#PAR-37").fill(SAISIE_SIMULEE.gazole);
  await page.getByLabel("Auteur des modifications").fill("test de bout en bout");
  await page
    .getByRole("form", { name: "Paramètres obligatoires" })
    .getByRole("button", { name: "Enregistrer" })
    .click();
  await expect(page.getByRole("link", { name: /^Paramètres$/ })).toBeVisible();
  await expect(page.getByText(/^\d+ à renseigner$/)).toHaveCount(0);
  const entreprise = (await (await page.request.get("/api/entreprise")).json()) as {
    renseignement_requis: boolean;
  };
  expect(entreprise.renseignement_requis).toBe(false);
});

test("import Excel d'une valeur modifiée, nouvelle version, puis restauration", async ({
  page,
}, info) => {
  const avant = (await (await page.request.get("/api/donnees/versions")).json()) as {
    id_version: string;
  }[];
  const versionAvant = avant[0]?.id_version ?? "";
  const modele = await page.request.get("/api/donnees/tables/production/modele.xlsx");
  const fichier = info.outputPath("production.xlsx");
  writeFileSync(fichier, await modele.body());
  // Saisie simulée pour le test : la production de Taounate 2017-2018 passe à 371 000 t.
  execFileSync(
    "python",
    [
      "-c",
      [
        "import sys, openpyxl",
        "classeur = openpyxl.load_workbook(sys.argv[1])",
        "feuille = classeur['données']",
        "entetes = [c.value for c in feuille[1]]",
        "i = {nom: entetes.index(nom) for nom in entetes}",
        "for ligne in feuille.iter_rows(min_row=2):",
        "    v = [c.value for c in ligne]",
        "    if (str(v[i['code_province']]), v[i['code_culture']], v[i['campagne']], v[i['variable']]) == ('3531', 'olivier', '2017-2018', 'production_t'):",
        "        ligne[i['valeur']].value = 371000",
        "classeur.save(sys.argv[1])",
      ].join("\n"),
      fichier,
    ],
    { cwd: DEPOT },
  );

  await ouvrirOnglet(page, "Import Excel");
  await page.getByLabel("Classeur modifié (.xlsx)").setInputFiles(fichier);
  await page.getByRole("button", { name: "Déposer et prévisualiser" }).click();
  await expect(page.getByText(/0 ajoutées, 1 modifiées, 0 rejetées/)).toBeVisible();
  const panneau = page.locator("form").filter({ hasText: "Valider l'import" });
  await panneau.getByLabel("Auteur").fill("test de bout en bout");
  await panneau.getByLabel("Commentaire").fill("saisie simulée pour le test");
  await page.getByRole("button", { name: "Valider l'import" }).click();
  await expect(
    page.getByText(/Version v\d+ enregistrée : 0 lignes ajoutées, 1 modifiées/),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Versions" }).click();
  await page.getByLabel("Auteur de la restauration").fill("test de bout en bout");
  await page.getByRole("button", { name: `Restaurer ${versionAvant}` }).click();
  await expect(page.getByText(`restauration de ${versionAvant}`).first()).toBeVisible();

  const apres = (await (await page.request.get("/api/donnees/versions")).json()) as {
    id_version: string;
    restauration_de: string | null;
  }[];
  expect(apres[0]?.restauration_de).toBe(versionAvant);
  const difference = (await (
    await page.request.get(
      `/api/donnees/versions/${versionAvant}/comparer/${apres[0]?.id_version ?? ""}?table=production`,
    )
  ).json()) as { ajoutees: unknown[]; modifiees: unknown[]; supprimees: unknown[] };
  expect(
    difference.ajoutees.length + difference.modifiees.length + difference.supprimees.length,
  ).toBe(0);
});

test("Paramètres : sections, recherche, filtre « modifiés seulement », réglages repliés", async ({
  page,
}) => {
  await page.goto("/parametres");
  const menu = page.getByRole("navigation", { name: "Sections des paramètres" });
  for (const titre of [
    "Entreprise",
    "Approvisionnement et logistique",
    "Économie",
    "Carbone et ACV",
    "Réglages techniques",
  ]) {
    await expect(menu.getByRole("link", { name: titre })).toBeVisible();
  }
  // Réglages techniques repliés par défaut.
  await expect(page.getByText("PAR-03", { exact: true })).toBeHidden();
  // La recherche trouve un paramètre et ouvre sa section repliée.
  await page.getByLabel("Rechercher un paramètre (nom ou PAR-xx)").fill("Monte Carlo");
  await expect(page.getByText("PAR-03", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Économie", level: 2 })).toBeHidden();
  await page.getByLabel("Rechercher un paramètre (nom ou PAR-xx)").fill("");
  // Filtre « modifiés seulement » : les quatre obligatoires saisis restent, rien d'autre.
  await page.getByLabel("Modifiés seulement").check();
  await expect(page.locator("#PAR-01")).toBeVisible();
  await expect(page.locator("#PAR-59")).toHaveCount(0);
  await expect(page.getByText("PAR-24", { exact: true })).toHaveCount(0);
});

test("le contexte du scénario s'ouvre depuis la navigation et enregistre un scénario", async ({
  page,
}) => {
  await page.goto("/gisements");
  // Plus de bandeau sous la navigation : le contexte est un bouton discret de la navigation.
  const bouton = page.getByRole("button", { name: /Contexte du scénario/ });
  await expect(bouton).toBeVisible();
  await bouton.click();
  await expect(page.getByText("Campagne de référence")).toBeVisible();
  await expect(
    page.getByText(/^(actif|arrêté : distances à vol d.oiseau × détour)$/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Enregistrer le scénario" }).click();
  const fenetre = page.getByRole("dialog", { name: "Enregistrer le scénario" });
  await fenetre.getByLabel("Nom du scénario").fill("Essai de bout en bout");
  await fenetre.getByLabel("Auteur").fill("test de bout en bout");
  await fenetre.getByRole("button", { name: "Enregistrer" }).click();
  await expect(fenetre).toBeHidden();
  await expect(
    page.getByRole("button", { name: /Contexte du scénario : Essai de bout en bout/ }),
  ).toBeVisible();
});

test("accueil : la molette fait défiler la page, Ctrl + molette zoome la carte", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  const carte = page.getByRole("img", { name: /Carte satellite du Maroc/ });
  await expect(carte).toHaveAttribute("data-zoom", /\d/);
  const zoomInitial = await carte.getAttribute("data-zoom");
  await page.mouse.move(640, 400);
  await page.mouse.wheel(0, 600);
  await expect(page.getByText("Ctrl + molette pour zoomer")).toBeVisible();
  await expect.poll(() => page.evaluate<number>("window.scrollY")).toBeGreaterThan(0);
  expect(await carte.getAttribute("data-zoom")).toBe(zoomInitial);
  await page.evaluate("window.scrollTo(0, 0)");
  // L'appareil « Desktop Chrome » annonce Windows : MapLibre attend Ctrl (⌘ sur un vrai Mac).
  await page.keyboard.down("Control");
  await page.mouse.move(640, 400);
  await page.mouse.wheel(0, -600);
  await page.keyboard.up("Control");
  await expect.poll(() => carte.getAttribute("data-zoom")).not.toBe(zoomInitial);
  // Boutons + et − de la carte.
  await expect(page.getByRole("button", { name: "Zoomer" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Dézoomer" }).first()).toBeVisible();
});

test("un clic sur une valeur affiche sa source, son année et son statut", async ({ page }) => {
  await ouvrirOnglet(page, "Tables et saisie");
  await page
    .getByLabel("Filtrer (province, culture, source…)")
    .fill("fes-meknes_2017-2018_olivier.html");
  await page.getByRole("button", { name: "Filtrer" }).click();
  await page
    .getByRole("button", { name: /voir la provenance/ })
    .first()
    .click();
  const fenetre = page.getByRole("dialog");
  await expect(fenetre).toContainText("Source");
  await expect(fenetre).toContainText("SRC-18");
  await expect(fenetre).toContainText("2018");
  await expect(fenetre).toContainText(/Mesurée|Estimée/);
});
