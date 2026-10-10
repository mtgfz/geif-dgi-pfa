// Accueil : file d'attente du rôle connecté. Une réclamation terminée n'apparaît JAMAIS ici (voir Historique).
import { api } from "../../assets/js/api.js";
import { POLL_MS } from "../../assets/js/config.js";
import { mountShell } from "../../assets/js/layout.js";
import {
  debounce, emptyState, formatDate, formatMoney, h, icon, ouvrirDossier, relativeTime, formatRef, skeletonRows,
  statusBadge, toast,
} from "../../assets/js/ui.js";

const SUBTITLES = {
  gestionnaire: "Réclamations à traiter, en cours d'instruction ou retournées par vos chefs.",
  chef_service: "Dossiers transmis par les gestionnaires, en attente de votre validation.",
  chef_subdivision: "Dossiers validés par le Chef de Service, en attente de votre décision finale.",
};
const ACTION = {
  gestionnaire: { href: (id) => `traiter.html?id=${encodeURIComponent(id)}`, label: (s) => (s === "en_traitement" ? "Reprendre" : s === "retournee" ? "Corriger" : "Traiter") },
  chef_service: { href: (id) => `validation.html?id=${encodeURIComponent(id)}`, label: () => "Examiner" },
  chef_subdivision: { href: (id) => `validation.html?id=${encodeURIComponent(id)}`, label: () => "Examiner" },
};

const shell = mountShell({ page: "accueil", title: "Accueil", subtitle: "" });
if (shell) init(shell);

function init({ user, main, setHeader, refreshCounts }) {
  setHeader("Accueil", SUBTITLES[user.role], [
    h("button", { class: "btn", onclick: () => { load(true); }, title: "Actualiser" }, icon("refresh"), "Actualiser"),
  ]);
  const action = ACTION[user.role];
  const isGest = user.role === "gestionnaire";

  // ---------------- KPI
  const kpis = h("div", { class: "grid kpis" });
  main.append(kpis);
  function renderKpis(c) {
    const s = c.par_statut;
    const cards = isGest
      ? [["inbox", "blue", s.nouvelle, "Nouvelles réclamations"], ["edit", "amber", s.en_traitement, "En traitement"],
         ["undo", "red", s.retournee, "Retournées à corriger"], ["archive", "green", c.historique, "Décisions envoyées"]]
      : [["inbox", "violet", c.accueil, "En attente de votre validation"], ["undo", "red", s.retournee, "Retournées aux gestionnaires"],
         ["archive", "green", c.historique, "Décisions envoyées"], ["users", "navy", c.total, "Réclamations au total"]];
    kpis.replaceChildren(...cards.map(([ico, tone, val, label]) =>
      h("div", { class: "card kpi" }, h("div", { class: `kpi-ico ${tone}` }, icon(ico)),
        h("div", {}, h("div", { class: "kpi-val" }, val ?? 0), h("div", { class: "kpi-label" }, label)))));
  }

  // ---------------- Filtres
  const search = h("input", { class: "input", type: "search", placeholder: "Référence, contribuable, IF, motif…", "aria-label": "Rechercher" });
  const tax = h("select", { class: "input", "aria-label": "Type d'impôt" },
    h("option", { value: "" }, "Tous les impôts"), ["IS", "IR", "TVA"].map((t) => h("option", { value: t }, t)));
  let statut = "";
  const chipDefs = [["", "Toutes"], ["nouvelle", "Nouvelles"], ["en_traitement", "En traitement"], ["retournee", "Retournées"]];
  const chipBtns = chipDefs.map(([v, l]) => h("button", { class: "chip", "aria-pressed": String(v === statut), onclick: () => {
    statut = v; chipBtns.forEach((b, i) => b.setAttribute("aria-pressed", String(chipDefs[i][0] === v))); load();
  } }, l));

  const tbody = h("tbody");
  const foot = h("div", { class: "table-foot" });
  const toolbar = h("div", { class: "toolbar" },
    h("div", { class: "field grow" }, h("label", {}, "Recherche"), h("div", { class: "search" }, icon("search"), search)),
    h("div", { class: "field" }, h("label", {}, "Impôt"), tax),
    isGest ? h("div", { class: "field" }, h("label", {}, "Statut"), h("div", { class: "chips" }, chipBtns)) : null);

  main.append(h("section", { class: "card" },
    h("div", { class: "card-head" }, h("h2", {}, "File d'attente")),
    toolbar,
    h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, ["Référence", "Contribuable", "Impôt", "Motif", "Montant contesté", "Statut", "Déposée", ""].map((t, i) =>
        h("th", { class: i === 4 ? "num" : "" }, t)))),
      tbody)),
    foot));

  // ---------------- Chargement
  let lastTotal = null;
  async function load(manual = false) {
    if (manual || tbody.children.length === 0) tbody.replaceChildren(...skeletonRows(8));
    try {
      const [res, counts] = await Promise.all([
        api.get("/reclamations", { scope: "accueil", q: search.value.trim(), tax: tax.value, status: statut, limit: 100 }),
        refreshCounts(),
      ]);
      if (counts) renderKpis(counts);
      if (isGest && lastTotal !== null && counts && counts.par_statut.nouvelle > lastTotal) toast("Nouvelle réclamation reçue depuis le portail.", "success");
      if (counts) lastTotal = counts.par_statut.nouvelle;
      render(res);
    } catch (e) {
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: 8 }, h("div", { class: "alert error", style: "margin:16px" }, icon("alert"), e.message))));
    }
  }

  function render({ items, total }) {
    if (!items.length) {
      const filtered = search.value.trim() || tax.value || statut;
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: 8 }, emptyState(
        filtered ? "Aucun résultat" : "Rien en attente",
        filtered ? "Aucune réclamation ne correspond à ces filtres." : "Votre file d'attente est vide. Les nouvelles réclamations du portail apparaîtront ici automatiquement."))));
      foot.replaceChildren(h("span", {}, "0 réclamation"));
      return;
    }
    tbody.replaceChildren(...items.map((r) => {
      const go = h("a", { class: "btn btn-sm btn-primary", href: action.href(r.id), onclick: (e) => e.stopPropagation() }, action.label(r.status), icon("right"));
      const row = h("tr", { class: "clickable", tabindex: "0", title: "Voir la fiche" },
        h("td", { class: "nowrap" }, h("span", { class: "mono", title: r.id }, formatRef(r.id))),
        h("td", {}, h("div", { class: "cell-main" }, r.contrib), h("div", { class: "cell-sub" }, "IF " + r.ifn)),
        h("td", {}, h("span", { class: "tag" }, r.tax)),
        h("td", {}, h("div", { class: "truncate", title: r.motif }, r.motif),
          r.status === "retournee" && r.commentaire_retour
            ? h("div", { class: "retour-note" }, icon("undo"), h("span", {}, r.commentaire_retour)) : null),
        h("td", { class: "num" }, formatMoney(r.montant)),
        h("td", {}, statusBadge(r.status)),
        h("td", { class: "nowrap" }, h("div", {}, formatDate(r.created_at)), h("div", { class: "cell-sub" }, relativeTime(r.created_at))),
        h("td", { class: "num" }, go));
      const open = () => ouvrirDossier(r.id, { actions: [() => h("a", { class: "btn btn-primary", href: action.href(r.id) }, action.label(r.status), icon("right"))] });
      row.addEventListener("click", open);
      row.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      return row;
    }));
    foot.replaceChildren(h("span", {}, `${total} réclamation${total > 1 ? "s" : ""} en attente`), h("span", {}, "Actualisation automatique toutes les 20 s"));
  }

  search.addEventListener("input", debounce(() => load(), 300));
  tax.addEventListener("change", () => load());
  load();
  setInterval(() => { if (!document.hidden && !document.querySelector(".drawer")) load(); }, POLL_MS);
}
