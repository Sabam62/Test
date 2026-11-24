/** Réponses de /api/potentiel (gisements, section 8.1) : affichage seulement. */

export interface IndicateurGisement {
  code: string;
  libelle: string;
  unite: string;
  additif: boolean;
}

export interface ResiduApi {
  code: string;
  nom: string;
}

export interface IndicateursPotentiel {
  indicateurs: IndicateurGisement[];
  residus: ResiduApi[];
}

export interface ProvinceCarte {
  code_province: string;
  nom_fr: string;
  valeur: number | null;
  statut: string | null;
  sources: string[];
  campagnes: string[];
  previsionnel: boolean;
  residus_calcules: string[];
  motifs: string[];
  classe: number | null;
}

export interface CarteGisements {
  residu: string;
  indicateur: string;
  libelle: string;
  unite: string;
  bornes: number[];
  provinces: ProvinceCarte[];
  provinces_avec_valeur: number;
}

export interface CelluleGisement {
  valeur: number | null;
  statut?: string;
  sources?: string;
  annee?: string;
  previsionnel?: boolean;
  note?: string;
  motif?: string | null;
}

export interface TableauGisements {
  indicateur: string;
  libelle: string;
  unite: string;
  residus: ResiduApi[];
  lignes: { code_province: string; nom_fr: string; cellules: Record<string, CelluleGisement> }[];
}

export interface TotalGisement {
  indicateur: string;
  libelle: string;
  unite: string;
  total: number | null;
  residus_calcules: string[];
}

export interface SyntheseGisements {
  residus: number;
  totaux: TotalGisement[];
  par_residu: {
    code_residu: string;
    indicateur: string;
    total: number | null;
    unite: string;
    provinces_calculees: number;
    provinces_exclues: number;
    statut: string | null;
  }[];
  bloquants: { motif: string; couples: number; residus: string[] }[];
}
