import { useSyncExternalStore } from "react";

import { api, json } from "./api";

/** Opération de démonstration en cours : chargement d'un scénario ou retour aux données réelles. */
export type OperationDemo = { type: "chargement"; nom: string } | { type: "sortie" } | null;

// État partagé par tous les composants (bandeau sur chaque écran, section Démonstration) : tant
// qu'une opération est en cours, aucune autre ne peut partir (pas de « Quitter » pendant un
// chargement, qui laisserait la démonstration active une fois le chargement terminé).
let operation: OperationDemo = null;
const abonnes = new Set<() => void>();

function poser(nouvelle: OperationDemo): void {
  operation = nouvelle;
  for (const prevenir of abonnes) prevenir();
}

function abonner(prevenir: () => void): () => void {
  abonnes.add(prevenir);
  return () => {
    abonnes.delete(prevenir);
  };
}

/** Opération de démonstration en cours (null : aucune), mise à jour dans chaque composant. */
export function useOperationDemo(): OperationDemo {
  return useSyncExternalStore(abonner, () => operation);
}

async function executer(nouvelle: NonNullable<OperationDemo>, appel: () => Promise<unknown>) {
  if (operation !== null) return false;
  poser(nouvelle);
  try {
    await appel();
    return true;
  } finally {
    poser(null);
  }
}

/**
 * Charge un scénario de démonstration dans une copie de travail (données réelles intactes).
 * Renvoie false, sans rien faire, si une autre opération de démonstration est en cours.
 */
export function chargerDemonstration(identifiant: string, nom: string): Promise<boolean> {
  return executer({ type: "chargement", nom }, () =>
    api(`/demo/${encodeURIComponent(identifiant)}`, json("POST")),
  );
}

/** Quitte la démonstration : l'outil revient aux paramètres et données réels, intacts. */
export function quitterDemonstration(): Promise<boolean> {
  return executer({ type: "sortie" }, () => api("/demo", json("DELETE")));
}

/** Texte de l'indicateur d'une opération en cours. */
export function texteOperation(o: NonNullable<OperationDemo>): string {
  return o.type === "chargement"
    ? `Chargement de la démonstration « ${o.nom} »…`
    : "Retour aux données réelles…";
}
