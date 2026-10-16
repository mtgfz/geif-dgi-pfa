// Dashboard : activité de traitement (volumes, délais, décisions, qualité des propositions) et anomalies à vérifier.
// Tous les chiffres viennent de la base (aucune donnée simulée) ; la prévision de charge est détaillée dans « Prévisions ».
import { api } from "../../assets/js/api.js";
import { anneau, barres, carteGraphique, chartDisponible, COULEURS, nombre, tracer, axeX, axeY } from "../../assets/js/charts.js";
import { mountShell } from "../../assets/js/layout.js";
import { emptyState, formatMoney, formatRef, h, icon, ouvrirDossier, STATUS_META, statusBadge } from "../../assets/js/ui.js";

const shell = mountShell({ page: "dashboard", title: "Dashboard", subtitle: "Vue d'ensemble de l'activité de traitement des réclamations." });

function kpi(ico, tone, valeur, label, sous) {
  return h("div", { class: "card kpi" }, h("div", { class: `kpi-ico ${tone}` }, icon(ico)),
    h("div", {}, h("div", { class: "kpi-val" }, valeur), h("div", { class: "kpi-label" }, label), sous ? h("div", { class: "kpi-sub" }, sous) : null));
}
const pct = (v) => (v === null || v === undefined ? "—" : `${nombre(v * 100)} %`);

async function init({ main, setHeader }) {
  const actualiser = h("button", { class: "btn", type: "button", onclick: () => charger() }, icon("refresh"), "Actualiser");
  setHeader("Dashboard", "Vue d'ensemble de l'activité de traitement des réclamations.", [actualiser]);
  const zone = h("div");
  main.append(zone);
  if (!chartDisponible()) { zone.append(h("div", { class: "alert error" }, icon("alert"), "La bibliothèque de graphiques n'a pas pu être chargée (assets/vendor/chart.umd.js).")); return; }

  async function charger() {
    zone.replaceChildren(h("div", { class: "skeleton", style: "height:120px;margin-bottom:16px" }), h("div", { class: "skeleton", style: "height:300px" }));
    try {
      const [s, an, ch] = await Promise.all([api.get("/statistiques"), api.get("/statistiques/anomalies"), api.get("/predictions/charge", { horizon_jours: 14 })]);
      zone.replaceChildren(...afficher(s, an, ch));
      tracerTout(s, ch);
    } catch (e) { zone.replaceChildren(h("div", { class: "alert error" }, icon("alert"), e.message)); }
  }

  // ----------------------------------------------------------------- éléments (créés ici, tracés ensuite)
  const graph = {};
  const defs = [
    ["impots", { titre: "Volumes par type d'impôt", sous: "Nombre de réclamations déposées." }],
    ["decisions", { titre: "Répartition des décisions", sous: "Dossiers dont la décision a été envoyée." }],
    ["mois", { titre: "Dépôts par mois", sous: "Évolution du nombre de réclamations reçues." }],
    ["statuts", { titre: "Dossiers par statut", sous: "Où en sont les réclamations dans le circuit." }],
    ["delais", { titre: "Délai moyen de traitement", sous: "En jours, du dépôt à l'envoi de la décision." }],
    ["motifs", { titre: "Motifs les plus fréquents", sous: "Objet des réclamations." }],
    ["ia", { titre: "Qualité des propositions automatiques", sous: "Ce que les gestionnaires font de la proposition.", hauteur: 240 }],
    ["articles", { titre: "Articles du CGI les plus mobilisés", sous: "Base légale retenue dans les dossiers.", hauteur: 240 }],
  ];

  function afficher(s, an, ch) {
    for (const [cle, d] of defs) graph[cle] = carteGraphique(d);
    graph.charge = carteGraphique({ titre: "Charge à venir (14 jours)", sous: "Historique des dépôts et tendance estimée.", hauteur: 240, large: true,
      entete: h("a", { class: "btn btn-sm", href: "previsions.html" }, "Prévisions détaillées", icon("right")) });

    const termine = s.terminees, taux = s.total_reclamations ? termine / s.total_reclamations : null;
    const degreve = s.montant_conteste_termine ? s.montant_total_degreve / s.montant_conteste_termine : null;
    const kpis = h("div", { class: "grid kpis kpis-6" },
      kpi("inbox", "navy", s.total_reclamations, "Réclamations reçues", `${s.traitees} déjà prises en charge`),
      kpi("check", "green", termine, "Décisions envoyées", `${pct(taux)} du total`),
      kpi("clock", "amber", s.delai_moyen_traitement_jours === null ? "—" : `${nombre(s.delai_moyen_traitement_jours)} j`, "Délai moyen de traitement", termine ? "du dépôt à la décision" : "aucune décision pour l'instant"),
      kpi("chart", "violet", pct(degreve), "Taux de dégrèvement accordé", degreve === null ? "sur les dossiers décidés" : `${formatMoney(s.montant_total_degreve)} sur ${formatMoney(s.montant_conteste_termine)}`),
      kpi("sparkles", "blue", pct(s.taux_acceptation_sans_modification), "Propositions retenues telles quelles", `${s.feedback_gestionnaire.accept + s.feedback_gestionnaire.modify + s.feedback_gestionnaire.reject} décisions de gestionnaires`),
      kpi("alert", an.total ? "red" : "green", an.total, "Dossiers à vérifier", an.total ? "voir la liste ci-dessous" : "aucune anomalie détectée"));

    const grille = h("div", { class: "chart-grid" }, ...defs.map(([cle]) => graph[cle].carte), graph.charge.carte);
    return [kpis, grille, carteAnomalies(an)];
  }

  function tracerTout(s, ch) {
    const g = graph;
    const impots = s.par_impot.sort((a, b) => a.tax.localeCompare(b.tax));
    if (!impots.length) g.impots.vide("Aucune réclamation pour l'instant."); else
      barres(g.impots.canvas, impots.map((i) => i.tax), impots.map((i) => i.nombre), impots.map((i) => COULEURS.impot[i.tax] || COULEURS.navy),
        { tooltip: (c) => { const i = impots[c.dataIndex]; return `${i.nombre} réclamation(s) · ${formatMoney(i.montant_emis)} contestés`; } });

    const dec = Object.entries(s.repartition_decisions).filter(([, n]) => n > 0);
    if (!dec.length) g.decisions.vide("Aucune décision envoyée pour l'instant."); else
      anneau(g.decisions.canvas, dec.map(([k]) => k), dec.map(([, n]) => n), dec.map(([k]) => COULEURS.decision[k]));

    const mois = Object.entries(s.par_mois);
    if (!mois.length) g.mois.vide("Aucun dépôt enregistré."); else
      barres(g.mois.canvas, mois.map(([m]) => m), mois.map(([, n]) => n), COULEURS.navy);

    const st = Object.entries(s.par_statut).filter(([, n]) => n > 0);
    if (!st.length) g.statuts.vide("Aucun dossier."); else
      barres(g.statuts.canvas, st.map(([k]) => (STATUS_META[k] || { label: k }).label), st.map(([, n]) => n), st.map(([k]) => COULEURS.statut[k]), { horizontal: true });

    const avecDelai = impots.filter((i) => i.delai_moyen_jours !== null);
    if (!avecDelai.length) g.delais.vide("Aucune décision envoyée : délai non calculable."); else
      barres(g.delais.canvas, avecDelai.map((i) => i.tax), avecDelai.map((i) => i.delai_moyen_jours), avecDelai.map((i) => COULEURS.impot[i.tax]),
        { libelle: "Jours", tooltip: (c) => `${nombre(c.parsed.y)} jours en moyenne` });

    const motifs = s.par_motif.slice(0, 6);
    if (!motifs.length) g.motifs.vide("Aucun motif."); else
      barres(g.motifs.canvas, motifs.map((m) => `${m.motif.length > 38 ? m.motif.slice(0, 36) + "…" : m.motif} (${m.tax})`), motifs.map((m) => m.nombre), motifs.map((m) => COULEURS.impot[m.tax] || COULEURS.navy), { horizontal: true });

    const fb = s.feedback_gestionnaire;
    if (!(fb.accept + fb.modify + fb.reject)) g.ia.vide("Aucune décision de gestionnaire enregistrée."); else
      anneau(g.ia.canvas, ["Retenue telle quelle", "Retenue avec corrections", "Rejetée"], [fb.accept, fb.modify, fb.reject], [COULEURS.ia.accept, COULEURS.ia.modify, COULEURS.ia.reject]);

    if (!s.articles_mobilises.length) g.articles.vide("Aucun article retenu pour l'instant."); else
      barres(g.articles.canvas, s.articles_mobilises.map((a) => a.article), s.articles_mobilises.map((a) => a.nombre), COULEURS.violet, { horizontal: true, libelle: "Dossiers" });

    if (!ch.disponible) g.charge.vide(ch.message); else {
      const hist = ch.historique.slice(-30), prev = ch.previsions;
      tracer(g.charge.canvas, {
        type: "bar",
        data: { labels: [...hist.map((x) => x.date.slice(5)), ...prev.map((x) => x.date.slice(5))], datasets: [
          { type: "bar", label: "Dépôts constatés", data: [...hist.map((x) => x.volume), ...prev.map(() => null)], backgroundColor: COULEURS.navy, borderRadius: 3 },
          { type: "line", label: "Tendance estimée", data: [...hist.map(() => null), ...prev.map((x) => x.volume_prevu)], borderColor: COULEURS.violet, backgroundColor: COULEURS.violet, borderDash: [6, 4], pointRadius: 0, tension: 0.2 },
        ] },
        options: { plugins: { legend: { position: "bottom" } }, scales: { x: axeX({ ticks: { maxTicksLimit: 12 } }), y: axeY() } },
      });
    }
  }

  function carteAnomalies(an) {
    const resume = Object.entries(an.resume).filter(([, n]) => n > 0)
      .map(([code, n]) => h("span", { class: "badge plain tone-amber" }, `${an.libelles[code]} · ${n}`));
    const lignes = an.items.slice(0, 12).map((i) => {
      const ouvrir = () => ouvrirDossier(i.id);
      const tr = h("tr", { class: "clickable", tabindex: "0" },
        h("td", {}, h("div", { class: "cell-main" }, i.contrib), h("div", { class: "cell-sub mono" }, formatRef(i.id))),
        h("td", {}, h("span", { class: "tag" }, i.tax)),
        h("td", {}, statusBadge(i.status)),
        h("td", {}, i.signaux.map((s) => h("span", { class: "badge plain tone-amber signal", title: s.detail }, s.libelle))),
        h("td", { class: "num" }, h("button", { class: "btn btn-sm", type: "button" }, "Ouvrir", icon("right"))));
      tr.addEventListener("click", ouvrir); tr.addEventListener("keydown", (e) => e.key === "Enter" && ouvrir());
      return tr;
    });
    return h("section", { class: "card", id: "anomalies" },
      h("div", { class: "card-head" }, h("div", {}, h("h2", {}, "Anomalies à vérifier"),
        h("p", { class: "muted", style: "font-size:12.5px" }, `${an.total} dossier(s) sur ${an.dossiers_analyses} analysé(s) · règles explicites, calculées sur les données réelles`))),
      resume.length ? h("div", { class: "chips-row" }, resume) : null,
      an.total
        ? h("div", { class: "table-wrap" }, h("table", { class: "table compact" },
            h("thead", {}, h("tr", {}, ["Dossier", "Impôt", "Statut", "Signaux (survolez pour le détail)", ""].map((t) => h("th", {}, t)))), h("tbody", {}, lignes)))
        : emptyState("Aucune anomalie détectée", "Tous les dossiers analysés sont cohérents avec les règles de contrôle."),
      an.total > 12 ? h("div", { class: "table-foot" }, h("span", {}, `${an.total - 12} autre(s) dossier(s) non affiché(s) — les plus signalés apparaissent en premier.`)) : null,
      h("div", { class: "table-foot" }, h("span", {}, `Seuils : délai de réclamation > ${an.seuils.delai_jours} j · attente > ${an.seuils.attente_jours} j · montant > ${an.seuils.montant_zscore} écarts-types (dès ${an.seuils.dossiers_min_zscore} dossiers par impôt).`)));
  }

  await charger();
}

// Appel en toute fin de fichier : toutes les constantes ci-dessus doivent exister avant init()
if (shell) init(shell);
