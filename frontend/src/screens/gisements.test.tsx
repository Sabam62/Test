import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { simulerApi } from "../test/fetch";
import Gisements from "./Gisements";

vi.mock("../map/CarteSatellite", () => ({
  default: ({ libelle }: { libelle: string }) => <div role="img" aria-label={libelle} />,
}));

// Réponse réelle de /api/potentiel/synthese sur les données préparées le 22/11/2026 (extrait).
const SYNTHESE_REELLE = {
  residus: 13,
  totaux: [
    {
      indicateur: "T",
      libelle: "Gisement théorique",
      unite: "t MS/an",
      total: 2010109,
      residus_calcules: ["R01", "R02", "R03", "R04", "R06"],
    },
    {
      indicateur: "M",
      libelle: "Gisement mobilisable",
      unite: "t MS/an",
      total: null,
      residus_calcules: [],
    },
  ],
  par_residu: [],
  bloquants: [
    {
      motif:
        "PAR-62 · Procédé de trituration de référence pour les grignons d'olive (R05) à compléter",
      couples: 75,
      residus: ["R05"],
    },
  ],
};

describe("Gisements", () => {
  it("titre sur la synthèse réelle et renvoie les valeurs bloquantes vers Paramètres", async () => {
    simulerApi({
      "/potentiel/indicateurs": {
        indicateurs: [
          { code: "T", libelle: "Gisement théorique", unite: "t MS/an", additif: true },
        ],
        residus: [{ code: "R01", nom: "Taille d'olivier" }],
      },
      "/potentiel/synthese": SYNTHESE_REELLE,
      "/referentiel/provinces/geojson": {
        type: "FeatureCollection",
        features: [],
        attribution: "© Haut-Commissariat au Plan",
      },
    });
    render(
      <MemoryRouter>
        <Gisements />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /5 résidus sur 13 ont un gisement théorique calculé/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("à compléter")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "compléter dans Paramètres" })).toHaveAttribute(
      "href",
      "/parametres#technique-PAR-62",
    );
  });
});
