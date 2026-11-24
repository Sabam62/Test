import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { simulerApi } from "../test/fetch";
import BandeauDemo from "./BandeauDemo";
import BarresSegmentees from "./BarresSegmentees";
import EtatVide from "./EtatVide";
import TableauEditable from "./TableauEditable";
import ValeurSourcee from "./ValeurSourcee";

// Provenance réelle : production d'olives 2017-2018 de Taounate (DRA Fès-Meknès, §14.2).
const PROVENANCE_TAOUNATE = {
  source_id: "SRC-18",
  annee: 2018,
  statut: "Mesurée",
  version: null,
  note: "Seconde source : fes-meknes_2017-2018_olivier_hespress.html",
};

describe("ValeurSourcee", () => {
  it("affiche la source, l'année et le statut au clic (UC-01)", () => {
    render(<ValeurSourcee valeur={370028} unite="t" provenance={PROVENANCE_TAOUNATE} />);
    fireEvent.click(screen.getByRole("button", { name: /voir la provenance/ }));
    expect(screen.getByText("SRC-18")).toBeInTheDocument();
    expect(screen.getByText("2018")).toBeInTheDocument();
    expect(screen.getByText("Mesurée")).toBeInTheDocument();
  });

  it("repère par une icône une valeur estimée", () => {
    render(
      <ValeurSourcee valeur={16990} provenance={{ ...PROVENANCE_TAOUNATE, statut: "Estimée" }} />,
    );
    expect(screen.getByLabelText("statut Estimée")).toBeInTheDocument();
  });

  it("n'invente rien pour une valeur à compléter", () => {
    render(<ValeurSourcee valeur={null} provenance={{ ...PROVENANCE_TAOUNATE, statut: null }} />);
    expect(screen.getByRole("button")).toHaveTextContent("À compléter");
  });
});

describe("EtatVide", () => {
  it("n'affiche aucun nombre", () => {
    const { container } = render(
      <MemoryRouter>
        <EtatVide
          message="Les gisements seront calculés à partir des productions préparées."
          lien={{ vers: "/donnees", libelle: "Voir les données" }}
        />
      </MemoryRouter>,
    );
    expect(container.textContent).not.toMatch(/\d/);
    expect(screen.getByRole("link", { name: /Voir les données/ })).toHaveAttribute(
      "href",
      "/donnees",
    );
  });
});

describe("TableauEditable", () => {
  it("rappelle l'unité dans l'en-tête et transmet la valeur corrigée", () => {
    const modifier = vi.fn();
    render(
      <TableauEditable
        libelle="Production"
        colonnes={[
          { cle: "code_province", libelle: "Province" },
          { cle: "valeur", libelle: "Production", unite: "t" },
        ]}
        lignes={[{ code_province: "3531", valeur: 370028, source_id: "SRC-18", annee: 2018 }]}
        colonneValeur="valeur"
        provenance={{ source: "source_id", annee: "annee" }}
        onModifier={modifier}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Production (t)" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Corriger la valeur de cette ligne" }));
    const champ = screen.getByLabelText("Nouvelle valeur de Production");
    expect(champ).toHaveValue("370028");
    fireEvent.change(champ, { target: { value: "371000" } });
    fireEvent.click(screen.getByRole("button", { name: "Valider" }));
    expect(modifier).toHaveBeenCalledWith(
      expect.objectContaining({ code_province: "3531" }),
      "371000",
    );
  });
});

describe("BarresSegmentees", () => {
  it("dessine 24 segments et le pourcentage", () => {
    render(<BarresSegmentees libelle="Ressource" part={0.5} axe="A" />);
    const mesure = screen.getByRole("meter", { name: "Ressource" });
    expect(mesure.children).toHaveLength(24);
    expect(mesure).toHaveAttribute("aria-valuenow", "50");
  });
});

// Réponse de GET /api/demo : textes de config/demo.yaml et de scenarios/demo/demo-1.yaml.
const BANDEAU = "Démonstration — paramètres d'hypothèse, pas un résultat réel";
const SCENARIO = {
  identifiant: "demo-1",
  nom: "Unité de référence à Meknès",
  description: "Unité de capacité moyenne près de Meknès.",
};

describe("BandeauDemo", () => {
  it("annonce la démonstration chargée et propose d'en sortir", async () => {
    const appel = simulerApi({
      "/demo": {
        active: { ...SCENARIO, bandeau: BANDEAU, date: "2026-11-23T13:18:46" },
        bandeau: BANDEAU,
        scenarios: [SCENARIO],
      },
    });
    render(<BandeauDemo />);
    expect(await screen.findByRole("status", { name: "Démonstration" })).toHaveTextContent(
      `${BANDEAU} · Unité de référence à Meknès`,
    );
    fireEvent.click(screen.getByRole("button", { name: "Quitter la démonstration" }));
    await waitFor(() => {
      expect(appel).toHaveBeenCalledWith(
        "/api/demo",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("ne montre rien hors démonstration, ni de bouton à l'impression", async () => {
    simulerApi({ "/demo": { active: null, bandeau: BANDEAU, scenarios: [SCENARIO] } });
    const { container } = render(<BandeauDemo impression />);
    await waitFor(() => {
      expect(container).toBeEmptyDOMElement();
    });
  });
});
