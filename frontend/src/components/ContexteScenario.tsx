import * as Dialog from "@radix-ui/react-dialog";
import { CaretDownIcon, FloppyDiskIcon, SlidersHorizontalIcon } from "@phosphor-icons/react";
import * as Popover from "@radix-ui/react-popover";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import {
  api,
  ErreurApi,
  json,
  type EntrepriseApi,
  type ParametreTechnique,
  type Sante,
  type ScenarioApi,
  type ValeurEntreprise,
  type Version,
} from "../lib/api";
import { date, nombre } from "../lib/format";
import { useApi } from "../lib/useApi";
import Bouton from "./Bouton";
import MessageErreur from "./MessageErreur";

function valeurEntreprise(entreprise: EntrepriseApi | null, identifiant: string): ReactNode {
  const parametre = entreprise?.parametres.find((p) => p.identifiant === identifiant);
  const valeur: ValeurEntreprise | undefined = parametre?.valeur;
  if (valeur === null || valeur === undefined) {
    return (
      <Link
        to={`/parametres#${identifiant}`}
        className="text-ink underline decoration-ember decoration-2 underline-offset-2"
      >
        à renseigner
      </Link>
    );
  }
  const texte =
    typeof valeur === "number"
      ? nombre(valeur)
      : typeof valeur === "string"
        ? valeur
        : JSON.stringify(valeur);
  return (
    <span className="chiffres">
      {texte}
      {typeof valeur === "number" ? ` ${parametre?.unite ?? ""}` : ""}
    </span>
  );
}

function Element({ libelle, children }: { libelle: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-1.5 last:border-0">
      <dt className="text-muted">{libelle}</dt>
      <dd className="text-right text-ink">{children}</dd>
    </div>
  );
}

/**
 * Contexte du scénario (section 12.1), élément discret de la navigation : un bouton qui
 * rappelle le scénario actif et ouvre un panneau avec la campagne de référence, le standard,
 * les paramètres de l'entreprise, la date des données, l'état d'OSRM et « Enregistrer ».
 */
export default function ContexteScenario() {
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const scenarios = useApi<ScenarioApi[]>("/scenarios");
  const versions = useApi<Version[]>("/donnees/versions");
  const sante = useApi<Sante>("/sante");
  const parametres = useApi<ParametreTechnique[]>("/parametres");
  const actif = scenarios.donnees?.[0] ?? null;
  const campagne = parametres.donnees?.find((p) => p.identifiant === "PAR-02")?.courante;
  const derniere = versions.donnees?.[0] ?? null;

  return (
    <Popover.Root>
      <Popover.Trigger
        className="inline-flex max-w-44 items-center gap-1.5 rounded-bouton border border-line px-2.5 py-1.5 text-libelle text-ink hover:bg-paper"
        aria-label={`Contexte du scénario : ${actif?.nom ?? "aucun scénario enregistré"}`}
      >
        <SlidersHorizontalIcon size={14} aria-hidden="true" className="shrink-0 text-muted" />
        <span className="truncate">{actif?.nom ?? "Scénario"}</span>
        <CaretDownIcon size={12} aria-hidden="true" className="shrink-0 text-muted" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={10}
          className="z-50 w-80 rounded-carte border border-line bg-card p-4 text-libelle shadow-douce"
        >
          <p className="text-muted">Scénario actif</p>
          <p className="text-secondaire font-medium text-ink">
            {actif?.nom ?? "aucun scénario enregistré"}
          </p>
          <dl className="mt-3">
            <Element libelle="Campagne de référence">
              {campagne?.valeur !== undefined && campagne.valeur !== null
                ? `moyenne des ${String(campagne.valeur)} dernières`
                : "—"}
            </Element>
            <Element libelle="Standard carbone">neutre (RG-07)</Element>
            <Element libelle="Capacité K">{valeurEntreprise(entreprise.donnees, "PAR-01")}</Element>
            <Element libelle="Prix plafond">
              {valeurEntreprise(entreprise.donnees, "PAR-34")}
            </Element>
            <Element libelle="Pyrolyse">{valeurEntreprise(entreprise.donnees, "PAR-21")}</Element>
            <Element libelle="Prix du gazole">
              {valeurEntreprise(entreprise.donnees, "PAR-37")}
            </Element>
            <Element libelle="Données du">{derniere ? date(derniere.date) : "—"}</Element>
            <Element libelle="OSRM">{sante.donnees?.osrm ?? "—"}</Element>
          </dl>
          <div className="mt-4">
            <Enregistrer onEnregistre={scenarios.recharger} />
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function Enregistrer({ onEnregistre }: { onEnregistre: () => void }) {
  const [ouvert, setOuvert] = useState(false);
  const [nom, setNom] = useState("");
  const [auteur, setAuteur] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);

  async function enregistrer() {
    try {
      await api<ScenarioApi>("/scenarios", json("POST", { nom, auteur }));
      setOuvert(false);
      setErreur(null);
      onEnregistre();
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Enregistrement impossible.");
    }
  }

  return (
    <Dialog.Root open={ouvert} onOpenChange={setOuvert}>
      <Dialog.Trigger asChild>
        <Bouton variante="secondaire" icone={<FloppyDiskIcon size={16} />}>
          Enregistrer le scénario
        </Bouton>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-charcoal/40" />
        <Dialog.Content className="fixed left-1/2 top-1/3 w-[26rem] -translate-x-1/2 rounded-carte bg-card p-5 shadow-douce">
          <Dialog.Title className="text-titre-4">Enregistrer le scénario</Dialog.Title>
          <Dialog.Description className="mt-1 text-secondaire text-muted">
            Le scénario garde les paramètres de l'entreprise, les réglages et la version des données
            en cours.
          </Dialog.Description>
          <form
            className="mt-4 grid gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void enregistrer();
            }}
          >
            <label className="grid gap-1 text-libelle text-muted">
              Nom du scénario
              <input
                required
                value={nom}
                onChange={(e) => {
                  setNom(e.target.value);
                }}
                className="rounded-bouton border border-line px-2 py-1.5 text-texte text-ink"
              />
            </label>
            <label className="grid gap-1 text-libelle text-muted">
              Auteur
              <input
                required
                value={auteur}
                onChange={(e) => {
                  setAuteur(e.target.value);
                }}
                className="rounded-bouton border border-line px-2 py-1.5 text-texte text-ink"
              />
            </label>
            {erreur ? <MessageErreur message={erreur} /> : null}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <Bouton variante="secondaire">Annuler</Bouton>
              </Dialog.Close>
              <Bouton type="submit">Enregistrer</Bouton>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
