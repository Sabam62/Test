/**
 * Format français des nombres et des dates (affichage seulement, aucun calcul métier).
 * Les milliers sont séparés par une espace fine insécable, la virgule est décimale.
 */

const formats = new Map<string, Intl.NumberFormat>();

function format(decimalesMax: number, decimalesMin: number): Intl.NumberFormat {
  const cle = `${String(decimalesMin)}-${String(decimalesMax)}`;
  let f = formats.get(cle);
  if (!f) {
    f = new Intl.NumberFormat("fr-FR", {
      maximumFractionDigits: decimalesMax,
      minimumFractionDigits: decimalesMin,
    });
    formats.set(cle, f);
  }
  return f;
}

/** 12400 → « 12 400 » ; 0.69 avec 2 décimales → « 0,69 ». */
export function nombre(valeur: number, decimales = 0, decimalesMin = 0): string {
  return format(decimales, Math.min(decimalesMin, decimales)).format(valeur);
}

/** Nombre suivi de son unité : 12400, « t » → « 12 400 t ». */
export function avecUnite(valeur: number, unite: string, decimales = 0): string {
  return `${nombre(valeur, decimales)}\u00a0${unite}`;
}

/** « 2026-11-22T17:31:31 » → « 22/11/2026 » ; une date absente donne « — ». */
export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short" }).format(d);
}

/** Valeur quelconque d'une cellule de tableau : nombre au format français, sinon texte. */
export function cellule(valeur: unknown, decimales = 2): string {
  if (valeur === null || valeur === undefined || valeur === "") return "—";
  if (typeof valeur === "number") return nombre(valeur, decimales);
  if (typeof valeur === "boolean") return valeur ? "oui" : "non";
  if (typeof valeur === "string") return valeur;
  return JSON.stringify(valeur);
}
