import { mountPortail } from "../../assets/js/portail.js";
import { h, icon } from "../../assets/js/ui.js";

const main = mountPortail({ page: "accueil", title: "Accueil" });

const carte = (href, tone, ico, titre, texte, lien) =>
  h("a", { class: "card p-card-link", href },
    h("div", { class: "big-ico", style: tone === "navy" ? "background:var(--navy-100);color:var(--navy-700)" : `background:var(--${tone}-bg);color:var(--${tone})` }, icon(ico)),
    h("h2", {}, titre), h("p", {}, texte), h("span", { class: "go" }, lien + " →"));

main.append(
  h("section", { class: "p-hero" },
    h("h1", {}, "Déposez et suivez votre réclamation fiscale en ligne"),
    h("p", {}, "Sans création de compte. À la fin du dépôt, vous recevez une référence et un code secret qui vous permettent de suivre l'avancement et de consulter la décision."),
    h("div", { class: "cta" },
      h("a", { class: "btn btn-light btn-lg", href: "deposer.html" }, icon("file"), "Déposer une réclamation"),
      h("a", { class: "btn btn-outline-light btn-lg", href: "suivi.html" }, icon("search"), "Suivre ma réclamation"))),
  h("div", { class: "p-cards" },
    carte("deposer.html", "navy", "file", "Déposer une réclamation", "Renseignez votre dossier et joignez vos justificatifs en trois étapes (PDF ou images).", "Commencer"),
    carte("suivi.html", "green", "clock", "Suivre ma réclamation", "Consultez l'avancement de votre dossier et la décision avec votre référence et votre code.", "Consulter"),
    carte("assistant.html", "violet", "sparkles", "Assistant fiscal", "Posez vos questions sur la procédure, les délais et les documents. Les réponses s'appuient sur le Code Général des Impôts.", "Poser une question")),
  h("section", { class: "how" }, h("h2", {}, "Comment ça marche"),
    h("ol", { class: "how-steps" },
      [["Remplissez le formulaire", "Identité fiscale, impôt concerné, objet et montant contesté."],
       ["Joignez vos justificatifs", "La demande de dégrèvement est obligatoire ; jusqu'à 5 pièces en plus."],
       ["Notez votre code", "Une référence et un code secret s'affichent, et vous sont envoyés par e-mail."],
       ["Suivez votre dossier", "Un gestionnaire l'instruit, puis la décision validée vous est notifiée ici."]]
        .map(([t, s]) => h("li", {}, h("strong", {}, t), h("span", {}, s))))),
  h("div", { class: "reassure" }, icon("shield"),
    h("div", {}, h("strong", {}, "Votre code de suivi est personnel. "), "Il est indispensable pour consulter votre dossier : ne le communiquez à personne.")));
