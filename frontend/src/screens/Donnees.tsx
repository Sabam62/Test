import * as Tabs from "@radix-ui/react-tabs";
import { DownloadSimpleIcon, UploadSimpleIcon } from "@phosphor-icons/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import Bouton from "../components/Bouton";
import CarteFlottante from "../components/CarteFlottante";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import TableauEditable, { type Colonne } from "../components/TableauEditable";
import {
  api,
  ErreurApi,
  json,
  type ApercuImport,
  type Comparaison,
  type GeoJsonContours,
  type Ligne,
  type PageTable,
  type PrixApi,
  type SourceApi,
  type StatutProvinces,
  type TableInfo,
  type Version,
} from "../lib/api";
import { date, nombre } from "../lib/format";
import type { Resume } from "../lib/resume";
import { useApi } from "../lib/useApi";
import CarteSatellite from "../map/CarteSatellite";
import { couleurs } from "../theme/couleurs";
import { STYLE_BOUTON_PRIMAIRE } from "../theme/boutons";

const ONGLETS = [
  ["controle", "Statut et contrôle"],
  ["tables", "Tables et saisie"],
  ["import", "Import Excel"],
  ["prix", "Prix et coûts"],
  ["versions", "Versions"],
  ["sources", "Sources"],
] as const;

/**
 * Colonnes de provenance détaillée masquées dans le tableau : elles restent lisibles au survol
 * de chaque valeur (UC-01) et dans le modèle Excel.
 */
const MASQUEES = new Set([
  "url",
  "document",
  "note",
  "soustraites",
  "ou_trouver",
  "autres_sources",
  "source_total",
  "part_cropgrids",
  "methode",
  "ecart_campagne",
  "periode",
  "annee",
  "version",
  "min",
  "mode",
  "max",
  "loi",
]);

/** Unité affichée dans l'en-tête de la colonne valeur de chaque table. */
const UNITES: Record<string, string> = { production: "t ou ha selon la grandeur" };

/** Page Données (section 7.3) : l'entreprise met l'outil à jour sans écrire de code. */
export default function Donnees() {
  const resume = useApi<Resume>("/donnees/resume");
  const tables = useApi<TableInfo[]>("/donnees/tables");
  const r = resume.donnees;
  const [rafraichissement, setRafraichissement] = useState(0);
  const modifie = () => {
    resume.recharger();
    tables.recharger();
    setRafraichissement((n) => n + 1);
  };

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-16 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={
          r
            ? `Données du ${date(r.derniere_version?.date)} : ${nombre(r.valeurs_production)} valeurs de production, dont ${nombre(r.valeurs_reelles)} publiées à la maille provinciale`
            : "Données"
        }
        phrase="Mettez à jour les tables par modèle Excel ou saisie directe, suivez les prix, comparez et restaurez les versions : chaque modification crée une version (RG-17)."
      />
      {resume.erreur ? <MessageErreur message={resume.erreur} /> : null}
      <Tabs.Root defaultValue="controle" className="grid min-w-0 gap-8">
        <Tabs.List
          aria-label="Outils de mise à jour des données"
          className="flex flex-wrap gap-6 border-b border-line"
        >
          {ONGLETS.map(([valeur, libelle]) => (
            <Tabs.Trigger
              key={valeur}
              value={valeur}
              className="-mb-px border-b-2 border-transparent pb-2 text-secondaire text-muted data-[state=active]:border-ink data-[state=active]:text-ink"
            >
              {libelle}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content className="min-w-0" value="tables">
          <OngletTables tables={tables.donnees ?? []} onModifie={modifie} cle={rafraichissement} />
        </Tabs.Content>
        <Tabs.Content className="min-w-0" value="import">
          <OngletImport tables={tables.donnees ?? []} onModifie={modifie} />
        </Tabs.Content>
        <Tabs.Content className="min-w-0" value="prix">
          <OngletPrix onModifie={modifie} />
        </Tabs.Content>
        <Tabs.Content className="min-w-0" value="versions">
          <OngletVersions
            tables={tables.donnees ?? []}
            onModifie={modifie}
            cle={rafraichissement}
          />
        </Tabs.Content>
        <Tabs.Content className="min-w-0" value="controle">
          <OngletControle />
        </Tabs.Content>
        <Tabs.Content className="min-w-0" value="sources">
          <OngletSources />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

// --- Champs communs ------------------------------------------------------------------------

function Champ({
  libelle,
  valeur,
  onChange,
  type = "text",
  requis = true,
  largeur = "w-56",
  liste,
}: {
  libelle: string;
  valeur: string;
  onChange: (v: string) => void;
  type?: string;
  requis?: boolean;
  largeur?: string;
  /** Identifiant d'une liste de suggestions (datalist). */
  liste?: string;
}) {
  return (
    <label className={`grid gap-1 text-libelle text-muted ${largeur}`}>
      {libelle}
      <input
        type={type}
        required={requis}
        list={liste}
        value={valeur}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        className="rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire text-ink"
      />
    </label>
  );
}

function Selection({
  libelle,
  valeur,
  options,
  onChange,
}: {
  libelle: string;
  valeur: string;
  options: { valeur: string; libelle: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="grid gap-1 text-libelle text-muted">
      {libelle}
      <select
        value={valeur}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        className="rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire text-ink"
      >
        {options.map((o) => (
          <option key={o.valeur} value={o.valeur}>
            {o.libelle}
          </option>
        ))}
      </select>
    </label>
  );
}

function aujourdhui(): string {
  return new Date().toISOString().slice(0, 10);
}

// --- Tables et saisie directe --------------------------------------------------------------

function OngletTables({
  tables,
  onModifie,
  cle,
}: {
  tables: TableInfo[];
  onModifie: () => void;
  cle: number;
}) {
  const [table, setTable] = useState("production");
  const [filtre, setFiltre] = useState("");
  const [recherche, setRecherche] = useState("");
  const [page, setPage] = useState(0);
  const chemin = `/donnees/tables/${table}?page=${String(page)}${recherche ? `&filtre=${encodeURIComponent(recherche)}` : ""}&_=${String(cle)}`;
  const donnees = useApi<PageTable>(chemin);
  const [saisie, setSaisie] = useState<{ ligne: Ligne; valeur: string } | null>(null);
  const info = tables.find((t) => t.table === table);

  const colonnes: Colonne[] = useMemo(
    () =>
      (donnees.donnees?.colonnes ?? [])
        .filter((c) => !MASQUEES.has(c))
        .map((c) => ({
          cle: c,
          libelle: c.replaceAll("_", " "),
          ...(c === "valeur" && UNITES[table] ? { unite: UNITES[table] } : {}),
          ...(c === "valeur" ? { decimales: 2 } : {}),
        })),
    [donnees.donnees, table],
  );

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-end gap-4">
        <Selection
          libelle="Table"
          valeur={table}
          options={tables.map((t) => ({ valeur: t.table, libelle: t.libelle }))}
          onChange={(v) => {
            setTable(v);
            setPage(0);
          }}
        />
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setRecherche(filtre);
            setPage(0);
          }}
        >
          <Champ
            libelle="Filtrer (province, culture, source…)"
            valeur={filtre}
            onChange={setFiltre}
            requis={false}
          />
          <Bouton type="submit" variante="secondaire">
            Filtrer
          </Bouton>
        </form>
        {info ? (
          <p className="text-libelle text-muted">
            {info.lignes !== null ? `${nombre(info.lignes)} lignes` : "table absente"} · mise à jour
            le {date(info.mise_a_jour)}
          </p>
        ) : null}
      </div>
      {donnees.erreur ? <MessageErreur message={donnees.erreur} /> : null}
      {saisie ? (
        <FormulaireSaisie
          table={table}
          cleTable={info?.cle ?? []}
          {...saisie}
          onFin={(ok) => {
            setSaisie(null);
            if (ok) onModifie();
          }}
        />
      ) : null}
      {donnees.donnees ? (
        <CarteFlottante
          titre={`${info?.libelle ?? table} : ${nombre(donnees.donnees.total)} lignes`}
          source="Survolez ou cliquez une valeur pour voir sa source, son année et son statut (UC-01). Le crayon corrige une valeur avec sa source et sa date (UC-DAT-07)."
        >
          <TableauEditable
            libelle={info?.libelle ?? table}
            colonnes={colonnes}
            lignes={donnees.donnees.lignes}
            colonneValeur="valeur"
            provenance={{
              source: "source_id",
              annee: "annee",
              statut: "statut",
              version: "version",
            }}
            onModifier={(ligne, valeur) => {
              setSaisie({ ligne, valeur });
            }}
          />
          <div className="mt-3 flex items-center gap-3 text-libelle text-muted">
            <Bouton
              variante="secondaire"
              disabled={page === 0}
              onClick={() => {
                setPage((p) => p - 1);
              }}
            >
              Page précédente
            </Bouton>
            <span>
              Page {nombre(page + 1)} sur{" "}
              {nombre(
                Math.max(1, Math.ceil(donnees.donnees.total / donnees.donnees.lignes_par_page)),
              )}
            </span>
            <Bouton
              variante="secondaire"
              disabled={(page + 1) * donnees.donnees.lignes_par_page >= donnees.donnees.total}
              onClick={() => {
                setPage((p) => p + 1);
              }}
            >
              Page suivante
            </Bouton>
          </div>
        </CarteFlottante>
      ) : null}
    </div>
  );
}

function FormulaireSaisie({
  table,
  cleTable,
  ligne,
  valeur,
  onFin,
}: {
  table: string;
  cleTable: string[];
  ligne: Ligne;
  valeur: string;
  onFin: (ok: boolean) => void;
}) {
  const [source, setSource] = useState("");
  const [jour, setJour] = useState(aujourdhui());
  const [auteur, setAuteur] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState(false);
  const cle = Object.fromEntries(cleTable.map((c) => [c, texte(ligne[c])]));

  async function enregistrer() {
    try {
      await api(
        `/donnees/tables/${table}/valeur`,
        json("PUT", {
          cle,
          valeur,
          source,
          date: jour,
          auteur,
          commentaire,
          confirmer: confirmation,
        }),
      );
      onFin(true);
    } catch (e) {
      if (e instanceof ErreurApi && e.confirmationRequise) setConfirmation(true);
      setErreur(e instanceof ErreurApi ? e.message : "Saisie impossible.");
    }
  }

  return (
    <CarteFlottante
      titre={`Corriger la valeur : ${Object.values(cle).join(" · ")}`}
      sousTitre={`Nouvelle valeur : ${valeur}. La source et la date sont obligatoires (RG-18).`}
    >
      <form
        className="flex flex-wrap items-end gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void enregistrer();
        }}
      >
        <Champ
          libelle="Source (lien, document ou « mesure interne »)"
          valeur={source}
          onChange={setSource}
          largeur="w-72"
        />
        <Champ
          libelle="Date de la valeur"
          type="date"
          valeur={jour}
          onChange={setJour}
          largeur="w-40"
        />
        <Champ libelle="Auteur" valeur={auteur} onChange={setAuteur} />
        <Champ
          libelle="Commentaire"
          valeur={commentaire}
          onChange={setCommentaire}
          largeur="w-72"
        />
        <Bouton type="submit">{confirmation ? "Confirmer la valeur" : "Enregistrer"}</Bouton>
        <Bouton
          variante="secondaire"
          onClick={() => {
            onFin(false);
          }}
        >
          Annuler
        </Bouton>
      </form>
      {erreur ? (
        <div className="mt-3">
          <MessageErreur message={erreur} />
        </div>
      ) : null}
    </CarteFlottante>
  );
}

function texte(valeur: unknown): string {
  if (valeur === null || valeur === undefined) return "";
  if (typeof valeur === "string") return valeur;
  if (typeof valeur === "number" || typeof valeur === "boolean") return String(valeur);
  return JSON.stringify(valeur);
}

// --- Import par modèle Excel (UC-DAT-06) ---------------------------------------------------

function OngletImport({ tables, onModifie }: { tables: TableInfo[]; onModifie: () => void }) {
  const [table, setTable] = useState("production");
  const [fichier, setFichier] = useState<File | null>(null);
  const [apercu, setApercu] = useState<ApercuImport | null>(null);
  const [confirmees, setConfirmees] = useState<number[]>([]);
  const [auteur, setAuteur] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [resultat, setResultat] = useState<string | null>(null);

  async function deposer() {
    if (!fichier) return;
    const formulaire = new FormData();
    formulaire.append("fichier", fichier);
    try {
      const reponse = await api<ApercuImport>(`/donnees/tables/${table}/import`, {
        method: "POST",
        body: formulaire,
      });
      setApercu(reponse);
      setConfirmees([]);
      setErreur(null);
      setResultat(null);
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Import impossible.");
    }
  }

  async function valider() {
    if (!apercu) return;
    try {
      const reponse = await api<{ version: Version | null }>(
        `/donnees/imports/${apercu.import}/valider`,
        json("POST", { auteur, commentaire, confirmees }),
      );
      setResultat(
        reponse.version
          ? `Version ${reponse.version.id_version} enregistrée : ${nombre(reponse.version.nb_lignes_ajoutees)} lignes ajoutées, ${nombre(reponse.version.nb_lignes_modifiees)} modifiées.`
          : "Aucune ligne importée : aucune version créée.",
      );
      setApercu(null);
      onModifie();
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Validation impossible.");
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
      <CarteFlottante
        titre="1. Télécharger le modèle, 2. le modifier dans Excel, 3. le déposer"
        source="Le modèle contient les données actuelles, un mode d'emploi et les fourchettes de contrôle (RG-19)."
      >
        <div className="grid gap-4">
          <Selection
            libelle="Table"
            valeur={table}
            options={tables.map((t) => ({ valeur: t.table, libelle: t.libelle }))}
            onChange={(v) => {
              setTable(v);
              setApercu(null);
            }}
          />
          <a
            href={`/api/donnees/tables/${table}/modele.xlsx`}
            className="inline-flex w-fit items-center gap-2 rounded-bouton border border-line bg-card px-4 py-2 text-secondaire font-medium text-ink shadow-douce"
            download
          >
            <DownloadSimpleIcon size={16} aria-hidden="true" />
            Télécharger le modèle Excel
          </a>
          <label className="grid gap-1 text-libelle text-muted">
            Classeur modifié (.xlsx)
            <input
              type="file"
              accept=".xlsx"
              onChange={(e) => {
                setFichier(e.target.files?.[0] ?? null);
              }}
              className="text-secondaire text-ink"
            />
          </label>
          <Bouton
            disabled={!fichier}
            icone={<UploadSimpleIcon size={16} />}
            onClick={() => {
              void deposer();
            }}
          >
            Déposer et prévisualiser
          </Bouton>
          {erreur ? <MessageErreur message={erreur} /> : null}
          {resultat ? <p className="text-secondaire text-ink">{resultat}</p> : null}
        </div>
      </CarteFlottante>
      {apercu ? (
        <CarteFlottante
          titre={`Prévisualisation : ${nombre(apercu.ajoutees.length)} ajoutées, ${nombre(apercu.modifiees.length)} modifiées, ${nombre(apercu.rejetees.length)} rejetées, ${nombre(apercu.a_confirmer.length)} à confirmer`}
          source="Lignes numérotées comme dans Excel. Rien n'est enregistré avant la validation."
        >
          <div className="grid gap-4 text-secondaire">
            <Liste titre="Lignes ajoutées" lignes={apercu.ajoutees} />
            <Liste titre="Lignes modifiées" lignes={apercu.modifiees} />
            {apercu.rejetees.length ? (
              <div>
                <h3 className="font-texte text-secondaire font-medium tracking-normal">
                  Lignes rejetées
                </h3>
                <ul className="mt-1 grid gap-1">
                  {apercu.rejetees.map((r) => (
                    <li key={r.ligne}>
                      Ligne {r.ligne} : {r.motif}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {apercu.a_confirmer.length ? (
              <fieldset>
                <legend className="font-medium">À confirmer (RG-19)</legend>
                {apercu.a_confirmer.map((r) => (
                  <label key={r.ligne} className="mt-1 flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={confirmees.includes(r.ligne)}
                      onChange={(e) => {
                        setConfirmees((c) =>
                          e.target.checked ? [...c, r.ligne] : c.filter((n) => n !== r.ligne),
                        );
                      }}
                    />
                    Ligne {r.ligne} : {r.motif}
                  </label>
                ))}
              </fieldset>
            ) : null}
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                void valider();
              }}
            >
              <Champ libelle="Auteur" valeur={auteur} onChange={setAuteur} />
              <Champ
                libelle="Commentaire"
                valeur={commentaire}
                onChange={setCommentaire}
                largeur="w-72"
              />
              <Bouton type="submit">Valider l'import</Bouton>
            </form>
          </div>
        </CarteFlottante>
      ) : null}
    </div>
  );
}

function Liste({ titre, lignes }: { titre: string; lignes: number[] }) {
  if (!lignes.length) return null;
  return (
    <p>
      <span className="font-medium">{titre} :</span> {lignes.join(", ")}
    </p>
  );
}

// --- Prix et coûts (UC-DAT-07) -------------------------------------------------------------

function OngletPrix({ onModifie }: { onModifie: () => void }) {
  const prix = useApi<PrixApi>("/donnees/prix");
  const residus = useApi<{ residus: { code: string; nom: string }[] }>("/potentiel/indicateurs");
  const vide = {
    date: aujourdhui(),
    produit: "",
    code_province: "NATIONAL",
    prix: "",
    unite: "",
    source: "",
    auteur: "",
    note: "",
  };
  const [champs, setChamps] = useState(vide);
  const [confirmer, setConfirmer] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const changer = (cle: keyof typeof vide) => (v: string) => {
    setChamps((c) => ({ ...c, [cle]: v }));
  };

  async function ajouter() {
    try {
      await api("/donnees/prix", json("POST", { ...champs, confirmer }));
      setChamps(vide);
      setConfirmer(false);
      setErreur(null);
      prix.recharger();
      onModifie();
    } catch (e) {
      if (e instanceof ErreurApi && e.confirmationRequise) setConfirmer(true);
      setErreur(e instanceof ErreurApi ? e.message : "Saisie impossible.");
    }
  }

  const colonnes: Colonne[] = [
    { cle: "date", libelle: "Date" },
    { cle: "produit", libelle: "Produit" },
    { cle: "code_province", libelle: "Zone" },
    { cle: "prix", libelle: "Prix" },
    { cle: "unite", libelle: "Unité" },
    { cle: "source", libelle: "Source" },
    { cle: "auteur", libelle: "Auteur" },
  ];

  return (
    <div className="grid gap-6">
      <CarteFlottante
        titre="Saisir un prix observé (grignons, paille, gazole…)"
        source="Le prix s'ajoute à l'historique ; le plus récent est utilisé dans les calculs, les anciens restent consultables. Un prix de résidu en DH/t (masse brute) remplace le prix d'achat de concurrence.csv dans le coût livré, pour sa zone."
      >
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void ajouter();
          }}
        >
          <Champ
            libelle="Date"
            type="date"
            valeur={champs.date}
            onChange={changer("date")}
            largeur="w-40"
          />
          <Champ
            libelle="Produit (code du résidu ou gazole)"
            valeur={champs.produit}
            onChange={changer("produit")}
            largeur="w-56"
            liste="produits-prix"
          />
          <datalist id="produits-prix">
            {(residus.donnees?.residus ?? []).map((r) => (
              <option key={r.code} value={r.code}>
                {r.nom}
              </option>
            ))}
            <option value="gazole">Gazole</option>
          </datalist>
          <Champ
            libelle="Zone (NATIONAL ou province)"
            valeur={champs.code_province}
            onChange={changer("code_province")}
          />
          <Champ libelle="Prix" valeur={champs.prix} onChange={changer("prix")} largeur="w-28" />
          <Champ
            libelle="Unité (DH/t, DH/L…)"
            valeur={champs.unite}
            onChange={changer("unite")}
            largeur="w-36"
          />
          <Champ
            libelle="Source"
            valeur={champs.source}
            onChange={changer("source")}
            largeur="w-64"
          />
          <Champ
            libelle="Auteur"
            valeur={champs.auteur}
            onChange={changer("auteur")}
            largeur="w-40"
          />
          <Bouton type="submit">{confirmer ? "Confirmer le prix" : "Ajouter le prix"}</Bouton>
        </form>
        {erreur ? (
          <div className="mt-3">
            <MessageErreur message={erreur} />
          </div>
        ) : null}
      </CarteFlottante>
      <CarteFlottante
        titre={
          prix.donnees?.historique.length
            ? `${nombre(prix.donnees.historique.length)} prix observés, ${nombre(prix.donnees.courants.length)} prix courants`
            : "Aucun prix observé saisi"
        }
      >
        {prix.donnees?.historique.length ? (
          <div className="grid gap-6">
            <TableauEditable
              libelle="Prix courants"
              colonnes={colonnes}
              lignes={prix.donnees.courants}
            />
            <TableauEditable
              libelle="Historique des prix"
              colonnes={colonnes}
              lignes={prix.donnees.historique}
            />
          </div>
        ) : (
          <p className="text-secondaire text-muted">
            Les prix d'achat livrés (PAR-14) sont des valeurs de littérature ; saisissez ici les
            prix relevés par l'équipe.
          </p>
        )}
      </CarteFlottante>
    </div>
  );
}

// --- Versions (UC-DAT-08) ------------------------------------------------------------------

function OngletVersions({
  tables,
  onModifie,
  cle,
}: {
  tables: TableInfo[];
  onModifie: () => void;
  cle: number;
}) {
  const versions = useApi<Version[]>(`/donnees/versions?_=${String(cle)}`);
  const liste = useMemo(() => versions.donnees ?? [], [versions.donnees]);
  const [avant, setAvant] = useState("");
  const [apres, setApres] = useState("");
  const [table, setTable] = useState("production");
  const [comparaison, setComparaison] = useState<Comparaison | null>(null);
  const [auteur, setAuteur] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    if (liste.length >= 2 && !avant) {
      setAvant(liste[1]?.id_version ?? "");
      setApres(liste[0]?.id_version ?? "");
    }
  }, [liste, avant]);

  async function comparer() {
    try {
      setComparaison(
        await api<Comparaison>(
          `/donnees/versions/${avant}/comparer/${apres}?table=${encodeURIComponent(table)}`,
        ),
      );
      setErreur(null);
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Comparaison impossible.");
    }
  }

  async function restaurer(id: string) {
    try {
      await api(
        `/donnees/versions/${id}/restaurer`,
        json("POST", { auteur, commentaire: `restauration de la version ${id}` }),
      );
      setErreur(null);
      onModifie();
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Restauration impossible.");
    }
  }

  const options = liste.map((v) => ({
    valeur: v.id_version,
    libelle: `${v.id_version} · ${date(v.date)}`,
  }));

  return (
    <div className="grid gap-6">
      {erreur ? <MessageErreur message={erreur} /> : null}
      <CarteFlottante
        titre={`${nombre(liste.length)} versions des données`}
        source="Une restauration crée une nouvelle version : rien n'est écrasé (RG-17)."
      >
        <div className="mb-4">
          <Champ
            libelle="Auteur de la restauration"
            valeur={auteur}
            onChange={setAuteur}
            requis={false}
          />
        </div>
        <ul className="grid gap-2">
          {liste.map((v) => (
            <li
              key={v.id_version}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-2 last:border-0"
            >
              <div className="text-secondaire">
                <span className="font-medium">{v.id_version}</span> · {date(v.date)} · {v.auteur} ·{" "}
                {v.commentaire}
                <p className="text-libelle text-muted">
                  {v.tables_modifiees.join(", ")} : {nombre(v.nb_lignes_ajoutees)} ajoutées,{" "}
                  {nombre(v.nb_lignes_modifiees)} modifiées, {nombre(v.nb_lignes_supprimees)}{" "}
                  supprimées
                  {v.restauration_de ? ` · restauration de ${v.restauration_de}` : ""}
                </p>
              </div>
              {v.id_version !== liste[0]?.id_version ? (
                <Bouton
                  variante="secondaire"
                  disabled={!auteur.trim()}
                  onClick={() => {
                    void restaurer(v.id_version);
                  }}
                >
                  Restaurer {v.id_version}
                </Bouton>
              ) : (
                <span className="text-libelle text-muted">version active</span>
              )}
            </li>
          ))}
        </ul>
      </CarteFlottante>
      {liste.length >= 2 ? (
        <CarteFlottante titre="Comparer deux versions">
          <div className="flex flex-wrap items-end gap-4">
            <Selection
              libelle="Version de départ"
              valeur={avant}
              options={options}
              onChange={setAvant}
            />
            <Selection
              libelle="Version d'arrivée"
              valeur={apres}
              options={options}
              onChange={setApres}
            />
            <Selection
              libelle="Table"
              valeur={table}
              options={tables.map((t) => ({ valeur: t.table, libelle: t.libelle }))}
              onChange={setTable}
            />
            <Bouton
              variante="secondaire"
              onClick={() => {
                void comparer();
              }}
            >
              Comparer
            </Bouton>
          </div>
          {comparaison ? <Differences comparaison={comparaison} /> : null}
        </CarteFlottante>
      ) : null}
    </div>
  );
}

function Differences({ comparaison }: { comparaison: Comparaison }) {
  const colonnes = (lignes: Ligne[]): Colonne[] =>
    Object.keys(lignes[0] ?? {})
      .filter((c) => !["url", "document", "note", "soustraites"].includes(c))
      .slice(0, 9)
      .map((c) => ({ cle: c, libelle: c.replaceAll("_", " ") }));
  const bloc = (titre: string, lignes: Ligne[]): ReactNode =>
    lignes.length ? (
      <div className="mt-4">
        <h3 className="font-texte text-secondaire font-medium tracking-normal">
          {titre} ({nombre(lignes.length)})
        </h3>
        <TableauEditable libelle={titre} colonnes={colonnes(lignes)} lignes={lignes.slice(0, 50)} />
      </div>
    ) : null;
  return (
    <div>
      {comparaison.ajoutees.length +
        comparaison.modifiees.length +
        comparaison.supprimees.length ===
      0 ? (
        <p className="mt-4 text-secondaire text-muted">Aucune différence pour cette table.</p>
      ) : null}
      {bloc("Avant modification", comparaison.avant)}
      {bloc("Après modification", comparaison.modifiees)}
      {bloc("Lignes ajoutées", comparaison.ajoutees)}
      {bloc("Lignes supprimées", comparaison.supprimees)}
    </div>
  );
}

// --- Statut par province et rapport de contrôle --------------------------------------------

const COULEUR_STATUT: Record<string, string> = {
  réelle: couleurs.green[700],
  estimée: couleurs.green[200],
  absente: couleurs.line,
};

function OngletControle() {
  const statut = useApi<StatutProvinces>("/donnees/statut-provinces");
  const contours = useApi<GeoJsonContours>("/referentiel/provinces/geojson");
  const remplissage = useMemo(
    () =>
      Object.fromEntries(
        (statut.donnees?.provinces ?? []).map((p) => [
          p.code_province,
          COULEUR_STATUT[p.statut] ?? couleurs.line,
        ]),
      ),
    [statut.donnees],
  );
  const s = statut.donnees;
  return (
    <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
      <CarteFlottante
        titre={
          s
            ? `${nombre(s.resume.réelle ?? 0)} provinces avec une production publiée à leur maille, ${nombre(s.resume.estimée ?? 0)} estimées`
            : "Statut de la production par province"
        }
        source="Source : production préparée (SRC-18, SRC-03, SRC-01, répartition CROPGRIDS SRC-04) · contours © Haut-Commissariat au Plan"
      >
        <CarteSatellite
          contours={contours.donnees}
          remplissage={remplissage}
          libelle="Carte du statut des données de production par province"
          className="relative h-[520px] rounded-bouton"
        />
        <ul className="mt-3 flex gap-5 text-libelle text-ink" aria-label="Légende">
          {(["réelle", "estimée", "absente"] as const).map((cle) => (
            <li key={cle} className="flex items-center gap-1.5">
              <span
                className="h-3 w-3 rounded-segment"
                style={{ backgroundColor: COULEUR_STATUT[cle] }}
              />
              {cle === "réelle"
                ? "Publiée à la maille provinciale"
                : cle === "estimée"
                  ? "Estimée (RG-04)"
                  : "Absente"}
            </li>
          ))}
        </ul>
      </CarteFlottante>
      <CarteFlottante
        titre="Rapport de contrôle de la dernière préparation"
        source="Lignes valides, rejetées, doublons, aberrantes et non utilisées par source ; contrôles des sommes (UC-DAT-02, UC-DAT-04)."
      >
        <a
          href="/api/donnees/rapport"
          target="_blank"
          rel="noreferrer"
          className={`inline-flex rounded-bouton px-4 py-2 text-secondaire font-medium shadow-douce ${STYLE_BOUTON_PRIMAIRE}`}
        >
          Ouvrir le rapport de contrôle
        </a>
        {s ? (
          <ul className="mt-4 grid max-h-[420px] gap-1 overflow-y-auto text-libelle">
            {s.provinces.map((p) => (
              <li
                key={p.code_province}
                className="flex justify-between gap-3 border-b border-line py-1"
              >
                <span>{p.nom_fr}</span>
                <span className="text-muted">
                  {p.statut} · {p.sources.join(", ")}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </CarteFlottante>
    </div>
  );
}

// --- Manifeste des sources (RG-05) ---------------------------------------------------------

function OngletSources() {
  const sources = useApi<SourceApi[]>("/donnees/sources");
  return (
    <CarteFlottante
      titre={
        sources.donnees
          ? `${nombre(sources.donnees.length)} sources inscrites au manifeste`
          : "Sources"
      }
      source="Manifeste data/sources.yaml : adresse, licence, date de téléchargement et empreinte de chaque fichier (RG-05)."
    >
      <TableauEditable
        libelle="Manifeste des sources"
        colonnes={[
          { cle: "source_id", libelle: "Identifiant" },
          { cle: "titre", libelle: "Titre" },
          { cle: "licence", libelle: "Licence" },
          { cle: "parent", libelle: "Source parente" },
        ]}
        lignes={(sources.donnees ?? []) as unknown as Ligne[]}
      />
    </CarteFlottante>
  );
}
