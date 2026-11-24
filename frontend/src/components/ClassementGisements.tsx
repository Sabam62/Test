import { useState } from "react";

import type { GisementsApi } from "../lib/decision";
import { nombre } from "../lib/format";
import type { SitesLogistique } from "../lib/logistique";
import { useApi } from "../lib/useApi";
import BandeauPartiel from "./BandeauPartiel";
import Bouton from "./Bouton";
import BoutonsExport from "./BoutonsExport";
import CarteFlottante from "./CarteFlottante";
import MessageErreur from "./MessageErreur";

/** Classement des gisements (couples province × résidu) sur les critères de niveau G. */
export default function ClassementGisements({ methode }: { methode: string }) {
  const sites = useApi<SitesLogistique>("/logistique/sites");
  const [site, setSite] = useState("AGP-MEKNES");
  const [tout, setTout] = useState(false);
  const g = useApi<GisementsApi>(
    `/decision/gisements?site=${encodeURIComponent(site)}&methode=${methode}`,
  );
  const d = g.donnees;
  const nomSite = sites.donnees?.sites.find((s) => s.id_site === site)?.nom ?? site;
  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h2 className="text-titre-3">
          {d && !d.bloque && d.classable
            ? `${d.classement[0]?.nom_residu ?? ""} de ${d.classement[0]?.nom_province ?? ""} est le 1er des ${nombre(d.classes)} gisements classés pour ${nomSite}`
            : `Classement des gisements pour ${nomSite}`}
        </h2>
        <label className="grid gap-1 text-libelle text-muted">
          Site (coût livré C1, marge C6 et bilan D1)
          <select
            value={site}
            onChange={(e) => {
              setSite(e.target.value);
            }}
            className="rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire text-ink"
          >
            {(sites.donnees?.sites ?? []).map((s) => (
              <option key={s.id_site} value={s.id_site}>
                {s.nom}
              </option>
            ))}
          </select>
        </label>
      </div>
      {g.erreur ? <MessageErreur message={g.erreur} /> : null}
      {d && !d.bloque ? (
        <BandeauPartiel
          utilises={d.partiel.utilises}
          actifs={d.partiel.actifs}
          retires={d.retires}
          libelles={d.libelles_retires}
          objet="classement des gisements"
        />
      ) : null}
      {d && !d.bloque && !d.classable ? (
        <CarteFlottante
          titre="Les gisements ne peuvent pas encore être classés"
          sousTitre={d.message}
        >
          <ul className="grid gap-1 text-secondaire text-ink">
            {Object.entries(d.manquants).map(([k, n]) => (
              <li key={k}>
                {k} · {d.libelles_manquants[k]} : manque pour {nombre(n)} couples sur{" "}
                {nombre(d.couples)} ({d.motifs_manquants[k]})
              </li>
            ))}
          </ul>
          <p className="mt-2 text-libelle text-muted">
            Complétez ces valeurs, ou désactivez le critère dans l'onglet Critères : un couple à qui
            manque un critère calculé pour d'autres couples est exclu, jamais compté zéro.
          </p>
        </CarteFlottante>
      ) : null}
      {d && !d.bloque && d.classable ? (
        <>
          <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
            <table className="w-full text-secondaire" aria-label="Classement des gisements">
              <thead>
                <tr className="border-b border-line text-left text-libelle text-muted">
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Rang
                  </th>
                  <th scope="col" className="px-2 py-2 font-medium">
                    Gisement (résidu · province)
                  </th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Score (0 à 1)
                  </th>
                  {d.criteres.map((k) => (
                    <th
                      key={k}
                      scope="col"
                      className="px-2 py-2 text-right font-medium"
                      title={d.libelles_criteres[k]}
                    >
                      {k} ({d.unites[k]})
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(tout ? d.classement : d.classement.slice(0, 20)).map((l) => (
                  <tr
                    key={`${l.code_province}-${l.code_residu}`}
                    className="border-b border-line last:border-0"
                  >
                    <td className="chiffres px-2 py-1.5 text-right">{nombre(l.rang)}</td>
                    <th scope="row" className="px-2 py-1.5 text-left font-normal">
                      {l.nom_residu} · {l.nom_province}
                    </th>
                    <td className="chiffres px-2 py-1.5 text-right">{nombre(l.score, 3, 3)}</td>
                    {d.criteres.map((k) => (
                      <td key={k} className="chiffres px-2 py-1.5 text-right">
                        {nombre(l.valeurs[k] ?? 0, 2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <BoutonsExport
              route="/exports/gisements"
              requete={`site=${encodeURIComponent(site)}&methode=${methode}`}
            />
            <Bouton
              variante="secondaire"
              onClick={() => {
                setTout((t) => !t);
              }}
            >
              {tout ? "Voir les 20 premiers" : `Voir les ${nombre(d.classement.length)} premiers`}
            </Bouton>
            <p className="text-libelle text-muted">
              {nombre(d.exclus.total)} couples exclus :{" "}
              {Object.entries(d.exclus.motifs)
                .map(([m, n]) => `${m} (${nombre(n)})`)
                .join(", ")}
            </p>
          </div>
        </>
      ) : null}
    </div>
  );
}
