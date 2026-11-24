import type { ReactNode } from "react";

interface Props {
  /** Titre qui énonce un fait calculé sur les données réelles (section 12.7). */
  titre: ReactNode;
  /** Phrase qui dit ce que la page permet de décider (section 12.1). */
  phrase: ReactNode;
}

/** En-tête asymétrique : titre à gauche, texte d'accompagnement plus petit à droite (12.2). */
export default function EnTeteEcran({ titre, phrase }: Props) {
  return (
    <header className="grid grid-cols-1 items-end gap-6 lg:grid-cols-[1.4fr_1fr]">
      <h1 id="titre-ecran" className="text-titre-2 text-ink">
        {titre}
      </h1>
      <p className="text-secondaire text-muted lg:text-right">{phrase}</p>
    </header>
  );
}
