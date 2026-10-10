// Utilitaires d'interface. Règle de sécurité : les données (raison sociale, motif, e-mail…) ne passent
// JAMAIS par innerHTML — elles sont insérées via h() qui utilise textContent (pas d'injection possible).
import { api } from "./api.js";

const ICONS = {
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
  check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  undo: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  archive: '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  chart: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  trend: '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
  book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  landmark: '<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  right: '<polyline points="9 18 15 12 9 6"/>',
  left: '<polyline points="15 18 9 12 15 6"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
};

export function icon(name, extraClass = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon " + extraClass);
  svg.innerHTML = ICONS[name] || ""; // chaînes constantes ci-dessus uniquement
  return svg;
}

// Hyperscript : h("div", {class:"x", onclick:fn}, "texte", enfant, [liste])
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  const add = (c) => {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) c.forEach(add);
    else el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  };
  children.forEach(add);
  return el;
}

// ---------------------------------------------------------------- Métadonnées métier
export const ROLE_LABELS = { gestionnaire: "Gestionnaire", chef_service: "Chef de Service", chef_subdivision: "Chef de Subdivision" };
export const STATUS_META = {
  nouvelle: { label: "Nouvelle", tone: "blue" },
  en_traitement: { label: "En traitement", tone: "amber" },
  envoyee_chef_service: { label: "Envoyée au Chef de Service", tone: "violet" },
  envoyee_chef_subdivision: { label: "Envoyée au Chef de Subdivision", tone: "indigo" },
  decision_envoyee: { label: "Décision envoyée", tone: "green" },
  retournee: { label: "Retournée", tone: "red" },
};
const DECISION_TONE = { "Rejet": "red", "Dégrèvement total": "green", "Dégrèvement partiel": "amber" };

export const statusBadge = (s) => {
  const m = STATUS_META[s] || { label: s, tone: "slate" };
  return h("span", { class: `badge tone-${m.tone}` }, m.label);
};
export const decisionBadge = (t) =>
  t ? h("span", { class: `badge plain tone-${DECISION_TONE[t] || "slate"}` }, t) : h("span", { class: "muted" }, "—");

// ---------------------------------------------------------------- Formats
const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
export const formatMoney = (v) => (v === null || v === undefined ? "—" : nf.format(Math.round(v)).replace(/\u202f|\u00a0/g, " ") + " MAD");
export const formatDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
};
export const formatDateTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleString("fr-FR", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};
export function relativeTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const min = Math.round((Date.now() - d) / 60000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const hh = Math.round(min / 60);
  if (hh < 24) return `il y a ${hh} h`;
  const j = Math.round(hh / 24);
  return j < 31 ? `il y a ${j} j` : formatDate(iso);
}
// Références récentes : REC-2026-483920 (inchangées). Anciennes (REC-AAAAMMJJHHMMSSuuuuuu) : forme compacte lisible.
export const formatRef = (id) => {
  const m = /^REC-(\d{8})\d{6}(\d{6})$/.exec(id || "");
  return m ? `REC-${m[1]}-${m[2]}` : id || "";
};
export const formatSize = (n) => (n == null ? "" : n < 1024 * 1024 ? Math.max(1, Math.round(n / 1024)) + " Ko" : (n / 1048576).toFixed(1) + " Mo");
export const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ---------------------------------------------------------------- Toasts
export function toast(message, type = "info") {
  let box = document.querySelector(".toasts");
  if (!box) { box = h("div", { class: "toasts", role: "status", "aria-live": "polite" }); document.body.append(box); }
  const t = h("div", { class: `toast ${type}` }, message);
  box.append(t);
  setTimeout(() => t.remove(), 4500);
}

// ---------------------------------------------------------------- États vides / chargement
const EMPTY_ART = '<svg class="art" viewBox="0 0 120 100" aria-hidden="true"><rect x="22" y="14" width="76" height="72" rx="10" fill="#e4ecf7"/><rect x="34" y="30" width="52" height="7" rx="3.5" fill="#fff"/><rect x="34" y="46" width="36" height="7" rx="3.5" fill="#fff"/><rect x="34" y="62" width="44" height="7" rx="3.5" fill="#fff"/><circle cx="92" cy="74" r="16" fill="#1b4478"/><path d="M85 74l5 5 9-10" stroke="#fff" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
export function emptyState(title, text) {
  const box = h("div", { class: "empty" }, h("h3", {}, title), h("p", {}, text));
  box.insertAdjacentHTML("afterbegin", EMPTY_ART); // illustration constante
  return box;
}
export function skeletonRows(cols, rows = 5) {
  return Array.from({ length: rows }, () =>
    h("tr", { class: "skeleton-row" }, Array.from({ length: cols }, () => h("td", {}, h("div", { class: "skeleton" })))));
}

// ---------------------------------------------------------------- Fiche dossier (volet latéral, lecture seule)
const EVENT_ACTORS = { contribuable: "Contribuable", systeme: "Système", ...ROLE_LABELS };

export async function ouvrirDossier(id, { actions = [] } = {}) {
  const overlay = h("div", { class: "overlay" });
  const body = h("div", { class: "drawer-body" }, h("div", { class: "skeleton", style: "height:120px" }));
  const title = h("div", {}, h("div", { class: "skeleton", style: "width:220px" }));
  const close = () => { overlay.remove(); drawer.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => e.key === "Escape" && close();
  const foot = h("div", { class: "drawer-foot" });
  const drawer = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Fiche de la réclamation" },
    h("div", { class: "drawer-head" }, title,
      h("button", { class: "btn btn-ghost btn-sm", onclick: close, "aria-label": "Fermer" }, icon("x"))),
    body, foot);
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.append(overlay, drawer);

  try {
    const [d, docs] = await Promise.all([api.get(`/reclamations/${encodeURIComponent(id)}`), api.get(`/reclamations/${encodeURIComponent(id)}/documents`)]);
    title.replaceChildren(
      h("div", { class: "mono muted", style: "font-size:12px" }, formatRef(d.id)),
      h("h2", { style: "font-size:20px;margin:3px 0 8px" }, d.contrib),
      statusBadge(d.status));
    body.replaceChildren(...fichierSections(d, docs));
    actions.forEach((a) => foot.append(a(d, close)));
    if (!actions.length) foot.remove();
  } catch (e) {
    body.replaceChildren(h("div", { class: "alert error" }, icon("alert"), e.message));
  }
  return close;
}

function fact(label, value, wide) {
  return h("div", { class: "fact" + (wide ? " wide" : "") }, h("span", {}, label), h("strong", {}, value ?? "—"));
}

function fichierSections(d, docs) {
  const out = [];
  if (d.commentaire_retour && d.status === "retournee") {
    out.push(h("div", { class: "alert error" }, icon("undo"), h("div", {}, h("strong", {}, "Dossier retourné : "), d.commentaire_retour)));
  }
  out.push(h("section", { class: "section" }, h("h4", {}, "Réclamation"),
    h("div", { class: "facts" },
      fact("Identifiant fiscal (IF)", d.ifn), fact("Type d'impôt", d.tax),
      fact("Montant contesté", formatMoney(d.montant)), fact("Montant dégrevé", formatMoney(d.montant_degreve)),
      fact("Mise en recouvrement", formatDate(d.date_mer)), fact("Date de la réclamation", formatDate(d.date_reclam)),
      fact("E-mail", d.email || "—"), fact("Téléphone", d.telephone || "—"),
      fact("Motif", d.motif, true))));

  out.push(h("section", { class: "section" }, h("h4", {}, `Pièces justificatives (${docs.length})`),
    docs.length
      ? h("div", { class: "doc-list" }, docs.map(docRow(d.id)))
      : h("p", { class: "muted" }, "Aucune pièce déposée.")));

  const texte = d.decision_finale || d.decision;
  if (texte || d.rapport) {
    out.push(h("section", { class: "section" },
      h("h4", {}, d.status === "decision_envoyee" ? "Décision envoyée" : "Décision proposée"),
      h("div", { style: "margin-bottom:10px" }, decisionBadge(d.type_decision),
        d.article ? h("span", { class: "muted", style: "margin-left:10px" }, d.article) : null),
      texte ? h("div", { class: "prose" }, texte) : null,
      d.rapport ? h("details", { class: "fold" }, h("summary", {}, "Rapport d'instruction"), h("div", { class: "prose" }, d.rapport)) : null));
  }

  const events = d.historique || [];
  out.push(h("section", { class: "section" }, h("h4", {}, "Circuit du dossier"),
    h("ol", { class: "timeline" }, events.map((e) => {
      const m = STATUS_META[e.vers] || { label: e.vers };
      return h("li", { class: e.vers === "decision_envoyee" ? "done" : e.vers === "retournee" ? "ret" : "" },
        h("div", { class: "t-title" }, m.label),
        h("div", { class: "t-meta" }, `${EVENT_ACTORS[e.role] || e.role}${e.role === "contribuable" || e.role === "systeme" ? "" : " · " + e.par} · ${formatDateTime(e.date)}`),
        e.commentaire ? h("div", { class: "t-comment" }, e.commentaire) : null);
    }))));
  return out;
}

const docRow = (recId) => (p) => {
  const lecture = p.ocr_ok
    ? h("span", { class: "badge plain tone-green" }, p.ocr_methode === "texte_pdf" ? "Texte PDF lu" : "OCR réussi")
    : h("span", { class: "badge plain tone-red", title: p.ocr_erreur || "" }, "Lecture échouée");
  const open = h("button", { class: "btn btn-sm" }, icon("external"), "Ouvrir");
  open.addEventListener("click", async () => {
    open.disabled = true;
    try {
      const blob = await api.blob(`/reclamations/${encodeURIComponent(recId)}/documents/${p.id}/fichier`);
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
    } catch (e) { toast(e.message, "error"); }
    open.disabled = false;
  });
  return h("div", { class: "doc" }, icon("file"),
    h("div", { class: "doc-main" }, h("strong", { title: p.filename }, p.filename),
      h("span", { class: "cell-sub" }, `${p.description} · ${formatSize(p.taille)}`)),
    lecture, open);
};
