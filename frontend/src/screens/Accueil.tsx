import {
  ArrowRightIcon,
  DatabaseIcon,
  LeafIcon,
  MapPinIcon,
  StackIcon,
} from "@phosphor-icons/react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import CarteFlottante from "../components/CarteFlottante";
import BandeauPartiel from "../components/BandeauPartiel";
import ClassementSites from "../components/ClassementSites";
import MessageErreur from "../components/MessageErreur";
import ParametresManquants from "../components/ParametresManquants";
import type { EntrepriseApi, GeoJsonContours, StatutProvinces } from "../lib/api";
import { date, nombre } from "../lib/format";
import type { SyntheseGisements } from "../lib/potentiel";
import type { Resume } from "../lib/resume";
import type { ClassementApi } from "../lib/decision";
import { useApi } from "../lib/useApi";
import CarteSatellite from "../map/CarteSatellite";
import { logo, voileHero } from "../theme";

const ETAPES = [
  {
    titre: "Collecter",
    texte:
      "Productions par province (DRA, HCP, Open Data), résidus et facteurs sourcés, mis à jour depuis la page Données.",
  },
  {
    titre: "Calculer",
    texte:
      "Gisements, coût livré, bilan climat : chaque valeur garde sa source, son année et son statut.",
  },
  {
    titre: "Décider",
    texte:
      "Classement multicritère des sites selon les paramètres d'Atlantic Biochar, avec sa robustesse.",
  },
] as const;

/** Accueil (section 12.1) : hero cartographique, état des données, étapes, paramètres (RG-15). */
export default function Accueil() {
  const resume = useApi<Resume>("/donnees/resume");
  const statut = useApi<StatutProvinces>("/donnees/statut-provinces");
  const contours = useApi<GeoJsonContours>("/referentiel/provinces/geojson");
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const r = resume.donnees;
  const gisements = useApi<SyntheseGisements>("/potentiel/synthese");
  const totalT = gisements.donnees?.totaux.find((t) => t.indicateur === "T");
  const totalM = gisements.donnees?.totaux.find((t) => t.indicateur === "M");
  // Sans fond satellite (hors connexion), le hero passe sur fond paper : texte ink, sans voile.
  const [horsLigne, setHorsLigne] = useState(false);
  const texteHero = horsLigne ? "text-ink" : "text-white";

  return (
    <>
      <section aria-labelledby="titre-ecran" className="relative h-screen min-h-[680px]">
        <CarteSatellite
          contours={contours.donnees}
          libelle="Carte satellite du Maroc et contours des 75 provinces"
          className="absolute inset-0 [&_.maplibregl-ctrl-top-right]:mt-24"
          coinZoom="top-right"
          onHorsLigne={setHorsLigne}
        >
          {horsLigne ? null : (
            <div
              className="pointer-events-none absolute inset-0"
              style={{ backgroundImage: voileHero }}
            />
          )}
        </CarteSatellite>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 mx-auto flex max-w-[1440px] items-end justify-between gap-8 px-6 pb-12">
          <div className={`pointer-events-auto max-w-2xl ${texteHero}`}>
            <h1 id="titre-ecran" className="text-titre-1">
              {r
                ? `${nombre(r.provinces_avec_production)} provinces sur ${nombre(r.provinces_total)} ont une production sourcée`
                : "Lecture des données préparées…"}
            </h1>
            <p className={`mt-4 max-w-xl text-texte ${texteHero}`}>
              {r
                ? `${nombre(r.provinces_avec_valeur_reelle)} d'entre elles ont une statistique publiée à leur maille ; les autres sont estimées selon la RG-04 à partir d'un total régional ou national réel, campagnes ${r.campagne_min ?? "—"} à ${r.campagne_max ?? "—"}.`
                : "Choisissez où implanter une unité de biochar à partir des résidus agricoles du Maroc."}
            </p>
            <Link
              to="/decision"
              className="mt-6 inline-flex items-center gap-2 rounded-bouton bg-card px-4 py-2 text-secondaire font-medium text-ink shadow-douce"
            >
              Voir le classement
              <ArrowRightIcon size={16} aria-hidden="true" />
            </Link>
          </div>
          {r ? (
            <CarteFlottante
              className="pointer-events-auto w-80"
              titre="État des données"
              sousTitre={`${nombre(r.cultures.length)} cultures, ${nombre(r.valeurs_production)} valeurs de production`}
              source={`Sources : DRA et DPA (SRC-18), HCP (SRC-03), Open Data Maroc (SRC-01), CROPGRIDS (SRC-04) · version ${r.derniere_version?.id_version ?? "livrée"} du ${date(r.derniere_version?.date)}`}
            >
              <ul className="grid gap-2 text-secondaire">
                <Ligne
                  icone={<MapPinIcon size={16} />}
                  libelle="Provinces avec statistique publiée"
                  valeur={nombre(r.provinces_avec_valeur_reelle)}
                />
                <Ligne
                  icone={<StackIcon size={16} />}
                  libelle="Provinces estimées (RG-04)"
                  valeur={nombre(r.provinces_estimees_seulement)}
                />
                <Ligne
                  icone={<DatabaseIcon size={16} />}
                  libelle="Valeurs de référence à compléter"
                  valeur={nombre(r.a_completer_total)}
                />
                <Ligne
                  icone={<LeafIcon size={16} />}
                  libelle="Gisement théorique national (t MS/an)"
                  valeur={totalT?.total != null ? nombre(totalT.total) : "à compléter"}
                />
                <Ligne
                  icone={<LeafIcon size={16} />}
                  libelle="Gisement mobilisable national (t MS/an)"
                  valeur={totalM?.total != null ? nombre(totalM.total) : "à compléter"}
                />
              </ul>
            </CarteFlottante>
          ) : null}
        </div>
      </section>

      <div className="mx-auto max-w-[1440px] px-6">
        {resume.erreur ? (
          <div className="pt-8">
            <MessageErreur message={resume.erreur} />
          </div>
        ) : null}
        <section aria-labelledby="titre-etapes" className="py-24">
          <img
            src={logo}
            alt="Atlantic Biochar"
            className="mb-10 h-20 w-auto"
            width={160}
            height={80}
          />
          <div className="grid grid-cols-1 items-end gap-6 lg:grid-cols-[1.4fr_1fr]">
            <h2 id="titre-etapes" className="text-titre-2">
              De la statistique provinciale au choix du site, en trois étapes
            </h2>
            <p className="text-secondaire text-muted lg:text-right">
              Chaque étape s'appuie sur les données réelles de la page Données et sur les paramètres
              réglés par Atlantic Biochar.
            </p>
          </div>
          <ol className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-3">
            {ETAPES.map((etape, i) => (
              <li key={etape.titre} className="rounded-carte border border-line bg-card p-5">
                <span className="inline-flex items-center gap-2 text-libelle text-ink">
                  <span className="chiffres inline-flex h-5 w-5 items-center justify-center rounded-full bg-ember text-source font-medium text-ink">
                    {i + 1}
                  </span>
                  Étape {i + 1}
                </span>
                <h3 className="mt-10 font-texte text-texte font-medium tracking-normal">
                  {etape.titre}
                </h3>
                <p className="mt-1 text-secondaire text-muted">{etape.texte}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="titre-alertes" className="grid gap-6 pb-24 lg:grid-cols-2">
          <div>
            <h2 id="titre-alertes" className="text-titre-3">
              {statut.donnees
                ? `${nombre(statut.donnees.resume.estimée ?? 0)} provinces reposent sur des valeurs estimées`
                : "Alertes sur les données"}
            </h2>
            <p className="mt-2 text-secondaire text-muted">
              Une valeur estimée vient d'un total régional ou national réparti au prorata des
              surfaces CROPGRIDS ; la page Données montre la carte du statut par province et le
              rapport de contrôle.
            </p>
            <Link to="/donnees" className="mt-4 inline-flex text-secondaire underline">
              Ouvrir la page Données
            </Link>
          </div>
          {entreprise.donnees?.renseignement_requis ? (
            <ParametresManquants
              requis={entreprise.donnees.obligatoires}
              pour="pour obtenir le classement des sites"
            />
          ) : (
            <TroisPremiers />
          )}
        </section>
      </div>
    </>
  );
}

/** Les trois premiers sites du classement actuel et leur variation de rang (RG-16). */
function TroisPremiers() {
  const { donnees: c, erreur } = useApi<ClassementApi>("/decision/classement");
  if (erreur) return <MessageErreur message={erreur} />;
  if (!c || c.bloque) return null;
  return (
    <div className="grid gap-3">
      <h2 className="text-titre-3">
        {c.classement[0]
          ? `${c.classement[0].nom} est 1er sur ${nombre(c.classement.length)} sites`
          : "Classement des sites"}
      </h2>
      <BandeauPartiel
        utilises={c.partiel.utilises}
        actifs={c.partiel.actifs}
        retires={c.retires}
        libelles={c.libelles_retires}
        objet="classement des sites"
      />
      <ClassementSites
        lignes={c.classement}
        scoresAxes={c.scores_axes}
        libellesAxes={c.libelles_axes}
        limite={3}
      />
      <Link to="/decision" className="text-secondaire underline">
        Voir tout le classement
      </Link>
    </div>
  );
}

function Ligne({ icone, libelle, valeur }: { icone: ReactNode; libelle: string; valeur: string }) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="flex items-center gap-2 text-muted">
        <span aria-hidden="true">{icone}</span>
        {libelle}
      </span>
      <span className="chiffres font-medium text-ink">{valeur}</span>
    </li>
  );
}
