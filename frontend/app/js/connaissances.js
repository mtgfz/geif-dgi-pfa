// Base de connaissances : le Code Général des Impôts indexé pour le RAG. État de l'index, consultation d'un article
// ou recherche libre (les mêmes passages que ceux utilisés pour instruire les dossiers et répondre aux contribuables).
import { api } from "../../assets/js/api.js";
import { nombre } from "../../assets/js/charts.js";
import { mountShell } from "../../assets/js/layout.js";
import { emptyState, h, icon, skeletonRows } from "../../assets/js/ui.js";

const shell = mountShell({ page: "connaissances", title: "Base de connaissances", subtitle: "Code Général des Impôts (CGI) indexé pour la recherche sémantique (RAG)." });

const EXEMPLES = ["délai de réclamation", "double imposition", "TVA déductible", "retenue à la source", "charges non déductibles", "Article 235"];

// Met en évidence les mots de la requête dans l'extrait (nœuds <mark> créés par h() : aucune injection possible)
function surligner(texte, requete) {
  const mots = [...new Set(requete.toLowerCase().split(/[^a-zàâçéèêëîïôûùüÿœ0-9]+/).filter((m) => m.length >= 4))];
  if (!mots.length) return [texte];
  const re = new RegExp(`(${mots.map((m) => m.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return texte.split(re).map((part, i) => (i % 2 ? h("mark", {}, part) : part));
}

function carteEtat(ico, tone, valeur, label, sous) {
  return h("div", { class: "card kpi" }, h("div", { class: `kpi-ico ${tone}` }, icon(ico)),
    h("div", {}, h("div", { class: "kpi-val", style: "font-size:22px" }, valeur), h("div", { class: "kpi-label" }, label), sous ? h("div", { class: "kpi-sub" }, sous) : null));
}

async function init({ main }) {
  const etat = h("div", { class: "grid kpis kpis-6" }, h("div", { class: "skeleton", style: "height:80px" }));
  const recherche = h("input", { class: "input", type: "search", maxlength: "300", placeholder: "Ex. délai de réclamation, charges déductibles, Article 235…", "aria-label": "Rechercher dans le CGI" });
  const bouton = h("button", { class: "btn btn-primary", type: "submit" }, icon("search"), "Rechercher");
  const exemples = h("div", { class: "chips-row" }, h("span", { class: "muted", style: "align-self:center;font-size:13px" }, "Essayer :"),
    EXEMPLES.map((e) => h("button", { class: "chip", type: "button", onclick: () => { recherche.value = e; chercher(); } }, e)));
  const resultats = h("div", { "aria-live": "polite" }, emptyState("Posez une question au CGI", "Saisissez un sujet, ou un numéro d'article (« Article 235 ») pour l'ouvrir directement."));
  const form = h("form", { class: "toolbar", novalidate: true }, h("div", { class: "field grow" }, h("label", {}, "Recherche"), h("div", { class: "search" }, icon("search"), recherche)), bouton);
  const mobilises = h("div");

  main.append(etat,
    h("section", { class: "card", style: "margin-top:16px" }, h("div", { class: "card-head" }, h("h2", {}, "Rechercher dans le CGI")), form, exemples, resultats),
    h("section", { class: "card section-gap" }, h("div", { class: "card-head" }, h("div", {}, h("h2", {}, "Articles les plus mobilisés dans les dossiers"),
      h("p", { class: "muted", style: "font-size:12.5px" }, "Base légale retenue lors du traitement des réclamations."))), mobilises));

  form.addEventListener("submit", (e) => { e.preventDefault(); chercher(); });

  async function chercher() {
    const q = recherche.value.trim();
    if (q.length < 3) { resultats.replaceChildren(h("div", { class: "alert warn", style: "margin:16px" }, icon("alert"), "Saisissez au moins 3 caractères.")); return; }
    bouton.disabled = true;
    resultats.replaceChildren(h("div", { class: "table-wrap" }, h("table", { class: "table" }, h("tbody", {}, skeletonRows(1, 3)))));
    try {
      const r = await api.get("/connaissances/recherche", { q, k: 6 });
      if (!r.disponible) { resultats.replaceChildren(h("div", { class: "alert error", style: "margin:16px" }, icon("alert"), r.message)); return; }
      if (!r.resultats.length) { resultats.replaceChildren(emptyState("Aucun résultat", "Reformulez votre recherche.")); return; }
      resultats.replaceChildren(
        r.consultation_directe ? h("div", { class: "alert info", style: "margin:16px 20px 0" }, icon("book"), "Consultation directe d'article, suivie des passages les plus proches.") : null,
        ...r.resultats.map((x) => h("article", { class: "result" },
          h("div", { class: "result-top" }, h("strong", {}, x.article), x.page ? h("span", { class: "muted" }, `page ${x.page}`) : null,
            x.exact ? h("span", { class: "badge plain tone-blue" }, "Article demandé")
              : x.pertinent ? h("span", { class: "badge plain tone-green" }, "Pertinent") : h("span", { class: "badge plain tone-slate" }, "Peu pertinent"),
            x.score != null ? h("span", { class: "muted", style: "font-size:12.5px" }, `score ${x.score} (seuil ${r.seuil})`) : null),
          h("div", { class: "prose" }, surligner(x.extrait, q)))));
    } catch (e) { resultats.replaceChildren(h("div", { class: "alert error", style: "margin:16px" }, icon("alert"), e.message)); }
    bouton.disabled = false;
  }

  try {
    const [e, s] = await Promise.all([api.get("/connaissances/etat"), api.get("/statistiques")]);
    if (!e.disponible) {
      etat.replaceChildren(h("div", { class: "alert error", style: "grid-column:1/-1" }, icon("alert"), h("div", {},
        h("strong", {}, "Base du CGI indisponible. "), e.message || "", " Relancez l'indexation : ", h("code", {}, "python rag/ingest_pdfs.py"))));
    } else {
      etat.replaceChildren(
        carteEtat("book", "navy", nombre(e.passages), "Passages indexés", "extraits du CGI"),
        carteEtat("file", "violet", nombre(e.articles), "Articles détectés", "numéros d'article reconnus"),
        carteEtat("archive", "amber", e.page_min ? `${e.page_min}–${e.page_max}` : "—", "Pages couvertes", e.source ? `${e.source.nom} · ${e.source.taille_mo} Mo` : "source non trouvée"),
        carteEtat("sparkles", e.modele_charge ? "green" : "blue", e.modele_charge ? "Actif" : "En veille", "Modèle de recherche", e.modele));
    }
    mobilises.replaceChildren(s.articles_mobilises.length
      ? h("div", { class: "chips-row", style: "border:0;background:none" }, s.articles_mobilises.map((a) =>
          h("button", { class: "chip", type: "button", title: "Ouvrir cet article", onclick: () => { recherche.value = a.article; chercher(); window.scrollTo({ top: 0, behavior: "smooth" }); } }, `${a.article} · ${a.nombre} dossier${a.nombre > 1 ? "s" : ""}`)))
      : emptyState("Aucun article retenu pour l'instant", "Les articles apparaîtront ici dès que des dossiers auront été traités."));
  } catch (err) { etat.replaceChildren(h("div", { class: "alert error", style: "grid-column:1/-1" }, icon("alert"), err.message)); }
}

// Appel en toute fin de fichier : toutes les constantes ci-dessus doivent exister avant init()
if (shell) init(shell);
