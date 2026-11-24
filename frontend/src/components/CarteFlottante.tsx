import type { ReactNode } from "react";

interface Props {
  titre: ReactNode;
  sousTitre?: ReactNode;
  /** Ligne grise de 11 px : source et date (section 12.2, règle 2). */
  source?: ReactNode;
  actions?: ReactNode;
  className?: string;
  children?: ReactNode;
}

/** Carte blanche de rayon 12 px qui porte les données (section 12.5). */
export default function CarteFlottante({
  titre,
  sousTitre,
  source,
  actions,
  className = "",
  children,
}: Props) {
  return (
    <section className={`rounded-carte border border-line bg-card p-4 shadow-douce ${className}`}>
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-texte text-secondaire font-medium tracking-normal text-ink">
            {titre}
          </h2>
          {sousTitre ? <p className="text-libelle text-muted">{sousTitre}</p> : null}
        </div>
        {actions}
      </header>
      {children ? <div className="mt-3">{children}</div> : null}
      {source ? <p className="mt-3 text-source text-muted">{source}</p> : null}
    </section>
  );
}
