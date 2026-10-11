// Coquille du portail contribuable : en-tête, navigation, pied de page, assistant de saisie en 3 étapes.
// Aucune authentification : cette interface est publique et distincte de l'espace agents.
import { h, icon } from "./ui.js";

const NAV = [
  { id: "accueil", label: "Accueil", href: "index.html" },
  { id: "deposer", label: "Déposer une réclamation", href: "deposer.html" },
  { id: "suivi", label: "Suivre ma réclamation", href: "suivi.html" },
  { id: "assistant", label: "Assistant fiscal", href: "assistant.html" },
];

export function mountPortail({ page, title }) {
  document.title = `${title} · Portail contribuable GEIF`;
  const nav = h("nav", { class: "p-nav", id: "p-nav", "aria-label": "Navigation du portail" },
    NAV.map((n) => h("a", { href: n.href, "aria-current": n.id === page ? "page" : null }, n.label)),
    h("a", { class: "p-agents-mobile", href: "../app/connexion.html" }, "Espace agents"));
  const burger = h("button", { class: "p-burger", "aria-label": "Menu", "aria-expanded": "false", onclick: () => {
    const open = nav.classList.toggle("open");
    burger.setAttribute("aria-expanded", String(open));
  } }, icon("menu"));

  const header = h("header", { class: "p-header" }, h("div", { class: "p-header-inner" },
    h("a", { class: "p-brand", href: "index.html", "aria-label": "Portail du contribuable — accueil" },
      h("div", { class: "brand-mark" }, "G"),
      h("div", {}, h("strong", {}, "Portail du contribuable"), h("span", {}, "Direction Générale des Impôts"))),
    nav,
    h("a", { class: "p-agents", href: "../app/connexion.html" }, icon("shield"), "Espace agents"),
    burger));
  const main = h("main", { class: "p-main", id: "contenu" });
  const footer = h("footer", { class: "p-footer" }, h("div", {},
    h("strong", {}, "GEIF — Gestion électronique intelligente des flux fiscaux"),
    h("p", {}, "Prototype académique (PFA) : les informations saisies sont fictives. Ne déposez pas de données fiscales réelles.")));
  document.body.replaceChildren(
    h("a", { class: "skip-link", href: "#contenu" }, "Aller au contenu"), header, main, footer);
  return main;
}

// Barre d'avancement du dépôt (étape courante : 1, 2 ou 3)
export function assistantEtapes(courante) {
  const etapes = ["Informations", "Documents", "Confirmation"];
  return h("ol", { class: "wizard", "aria-label": "Étapes du dépôt" }, etapes.map((t, i) => {
    const n = i + 1;
    const etat = n < courante ? "done" : n === courante ? "current" : "todo";
    return h("li", { class: etat, "aria-current": etat === "current" ? "step" : null },
      h("span", { class: "wiz-dot" }, etat === "done" ? icon("check") : String(n)), h("span", { class: "wiz-label" }, t));
  }));
}

// État du dépôt conservé le temps de la session de l'onglet (jamais envoyé nulle part, effacé à la fin)
const CLE = "geif_depot";
export const depot = {
  get() { try { return JSON.parse(sessionStorage.getItem(CLE) || "null") || {}; } catch { return {}; } },
  set(patch) { sessionStorage.setItem(CLE, JSON.stringify({ ...depot.get(), ...patch })); },
  clear() { sessionStorage.removeItem(CLE); },
};

// Champ de formulaire avec libellé, aide et message d'erreur accessible
export function champ({ id, label, requis = false, aide = null, element }) {
  element.id = id;
  const erreur = h("div", { class: "field-error", id: id + "-err", role: "alert" });
  element.setAttribute("aria-describedby", id + "-err");
  const boite = h("div", { class: "field" },
    h("label", { for: id }, label, requis ? h("span", { class: "req", "aria-hidden": "true" }, " *") : null),
    element, aide ? h("span", { class: "hint" }, aide) : null, erreur);
  boite.erreur = (msg) => {
    erreur.textContent = msg || "";
    boite.classList.toggle("invalid", !!msg);
    element.setAttribute("aria-invalid", msg ? "true" : "false");
  };
  return boite;
}

export const aujourdhui = () => new Date().toLocaleDateString("en-CA"); // AAAA-MM-JJ en heure locale
