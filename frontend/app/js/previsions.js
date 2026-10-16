// Prévisions : (1) charge à venir d'après l'historique RÉEL des dépôts, (2) saisonnalité attendue d'après le modèle
// de séries temporelles (baseline saisonnier + SARIMAX) appliqué à une série SIMULÉE — toujours signalé comme tel.
import { api } from "../../assets/js/api.js";
import { carteGraphique, chartDisponible, COULEURS, nombre, tracer, axeX, axeY } from "../../assets/js/charts.js";
import { mountShell } from "../../assets/js/layout.js";
import { emptyState, h, icon } from "../../assets/js/ui.js";

const shell = mountShell({ page: "previsions", title: "Prévisions", subtitle: "Anticiper la charge de travail : tendance réelle et saisonnalité attendue." });

const FIABILITE = { insuffisante: ["Fiabilité insuffisante", "red"], indicative: ["Fiabilité indicative", "amber"], correcte: ["Fiabilité correcte", "green"] };
const select = (options, valeur) => h("select", { class: "input" }, options.map(([v, l]) => h("option", { value: v, selected: String(v) === String(valeur) }, l)));
const champ = (label, el) => h("div", { class: "field" }, h("label", {}, label), el);
const kpi = (ico, tone, valeur, label, sous) => h("div", { class: "card kpi" }, h("div", { class: `kpi-ico ${tone}` }, icon(ico)),
  h("div", {}, h("div", { class: "kpi-val" }, valeur), h("div", { class: "kpi-label" }, label), sous ? h("div", { class: "kpi-sub" }, sous) : null));

function init({ main }) {
  if (!chartDisponible()) { main.append(h("div", { class: "alert error" }, icon("alert"), "La bibliothèque de graphiques n'a pas pu être chargée.")); return; }
  main.append(sectionCharge(), sectionSaisonnalite());
}

// =============================================================================================== 1. charge réelle
function sectionCharge() {
  const impot = select([["", "Tous les impôts"], ["IS", "IS"], ["IR", "IR"], ["TVA", "TVA"]], "");
  const horizon = select([[14, "14 jours"], [28, "28 jours"], [60, "60 jours"]], 28);
  const kpis = h("div", { class: "grid kpis kpis-6", style: "margin:16px 0" });
  const info = h("div");
  const g = carteGraphique({ titre: "Dépôts par jour : historique et tendance", sous: "Barres = dépôts constatés · ligne = tendance linéaire estimée", hauteur: 300, large: true });
  const zone = h("div", { class: "chart-grid", style: "margin:0" }, g.carte);

  async function charger() {
    try {
      const d = await api.get("/predictions/charge", { tax: impot.value, horizon_jours: horizon.value });
      if (!d.disponible) { kpis.replaceChildren(); info.replaceChildren(h("div", { class: "alert info" }, icon("alert"), d.message)); g.vide("Pas encore assez de dépôts pour estimer une charge."); return; }
      const [libFiab, toneFiab] = FIABILITE[d.fiabilite];
      kpis.replaceChildren(
        kpi("inbox", "navy", nombre(d.total_prevu_7j), "Dépôts attendus sous 7 jours", "estimation"),
        kpi("clock", "violet", nombre(d.total_prevu_horizon), `Dépôts attendus sous ${horizon.value} jours`, "estimation"),
        kpi("trend", d.tendance === "hausse" ? "red" : d.tendance === "baisse" ? "green" : "blue", d.tendance[0].toUpperCase() + d.tendance.slice(1), "Tendance", `${d.pente_par_jour > 0 ? "+" : ""}${nombre(d.pente_par_jour)} dépôt/jour par jour`),
        kpi("archive", "amber", d.dossiers, "Dossiers dans l'historique", `${d.jours_historique} jour(s) de recul`));
      info.replaceChildren(h("div", { class: `alert ${d.fiabilite === "correcte" ? "info" : "warn"}` }, icon("alert"), h("div", {},
        h("span", { class: `badge tone-${toneFiab}`, style: "margin-right:10px" }, libFiab), d.explication, ` Méthode : ${d.methode}.`)));
      g.carte.querySelector(".chart-box").replaceChildren(g.canvas);
      g.carte.querySelector(".chart-box").style.height = "300px";
      const hist = d.historique, prev = d.previsions;
      tracer(g.canvas, {
        type: "bar",
        data: { labels: [...hist.map((x) => x.date.slice(5)), ...prev.map((x) => x.date.slice(5))], datasets: [
          { type: "bar", label: "Dépôts constatés", data: [...hist.map((x) => x.volume), ...prev.map(() => null)], backgroundColor: COULEURS.navy, borderRadius: 3 },
          { type: "line", label: "Tendance estimée", data: [...hist.map(() => null), ...prev.map((x) => x.volume_prevu)], borderColor: COULEURS.violet, backgroundColor: COULEURS.violet, borderDash: [6, 4], pointRadius: 0, tension: 0.2 },
        ] },
        options: { plugins: { legend: { position: "bottom" } }, scales: { x: axeX({ ticks: { maxTicksLimit: 16 } }), y: axeY() } },
      });
    } catch (e) { info.replaceChildren(h("div", { class: "alert error" }, icon("alert"), e.message)); }
  }
  impot.addEventListener("change", charger); horizon.addEventListener("change", charger);
  charger();
  return h("section", {}, h("div", { class: "card-head", style: "background:none;border:0;padding:0 0 4px" },
    h("div", {}, h("h2", { style: "font-size:19px" }, "Charge à venir"), h("p", { class: "muted" }, "À partir des réclamations réellement déposées (base de données).")),
    h("div", { class: "controls" }, champ("Impôt", impot), champ("Horizon", horizon))), kpis, info, h("div", { style: "height:12px" }), zone);
}

// ======================================================================================= 2. saisonnalité (simulée)
function sectionSaisonnalite() {
  const impot = select([["TVA", "TVA"], ["IS", "IS"], ["IR", "IR"]], "TVA");
  const horizon = select([[3, "3 mois"], [6, "6 mois"], [12, "12 mois"]], 6);
  const bandeau = h("div", { class: "alert warn", style: "margin:14px 0" }, icon("alert"), h("div", {},
    h("strong", {}, "Série simulée. "), "Le projet ne dispose pas de l'historique réel de la DGI : ces volumes sont générés avec une saisonnalité simulée (graine fixe) pour démontrer la méthode. Ils ne reflètent pas l'activité réelle."));
  const g = carteGraphique({ titre: "Volumes mensuels attendus", sous: "Historique simulé, baseline saisonnier et SARIMAX (intervalle de confiance à 95 %)", hauteur: 340, large: true });
  const resultats = h("div");

  async function charger() {
    resultats.replaceChildren(h("div", { class: "skeleton", style: "height:60px" }));
    try {
      const d = await api.get("/predictions/saisonnalite", { tax: impot.value, horizon: horizon.value });
      if (!d.disponible) { resultats.replaceChildren(h("div", { class: "alert error" }, icon("alert"), d.message)); return; }
      g.carte.querySelector(".chart-box").replaceChildren(g.canvas);
      const recent = d.historique.slice(-24), n = recent.length;
      const futur = d.baseline.map((b) => b.mois);
      const libelles = [...recent.map((x) => x.mois), ...futur];
      const nulsHist = Array(n - 1).fill(null);
      const sar = d.sarimax;
      tracer(g.canvas, {
        type: "line",
        data: { labels: libelles, datasets: [
          { label: "Historique (simulé)", data: [...recent.map((x) => x.volume), ...futur.map(() => null)], borderColor: COULEURS.navy, backgroundColor: COULEURS.navy, pointRadius: 2, tension: 0.25 },
          { label: "Baseline saisonnier", data: [...nulsHist, recent[n - 1].volume, ...d.baseline.map((x) => x.volume)], borderColor: COULEURS.gris, backgroundColor: COULEURS.gris, borderDash: [6, 4], pointRadius: 3, tension: 0.25 },
          ...(sar ? [
            { label: "IC bas", data: [...Array(n).fill(null), ...sar.map((x) => x.bas)], borderWidth: 0, pointRadius: 0, fill: false },
            { label: "Intervalle de confiance 95 %", data: [...Array(n).fill(null), ...sar.map((x) => x.haut)], borderWidth: 0, pointRadius: 0, backgroundColor: "rgba(109,63,192,.15)", fill: "-1" },
            { label: "SARIMAX", data: [...nulsHist, recent[n - 1].volume, ...sar.map((x) => x.volume)], borderColor: COULEURS.violet, backgroundColor: COULEURS.violet, pointRadius: 3, tension: 0.25 },
          ] : []),
        ] },
        options: { interaction: { mode: "index", intersect: false },
          plugins: { legend: { position: "bottom", labels: { filter: (item) => item.text !== "IC bas" } } },
          scales: { x: axeX({ ticks: { maxTicksLimit: 14 } }), y: axeY({ title: { display: true, text: d.unite } }) } },
      });

      const lignes = d.baseline.map((b, i) => h("tr", {}, h("td", {}, b.mois), h("td", { class: "num" }, nombre(b.volume)),
        h("td", { class: "num" }, sar ? nombre(sar[i].volume) : "—"), h("td", { class: "num muted-cell" }, sar ? `${nombre(sar[i].bas)} – ${nombre(sar[i].haut)}` : "—")));
      const bt = d.backtest;
      resultats.replaceChildren(
        h("div", { class: "split-2" },
          h("section", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, "Valeurs prévues")),
            h("div", { class: "table-wrap" }, h("table", { class: "table compact", style: "min-width:420px" },
              h("thead", {}, h("tr", {}, [["Mois"], ["Baseline", 1], ["SARIMAX", 1], ["Intervalle 95 %", 1]].map(([t, num]) => h("th", { class: num ? "num" : "" }, t)))), h("tbody", {}, lignes)))),
          h("section", { class: "card card-pad" }, h("h2", { style: "font-size:16px;margin-bottom:6px" }, "Fiabilité du modèle"),
            bt ? h("div", {}, h("p", { class: "muted", style: "margin-bottom:12px;font-size:13px" }, `Test sur les ${bt.mois} derniers mois connus : erreur moyenne absolue (MAE), en réclamations par mois. Plus c'est bas, mieux c'est.`),
              h("div", { class: "facts" }, h("div", { class: "fact" }, h("span", {}, "Baseline saisonnier"), h("strong", {}, nombre(bt.mae_baseline))),
                h("div", { class: "fact" }, h("span", {}, "SARIMAX"), h("strong", {}, nombre(bt.mae_sarimax)))),
              bt.sarimax_converge === false ? h("div", { class: "alert warn", style: "margin-top:12px" }, icon("alert"), "SARIMAX n'a pas convergé sur ce test : son erreur n'est pas représentative de sa précision.") : null,
              h("p", { style: "margin-top:14px" }, "Meilleur modèle sur ce test : ", h("span", { class: "badge tone-green" }, bt.meilleur)))
              : h("p", { class: "muted" }, "Test indisponible."),
            sar ? (d.sarimax_converge === false ? h("div", { class: "alert warn", style: "margin-top:14px" }, icon("alert"), "Sur la série complète, SARIMAX signale une convergence incomplète : prudence sur ses valeurs.") : null)
                : h("div", { class: "alert warn", style: "margin-top:14px" }, icon("alert"), "SARIMAX n'a pas pu être calculé : seule la baseline saisonnière est affichée."))));
    } catch (e) { resultats.replaceChildren(h("div", { class: "alert error" }, icon("alert"), e.message)); }
  }
  impot.addEventListener("change", charger); horizon.addEventListener("change", charger);
  charger();
  return h("section", { class: "section-gap" }, h("div", { class: "card-head", style: "background:none;border:0;padding:0 0 4px" },
    h("div", {}, h("h2", { style: "font-size:19px" }, "Saisonnalité attendue"), h("p", { class: "muted" }, "Modèle de séries temporelles : baseline saisonnier et SARIMAX.")),
    h("div", { class: "controls" }, champ("Impôt", impot), champ("Horizon", horizon))), bandeau,
    h("div", { class: "chart-grid", style: "margin-bottom:16px" }, g.carte), resultats);
}

// Appel en toute fin de fichier : toutes les constantes ci-dessus doivent exister avant init()
if (shell) init(shell);
