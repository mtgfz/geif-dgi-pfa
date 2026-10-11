// Assistant fiscal : questions sur la procédure, réponses appuyées sur le CGI (RAG) avec les articles cités.
import { api } from "../../assets/js/api.js";
import { mountPortail } from "../../assets/js/portail.js";
import { h, icon } from "../../assets/js/ui.js";

const main = mountPortail({ page: "assistant", title: "Assistant fiscal" });
const MAX = 500;
const historique = [];   // conservé en mémoire seulement (jamais stocké)
let occupe = false;

const log = h("div", { class: "chat-log", role: "log", "aria-live": "polite", "aria-label": "Conversation" });
const zone = h("textarea", { class: "input", rows: "1", maxlength: String(MAX), placeholder: "Posez votre question…", "aria-label": "Votre question" });
const envoyer = h("button", { class: "btn btn-primary", type: "button", style: "height:46px" }, icon("send"), "Envoyer");
const compteur = h("div", { class: "counter" }, `0 / ${MAX}`);

const bulleBot = (texte, sources = [], limite = false) => h("div", { class: "msg-wrap" },
  h("div", { class: "msg bot" }, texte),
  limite ? h("span", { class: "badge plain tone-amber" }, "Réponse automatique limitée : l'assistant IA est indisponible") : null,
  sources.length ? h("div", { class: "sources" }, sources.map((s) =>
    h("details", { class: "source" }, h("summary", {}, `${s.article}${s.page ? " · p. " + s.page : ""}`), h("p", {}, s.extrait)))) : null);

function ajouter(el) { log.append(el); log.scrollTop = log.scrollHeight; return el; }

async function poser(question) {
  question = question.trim();
  if (!question || occupe) return;
  occupe = true; envoyer.disabled = true; zone.value = ""; compteur.textContent = `0 / ${MAX}`; zone.style.height = "auto";
  ajouter(h("div", { class: "msg user" }, question));
  const attente = ajouter(h("div", { class: "msg bot", "aria-label": "L'assistant rédige sa réponse" }, h("span", { class: "typing" }, h("i"), h("i"), h("i"))));
  try {
    const r = await api.post("/assistant/sit", { question, historique: historique.slice(-6) }, { auth: false });
    attente.replaceWith(bulleBot(r.reponse, r.sources || [], r.genere === false));
    historique.push({ role: "user", content: question }, { role: "assistant", content: r.reponse });
  } catch (e) {
    attente.replaceWith(h("div", { class: "msg bot" }, h("span", { class: "badge plain tone-red" }, "Erreur"), " ", e.message));
  }
  log.scrollTop = log.scrollHeight;
  occupe = false; envoyer.disabled = false; zone.focus();
}

envoyer.addEventListener("click", () => poser(zone.value));
zone.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); poser(zone.value); } });
zone.addEventListener("input", () => {
  compteur.textContent = `${zone.value.length} / ${MAX}`;
  zone.style.height = "auto"; zone.style.height = Math.min(zone.scrollHeight, 120) + "px";
});

const SUGGESTIONS = [
  "Dans quel délai puis-je déposer une réclamation ?",
  "Quels documents dois-je joindre à ma demande ?",
  "Comment contester un redressement de TVA ?",
  "Comment suivre mon dossier ?",
];
const suggestions = h("div", { class: "suggestions" }, SUGGESTIONS.map((s) =>
  h("button", { class: "chip", type: "button", onclick: () => poser(s) }, s)));

ajouter(bulleBot("Bonjour, je suis l'assistant fiscal. Je peux vous orienter sur la procédure de réclamation (motifs, documents, délais) en m'appuyant sur le Code Général des Impôts. Je ne rends aucune décision : votre dossier sera instruit par un gestionnaire."));

main.append(
  h("div", { class: "p-title", style: "max-width:820px" }, h("h1", {}, "Assistant fiscal"),
    h("p", {}, "Une aide pour comprendre la procédure. Les passages du CGI utilisés pour répondre sont indiqués sous chaque réponse.")),
  h("div", { class: "card chat-shell" }, log,
    h("div", { class: "chat-input" }, suggestions, h("div", { class: "chat-row" }, h("div", { style: "flex:1" }, zone, compteur), envoyer))),
  h("p", { class: "muted", style: "max-width:820px;margin:14px auto 0;font-size:13px" },
    "Les réponses sont fournies à titre indicatif et ne constituent pas un avis juridique."));
zone.focus();
