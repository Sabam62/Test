import { InfoIcon } from "@phosphor-icons/react";
import * as Popover from "@radix-ui/react-popover";
import { useState } from "react";

import type { Statut } from "../lib/api";
import { STATUTS_SIGNALES } from "../lib/statuts";
import { cellule } from "../lib/format";

export interface ProvenanceAffichee {
  source_id: string | null;
  annee: number | string | null;
  statut: string | null;
  version?: string | null;
  previsionnel?: boolean;
  note?: string | null;
}

interface Props {
  valeur: unknown;
  unite?: string;
  decimales?: number;
  provenance: ProvenanceAffichee;
}

/** Valeur dont la provenance s'affiche au survol ou au clic (UC-01, RG-03). */
export default function ValeurSourcee({ valeur, unite, decimales = 0, provenance }: Props) {
  const [ouvert, setOuvert] = useState(false);
  const signale = STATUTS_SIGNALES.includes(provenance.statut as Statut);
  const texte =
    valeur === null || valeur === undefined ? "À compléter" : cellule(valeur, decimales);
  return (
    <Popover.Root open={ouvert} onOpenChange={setOuvert}>
      <Popover.Trigger
        className="chiffres inline-flex items-center gap-1 rounded-segment underline decoration-line decoration-dotted underline-offset-4 hover:decoration-muted"
        onMouseEnter={() => {
          setOuvert(true);
        }}
        onMouseLeave={() => {
          setOuvert(false);
        }}
        aria-label={`${texte}${unite ? ` ${unite}` : ""} : voir la provenance`}
      >
        {texte}
        {unite ? <span className="text-muted">{unite}</span> : null}
        {signale ? (
          <InfoIcon
            size={12}
            className="text-muted"
            aria-label={`statut ${provenance.statut ?? ""}`}
          />
        ) : null}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded-bouton border border-line bg-card p-3 text-libelle text-ink shadow-douce"
        >
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted">Source</dt>
            <dd>{provenance.source_id ?? "—"}</dd>
            <dt className="text-muted">Année</dt>
            <dd>{provenance.annee ?? "—"}</dd>
            <dt className="text-muted">Statut</dt>
            <dd>
              {provenance.statut ?? "—"}
              {provenance.previsionnel ? " · prévisionnelle" : ""}
            </dd>
            {provenance.version ? (
              <>
                <dt className="text-muted">Version</dt>
                <dd>{provenance.version}</dd>
              </>
            ) : null}
          </dl>
          {provenance.note ? <p className="mt-2 text-muted">{provenance.note}</p> : null}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
