/** Réponses des routes `/api/acv` (UC-ACV-01 à 03) : affichage seulement. */

export type Terme = "E_col" | "E_pre" | "E_tr" | "E_pyr" | "E_ep" | "E_ref" | "stock" | "BN";

export interface ContexteAcv {
  unite_fonctionnelle: string;
  standard: string;
  classe_temperature: string | null;
  permanence: number | null;
  permanence_motif: string | null;
  etapes: Record<string, string>;
  projet: string;
  dossier_brightway: string;
  methode: string[];
}

export interface BilanResidu {
  code_residu: string;
  nom: string;
  scenario: string | null;
  couples: number;
  couples_calcules: number;
  BN_median: number | null;
  BN_min: number | null;
  BN_max: number | null;
  motif: string | null;
}

export interface BilanCouple extends Record<Terme, number> {
  code_province: string;
  nom_province: string;
  code_residu: string;
  nom_residu: string;
  distance_km: number;
  statut: string;
  sources: string;
}

export interface BilansSite extends ContexteAcv {
  site: string;
  couples: number;
  couples_calcules: number;
  par_residu: BilanResidu[];
  bilan_site: (Record<Terme, number> & { tonnage: number; couples: number }) | null;
  motif_site: string | null;
  a_saisir: { motif: string; couples: number }[];
  bilans: BilanCouple[];
}
