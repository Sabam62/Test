import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { simulerApi } from "../test/fetch";
import Accueil from "./Accueil";
import Decision from "./Decision";

vi.mock("../map/CarteSatellite", () => ({
  default: ({ libelle }: { libelle: string }) => <div role="img" aria-label={libelle} />,
}));

// Réponse réelle de /api/donnees/resume sur les données préparées le 22/11/2026.
const RESUME_REEL = {
  provinces_total: 75,
  provinces_avec_production: 75,
  provinces_avec_valeur_reelle: 9,
  provinces_estimees_seulement: 66,
  cultures: [
    "agrumes",
    "amandier",
    "avoine",
    "betterave",
    "ble",
    "olivier",
    "orge",
    "palmier_dattier",
    "riz",
    "rosacees",
    "tomate",
    "vigne",
  ],
  campagne_min: "2010-2011",
  campagne_max: "2024-2025",
  valeurs_production: 9084,
  valeurs_reelles: 11,
  a_completer: { residus: 111, concurrence: 38, facteurs_emission: 14 },
  a_completer_total: 163,
  derniere_version: null,
  sources: 58,
};
// Paramètres de l'entreprise livrés vides (RG-15).
const ENTREPRISE_LIVREE = {
  renseignement_requis: true,
  obligatoires: ["PAR-01", "PAR-21", "PAR-34", "PAR-37"],
  a_renseigner: ["PAR-01", "PAR-21", "PAR-34", "PAR-37"],
  date_modification: null,
  auteur: null,
  parametres: [
    {
      identifiant: "PAR-01",
      libelle: "Capacité visée K d'une unité",
      unite: "t MS/an",
      type: "nombre",
      choix: [],
      obligatoire: true,
      valeur: null,
    },
    {
      identifiant: "PAR-21",
      libelle: "Température de pyrolyse du procédé",
      unite: "°C ou classe",
      type: "nombre_ou_choix",
      choix: ["basse", "moyenne", "haute"],
      obligatoire: true,
      valeur: null,
    },
    {
      identifiant: "PAR-34",
      libelle: "Prix plafond livré à l'usine",
      unite: "DH/t MS",
      type: "nombre",
      choix: [],
      obligatoire: true,
      valeur: null,
    },
    {
      identifiant: "PAR-37",
      libelle: "Prix du gazole",
      unite: "DH/L",
      type: "nombre",
      choix: [],
      obligatoire: true,
      valeur: null,
    },
  ],
};

describe("écrans", () => {
  it("l'accueil titre sur les données réelles et renvoie vers les paramètres obligatoires (RG-15)", async () => {
    simulerApi({
      "/donnees/resume": RESUME_REEL,
      "/donnees/statut-provinces": { provinces: [], resume: { réelle: 9, estimée: 66 }, total: 75 },
      "/referentiel/provinces/geojson": {
        type: "FeatureCollection",
        features: [],
        attribution: "© Haut-Commissariat au Plan",
      },
      "/entreprise": ENTREPRISE_LIVREE,
    });
    render(
      <MemoryRouter>
        <Accueil />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "75 provinces sur 75 ont une production sourcée",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const lien = await screen.findByRole("link", { name: "capacité visée K d'une unité" });
    expect(lien).toHaveAttribute("href", "/parametres#PAR-01");
    expect(screen.getByRole("link", { name: "prix du gazole" })).toHaveAttribute(
      "href",
      "/parametres#PAR-37",
    );
  });

  it("la décision dit quels paramètres manquent, sans valeur supposée", async () => {
    simulerApi({
      "/entreprise": ENTREPRISE_LIVREE,
      "/decision/classement": {
        bloque: true,
        a_renseigner: ["PAR-01", "PAR-21", "PAR-34", "PAR-37"],
      },
    });
    render(
      <MemoryRouter>
        <Decision />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Le classement attend 4 paramètres obligatoires de l'entreprise",
      );
    });
    expect(screen.getByRole("link", { name: "prix du gazole" })).toHaveAttribute(
      "href",
      "/parametres#PAR-37",
    );
  });
});
