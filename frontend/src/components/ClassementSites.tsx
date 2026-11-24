import { CaretDownIcon, CaretUpIcon } from "@phosphor-icons/react";
import { Link } from "react-router";

import type { LigneClassement } from "../lib/decision";
import { nombre } from "../lib/format";
import { couleursAxes, type Axe } from "../theme/couleurs";
import BarresSegmentees from "./BarresSegmentees";

interface Props {
  lignes: LigneClassement[];
  scoresAxes: Record<string, Record<string, number>>;
  libellesAxes: Record<string, string>;
  limite?: number | undefined;
}

/** Variation de rang depuis le réglage précédent (RG-16) : ▲ up, ▼ ember. */
export function Variation({ valeur }: { valeur: number | null }) {
  if (valeur === null || valeur === 0)
    return (
      <span
        className="text-libelle text-muted"
        title={valeur === 0 ? "rang inchangé" : "pas de réglage précédent à comparer"}
      >
        {valeur === 0 ? "=" : "—"}
      </span>
    );
  return valeur > 0 ? (
    <span className="inline-flex items-center gap-0.5 text-libelle font-medium text-up">
      <CaretUpIcon size={12} weight="fill" aria-hidden="true" />
      {nombre(valeur)}
      <span className="sr-only"> places gagnées</span>
    </span>
  ) : (
    <span className="inline-flex items-center gap-0.5 text-libelle font-medium text-ember">
      <CaretDownIcon size={12} weight="fill" aria-hidden="true" />
      {nombre(-valeur)}
      <span className="sr-only"> places perdues</span>
    </span>
  );
}

/** Classement des sites : cartes horizontales, rang en grand, mini barres par axe (12.5). */
export default function ClassementSites({ lignes, scoresAxes, libellesAxes, limite }: Props) {
  const affichees = limite ? lignes.slice(0, limite) : lignes;
  return (
    <ol className="grid gap-3">
      {affichees.map((l) => {
        const axes = Object.entries(scoresAxes[l.id_site] ?? {});
        return (
          <li
            key={l.id_site}
            className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-4 rounded-carte border border-line bg-card p-4 shadow-douce lg:grid-cols-[64px_minmax(0,1.2fr)_minmax(0,2fr)]"
          >
            <span className="chiffres text-titre-2 text-ink" aria-label={`rang ${String(l.rang)}`}>
              {nombre(l.rang)}
            </span>
            <div>
              <Link
                to={`/fiche-site?site=${encodeURIComponent(l.id_site)}`}
                className="text-texte font-medium text-ink underline-offset-2 hover:underline"
              >
                {l.nom}
              </Link>
              <p className="flex items-center gap-2 text-libelle text-muted">
                score {nombre(l.score, 3, 3)} · <Variation valeur={l.variation} />
              </p>
            </div>
            <div className="col-span-2 grid grid-cols-2 gap-x-4 gap-y-1 lg:col-span-1">
              {axes.map(([axe, part]) => (
                <BarresSegmentees
                  key={axe}
                  libelle={`${axe} · ${libellesAxes[axe] ?? axe}`}
                  part={part}
                  axe={(axe in couleursAxes ? axe : "A") as Axe}
                />
              ))}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
