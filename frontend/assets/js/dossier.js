// Briques d'affichage d'un dossier pour les pages Traiter et Validation (lecture OCR, articles du CGI…).
// Toutes les données passent par h() : aucune injection HTML possible.
import { api } from "./api.js";
import { formatMoney, formatSize, h, icon, toast } from "./ui.js";

const CHAMPS = {
  identifiant_fiscal: "Identifiant fiscal (IF)", ice: "ICE", registre_commerce: "Registre de commerce",
  montants: "Montants", dates: "Dates", reference: "Référence", articles_cites: "Articles cités",
};

const METHODES = {
  ocr: ["OCR Tesseract", "blue"],
  texte_pdf: ["Texte du PDF", "slate"],
  mixte: ["OCR + texte du PDF", "blue"],
};

export function titreEtape(numero, titre, sous) {
  return h("div", { class: "step-title" }, h("span", { class: "step-no" }, numero),
    h("div", {}, h("h2", {}, titre), sous ? h("p", { class: "muted" }, sous) : null));
}

function valeurChamp(cle, v) {
  if (cle === "montants") return v.map(formatMoney);
  return Array.isArray(v) ? v : [v];
}

const nettoyerIF = (v) => String(v ?? "").replace(/\s/g, "");

function carteDocument(recId, p, ifDeclare) {
  const [mLabel, mTone] = METHODES[p.ocr_methode] || ["Lecture", "slate"];
  const ouvrir = h("button", { class: "btn btn-sm", type: "button" }, icon("external"), "Ouvrir l'original");
  ouvrir.addEventListener("click", async () => {
    ouvrir.disabled = true;
    try {
      const blob = await api.blob(`/reclamations/${encodeURIComponent(recId)}/documents/${p.id}/fichier`);
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
    } catch (e) { toast(e.message, "error"); }
    ouvrir.disabled = false;
  });

  const champs = Object.entries(p.champs_ocr || {});
  const corps = [];
  if (!p.ocr_ok) {
    corps.push(h("div", { class: "alert warn" }, icon("alert"), h("div", {},
      h("strong", {}, "Lecture automatique impossible. "), p.ocr_erreur || "Aucun texte détecté.",
      " Ouvrez l'original pour le lire manuellement.")));
  } else if (!champs.length) {
    corps.push(h("p", { class: "muted" }, "Texte lu, mais aucun champ clé reconnu automatiquement."));
  } else {
    corps.push(h("div", { class: "fields" }, champs.map(([cle, v]) => {
      // Recoupement utile : l'IF lu sur le document doit être celui déclaré par le contribuable
      const different = cle === "identifiant_fiscal" && ifDeclare && nettoyerIF(v) !== nettoyerIF(ifDeclare);
      return h("div", { class: "field-chip" + (different ? " alerte" : "") }, h("span", {}, CHAMPS[cle] || cle),
        h("strong", {}, valeurChamp(cle, v).join("  ·  ")),
        different ? h("em", {}, `⚠ Différent de l'IF déclaré (${ifDeclare})`) : null);
    })));
  }
  if (p.texte_ocr) {
    corps.push(h("details", { class: "fold" }, h("summary", {}, `Texte lu (${p.texte_ocr.length} caractères)`),
      h("div", { class: "prose" }, p.texte_ocr)));
  }
  return h("div", { class: "piece" },
    h("div", { class: "piece-head" }, icon("file"),
      h("div", { class: "doc-main" }, h("strong", { title: p.filename }, p.filename),
        h("span", { class: "cell-sub" }, `${p.description}${p.obligatoire ? " · pièce obligatoire" : ""} · ${formatSize(p.taille)}`)),
      p.ocr_ok ? h("span", { class: `badge plain tone-${mTone}` }, mLabel) : h("span", { class: "badge plain tone-red" }, "Non lu"),
      ouvrir),
    ...corps);
}

export function sectionPieces(recId, docs, ifDeclare) {
  if (!docs.length) return h("p", { class: "muted" }, "Aucune pièce déposée par le contribuable.");
  return h("div", { class: "pieces" }, docs.map((p) => carteDocument(recId, p, ifDeclare)));
}

export function sectionArticles(d) {
  const arts = d.articles_rag || [];
  if (!arts.length) {
    return h("div", { class: "alert warn" }, icon("alert"),
      "La base du CGI n'a retourné aucun article : le texte s'appuie sur le résumé légal intégré. Vérifiez la base légale manuellement.");
  }
  const max = Math.max(...arts.map((a) => a.score), 1);
  const blocs = [];
  if (d.retrieval_faible) {
    blocs.push(h("div", { class: "alert warn", style: "margin-bottom:12px" }, icon("alert"),
      "Pertinence faible : les articles retrouvés correspondent mal au motif. Vérifiez la base légale avant de valider."));
  }
  blocs.push(h("div", { class: "articles" }, arts.map((a, i) => {
    const retenu = a.article === d.article;
    return h("div", { class: "article" + (retenu ? " retenu" : "") },
      h("div", { class: "article-head" },
        h("strong", {}, a.article), a.page ? h("span", { class: "muted" }, `p. ${a.page}`) : null,
        retenu ? h("span", { class: "badge plain tone-green" }, "Article retenu") : null,
        h("span", { class: "score", title: `Pertinence : ${a.score}` }, h("i", { style: `width:${Math.max(8, Math.round((a.score / max) * 100))}%` }))),
      h("details", { class: "fold" }, h("summary", {}, "Extrait du CGI"), h("div", { class: "prose" }, a.extrait)));
  })));
  return h("div", {}, blocs);
}

export const SOURCES = {
  groq_llm: ["Rédigé par le modèle de langage (Groq)", "green"],
  groq_llm_decision_repli: ["Rapport rédigé par le modèle · décision issue des règles (format de réponse non reconnu)", "amber"],
  repli_sans_cle: ["Texte de repli : clé Groq non configurée", "amber"],
};
export function badgeSource(src) {
  if (!src) return null;
  const [label, tone] = SOURCES[src] || ["Texte de repli : modèle de langage indisponible", "amber"];
  return h("span", { class: `badge tone-${tone}` }, label);
}

export function chargerDossier(id) {
  const enc = encodeURIComponent(id);
  return Promise.all([api.get(`/reclamations/${enc}`), api.get(`/reclamations/${enc}/documents`)]);
}
