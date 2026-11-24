import { ArrowRightIcon } from "@phosphor-icons/react";
import { Fragment } from "react";
import { Link } from "react-router";

import type { EntrepriseApi } from "../lib/api";
import { useApi } from "../lib/useApi";
import { STYLE_BOUTON_PRIMAIRE } from "../theme/boutons";

interface Props {
  /** Paramètres de l'entreprise dont dépend l'écran. */
  requis: readonly string[];
  /** Ce que l'écran calculera une fois les paramètres renseignés. */
  pour: string;
}

/**
 * État vide « Renseignez … dans Paramètres » (RG-15) : chaque paramètre manquant est un lien
 * direct vers son champ. Rien ne s'affiche quand tous sont renseignés.
 */
export default function ParametresManquants({ requis, pour }: Props) {
  const { donnees } = useApi<EntrepriseApi>("/entreprise");
  const manquants = (donnees?.parametres ?? []).filter(
    (p) => requis.includes(p.identifiant) && p.valeur === null,
  );
  if (!manquants.length) return null;
  return (
    <div className="rounded-carte border border-dashed border-line bg-card p-6">
      <p className="text-texte text-ink">
        Renseignez{" "}
        {manquants.map((p, i) => (
          <Fragment key={p.identifiant}>
            {i > 0 ? (i === manquants.length - 1 ? " et " : ", ") : ""}
            <Link
              to={`/parametres#${p.identifiant}`}
              className="underline decoration-marque-principal decoration-2 underline-offset-2"
            >
              {p.libelle.charAt(0).toLowerCase() + p.libelle.slice(1)}
            </Link>
          </Fragment>
        ))}{" "}
        dans Paramètres {pour}.
      </p>
      <Link
        to={`/parametres#${manquants[0]?.identifiant ?? ""}`}
        className={`mt-4 inline-flex items-center gap-2 rounded-bouton px-4 py-2 text-secondaire font-medium shadow-douce ${STYLE_BOUTON_PRIMAIRE}`}
      >
        Ouvrir Paramètres
        <ArrowRightIcon size={16} aria-hidden="true" />
      </Link>
    </div>
  );
}
