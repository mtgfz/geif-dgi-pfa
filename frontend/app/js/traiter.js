// Traiter : le gestionnaire lance « Traiter la réclamation » (pièces lues, articles du CGI via RAG, rapport + décision
// par le modèle de langage), modifie le texte, puis valide et envoie au Chef de Service.
import { api } from "../../assets/js/api.js";
import { badgeSource, chargerDossier, sectionArticles, sectionPieces, titreEtape } from "../../assets/js/dossier.js";
import { mountShell } from "../../assets/js/layout.js";
import {
  circuitDossier, confirmer, decisionBadge, faitsDossier, flash, formatMoney, formatRef, h, icon, statusBadge, toast,
} from "../../assets/js/ui.js";

const params = new URLSearchParams(location.search);
const id = params.get("id");
const shell = mountShell({ page: "traiter", title: "Traiter une réclamation", subtitle: "" });
if (shell) init(shell);

async function ouvrirSuivant(main) {
  const { items } = await api.get("/reclamations", { scope: "accueil", status: "retournee,en_traitement,nouvelle", limit: 100 });
  const plusAncien = (statut) => [...items].filter((r) => r.status === statut).sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
  const cible = plusAncien("retournee") || plusAncien("en_traitement") || plusAncien("nouvelle");
  if (cible) { location.replace(`traiter.html?id=${encodeURIComponent(cible.id)}`); return; }
  main.append(h("section", { class: "card" }, h("div", { class: "empty" },
    h("h3", {}, "Aucune réclamation à traiter"), h("p", {}, "Votre file d'attente est vide."),
    h("a", { class: "btn btn-primary", href: "accueil.html", style: "margin-top:14px" }, "Retour à l'accueil"))));
}

async function init({ main, setHeader }) {
  setHeader("Traiter une réclamation", "Chargement…");
  if (!id) {
    try { await ouvrirSuivant(main); } catch (e) { main.append(h("div", { class: "alert error" }, icon("alert"), e.message)); }
    return;
  }
  const zone = h("div");
  main.append(zone);
  const charger = async () => {
    zone.replaceChildren(h("div", { class: "skeleton", style: "height:200px" }));
    try {
      const [d, docs] = await chargerDossier(id);
      afficher(d, docs);
    } catch (e) {
      zone.replaceChildren(h("div", { class: "alert error" }, icon("alert"), e.message));
      setHeader("Traiter une réclamation", "");
    }
  };

  // ------------------------------------------------------------------ rendu
  function afficher(d, docs) {
    setHeader("Traiter la réclamation", `${d.contrib} · ${formatRef(d.id)}`, [
      statusBadge(d.status), h("a", { class: "btn", href: "accueil.html" }, "Retour à l'accueil"),
    ]);
    const resume = h("section", { class: "card card-pad" }, h("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:14px" },
      h("h2", { style: "font-size:16px" }, "Dossier"), h("span", { class: "tag" }, d.tax)), faitsDossier(d));
    const circuit = h("section", { class: "card card-pad" }, h("h2", { style: "font-size:16px;margin-bottom:14px" }, "Circuit du dossier"), circuitDossier(d.historique));

    const editable = d.status === "en_traitement" && (d.rapport || d.decision);
    const aTexte = !!(d.rapport || d.decision);  // un seul des deux suffit : le gestionnaire complète l'autre
    const gauche = h("div", { class: "stack" });
    const droite = h("div", { class: "sticky" });

    if (!["nouvelle", "en_traitement", "retournee"].includes(d.status)) {
      gauche.append(h("div", { class: "alert info" }, icon("alert"),
        `Ce dossier n'est plus modifiable : statut « ${d.status_label} ». Consultez-le dans l'Historique ou suivez-le depuis l'Accueil.`));
    }
    if (d.status === "retournee" && d.commentaire_retour) {
      gauche.append(h("div", { class: "alert error" }, icon("undo"), h("div", {}, h("strong", {}, "Retourné par votre hiérarchie : "), d.commentaire_retour)));
    }

    if (!aTexte || d.status === "retournee") {  // avant le traitement, ou dossier retourné à reprendre
      gauche.append(carteDepart(d, docs));
    } else {
      gauche.append(
        h("section", { class: "card card-pad" }, titreEtape(1, "Pièces lues", "Texte et champs clés extraits des documents déposés par le contribuable."), sectionPieces(d.id, docs, d.ifn)),
        h("section", { class: "card card-pad" }, titreEtape(2, "Articles du CGI retrouvés", "Recherche sémantique dans le Code Général des Impôts à partir du motif de la réclamation."), sectionArticles(d)),
        editable ? editeur(d, droite) : lectureSeule(d));
    }
    droite.prepend(resume);
    droite.append(circuit);
    zone.replaceChildren(h("div", { class: "layout-2col" }, gauche, droite));
  }

  // ------------------------------------------------------------------ avant le traitement
  function carteDepart(d, docs) {
    const retour = d.status === "retournee";
    const bouton = h("button", { class: "btn btn-primary", type: "button" }, icon("sparkles"), retour ? "Reprendre le traitement" : "Traiter la réclamation");
    const carte = h("section", { class: "card hero" },
      h("div", { class: "ico" }, icon("sparkles")),
      h("h2", {}, retour ? "Reprendre le dossier" : "Prêt à traiter"),
      h("p", {}, retour
        ? "Votre texte précédent est conservé. Vous pouvez le corriger en tenant compte du commentaire de votre hiérarchie."
        : "GEIF va lire les pièces déposées, rechercher les articles pertinents du CGI et préparer un rapport d'instruction ainsi qu'une proposition de décision, que vous pourrez modifier avant de les envoyer."),
      bouton);
    if (!docs.length) carte.append(h("div", { class: "alert warn", style: "margin:20px auto 0;max-width:520px;text-align:left" }, icon("alert"), "Aucune pièce déposée : le rapport s'appuiera uniquement sur les informations saisies par le contribuable."));
    else if (docs.some((p) => !p.ocr_ok)) carte.append(h("div", { class: "alert warn", style: "margin:20px auto 0;max-width:520px;text-align:left" }, icon("alert"), "Certaines pièces n'ont pas pu être lues automatiquement : consultez-les manuellement."));
    if (docs.length) carte.append(h("div", { style: "margin-top:22px;text-align:left" }, h("h4", { style: "font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-bottom:8px" }, `Pièces déposées (${docs.length})`), sectionPieces(d.id, docs, d.ifn)));

    bouton.addEventListener("click", async () => {
      bouton.disabled = true;
      carte.replaceChildren(h("div", { class: "ico" }, icon("loader", "spin")), h("h2", {}, "Traitement en cours…"),
        h("p", {}, "La première analyse peut prendre jusqu'à une minute (chargement du modèle de recherche)."),
        h("ul", { class: "progress-list" }, [
          "Lecture des pièces jointes", "Recherche des articles du Code Général des Impôts", "Rédaction du rapport d'instruction et de la décision",
        ].map((t) => h("li", {}, icon("loader", "spin"), t))));
      try {
        await api.post(`/reclamations/${encodeURIComponent(d.id)}/traiter`);
        toast("Traitement terminé. Relisez et modifiez le texte avant de l'envoyer.", "success");
        await charger();
        shell.refreshCounts();
      } catch (e) { toast(e.message, "error"); await charger(); }
    });
    return carte;
  }

  // ------------------------------------------------------------------ lecture seule (dossier déjà envoyé)
  function lectureSeule(d) {
    return h("section", { class: "card card-pad" }, titreEtape(3, "Rapport et décision"), decisionBadge(d.type_decision),
      h("h4", { style: "margin:14px 0 6px" }, "Rapport d'instruction"), h("div", { class: "prose" }, d.rapport),
      h("h4", { style: "margin:14px 0 6px" }, "Décision"), h("div", { class: "prose" }, d.decision));
  }

  // ------------------------------------------------------------------ éditeur
  function editeur(d, droite) {
    const rapport = h("textarea", { class: "input", rows: "17", id: "rapport", "aria-label": "Rapport d'instruction" });
    const decision = h("textarea", { class: "input", rows: "7", id: "decision", "aria-label": "Décision" });
    const type = h("select", { class: "input", id: "type", style: "max-width:240px" },
      ["Rejet", "Dégrèvement total", "Dégrèvement partiel"].map((t) => h("option", { value: t }, t)));
    rapport.value = d.rapport; decision.value = d.decision; type.value = d.type_decision || "Dégrèvement partiel";
    const instant = () => JSON.stringify([rapport.value, decision.value, type.value]);
    let enregistre = instant();
    let precedent = null;
    const indicateur = h("span", { class: "dirty", hidden: true }, icon("alert"), "Modifications non enregistrées");
    const majEtat = () => { indicateur.hidden = instant() === enregistre; };
    [rapport, decision].forEach((el) => el.addEventListener("input", majEtat));
    type.addEventListener("change", majEtat);
    window.addEventListener("beforeunload", (e) => { if (instant() !== enregistre) { e.preventDefault(); e.returnValue = ""; } });

    // --- assistant de reformulation
    const consigne = h("input", { class: "input", maxlength: "300", placeholder: "Ex : ajoute une phrase sur le délai de réclamation, ton plus sobre…", "aria-label": "Consigne pour l'assistant" });
    const reform = h("button", { class: "btn", type: "button" }, icon("sparkles"), "Reformuler");
    const annuler = h("button", { class: "btn btn-sm", type: "button", hidden: true }, icon("undo"), "Annuler la reformulation");
    reform.addEventListener("click", async () => {
      if (!consigne.value.trim()) { consigne.focus(); return; }
      reform.disabled = true;
      try {
        const r = await api.post(`/reclamations/${encodeURIComponent(d.id)}/reformuler`, { instruction: consigne.value.trim() });
        precedent = [rapport.value, decision.value];
        rapport.value = r.rapport; decision.value = r.decision; annuler.hidden = false; majEtat();
        toast("Proposition de l'assistant appliquée : relisez-la avant de valider.", "success");
      } catch (e) { toast(e.message, "error"); }
      reform.disabled = false;
    });
    annuler.addEventListener("click", () => { if (precedent) { [rapport.value, decision.value] = precedent; precedent = null; annuler.hidden = true; majEtat(); } });

    // --- actions
    const corps = () => ({ rapport_finale: rapport.value, decision_finale: decision.value, type_decision: type.value });
    const boutons = [];
    const occupe = (b) => { boutons.forEach((x) => (x.disabled = b)); };
    const enregistrer = async (silencieux = false) => {
      await api.post(`/reclamations/${encodeURIComponent(d.id)}/brouillon`, corps());
      enregistre = instant(); majEtat();
      if (!silencieux) toast("Brouillon enregistré.", "success");
    };
    const btnSave = h("button", { class: "btn btn-block", type: "button" }, icon("save"), "Enregistrer le brouillon");
    const btnRegen = h("button", { class: "btn btn-ghost btn-block", type: "button" }, icon("refresh"), "Régénérer le texte");
    const btnSend = h("button", { class: "btn btn-primary btn-block", type: "button", style: "padding:12px" }, icon("send"), "Valider et envoyer au Chef de Service");
    boutons.push(btnSave, btnRegen, btnSend);

    btnSave.addEventListener("click", async () => { occupe(true); try { await enregistrer(); } catch (e) { toast(e.message, "error"); } occupe(false); });
    btnRegen.addEventListener("click", async () => {
      const ok = await confirmer({ titre: "Régénérer le texte ?", message: "Le rapport et la décision actuels seront remplacés par une nouvelle proposition. Vos modifications seront perdues.", bouton: "Régénérer", danger: true });
      if (!ok) return;
      occupe(true);
      try { await api.post(`/reclamations/${encodeURIComponent(d.id)}/traiter?regenerer=true`); enregistre = instant(); await charger(); toast("Nouvelle proposition générée.", "success"); }
      catch (e) { toast(e.message, "error"); occupe(false); }
    });
    btnSend.addEventListener("click", async () => {
      if (!rapport.value.trim() || !decision.value.trim()) { toast("Le rapport et la décision ne peuvent pas être vides.", "error"); return; }
      const choix = await confirmer({
        titre: "Envoyer au Chef de Service ?", bouton: "Valider et envoyer",
        message: "Le dossier quittera votre file d'attente. Indiquez ce que vous avez fait de la proposition automatique (cela alimente l'amélioration des propositions futures) :",
        options: [
          { value: "accept", label: "J'ai retenu la proposition", hint: "Telle quelle, ou avec mes corrections." },
          { value: "reject", label: "J'ai rejeté la proposition", hint: "J'ai rédigé la décision moi-même, la proposition était inadaptée." },
        ],
      });
      if (!choix) return;
      occupe(true);
      try {
        await api.post(`/reclamations/${encodeURIComponent(d.id)}/decision`, { outcome: choix.option, ...corps() });
        enregistre = instant();
        flash("Dossier envoyé au Chef de Service.");
        location.href = "accueil.html";
      } catch (e) { toast(e.message, "error"); occupe(false); }
    });
    droite.append(h("section", { class: "card actions-card" }, h("h2", { style: "font-size:16px" }, "Actions"), indicateur, btnSave, btnRegen, h("div", { class: "sep" }), btnSend));

    return h("section", { class: "card card-pad" },
      titreEtape(3, "Rapport d'instruction et décision", "Modifiez librement le texte, puis validez."),
      h("div", { class: "editor-meta", style: "margin-bottom:16px" }, badgeSource(d.source_texte),
        d.article ? h("span", { class: "tag" }, d.article) : null,
        h("span", { class: "muted" }, `Montant dégrevé calculé : ${formatMoney(d.montant_degreve)}`)),
      h("div", { class: "editor-grid" },
        h("div", { class: "field" }, h("label", { for: "rapport" }, "Rapport d'instruction"), rapport),
        h("div", { class: "field" }, h("label", { for: "decision" }, "Décision proposée"), decision),
        h("div", { class: "field" }, h("label", { for: "type" }, "Type de décision"), type,
          h("span", { class: "hint" }, "Sert aux statistiques. Le montant dégrevé provient de la règle appliquée.")),
        h("div", { class: "assistant-box" }, h("div", { class: "field" }, h("label", {}, "Assistant de rédaction"), consigne), reform, annuler)));
  }

  await charger();
}
