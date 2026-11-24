import type { ParametreEntrepriseApi } from "../lib/api";

interface Props {
  parametre: ParametreEntrepriseApi;
  valeur: string;
  onChange: (valeur: string) => void;
}

/**
 * Champ d'un paramètre de l'entreprise. L'identifiant du champ est celui du paramètre
 * (« PAR-01 ») : les états vides des autres écrans y renvoient par /parametres#PAR-01.
 */
export default function ChampParametre({ parametre, valeur, onChange }: Props) {
  const libelle = `${parametre.libelle} (${parametre.unite})`;
  const obligatoire = parametre.obligatoire && parametre.valeur === null;
  const etiquette = (
    <span className="flex items-center gap-2">
      {libelle}
      {parametre.obligatoire ? (
        <span className="rounded-full border border-line px-1.5 text-source text-ink">
          obligatoire
        </span>
      ) : null}
    </span>
  );
  const classeChamp = `chiffres rounded-bouton border bg-card px-2 py-1.5 text-texte text-ink scroll-mt-40 ${
    obligatoire ? "border-ember" : "border-line"
  }`;
  if (parametre.type === "choix") {
    return (
      <label className="grid gap-1 text-libelle text-muted">
        {etiquette}
        <select
          id={parametre.identifiant}
          value={valeur}
          onChange={(e) => {
            onChange(e.target.value);
          }}
          className={classeChamp}
        >
          <option value="">— à renseigner —</option>
          {parametre.choix.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <label className="grid gap-1 text-libelle text-muted">
      {etiquette}
      <input
        id={parametre.identifiant}
        inputMode={parametre.type === "nombre" ? "decimal" : "text"}
        list={parametre.choix.length ? `choix-${parametre.identifiant}` : undefined}
        value={valeur}
        placeholder={obligatoire ? "à renseigner" : ""}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        className={classeChamp}
      />
      {parametre.choix.length ? (
        <>
          <datalist id={`choix-${parametre.identifiant}`}>
            {parametre.choix.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
          <span className="text-source">
            Nombre en {parametre.unite.split(" ")[0]} ou classe : {parametre.choix.join(", ")}
          </span>
        </>
      ) : null}
    </label>
  );
}
