import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import App from "./App";
import "./index.css";
import { symbole } from "./theme/logo";

// Icône de l'onglet : symbole d'Atlantic Biochar (SVG officiel dès qu'il sera déposé).
const icone = document.createElement("link");
icone.rel = "icon";
icone.href = symbole;
document.head.appendChild(icone);

const racine = document.getElementById("root");
if (!racine) {
  throw new Error("Élément #root introuvable dans index.html.");
}

createRoot(racine).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
