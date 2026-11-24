import { couleursAxes, type Axe } from "../theme";
import { nombre } from "../lib/format";

const SEGMENTS = 24;

interface Props {
  libelle: string;
  /** Part entre 0 et 1, calculée par l'API. */
  part: number;
  axe: Axe;
}

/** 24 segments arrondis dans la couleur de l'axe, pourcentage aligné à droite (section 12.5). */
export default function BarresSegmentees({ libelle, part, axe }: Props) {
  const pleins = Math.round(Math.max(0, Math.min(1, part)) * SEGMENTS);
  return (
    <div>
      <div className="flex items-baseline justify-between text-libelle">
        <span className="text-ink">{libelle}</span>
        <span className="chiffres text-ink">{nombre(part * 100)} %</span>
      </div>
      <div
        className="mt-1 flex gap-0.5"
        role="meter"
        aria-label={libelle}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(part * 100)}
      >
        {Array.from({ length: SEGMENTS }, (_, i) => (
          <span
            key={i}
            className="h-2.5 flex-1 rounded-segment"
            style={{
              backgroundColor: couleursAxes[axe],
              opacity: i < pleins ? 1 : 0.18,
            }}
          />
        ))}
      </div>
    </div>
  );
}
