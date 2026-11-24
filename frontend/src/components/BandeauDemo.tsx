import { PresentationChartIcon } from "@phosphor-icons/react";
import { useState } from "react";

import { ErreurApi, signalerModification, type DemoApi } from "../lib/api";
import { quitterDemonstration, useOperationDemo } from "../lib/demo";
import { useApi } from "../lib/useApi";
import Bouton from "./Bouton";
import IndicateurDemo from "./IndicateurDemo";

interface Props {
  /** Version imprimée (fiche site, exports d'écran) : sans bouton. */
  impression?: boolean;
}

/**
 * Bandeau « Démonstration — paramètres d'hypothèse, pas un résultat réel », visible sur tous les
 * écrans tant qu'un scénario de démonstration est chargé, et en tête de toute page imprimée.
 * Pendant un chargement ou un retour aux données réelles, il porte l'indicateur de l'opération
 * et son bouton « Quitter » est désactivé.
 */
export default function BandeauDemo({ impression = false }: Props) {
  const demo = useApi<DemoApi>("/demo");
  const operation = useOperationDemo();
  const [erreur, setErreur] = useState<string | null>(null);
  const active = demo.donnees?.active;
  if (impression && !active) return null;
  if (!active)
    return operation ? (
      <div className="rounded-carte border-2 border-ember bg-card px-4 py-2 shadow-douce">
        <IndicateurDemo operation={operation} />
      </div>
    ) : null;

  async function quitter() {
    try {
      if (await quitterDemonstration()) signalerModification();
      setErreur(null);
    } catch (ex) {
      setErreur(ex instanceof ErreurApi ? ex.message : "Retour aux données réelles impossible.");
    }
  }

  return (
    <div
      role="status"
      aria-label="Démonstration"
      aria-busy={operation !== null}
      className="flex flex-wrap items-center justify-between gap-3 rounded-carte border-2 border-ember bg-card px-4 py-2 shadow-douce"
    >
      <p className="flex items-center gap-2 text-secondaire font-medium text-ink">
        <PresentationChartIcon size={20} className="shrink-0 text-ember" aria-hidden="true" />
        <span>
          {active.bandeau}
          <span className="font-normal text-muted"> · {active.nom}</span>
        </span>
      </p>
      {impression ? null : (
        <div className="flex items-center gap-3">
          {operation ? <IndicateurDemo operation={operation} /> : null}
          {erreur ? <span className="text-libelle text-ink">{erreur}</span> : null}
          <Bouton
            variante="secondaire"
            disabled={operation !== null}
            onClick={() => {
              void quitter();
            }}
          >
            Quitter la démonstration
          </Bouton>
        </div>
      )}
    </div>
  );
}
