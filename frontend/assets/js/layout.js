// Coquille de l'application interne : barre de navigation selon le rôle, garde d'accès, badges.
import { api, goToLogin, session } from "./api.js";
import { HOME_PAGE, LOGIN_PAGE } from "./config.js";
import { h, icon, ROLE_LABELS, showFlash, toast } from "./ui.js";

const TOUS = ["gestionnaire", "chef_service", "chef_subdivision"];
const CHEFS = ["chef_service", "chef_subdivision"];

export const NAV = [
  { id: "accueil", label: "Accueil", href: "accueil.html", icon: "inbox", roles: TOUS, badge: true },
  { id: "traiter", label: "Traiter", href: "traiter.html", icon: "edit", roles: ["gestionnaire"] },
  { id: "validation", label: "Validation", href: "validation.html", icon: "check", roles: CHEFS },
  { id: "historique", label: "Historique", href: "historique.html", icon: "archive", roles: TOUS },
  { id: "dashboard", label: "Dashboard", href: "dashboard.html", icon: "chart", roles: TOUS },
  { id: "previsions", label: "Prévisions", href: "previsions.html", icon: "trend", roles: TOUS },
  { id: "connaissances", label: "Connaissances", href: "connaissances.html", icon: "book", roles: TOUS },
  { id: "ammc", label: "AMMC & banques", href: "ammc.html", icon: "landmark", roles: TOUS },
];

const initiales = (name) => (name || "?").slice(0, 2).toUpperCase();

export function logout() {
  session.clear();
  location.replace(LOGIN_PAGE);
}

/**
 * Construit la page : barre de navigation + conteneur.
 * @returns {{user, main, setHeader, refreshCounts}} main = élément où la page insère son contenu.
 */
export function mountShell({ page, title, subtitle = "", actions = [] }) {
  const user = session.user;
  if (!session.token || !user) { goToLogin(); return null; }
  const item = NAV.find((n) => n.id === page);
  if (item && !item.roles.includes(user.role)) { location.replace(`${HOME_PAGE}?denied=1`); return null; }

  document.title = `${title} · GEIF`;
  const links = NAV.filter((n) => n.roles.includes(user.role)).map((n) => {
    const count = h("span", { class: "count", hidden: true, id: "count-" + n.id });
    return h("a", { href: n.href, "aria-current": n.id === page ? "page" : null }, icon(n.icon), n.label, n.badge ? count : null);
  });
  const nav = h("nav", { class: "nav", id: "nav", "aria-label": "Navigation principale" }, links,
    h("div", { class: "nav-user" }, `${user.username} · ${ROLE_LABELS[user.role] || user.role}`),
    h("a", { href: "#", class: "nav-user", onclick: (e) => { e.preventDefault(); logout(); }, style: "padding-top:4px" }, icon("logout"), "Se déconnecter"));
  const burger = h("button", { class: "icon-btn burger", "aria-label": "Menu", "aria-expanded": "false", onclick: () => {
    const open = nav.classList.toggle("open");
    burger.setAttribute("aria-expanded", String(open));
  } }, icon("menu"));

  const bar = h("header", { class: "topbar" }, h("div", { class: "topbar-inner" },
    h("a", { class: "brand", href: HOME_PAGE, "aria-label": "GEIF — accueil" },
      h("div", { class: "brand-mark" }, "G"),
      h("div", { class: "brand-text" }, h("strong", {}, "GEIF"), h("span", {}, "Direction Générale des Impôts"))),
    nav,
    h("div", { class: "user-chip" },
      h("div", { class: "user-meta" }, h("strong", {}, user.username), h("span", {}, ROLE_LABELS[user.role] || user.role)),
      h("div", { class: "avatar", "aria-hidden": "true" }, initiales(user.username)),
      h("button", { class: "icon-btn", title: "Se déconnecter", "aria-label": "Se déconnecter", onclick: logout }, icon("logout"))),
    burger));

  const headerBox = h("div", { class: "page-head" });
  const main = h("main", { class: "container", id: "page" }, headerBox);
  const setHeader = (t, s, acts = []) => {
    const parts = [h("div", {}, h("h1", {}, t), s ? h("p", {}, s) : null)];
    if (acts.length) parts.push(h("div", { style: "display:flex;gap:10px" }, acts));
    headerBox.replaceChildren(...parts);
  };
  setHeader(title, subtitle, actions);
  document.body.replaceChildren(bar, main);

  showFlash();
  if (new URLSearchParams(location.search).get("denied")) toast("Cette page n'est pas accessible avec votre rôle.", "error");

  async function refreshCounts() {
    try {
      const c = await api.get("/reclamations/compteurs");
      const badge = document.getElementById("count-accueil");
      if (badge) { badge.textContent = c.accueil; badge.hidden = c.accueil === 0; }
      return c;
    } catch { return null; }
  }
  refreshCounts();
  return { user, main, setHeader, refreshCounts };
}
