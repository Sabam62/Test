/**
 * Rangement des paramètres sur l'écran Paramètres (présentation seulement, section 14) :
 * sections du menu de gauche, puis cartes de quelques champs. Un identifiant se termine par
 * « : » pour désigner toutes les composantes d'un paramètre (« PAR-14: »). Un paramètre
 * technique absent de ce rangement est affiché dans « Réglages techniques », carte « Autres ».
 */

export type Origine = "entreprise" | "technique";

export interface CarteParametres {
  titre: string;
  description: string;
  origine: Origine;
  parametres: string[];
}

export interface SectionParametres {
  id: string;
  titre: string;
  description: string;
  /** Section repliée à l'ouverture de l'écran. */
  repliee: boolean;
  cartes: CarteParametres[];
}

export const SECTIONS: SectionParametres[] = [
  {
    id: "entreprise",
    titre: "Entreprise",
    description:
      "Stratégie d'Atlantic Biochar (section 14.1) ; les quatre paramètres obligatoires orientent tout le classement (RG-15).",
    repliee: false,
    cartes: [
      {
        titre: "Paramètres obligatoires",
        description: "Sans eux, le classement des sites et le coût livré restent bloqués.",
        origine: "entreprise",
        parametres: ["PAR-01", "PAR-21", "PAR-34", "PAR-37"],
      },
      {
        titre: "Sites",
        description: "Sites toujours évalués ou retirés du classement.",
        origine: "entreprise",
        parametres: ["PAR-57"],
      },
    ],
  },
  {
    id: "approvisionnement",
    titre: "Approvisionnement et logistique",
    description: "Bassin, mélange et transport des résidus jusqu'à l'usine.",
    repliee: false,
    cartes: [
      {
        titre: "Bassin d'approvisionnement",
        description: "Les gisements au-delà de cette distance sont exclus du bassin.",
        origine: "entreprise",
        parametres: ["PAR-59"],
      },
      {
        titre: "Contraintes du mélange",
        description: "Moyennes maximales et dépendance à un seul résidu (programme du mélange).",
        origine: "entreprise",
        parametres: ["PAR-52", "PAR-53", "PAR-51"],
      },
      {
        titre: "Procédés des résidus",
        description: "Procédé ou forme retenus quand un résidu en a plusieurs (section 8.1).",
        origine: "technique",
        parametres: ["PAR-62", "PAR-63"],
      },
      {
        titre: "Camion",
        description: "Caractéristiques du camion lourd et coût fixe d'une rotation.",
        origine: "technique",
        parametres: ["PAR-31", "PAR-38", "PAR-32", "PAR-61"],
      },
      {
        titre: "Coût du transport",
        description: "Coût variable calculé à partir du prix du gazole saisi par l'entreprise.",
        origine: "technique",
        parametres: ["PAR-37", "PAR-39", "PAR-33", "PAR-30"],
      },
    ],
  },
  {
    id: "economie",
    titre: "Économie",
    description: "Prix de vente, crédit carbone et prix d'achat des résidus.",
    repliee: false,
    cartes: [
      {
        titre: "Recettes",
        description: "Marge estimée de chaque site (critère C6).",
        origine: "entreprise",
        parametres: ["PAR-55", "PAR-56"],
      },
      {
        titre: "Prix d'achat des résidus",
        description: "Prix cités pour les résidus déjà commercialisés (PAR-14).",
        origine: "technique",
        parametres: ["PAR-14:"],
      },
    ],
  },
  {
    id: "carbone",
    titre: "Carbone et ACV",
    description: "Permanence du carbone stocké et facteurs du bilan climat.",
    repliee: false,
    cartes: [
      {
        titre: "Permanence du carbone",
        description: "Fraction du carbone encore stockée à 100 ans, par classe de température.",
        origine: "technique",
        parametres: ["PAR-20:"],
      },
      {
        titre: "Électricité et objectif",
        description: "Émissions du réseau marocain ; poids du carbone dans le mélange.",
        origine: "technique",
        parametres: ["PAR-24", "PAR-54"],
      },
      {
        titre: "Potentiels de réchauffement",
        description: "PRG à 100 ans du 6e rapport du GIEC (méthode Brightway).",
        origine: "technique",
        parametres: ["PAR-27:"],
      },
    ],
  },
  {
    id: "techniques",
    titre: "Réglages techniques",
    description: "Réglages de calcul et de décision (section 14.3), rarement modifiés.",
    repliee: true,
    cartes: [
      {
        titre: "Campagne et Monte Carlo",
        description: "Campagne de référence, tirages et graine aléatoire.",
        origine: "technique",
        parametres: ["PAR-02", "PAR-03", "PAR-04"],
      },
      {
        titre: "Critères",
        description: "Rayons des critères et alerte de corrélation.",
        origine: "technique",
        parametres: ["PAR-35", "PAR-36", "PAR-43"],
      },
      {
        titre: "Classement et robustesse",
        description: "Méthode par défaut, poids, cohérence AHP et seuil de robustesse.",
        origine: "technique",
        parametres: ["PAR-40", "PAR-45", "PAR-44", "PAR-41", "PAR-42"],
      },
    ],
  },
];

/** Vrai si l'identifiant ``id`` appartient au motif ``motif`` (« PAR-14: » couvre « PAR-14:x »). */
export function correspond(motif: string, id: string): boolean {
  return motif.endsWith(":") ? id.startsWith(motif) : id === motif;
}
