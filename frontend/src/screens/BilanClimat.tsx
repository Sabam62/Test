import { CloudIcon, LeafIcon, RecycleIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import BoutonsExport from "../components/BoutonsExport";
import CarteFlottante from "../components/CarteFlottante";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import ParametresManquants from "../components/ParametresManquants";
import TuileKPI from "../components/TuileKPI";
import type { BilansSite, Terme } from "../lib/acv";
import { nombre } from "../lib/format";
import type { SitesLogistique } from "../lib/logistique";
import { useApi } from "../lib/useApi";
import { couleurs, couleursAxes } from "../theme/couleurs";

const UNITE = "t CO₂e/t biochar";
const SITE_PAR_DEFAUT = "AGP-MEKNES";
/** Couleur de chaque terme du bilan : stock et émissions évitées en vert, étapes en couleurs d'axes. */
const COULEURS: Record<Terme, string> = {
  stock: couleurs.green[700],
  E_ref: couleurs.green[500],
  E_col: couleursAxes.B,
  E_pre: couleursAxes.F,
  E_tr: couleursAxes.C,
  E_pyr: couleurs.ember,
  E_ep: couleursAxes.E,
  BN: couleurs.ink,
};

/** Lien vers l'endroit où saisir une valeur bloquante. */
function lienSaisie(motif: string): { vers: string; libelle: string } {
  const parametre = /(PAR-\d+)/.exec(motif)?.[1];
  if (parametre === "PAR-21") return { vers: "/parametres#PAR-21", libelle: "Paramètres" };
  if (parametre) return { vers: `/parametres#technique-${parametre}`, libelle: "Paramètres" };
  return { vers: "/donnees", libelle: "Données" };
}

function signe(v: number | null | undefined, decimales = 2): string {
  return v === null || v === undefined ? "—" : `${nombre(v, decimales, decimales)} ${UNITE}`;
}

/** Bilan climat (UC-ACV-01 à 03) : bilan net par résidu et par site, contributions par étape. */
export default function BilanClimat() {
  const sites = useApi<SitesLogistique>("/logistique/sites");
  const [site, setSite] = useState(SITE_PAR_DEFAUT);
  const bilans = useApi<BilansSite>(`/acv/sites/${encodeURIComponent(site)}`);
  const b = bilans.donnees;
  const nomSite = sites.donnees?.sites.find((s) => s.id_site === site)?.nom ?? site;
  const meilleurs = (b?.par_residu ?? [])
    .filter((r) => r.BN_median !== null)
    .sort((x, y) => (y.BN_median ?? 0) - (x.BN_median ?? 0));
  const premier = meilleurs[0];

  const titre = !b
    ? "Bilan climat"
    : premier && premier.BN_median !== null
      ? `${premier.nom} : ${nombre(premier.BN_median, 2, 2)} t CO₂e retirées par t de biochar livré à ${nomSite} (médiane)`
      : `Le bilan climat des ${nombre(b.couples)} chaînes vers ${nomSite} attend ${nombre(b.a_saisir.length)} valeurs`;

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-16 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={titre}
        phrase="Mesurez le carbone retiré par tonne de biochar pour chaque chaîne résidu × site, et ce que coûte chaque étape en émissions."
      />
      {bilans.erreur ? <MessageErreur message={bilans.erreur} /> : null}

      <section aria-label="Conventions du bilan" className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <label className="grid gap-1 text-libelle text-muted">
            Site
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
          {b ? (
            <p className="text-libelle text-muted lg:text-right">
              Unité fonctionnelle : {b.unite_fonctionnelle} · standard : {b.standard} · permanence à
              100 ans :{" "}
              {b.permanence !== null
                ? `${nombre(b.permanence, 2, 2)} (classe ${b.classe_temperature ?? "—"}, GIEC 2019)`
                : "à renseigner"}{" "}
              · méthode : {b.methode.slice(1).join(", ")} (RG-07)
            </p>
          ) : null}
        </div>
        <ParametresManquants
          requis={["PAR-21"]}
          pour="pour choisir la permanence du carbone stocké (classe de température du GIEC)"
        />
      </section>

      <SectionSite b={b} nomSite={nomSite} />

      <section aria-labelledby="titre-residus" className="grid gap-4">
        <h2 id="titre-residus" className="text-titre-3">
          Bilan net par résidu vers {nomSite} ({UNITE})
        </h2>
        <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
          <table className="w-full text-secondaire" aria-label="Bilan net par résidu">
            <thead>
              <tr className="border-b border-line text-left text-libelle text-muted">
                <th scope="col" className="px-2 py-2 font-medium">
                  Résidu
                </th>
                <th scope="col" className="px-2 py-2 font-medium">
                  Scénario de référence
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  Chaînes calculées (nombre)
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  Bilan médian ({UNITE})
                </th>
                <th scope="col" className="px-2 py-2 text-right font-medium">
                  Étendue ({UNITE})
                </th>
              </tr>
            </thead>
            <tbody>
              {(b?.par_residu ?? []).map((r) => (
                <tr key={r.code_residu} className="border-b border-line last:border-0">
                  <th scope="row" className="px-2 py-1.5 text-left font-normal">
                    {r.code_residu} · {r.nom}
                  </th>
                  <td className="px-2 py-1.5">{r.scenario ?? "à compléter"}</td>
                  <td className="chiffres px-2 py-1.5 text-right">
                    {nombre(r.couples_calcules)} / {nombre(r.couples)}
                  </td>
                  <td className="chiffres px-2 py-1.5 text-right">
                    {r.BN_median === null ? (
                      <span className="text-muted" title={r.motif ?? ""}>
                        —
                      </span>
                    ) : (
                      nombre(r.BN_median, 2, 2)
                    )}
                  </td>
                  <td className="chiffres px-2 py-1.5 text-right">
                    {r.BN_min === null || r.BN_max === null
                      ? "—"
                      : `${nombre(r.BN_min, 2, 2)} à ${nombre(r.BN_max, 2, 2)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {b ? (
          <BoutonsExport
            table={{
              titre: `Bilan net par résidu · ${nomSite}`,
              colonnes: [
                { cle: "code_residu", libelle: "Résidu" },
                { cle: "nom", libelle: "Nom" },
                { cle: "scenario", libelle: "Scénario de référence" },
                { cle: "couples_calcules", libelle: "Chaînes calculées", unite: "nombre" },
                { cle: "couples", libelle: "Chaînes", unite: "nombre" },
                { cle: "BN_median", libelle: "Bilan médian", unite: UNITE },
                { cle: "BN_min", libelle: "Bilan minimal", unite: UNITE },
                { cle: "BN_max", libelle: "Bilan maximal", unite: UNITE },
                { cle: "motif", libelle: "Valeur à saisir" },
              ],
              lignes: b.par_residu as unknown as Record<string, unknown>[],
              notes: [
                `Unité fonctionnelle : ${b.unite_fonctionnelle} ; standard : ${b.standard} (RG-07)`,
              ],
            }}
          />
        ) : null}
        <p className="text-source text-muted">
          Sources : facteurs d'émission (facteurs_emission.csv, SRC-15), rendement et carbone du
          biochar (residus.csv, SRC-16), distances OSRM (SRC-07), PRG100 du GIEC AR6 (PAR-27) ·
          calcul Brightway 2.5, projet « {b?.projet ?? "atlantic_biochar"} », lisible dans Activity
          Browser
        </p>
      </section>

      {b?.a_saisir.length ? (
        <CarteFlottante
          titre={`${nombre(b.a_saisir.length)} valeurs à saisir pour calculer les bilans`}
          sousTitre="Une chaîne dont une valeur manque n'est pas calculée, jamais comptée zéro (RG-06, RG-14)"
        >
          <ul className="grid gap-2 text-secondaire text-ink">
            {b.a_saisir.slice(0, 14).map((m) => {
              const lien = lienSaisie(m.motif);
              return (
                <li key={m.motif} className="flex gap-2 border-b border-line pb-2 last:border-0">
                  <WarningCircleIcon
                    size={16}
                    className="mt-0.5 shrink-0 text-ember"
                    aria-hidden="true"
                  />
                  <span>
                    {m.motif} · {nombre(m.couples)} chaînes ·{" "}
                    <Link
                      to={lien.vers}
                      className="underline decoration-marque-principal decoration-2"
                    >
                      saisir dans {lien.libelle}
                    </Link>
                  </span>
                </li>
              );
            })}
          </ul>
        </CarteFlottante>
      ) : null}
    </div>
  );
}

function SectionSite({ b, nomSite }: { b: BilansSite | null; nomSite: string }) {
  if (!b) return null;
  const s = b.bilan_site;
  const reference = b.bilans[0];
  const source = s ?? reference;
  const donnees = source
    ? (["stock", "E_ref", "E_col", "E_pre", "E_tr", "E_pyr", "E_ep"] as Terme[]).map((t) => ({
        terme: t,
        libelle:
          t === "stock"
            ? "Carbone stocké à 100 ans"
            : t === "E_ref"
              ? "Émissions évitées (référence)"
              : (b.etapes[t] ?? t),
        valeur: t === "stock" || t === "E_ref" ? source[t] : -source[t],
      }))
    : [];
  return (
    <section aria-labelledby="titre-site" className="grid gap-6">
      <h2 id="titre-site" className="text-titre-3">
        {s
          ? `Bilan de ${nomSite}, moyenne pondérée de ${nombre(s.couples)} gisements du bassin`
          : reference
            ? `Contributions de la meilleure chaîne : ${reference.nom_residu} de ${reference.nom_province} vers ${nomSite}`
            : `Bilan de ${nomSite}`}
      </h2>
      {!s && b.motif_site ? (
        <p className="text-secondaire text-muted">
          Bilan du site non calculé : {b.motif_site.split(" ; ")[0]}.
        </p>
      ) : null}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <TuileKPI icone={<LeafIcon size={14} />} libelle="Bilan net" valeur={signe(source?.BN)} />
        <TuileKPI
          icone={<LeafIcon size={14} />}
          libelle="Carbone stocké"
          valeur={signe(source?.stock)}
        />
        <TuileKPI
          icone={<CloudIcon size={14} />}
          libelle="Émissions de la chaîne"
          valeur={signe(
            source ? source.E_col + source.E_pre + source.E_tr + source.E_pyr + source.E_ep : null,
          )}
        />
        <TuileKPI
          icone={<RecycleIcon size={14} />}
          libelle="Émissions évitées"
          valeur={signe(source?.E_ref)}
        />
      </div>
      {donnees.length ? (
        <CarteFlottante
          titre={`Contributions au bilan net (${UNITE})`}
          sousTitre="Positif : carbone retiré ou émissions évitées ; négatif : émissions de chaque étape"
          source="Calcul Brightway (méthode PRG100 AR6) · unité fonctionnelle : 1 t de biochar produite et épandue · standard neutre"
        >
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={donnees} layout="vertical" margin={{ left: 24, right: 24 }}>
                <CartesianGrid stroke={couleurs.line} horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={(v: number) => nombre(v, 2)}
                  stroke={couleurs.muted}
                  fontSize={12}
                />
                <YAxis
                  type="category"
                  dataKey="libelle"
                  width={210}
                  stroke={couleurs.muted}
                  fontSize={12}
                />
                <Tooltip formatter={(v: number) => [`${nombre(v, 3)} ${UNITE}`, "Contribution"]} />
                <ReferenceLine x={0} stroke={couleurs.ink} />
                <Bar dataKey="valeur" radius={6} isAnimationActive={false}>
                  {donnees.map((d) => (
                    <Cell key={d.terme} fill={COULEURS[d.terme]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CarteFlottante>
      ) : (
        <p className="text-secondaire text-muted">
          Aucune chaîne n'a encore de bilan : les valeurs à saisir sont listées en bas de page.
        </p>
      )}
    </section>
  );
}
