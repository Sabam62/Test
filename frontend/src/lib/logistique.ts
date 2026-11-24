/** Réponses des routes `/api/logistique` (UC-LOG-01 à 04) : affichage seulement. */

import type { FeatureCollection } from "geojson";

export interface Site {
  id_site: string;
  nom: string;
  type: "chef-lieu" | "agropole" | "utilisateur";
  lon: number;
  lat: number;
  code_province: string | null;
  nom_province: string | null;
  impose: boolean;
  source_id: string;
  annee: number | null;
  statut: string;
  note: string;
  tonnage_rayon_c3: number | null;
}

export interface SitesLogistique {
  sites: Site[];
  a_completer: { id_site: string; nom: string; type: string; ou_trouver: string }[];
  methode: "osrm" | "vol_oiseau";
  message: string | null;
  calibration: { coefficient: number; paires: number; date: string } | null;
  rayon_c3: number | null;
  transport_bloque: string | null;
}

export interface PointCourbe {
  code_province: string;
  nom_province: string;
  code_residu: string;
  nom_residu: string;
  tonnage: number;
  cumul: number;
  cout_livre: number;
  distance_km: number;
  prix_achat: number;
  cout_collecte: number;
  cout_pretraitement: number;
  cout_transport: number;
  statut: string;
  sources: string;
  dans_bassin: boolean;
}

interface CourbeBase {
  site: Site;
  methode: "osrm" | "vol_oiseau";
  message: string | null;
  gisements_calcules: number;
}

export interface CourbeBloquee extends CourbeBase {
  bloque: true;
  a_saisir: string[];
}

export interface CourbeCalculee extends CourbeBase {
  bloque: false;
  capacite: number;
  plafond: number;
  points: PointCourbe[];
  tonnage_total: number;
  tonnage_sous_plafond: number;
  atteignable: boolean;
  manque: number;
  cout_moyen_k: number | null;
  cout_marginal_k: number | null;
  distance_moyenne_k: number | null;
  distance_max_bassin: number | null;
  exclus: { motif: string; couples: number; residus: string[] }[];
}

export type Courbe = CourbeBloquee | CourbeCalculee;

export type Bassin =
  | { site: Site; bloque: true; a_saisir: string[] }
  | {
      site: Site;
      bloque: false;
      gisements: FeatureCollection;
      distance_max_bassin: number | null;
      isodistance: FeatureCollection | null;
      coefficient_detour: number | null;
    };

export interface EtatOsrm {
  osrm: boolean;
  url: string;
  commande: string;
}
