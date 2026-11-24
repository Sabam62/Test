import type { ReactNode } from "react";

import EnTeteEcran from "./EnTeteEcran";
import EtatVide from "./EtatVide";

interface Props {
  titre: ReactNode;
  phrase: string;
  /** Ce qui manque pour remplir l'écran : donnée, paramètre ou module à livrer. */
  manque: string;
  detail?: ReactNode;
  lien?: { vers: string; libelle: string };
  children?: ReactNode;
}

/** Écran dont le module de calcul arrive dans un lot suivant : titre factuel, état vide (12.5). */
export default function EcranSquelette({ titre, phrase, manque, detail, lien, children }: Props) {
  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-16 px-6 pb-24 pt-16">
      <EnTeteEcran titre={titre} phrase={phrase} />
      {children}
      <EtatVide message={manque} {...(detail ? { detail } : {})} {...(lien ? { lien } : {})} />
    </div>
  );
}
