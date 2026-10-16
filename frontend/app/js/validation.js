// Validation : le Chef de Service / Chef de Subdivision lit les pièces, le rapport et la décision, puis valide
// ou retourne le dossier au gestionnaire avec un commentaire obligatoire.
import { api } from "../../assets/js/api.js";
import { badgeSource, carteAmmc, chargerDossier, sectionArticles, sectionPieces, titreEtape } from "../../assets/js/dossier.js";
import { mountShell } from "../../assets/js/layout.js";
import {
  circuitDossier, confirmer, decisionBadge, faitsDossier, flash, formatDateTime, formatMoney, formatRef, h, icon, statusBadge, toast,
} from "../../assets/js/ui.js";

const CONFIG = {
  chef_service: {
    attendu: "envoyee_chef_service", route: "decision-service", valider: "Valider et transmettre au Chef de Subdivision",
    messageValider: "Le dossier sera transmis au Chef de Subdivision pour validation finale.",
    messageToast: "Dossier transmis au Chef de Subdivision.",
  },
  chef_subdivision: {
    attendu: "envoyee_chef_subdivision", route: "decision-subdivision", valider: "Validation finale et envoi au contribuable",
    messageValider: "Validation FINALE : la décision sera envoyée au contribuable (page Suivi et e-mail) et le dossier sera archivé dans l'Historique. Cette action est définitive.",
    messageToast: "Décision envoyée au contribuable.",
  },
};

const params = new URLSearchParams(location.search);
const id = params.get("id");
const shell = mountShell({ page: "validation", title: "Validation", subtitle: "" });

async function init({ main, setHeader, user }) {
  const cfg = CONFIG[user.role];
  setHeader("Validation", "Chargement…");

  if (!id) {  // « Validation » dans le menu : on ouvre le dossier le plus ancien en attente
    try {
      const { items } = await api.get("/reclamations", { scope: "accueil", limit: 100 });
      const cible = [...items].sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
      if (cible) { location.replace(`validation.html?id=${encodeURIComponent(cible.id)}`); return; }
      setHeader("Validation", "Dossiers en attente de votre validation.");
      main.append(h("section", { class: "card" }, h("div", { class: "empty" }, h("h3", {}, "Aucun dossier en attente"),
        h("p", {}, "Rien n'attend votre validation pour le moment."),
        h("a", { class: "btn btn-primary", href: "accueil.html", style: "margin-top:14px" }, "Retour à l'accueil"))));
    } catch (e) { main.append(h("div", { class: "alert error" }, icon("alert"), e.message)); }
    return;
  }

  const zone = h("div");
  main.append(zone);
  try {
    const [d, docs] = await chargerDossier(id);
    afficher(d, docs);
  } catch (e) {
    zone.replaceChildren(h("div", { class: "alert error" }, icon("alert"), e.message));
  }

  function afficher(d, docs) {
    const transmis = [...(d.historique || [])].reverse().find((e) => e.vers === cfg.attendu);
    setHeader("Validation du dossier", `${d.contrib} · ${formatRef(d.id)}`, [
      statusBadge(d.status), h("a", { class: "btn", href: "accueil.html" }, "Retour à l'accueil"),
    ]);
    const enAttente = d.status === cfg.attendu;
    const gauche = h("div", { class: "stack" });
    const droite = h("div", { class: "sticky" });

    if (!enAttente) {
      gauche.append(h("div", { class: "alert info" }, icon("alert"),
        `Ce dossier n'est pas (ou plus) en attente de votre validation : statut « ${d.status_label} ».`));
    } else if (transmis) {
      gauche.append(h("div", { class: "alert info" }, icon("send"),
        `Transmis par ${transmis.par} le ${formatDateTime(transmis.date)}.`));
    }

    gauche.append(
      h("section", { class: "card card-pad" }, titreEtape(1, "Pièces du contribuable", "Ouvrez les originaux ; le texte et les champs lus automatiquement sont affichés pour vérification."), sectionPieces(d.id, docs, d.ifn)),
      h("section", { class: "card card-pad" }, titreEtape(2, "Articles du CGI retenus"), sectionArticles(d)),
    );

    // --- rapport et décision (lecture seule, correction possible)
    const rapport = h("textarea", { class: "input", rows: "15", readonly: true, "aria-label": "Rapport d'instruction" });
    const decision = h("textarea", { class: "input", rows: "6", readonly: true, "aria-label": "Décision" });
    rapport.value = d.rapport || ""; decision.value = d.decision || "";
    const instant = () => rapport.value + "\u0000" + decision.value;
    let enregistre = instant();
    const indicateur = h("span", { class: "dirty", hidden: true }, icon("alert"), "Corrections non enregistrées");
    const maj = () => { indicateur.hidden = instant() === enregistre; };
    [rapport, decision].forEach((el) => el.addEventListener("input", maj));
    window.addEventListener("beforeunload", (e) => { if (instant() !== enregistre) { e.preventDefault(); e.returnValue = ""; } });

    const corriger = h("button", { class: "btn btn-sm", type: "button" }, icon("edit"), "Corriger le texte");
    corriger.addEventListener("click", () => {
      const lecture = !rapport.readOnly;
      rapport.readOnly = decision.readOnly = lecture;
      corriger.replaceChildren(icon("edit"), lecture ? "Corriger le texte" : "Terminer la correction");
      if (!lecture) rapport.focus();
    });
    gauche.append(h("section", { class: "card card-pad" },
      titreEtape(3, "Rapport d'instruction et décision proposée"),
      h("div", { class: "editor-meta", style: "margin-bottom:16px" }, decisionBadge(d.type_decision), badgeSource(d.source_texte),
        d.article ? h("span", { class: "tag" }, d.article) : null,
        h("span", { class: "muted" }, `Montant dégrevé : ${formatMoney(d.montant_degreve)} sur ${formatMoney(d.montant)} contestés`),
        enAttente ? h("span", { style: "margin-left:auto" }, corriger) : null),
      h("div", { class: "editor-grid" },
        h("div", { class: "field" }, h("label", {}, "Rapport d'instruction"), rapport),
        h("div", { class: "field" }, h("label", {}, "Décision"), decision))));

    // --- actions
    droite.append(h("section", { class: "card card-pad" }, h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:14px" },
      h("h2", { style: "font-size:16px" }, "Dossier"), h("span", { class: "tag" }, d.tax)), faitsDossier(d)));

    if (enAttente) {
      const boutons = [];
      const occupe = (b) => boutons.forEach((x) => (x.disabled = b));
      const sauver = async () => {
        await api.post(`/reclamations/${encodeURIComponent(d.id)}/brouillon`, { rapport_finale: rapport.value, decision_finale: decision.value });
        enregistre = instant(); maj();
      };
      const btnSave = h("button", { class: "btn btn-block", type: "button", hidden: true }, icon("save"), "Enregistrer mes corrections");
      const btnOk = h("button", { class: "btn btn-primary btn-block", type: "button", style: "padding:12px" }, icon("check"), cfg.valider);
      const btnRet = h("button", { class: "btn btn-block", type: "button", style: "color:var(--red);border-color:#f0b9b4" }, icon("undo"), "Retourner au gestionnaire");
      boutons.push(btnSave, btnOk, btnRet);
      const montrerSave = () => { btnSave.hidden = instant() === enregistre; };
      [rapport, decision].forEach((el) => el.addEventListener("input", montrerSave));

      btnSave.addEventListener("click", async () => {
        occupe(true);
        try { await sauver(); toast("Corrections enregistrées.", "success"); montrerSave(); } catch (e) { toast(e.message, "error"); }
        occupe(false);
      });
      btnOk.addEventListener("click", async () => {
        const choix = await confirmer({ titre: cfg.valider + " ?", message: cfg.messageValider, bouton: "Valider", danger: false });
        if (!choix) return;
        occupe(true);
        try {
          if (instant() !== enregistre) await sauver();
          const r = await api.post(`/reclamations/${encodeURIComponent(d.id)}/${cfg.route}`, { outcome: "accept" });
          const suffixe = user.role === "chef_subdivision" ? (r.email_envoye ? " Un e-mail a été envoyé au contribuable." : " (E-mail non envoyé : la décision reste consultable dans la page Suivi.)") : "";
          flash(cfg.messageToast + suffixe);
          location.href = "accueil.html";
        } catch (e) { toast(e.message, "error"); occupe(false); }
      });
      btnRet.addEventListener("click", async () => {
        const choix = await confirmer({
          titre: "Retourner au gestionnaire ?", bouton: "Retourner le dossier", danger: true,
          message: "Le dossier reviendra dans la file du gestionnaire avec votre commentaire.",
          champ: { label: "Motif du retour (obligatoire)", placeholder: "Ex : préciser la base légale, joindre la pièce manquante…", min: 3 },
        });
        if (!choix) return;
        occupe(true);
        try {
          await api.post(`/reclamations/${encodeURIComponent(d.id)}/${cfg.route}`, { outcome: "return", commentaire: choix.valeur });
          flash("Dossier retourné au gestionnaire.");
          location.href = "accueil.html";
        } catch (e) { toast(e.message, "error"); occupe(false); }
      });
      droite.append(h("section", { class: "card actions-card" }, h("h2", { style: "font-size:16px" }, "Décision"), indicateur, btnSave, btnOk, btnRet));
    }
    const ammc = h("div", { hidden: true });
    carteAmmc(d).then((c) => { if (c) { ammc.replaceChildren(c); ammc.hidden = false; } });
    droite.append(ammc, h("section", { class: "card card-pad" }, h("h2", { style: "font-size:16px;margin-bottom:14px" }, "Circuit du dossier"), circuitDossier(d.historique)));
    zone.replaceChildren(h("div", { class: "layout-2col" }, gauche, droite));
  }
}

// Appel en toute fin de fichier : toutes les constantes ci-dessus doivent exister avant init()
if (shell) init(shell);
