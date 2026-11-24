import { Route, Routes, useLocation } from "react-router";

import BandeauDemo from "./components/BandeauDemo";
import NavFlottante from "./components/NavFlottante";
import type { EntrepriseApi } from "./lib/api";
import { useApi } from "./lib/useApi";
import Accueil from "./screens/Accueil";
import BilanClimat from "./screens/BilanClimat";
import Decision from "./screens/Decision";
import Donnees from "./screens/Donnees";
import FicheSite from "./screens/FicheSite";
import Gisements from "./screens/Gisements";
import Melange from "./screens/Melange";
import ParametresEntreprise from "./screens/ParametresEntreprise";
import Sites from "./screens/Sites";

/** Les 9 écrans de la section 12.1, dans l'ordre du pipeline. */
export const ECRANS = [
  { chemin: "/", libelle: "Accueil", Composant: Accueil },
  { chemin: "/gisements", libelle: "Gisements", Composant: Gisements },
  { chemin: "/sites", libelle: "Sites", Composant: Sites },
  { chemin: "/bilan-climat", libelle: "Bilan climat", Composant: BilanClimat },
  { chemin: "/decision", libelle: "Décision", Composant: Decision },
  { chemin: "/melange", libelle: "Mélange", Composant: Melange },
  { chemin: "/fiche-site", libelle: "Fiche site", Composant: FicheSite },
  { chemin: "/parametres", libelle: "Paramètres", Composant: ParametresEntreprise },
  { chemin: "/donnees", libelle: "Données", Composant: Donnees },
] as const;

/**
 * Coquille : navigation flottante posée en haut de chaque écran (le contexte du scénario est un
 * élément discret de la navigation) ; sur l'accueil, elle flotte sur la carte satellite (12.2).
 * Pendant une démonstration, son bandeau précède la navigation et chaque page imprimée.
 */
export default function App() {
  const { pathname } = useLocation();
  const hero = pathname === "/";
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const aRenseigner = entreprise.donnees?.a_renseigner.length ?? 0;
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header
        className={`${hero ? "absolute" : "relative"} inset-x-0 top-0 z-20 mx-auto grid max-w-[1440px] gap-2 px-6 pt-4 print:hidden`}
      >
        <BandeauDemo />
        <NavFlottante
          onglets={ECRANS}
          badges={aRenseigner ? { "/parametres": `${String(aRenseigner)} à renseigner` } : {}}
        />
      </header>
      <main>
        <div className="hidden px-6 pt-4 print:block">
          <BandeauDemo impression />
        </div>
        <Routes>
          {ECRANS.map(({ chemin, Composant }) => (
            <Route key={chemin} path={chemin} element={<Composant />} />
          ))}
        </Routes>
      </main>
    </div>
  );
}
