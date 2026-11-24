import { avecUnite, cellule, date, nombre } from "./format";

const espaceFine = "\u202f";

describe("format français", () => {
  it("sépare les milliers par une espace et met une virgule décimale", () => {
    expect(nombre(12400)).toBe(`12${espaceFine}400`);
    expect(nombre(0.69, 2)).toBe("0,69");
    expect(avecUnite(12400, "t")).toBe(`12${espaceFine}400\u00a0t`);
  });

  it("formate les dates et les cellules", () => {
    expect(date("2026-11-22T17:31:31")).toBe("22/11/2026");
    expect(date(null)).toBe("—");
    expect(cellule(null)).toBe("—");
    expect(cellule(true)).toBe("oui");
    expect(cellule(1027573.5, 0)).toBe(`1${espaceFine}027${espaceFine}574`);
  });
});
