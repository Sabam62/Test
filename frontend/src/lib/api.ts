/** Client de l'API locale (`/api`) : requêtes typées et erreurs en français (ENF-12). */

export class ErreurApi extends Error {
  constructor(
    message: string,
    readonly statut: number,
    readonly confirmationRequise = false,
  ) {
    super(message);
    this.name = "ErreurApi";
  }
}

interface CorpsErreur {
  erreur?: string;
  confirmation_requise?: boolean;
}

/** Appelle l'API et renvoie le JSON ; lève {@link ErreurApi} avec le message du serveur. */
export async function api<T>(chemin: string, options: RequestInit = {}): Promise<T> {
  let reponse: Response;
  try {
    const entetes = new Headers(options.headers);
    if (!(options.body instanceof FormData) && !entetes.has("Content-Type")) {
      entetes.set("Content-Type", "application/json");
    }
    reponse = await fetch(`/api${chemin}`, { ...options, headers: entetes });
  } catch {
    throw new ErreurApi(
      "L'outil ne répond pas : vérifiez que « python -m ab_dss » est lancé dans un terminal.",
      0,
    );
  }
  if (!reponse.ok) {
    let corps: CorpsErreur = {};
    try {
      corps = (await reponse.json()) as CorpsErreur;
    } catch {
      corps = {};
    }
    throw new ErreurApi(
      corps.erreur ?? "La requête n'a pas pu aboutir.",
      reponse.status,
      corps.confirmation_requise === true,
    );
  }
  const corps = (await reponse.json()) as T;
  if (options.method && options.method !== "GET") signalerModification();
  return corps;
}

/** Événement émis après toute modification : les lectures en cours se rafraîchissent. */
export const EVENEMENT_MODIFICATION = "ab-dss:modification";

/** Prévient les écrans qu'une donnée ou un paramètre vient de changer. */
export function signalerModification(): void {
  window.dispatchEvent(new Event(EVENEMENT_MODIFICATION));
}

/** Corps JSON d'une requête. */
export function json(methode: "POST" | "PUT" | "DELETE", corps?: unknown): RequestInit {
  return corps === undefined
    ? { method: methode }
    : { method: methode, body: JSON.stringify(corps) };
}

// --- Types des réponses ----------------------------------------------------------------

export type Statut = "Mesurée" | "Estimée" | "Littérature" | "Terrain" | "Hypothèse";

export interface Provenance {
  source_id: string;
  annee: number | null;
  statut: Statut;
  version: string | null;
  autres_sources?: string[];
  note?: string | null;
}

export interface ValeurSourceeApi {
  nom: string;
  valeur: number | string | null;
  unite: string;
  provenance: Provenance | null;
  ou_trouver: string | null;
  a_completer: boolean;
  min: number | null;
  max: number | null;
  mode: number | null;
  loi: string | null;
}

export interface Sante {
  statut: string;
  version_outil: string;
  donnees_preparees: boolean;
  osrm: string;
}

export type ValeurEntreprise = number | string | string[] | Record<string, string[]> | null;

export interface ParametreEntrepriseApi {
  identifiant: string;
  libelle: string;
  unite: string;
  type: "nombre" | "choix" | "nombre_ou_choix" | "sites";
  choix: string[];
  obligatoire: boolean;
  valeur: ValeurEntreprise;
}

export interface EntrepriseApi {
  renseignement_requis: boolean;
  obligatoires: string[];
  a_renseigner: string[];
  date_modification: string | null;
  auteur: string | null;
  parametres: ParametreEntrepriseApi[];
  modifies?: string[];
}

export interface ParametreTechnique {
  identifiant: string;
  libelle: string;
  defaut: ValeurSourceeApi | null;
  courante: ValeurSourceeApi | null;
  modifie: boolean;
  calcul: string | null;
}

export interface ScenarioApi {
  nom: string;
  date: string;
  auteur: string;
  version_donnees: string | null;
  parametres_entreprise: Record<string, ValeurEntreprise>;
  ecart_version: string | null;
}

/** Scénario de démonstration (scenarios/demo/, docs/demo.md). */
export interface ScenarioDemoApi {
  identifiant: string;
  nom: string;
  description: string;
}

/** Démonstration chargée : la copie de travail remplace les données réelles, intactes. */
export interface DemoActiveApi {
  identifiant: string;
  nom: string;
  bandeau: string;
  date: string;
}

export interface DemoApi {
  active: DemoActiveApi | null;
  bandeau: string;
  scenarios: ScenarioDemoApi[];
}

export interface TableInfo {
  table: string;
  libelle: string;
  cle: string[];
  mise_a_jour: string | null;
  lignes: number | null;
  disponible: boolean;
}

export type Ligne = Record<string, unknown>;

export interface PageTable {
  table: string;
  total: number;
  page: number;
  lignes_par_page: number;
  colonnes: string[];
  lignes: Ligne[];
}

export interface Version {
  id_version: string;
  date: string;
  auteur: string;
  commentaire: string;
  tables_modifiees: string[];
  nb_lignes_ajoutees: number;
  nb_lignes_modifiees: number;
  nb_lignes_supprimees: number;
  restauration_de: string | null;
}

export interface ApercuImport {
  import: string;
  table: string;
  ajoutees: number[];
  modifiees: number[];
  rejetees: { ligne: number; motif: string }[];
  a_confirmer: { ligne: number; motif: string }[];
}

export interface Comparaison {
  table: string;
  ajoutees: Ligne[];
  modifiees: Ligne[];
  avant: Ligne[];
  supprimees: Ligne[];
}

export interface StatutProvince {
  code_province: string;
  nom_fr: string;
  statut: "réelle" | "estimée" | "absente";
  valeurs: number;
  valeurs_reelles: number;
  sources: string[];
  niveaux_source: string[];
}

export interface StatutProvinces {
  provinces: StatutProvince[];
  resume: Partial<Record<StatutProvince["statut"], number>>;
  total: number;
}

export interface SourceApi {
  source_id: string;
  titre: string;
  url?: string;
  licence?: string;
  parent?: string;
  fichiers?: Record<string, { date_telechargement?: string; sha256?: string }>;
}

export interface PrixApi {
  historique: Ligne[];
  courants: Ligne[];
}

export interface GeoJsonContours {
  type: "FeatureCollection";
  features: unknown[];
  attribution: string;
}
