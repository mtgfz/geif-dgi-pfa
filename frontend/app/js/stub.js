// Page provisoire : la navigation ne mène jamais à une 404. Remplacée au fil des étapes de développement.
import { mountShell } from "../../assets/js/layout.js";
import { emptyState, h } from "../../assets/js/ui.js";

const PAGES = {
  traiter: ["Traiter", "Lecture des pièces (OCR), articles du CGI (RAG), rapport d'instruction et décision.", "étape 3"],
  validation: ["Validation", "Examen des dossiers transmis, validation ou retour avec commentaire.", "étape 3"],
  dashboard: ["Dashboard", "Statistiques, volumes par impôt, délais de traitement, répartition des décisions.", "étape 5"],
  previsions: ["Prévisions", "Prévision des volumes de réclamations par type d'impôt.", "étape 5"],
  connaissances: ["Base de connaissances", "Base documentaire du Code Général des Impôts utilisée par le RAG.", "étape 6"],
  ammc: ["Données AMMC & banques", "Consultation et filtrage des données de marché collectées.", "étape 6"],
};

const page = document.body.dataset.page;
const [title, subtitle, step] = PAGES[page] || ["Page", "", ""];
const shell = mountShell({ page, title, subtitle });
if (shell) {
  shell.main.append(h("section", { class: "card" },
    emptyState("Page en cours de construction", `Cette fonctionnalité sera livrée à l'${step} du développement.`)));
}
