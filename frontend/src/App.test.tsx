import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import App, { ECRANS } from "./App";
import { simulerApi } from "./test/fetch";

vi.mock("./map/CarteSatellite", () => ({
  default: ({ libelle }: { libelle: string }) => <div role="img" aria-label={libelle} />,
}));

// États de l'outil livré : paramètres de l'entreprise vides (RG-15), aucun scénario.
const LIVRE = {
  "/entreprise": {
    renseignement_requis: true,
    obligatoires: ["PAR-01", "PAR-21", "PAR-34", "PAR-37"],
    a_renseigner: ["PAR-01", "PAR-21", "PAR-34", "PAR-37"],
    date_modification: null,
    auteur: null,
    parametres: [],
  },
  "/scenarios": [],
  "/donnees/versions": [],
  "/sante": {
    statut: "ok",
    version_outil: "0.1.0",
    donnees_preparees: false,
    osrm: "non configuré (lot 3)",
  },
  "/parametres": [],
};

describe("App", () => {
  it("propose les 9 écrans dans la navigation flottante", async () => {
    simulerApi(LIVRE);
    render(
      <MemoryRouter initialEntries={["/fiche-site"]}>
        <App />
      </MemoryRouter>,
    );
    const navigation = screen.getByRole("navigation", { name: "Navigation principale" });
    expect(ECRANS).toHaveLength(9);
    for (const { libelle } of ECRANS) {
      expect(navigation).toHaveTextContent(libelle);
    }
    expect(await screen.findByText("4 à renseigner")).toBeInTheDocument();
    // Le contexte du scénario est un élément discret de la navigation, ouvert au clic.
    fireEvent.click(screen.getByRole("button", { name: /Contexte du scénario/ }));
    expect(await screen.findByText("non configuré (lot 3)")).toBeInTheDocument();
    expect(screen.getAllByText("aucun scénario enregistré").length).toBeGreaterThan(0);
    expect(screen.getAllByText("à renseigner").length).toBeGreaterThan(0);
  });
});
