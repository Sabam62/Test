import { DownloadSimpleIcon } from "@phosphor-icons/react";
import { useState } from "react";

import { ErreurApi } from "../lib/api";
import Bouton from "./Bouton";

export interface ColonneExport {
  cle: string;
  libelle: string;
  unite?: string;
}

export interface TableExport {
  titre: string;
  colonnes: ColonneExport[];
  lignes: Record<string, unknown>[];
  partiel?: {
    utilises: number;
    actifs: number;
    retires: Record<string, string>;
    libelles: Record<string, string>;
  };
  notes?: string[];
}

interface Props {
  /** Export produit par le serveur (classements), sans l'extension : « /exports/classement ». */
  route?: string;
  /** Paramètres de requête de l'export serveur (méthode, site). */
  requete?: string;
  /** Tableau affiché, envoyé tel quel (les valeurs viennent de l'API). */
  table?: TableExport;
}

async function telecharger(reponse: Response, defaut: string): Promise<void> {
  if (!reponse.ok) {
    let message = "L'export a échoué.";
    try {
      message = ((await reponse.json()) as { erreur?: string }).erreur ?? message;
    } catch {
      // réponse sans corps JSON
    }
    throw new ErreurApi(message, reponse.status);
  }
  const nom = /filename="([^"]+)"/.exec(reponse.headers.get("content-disposition") ?? "")?.[1];
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(await reponse.blob());
  lien.download = nom ?? defaut;
  lien.click();
  URL.revokeObjectURL(lien.href);
}

/** Boutons « CSV » et « Excel » (UC-RES-02) ; l'Excel a les feuilles « paramètres » et « sources ». */
export default function BoutonsExport({ route, requete = "", table }: Props) {
  const [erreur, setErreur] = useState<string | null>(null);
  async function exporter(format: "csv" | "xlsx") {
    setErreur(null);
    try {
      const reponse = route
        ? await fetch(`/api${route}.${format}${requete ? `?${requete}` : ""}`)
        : await fetch(`/api/exports/${format}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(table),
          });
      await telecharger(reponse, `export.${format}`);
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "L'export a échoué.");
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {(["xlsx", "csv"] as const).map((format) => (
        <Bouton
          key={format}
          variante="secondaire"
          icone={<DownloadSimpleIcon size={16} aria-hidden="true" />}
          onClick={() => void exporter(format)}
        >
          {format === "xlsx" ? "Exporter en Excel" : "Exporter en CSV"}
        </Bouton>
      ))}
      {erreur ? (
        <p role="alert" className="text-libelle text-ink">
          {erreur}
        </p>
      ) : null}
    </div>
  );
}
