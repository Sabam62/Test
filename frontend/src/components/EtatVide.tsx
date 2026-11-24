import { ArrowRightIcon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { STYLE_BOUTON_PRIMAIRE } from "../theme/boutons";

interface Props {
  /** Phrase qui dit quelle donnée ou quel lot manque ; jamais de valeur factice. */
  message: string;
  detail?: ReactNode;
  lien?: { vers: string; libelle: string };
}

/** État vide de la section 12.5 : ce qui manque, et un bouton vers l'endroit où le fournir. */
export default function EtatVide({ message, detail, lien }: Props) {
  return (
    <div className="rounded-carte border border-dashed border-line bg-card p-6">
      <p className="text-texte text-ink">{message}</p>
      {detail ? <p className="mt-1 text-secondaire text-muted">{detail}</p> : null}
      {lien ? (
        <Link
          to={lien.vers}
          className={`mt-4 inline-flex items-center gap-2 rounded-bouton px-4 py-2 text-secondaire font-medium shadow-douce ${STYLE_BOUTON_PRIMAIRE}`}
        >
          {lien.libelle}
          <ArrowRightIcon size={16} aria-hidden="true" />
        </Link>
      ) : null}
    </div>
  );
}
