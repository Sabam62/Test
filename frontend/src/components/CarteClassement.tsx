import { useMemo } from "react";
import { useNavigate } from "react-router";

import type { GeoJsonContours } from "../lib/api";
import type { ClassementApi } from "../lib/decision";
import { nombre } from "../lib/format";
import { useApi } from "../lib/useApi";
import CarteSatellite, { type Epingle } from "../map/CarteSatellite";
import { classesRang, couleurs, texteClassesRang } from "../theme/couleurs";
import BandeauPartiel from "./BandeauPartiel";
import CarteFlottante from "./CarteFlottante";

type Classe = Extract<ClassementApi, { bloque: false }>;

/** Sites dont le numéro de rang est écrit dans l'épingle. */
const RANGS_NUMEROTES = 5;

/**
 * Carte des sites colorée par rang (section 11.2.3) : une épingle par site, de la couleur de sa
 * classe de rang ; info-bulle avec le rang et le score ; un clic ouvre la fiche du site. Les
 * sites exclus restent visibles en gris, avec leur motif (RG-09).
 */
export default function CarteClassement({ c }: { c: Classe }) {
  const contours = useApi<GeoJsonContours>("/referentiel/provinces/geojson");
  const naviguer = useNavigate();
  const epingles = useMemo<Epingle[]>(
    () => [
      ...c.exclus.map((e) => ({
        id: e.id_site,
        lon: e.lon,
        lat: e.lat,
        libelle: e.nom,
        couleur: couleurs.muted,
        bulle: `exclu : ${e.motif}`,
      })),
      ...[...c.classement].reverse().map((s) => ({
        id: s.id_site,
        lon: s.lon,
        lat: s.lat,
        libelle: s.nom,
        couleur: classesRang[s.classe] ?? couleurs.muted,
        bulle: `rang ${nombre(s.rang)} · score ${nombre(s.score, 3, 3)}`,
        ...(s.rang <= RANGS_NUMEROTES
          ? { etiquette: String(s.rang), couleurTexte: texteClassesRang[s.classe] ?? couleurs.ink }
          : {}),
      })),
    ],
    [c],
  );
  return (
    <CarteFlottante
      titre={`Carte des ${nombre(c.classement.length)} sites classés, colorés par rang`}
      sousTitre="Les 5 premiers portent leur numéro ; survolez une épingle pour son rang et son score, un clic ouvre la fiche du site"
      source="Sites : chefs-lieux OpenStreetMap (SRC-06), agropoles et sites ajoutés · contours © Haut-Commissariat au Plan"
    >
      <CarteSatellite
        contours={contours.donnees}
        epingles={epingles}
        libelle="Carte des sites candidats colorés par rang"
        className="relative h-[520px] rounded-bouton"
        coinZoom="top-right"
        onEpingle={(id) => {
          void naviguer(`/fiche-site?site=${encodeURIComponent(id)}`);
        }}
      >
        <div className="absolute left-3 top-3">
          <BandeauPartiel
            utilises={c.partiel.utilises}
            actifs={c.partiel.actifs}
            retires={c.retires}
            libelles={c.libelles_retires}
            objet="classement des sites"
            compact
          />
        </div>
      </CarteSatellite>
      <ul
        className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-libelle text-ink"
        aria-label="Légende des rangs"
      >
        {c.legende_rangs.map((l) => (
          <li key={l.classe} className="flex items-center gap-1.5">
            <span
              className="h-3 w-3 rounded-full border border-line"
              style={{ backgroundColor: classesRang[l.classe] ?? couleurs.muted }}
            />
            <span className="chiffres">
              rangs {nombre(l.rang_min)} à {nombre(l.rang_max)}
            </span>
          </li>
        ))}
        {c.exclus.length ? (
          <li className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full" style={{ backgroundColor: couleurs.muted }} />
            exclus ({nombre(c.exclus.length)})
          </li>
        ) : null}
      </ul>
    </CarteFlottante>
  );
}
