import { classesRang, couleurs, marque, texteClassesRang } from "../theme/couleurs";

/** Rapport de contraste WCAG 2.1 entre deux couleurs hexadécimales. */
function contraste(a: string, b: string): number {
  const luminance = (hexa: string) => {
    const canaux = [1, 3, 5].map((i) => parseInt(hexa.slice(i, i + 2), 16) / 255);
    const [r = 0, v = 0, b2 = 0] = canaux.map((c) =>
      c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
    );
    return 0.2126 * r + 0.7152 * v + 0.0722 * b2;
  };
  const [clair, sombre] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((clair ?? 0) + 0.05) / ((sombre ?? 0) + 0.05);
}

const TEXTE = 4.5; // WCAG AA, texte courant
const GRAPHIQUE = 3; // WCAG AA, éléments graphiques et texte de grande taille

describe("contrastes des couleurs de la marque (section 12.3)", () => {
  it.each([
    ["texte vert foncé sur carte blanche", marque.fonce, couleurs.card, TEXTE],
    ["texte blanc sur bouton primaire vert foncé", couleurs.card, marque.fonce, TEXTE],
    [
      "texte blanc sur bouton primaire survolé (green-900)",
      couleurs.card,
      couleurs.green[900],
      TEXTE,
    ],
    ["texte vert principal en mode sombre", marque.principal, couleurs.charcoal, TEXTE],
    ["texte vert clair en mode sombre", marque.clair, couleurs.charcoal, TEXTE],
    ["texte ink sur fond vert principal", couleurs.ink, marque.principal, TEXTE],
    ["repère vert principal sur carte blanche", marque.principal, couleurs.card, GRAPHIQUE],
    ["texte secondaire muted sur paper", couleurs.muted, couleurs.paper, TEXTE],
  ])("%s", (_, avant, fond, seuil) => {
    expect(contraste(avant, fond)).toBeGreaterThanOrEqual(seuil);
  });

  it.each([
    ["vert principal en texte sur paper", marque.principal, couleurs.paper],
    ["vert clair en texte sur carte blanche", marque.clair, couleurs.card],
    ["texte blanc sur fond vert principal", couleurs.card, marque.principal],
  ])("%s est exclu (contraste insuffisant)", (_, avant, fond) => {
    expect(contraste(avant, fond)).toBeLessThan(TEXTE);
  });
});

/** Écart de couleur ΔE76 dans l'espace CIELAB (illuminant D65). */
function ecartLab(a: string, b: string): number {
  const lab = (hexa: string) => {
    const [r = 0, v = 0, b2 = 0] = [1, 3, 5]
      .map((i) => parseInt(hexa.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    const x = (0.4124 * r + 0.3576 * v + 0.1805 * b2) / 0.95047;
    const y = 0.2126 * r + 0.7152 * v + 0.0722 * b2;
    const z = (0.0193 * r + 0.1192 * v + 0.9505 * b2) / 1.08883;
    const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
    return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
  };
  const [p, q] = [lab(a), lab(b)];
  return Math.hypot(...p.map((c, i) => c - (q[i] ?? 0)));
}

const ECART_MINIMAL = 10; // ΔE76 nettement au-dessus du seuil de perception (≈ 2,3)

describe("classes de rang de la carte des sites (section 11.2.3)", () => {
  it("vont du vert foncé de la marque au vert très clair", () => {
    expect(classesRang[0]).toBe(marque.fonce);
    expect(classesRang).toHaveLength(5);
  });

  it.each(classesRang.slice(1).map((c, i) => [i + 1, classesRang[i] ?? "", c]))(
    "classes %i et voisine distinguables",
    (_, a, b) => {
      expect(ecartLab(a, b)).toBeGreaterThanOrEqual(ECART_MINIMAL);
    },
  );

  it.each(classesRang.map((c, i) => [i, c, texteClassesRang[i] ?? ""]))(
    "numéro de rang lisible sur la classe %i",
    (_, fond, texte) => {
      expect(contraste(texte, fond)).toBeGreaterThanOrEqual(TEXTE);
    },
  );
});
