// Éléments d'affichage communs à la confirmation et au suivi.
import { formatDate, formatMoney, h } from "../../assets/js/ui.js";

const fait = (label, valeur, large) => h("div", { class: "fact" + (large ? " wide" : "") }, h("span", {}, label), h("strong", {}, valeur || "—"));

// `f` = informations de la réclamation (formulaire de dépôt ou réponse de suivi)
export function faitsPublics(f) {
  return h("div", { class: "facts" },
    fait("Raison sociale", f.contrib), fait("Identifiant fiscal", f.ifn),
    fait("Type d'impôt", f.tax), fait("Montant contesté", formatMoney(Number(f.montant))),
    fait("Date de mise en recouvrement", f.date_mer ? formatDate(f.date_mer) : ""), fait("Période concernée", f.periode),
    fait("Objet", f.motif, true));
}
