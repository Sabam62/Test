import { WarningCircleIcon } from "@phosphor-icons/react";

/** Message d'erreur en français, lisible (contraste AA) : texte ink, repère ember. */
export default function MessageErreur({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-start gap-2 text-secondaire text-ink">
      <WarningCircleIcon size={18} className="mt-0.5 shrink-0 text-ember" aria-hidden="true" />
      {message}
    </p>
  );
}
