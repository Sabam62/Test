import type { ReactNode } from "react";

interface Props {
  icone: ReactNode;
  libelle: string;
  valeur: ReactNode;
}

/** Tuile d'indicateur : fond paper, icône 14 px, libellé 12 px, valeur 20 px (section 12.5). */
export default function TuileKPI({ icone, libelle, valeur }: Props) {
  return (
    <div className="rounded-bouton bg-paper p-3">
      <p className="flex items-center gap-1.5 text-libelle text-muted">
        <span aria-hidden="true" className="text-muted">
          {icone}
        </span>
        {libelle}
      </p>
      <p className="chiffres mt-1 text-valeur text-ink">{valeur}</p>
    </div>
  );
}
