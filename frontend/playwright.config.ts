import { defineConfig, devices } from "@playwright/test";

/**
 * Tests de bout en bout sur l'outil lancé comme par l'utilisateur (`python -m ab_dss`), sur une
 * copie des données réelles (scripts.racine_essai) : les essais ne touchent pas data/ ni config/,
 * ni les projets Brightway de l'utilisateur (BRIGHTWAY2_DIR dans la copie d'essai).
 */
const PORT = 8765;
const RACINE_ESSAI = "frontend/test-results/racine-essai";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${String(PORT)}`,
    locale: "fr-FR",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `cd .. && python -m scripts.racine_essai ${RACINE_ESSAI} && mkdir -p ${RACINE_ESSAI}/brightway && AB_DSS_RACINE=${RACINE_ESSAI} BRIGHTWAY2_DIR=${RACINE_ESSAI}/brightway python -m ab_dss --sans-navigateur --port ${String(PORT)}`,
    url: `http://127.0.0.1:${String(PORT)}/api/sante`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
