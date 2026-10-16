// Aides Chart.js (bibliothèque locale : assets/vendor/chart.umd.js, chargée par la page avant ce module).
import { h, icon } from "./ui.js";

export const COULEURS = {
  impot: { IS: "#1b4478", IR: "#0f8b8d", TVA: "#6d3fc0" },
  decision: { "Rejet": "#b42318", "Dégrèvement total": "#137a4b", "Dégrèvement partiel": "#d98b0a" },
  statut: { nouvelle: "#1d6fd8", en_traitement: "#d98b0a", envoyee_chef_service: "#6d3fc0", envoyee_chef_subdivision: "#3b4cc0", decision_envoyee: "#137a4b", retournee: "#b42318" },
  ia: { accept: "#137a4b", modify: "#d98b0a", reject: "#b42318" },
  navy: "#1b4478", gris: "#8a97ad", violet: "#6d3fc0",
};

const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
export const nombre = (v) => (v === null || v === undefined ? "—" : nf.format(v).replace(/\u202f|\u00a0/g, " "));

export function chartDisponible() {
  if (!window.Chart) return false;
  const d = window.Chart.defaults;
  d.font.family = '"Inter","Segoe UI",system-ui,-apple-system,Arial,sans-serif';
  d.font.size = 12;
  d.color = "#46566f";
  d.plugins.legend.labels.usePointStyle = true;
  d.plugins.legend.labels.boxWidth = 8;
  d.plugins.tooltip.backgroundColor = "#0b1f3a";
  d.plugins.tooltip.padding = 10;
  d.plugins.tooltip.cornerRadius = 8;
  d.maintainAspectRatio = false;
  return true;
}

/** Carte contenant un graphique. `vide` (texte) remplace le graphique quand il n'y a rien à montrer. */
export function carteGraphique({ titre, sous = null, hauteur = 260, large = false, entete = null }) {
  const canvas = h("canvas", { "aria-label": titre, role: "img" });
  const zone = h("div", { class: "chart-box", style: `height:${hauteur}px` }, canvas);
  const carte = h("section", { class: "card chart-card" + (large ? " wide" : "") },
    h("div", { class: "chart-head" }, h("div", {}, h("h2", {}, titre), sous ? h("p", { class: "muted" }, sous) : null), entete),
    zone);
  return {
    carte, canvas,
    vide(texte) { zone.replaceChildren(h("div", { class: "chart-empty" }, icon("chart"), texte)); zone.style.height = "auto"; },
  };
}

export function tracer(canvas, config) {
  window.Chart.getChart(canvas)?.destroy();
  return new window.Chart(canvas, config);
}

const axeY = (extra = {}) => ({ beginAtZero: true, grid: { color: "#eef1f6" }, border: { display: false }, ticks: { precision: 0 }, ...extra });
const axeX = (extra = {}) => ({ grid: { display: false }, border: { display: false }, ...extra });

export const barres = (canvas, labels, data, couleurs, { horizontal = false, libelle = "Nombre", tooltip = null } = {}) =>
  tracer(canvas, {
    type: "bar",
    data: { labels, datasets: [{ label: libelle, data, backgroundColor: couleurs, borderRadius: 6, maxBarThickness: horizontal ? 22 : 56 }] },
    options: {
      indexAxis: horizontal ? "y" : "x", plugins: { legend: { display: false }, tooltip: tooltip ? { callbacks: { label: tooltip } } : {} },
      scales: horizontal ? { x: axeY(), y: axeX({ ticks: { autoSkip: false } }) } : { x: axeX(), y: axeY() },
    },
  });

export const anneau = (canvas, labels, data, couleurs) =>
  tracer(canvas, {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: couleurs, borderWidth: 3, borderColor: "#fff", hoverOffset: 6 }] },
    options: { cutout: "64%", plugins: { legend: { position: "bottom" } } },
  });

export { axeX, axeY };
