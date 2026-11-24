import { useCallback, useEffect, useState } from "react";

import { api, ErreurApi, EVENEMENT_MODIFICATION } from "./api";

export interface EtatApi<T> {
  donnees: T | null;
  erreur: string | null;
  chargement: boolean;
  recharger: () => void;
}

/** Lit une route de l'API ; `recharger` relance la lecture (après une modification). */
export function useApi<T>(chemin: string | null): EtatApi<T> {
  const [donnees, setDonnees] = useState<T | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [chargement, setChargement] = useState(chemin !== null);
  const [compteur, setCompteur] = useState(0);

  useEffect(() => {
    if (chemin === null) return;
    let actif = true;
    setChargement(true);
    api<T>(chemin)
      .then((resultat) => {
        if (!actif) return;
        setDonnees(resultat);
        setErreur(null);
      })
      .catch((e: unknown) => {
        if (!actif) return;
        setErreur(e instanceof ErreurApi ? e.message : "La lecture des données a échoué.");
      })
      .finally(() => {
        if (actif) setChargement(false);
      });
    return () => {
      actif = false;
    };
  }, [chemin, compteur]);

  const recharger = useCallback(() => {
    setCompteur((c) => c + 1);
  }, []);

  // Toute modification enregistrée ailleurs (paramètres, import, saisie) rafraîchit la lecture.
  useEffect(() => {
    window.addEventListener(EVENEMENT_MODIFICATION, recharger);
    return () => {
      window.removeEventListener(EVENEMENT_MODIFICATION, recharger);
    };
  }, [recharger]);
  return { donnees, erreur, chargement, recharger };
}
