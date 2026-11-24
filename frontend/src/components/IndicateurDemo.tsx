import { CircleNotchIcon } from "@phosphor-icons/react";

import { texteOperation, type OperationDemo } from "../lib/demo";

/** Indicateur d'une opération de démonstration en cours ; les boutons restent désactivés. */
export default function IndicateurDemo({ operation }: { operation: NonNullable<OperationDemo> }) {
  return (
    <p
      role="status"
      aria-label="Chargement de la démonstration"
      className="flex items-center gap-2 text-secondaire text-ink"
    >
      <CircleNotchIcon
        size={18}
        className="shrink-0 animate-spin text-ember motion-reduce:animate-none"
        aria-hidden="true"
      />
      {texteOperation(operation)}
    </p>
  );
}
