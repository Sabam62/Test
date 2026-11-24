import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import urlWorker from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import {
  Map as CarteMapLibre,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
  type ErrorEvent,
  type GeoJSONSource,
  type StyleSpecification,
} from "maplibre-gl";
import { useEffect, useRef, useState, type ReactNode } from "react";

import type { GeoJsonContours } from "../lib/api";
import { couleurs } from "../theme/couleurs";

// Le worker de MapLibre (sources GeoJSON) est servi comme fichier de l'interface compilée.
setWorkerUrl(urlWorker);

/** Imagerie satellite Esri World Imagery (section 12.6), chargée par le navigateur. */
const TUILES_ESRI =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ATTRIBUTION_ESRI = "Imagerie © Esri, Maxar, Earthstar Geographics";
/**
 * Gestes « coopératifs » : la molette seule fait défiler la page ; Ctrl (⌘ sur Mac) + molette
 * zoome, comme les boutons + et −. Un message l'indique quand on essaie (section 12.6).
 */
const TEXTES_CARTE = {
  "CooperativeGesturesHandler.WindowsHelpText": "Ctrl + molette pour zoomer",
  "CooperativeGesturesHandler.MacHelpText": "⌘ + molette pour zoomer",
  "CooperativeGesturesHandler.MobileHelpText": "Utilisez deux doigts pour déplacer la carte",
  "NavigationControl.ZoomIn": "Zoomer",
  "NavigationControl.ZoomOut": "Dézoomer",
};

/** Emprise du Maroc (12 régions du RGPH 2024), en degrés : ouest, sud, est, nord. */
const EMPRISE_MAROC: [number, number, number, number] = [-17.3, 20.7, -0.9, 36.0];

export interface Epingle {
  lon: number;
  lat: number;
  libelle: string;
  /** Site sélectionné : épingle plus grande, étiquette visible. */
  active?: boolean;
  /** Identifiant renvoyé par `onEpingle` au clic. */
  id?: string;
  /** Couleur de l'épingle (jeton de couleur) ; ember par défaut. */
  couleur?: string;
  /** Texte de l'info-bulle au survol (rang, score…). */
  bulle?: string;
  /** Texte court affiché dans l'épingle (numéro de rang), et sa couleur. */
  etiquette?: string;
  couleurTexte?: string;
}

interface Props {
  contours: GeoJsonContours | null;
  /** Couleur de remplissage par code de province (jeton de couleur), par exemple un statut. */
  remplissage?: Record<string, string>;
  epingles?: Epingle[];
  libelle: string;
  className?: string;
  /** Coin des boutons + et − (en haut à droite sous la navigation de l'accueil). */
  coinZoom?: "top-right" | "bottom-left";
  /** Prévenu quand le fond satellite est indisponible (hors connexion) : fond paper. */
  onHorsLigne?: (horsLigne: boolean) => void;
  /** Clic sur une province (code du référentiel), si la carte a un remplissage. */
  onSelection?: (codeProvince: string) => void;
  /** Texte de l'info-bulle d'une province au survol ; null pour ne rien afficher. */
  infoBulle?: (codeProvince: string) => string | null;
  /** Clic sur une épingle (identifiant de l'épingle). */
  onEpingle?: (id: string) => void;
  /** Clic sur la carte hors épingle : coordonnées WGS 84 (ajout d'un site, UC-LOG-01). */
  onClicCarte?: (lon: number, lat: number) => void;
  /** Points (GeoJSON) dessinés en cercles verts, de rayon proportionnel à la propriété `poids`. */
  points?: FeatureCollection | null;
  /** Zone (GeoJSON polygone) dessinée en pointillés blancs : isodistance d'un bassin. */
  zone?: FeatureCollection | null;
  /** Emprise à cadrer avec un zoom fluide : ouest, sud, est, nord. */
  cadrage?: [number, number, number, number] | null;
  children?: ReactNode;
}

function style(satellite: boolean): StyleSpecification {
  return {
    version: 8,
    sources: satellite
      ? {
          satellite: {
            type: "raster",
            tiles: [TUILES_ESRI],
            tileSize: 256,
            attribution: ATTRIBUTION_ESRI,
          },
        }
      : {},
    layers: [
      { id: "fond", type: "background", paint: { "background-color": couleurs.paper } },
      ...(satellite ? [{ id: "satellite", type: "raster" as const, source: "satellite" }] : []),
    ],
  };
}

/**
 * Carte satellite plein cadre ; contours provinciaux en pointillés blancs, épingles ember.
 * Sans connexion (tuiles indisponibles), elle passe sur un fond paper avec les limites (12.6).
 */
export default function CarteSatellite({
  contours,
  remplissage,
  epingles = [],
  libelle,
  className = "relative",
  coinZoom = "bottom-left",
  onHorsLigne,
  onSelection,
  infoBulle,
  onEpingle,
  onClicCarte,
  points = null,
  zone = null,
  cadrage = null,
  children,
}: Props) {
  const conteneur = useRef<HTMLDivElement>(null);
  const carte = useRef<CarteMapLibre | null>(null);
  const [horsLigne, setHorsLigne] = useState(!navigator.onLine);
  const [indisponible, setIndisponible] = useState(false);
  // Rappels gardés à jour sans réenregistrer les gestionnaires de la carte.
  const rappels = useRef({ onSelection, infoBulle, onEpingle, onClicCarte });
  rappels.current = { onSelection, infoBulle, onEpingle, onClicCarte };

  useEffect(() => {
    onHorsLigne?.(horsLigne || indisponible);
  }, [horsLigne, indisponible, onHorsLigne]);

  useEffect(() => {
    if (!conteneur.current) return;
    let instance: CarteMapLibre;
    try {
      instance = new CarteMapLibre({
        container: conteneur.current,
        style: style(!horsLigne),
        bounds: EMPRISE_MAROC,
        attributionControl: false,
        interactive: true,
        cooperativeGestures: true,
        locale: TEXTES_CARTE,
      });
      instance.addControl(
        new NavigationControl({ showCompass: false, visualizePitch: false }),
        coinZoom,
      );
    } catch {
      setIndisponible(true);
      return;
    }
    carte.current = instance;
    // Niveau de zoom exposé sur le conteneur (lisible par les tests de bout en bout).
    const noterZoom = () => {
      conteneur.current?.setAttribute("data-zoom", instance.getZoom().toFixed(2));
    };
    instance.on("load", noterZoom);
    instance.on("zoomend", noterZoom);
    instance.on("click", (evenement) => {
      rappels.current.onClicCarte?.(evenement.lngLat.lng, evenement.lngLat.lat);
    });
    // La carte suit la taille de son conteneur (fenêtre redimensionnée, mise en page).
    const observateur = new ResizeObserver(() => {
      instance.resize();
    });
    observateur.observe(conteneur.current);
    instance.on("error", (evenement: ErrorEvent & { sourceId?: string }) => {
      const source = evenement.sourceId;
      if (source === "satellite") setHorsLigne(true);
    });
    return () => {
      observateur.disconnect();
      instance.remove();
      carte.current = null;
    };
  }, [horsLigne, coinZoom]);

  useEffect(() => {
    const instance = carte.current;
    if (!instance || !contours) return;
    const appliquer = () => {
      const donnees = {
        ...contours,
        features: (contours.features as { properties: Record<string, unknown> }[]).map((f) => ({
          ...f,
          properties: {
            ...f.properties,
            remplissage: remplissage?.[String(f.properties.code_province)] ?? couleurs.card,
          },
        })),
      } as unknown as FeatureCollection;
      const source = instance.getSource<GeoJSONSource>("provinces");
      if (source) {
        void source.setData(donnees);
        return;
      }
      instance.addSource("provinces", { type: "geojson", data: donnees });
      if (remplissage) {
        instance.addLayer({
          id: "provinces-remplissage",
          type: "fill",
          source: "provinces",
          paint: { "fill-color": ["get", "remplissage"], "fill-opacity": 0.55 },
        });
      }
      if (remplissage) {
        const bulle = new Popup({ closeButton: false, closeOnClick: false, offset: 8 });
        instance.on("mousemove", "provinces-remplissage", (evenement) => {
          const code = String(evenement.features?.[0]?.properties.code_province ?? "");
          const texte = code ? rappels.current.infoBulle?.(code) : null;
          instance.getCanvas().style.cursor = rappels.current.onSelection ? "pointer" : "";
          if (!texte) {
            bulle.remove();
            return;
          }
          const contenu = document.createElement("p");
          contenu.className = "whitespace-pre-line text-libelle text-ink";
          contenu.textContent = texte;
          bulle.setLngLat(evenement.lngLat).setDOMContent(contenu).addTo(instance);
        });
        instance.on("mouseleave", "provinces-remplissage", () => {
          instance.getCanvas().style.cursor = "";
          bulle.remove();
        });
        instance.on("click", "provinces-remplissage", (evenement) => {
          const code = String(evenement.features?.[0]?.properties.code_province ?? "");
          if (code) rappels.current.onSelection?.(code);
        });
      }
      instance.addLayer({
        id: "provinces-contours",
        type: "line",
        source: "provinces",
        paint: {
          "line-color": horsLigne ? couleurs.muted : couleurs.card,
          "line-width": 1.2,
          "line-dasharray": [2, 2],
        },
      });
    };
    if (instance.isStyleLoaded()) appliquer();
    else void instance.once("load", appliquer);
  }, [contours, remplissage, horsLigne]);

  useEffect(() => {
    const instance = carte.current;
    if (!instance) return;
    const marqueurs = epingles.map((e) => {
      const element = document.createElement(e.id ? "button" : "div");
      element.className = e.active
        ? "flex items-center gap-1.5 rounded-full border-2 border-white bg-ember py-0.5 pl-1 pr-2 text-libelle font-medium text-white shadow-douce"
        : "h-3 w-3 rounded-full border-2 border-white bg-ember";
      element.setAttribute("aria-label", e.bulle ? `${e.libelle} · ${e.bulle}` : e.libelle);
      element.title = e.bulle ? `${e.libelle}\n${e.bulle}` : e.libelle;
      if (e.couleur && !e.active) {
        element.className = e.etiquette
          ? "chiffres flex h-6 w-6 items-center justify-center rounded-full border-2 border-white text-libelle font-medium shadow-douce"
          : "h-3.5 w-3.5 rounded-full border-2 border-white shadow-douce";
        element.style.backgroundColor = e.couleur;
        if (e.etiquette) {
          element.textContent = e.etiquette;
          element.style.color = e.couleurTexte ?? "";
        }
      }
      if (e.active) {
        const point = document.createElement("span");
        point.className = "h-2 w-2 rounded-full bg-white";
        element.append(point, document.createTextNode(e.libelle));
      }
      if (e.id) {
        const id = e.id;
        element.addEventListener("click", (evenement) => {
          evenement.stopPropagation();
          rappels.current.onEpingle?.(id);
        });
      }
      return new Marker({ element }).setLngLat([e.lon, e.lat]).addTo(instance);
    });
    return () => {
      marqueurs.forEach((m) => m.remove());
    };
  }, [epingles]);

  // Couches du bassin : zone (isodistance) et gisements retenus, sous les épingles.
  useEffect(() => {
    const instance = carte.current;
    if (!instance) return;
    const vide: FeatureCollection = { type: "FeatureCollection", features: [] };
    const appliquer = () => {
      for (const [id, donnees] of [
        ["zone", zone ?? vide],
        ["points", points ?? vide],
      ] as const) {
        const source = instance.getSource<GeoJSONSource>(id);
        if (source) void source.setData(donnees);
        else instance.addSource(id, { type: "geojson", data: donnees });
      }
      if (!instance.getLayer("zone-contour")) {
        instance.addLayer({
          id: "zone-fond",
          type: "fill",
          source: "zone",
          paint: { "fill-color": couleurs.card, "fill-opacity": 0.08 },
        });
        instance.addLayer({
          id: "zone-contour",
          type: "line",
          source: "zone",
          paint: { "line-color": couleurs.card, "line-width": 1.5, "line-dasharray": [3, 2] },
        });
        instance.addLayer({
          id: "points-cercles",
          type: "circle",
          source: "points",
          paint: {
            "circle-color": couleurs.green[500],
            "circle-opacity": 0.85,
            "circle-stroke-color": couleurs.card,
            "circle-stroke-width": 1,
            "circle-radius": ["interpolate", ["linear"], ["get", "poids"], 0, 3, 1, 14],
          },
        });
      }
    };
    if (instance.isStyleLoaded()) appliquer();
    else void instance.once("load", appliquer);
  }, [points, zone, horsLigne]);

  useEffect(() => {
    const instance = carte.current;
    if (!instance || !cadrage) return;
    instance.fitBounds(cadrage, { padding: 48, duration: 200, maxZoom: 9 });
  }, [cadrage]);

  return (
    <div className={`overflow-hidden ${className}`}>
      <div ref={conteneur} className="absolute inset-0 bg-paper" role="img" aria-label={libelle} />
      {indisponible ? (
        <p className="absolute left-4 top-4 rounded-bouton bg-card px-3 py-2 text-libelle text-muted">
          La carte ne peut pas s'afficher dans ce navigateur (WebGL indisponible).
        </p>
      ) : null}
      {children}
      <p className="absolute bottom-1 right-2 rounded-segment bg-card px-1.5 text-source text-muted">
        {horsLigne ? "Fond hors connexion" : ATTRIBUTION_ESRI}
        {contours ? ` · Contours ${contours.attribution}` : ""}
      </p>
    </div>
  );
}
