import {
  CrosshairIcon,
  MapPinIcon,
  PathIcon,
  PlusIcon,
  RoadHorizonIcon,
  StackIcon,
  TrashIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react";
import type { FeatureCollection } from "geojson";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import Bouton from "../components/Bouton";
import CarteFlottante from "../components/CarteFlottante";
import EnTeteEcran from "../components/EnTeteEcran";
import MessageErreur from "../components/MessageErreur";
import ParametresManquants from "../components/ParametresManquants";
import TuileKPI from "../components/TuileKPI";
import { api, ErreurApi, json, type EntrepriseApi, type GeoJsonContours } from "../lib/api";
import { nombre } from "../lib/format";
import type {
  Bassin,
  Courbe,
  CourbeCalculee,
  EtatOsrm,
  Site,
  SitesLogistique,
} from "../lib/logistique";
import { useApi } from "../lib/useApi";
import CarteSatellite, { type Epingle } from "../map/CarteSatellite";
import { couleurs } from "../theme/couleurs";

const SITE_PAR_DEFAUT = "AGP-MEKNES";
const TYPES: Record<Site["type"], string> = {
  "chef-lieu": "Chef-lieu",
  agropole: "Agropole",
  utilisateur: "Site ajouté",
};

/** Lien vers l'endroit où saisir une valeur bloquante : Paramètres (entreprise ou technique) ou Données. */
function lienSaisie(texte: string, entreprise: string[]): { vers: string; libelle: string } {
  const parametre = /(PAR-\d+)/.exec(texte)?.[1];
  if (parametre && entreprise.includes(parametre))
    return { vers: `/parametres#${parametre}`, libelle: "Paramètres" };
  if (parametre) return { vers: `/parametres#technique-${parametre}`, libelle: "Paramètres" };
  if (texte.includes("Gisements")) return { vers: "/gisements", libelle: "Gisements" };
  return { vers: "/donnees", libelle: "Données" };
}

function emprise(
  collection: FeatureCollection | null | undefined,
): [number, number, number, number] | null {
  const coordonnees: number[][] = [];
  for (const entite of collection?.features ?? []) {
    const g = entite.geometry;
    if (g.type === "Point") coordonnees.push(g.coordinates);
    if (g.type === "Polygon") coordonnees.push(...(g.coordinates[0] ?? []));
  }
  if (!coordonnees.length) return null;
  const xs = coordonnees.map((c) => c[0] ?? 0);
  const ys = coordonnees.map((c) => c[1] ?? 0);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** Sites et logistique (UC-LOG-01 à 04) : sites candidats, courbe et bassin d'approvisionnement. */
export default function Sites() {
  const sites = useApi<SitesLogistique>("/logistique/sites");
  const etatOsrm = useApi<EtatOsrm>("/logistique/etat");
  const contours = useApi<GeoJsonContours>("/referentiel/provinces/geojson");
  const entreprise = useApi<EntrepriseApi>("/entreprise");
  const [choix, setChoix] = useState(SITE_PAR_DEFAUT);
  const [recherche, setRecherche] = useState("");
  const [clic, setClic] = useState<{ lon: number; lat: number } | null>(null);
  const courbe = useApi<Courbe>(`/logistique/sites/${encodeURIComponent(choix)}/courbe`);
  const bassin = useApi<Bassin>(`/logistique/sites/${encodeURIComponent(choix)}/bassin`);

  const liste = useMemo(() => sites.donnees?.sites ?? [], [sites.donnees]);
  const site = liste.find((s) => s.id_site === choix);
  const identifiantsEntreprise = (entreprise.donnees?.parametres ?? []).map((p) => p.identifiant);

  const epingles = useMemo<Epingle[]>(
    () =>
      liste.map((s) => ({
        id: s.id_site,
        lon: s.lon,
        lat: s.lat,
        libelle: s.nom,
        active: s.id_site === choix,
      })),
    [liste, choix],
  );
  const b = bassin.donnees;
  const points = useMemo<FeatureCollection | null>(() => {
    if (!b || b.bloque) return null;
    const plus = Math.max(
      1,
      ...b.gisements.features.map((f) => Number(f.properties?.tonnage_retenu ?? 0)),
    );
    return {
      ...b.gisements,
      features: b.gisements.features.map((f) => ({
        ...f,
        properties: { ...f.properties, poids: Number(f.properties?.tonnage_retenu ?? 0) / plus },
      })),
    };
  }, [b]);
  const zone = b && !b.bloque ? b.isodistance : null;
  const cadrage = useMemo(() => {
    if (zone) return emprise(zone);
    if (site)
      return [site.lon - 1.2, site.lat - 0.9, site.lon + 1.2, site.lat + 0.9] as [
        number,
        number,
        number,
        number,
      ];
    return null;
  }, [zone, site]);

  const c = courbe.donnees;
  const titre =
    c && !c.bloque && site
      ? c.atteignable
        ? `${site.nom} atteint ${nombre(c.capacite)} t MS/an à ${nombre(c.cout_moyen_k ?? 0)} DH/t MS en moyenne`
        : `${site.nom} n'atteint pas ${nombre(c.capacite)} t MS/an sous le prix plafond : il manque ${nombre(c.manque)} t MS`
      : c?.bloque && site
        ? `${nombre(liste.length)} sites candidats placés ; la courbe de ${site.nom} attend ${nombre(c.a_saisir.length)} valeur${c.a_saisir.length > 1 ? "s" : ""}`
        : "Sites et logistique";

  const filtres = liste.filter((s) =>
    `${s.nom} ${s.nom_province ?? ""}`.toLowerCase().includes(recherche.toLowerCase()),
  );

  return (
    <div className="mx-auto grid max-w-[1440px] grid-cols-[minmax(0,1fr)] gap-16 px-6 pb-24 pt-16">
      <EnTeteEcran
        titre={titre}
        phrase="Comparez les sites candidats par la distance routière, le coût livré de chaque gisement et le tonnage disponible sous votre prix plafond."
      />
      {sites.erreur ? <MessageErreur message={sites.erreur} /> : null}
      {sites.donnees?.methode === "vol_oiseau" && sites.donnees.message ? (
        <p
          role="status"
          className="flex items-start gap-2 rounded-carte border border-ember bg-card px-4 py-3 text-secondaire text-ink"
        >
          <WarningCircleIcon size={18} className="mt-0.5 shrink-0 text-ember" aria-hidden="true" />
          <span>
            {sites.donnees.message}.
            {etatOsrm.donnees ? (
              <>
                {" "}
                Démarrez OSRM : <code>{etatOsrm.donnees.commande}</code>
              </>
            ) : null}
          </span>
        </p>
      ) : null}

      <section aria-labelledby="titre-carte-sites" className="grid gap-4">
        <h2 id="titre-carte-sites" className="sr-only">
          Carte des sites candidats
        </h2>
        <div className="relative">
          <CarteSatellite
            contours={contours.donnees}
            epingles={epingles}
            points={points}
            zone={zone}
            cadrage={cadrage}
            libelle={`Carte des sites candidats${site ? `, bassin de ${site.nom}` : ""}`}
            className="relative h-[640px] rounded-carte"
            coinZoom="top-right"
            onEpingle={setChoix}
            onClicCarte={(lon, lat) => {
              setClic({ lon, lat });
            }}
          >
            <div className="absolute left-4 top-4 grid w-[320px] gap-3">
              <CarteFlottante
                titre={`${nombre(liste.length)} sites candidats`}
                sousTitre="Chefs-lieux, agropoles et sites ajoutés"
              >
                <input
                  type="search"
                  value={recherche}
                  onChange={(e) => {
                    setRecherche(e.target.value);
                  }}
                  placeholder="Rechercher un site ou une province"
                  aria-label="Rechercher un site"
                  className="w-full rounded-bouton border border-line bg-card px-2 py-1.5 text-secondaire"
                />
                <ul className="mt-2 grid max-h-[260px] gap-0.5 overflow-y-auto text-secondaire">
                  {filtres.map((s) => (
                    <li key={s.id_site}>
                      <button
                        type="button"
                        onClick={() => {
                          setChoix(s.id_site);
                        }}
                        aria-current={s.id_site === choix}
                        className={`flex w-full items-center justify-between gap-2 rounded-segment px-2 py-1 text-left hover:bg-paper ${s.id_site === choix ? "bg-paper font-medium" : ""}`}
                      >
                        <span className="truncate">{s.nom}</span>
                        <span className="shrink-0 text-libelle text-muted">
                          {s.impose ? "imposé · " : ""}
                          {TYPES[s.type]}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </CarteFlottante>
              <AjoutSite
                clic={clic}
                onAjout={(id) => {
                  setChoix(id);
                  setClic(null);
                }}
              />
            </div>
          </CarteSatellite>
        </div>
        <p className="text-source text-muted">
          Sources : chefs-lieux et routes OpenStreetMap (SRC-06, © contributeurs OpenStreetMap,
          ODbL), distances OSRM (SRC-07)
          {sites.donnees?.calibration
            ? `, coefficient de détour ${nombre(sites.donnees.calibration.coefficient, 2)} calibré le ${sites.donnees.calibration.date} sur ${nombre(sites.donnees.calibration.paires)} trajets`
            : ""}
          , points de rattachement au barycentre des cultures CROPGRIDS (SRC-04) · contours ©
          Haut-Commissariat au Plan
        </p>
      </section>

      {site ? (
        <FicheLogistique
          site={site}
          courbe={c}
          rayon={sites.donnees?.rayon_c3 ?? null}
          entreprise={identifiantsEntreprise}
          erreur={courbe.erreur}
        />
      ) : null}

      {sites.donnees?.a_completer.length ? (
        <CarteFlottante
          titre={`${nombre(sites.donnees.a_completer.length)} agropoles à placer`}
          sousTitre="Absentes de l'extrait OpenStreetMap : elles n'entrent dans aucun calcul tant que leurs coordonnées manquent (RG-14)"
        >
          <ul className="grid gap-1 text-secondaire">
            {sites.donnees.a_completer.map((a) => (
              <li key={a.id_site} className="flex gap-2">
                <MapPinIcon size={16} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
                <span>
                  {a.nom} ·{" "}
                  <span className="text-muted">
                    {a.ou_trouver} ; ajoutez-la par coordonnées ci-dessus
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </CarteFlottante>
      ) : null}
    </div>
  );
}

function FicheLogistique({
  site,
  courbe,
  rayon,
  entreprise,
  erreur,
}: {
  site: Site;
  courbe: Courbe | null;
  rayon: number | null;
  entreprise: string[];
  erreur: string | null;
}) {
  return (
    <section aria-labelledby="titre-site" className="grid gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 id="titre-site" className="text-titre-3">
            {site.nom}
          </h2>
          <p className="text-secondaire text-muted">
            {TYPES[site.type]}
            {site.nom_province ? ` · province de ${site.nom_province}` : ""}
            {site.impose ? " · site imposé (H4)" : ""} · {site.note}
          </p>
        </div>
        {site.type === "utilisateur" ? <RetraitSite site={site} /> : null}
      </div>
      {erreur ? <MessageErreur message={erreur} /> : null}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <TuileKPI
          icone={<StackIcon size={14} />}
          libelle={`Gisement mobilisable à moins de ${rayon === null ? "R" : nombre(rayon)} km (C3)`}
          valeur={
            site.tonnage_rayon_c3 === null
              ? "à compléter"
              : `${nombre(site.tonnage_rayon_c3)} t MS/an`
          }
        />
        <TuileKPI
          icone={<PathIcon size={14} />}
          libelle="Coût moyen pour atteindre K (C1)"
          valeur={
            courbe && !courbe.bloque && courbe.cout_moyen_k !== null
              ? `${nombre(courbe.cout_moyen_k)} DH/t MS`
              : "—"
          }
        />
        <TuileKPI
          icone={<PathIcon size={14} />}
          libelle="Coût marginal à K"
          valeur={
            courbe && !courbe.bloque && courbe.cout_marginal_k !== null
              ? `${nombre(courbe.cout_marginal_k)} DH/t MS`
              : "—"
          }
        />
        <TuileKPI
          icone={<RoadHorizonIcon size={14} />}
          libelle="Distance routière moyenne (C2)"
          valeur={
            courbe && !courbe.bloque && courbe.distance_moyenne_k !== null
              ? `${nombre(courbe.distance_moyenne_k)} km`
              : "—"
          }
        />
        <TuileKPI
          icone={<StackIcon size={14} />}
          libelle="Tonnage sous le prix plafond"
          valeur={courbe && !courbe.bloque ? `${nombre(courbe.tonnage_sous_plafond)} t MS/an` : "—"}
        />
      </div>
      <ParametresManquants
        requis={["PAR-01", "PAR-34", "PAR-37"]}
        pour="pour calculer le coût livré, la courbe et le bassin d'approvisionnement"
      />
      {courbe?.bloque ? (
        <CarteFlottante
          titre="Valeurs à saisir pour tracer la courbe d'approvisionnement"
          sousTitre="Aucune valeur n'est supposée à la place de l'entreprise (RG-14, RG-15)"
        >
          <ul className="grid gap-2 text-secondaire text-ink">
            {courbe.a_saisir.map((texte) => {
              const lien = lienSaisie(texte, entreprise);
              return (
                <li key={texte} className="flex gap-2 border-b border-line pb-2 last:border-0">
                  <WarningCircleIcon
                    size={16}
                    className="mt-0.5 shrink-0 text-ember"
                    aria-hidden="true"
                  />
                  <span>
                    {texte} ·{" "}
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
      {courbe && !courbe.bloque ? <GraphiqueCourbe courbe={courbe} /> : null}
      {courbe && !courbe.bloque && courbe.exclus.length ? (
        <CarteFlottante
          titre="Gisements non comptés dans la courbe"
          sousTitre="Chaque couple bloqué est exclu, jamais compté zéro (RG-06)"
        >
          <ul className="grid gap-1 text-libelle text-ink">
            {courbe.exclus.slice(0, 6).map((e) => (
              <li key={e.motif}>
                {nombre(e.couples)} couples ({e.residus.join(", ")}) : {e.motif}
              </li>
            ))}
          </ul>
        </CarteFlottante>
      ) : null}
    </section>
  );
}

function GraphiqueCourbe({ courbe }: { courbe: CourbeCalculee }) {
  const donnees = courbe.points.flatMap((p) => [
    { cumul: p.cumul - p.tonnage, cout: p.cout_livre, point: p },
    { cumul: p.cumul, cout: p.cout_livre, point: p },
  ]);
  return (
    <CarteFlottante
      titre={`Courbe d'approvisionnement : coût livré (DH/t MS) selon le tonnage cumulé (t MS/an)`}
      sousTitre={`${nombre(courbe.points.length)} gisements triés par coût livré croissant ; trait vertical : capacité K ; trait horizontal : prix plafond`}
      source={`Sources : gisements M (écran Gisements), distances ${courbe.methode === "osrm" ? "OSRM" : "à vol d'oiseau × détour"}, coût livré de la section 8.2 · statut le moins fiable de chaque couple au survol`}
    >
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={donnees} margin={{ top: 8, right: 16, bottom: 20, left: 8 }}>
            <CartesianGrid stroke={couleurs.line} vertical={false} />
            <XAxis
              dataKey="cumul"
              type="number"
              tickFormatter={(v: number) => nombre(v)}
              stroke={couleurs.muted}
              fontSize={12}
              label={{
                value: "Tonnage cumulé (t MS/an)",
                position: "insideBottom",
                offset: -12,
                fill: couleurs.muted,
                fontSize: 12,
              }}
            />
            <YAxis
              tickFormatter={(v: number) => nombre(v)}
              stroke={couleurs.muted}
              fontSize={12}
              label={{
                value: "Coût livré (DH/t MS)",
                angle: -90,
                position: "insideLeft",
                fill: couleurs.muted,
                fontSize: 12,
              }}
            />
            <Tooltip
              formatter={(v: number) => [`${nombre(v)} DH/t MS`, "Coût livré"]}
              labelFormatter={(v: number) => `${nombre(v)} t MS/an cumulées`}
            />
            <ReferenceLine x={courbe.capacite} stroke={couleurs.ink} strokeDasharray="4 3" />
            <ReferenceLine y={courbe.plafond} stroke={couleurs.muted} strokeDasharray="4 3" />
            <Line
              type="stepAfter"
              dataKey="cout"
              stroke={couleurs.ember}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </CarteFlottante>
  );
}

function AjoutSite({
  clic,
  onAjout,
}: {
  clic: { lon: number; lat: number } | null;
  onAjout: (id: string) => void;
}) {
  const [nom, setNom] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [auteur, setAuteur] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [ouvert, setOuvert] = useState(false);
  const latitude = clic ? clic.lat.toFixed(5) : lat;
  const longitude = clic ? clic.lon.toFixed(5) : lon;

  async function envoyer(evenement: FormEvent) {
    evenement.preventDefault();
    setErreur(null);
    try {
      const site = await api<Site>(
        "/logistique/sites",
        json("POST", {
          nom,
          auteur,
          lat: Number(latitude.replace(",", ".")),
          lon: Number(longitude.replace(",", ".")),
        }),
      );
      setNom("");
      setOuvert(false);
      onAjout(site.id_site);
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "L'ajout du site a échoué.");
    }
  }

  if (!ouvert && !clic)
    return (
      <Bouton
        variante="secondaire"
        icone={<PlusIcon size={16} aria-hidden="true" />}
        onClick={() => {
          setOuvert(true);
        }}
        className="justify-self-start"
      >
        Ajouter un site
      </Bouton>
    );
  return (
    <CarteFlottante
      titre="Ajouter un site"
      sousTitre={clic ? "Point choisi sur la carte" : "Par coordonnées, ou cliquez sur la carte"}
    >
      <form onSubmit={(e) => void envoyer(e)} className="grid gap-2 text-libelle text-muted">
        <label className="grid gap-1">
          Nom du site
          <input
            required
            value={nom}
            onChange={(e) => {
              setNom(e.target.value);
            }}
            className="rounded-bouton border border-line px-2 py-1 text-secondaire text-ink"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1">
            Latitude (°)
            <input
              required
              inputMode="decimal"
              value={latitude}
              onChange={(e) => {
                setLat(e.target.value);
              }}
              className="chiffres rounded-bouton border border-line px-2 py-1 text-secondaire text-ink"
            />
          </label>
          <label className="grid gap-1">
            Longitude (°)
            <input
              required
              inputMode="decimal"
              value={longitude}
              onChange={(e) => {
                setLon(e.target.value);
              }}
              className="chiffres rounded-bouton border border-line px-2 py-1 text-secondaire text-ink"
            />
          </label>
        </div>
        <label className="grid gap-1">
          Auteur
          <input
            required
            value={auteur}
            onChange={(e) => {
              setAuteur(e.target.value);
            }}
            className="rounded-bouton border border-line px-2 py-1 text-secondaire text-ink"
          />
        </label>
        {erreur ? <p className="text-secondaire text-ink">{erreur}</p> : null}
        <div className="flex gap-2">
          <Bouton type="submit" icone={<CrosshairIcon size={16} aria-hidden="true" />}>
            Ajouter
          </Bouton>
          <Bouton
            variante="secondaire"
            onClick={() => {
              setOuvert(false);
            }}
          >
            Fermer
          </Bouton>
        </div>
      </form>
    </CarteFlottante>
  );
}

function RetraitSite({ site }: { site: Site }) {
  const [erreur, setErreur] = useState<string | null>(null);
  return (
    <div className="grid justify-items-end gap-1">
      <Bouton
        variante="secondaire"
        icone={<TrashIcon size={16} aria-hidden="true" />}
        onClick={() => {
          api(`/logistique/sites/${encodeURIComponent(site.id_site)}`, json("DELETE")).catch(
            (e: unknown) => {
              setErreur(e instanceof ErreurApi ? e.message : "Le retrait a échoué.");
            },
          );
        }}
      >
        Retirer ce site
      </Bouton>
      {erreur ? <p className="text-libelle text-ink">{erreur}</p> : null}
    </div>
  );
}
