// Historique : toutes les réclamations dont la décision a été envoyée. Recherche et filtres complets.
import { api } from "../../assets/js/api.js";
import { mountShell } from "../../assets/js/layout.js";
import {
  debounce, decisionBadge, emptyState, formatDate, formatMoney, h, icon, ouvrirDossier, formatRef, skeletonRows,
} from "../../assets/js/ui.js";

const PAGE = 15;
const shell = mountShell({ page: "historique", title: "Historique", subtitle: "Réclamations traitées, décision envoyée au contribuable. Elles ne réapparaissent plus sur l'Accueil." });

function init({ main }) {
  let page = 0;
  const q = h("input", { class: "input", type: "search", placeholder: "Référence, contribuable, IF, motif, e-mail…", "aria-label": "Rechercher" });
  const tax = h("select", { class: "input" }, h("option", { value: "" }, "Tous"), ["IS", "IR", "TVA"].map((t) => h("option", { value: t }, t)));
  const dec = h("select", { class: "input" }, h("option", { value: "" }, "Toutes"),
    ["Rejet", "Dégrèvement total", "Dégrèvement partiel"].map((t) => h("option", { value: t }, t)));
  const from = h("input", { class: "input", type: "date" });
  const to = h("input", { class: "input", type: "date" });
  const reset = h("button", { class: "btn", onclick: () => { [q, from, to].forEach((i) => (i.value = "")); tax.value = dec.value = ""; page = 0; load(); } }, "Réinitialiser");

  const tbody = h("tbody");
  const foot = h("div", { class: "table-foot" });
  main.append(h("section", { class: "card" },
    h("div", { class: "toolbar" },
      h("div", { class: "field grow" }, h("label", {}, "Recherche"), h("div", { class: "search" }, icon("search"), q)),
      h("div", { class: "field" }, h("label", {}, "Impôt"), tax),
      h("div", { class: "field" }, h("label", {}, "Décision"), dec),
      h("div", { class: "field" }, h("label", {}, "Envoyée du"), from),
      h("div", { class: "field" }, h("label", {}, "au"), to),
      reset),
    h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, ["Référence", "Contribuable", "Impôt", "Décision", "Montant contesté", "Montant dégrevé", "Envoyée le"].map((t, i) =>
        h("th", { class: i === 4 || i === 5 ? "num" : "" }, t)))),
      tbody)),
    foot));

  async function load() {
    tbody.replaceChildren(...skeletonRows(7));
    try {
      const { items, total } = await api.get("/reclamations", {
        scope: "historique", q: q.value.trim(), tax: tax.value, type_decision: dec.value,
        date_from: from.value, date_to: to.value, limit: PAGE, skip: page * PAGE,
      });
      if (!items.length) {
        const filtered = q.value.trim() || tax.value || dec.value || from.value || to.value;
        tbody.replaceChildren(h("tr", {}, h("td", { colspan: 7 }, emptyState(
          filtered ? "Aucun résultat" : "Historique vide",
          filtered ? "Aucune réclamation traitée ne correspond à ces critères." : "Les réclamations dont la décision a été envoyée apparaîtront ici."))));
        foot.replaceChildren(h("span", {}, "0 résultat"));
        return;
      }
      tbody.replaceChildren(...items.map((r) => {
        const row = h("tr", { class: "clickable", tabindex: "0", title: "Voir la fiche" },
          h("td", { class: "nowrap" }, h("span", { class: "mono", title: r.id }, formatRef(r.id))),
          h("td", {}, h("div", { class: "cell-main" }, r.contrib), h("div", { class: "cell-sub" }, "IF " + r.ifn)),
          h("td", {}, h("span", { class: "tag" }, r.tax)),
          h("td", {}, decisionBadge(r.type_decision)),
          h("td", { class: "num" }, formatMoney(r.montant)),
          h("td", { class: "num" }, formatMoney(r.montant_degreve)),
          h("td", { class: "nowrap" }, formatDate(r.closed_at)));
        const open = () => ouvrirDossier(r.id);
        row.addEventListener("click", open);
        row.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
        return row;
      }));
      const pages = Math.max(1, Math.ceil(total / PAGE));
      const prev = h("button", { class: "btn btn-sm", disabled: page === 0, onclick: () => { page--; load(); }, "aria-label": "Page précédente" }, icon("left"));
      const next = h("button", { class: "btn btn-sm", disabled: page + 1 >= pages, onclick: () => { page++; load(); }, "aria-label": "Page suivante" }, icon("right"));
      foot.replaceChildren(h("span", {}, `${total} réclamation${total > 1 ? "s" : ""} traitée${total > 1 ? "s" : ""}`),
        h("div", { class: "pager" }, prev, h("span", {}, `Page ${page + 1} / ${pages}`), next));
    } catch (e) {
      tbody.replaceChildren(h("tr", {}, h("td", { colspan: 7 }, h("div", { class: "alert error", style: "margin:16px" }, icon("alert"), e.message))));
    }
  }

  const refilter = () => { page = 0; load(); };
  q.addEventListener("input", debounce(refilter, 300));
  [tax, dec, from, to].forEach((el) => el.addEventListener("change", refilter));
  load();
}

// Appel en toute fin de fichier : toutes les constantes ci-dessus doivent exister avant init()
if (shell) init(shell);
