import type { Version } from "./api";

/** Réponse de `/api/donnees/resume` : faits calculés par l'API pour les titres des écrans. */
export interface Resume {
  provinces_total: number;
  provinces_avec_production: number;
  provinces_avec_valeur_reelle: number;
  provinces_estimees_seulement: number;
  cultures: string[];
  campagne_min: string | null;
  campagne_max: string | null;
  valeurs_production: number;
  valeurs_reelles: number;
  a_completer: Record<string, number>;
  a_completer_total: number;
  derniere_version: Version | null;
  sources: number;
}
