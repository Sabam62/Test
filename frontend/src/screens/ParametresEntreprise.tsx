import {
  ArrowCounterClockwiseIcon,
  CaretRightIcon,
  MagnifyingGlassIcon,
  PencilSimpleIcon,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router";

import Bouton from "../components/Bouton";
import ChampParametre from "../components/ChampParametre";
import EnTeteEcran from "../components/EnTeteEcran";
import EtatVide from "../components/EtatVide";
import IndicateurDemo from "../components/IndicateurDemo";
import MessageErreur from "../components/MessageErreur";
import ValeurSourcee from "../components/ValeurSourcee";
import {
  api,
  ErreurApi,
  json,
  signalerModification,
  type DemoApi,
  type EntrepriseApi,
  type ParametreEntrepriseApi,
  type ParametreTechnique,
  type ScenarioApi,
  type ValeurEntreprise,
} from "../lib/api";
import { chargerDemonstration, quitterDemonstration, useOperationDemo } from "../lib/demo";
import { date, nombre } from "../lib/format";
import { correspond, SECTIONS, type CarteParametres } from "../lib/sectionsParametres";
import { useApi } from "../lib/useApi";

const CLE_AUTEUR = "ab-dss:auteur";
const SECTION_SCENARIOS = "scenarios";

function enTexte(valeur: ValeurEntreprise): string {
  if (valeur === null) return "";
  if (typeof valeur === "number" || typeof valeur === "string") return String(valeur);
  if (Array.isArray(valeur)) return valeur.join(", ");
  return "";
}

/** Clé de recherche : sans accents ni casse. */
function cle(texte: string): string {
  return texte
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

interface Filtres {
  recherche: string;
  modifiesSeulement: boolean;
}

function retenuEntreprise(p: ParametreEntrepriseApi, f: Filtres): boolean {
  if (f.modifiesSeulement && p.valeur === null) return false;
  return !f.recherche || cle(`${p.identifiant} ${p.libelle}`).includes(cle(f.recherche));
}

function retenuTechnique(p: ParametreTechnique, f: Filtres): boolean {
  if (f.modifiesSeulement && !p.modifie) return false;
  return !f.recherche || cle(`${p.identifiant} ${p.libelle}`).includes(cle(f.recherche));
}

/**
 * Paramètres (UC-ENT-01, UC-SCN-01, 02) : menu de sections à gauche, cartes de quelques champs
 * rangées selon la section 14, recherche et filtre « modifiés seulement ».
 */
export default function ParametresEntreprise() {
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const techniques = useApi<ParametreTechnique[]>("/parametres");
  const scenarios = useApi<ScenarioApi[]>("/scenarios");
  const e = entreprise.donnees;
  const t = useMemo(() => techniques.donnees ?? [], [techniques.donnees]);
  const [recherche, setRecherche] = useState("");
  const [modifiesSeulement, setModifiesSeulement] = useState(false);
  const [auteur, setAuteur] = useState(() => localStorage.getItem(CLE_AUTEUR) ?? "");
  const [techniquesOuverts, setTechniquesOuverts] = useState(false);
  const { hash } = useLocation();
  const filtres: Filtres = { recherche, modifiesSeulement };

  useEffect(() => {
    localStorage.setItem(CLE_AUTEUR, auteur);
  }, [auteur]);

  // Arrivée par un lien « Renseignez … dans Paramètres » ou par le menu : section ou champ visé.
  useEffect(() => {
    if (!hash || !e || !techniques.donnees) return;
    const cible = decodeURIComponent(hash.slice(1));
    if (cible === "section-techniques" || cible.startsWith("technique-")) {
      setTechniquesOuverts(true);
    }
    const element = document.getElementById(cible);
    if (element) {
      element.scrollIntoView({ block: cible.startsWith("section-") ? "start" : "center" });
      if (!cible.startsWith("section-")) element.focus({ preventScroll: true });
    }
  }, [hash, e, techniques.donnees]);

  // Une recherche qui touche les réglages techniques ouvre leur section.
  useEffect(() => {
    if (recherche && t.some((p) => retenuTechnique(p, { recherche, modifiesSeulement: false }))) {
      setTechniquesOuverts(true);
    }
  }, [recherche, t]);

  const places = new Set(
    SECTIONS.flatMap((s) => s.cartes.filter((c) => c.origine === "technique")).flatMap((c) =>
      t
        .filter((p) => c.parametres.some((m) => correspond(m, p.identifiant)))
        .map((p) => p.identifiant),
    ),
  );
  const orphelins = t.filter((p) => !places.has(p.identifiant)).map((p) => p.identifiant);
  const sections = SECTIONS.map((s) =>
    s.id === "techniques" && orphelins.length
      ? {
          ...s,
          cartes: [
            ...s.cartes,
            {
              titre: "Autres",
              description: "Paramètres techniques non classés.",
              origine: "technique" as const,
              parametres: orphelins,
            },
          ],
        }
      : s,
  );

  const parametresCarte = (c: CarteParametres) =>
    c.origine === "entreprise"
      ? (e?.parametres ?? []).filter(
          (p) => c.parametres.includes(p.identifiant) && retenuEntreprise(p, filtres),
        )
      : t.filter(
          (p) =>
            c.parametres.some((m) => correspond(m, p.identifiant)) && retenuTechnique(p, filtres),
        );

  const manquants = e?.a_renseigner.length ?? 0;
  const modifies = t.filter((p) => p.modifie).length;

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-12 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={
          e === null
            ? "Paramètres"
            : manquants > 0
              ? `${nombre(manquants)} paramètres obligatoires sur ${nombre(e.obligatoires.length)} restent à renseigner`
              : `Les ${nombre(e.obligatoires.length)} paramètres obligatoires sont renseignés ; ${nombre(modifies)} réglages techniques modifiés`
        }
        phrase="Réglez la stratégie d'Atlantic Biochar et les réglages de calcul : chaque valeur garde sa source, chaque modification est datée et signée."
      />
      {entreprise.erreur ? <MessageErreur message={entreprise.erreur} /> : null}
      {techniques.erreur ? <MessageErreur message={techniques.erreur} /> : null}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <nav aria-label="Sections des paramètres">
            <ul className="grid gap-1 text-secondaire">
              {[...sections, { id: SECTION_SCENARIOS, titre: "Scénarios" }].map((s) => (
                <li key={s.id}>
                  <a
                    href={`#section-${s.id}`}
                    className="flex items-center justify-between gap-2 rounded-bouton px-3 py-2 text-ink hover:bg-card"
                  >
                    {s.titre}
                    {s.id === "entreprise" && manquants > 0 ? (
                      <span className="rounded-full bg-ember px-1.5 text-source font-medium text-ink">
                        {nombre(manquants)}
                      </span>
                    ) : null}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <label className="mt-6 grid gap-1 text-libelle text-muted">
            Auteur des modifications
            <input
              value={auteur}
              onChange={(ev) => {
                setAuteur(ev.target.value);
              }}
              className="rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire text-ink"
            />
          </label>
        </aside>

        <div className="grid min-w-0 gap-12">
          <div className="flex flex-wrap items-end gap-4">
            <label className="grid w-80 gap-1 text-libelle text-muted">
              Rechercher un paramètre (nom ou PAR-xx)
              <span className="flex items-center gap-2 rounded-bouton border border-line bg-card px-2">
                <MagnifyingGlassIcon size={16} aria-hidden="true" />
                <input
                  type="search"
                  value={recherche}
                  onChange={(ev) => {
                    setRecherche(ev.target.value);
                  }}
                  className="w-full bg-card py-1.5 text-secondaire text-ink outline-none"
                />
              </span>
            </label>
            <label className="flex items-center gap-2 pb-2 text-secondaire text-ink">
              <input
                type="checkbox"
                checked={modifiesSeulement}
                onChange={(ev) => {
                  setModifiesSeulement(ev.target.checked);
                }}
              />
              Modifiés seulement
            </label>
          </div>

          {sections.map((s) => {
            const cartes = s.cartes
              .map((c) => ({ carte: c, parametres: parametresCarte(c) }))
              .filter((c) => c.parametres.length > 0);
            if (!cartes.length && (recherche || modifiesSeulement)) return null;
            const contenu = (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {cartes.map(({ carte, parametres }) =>
                  carte.origine === "entreprise" ? (
                    <CarteEntreprise
                      key={`${carte.titre}|${parametres.map((p) => `${p.identifiant}=${enTexte((p as ParametreEntrepriseApi).valeur)}`).join("|")}`}
                      carte={carte}
                      parametres={parametres as ParametreEntrepriseApi[]}
                      auteur={auteur}
                    />
                  ) : (
                    <CarteTechnique
                      key={carte.titre}
                      carte={carte}
                      parametres={parametres as ParametreTechnique[]}
                      auteur={auteur}
                    />
                  ),
                )}
                {!cartes.length ? (
                  <p className="text-secondaire text-muted">Aucun paramètre dans cette section.</p>
                ) : null}
              </div>
            );
            return (
              <section
                key={s.id}
                id={`section-${s.id}`}
                aria-labelledby={`titre-${s.id}`}
                className="grid scroll-mt-6 gap-4"
              >
                {s.repliee ? (
                  <details
                    open={techniquesOuverts}
                    onToggle={(ev) => {
                      setTechniquesOuverts((ev.target as HTMLDetailsElement).open);
                    }}
                    className="group grid gap-4"
                  >
                    <summary className="flex cursor-pointer list-none items-center gap-2">
                      <CaretRightIcon
                        size={18}
                        aria-hidden="true"
                        className="transition-transform duration-courte group-open:rotate-90"
                      />
                      <h2 id={`titre-${s.id}`} className="text-titre-3">
                        {s.titre}
                      </h2>
                    </summary>
                    <p className="mb-4 mt-1 text-secondaire text-muted">{s.description}</p>
                    {contenu}
                  </details>
                ) : (
                  <>
                    <div>
                      <h2 id={`titre-${s.id}`} className="text-titre-3">
                        {s.titre}
                      </h2>
                      <p className="mt-1 text-secondaire text-muted">{s.description}</p>
                    </div>
                    {contenu}
                  </>
                )}
              </section>
            );
          })}

          <section
            id={`section-${SECTION_SCENARIOS}`}
            aria-labelledby="titre-scenarios"
            className="grid scroll-mt-6 gap-4"
          >
            <h2 id="titre-scenarios" className="text-titre-3">
              {scenarios.donnees?.length
                ? `${nombre(scenarios.donnees.length)} scénarios enregistrés`
                : "Aucun scénario enregistré"}
            </h2>
            {scenarios.donnees?.length ? (
              <ListeScenarios scenarios={scenarios.donnees} auteur={auteur} />
            ) : (
              <EtatVide message="Enregistrez l'état courant depuis le bouton « Scénario » de la navigation : le scénario garde les paramètres et la version des données." />
            )}
            <EtatVide message="L'effet d'un paramètre sur le rang des sites sera tracé quand le classement sera disponible." />
            <SectionDemonstration />
          </section>
        </div>
      </div>
    </div>
  );
}

// --- Carte de paramètres de l'entreprise ----------------------------------------------------

function CarteEntreprise({
  carte,
  parametres,
  auteur,
}: {
  carte: CarteParametres;
  parametres: ParametreEntrepriseApi[];
  auteur: string;
}) {
  // Valeurs initiales : la carte est remontée (clé) quand les valeurs enregistrées changent.
  const [valeurs, setValeurs] = useState<Record<string, string>>(() =>
    Object.fromEntries(parametres.map((p) => [p.identifiant, enTexte(p.valeur)])),
  );
  const [message, setMessage] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const modifiees = Object.fromEntries(
    Object.entries(valeurs).filter(([id, v]) => {
      const actuel = parametres.find((p) => p.identifiant === id);
      return actuel !== undefined && actuel.type !== "sites" && enTexte(actuel.valeur) !== v;
    }),
  );

  async function enregistrer() {
    try {
      const reponse = await api<EntrepriseApi>(
        "/entreprise",
        json("PUT", { auteur, valeurs: modifiees }),
      );
      setErreur(null);
      setMessage(
        reponse.modifies?.length
          ? `Enregistré : ${reponse.modifies.join(", ")}.`
          : "Aucun changement.",
      );
    } catch (ex) {
      setMessage(null);
      setErreur(ex instanceof ErreurApi ? ex.message : "Enregistrement impossible.");
    }
  }

  return (
    <form
      className="grid content-start gap-4 rounded-carte border border-line bg-card p-4 shadow-douce"
      aria-label={carte.titre}
      onSubmit={(ev) => {
        ev.preventDefault();
        void enregistrer();
      }}
    >
      <header>
        <h3 className="font-texte text-secondaire font-medium tracking-normal">{carte.titre}</h3>
        <p className="text-libelle text-muted">{carte.description}</p>
      </header>
      {parametres.map((p) =>
        p.type === "sites" ? (
          <p key={p.identifiant} className="text-libelle text-muted">
            {p.libelle} : la liste des sites candidats arrive avec le module logistique.
          </p>
        ) : (
          <ChampParametre
            key={p.identifiant}
            parametre={p}
            valeur={valeurs[p.identifiant] ?? ""}
            onChange={(v) => {
              setValeurs((a) => ({ ...a, [p.identifiant]: v }));
            }}
          />
        ),
      )}
      {parametres.some((p) => p.type !== "sites") ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-libelle text-muted">
            {auteur.trim() ? `Signé ${auteur.trim()}` : "Indiquez l'auteur dans le menu de gauche"}
          </span>
          <Bouton type="submit" disabled={!auteur.trim() || !Object.keys(modifiees).length}>
            Enregistrer
          </Bouton>
        </div>
      ) : null}
      {message ? <p className="text-secondaire text-ink">{message}</p> : null}
      {erreur ? <MessageErreur message={erreur} /> : null}
    </form>
  );
}

// --- Carte de paramètres techniques ---------------------------------------------------------

function CarteTechnique({
  carte,
  parametres,
  auteur,
}: {
  carte: CarteParametres;
  parametres: ParametreTechnique[];
  auteur: string;
}) {
  const [edition, setEdition] = useState<string | null>(null);
  const [champs, setChamps] = useState({ valeur: "", source: "" });
  const [erreur, setErreur] = useState<string | null>(null);

  async function regler(identifiant: string) {
    try {
      await api(
        `/parametres/${encodeURIComponent(identifiant)}`,
        json("PUT", { ...champs, auteur }),
      );
      setEdition(null);
      setErreur(null);
    } catch (ex) {
      setErreur(ex instanceof ErreurApi ? ex.message : "Réglage impossible.");
    }
  }

  async function defaut(identifiant: string) {
    await api(`/parametres/${encodeURIComponent(identifiant)}`, json("DELETE"));
  }

  return (
    <section
      className="rounded-carte border border-line bg-card p-4 shadow-douce"
      aria-label={carte.titre}
    >
      <header>
        <h3 className="font-texte text-secondaire font-medium tracking-normal">{carte.titre}</h3>
        <p className="text-libelle text-muted">{carte.description}</p>
      </header>
      {erreur ? (
        <div className="mt-2">
          <MessageErreur message={erreur} />
        </div>
      ) : null}
      <ul className="mt-3 grid">
        {parametres.map((p) => (
          <li
            key={p.identifiant}
            id={`technique-${p.identifiant}`}
            tabIndex={-1}
            className="grid gap-1 border-b border-line py-2 text-secondaire last:border-0"
          >
            <div className="flex items-start justify-between gap-3">
              <span>
                <span className="text-muted">{p.identifiant}</span> · {p.libelle}
              </span>
              {p.calcul ? null : (
                <span className="inline-flex shrink-0 gap-2">
                  <button
                    type="button"
                    className="p-1 text-muted hover:text-ink"
                    aria-label={`Régler ${p.identifiant}`}
                    onClick={() => {
                      setChamps({ valeur: "", source: "" });
                      setEdition(p.identifiant);
                    }}
                  >
                    <PencilSimpleIcon size={16} aria-hidden="true" />
                  </button>
                  {p.modifie ? (
                    <button
                      type="button"
                      className="p-1 text-muted hover:text-ink"
                      aria-label={`Revenir à la valeur par défaut de ${p.identifiant}`}
                      onClick={() => {
                        void defaut(p.identifiant);
                      }}
                    >
                      <ArrowCounterClockwiseIcon size={16} aria-hidden="true" />
                    </button>
                  ) : null}
                </span>
              )}
            </div>
            {p.calcul ? (
              <span className="text-libelle text-muted">Calculé : {p.calcul}</span>
            ) : edition === p.identifiant ? (
              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(ev) => {
                  ev.preventDefault();
                  void regler(p.identifiant);
                }}
              >
                {(["valeur", "source"] as const).map((champ) => (
                  <input
                    key={champ}
                    required
                    aria-label={`${champ} du réglage de ${p.identifiant}`}
                    placeholder={champ}
                    value={champs[champ]}
                    onChange={(ev) => {
                      setChamps((c) => ({ ...c, [champ]: ev.target.value }));
                    }}
                    className="w-40 rounded-segment border border-line px-1.5 py-0.5"
                  />
                ))}
                <Bouton type="submit" className="px-2 py-1" disabled={!auteur.trim()}>
                  Régler
                </Bouton>
                <Bouton
                  variante="secondaire"
                  className="px-2 py-1"
                  onClick={() => {
                    setEdition(null);
                  }}
                >
                  Annuler
                </Bouton>
              </form>
            ) : p.courante ? (
              <span className="flex flex-wrap items-baseline gap-x-3">
                <ValeurSourcee
                  valeur={p.courante.valeur}
                  unite={p.courante.unite}
                  decimales={3}
                  provenance={{
                    source_id: p.courante.provenance?.source_id ?? null,
                    annee: p.courante.provenance?.annee ?? null,
                    statut:
                      p.courante.provenance?.statut ??
                      (p.courante.a_completer ? "À compléter" : null),
                    note: p.courante.ou_trouver
                      ? `Où la trouver : ${p.courante.ou_trouver}`
                      : (p.courante.provenance?.note ?? null),
                  }}
                />
                {p.modifie && p.defaut ? (
                  <span className="text-libelle text-muted">
                    défaut : {String(p.defaut.valeur ?? "À compléter")}
                  </span>
                ) : null}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- Scénarios ------------------------------------------------------------------------------

function ListeScenarios({ scenarios, auteur }: { scenarios: ScenarioApi[]; auteur: string }) {
  const [erreur, setErreur] = useState<string | null>(null);

  async function charger(nom: string) {
    try {
      await api(`/scenarios/${encodeURIComponent(nom)}/appliquer`, json("POST", { auteur }));
      setErreur(null);
    } catch (ex) {
      setErreur(ex instanceof ErreurApi ? ex.message : "Chargement impossible.");
    }
  }

  return (
    <div className="grid gap-3">
      {erreur ? <MessageErreur message={erreur} /> : null}
      <ul className="grid gap-2">
        {scenarios.map((s) => (
          <li
            key={s.nom}
            className="flex flex-wrap items-center justify-between gap-4 rounded-carte border border-line bg-card px-4 py-3"
          >
            <div>
              <p className="font-medium text-ink">{s.nom}</p>
              <p className="text-libelle text-muted">
                {date(s.date)} · {s.auteur} · données {s.version_donnees ?? "livrées"}
              </p>
              {s.ecart_version ? (
                <p className="text-libelle text-ink">Attention : {s.ecart_version}.</p>
              ) : null}
            </div>
            <Bouton
              variante="secondaire"
              disabled={!auteur.trim()}
              onClick={() => {
                void charger(s.nom);
              }}
            >
              Charger
            </Bouton>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Démonstration --------------------------------------------------------------------------

/**
 * Scénarios de démonstration (soutenance) : un clic charge le scénario dans une copie de travail
 * (paramètres d'hypothèse, valeurs manquantes complétées) ; les saisies réelles ne sont jamais
 * modifiées et « Quitter la démonstration » y revient.
 */
function SectionDemonstration() {
  const demo = useApi<DemoApi>("/demo");
  // Opération partagée avec le bandeau : un seul chargement ou retour à la fois.
  const operation = useOperationDemo();
  const [erreur, setErreur] = useState<string | null>(null);
  const d = demo.donnees;
  if (!d?.scenarios.length) return null;
  const active = d.active;
  const occupe = operation !== null;

  async function agir(action: () => Promise<boolean>) {
    try {
      if (await action()) signalerModification();
      setErreur(null);
    } catch (ex) {
      setErreur(
        ex instanceof ErreurApi ? ex.message : "Chargement de la démonstration impossible.",
      );
    }
  }

  return (
    <section aria-labelledby="titre-demonstration" className="grid gap-3">
      <h3 id="titre-demonstration" className="text-titre-3">
        Démonstration :{" "}
        {active
          ? `« ${active.nom} » chargée`
          : `${nombre(d.scenarios.length)} scénarios à charger en un clic`}
      </h3>
      <p className="text-secondaire text-muted">
        {d.bandeau}. Les paramètres de l&apos;entreprise et les valeurs manquantes sont fixés par
        hypothèse (liste et sources : docs/demo.md) dans une copie de travail ; vos saisies et vos
        données ne sont jamais modifiées.
      </p>
      {operation ? <IndicateurDemo operation={operation} /> : null}
      {erreur ? <MessageErreur message={erreur} /> : null}
      <ul className="grid gap-2" aria-busy={occupe}>
        {d.scenarios.map((s) => {
          const charge = active?.identifiant === s.identifiant;
          return (
            <li
              key={s.identifiant}
              className={`flex flex-wrap items-center justify-between gap-4 rounded-carte border bg-card px-4 py-3 ${charge ? "border-2 border-ember" : "border-line"}`}
            >
              <div>
                <p className="font-medium text-ink">{s.nom}</p>
                <p className="text-libelle text-muted">{s.description}</p>
              </div>
              <Bouton
                variante={charge ? "secondaire" : "primaire"}
                disabled={occupe}
                aria-label={`Charger la démonstration « ${s.nom} »`}
                onClick={() => {
                  void agir(() => chargerDemonstration(s.identifiant, s.nom));
                }}
              >
                {operation?.type === "chargement" && operation.nom === s.nom
                  ? "Chargement…"
                  : charge
                    ? "Recharger"
                    : "Charger"}
              </Bouton>
            </li>
          );
        })}
      </ul>
      {active ? (
        <div>
          <Bouton
            variante="secondaire"
            disabled={occupe}
            onClick={() => {
              void agir(quitterDemonstration);
            }}
          >
            Quitter la démonstration
          </Bouton>
        </div>
      ) : null}
    </section>
  );
}
