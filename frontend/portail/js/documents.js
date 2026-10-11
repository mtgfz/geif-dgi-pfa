// Étape 2 — pièces justificatives. À l'envoi : (1) création du dossier, (2) dépôt des fichiers. Si l'étape 2 échoue,
// le dossier existe déjà : on conserve sa référence/son code et seul le dépôt des fichiers est rejoué.
import { ApiError, api } from "../../assets/js/api.js";
import { aujourdhui, assistantEtapes, champ, depot, mountPortail } from "../../assets/js/portail.js";
import { formatSize, h, icon } from "../../assets/js/ui.js";

const main = mountPortail({ page: "deposer", title: "Documents justificatifs" });
const etat = depot.get();

const TYPES = { pdf: "application/pdf", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg" };
const MAX_OCTETS = 10 * 1024 * 1024;
const MAX_OPTIONNELS = 5;
const MAX_DESC = 50;
const typeDe = (f) => f.type || TYPES[(f.name.split(".").pop() || "").toLowerCase()] || "";

function zone({ titre, obligatoire, description, retirer }) {
  let fichier = null;
  const input = h("input", { type: "file", accept: ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg", "aria-label": `Fichier : ${titre}` });
  const nom = h("span", { class: "file-name" }, "Aucun fichier choisi");
  const desc = h("input", { class: "input", maxlength: String(MAX_DESC), value: description || "", placeholder: "Ex : relevé de TVA du 1er trimestre" });
  const compteur = h("div", { class: "counter" });
  const maj = () => { compteur.textContent = `${desc.value.length} / ${MAX_DESC}`; };
  desc.addEventListener("input", maj); maj();
  const cDesc = champ({ id: "d" + Math.random().toString(36).slice(2, 8), label: "Description du document", requis: true, element: desc });
  const erreurFichier = h("div", { class: "field-error", role: "alert" });
  const boite = h("div", { class: "drop" },
    h("div", { class: "opt-head" }, h("h3", {}, icon("file"), titre, obligatoire ? h("span", { class: "badge plain tone-red" }, "Obligatoire") : h("span", { class: "badge plain tone-slate" }, "Facultatif")),
      retirer ? h("button", { class: "btn btn-sm btn-ghost", type: "button", onclick: retirer }, icon("x"), "Retirer") : null),
    h("div", { class: "file-row" },
      h("div", { class: "file-pick" }, h("span", { class: "btn" }, icon("file"), "Choisir un fichier"), input), nom),
    erreurFichier, cDesc, compteur);
  input.addEventListener("change", () => {
    fichier = input.files[0] || null;
    nom.textContent = fichier ? `${fichier.name} · ${formatSize(fichier.size)}` : "Aucun fichier choisi";
    boite.classList.toggle("has-file", !!fichier);
    erreurFichier.textContent = "";
  });
  return {
    el: boite,
    vide: () => !fichier && !desc.value.trim(),
    fichier: () => fichier,
    description: () => desc.value.trim(),
    valider() {
      let msg = null;
      if (!fichier) msg = "Choisissez un fichier.";
      else if (!typeDe(fichier) || !Object.values(TYPES).includes(typeDe(fichier))) msg = "Format non accepté (PDF, PNG ou JPG uniquement).";
      else if (fichier.size > MAX_OCTETS) msg = "Fichier trop volumineux (10 Mo maximum).";
      else if (fichier.size === 0) msg = "Ce fichier est vide.";
      erreurFichier.textContent = msg || "";
      const msgDesc = !desc.value.trim() ? "Décrivez brièvement ce document." : null;
      cDesc.erreur(msgDesc);
      return !msg && !msgDesc;
    },
  };
}

function init() {
  const obligatoire = zone({ titre: "Demande de dégrèvement", obligatoire: true, description: "Demande de dégrèvement" });
  const optionnelles = [];
  const listeOpt = h("div", { class: "opt-list" });
  const ajouter = h("button", { class: "btn", type: "button" }, icon("file"), "Ajouter un document");
  const majAjout = () => { ajouter.hidden = optionnelles.length >= MAX_OPTIONNELS; ajouter.textContent = ""; ajouter.append(icon("file"), `Ajouter un document (${optionnelles.length}/${MAX_OPTIONNELS})`); };
  ajouter.addEventListener("click", () => {
    const z = zone({ titre: `Document complémentaire ${optionnelles.length + 1}`, obligatoire: false,
      retirer: () => { optionnelles.splice(optionnelles.indexOf(z), 1); z.el.remove(); majAjout(); } });
    optionnelles.push(z); listeOpt.append(z.el); majAjout();
  });
  majAjout();

  const alerte = h("div", { class: "alert error", hidden: true, role: "alert", style: "margin-bottom:18px" });
  const montrer = (msg) => { alerte.replaceChildren(icon("alert"), msg); alerte.hidden = false; alerte.scrollIntoView({ block: "center" }); };
  const envoyer = h("button", { class: "btn btn-primary btn-lg", type: "submit" }, icon("send"), "Envoyer ma réclamation");
  const retour = etat.id ? null : h("a", { class: "btn", href: "deposer.html" }, icon("left"), "Modifier mes informations");

  const form = h("form", { novalidate: true }, alerte,
    h("p", { class: "muted", style: "margin-bottom:18px" }, "Formats acceptés : PDF, PNG, JPG — 10 Mo maximum par fichier. Vos documents sont lus automatiquement pour faciliter l'instruction."),
    obligatoire.el, listeOpt, h("div", { style: "margin-top:14px" }, ajouter),
    h("div", { class: "form-actions" }, retour || h("span"), envoyer));

  form.addEventListener("submit", async (e) => {
    e.preventDefault(); alerte.hidden = true;
    const zones = [obligatoire, ...optionnelles.filter((z) => !z.vide())];
    optionnelles.filter((z) => z.vide()).forEach((z) => z.el.remove());  // lignes laissées entièrement vides : ignorées
    optionnelles.splice(0, optionnelles.length, ...optionnelles.filter((z) => !z.vide()));
    const tousValides = zones.map((z) => z.valider()).every(Boolean);
    if (!tousValides) { form.querySelector(".field-error:not(:empty)")?.scrollIntoView({ block: "center" }); return; }

    envoyer.disabled = true;
    envoyer.replaceChildren(icon("loader", "spin"), "Envoi et lecture des documents…");
    try {
      let courant = depot.get();
      if (!courant.id) {
        const f = courant.form;
        const r = await api.post("/reclamations", { ...f, montant: Number(f.montant), date_reclam: aujourdhui(),
          email: f.email || null, telephone: f.telephone || null, periode: f.periode || null }, { auth: false });
        depot.set({ id: r.id, cle: r.cle_verification, emailEnvoye: !!r.email_confirmation_envoye });
        courant = depot.get();
      }
      const fd = new FormData();
      fd.append("cle", courant.cle);
      const fichierOk = (z) => new File([z.fichier()], z.fichier().name, { type: typeDe(z.fichier()) });
      fd.append("demande_degrevement", fichierOk(obligatoire));
      fd.append("description_demande", obligatoire.description());
      for (const z of optionnelles) { fd.append("documents_optionnels", fichierOk(z)); fd.append("descriptions_optionnelles", z.description()); }
      try {
        await api.upload(`/reclamations/${encodeURIComponent(courant.id)}/documents`, fd);
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 409 && /déjà/.test(err.message))) throw err;  // déjà déposés : on continue
      }
      depot.set({ deposited: true });
      location.href = "confirmation.html";
    } catch (err) {
      const cree = depot.get().id;
      montrer(cree
        ? `Votre dossier est enregistré (référence ${depot.get().id}) mais l'envoi des documents a échoué : ${err.message} Corrigez puis renvoyez.`
        : err.message);
      envoyer.disabled = false;
      envoyer.replaceChildren(icon("send"), "Envoyer ma réclamation");
    }
  });

  main.append(assistantEtapes(2),
    h("div", { class: "p-title" }, h("h1", {}, "Vos justificatifs"), h("p", {}, "Joignez la demande de dégrèvement et, si besoin, jusqu'à 5 pièces complémentaires.")),
    h("div", { class: "p-card" }, form));
}

// Appel placé en fin de fichier : toutes les constantes ci-dessus doivent être définies avant init()
if (etat.deposited) location.replace("confirmation.html");
else if (!etat.form) location.replace("deposer.html");
else init();
