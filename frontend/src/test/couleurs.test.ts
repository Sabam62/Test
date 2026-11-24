import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const RACINE = join(import.meta.dirname, "..");
const HEXA = /#[0-9a-fA-F]{3,8}\b/;
const COULEUR_CSS = /\brgba?\(|\bhsla?\(/;

function fichiers(dossier: string): string[] {
  return readdirSync(dossier).flatMap((nom: string) => {
    const chemin = join(dossier, nom);
    if (statSync(chemin).isDirectory()) return nom === "theme" ? [] : fichiers(chemin);
    return /\.(tsx?|css)$/.test(nom) && !nom.includes(".test.") ? [chemin] : [];
  });
}

describe("jetons de couleur", () => {
  it("aucune couleur écrite en dur hors de src/theme/", () => {
    const fautifs = fichiers(RACINE).flatMap((chemin) =>
      readFileSync(chemin, "utf-8")
        .split("\n")
        .map((ligne: string, i: number) => ({ ligne, i }))
        .filter(({ ligne }) => HEXA.test(ligne) || COULEUR_CSS.test(ligne))
        .map(({ ligne, i }) => `${relative(RACINE, chemin)}:${String(i + 1)} ${ligne.trim()}`),
    );
    expect(fautifs).toEqual([]);
  });
});
