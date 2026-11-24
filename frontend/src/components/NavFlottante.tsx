import { NavLink } from "react-router";

import { symbole } from "../theme/logo";
import ContexteScenario from "./ContexteScenario";
import { STYLE_BOUTON_PRIMAIRE } from "../theme/boutons";

export interface Onglet {
  chemin: string;
  libelle: string;
}

interface Props {
  onglets: readonly Onglet[];
  /** Badge discret par chemin d'onglet, par exemple « 4 à renseigner » sur Paramètres. */
  badges?: Partial<Record<string, string>>;
}

/**
 * Navigation flottante (section 12.5) : logotype Atlantic Biochar à gauche, onglets au centre
 * (onglet actif souligné du vert de la marque), contexte du scénario (bouton discret qui ouvre
 * un panneau) et bouton noir « Lancer l'analyse » à droite.
 * Le symbole est celui du logo fourni par l'entreprise (PNG en attendant le SVG officiel).
 */
export default function NavFlottante({ onglets, badges = {} }: Props) {
  return (
    <nav
      aria-label="Navigation principale"
      className="flex items-center justify-between gap-6 rounded-carte bg-card px-4 py-2.5 shadow-douce"
    >
      <NavLink to="/" className="flex items-center gap-2" aria-label="Atlantic Biochar, accueil">
        <img src={symbole} alt="" aria-hidden="true" className="h-6 w-auto" />
        <span className="font-titre text-secondaire font-medium tracking-tight text-ink">
          Atlantic Biochar
        </span>
      </NavLink>
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-secondaire">
        {onglets.map(({ chemin, libelle }) => (
          <li key={chemin}>
            <NavLink
              to={chemin}
              end={chemin === "/"}
              className={({ isActive }) =>
                `underline-offset-[6px] transition-colors duration-courte ${
                  isActive
                    ? "text-ink underline decoration-marque-principal decoration-2"
                    : "text-muted hover:text-ink"
                }`
              }
            >
              {libelle}
              {badges[chemin] ? (
                <span className="ml-1.5 inline-block whitespace-nowrap rounded-full bg-ember px-1.5 py-0.5 text-source font-medium text-ink">
                  {badges[chemin]}
                </span>
              ) : null}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2">
        <ContexteScenario />
        <NavLink
          to="/decision"
          className={`whitespace-nowrap rounded-bouton px-3.5 py-2 text-secondaire font-medium shadow-douce ${STYLE_BOUTON_PRIMAIRE}`}
        >
          Lancer l'analyse
        </NavLink>
      </div>
    </nav>
  );
}
