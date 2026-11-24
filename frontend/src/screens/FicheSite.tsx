import {
  ChartBarIcon,
  LeafIcon,
  PathIcon,
  PrinterIcon,
  StackIcon,
  TrophyIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import { Link, useSearchParams } from "react-router";

import BandeauPartiel from "../components/BandeauPartiel";
import BarresSegmentees from "../components/BarresSegmentees";
import Bouton from "../components/Bouton";
import BoutonsExport from "../components/BoutonsExport";
import CarteFlottante from "../components/CarteFlottante";
import { Variation } from "../components/ClassementSites";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import ParametresManquants from "../components/ParametresManquants";
import TuileKPI from "../components/TuileKPI";
import type { BilansSite } from "../lib/acv";
import type { LigneClassement, MelangeApi } from "../lib/decision";
import { nombre } from "../lib/format";
import type { Courbe, Site, SitesLogistique } from "../lib/logistique";
import { useApi } from "../lib/useApi";
import { couleursAxes, type Axe } from "../theme/couleurs";

interface CritereFiche {
  code: string;
  libelle: string;
  axe: string;
  unite: string;
  sens: string;
  valeur: number | null;
  motif: string | null;
}

interface Fiche {
  site: Site;
  criteres: CritereFiche[];
  axes: Record<string, string>;
  classement?: LigneClassement | null;
  exclu?: { id_site: string; motif: string } | null;
  sites_classes?: number;
  scores_axes?: Record<string, number>;
  partiel?: { utilises: number; actifs: number; partiel: boolean };
  retires?: Record<string, string>;
  libelles_retires?: Record<string, string>;
  robustesse?: {
    proba_premier: number;
    proba_tete: number;
    rang_wsm: number;
    rang_topsis: number;
    robuste: boolean;
  } | null;
  a_renseigner?: string[];
  bassin: Omit<Courbe, "site" | "points"> & Record<string, unknown>;
  melange: MelangeApi;
  bilan: Pick<
    BilansSite,
    "bilan_site" | "motif_site" | "par_residu" | "unite_fonctionnelle" | "standard"
  >;
}

const SITE_PAR_DEFAUT = "AGP-MEKNES";

/** Fiche site (UC-RES-01) : rang, score, critères, bassin, mélange, bilan, robustesse. */
export default function FicheSite() {
  const [parametres, setParametres] = useSearchParams();
  const id = parametres.get("site") ?? SITE_PAR_DEFAUT;
  const sites = useApi<SitesLogistique>("/logistique/sites");
  const fiche = useApi<Fiche>(`/fiche/${encodeURIComponent(id)}`);
  const f = fiche.donnees;
  const rang = f?.classement?.rang;
  const titre = !f
    ? "Fiche site"
    : rang
      ? `${f.site.nom} est ${nombre(rang)}${rang === 1 ? "er" : "e"} sur ${nombre(f.sites_classes ?? 0)} sites`
      : f.exclu
        ? `${f.site.nom} est exclu du classement : ${f.exclu.motif}`
        : `${f.site.nom} n'est pas encore classé`;
  const bassin = f?.bassin;
  const m = f?.melange;
  const b = f?.bilan.bilan_site;

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-10 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={titre}
        phrase="Lisez sur une page le rang, le score, le bassin, le mélange, le bilan climat et la robustesse d'un site, prête à l'export."
      />
      <div className="flex flex-wrap items-end justify-between gap-4 print:hidden">
        <label className="grid gap-1 text-libelle text-muted">
          Site
          <select
            value={id}
            onChange={(e) => {
              setParametres({ site: e.target.value });
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
        <div className="flex flex-wrap gap-2">
          <Bouton
            variante="secondaire"
            icone={<PrinterIcon size={16} aria-hidden="true" />}
            onClick={() => {
              window.print();
            }}
          >
            Imprimer en PDF
          </Bouton>
          {f ? (
            <BoutonsExport
              table={{
                titre: `Fiche · ${f.site.nom}`,
                colonnes: [
                  { cle: "code", libelle: "Critère" },
                  { cle: "libelle", libelle: "Libellé" },
                  { cle: "valeur", libelle: "Valeur" },
                  { cle: "unite", libelle: "Unité" },
                  { cle: "motif", libelle: "Valeur à saisir" },
                ],
                lignes: f.criteres as unknown as Record<string, unknown>[],
                ...(f.partiel && f.retires && f.libelles_retires
                  ? {
                      partiel: {
                        utilises: f.partiel.utilises,
                        actifs: f.partiel.actifs,
                        retires: f.retires,
                        libelles: f.libelles_retires,
                      },
                    }
                  : {}),
                notes: [
                  `Rang : ${rang ? String(rang) : "non classé"} ; score : ${f.classement ? String(f.classement.score) : "—"}`,
                ],
              }}
            />
          ) : null}
        </div>
      </div>
      {fiche.erreur ? <MessageErreur message={fiche.erreur} /> : null}
      {f?.a_renseigner ? (
        <ParametresManquants requis={f.a_renseigner} pour="pour classer ce site" />
      ) : null}
      {f?.partiel && f.retires && f.libelles_retires ? (
        <BandeauPartiel
          utilises={f.partiel.utilises}
          actifs={f.partiel.actifs}
          retires={f.retires}
          libelles={f.libelles_retires}
          objet="rang de ce site"
        />
      ) : null}
      {f ? (
        <>
          <section
            aria-label="Synthèse"
            className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]"
          >
            <CarteFlottante
              titre={`${f.site.nom}${f.site.nom_province ? ` · province de ${f.site.nom_province}` : ""}`}
              sousTitre={`${f.site.type}${f.site.impose ? " · site imposé (H4)" : ""} · ${f.site.note}`}
            >
              <div className="grid grid-cols-2 gap-3">
                <TuileKPI
                  icone={<TrophyIcon size={14} />}
                  libelle="Rang"
                  valeur={rang ? `${nombre(rang)} / ${nombre(f.sites_classes ?? 0)}` : "—"}
                />
                <TuileKPI
                  icone={<ChartBarIcon size={14} />}
                  libelle={`Score (${f.classement ? "0 à 1" : "—"})`}
                  valeur={f.classement ? nombre(f.classement.score, 3, 3) : "—"}
                />
                <TuileKPI
                  icone={<ChartBarIcon size={14} />}
                  libelle="Probabilité d'être 1er"
                  valeur={f.robustesse ? `${nombre(f.robustesse.proba_premier * 100, 1)} %` : "—"}
                />
                <TuileKPI
                  icone={<ChartBarIcon size={14} />}
                  libelle="Variation de rang"
                  valeur={f.classement ? <Variation valeur={f.classement.variation} /> : "—"}
                />
              </div>
              {f.robustesse ? (
                <p className="mt-3 text-libelle text-muted">
                  Rang WSM {nombre(f.robustesse.rang_wsm)}, TOPSIS{" "}
                  {nombre(f.robustesse.rang_topsis)} ; dans les 3 premiers dans{" "}
                  {nombre(f.robustesse.proba_tete * 100, 1)} % des tirages ·{" "}
                  {f.robustesse.robuste ? "robuste (RG-12)" : "non robuste (RG-12)"}
                </p>
              ) : null}
            </CarteFlottante>
            <CarteFlottante titre="Score normalisé de chaque axe">
              <div className="grid gap-2">
                {Object.entries(f.scores_axes ?? {}).map(([axe, part]) => (
                  <BarresSegmentees
                    key={axe}
                    libelle={`${axe} · ${f.axes[axe] ?? axe}`}
                    part={part}
                    axe={(axe in couleursAxes ? axe : "A") as Axe}
                  />
                ))}
                {!Object.keys(f.scores_axes ?? {}).length ? (
                  <p className="text-secondaire text-muted">Aucun axe calculé pour ce site.</p>
                ) : null}
              </div>
            </CarteFlottante>
          </section>

          <section aria-labelledby="titre-criteres" className="grid gap-3">
            <h2 id="titre-criteres" className="text-titre-3">
              Valeur de chaque critère actif
            </h2>
            <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
              <table className="w-full text-secondaire" aria-label="Critères du site">
                <thead>
                  <tr className="border-b border-line text-left text-libelle text-muted">
                    <th scope="col" className="px-2 py-2 font-medium">
                      Critère
                    </th>
                    <th scope="col" className="px-2 py-2 text-right font-medium">
                      Valeur (unité du critère)
                    </th>
                    <th scope="col" className="px-2 py-2 font-medium">
                      Valeur à saisir
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {f.criteres.map((c) => (
                    <tr key={c.code} className="border-b border-line last:border-0">
                      <th scope="row" className="px-2 py-1.5 text-left font-normal">
                        <span
                          className="mr-2 inline-block h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: couleursAxes[c.axe as Axe] }}
                          aria-hidden="true"
                        />
                        {c.code} · {c.libelle}
                      </th>
                      <td className="chiffres px-2 py-1.5 text-right">
                        {c.valeur === null
                          ? "—"
                          : `${nombre(c.valeur, c.valeur < 10 ? 2 : 0)} ${c.unite}`}
                      </td>
                      <td className="px-2 py-1.5 text-libelle text-muted">{c.motif ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-label="Bassin, mélange et bilan" className="grid gap-4 lg:grid-cols-3">
            <CarteFlottante
              titre="Bassin d'approvisionnement"
              source="Écran Sites et logistique : courbe complète et carte du bassin"
            >
              {bassin && !bassin.bloque ? (
                <ul className="grid gap-1 text-secondaire">
                  <li className="flex items-center gap-2">
                    <StackIcon size={14} aria-hidden="true" />
                    {nombre(Number(bassin.tonnage_sous_plafond))} t MS/an sous le prix plafond
                  </li>
                  <li className="flex items-center gap-2">
                    <PathIcon size={14} aria-hidden="true" />
                    {bassin.cout_moyen_k === null
                      ? "capacité K non atteignable"
                      : `${nombre(Number(bassin.cout_moyen_k))} DH/t MS en moyenne pour K`}
                  </li>
                </ul>
              ) : (
                <Attente lignes={(bassin?.a_saisir as string[] | undefined) ?? []} lien="/sites" />
              )}
            </CarteFlottante>
            <CarteFlottante
              titre="Mélange de coût minimal"
              source="Écran Mélange : détail par résidu et province"
            >
              {m && !m.bloque ? (
                m.faisable ? (
                  <ul className="grid gap-1 text-secondaire">
                    {m.melange.slice(0, 5).map((l) => (
                      <li key={`${l.code_province}-${l.code_residu}`}>
                        {l.nom_residu} · {l.nom_province} : {nombre(l.part * 100)} %
                      </li>
                    ))}
                    <li className="text-muted">coût moyen {nombre(m.cout_moyen ?? 0)} DH/t MS</li>
                  </ul>
                ) : (
                  <p className="text-secondaire text-ink">{m.message}</p>
                )
              ) : (
                <Attente lignes={m?.bloque ? m.a_saisir : []} lien="/melange" />
              )}
            </CarteFlottante>
            <CarteFlottante
              titre="Bilan climat"
              source={`${f.bilan.unite_fonctionnelle} · standard ${f.bilan.standard} (RG-07)`}
            >
              {b ? (
                <ul className="grid gap-1 text-secondaire">
                  <li className="flex items-center gap-2">
                    <LeafIcon size={14} aria-hidden="true" />
                    {nombre(b.BN, 2, 2)} t CO₂e retirées par t de biochar
                  </li>
                  <li className="text-muted">
                    moyenne de {nombre(b.couples)} gisements du bassin, pondérée par le tonnage
                  </li>
                </ul>
              ) : (
                <p className="text-secondaire text-muted">
                  {f.bilan.motif_site ?? "Bilan non calculé"} ·{" "}
                  <Link to="/bilan-climat" className="underline">
                    écran Bilan climat
                  </Link>
                </p>
              )}
            </CarteFlottante>
          </section>
        </>
      ) : null}
    </div>
  );
}

function Attente({ lignes, lien }: { lignes: string[]; lien: string }) {
  return (
    <div className="grid gap-1 text-libelle text-ink">
      {lignes.slice(0, 4).map((l) => (
        <p key={l} className="flex gap-2">
          <WarningCircleIcon size={14} className="mt-0.5 shrink-0 text-ember" aria-hidden="true" />
          {l}
        </p>
      ))}
      <Link to={lien} className="text-secondaire underline">
        Voir le détail
      </Link>
    </div>
  );
}
