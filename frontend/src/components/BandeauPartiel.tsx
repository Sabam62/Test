import { WarningIcon } from "@phosphor-icons/react";

import { nombre } from "../lib/format";

interface Props {
  utilises: number;
  actifs: number;
  retires: Record<string, string>;
  libelles: Record<string, string>;
  /** « classement des sites » ou « classement des gisements ». */
  objet: string;
  /** Version courte, posée sur une carte : titre et critères retirés, sans les motifs. */
  compact?: boolean;
}

/**
 * Bandeau « Classement partiel : n critères sur N » (décision de l'équipe du 23/11/2026) :
 * chaque critère actif retiré du calcul est listé avec son motif ; son poids est redistribué.
 */
export default function BandeauPartiel({
  utilises,
  actifs,
  retires,
  libelles,
  objet,
  compact = false,
}: Props) {
  const codes = Object.keys(retires);
  if (!codes.length) return null;
  if (compact)
    return (
      <div
        role="status"
        aria-label="Classement partiel"
        className="max-w-[360px] rounded-carte border-2 border-ember bg-card px-3 py-2 shadow-douce"
      >
        <p className="flex items-center gap-2 text-secondaire font-medium text-ink">
          <WarningIcon size={16} className="shrink-0 text-ember" aria-hidden="true" />
          Classement partiel : {nombre(utilises)} critères sur {nombre(actifs)}
        </p>
        <p className="mt-0.5 text-libelle text-muted">
          Non comptés : {codes.map((c) => `${c} ${libelles[c] ?? ""}`.trim()).join(", ")}
        </p>
      </div>
    );
  return (
    <section
      role="status"
      aria-label="Classement partiel"
      className="rounded-carte border-2 border-ember bg-card p-4"
    >
      <p className="flex items-center gap-2 text-texte font-medium text-ink">
        <WarningIcon size={20} className="shrink-0 text-ember" aria-hidden="true" />
        Classement partiel : {nombre(utilises)} critères sur {nombre(actifs)}
      </p>
      <p className="mt-1 text-secondaire text-muted">
        Le {objet} ne tient pas compte des critères suivants ; leur poids est redistribué entre les
        critères calculés. Une valeur manquante n'est jamais comptée zéro (RG-14).
      </p>
      <ul className="mt-2 grid gap-1 text-libelle text-ink">
        {codes.map((code) => (
          <li key={code}>
            <span className="font-medium">
              {code} · {libelles[code] ?? code}
            </span>{" "}
            : {retires[code]}
          </li>
        ))}
      </ul>
    </section>
  );
}
