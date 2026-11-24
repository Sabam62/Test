import {
  CircleIcon,
  FlaskIcon,
  LeafIcon,
  StackIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import BoutonsExport from "../components/BoutonsExport";
import CarteFlottante from "../components/CarteFlottante";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import TuileKPI from "../components/TuileKPI";
import ValeurSourcee from "../components/ValeurSourcee";
import type { GeoJsonContours } from "../lib/api";
import { nombre } from "../lib/format";
import type {
  CarteGisements,
  IndicateursPotentiel,
  SyntheseGisements,
  TableauGisements,
} from "../lib/potentiel";
import { useApi } from "../lib/useApi";
import CarteSatellite from "../map/CarteSatellite";
import { classesGisement, couleurs } from "../theme/couleurs";

const TOUS = "tous";

function valeurAffichee(valeur: number | null | undefined, unite: string): string {
  if (valeur === null || valeur === undefined) return "à compléter";
  return `${nombre(valeur, unite === "fraction" ? 2 : 0)} ${unite}`;
}

/** Lien vers l'endroit où compléter une valeur bloquante (Paramètres ou Données). */
function lienBloquant(motif: string): { vers: string; libelle: string } {
  const parametre = /^(PAR-\d+)/.exec(motif)?.[1];
  if (parametre) return { vers: `/parametres#technique-${parametre}`, libelle: "Paramètres" };
  return { vers: "/donnees", libelle: "Données" };
}

/** Gisements (UC-POT-01 à 03) : carte choroplèthe, totaux, histogramme et tableau. */
export default function Gisements() {
  const filtres = useApi<IndicateursPotentiel>("/potentiel/indicateurs");
  const synthese = useApi<SyntheseGisements>("/potentiel/synthese");
  const contours = useApi<GeoJsonContours>("/referentiel/provinces/geojson");
  const [residu, setResidu] = useState("R01");
  const [indicateur, setIndicateur] = useState("T");
  const [selection, setSelection] = useState<string | null>(null);
  const carte = useApi<CarteGisements>(
    `/potentiel/carte?residu=${encodeURIComponent(residu)}&indicateur=${encodeURIComponent(indicateur)}`,
  );
  const tableau = useApi<TableauGisements>(
    `/potentiel/tableau?indicateur=${encodeURIComponent(indicateur)}`,
  );

  const definition = filtres.donnees?.indicateurs.find((i) => i.code === indicateur);
  const s = synthese.donnees;
  const totalT = s?.totaux.find((t) => t.indicateur === "T");
  const totalM = s?.totaux.find((t) => t.indicateur === "M");

  const remplissage = useMemo(
    () =>
      Object.fromEntries(
        (carte.donnees?.provinces ?? []).map((p) => [
          p.code_province,
          p.classe === null ? couleurs.paper : (classesGisement[p.classe] ?? couleurs.paper),
        ]),
      ),
    [carte.donnees],
  );
  const parCode = useMemo(
    () => new Map((carte.donnees?.provinces ?? []).map((p) => [p.code_province, p])),
    [carte.donnees],
  );
  const choisie = selection ? parCode.get(selection) : undefined;

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-16 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={
          s && totalT
            ? `${nombre(totalT.residus_calcules.length)} résidus sur ${nombre(s.residus)} ont un gisement théorique calculé : ${valeurAffichee(totalT.total, totalT.unite)}`
            : "Gisements"
        }
        phrase={
          totalM && totalM.total === null
            ? "Le gisement mobilisable attend le taux de collecte, la part prélevable et la part déjà utilisée de chaque résidu : la carte montre en attendant le gisement théorique, avec la provenance de chaque valeur."
            : "Repérez les provinces où les résidus agricoles mobilisables sont les plus abondants, en matière sèche, en carbone et en biochar."
        }
      />
      {synthese.erreur ? <MessageErreur message={synthese.erreur} /> : null}

      <section aria-label="Totaux nationaux" className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {(s?.totaux ?? []).map((t) => (
          <TuileKPI
            key={t.indicateur}
            icone={
              t.indicateur.startsWith("C") ? (
                <LeafIcon size={14} />
              ) : t.indicateur.startsWith("B") ? (
                <FlaskIcon size={14} />
              ) : (
                <StackIcon size={14} />
              )
            }
            libelle={`${t.libelle} (national)`}
            valeur={valeurAffichee(t.total, t.unite)}
          />
        ))}
      </section>

      <section aria-labelledby="titre-carte" className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 id="titre-carte" className="text-titre-3">
            {carte.donnees
              ? `${carte.donnees.libelle} : ${nombre(carte.donnees.provinces_avec_valeur)} provinces sur ${nombre(carte.donnees.provinces.length)} calculées`
              : "Carte des gisements"}
          </h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1 text-libelle text-muted">
              Résidu
              <select
                value={residu}
                onChange={(e) => {
                  setResidu(e.target.value);
                }}
                className="rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire text-ink"
              >
                <option value={TOUS} disabled={definition ? !definition.additif : false}>
                  Tous les résidus (somme)
                </option>
                {(filtres.donnees?.residus ?? []).map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.code} · {r.nom}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-libelle text-muted">
              Indicateur
              <select
                value={indicateur}
                onChange={(e) => {
                  const choisi = filtres.donnees?.indicateurs.find(
                    (i) => i.code === e.target.value,
                  );
                  if (residu === TOUS && choisi && !choisi.additif) setResidu("R01");
                  setIndicateur(e.target.value);
                }}
                className="rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire text-ink"
              >
                {(filtres.donnees?.indicateurs ?? []).map((i) => (
                  <option key={i.code} value={i.code}>
                    {i.libelle} ({i.unite})
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {carte.erreur ? <MessageErreur message={carte.erreur} /> : null}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <CarteFlottante
            titre={definition ? `${definition.libelle} (${definition.unite})` : "Carte"}
            source="Sources : production par province (SRC-18, SRC-03, SRC-01 réparti selon CROPGRIDS SRC-04), ratios des résidus (§14.2) · moyenne des 5 dernières campagnes disponibles · contours © Haut-Commissariat au Plan"
          >
            <CarteSatellite
              contours={contours.donnees}
              remplissage={remplissage}
              libelle={`Carte des gisements : ${definition?.libelle ?? ""} par province`}
              className="relative h-[560px] rounded-bouton"
              onSelection={setSelection}
              infoBulle={(code) => {
                const p = parCode.get(code);
                if (!p) return null;
                const valeur = valeurAffichee(p.valeur, carte.donnees?.unite ?? "");
                return p.valeur === null
                  ? `${p.nom_fr}\nsans valeur : ${p.motifs[0] ?? "donnée manquante"}`
                  : `${p.nom_fr}\n${valeur} · ${p.statut ?? ""}`;
              }}
            />
            <Legende carte={carte.donnees} />
          </CarteFlottante>
          <div className="grid content-start gap-4">
            <CarteFlottante
              titre={choisie ? choisie.nom_fr : "Province"}
              sousTitre={choisie ? undefined : "Cliquez une province sur la carte"}
            >
              {choisie ? (
                choisie.valeur === null ? (
                  <ul className="grid gap-1 text-secondaire text-ink">
                    {choisie.motifs.map((m) => (
                      <li key={m} className="flex gap-2">
                        <WarningCircleIcon
                          size={16}
                          className="mt-0.5 shrink-0 text-ember"
                          aria-hidden="true"
                        />
                        {m}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="grid gap-2 text-secondaire">
                    <ValeurSourcee
                      valeur={choisie.valeur}
                      unite={carte.donnees?.unite ?? ""}
                      decimales={carte.donnees?.unite === "fraction" ? 2 : 0}
                      provenance={{
                        source_id: choisie.sources.join(", "),
                        annee: choisie.campagnes.join(", "),
                        statut: choisie.statut,
                        previsionnel: choisie.previsionnel,
                        note: `Résidus calculés : ${choisie.residus_calcules.join(", ")}`,
                      }}
                    />
                    <p className="text-libelle text-muted">
                      Campagnes : {choisie.campagnes.join(", ")}
                      {choisie.previsionnel ? " (dont prévisionnelles)" : ""}
                    </p>
                    {choisie.motifs.length ? (
                      <p className="text-libelle text-muted">
                        Non compté : {choisie.motifs.join(" ; ")}
                      </p>
                    ) : null}
                  </div>
                )
              ) : null}
            </CarteFlottante>
            <Bloquants synthese={s} />
          </div>
        </div>
      </section>

      <Histogramme synthese={s} indicateur="T" residus={filtres.donnees?.residus ?? []} />

      <section aria-labelledby="titre-tableau" className="grid gap-4">
        <h2 id="titre-tableau" className="text-titre-3">
          {tableau.donnees
            ? `${tableau.donnees.libelle} par province et par résidu (${tableau.donnees.unite})`
            : "Tableau des gisements"}
        </h2>
        {tableau.donnees ? (
          <>
            <BoutonsExport
              table={{
                titre: `${tableau.donnees.libelle} par province et résidu`,
                colonnes: [
                  { cle: "nom_fr", libelle: "Province" },
                  ...tableau.donnees.residus.map((r) => ({
                    cle: r.code,
                    libelle: `${r.code} · ${r.nom}`,
                    unite: tableau.donnees?.unite ?? "",
                  })),
                ],
                lignes: tableau.donnees.lignes.map((l) => ({
                  nom_fr: l.nom_fr,
                  ...Object.fromEntries(
                    Object.entries(l.cellules).map(([code, c]) => [code, c.valeur]),
                  ),
                })),
                notes: ["Cellule vide : valeur non calculée (motif dans l'outil, RG-06)"],
              }}
            />
            <Tableau tableau={tableau.donnees} />
          </>
        ) : null}
      </section>
    </div>
  );
}

function Legende({ carte }: { carte: CarteGisements | null }) {
  if (!carte) return null;
  const bornes = carte.bornes;
  return (
    <ul
      className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-libelle text-ink"
      aria-label="Légende"
    >
      {bornes.slice(0, -1).map((bas, i) => (
        <li key={bas} className="flex items-center gap-1.5">
          <span
            className="h-3 w-3 rounded-segment"
            style={{ backgroundColor: classesGisement[i] ?? couleurs.paper }}
          />
          <span className="chiffres">
            {nombre(bas)} à {nombre(bornes[i + 1] ?? bas)}
          </span>
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-segment border border-line bg-paper" />
        sans valeur (motif au survol)
      </li>
      <li className="text-muted">{carte.unite}</li>
    </ul>
  );
}

function Bloquants({ synthese }: { synthese: SyntheseGisements | null }) {
  if (!synthese?.bloquants.length) return null;
  return (
    <CarteFlottante
      titre="Valeurs qui bloquent les calculs"
      sousTitre="Chaque couple bloqué est exclu, jamais compté zéro (RG-06)"
    >
      <ul className="grid max-h-[300px] gap-2 overflow-y-auto text-libelle text-ink">
        {synthese.bloquants.slice(0, 8).map((b) => {
          const lien = lienBloquant(b.motif);
          return (
            <li key={b.motif} className="border-b border-line pb-2 last:border-0">
              <p className="flex gap-2">
                <CircleIcon
                  size={8}
                  weight="fill"
                  className="mt-1 shrink-0 text-ember"
                  aria-hidden="true"
                />
                <span>{b.motif}</span>
              </p>
              <p className="mt-0.5 text-muted">
                {b.residus.join(", ")} ·{" "}
                <Link to={lien.vers} className="underline decoration-marque-principal decoration-2">
                  compléter dans {lien.libelle}
                </Link>
              </p>
            </li>
          );
        })}
      </ul>
    </CarteFlottante>
  );
}

function Histogramme({
  synthese,
  indicateur,
  residus,
}: {
  synthese: SyntheseGisements | null;
  indicateur: string;
  residus: { code: string; nom: string }[];
}) {
  const barres = (synthese?.par_residu ?? []).filter(
    (r) => r.indicateur === indicateur && r.total !== null,
  );
  if (!barres.length) return null;
  const plus = Math.max(...barres.map((b) => b.total ?? 0));
  const nuances = [
    couleurs.green[900],
    couleurs.green[700],
    couleurs.green[500],
    couleurs.green[200],
  ];
  return (
    <section aria-labelledby="titre-histogramme" className="grid gap-4">
      <h2 id="titre-histogramme" className="text-titre-3">
        Gisement théorique national par résidu ({barres[0]?.unite})
      </h2>
      <div className="flex h-72 items-end gap-4 rounded-carte border border-line bg-card p-6">
        {barres.map((b, i) => (
          <figure
            key={b.code_residu}
            className="flex h-full flex-1 flex-col items-center justify-end gap-2"
          >
            <div
              className="relative w-full rounded-barre"
              style={{
                height: `${String(Math.max(2, ((b.total ?? 0) / plus) * 100))}%`,
                backgroundColor: nuances[Math.min(i, nuances.length - 1)],
              }}
            >
              <span className="chiffres absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-card px-2 py-0.5 text-source text-ink shadow-douce">
                {nombre(b.total ?? 0)}
              </span>
            </div>
            <figcaption className="text-center text-libelle text-muted">
              {b.code_residu} · {residus.find((r) => r.code === b.code_residu)?.nom ?? ""}
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function Tableau({ tableau }: { tableau: TableauGisements }) {
  return (
    <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
      <table
        className="w-full text-secondaire"
        aria-label={`${tableau.libelle} par province et par résidu`}
      >
        <thead>
          <tr className="border-b border-line text-left text-libelle text-muted">
            <th scope="col" className="sticky left-0 bg-card px-2 py-2 font-medium">
              Province
            </th>
            {tableau.residus.map((r) => (
              <th
                key={r.code}
                scope="col"
                className="whitespace-nowrap px-2 py-2 text-right font-medium"
                title={r.nom}
              >
                {r.code} ({tableau.unite})
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableau.lignes.map((ligne) => (
            <tr key={ligne.code_province} className="border-b border-line last:border-0">
              <th
                scope="row"
                className="sticky left-0 whitespace-nowrap bg-card px-2 py-1.5 text-left font-normal"
              >
                {ligne.nom_fr}
              </th>
              {tableau.residus.map((r) => {
                const cellule = ligne.cellules[r.code];
                return (
                  <td key={r.code} className="whitespace-nowrap px-2 py-1.5 text-right">
                    {cellule && cellule.valeur !== null ? (
                      <ValeurSourcee
                        valeur={cellule.valeur}
                        decimales={tableau.unite === "fraction" ? 2 : 0}
                        provenance={{
                          source_id: cellule.sources ?? null,
                          annee: cellule.annee ?? null,
                          statut: cellule.statut ?? null,
                          previsionnel: cellule.previsionnel ?? false,
                          note: cellule.note ?? null,
                        }}
                      />
                    ) : (
                      <span className="text-muted" title={cellule?.motif ?? ""}>
                        —
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
