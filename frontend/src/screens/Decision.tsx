import * as Tabs from "@radix-ui/react-tabs";
import { ArrowCounterClockwiseIcon, ChartBarIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import BandeauPartiel from "../components/BandeauPartiel";
import BoutonsExport from "../components/BoutonsExport";
import Bouton from "../components/Bouton";
import CarteFlottante from "../components/CarteFlottante";
import CarteClassement from "../components/CarteClassement";
import ClassementGisements from "../components/ClassementGisements";
import ClassementSites from "../components/ClassementSites";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import ParametresManquants from "../components/ParametresManquants";
import { api, ErreurApi, json, type EntrepriseApi } from "../lib/api";
import type { AhpApi, ClassementApi, CriteresApi, RobustesseApi, SeuilApi } from "../lib/decision";
import { nombre } from "../lib/format";
import { useApi } from "../lib/useApi";
import { couleursAxes, type Axe } from "../theme/couleurs";

const SAATY = [1 / 9, 1 / 7, 1 / 5, 1 / 3, 1, 3, 5, 7, 9];
const LIBELLE_SAATY = ["1/9", "1/7", "1/5", "1/3", "1", "3", "5", "7", "9"];
const STYLE_ONGLET =
  "rounded-bouton px-3 py-1.5 text-secondaire text-muted data-[state=active]:bg-card data-[state=active]:text-ink data-[state=active]:shadow-douce";

function messageErreur(e: unknown, defaut: string): string {
  return e instanceof ErreurApi ? e.message : defaut;
}

/** Décision (UC-DEC-01, 02, 04, 06) : critères, poids et classement des sites. */
export default function Decision() {
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const criteres = useApi<CriteresApi>("/decision/criteres");
  const [methode, setMethode] = useState<string | null>(null);
  const classement = useApi<ClassementApi>(
    `/decision/classement${methode ? `?methode=${methode}` : ""}`,
  );
  const c = classement.donnees;
  const premier = c && !c.bloque ? c.classement[0] : undefined;
  const titre =
    c && !c.bloque && premier
      ? `${premier.nom} est 1er sur ${nombre(c.classement.length)} sites classés, sur ${nombre(c.criteres.length)} critères calculables`
      : c?.bloque
        ? `Le classement attend ${nombre(c.a_renseigner.length)} paramètres obligatoires de l'entreprise`
        : "Décision";

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-12 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={titre}
        phrase="Classez les sites candidats selon vos critères et vos poids, puis vérifiez que le premier reste premier quand les poids varient."
      />
      <ParametresManquants
        requis={entreprise.donnees?.obligatoires ?? []}
        pour="pour classer les sites"
      />
      {criteres.erreur ? <MessageErreur message={criteres.erreur} /> : null}
      <Tabs.Root defaultValue="classement" className="grid gap-6">
        <Tabs.List
          aria-label="Étapes de la décision"
          className="flex w-fit gap-1 rounded-carte bg-paper p-1 ring-1 ring-line"
        >
          <Tabs.Trigger value="criteres" className={STYLE_ONGLET}>
            Critères
          </Tabs.Trigger>
          <Tabs.Trigger value="poids" className={STYLE_ONGLET}>
            Poids
          </Tabs.Trigger>
          <Tabs.Trigger value="classement" className={STYLE_ONGLET}>
            Classement des sites
          </Tabs.Trigger>
          <Tabs.Trigger value="gisements" className={STYLE_ONGLET}>
            Classement des gisements
          </Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="criteres">
          {criteres.donnees ? <OngletCriteres donnees={criteres.donnees} /> : null}
        </Tabs.Content>
        <Tabs.Content value="poids">
          {criteres.donnees ? <OngletPoids donnees={criteres.donnees} /> : null}
        </Tabs.Content>
        <Tabs.Content value="classement">
          <OngletClassement
            classement={c}
            erreur={classement.erreur}
            methodes={criteres.donnees?.methodes ?? {}}
            methode={methode ?? (c && !c.bloque ? c.methode : "somme_ponderee")}
            onMethode={setMethode}
          />
        </Tabs.Content>
        <Tabs.Content value="gisements">
          <ClassementGisements
            methode={methode ?? (c && !c.bloque ? c.methode : "somme_ponderee")}
          />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function OngletCriteres({ donnees }: { donnees: CriteresApi }) {
  const [actifs, setActifs] = useState<string[]>(donnees.actifs);
  const [seuils, setSeuils] = useState<Record<string, SeuilApi>>(donnees.seuils);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    setActifs(donnees.actifs);
    setSeuils(donnees.seuils);
  }, [donnees]);
  const site = donnees.criteres.filter((c) => c.priorite === "P1" && c.niveaux.includes("S"));
  const motif = (code: string) => donnees.sites.find((s) => s.motifs[code])?.motifs[code];

  async function enregistrer() {
    try {
      await api(
        "/decision/reglages",
        json("PUT", { actifs, poids: donnees.poids, seuils, methode: donnees.methode }),
      );
      setMessage("Critères et seuils enregistrés ; le classement est recalculé.");
    } catch (e) {
      setMessage(messageErreur(e, "L'enregistrement a échoué."));
    }
  }

  function seuil(code: string, borne: keyof SeuilApi, texte: string) {
    const valeur = texte.trim() === "" ? null : Number(texte.replace(",", "."));
    setSeuils((s) => ({
      ...s,
      [code]: { minimum: null, maximum: null, ...s[code], [borne]: valeur },
    }));
  }

  return (
    <div className="grid gap-4">
      <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
        <table className="w-full text-secondaire" aria-label="Critères de décision des sites">
          <thead>
            <tr className="border-b border-line text-left text-libelle text-muted">
              <th scope="col" className="px-2 py-2 font-medium">
                Actif
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Critère
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Sens
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Seuil minimal (unité du critère)
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Seuil maximal (unité du critère)
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                Calcul
              </th>
            </tr>
          </thead>
          <tbody>
            {site.map((c) => (
              <tr key={c.code} className="border-b border-line last:border-0">
                <td className="px-2 py-1.5">
                  <input
                    type="checkbox"
                    aria-label={`Activer ${c.code}`}
                    checked={actifs.includes(c.code)}
                    onChange={(e) => {
                      setActifs((a) =>
                        e.target.checked ? [...a, c.code] : a.filter((x) => x !== c.code),
                      );
                    }}
                  />
                </td>
                <th scope="row" className="px-2 py-1.5 text-left font-normal">
                  <span
                    className="mr-2 inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: couleursAxes[c.axe as Axe] }}
                    aria-hidden="true"
                  />
                  {c.code} · {c.libelle} ({c.unite})
                </th>
                <td className="px-2 py-1.5 text-muted">
                  {c.sens === "hausse"
                    ? "↑ plus élevé"
                    : c.sens === "baisse"
                      ? "↓ plus bas"
                      : "filtre"}
                </td>
                {(["minimum", "maximum"] as const).map((borne) => (
                  <td key={borne} className="px-2 py-1.5">
                    {c.sens === "filtre" ? null : (
                      <input
                        inputMode="decimal"
                        aria-label={`Seuil ${borne === "minimum" ? "minimal" : "maximal"} ${c.code}`}
                        value={seuils[c.code]?.[borne] ?? ""}
                        onChange={(e) => {
                          seuil(c.code, borne, e.target.value);
                        }}
                        className="chiffres w-24 rounded-bouton border border-line px-2 py-1"
                      />
                    )}
                  </td>
                ))}
                <td className="px-2 py-1.5 text-libelle">
                  {c.calculable ? (
                    <span className="text-marque-fonce">calculé</span>
                  ) : (
                    <span className="text-muted" title={motif(c.code) ?? ""}>
                      à compléter : {(motif(c.code) ?? "valeur manquante").slice(0, 90)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Bouton onClick={() => void enregistrer()}>Enregistrer les critères</Bouton>
        <Bouton
          variante="secondaire"
          icone={<ArrowCounterClockwiseIcon size={16} aria-hidden="true" />}
          onClick={() => {
            api("/decision/reglages", json("DELETE"))
              .then(() => {
                setMessage("Critères et poids remis aux valeurs par défaut (section 9, PAR-45).");
              })
              .catch((e: unknown) => {
                setMessage(messageErreur(e, "La remise à zéro a échoué."));
              });
          }}
        >
          Critères par défaut
        </Bouton>
        {message ? (
          <p role="status" className="text-secondaire text-muted">
            {message}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function OngletPoids({ donnees }: { donnees: CriteresApi }) {
  const actifs = donnees.criteres.filter(
    (c) => donnees.actifs.includes(c.code) && c.sens !== "filtre",
  );
  const [curseurs, setCurseurs] = useState<Record<string, number>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [ahp, setAhp] = useState<AhpApi | null>(null);
  const axes = [...new Set(actifs.map((c) => c.axe))].sort();
  const [comparaisons, setComparaisons] = useState<Record<string, number>>({});
  useEffect(() => {
    const total = Object.values(donnees.poids).reduce((a, b) => a + b, 0);
    setCurseurs(
      Object.fromEntries(
        actifs.map((c) => [
          c.code,
          total ? Math.round(((donnees.poids[c.code] ?? 0) / total) * 100) : 0,
        ]),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [donnees]);

  async function enregistrer(poids: Record<string, number>) {
    try {
      await api(
        "/decision/reglages",
        json("PUT", {
          actifs: donnees.actifs,
          poids,
          seuils: donnees.seuils,
          methode: donnees.methode,
        }),
      );
      setMessage("Poids enregistrés ; le classement est recalculé.");
    } catch (e) {
      setMessage(messageErreur(e, "L'enregistrement a échoué."));
    }
  }

  async function calculerAhp() {
    const matrice = axes.map((a, i) =>
      axes.map((b, j) => {
        if (i === j) return 1;
        const cle = i < j ? `${a}-${b}` : `${b}-${a}`;
        const v = comparaisons[cle] ?? 1;
        return i < j ? v : 1 / v;
      }),
    );
    const parAxe = Object.fromEntries(
      axes.map((axe) => {
        const codes = actifs.filter((c) => c.axe === axe).map((c) => c.code);
        return [
          axe,
          { codes, matrice: codes.map((_, i) => codes.map((__, j) => (i === j ? 1 : 1))) },
        ];
      }),
    );
    try {
      setAhp(
        await api<AhpApi>(
          "/decision/ahp",
          json("POST", { axes: { codes: axes, matrice }, criteres: parAxe }),
        ),
      );
    } catch (e) {
      setMessage(messageErreur(e, "Le calcul AHP a échoué."));
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <CarteFlottante
        titre="Poids directs"
        sousTitre={
          donnees.personnalises
            ? "Poids choisis ; ramenés à 100 % au calcul"
            : "Poids par défaut (PAR-45) : égaux entre axes, puis entre critères d'un axe"
        }
      >
        <ul className="grid gap-3">
          {actifs.map((c) => (
            <li
              key={c.code}
              className="grid grid-cols-[minmax(0,1fr)_160px_48px] items-center gap-3"
            >
              <label htmlFor={`poids-${c.code}`} className="text-secondaire">
                {c.code} · {c.libelle}
              </label>
              <input
                id={`poids-${c.code}`}
                type="range"
                min={0}
                max={100}
                value={curseurs[c.code] ?? 0}
                onChange={(e) => {
                  setCurseurs((s) => ({ ...s, [c.code]: Number(e.target.value) }));
                }}
              />
              <span className="chiffres text-right text-secondaire">
                {nombre(curseurs[c.code] ?? 0)}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap gap-3">
          <Bouton onClick={() => void enregistrer(curseurs)}>Enregistrer les poids</Bouton>
          <Bouton variante="secondaire" onClick={() => void enregistrer({})}>
            Poids par défaut
          </Bouton>
        </div>
      </CarteFlottante>
      <CarteFlottante
        titre="Pondération AHP des axes"
        sousTitre="Comparez les axes deux à deux sur l'échelle de Saaty (1 : égal, 9 : extrêmement plus important)"
      >
        <ul className="grid gap-2">
          {axes.flatMap((a, i) =>
            axes.slice(i + 1).map((b) => {
              const cle = `${a}-${b}`;
              return (
                <li key={cle} className="flex items-center justify-between gap-3 text-secondaire">
                  <span>
                    {a} {donnees.axes[a]} par rapport à {b} {donnees.axes[b]}
                  </span>
                  <select
                    aria-label={`Comparaison ${a} et ${b}`}
                    value={comparaisons[cle] ?? 1}
                    onChange={(e) => {
                      setComparaisons((s) => ({ ...s, [cle]: Number(e.target.value) }));
                    }}
                    className="rounded-bouton border border-line bg-card px-2 py-1"
                  >
                    {SAATY.map((v, k) => (
                      <option key={v} value={v}>
                        {LIBELLE_SAATY[k]}
                      </option>
                    ))}
                  </select>
                </li>
              );
            }),
          )}
        </ul>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Bouton variante="secondaire" onClick={() => void calculerAhp()}>
            Calculer les poids AHP
          </Bouton>
          {ahp ? (
            <Bouton
              onClick={() =>
                void enregistrer(
                  Object.fromEntries(Object.entries(ahp.poids).map(([k, v]) => [k, v * 100])),
                )
              }
            >
              Appliquer les poids AHP
            </Bouton>
          ) : null}
        </div>
        {ahp ? (
          <div className="mt-3 grid gap-1 text-secondaire">
            <p>
              Ratio de cohérence des axes :{" "}
              <span className="chiffres">
                {ahp.matrices.axes?.cr === null || ahp.matrices.axes === undefined
                  ? "sans objet (2 axes ou moins)"
                  : nombre(ahp.matrices.axes.cr, 3, 3)}
              </span>{" "}
              (maximum {nombre(ahp.cr_maximal, 2, 2)}, PAR-44)
            </p>
            {ahp.avertissements.map((a) => (
              <p key={a} className="flex gap-2 text-ink">
                <WarningCircleIcon
                  size={16}
                  className="mt-0.5 shrink-0 text-ember"
                  aria-hidden="true"
                />
                {a}
              </p>
            ))}
            <p className="text-libelle text-muted">
              Les critères d'un même axe reçoivent des poids égaux ; poids final = poids de l'axe ×
              poids du critère dans l'axe (section 10.2).
            </p>
          </div>
        ) : null}
      </CarteFlottante>
      {message ? (
        <p role="status" className="text-secondaire text-muted lg:col-span-2">
          {message}
        </p>
      ) : null}
    </div>
  );
}

function OngletClassement({
  classement,
  erreur,
  methodes,
  methode,
  onMethode,
}: {
  classement: ClassementApi | null;
  erreur: string | null;
  methodes: Record<string, string>;
  methode: string;
  onMethode: (m: string) => void;
}) {
  const [tout, setTout] = useState(false);
  const [lancee, setLancee] = useState(false);
  const robustesse = useApi<RobustesseApi>(
    lancee ? `/decision/robustesse?methode=${methode}` : null,
  );
  if (erreur) return <MessageErreur message={erreur} />;
  if (!classement || classement.bloque) return null;
  const c = classement;
  const r = robustesse.donnees;
  return (
    <div className="grid gap-8">
      <BandeauPartiel
        utilises={c.partiel.utilises}
        actifs={c.partiel.actifs}
        retires={c.retires}
        libelles={c.libelles_retires}
        objet="classement des sites"
      />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div
          className="flex gap-1 rounded-carte bg-paper p-1 ring-1 ring-line"
          role="group"
          aria-label="Méthode de classement"
        >
          {Object.entries(methodes).map(([code, libelle]) => (
            <button
              key={code}
              type="button"
              aria-pressed={code === methode}
              onClick={() => {
                onMethode(code);
              }}
              className={`rounded-bouton px-3 py-1.5 text-secondaire ${code === methode ? "bg-card text-ink shadow-douce" : "text-muted"}`}
            >
              {libelle}
            </button>
          ))}
        </div>
        <p className="text-libelle text-muted">
          Critères utilisés :{" "}
          {c.criteres.map((k) => `${k} (${nombre((c.poids[k] ?? 0) * 100)} %)`).join(", ")}
        </p>
      </div>
      {c.avertissements.length ? (
        <ul
          className="grid gap-1 text-libelle text-muted"
          aria-label="Avertissements du classement"
        >
          {c.avertissements.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      ) : null}
      <CarteClassement c={c} />
      <ClassementSites
        lignes={c.classement}
        scoresAxes={c.scores_axes}
        libellesAxes={c.libelles_axes}
        limite={tout ? undefined : 10}
      />
      <div className="flex flex-wrap gap-3">
        <BoutonsExport route="/exports/classement" requete={`methode=${methode}`} />
        <Bouton
          variante="secondaire"
          onClick={() => {
            setTout((t) => !t);
          }}
        >
          {tout ? "Voir les 10 premiers" : `Voir les ${nombre(c.classement.length)} sites`}
        </Bouton>
      </div>
      {c.exclus.length ? (
        <CarteFlottante
          titre={`${nombre(c.exclus.length)} sites exclus avant le classement`}
          sousTitre="Ils restent visibles avec leur motif (RG-09, RG-10)"
        >
          <ul className="grid gap-1 text-secondaire text-muted">
            {c.exclus.map((e) => (
              <li key={e.id_site}>
                {e.nom} · {e.motif}
              </li>
            ))}
          </ul>
        </CarteFlottante>
      ) : null}
      <section aria-labelledby="titre-robustesse" className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 id="titre-robustesse" className="text-titre-3">
            {r && !r.bloque
              ? `${r.sites[0]?.nom ?? ""} est 1er dans ${nombre((r.sites[0]?.proba_premier ?? 0) * 100)} % des ${nombre(r.tirages)} tirages de poids`
              : "Robustesse du classement"}
          </h2>
          {!lancee ? (
            <Bouton
              icone={<ChartBarIcon size={16} aria-hidden="true" />}
              onClick={() => {
                setLancee(true);
              }}
            >
              Lancer l'analyse de robustesse
            </Bouton>
          ) : null}
        </div>
        {r && !r.bloque ? (
          <div className="overflow-x-auto rounded-carte border border-line bg-card p-4">
            <table className="w-full text-secondaire" aria-label="Robustesse du classement">
              <thead>
                <tr className="border-b border-line text-left text-libelle text-muted">
                  <th scope="col" className="px-2 py-2 font-medium">
                    Site
                  </th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Probabilité d'être 1er (%)
                  </th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Probabilité d'être dans les 3 premiers (%)
                  </th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">
                    Rang WSM / TOPSIS
                  </th>
                  <th scope="col" className="px-2 py-2 font-medium">
                    Lecture (RG-12)
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.sites.slice(0, 10).map((s) => (
                  <tr key={s.id_site} className="border-b border-line last:border-0">
                    <th scope="row" className="px-2 py-1.5 text-left font-normal">
                      {s.nom}
                    </th>
                    <td className="chiffres px-2 py-1.5 text-right">
                      {nombre(s.proba_premier * 100, 1)}
                    </td>
                    <td className="chiffres px-2 py-1.5 text-right">
                      {nombre(s.proba_tete * 100, 1)}
                    </td>
                    <td className="chiffres px-2 py-1.5 text-right">
                      {nombre(s.rang_wsm)} / {nombre(s.rang_topsis)}
                    </td>
                    <td className="px-2 py-1.5">
                      {s.robuste ? (
                        <span className="font-medium text-marque-fonce">robuste</span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-libelle text-muted">
              Un poids à la fois (−50 % à +50 %) : le premier change pour{" "}
              {Object.entries(r.seuils_changement)
                .map(
                  ([k, v]) =>
                    `${k} ${v === null ? "jamais" : `à ${v > 0 ? "+" : ""}${nombre(v * 100)} %`}`,
                )
                .join(", ")}
              . Robuste : 1er dans au moins {nombre(r.seuil_robustesse * 100)} % des tirages et dans
              le trio de tête de WSM et de TOPSIS.
            </p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
