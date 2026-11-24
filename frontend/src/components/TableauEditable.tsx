import { PencilSimpleIcon } from "@phosphor-icons/react";
import { useState } from "react";

import type { Ligne } from "../lib/api";
import { cellule } from "../lib/format";
import ValeurSourcee from "./ValeurSourcee";

export interface Colonne {
  cle: string;
  libelle: string;
  /** Unité rappelée dans l'en-tête (section 12.1). */
  unite?: string;
  decimales?: number;
}

interface Props {
  colonnes: Colonne[];
  lignes: Ligne[];
  /** Colonne de la valeur, affichée avec sa provenance et modifiable. */
  colonneValeur?: string;
  /** Colonnes de provenance de chaque ligne (RG-03). */
  provenance?: { source: string; annee: string; statut?: string; version?: string };
  libelle: string;
  onModifier?: (ligne: Ligne, valeur: string) => void;
}

/** Tableau compact ; la valeur porte sa provenance et peut être corrigée (UC-DAT-07, UC-01). */
export default function TableauEditable({
  colonnes,
  lignes,
  colonneValeur,
  provenance,
  libelle,
  onModifier,
}: Props) {
  const [edition, setEdition] = useState<{ index: number; texte: string } | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-secondaire" aria-label={libelle}>
        <thead>
          <tr className="border-b border-line text-left text-libelle text-muted">
            {colonnes.map((c) => (
              <th key={c.cle} scope="col" className="whitespace-nowrap px-2 py-2 font-medium">
                {c.libelle}
                {c.unite ? ` (${c.unite})` : ""}
              </th>
            ))}
            {onModifier ? (
              <th scope="col" className="px-2 py-2">
                <span className="sr-only">Corriger</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {lignes.map((ligne, index) => (
            <tr key={index} className="border-b border-line last:border-0">
              {colonnes.map((c) => (
                <td key={c.cle} className="whitespace-nowrap px-2 py-1.5 align-top">
                  {c.cle === colonneValeur && edition?.index === index ? (
                    <form
                      className="flex gap-1"
                      onSubmit={(e) => {
                        e.preventDefault();
                        onModifier?.(ligne, edition.texte);
                        setEdition(null);
                      }}
                    >
                      <input
                        aria-label={`Nouvelle valeur de ${c.libelle}`}
                        className="w-28 rounded-segment border border-line px-1"
                        value={edition.texte}
                        onChange={(e) => {
                          setEdition({ index, texte: e.target.value });
                        }}
                      />
                      <button type="submit" className="text-libelle underline">
                        Valider
                      </button>
                    </form>
                  ) : c.cle === colonneValeur && provenance ? (
                    <ValeurSourcee
                      valeur={ligne[c.cle]}
                      decimales={c.decimales ?? 0}
                      provenance={{
                        source_id: texte(ligne[provenance.source]),
                        annee: texte(ligne[provenance.annee]),
                        statut: provenance.statut ? texte(ligne[provenance.statut]) : null,
                        version: provenance.version ? texte(ligne[provenance.version]) : null,
                        previsionnel: ligne.previsionnel === true,
                        note: texte(ligne.note),
                      }}
                    />
                  ) : (
                    <span className={typeof ligne[c.cle] === "number" ? "chiffres" : ""}>
                      {cellule(ligne[c.cle], c.decimales ?? 2)}
                    </span>
                  )}
                </td>
              ))}
              {onModifier ? (
                <td className="px-2 py-1.5 text-right">
                  <button
                    type="button"
                    className="text-muted hover:text-ink"
                    aria-label="Corriger la valeur de cette ligne"
                    onClick={() => {
                      setEdition({
                        index,
                        texte: colonneValeur ? brut(ligne[colonneValeur]) : "",
                      });
                    }}
                  >
                    <PencilSimpleIcon size={16} aria-hidden="true" />
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function brut(valeur: unknown): string {
  return typeof valeur === "number" || typeof valeur === "string" ? String(valeur) : "";
}

function texte(valeur: unknown): string | null {
  if (valeur === null || valeur === undefined || valeur === "") return null;
  if (typeof valeur === "string") return valeur;
  if (typeof valeur === "number" || typeof valeur === "boolean") return String(valeur);
  return JSON.stringify(valeur);
}
