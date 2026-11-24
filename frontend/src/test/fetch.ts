import { vi } from "vitest";

/**
 * Remplace `fetch` par des réponses enregistrées par route. Les corps sont fournis par chaque
 * test à partir des réponses réelles de l'API ou d'états vides ; aucune donnée inventée.
 */
export function simulerApi(reponses: Record<string, unknown>) {
  const appel = vi.fn((entree: RequestInfo | URL) => {
    const adresse =
      typeof entree === "string" ? entree : entree instanceof URL ? entree.href : entree.url;
    const chemin = adresse.replace(/^\/api/, "").split("?")[0] ?? "";
    if (!(chemin in reponses)) {
      return Promise.resolve(
        new Response(JSON.stringify({ erreur: `route non simulée : ${chemin}` }), { status: 404 }),
      );
    }
    return Promise.resolve(new Response(JSON.stringify(reponses[chemin]), { status: 200 }));
  });
  vi.stubGlobal("fetch", appel);
  return appel;
}
