/** Réponses des routes `/api/decision` et `/api/melange` : affichage seulement. */

export interface CritereCatalogue {
  code: string;
  libelle: string;
  axe: string;
  unite: string;
  sens: "hausse" | "baisse" | "filtre";
  niveaux: string[];
  priorite: string;
  actif_defaut: boolean;
  actif_si: string[];
  calculable: boolean;
}

export interface SeuilApi {
  minimum: number | null;
  maximum: number | null;
}

export interface CriteresApi {
  axes: Record<string, string>;
  criteres: CritereCatalogue[];
  actifs: string[];
  poids: Record<string, number>;
  seuils: Record<string, SeuilApi>;
  methode: string;
  methodes: Record<string, string>;
  filtre_capacite: boolean;
  personnalises: boolean;
  sites: {
    id_site: string;
    nom: string;
    valeurs: Record<string, number | null>;
    motifs: Record<string, string>;
  }[];
}

export interface LigneClassement {
  id_site: string;
  nom: string;
  type: string;
  score: number;
  rang: number;
  variation: number | null;
  /** Classe de rang de la carte (0 : premiers), calculée par l'API. */
  classe: number;
  lon: number;
  lat: number;
  [contribution: `contribution_${string}`]: number;
}

export type ClassementApi =
  | { bloque: true; a_renseigner: string[] }
  | {
      bloque: false;
      methode: string;
      classement: LigneClassement[];
      exclus: { id_site: string; nom: string; motif: string; lon: number; lat: number }[];
      legende_rangs: { classe: number; rang_min: number; rang_max: number }[];
      retires: Record<string, string>;
      partiel: { utilises: number; actifs: number; partiel: boolean };
      libelles_retires: Record<string, string>;
      avertissements: string[];
      poids: Record<string, number>;
      criteres: string[];
      axes_criteres: Record<string, string>;
      scores_axes: Record<string, Record<string, number>>;
      libelles_axes: Record<string, string>;
      libelles_criteres: Record<string, string>;
      valeurs: Record<string, Record<string, number>>;
    };

export type RobustesseApi =
  | { bloque: true; a_renseigner: string[] }
  | {
      bloque: false;
      un_poids: { critere: string; variation: number; premier: string }[];
      seuils_changement: Record<string, number | null>;
      sites: {
        id_site: string;
        nom: string;
        proba_premier: number;
        proba_tete: number;
        rang_wsm: number;
        rang_topsis: number;
        robuste: boolean;
      }[];
      seuil_robustesse: number;
      tirages: number;
    };

export interface AhpApi {
  poids: Record<string, number>;
  matrices: Record<string, { poids: Record<string, number>; cr: number | null }>;
  cr_maximal: number;
  avertissements: string[];
}

export type MelangeApi =
  | { bloque: true; a_saisir: string[] }
  | {
      bloque: false;
      faisable: boolean;
      message: string;
      melange: {
        code_province: string;
        code_residu: string;
        nom_province: string;
        nom_residu: string;
        tonnage: number;
        part: number;
        cout_livre: number;
        cendres: number;
        humidite: number;
      }[];
      cout_moyen: number | null;
      cendres_moyennes: number | null;
      humidite_moyenne: number | null;
      bilan_moyen: number | null;
      bloquantes: string[];
      non_appliquees: string[];
      exclus: string[];
      capacite: number;
    };

interface PartielApi {
  utilises: number;
  actifs: number;
  partiel: boolean;
}

export type GisementsApi =
  | { bloque: true; a_renseigner: string[] }
  | {
      bloque: false;
      classable: false;
      site: string;
      couples: number;
      message: string;
      retires: Record<string, string>;
      libelles_retires: Record<string, string>;
      manquants: Record<string, number>;
      motifs_manquants: Record<string, string>;
      libelles_manquants: Record<string, string>;
      partiel: PartielApi;
    }
  | {
      bloque: false;
      classable: true;
      site: string;
      couples: number;
      classement: {
        code_province: string;
        nom_province: string;
        code_residu: string;
        nom_residu: string;
        rang: number;
        score: number;
        valeurs: Record<string, number>;
      }[];
      classes: number;
      exclus: { total: number; motifs: Record<string, number> };
      retires: Record<string, string>;
      libelles_retires: Record<string, string>;
      partiel: PartielApi;
      criteres: string[];
      libelles_criteres: Record<string, string>;
      unites: Record<string, string>;
      poids: Record<string, number>;
      avertissements: string[];
    };
