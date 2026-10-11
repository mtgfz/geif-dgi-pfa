// Étape 3 — confirmation : référence unique + code secret.
import { assistantEtapes, depot, mountPortail } from "../../assets/js/portail.js";
import { faitsPublics } from "./commun.js";
import { h, icon, toast } from "../../assets/js/ui.js";

const main = mountPortail({ page: "deposer", title: "Confirmation" });
const d = depot.get();
if (!d.id || !d.cle || !d.deposited) location.replace("deposer.html");
else init();

async function copier(texte, libelle) {
  try { await navigator.clipboard.writeText(texte); }
  catch {
    const t = h("textarea", { style: "position:fixed;opacity:0" }, texte); document.body.append(t); t.select();
    try { document.execCommand("copy"); } catch { /* rien */ }
    t.remove();
  }
  toast(`${libelle} copié.`, "success");
}

function boiteCode(libelle, valeur) {
  return h("div", { class: "code-box" }, h("span", {}, libelle), h("strong", { "data-testid": libelle }, valeur),
    h("button", { class: "btn btn-sm no-print", type: "button", onclick: () => copier(valeur, libelle) }, "Copier"));
}

function init() {
  const f = d.form || {};
  const emailNote = d.emailEnvoye
    ? h("div", { class: "alert info", style: "text-align:left" }, icon("send"), `Un e-mail récapitulatif a été envoyé à ${f.email}.`)
    : h("div", { class: "alert warn", style: "text-align:left" }, icon("alert"),
        "L'e-mail de confirmation n'a pas pu être envoyé : notez bien votre référence et votre code ci-dessous, ils ne seront pas réaffichés.");

  main.append(assistantEtapes(4),
    h("div", { class: "p-card success" },
      h("div", { class: "ok-ico" }, icon("check")),
      h("h1", {}, "Votre réclamation est enregistrée"),
      h("p", { class: "muted", style: "margin-top:8px" }, "Conservez précieusement ces deux informations : elles sont nécessaires pour suivre votre dossier et consulter la décision."),
      h("div", { class: "codes" }, boiteCode("Référence", d.id), boiteCode("Code de suivi", d.cle)),
      h("div", { class: "alert error no-print", style: "text-align:left" }, icon("shield"),
        "Le code de suivi est secret et ne sera plus affiché une fois cette page quittée. Ne le communiquez à personne."),
      h("div", { style: "margin-top:12px" }, emailNote),
      h("div", { class: "recap" }, h("h2", {}, "Récapitulatif"), faitsPublics(f)),
      h("ol", { class: "next-steps" },
        h("li", {}, "Un gestionnaire des impôts instruit votre dossier à partir des pièces jointes."),
        h("li", {}, "Il est ensuite validé par le Chef de Service puis par le Chef de Subdivision."),
        h("li", {}, "La décision vous est notifiée sur la page de suivi (et par e-mail).")),
      h("div", { class: "center-actions" },
        h("a", { class: "btn btn-primary btn-lg", href: `suivi.html?ref=${encodeURIComponent(d.id)}`, onclick: () => {} }, icon("search"), "Suivre ma réclamation"),
        h("button", { class: "btn btn-lg", type: "button", onclick: () => window.print() }, "Imprimer le récapitulatif"),
        h("button", { class: "btn btn-lg btn-ghost", type: "button", onclick: () => { depot.clear(); location.href = "index.html"; } }, "J'ai noté mon code — terminer"))));
}
