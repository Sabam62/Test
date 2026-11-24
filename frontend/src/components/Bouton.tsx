import { STYLE_BOUTON_PRIMAIRE, STYLE_BOUTON_SECONDAIRE } from "../theme/boutons";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Variante = "primaire" | "secondaire";

const STYLES: Record<Variante, string> = {
  primaire: STYLE_BOUTON_PRIMAIRE,
  secondaire: STYLE_BOUTON_SECONDAIRE,
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  icone?: ReactNode;
}

/** Bouton de la section 12.5 : primaire vert foncé de la marque, secondaire blanc bordé. */
const Bouton = forwardRef<HTMLButtonElement, Props>(function Bouton(
  { variante = "primaire", icone, className = "", children, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`inline-flex items-center gap-2 rounded-bouton px-4 py-2 text-secondaire font-medium shadow-douce transition-colors duration-courte disabled:cursor-not-allowed disabled:opacity-50 ${STYLES[variante]} ${className}`}
      {...props}
    >
      {icone}
      {children}
    </button>
  );
});

export default Bouton;
