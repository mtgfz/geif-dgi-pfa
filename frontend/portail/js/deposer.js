// Étape 1 — informations de la réclamation. Rien n'est envoyé au serveur avant l'étape 2 (pas de dossier orphelin
// si le contribuable abandonne).
import { api } from "../../assets/js/api.js";
import { aujourdhui, assistantEtapes, champ, depot, mountPortail } from "../../assets/js/portail.js";
import { h, icon } from "../../assets/js/ui.js";

const main = mountPortail({ page: "deposer", title: "Déposer une réclamation" });
const etat = depot.get();
if (etat.deposited) location.replace("confirmation.html");
else if (etat.id) location.replace("documents.html");  // dossier déjà créé : reste à joindre les pièces
else init();

async function init() {
  let motifs = { IS: [], IR: [], TVA: [] };
  try { motifs = await api.get("/reclamations/motifs", undefined, { auth: false }); } catch { /* message plus bas */ }

  const f = etat.form || {};
  const contrib = h("input", { class: "input", maxlength: "200", autocomplete: "organization", value: f.contrib || "" });
  const ifn = h("input", { class: "input", maxlength: "30", inputmode: "numeric", autocomplete: "off", value: f.ifn || "" });
  const tax = h("select", { class: "input" }, h("option", { value: "" }, "Choisir…"),
    [["IS", "IS — Impôt sur les sociétés"], ["IR", "IR — Impôt sur le revenu"], ["TVA", "TVA — Taxe sur la valeur ajoutée"]]
      .map(([v, l]) => h("option", { value: v, selected: f.tax === v }, l)));
  const motif = h("select", { class: "input", disabled: true });
  const montant = h("input", { class: "input", type: "number", min: "1", step: "any", inputmode: "decimal", value: f.montant ?? "" });
  const dateMer = h("input", { class: "input", type: "date", max: aujourdhui(), value: f.date_mer || "" });
  const periode = h("input", { class: "input", maxlength: "60", placeholder: "Ex : 2023 ou T1 2024", value: f.periode || "" });
  const email = h("input", { class: "input", type: "email", maxlength: "120", autocomplete: "email", value: f.email || "" });
  const tel = h("input", { class: "input", type: "tel", maxlength: "30", autocomplete: "tel", value: f.telephone || "" });
  const delai = h("div", { class: "alert warn full", hidden: true, style: "grid-column:1/-1" }, icon("clock"),
    "Plus de 6 mois séparent la mise en recouvrement d'aujourd'hui : votre réclamation sera bien enregistrée, et le gestionnaire examinera la question du délai.");

  const remplirMotifs = (garder) => {
    const liste = motifs[tax.value] || [];
    motif.replaceChildren(h("option", { value: "" }, tax.value ? "Choisir l'objet…" : "Choisissez d'abord l'impôt"),
      ...liste.map((m) => h("option", { value: m, selected: garder === m }, m)));
    motif.disabled = !tax.value;
  };
  remplirMotifs(f.motif);
  tax.addEventListener("change", () => remplirMotifs());
  const majDelai = () => {
    const jours = dateMer.value ? Math.floor((new Date(aujourdhui()) - new Date(dateMer.value)) / 86400000) : 0;
    delai.hidden = jours <= 180;
  };
  dateMer.addEventListener("change", majDelai); majDelai();

  const champs = {
    contrib: champ({ id: "contrib", label: "Raison sociale", requis: true, element: contrib }),
    ifn: champ({ id: "ifn", label: "Identifiant fiscal (IF)", requis: true, aide: "Figure sur vos déclarations et avis d'imposition.", element: ifn }),
    tax: champ({ id: "tax", label: "Type d'impôt", requis: true, element: tax }),
    motif: champ({ id: "motif", label: "Objet de la réclamation", requis: true, element: motif }),
    montant: champ({ id: "montant", label: "Montant contesté (MAD)", requis: true, element: montant }),
    date_mer: champ({ id: "date_mer", label: "Date de mise en recouvrement", requis: true, aide: "Indiquée sur l'avis de mise en recouvrement ou de rappel.", element: dateMer }),
    periode: champ({ id: "periode", label: "Période concernée", aide: "Facultatif — exercice ou période visée.", element: periode }),
    email: champ({ id: "email", label: "Adresse e-mail", requis: true, aide: "Vous y recevrez votre référence, votre code de suivi puis la décision.", element: email }),
    telephone: champ({ id: "telephone", label: "Téléphone", aide: "Facultatif.", element: tel }),
  };

  const regles = {
    contrib: (v) => (v.length < 2 ? "Indiquez la raison sociale." : null),
    ifn: (v) => (v.length < 3 ? "Indiquez votre identifiant fiscal." : v.length > 30 ? "30 caractères maximum." : null),
    tax: (v) => (!v ? "Choisissez le type d'impôt." : null),
    motif: (v) => (!v ? "Choisissez l'objet de la réclamation." : null),
    montant: (v) => (!(Number(v) > 0) ? "Indiquez un montant supérieur à 0." : null),
    date_mer: (v) => (!v ? "Indiquez la date de mise en recouvrement." : v > aujourdhui() ? "Cette date ne peut pas être dans le futur." : null),
    periode: () => null,
    email: (v) => (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? "Indiquez une adresse e-mail valide." : null),
    telephone: (v) => (v && !/^[0-9+().\s-]{6,30}$/.test(v) ? "Numéro de téléphone invalide." : null),
  };
  const elements = { contrib, ifn, tax, motif, montant, date_mer: dateMer, periode, email, telephone: tel };
  const lire = () => Object.fromEntries(Object.entries(elements).map(([k, el]) => [k, el.value.trim()]));

  const valider = () => {
    const v = lire(); let premier = null;
    for (const k of Object.keys(regles)) {
      const msg = regles[k](v[k]);
      champs[k].erreur(msg);
      if (msg && !premier) premier = k;
    }
    if (premier) elements[premier].focus();
    return !premier;
  };
  Object.entries(elements).forEach(([k, el]) => el.addEventListener("blur", () => champs[k].erreur(regles[k](el.value.trim()))));

  const alerte = h("div", { class: "alert error", hidden: true, role: "alert", style: "margin-bottom:18px" });
  if (!motifs.IS.length) { alerte.replaceChildren(icon("alert"), "Le service est momentanément indisponible. Réessayez dans un instant."); alerte.hidden = false; }

  const form = h("form", { novalidate: true },
    alerte,
    h("div", { class: "form-grid" },
      h("div", { class: "section-label" }, "Identification"),
      champs.contrib, champs.ifn,
      h("div", { class: "section-label" }, "Objet de la réclamation"),
      champs.tax, champs.motif, champs.montant, champs.date_mer, delai, champs.periode,
      h("div", { class: "section-label" }, "Coordonnées"),
      champs.email, champs.telephone),
    h("div", { class: "form-actions" }, h("a", { class: "btn", href: "index.html" }, "Annuler"),
      h("button", { class: "btn btn-primary btn-lg", type: "submit" }, "Continuer", icon("right"))));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!valider()) return;
    depot.set({ form: lire() });
    location.href = "documents.html";
  });

  main.append(assistantEtapes(1),
    h("div", { class: "p-title" }, h("h1", {}, "Votre réclamation"), h("p", {}, "Les champs marqués d'un * sont obligatoires.")),
    h("div", { class: "p-card" }, form));
  contrib.focus();
}
