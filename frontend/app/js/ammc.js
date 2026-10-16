// Données AMMC & banques : états financiers des banques cotées collectés sur le site de l'AMMC.
// L'extraction automatique des PDF est partielle : chaque ligne indique clairement sa qualité.
import { api } from "../../assets/js/api.js";
import { nombre } from "../../assets/js/charts.js";
import { mountShell } from "../../assets/js/layout.js";
import { debounce, emptyState, h, icon, skeletonRows } from "../../assets/js/ui.js";

const shell = mountShell({ page: "ammc", title: "Données AMMC & banques", subtitle: "États financiers des banques cotées, collectés sur le site de l'AMMC." });

const TON = { valide: "green", partiel: "amber", non_extrait: "slate", erreur: "red" };
const kpi = (ico, tone, valeur, label) => h("div", { class: "card kpi" }, h("div", { class: `kpi-ico ${tone}` }, icon(ico)),
  h("div", {}, h("div", { class: "kpi-val" }, valeur), h("div", { class: "kpi-label" }, label)));
const valeur = (v) => (v === null || v === undefined ? h("span", { class: "muted-cell" }, "—") : nombre(v));

function init({ main }) {
  const params = new URLSearchParams(location.search);
  const banque = h("select", { class: "input" }, h("option", { value: "" }, "Toutes les banques"));
  const annee = h("select", { class: "input" }, h("option", { value: "" }, "Tous les exercices"));
  const statut = h("select", { class: "input" }, h("option", { value: "" }, "Tous les statuts"));
  const q = h("input", { class: "input", type: "search", placeholder: "Nom de la banque…", "aria-label": "Rechercher une banque" });
  const reset = h("button", { class: "btn", type: "button", onclick: () => { [banque, annee, statut].forEach((s) => (s.value = "")); q.value = ""; charger(); } }, "Réinitialiser");
  const kpis = h("div", { class: "grid kpis" });
  const tbody = h("tbody");
  const pied = h("div", { class: "table-foot" });
  let lignes = [], tri = { cle: "banque", sens: 1 }, initialise = false;

  const entete = [["banque", "Banque"], ["annee", "Exercice"], ["total_actif", "Total actif", 1], ["resultat_net", "Résultat net", 1], ["pnb", "PNB", 1], [null, "Unité"], ["statut", "Statut"], [null, "Source"]];
  const thead = h("thead", {}, h("tr", {}, entete.map(([cle, lib, num]) => {
    const th = h("th", { class: (num ? "num " : "") + (cle ? "sort" : ""), "aria-sort": "none" }, lib);
    if (cle) th.addEventListener("click", () => { tri = { cle, sens: tri.cle === cle ? -tri.sens : 1 }; dessiner(); });
    return th;
  })));

  main.append(
    h("div", { class: "alert info", style: "margin-bottom:16px" }, icon("alert"), h("div", {},
      h("strong", {}, "Extraction automatique partielle. "), "Seuls les états « Validé » ont passé le contrôle actif = passif ; les autres sont à vérifier dans le PDF. Les unités sont celles lues dans le document (sinon « non déterminée »). Ces données servent de repère sectoriel : elles ne sont pas utilisées pour décider des réclamations.")),
    kpis,
    h("section", { class: "card" },
      h("div", { class: "toolbar" },
        h("div", { class: "field" }, h("label", {}, "Banque"), banque), h("div", { class: "field" }, h("label", {}, "Exercice"), annee),
        h("div", { class: "field" }, h("label", {}, "Qualité d'extraction"), statut),
        h("div", { class: "field grow" }, h("label", {}, "Recherche"), h("div", { class: "search" }, icon("search"), q)), reset),
      h("div", { class: "table-wrap" }, h("table", { class: "table compact", style: "min-width:960px" }, thead, tbody)), pied));

  function dessiner() {
    const { cle, sens } = tri;
    const tries = [...lignes].sort((a, b) => {
      const x = a[cle], y = b[cle];
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (typeof x === "string" ? x.localeCompare(y, "fr") : x - y) * sens || a.annee - b.annee;
    });
    thead.querySelectorAll("th").forEach((th, i) => th.setAttribute("aria-sort", entete[i][0] === cle ? (sens > 0 ? "ascending" : "descending") : "none"));
    if (!tries.length) { tbody.replaceChildren(h("tr", {}, h("td", { colspan: 8 }, emptyState("Aucun état financier", "Aucune ligne ne correspond à ces filtres.")))); return; }
    tbody.replaceChildren(...tries.map((l) => h("tr", {},
      h("td", { class: "cell-main" }, l.banque), h("td", {}, l.annee),
      h("td", { class: "num" }, valeur(l.total_actif)), h("td", { class: "num" }, valeur(l.resultat_net)), h("td", { class: "num" }, valeur(l.pnb)),
      h("td", { class: "cell-sub" }, l.unite || (l.statut === "non_extrait" ? "—" : "non déterminée")),
      h("td", {}, h("span", { class: `badge tone-${TON[l.statut]}` }, l.statut_libelle)),
      h("td", {}, l.pdf_url ? h("a", { href: l.pdf_url, target: "_blank", rel: "noopener noreferrer" }, "PDF") : null, l.pdf_url && l.detail_url ? " · " : null,
        l.detail_url ? h("a", { href: l.detail_url, target: "_blank", rel: "noopener noreferrer" }, "Fiche AMMC") : null))));
  }

  async function charger() {
    tbody.replaceChildren(...skeletonRows(8, 6));
    try {
      const d = await api.get("/marche-ammc", { banque: banque.value, annee: annee.value, statut: statut.value, q: q.value.trim() });
      if (!d.disponible) { tbody.replaceChildren(h("tr", {}, h("td", { colspan: 8 }, h("div", { class: "alert error", style: "margin:16px" }, icon("alert"), d.message)))); return; }
      if (!initialise) {  // listes déroulantes remplies une seule fois
        d.banques.forEach((b) => banque.append(h("option", { value: b }, b)));
        d.annees.forEach((a) => annee.append(h("option", { value: a }, a)));
        Object.entries(d.statuts).forEach(([k, l]) => statut.append(h("option", { value: k }, l)));
        initialise = true;
      }
      kpis.replaceChildren(kpi("landmark", "navy", d.kpis.banques, "Banques suivies"), kpi("file", "violet", d.kpis.etats_financiers, "États financiers collectés"),
        kpi("archive", "amber", d.kpis.extraits, "Avec des valeurs extraites"), kpi("check", "green", d.kpis.valides, "Validés (actif = passif)"));
      lignes = d.lignes;
      dessiner();
      pied.replaceChildren(h("span", {}, `${d.total_filtre} état${d.total_filtre > 1 ? "s" : ""} financier${d.total_filtre > 1 ? "s" : ""} affiché${d.total_filtre > 1 ? "s" : ""}`), h("span", {}, "Cliquez sur un en-tête pour trier"));
    } catch (e) { tbody.replaceChildren(h("tr", {}, h("td", { colspan: 8 }, h("div", { class: "alert error", style: "margin:16px" }, icon("alert"), e.message)))); }
  }

  [banque, annee, statut].forEach((s) => s.addEventListener("change", charger));
  q.addEventListener("input", debounce(charger, 300));
  (async () => {
    await charger();
    if (params.get("banque")) { banque.value = params.get("banque"); if (banque.value) charger(); }  // lien depuis un dossier
  })();
}

// Appel en toute fin de fichier : toutes les constantes ci-dessus doivent exister avant init()
if (shell) init(shell);
