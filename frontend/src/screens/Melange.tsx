import { DropIcon, FireIcon, LeafIcon, PathIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import BoutonsExport from "../components/BoutonsExport";
import CarteFlottante from "../components/CarteFlottante";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import ParametresManquants from "../components/ParametresManquants";
import TuileKPI from "../components/TuileKPI";
import type { EntrepriseApi } from "../lib/api";
import type { MelangeApi } from "../lib/decision";
import { nombre } from "../lib/format";
import type { SitesLogistique } from "../lib/logistique";
import { useApi } from "../lib/useApi";
import { couleurs, marque } from "../theme/couleurs";

const SITE_PAR_DEFAUT = "AGP-MEKNES";
const CONTRAINTES = ["PAR-51", "PAR-52", "PAR-53"];
const NUANCES = [
  couleurs.green[900],
  couleurs.green[700],
  couleurs.green[500],
  marque.principal,
  couleurs.green[200],
];

/** Lien vers le champ d'une valeur à saisir. */
function lien(texte: string): string {
  const parametre = /(PAR-\d+)/.exec(texte)?.[1];
  if (!parametre) return texte.includes("Gisements") ? "/gisements" : "/donnees";
  return ["PAR-01", "PAR-21", "PAR-34", "PAR-37", ...CONTRAINTES].includes(parametre)
    ? `/parametres#${parametre}`
    : `/parametres#technique-${parametre}`;
}

/** Mélange (UC-MIX-01) : mélange de résidus de coût minimal pour un site et la capacité K. */
export default function Melange() {
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const sites = useApi<SitesLogistique>("/logistique/sites");
  const [site, setSite] = useState(SITE_PAR_DEFAUT);
  const melange = useApi<MelangeApi>(`/melange/${encodeURIComponent(site)}`);
  const m = melange.donnees;
  const nomSite = sites.donnees?.sites.find((s) => s.id_site === site)?.nom ?? site;
  const parResidu = new Map<string, number>();
  if (m && !m.bloque)
    for (const l of m.melange)
      parResidu.set(l.code_residu, (parResidu.get(l.code_residu) ?? 0) + l.part);
  const parts = [...parResidu.entries()].map(([code, part]) => ({ code, part }));

  const titre = !m
    ? "Mélange"
    : m.bloque
      ? `Le mélange de ${nomSite} attend ${nombre(m.a_saisir.length)} valeurs`
      : m.faisable
        ? `${nomSite} : ${nombre(m.capacite)} t MS/an à ${nombre(m.cout_moyen ?? 0)} DH/t MS en moyenne, avec ${nombre(parts.length)} résidus`
        : `Aucun mélange ne remplit ${nombre(m.capacite)} t MS/an à ${nomSite}`;

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-12 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={titre}
        phrase="Trouvez le mélange de résidus de coût minimal qui remplit la capacité visée en respectant les cendres, l'humidité et la part maximale d'un résidu."
      />
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
        <p className="text-libelle text-muted lg:text-right">
          Contraintes :{" "}
          {(entreprise.donnees?.parametres ?? [])
            .filter((p) => CONTRAINTES.includes(p.identifiant))
            .map((p) => (
              <span key={p.identifiant} className="mr-3">
                <Link to={`/parametres#${p.identifiant}`} className="underline">
                  {p.libelle}
                </Link>{" "}
                :{" "}
                {typeof p.valeur === "number" ? `${nombre(p.valeur)} ${p.unite}` : "non appliquée"}
              </span>
            ))}
        </p>
      </div>
      <ParametresManquants
        requis={["PAR-01", "PAR-34", "PAR-37"]}
        pour="pour dimensionner le mélange"
      />
      {melange.erreur ? <MessageErreur message={melange.erreur} /> : null}
      {m?.bloque ? (
        <CarteFlottante
          titre="Valeurs à saisir pour calculer le mélange"
          sousTitre="Le mélange part du bassin d'approvisionnement du site (écran Sites)"
        >
          <ul className="grid gap-2 text-secondaire text-ink">
            {m.a_saisir.map((t) => (
              <li key={t} className="flex gap-2">
                <WarningCircleIcon
                  size={16}
                  className="mt-0.5 shrink-0 text-ember"
                  aria-hidden="true"
                />
                <span>
                  {t} ·{" "}
                  <Link to={lien(t)} className="underline decoration-marque-principal decoration-2">
                    saisir
                  </Link>
                </span>
              </li>
            ))}
          </ul>
        </CarteFlottante>
      ) : null}
      {m && !m.bloque ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <TuileKPI
              icone={<PathIcon size={14} />}
              libelle="Coût livré moyen"
              valeur={m.cout_moyen === null ? "—" : `${nombre(m.cout_moyen)} DH/t MS`}
            />
            <TuileKPI
              icone={<FireIcon size={14} />}
              libelle="Cendres moyennes"
              valeur={m.cendres_moyennes === null ? "—" : `${nombre(m.cendres_moyennes, 1)} % MS`}
            />
            <TuileKPI
              icone={<DropIcon size={14} />}
              libelle="Humidité moyenne"
              valeur={m.humidite_moyenne === null ? "—" : `${nombre(m.humidite_moyenne, 1)} %`}
            />
            <TuileKPI
              icone={<LeafIcon size={14} />}
              libelle="Carbone retiré"
              valeur={m.bilan_moyen === null ? "—" : `${nombre(m.bilan_moyen, 2)} t CO₂e/t MS`}
            />
          </div>
          {!m.faisable ? (
            <CarteFlottante titre="Problème infaisable" sousTitre={m.message}>
              <p className="text-secondaire text-ink">
                Contraintes qui bloquent : {m.bloquantes.join(", ") || "aucune seule"}.
              </p>
            </CarteFlottante>
          ) : (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
              <CarteFlottante
                titre="Part de chaque résidu dans le mélange (% de K)"
                source="Programme linéaire de la section 11.2.4 (HiGHS), sur les gisements sous le prix plafond"
              >
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={parts}
                        dataKey="part"
                        nameKey="code"
                        innerRadius="58%"
                        outerRadius="90%"
                        isAnimationActive={false}
                        label={({ code, part }: { code: string; part: number }) =>
                          `${code} ${nombre(part * 100)} %`
                        }
                      >
                        {parts.map((p, i) => (
                          <Cell key={p.code} fill={NUANCES[i % NUANCES.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v: number) => `${nombre(v * 100, 1)} %`} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </CarteFlottante>
              <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
                <table
                  className="w-full text-secondaire"
                  aria-label="Mélange par résidu et par province"
                >
                  <thead>
                    <tr className="border-b border-line text-left text-libelle text-muted">
                      <th scope="col" className="px-2 py-2 font-medium">
                        Résidu · province
                      </th>
                      <th scope="col" className="px-2 py-2 text-right font-medium">
                        Tonnage (t MS/an)
                      </th>
                      <th scope="col" className="px-2 py-2 text-right font-medium">
                        Part (%)
                      </th>
                      <th scope="col" className="px-2 py-2 text-right font-medium">
                        Coût livré (DH/t MS)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.melange.map((l) => (
                      <tr
                        key={`${l.code_province}-${l.code_residu}`}
                        className="border-b border-line last:border-0"
                      >
                        <th scope="row" className="px-2 py-1.5 text-left font-normal">
                          {l.nom_residu} · {l.nom_province}
                        </th>
                        <td className="chiffres px-2 py-1.5 text-right">{nombre(l.tonnage)}</td>
                        <td className="chiffres px-2 py-1.5 text-right">
                          {nombre(l.part * 100, 1)}
                        </td>
                        <td className="chiffres px-2 py-1.5 text-right">{nombre(l.cout_livre)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {m.faisable ? (
            <BoutonsExport
              table={{
                titre: `Mélange · ${nomSite}`,
                colonnes: [
                  { cle: "nom_residu", libelle: "Résidu" },
                  { cle: "nom_province", libelle: "Province" },
                  { cle: "tonnage", libelle: "Tonnage", unite: "t MS/an" },
                  { cle: "part", libelle: "Part", unite: "fraction de K" },
                  { cle: "cout_livre", libelle: "Coût livré", unite: "DH/t MS" },
                  { cle: "cendres", libelle: "Cendres", unite: "% MS" },
                  { cle: "humidite", libelle: "Humidité", unite: "%" },
                ],
                lignes: m.melange,
                notes: m.non_appliquees.length
                  ? [`Contraintes non appliquées : ${m.non_appliquees.join(", ")}`]
                  : [],
              }}
            />
          ) : null}
          {m.non_appliquees.length || m.exclus.length ? (
            <p className="text-libelle text-muted">
              {m.non_appliquees.length
                ? `Contraintes non appliquées faute de valeur saisie : ${m.non_appliquees.join(", ")}. `
                : ""}
              {m.exclus.join(" ; ")}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
