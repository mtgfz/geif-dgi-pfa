// Suivi : référence + code → frise d'avancement et, une fois la décision validée, la décision.
import { api } from "../../assets/js/api.js";
import { champ, mountPortail } from "../../assets/js/portail.js";
import { decisionBadge, formatDate, formatDateTime, formatMoney, h, icon, relativeTime, STATUS_META } from "../../assets/js/ui.js";

const main = mountPortail({ page: "suivi", title: "Suivre ma réclamation" });
const params = new URLSearchParams(location.search);

const ref = h("input", { class: "input", maxlength: "40", autocomplete: "off", spellcheck: "false", placeholder: "REC-2026-123456", value: params.get("ref") || "" });
const cle = h("input", { class: "input", maxlength: "20", autocomplete: "off", spellcheck: "false", placeholder: "XXXX-XXXX" });
const cRef = champ({ id: "ref", label: "Référence de la réclamation", element: ref });
const cCle = champ({ id: "cle", label: "Code de suivi", element: cle });
const alerte = h("div", { class: "alert error", hidden: true, role: "alert", style: "margin-top:16px" });
const resultat = h("div", { class: "cible", "aria-live": "polite" });
const bouton = h("button", { class: "btn btn-primary btn-lg", type: "submit" }, icon("search"), "Consulter");

const form = h("form", { class: "suivi-form", novalidate: true }, cRef, cCle, bouton);
form.addEventListener("submit", (e) => { e.preventDefault(); consulter(); });

main.append(
  h("div", { class: "p-title", style: "max-width:900px" }, h("h1", {}, "Suivre ma réclamation"),
    h("p", {}, "Saisissez la référence et le code de suivi reçus à la fin du dépôt (et par e-mail).")),
  h("div", { class: "p-card", style: "max-width:900px" }, form, alerte),
  h("div", { style: "max-width:900px;margin:0 auto" }, resultat));
(params.get("ref") ? cle : ref).focus();

async function consulter() {
  alerte.hidden = true; cRef.erreur(""); cCle.erreur("");
  const r = ref.value.trim().toUpperCase(), c = cle.value.trim().toUpperCase();
  if (!r) { cRef.erreur("Saisissez la référence."); ref.focus(); return; }
  if (!c) { cCle.erreur("Saisissez le code de suivi."); cle.focus(); return; }
  bouton.disabled = true; bouton.replaceChildren(icon("loader", "spin"), "Recherche…");
  try {
    const d = await api.get(`/reclamations/suivi/${encodeURIComponent(r)}`, { cle: c }, { auth: false });
    afficher(d, r, c);
  } catch (e) {
    resultat.replaceChildren();
    alerte.replaceChildren(icon("alert"), e.message); alerte.hidden = false;
  }
  bouton.disabled = false; bouton.replaceChildren(icon("search"), "Consulter");
}

function afficher(d, r, c) {
  const meta = { tone: d.status === "retournee" ? "amber" : (STATUS_META[d.status] || { tone: "slate" }).tone };  // « retournée » : pas d'alarme côté contribuable
  const etapes = h("ol", { class: "vstepper" }, d.etapes.map((e) =>
    h("li", { class: `${e.etat}${e.statut === "decision_envoyee" ? " final" : ""}`, "aria-current": e.etat === "en_cours" ? "step" : null },
      h("span", { class: "vs-dot" }, e.etat === "fait" ? icon("check") : e.etat === "en_cours" ? icon("clock") : ""),
      h("div", { class: "vs-title" }, e.libelle),
      e.date ? h("div", { class: "vs-date" }, formatDateTime(e.date)) : null)));

  const dernier = d.evenements[d.evenements.length - 1];
  const gauche = h("div", { class: "card card-pad" }, h("h3", { style: "font-size:16px;margin-bottom:18px" }, "Avancement de votre dossier"), etapes,
    dernier ? h("p", { class: "muted", style: "margin-top:18px;font-size:13px" }, `Dernière mise à jour ${relativeTime(dernier.date)}.`) : null);
  const droite = h("div", { class: "card card-pad" }, h("h3", { style: "font-size:16px;margin-bottom:14px" }, "Votre réclamation"),
    h("div", { class: "facts", style: "grid-template-columns:1fr" },
      h("div", { class: "fact" }, h("span", {}, "Raison sociale"), h("strong", {}, d.contrib)),
      h("div", { class: "fact" }, h("span", {}, "Impôt · montant contesté"), h("strong", {}, `${d.tax} · ${formatMoney(d.montant)}`)),
      h("div", { class: "fact" }, h("span", {}, "Objet"), h("strong", {}, d.motif)),
      h("div", { class: "fact" }, h("span", {}, "Déposée le"), h("strong", {}, formatDate(d.created_at)))));

  const blocs = [
    h("div", { class: "result-head" },
      h("div", {}, h("div", { class: "mono muted", style: "font-size:13px" }, d.id), h("h2", {}, d.status_label)),
      h("div", { style: "display:flex;gap:10px;align-items:center" }, h("span", { class: `badge tone-${meta.tone}` }, d.status_label),
        h("button", { class: "btn btn-sm no-print", type: "button", onclick: () => consulter() }, icon("refresh"), "Actualiser"))),
    h("div", { class: "two-col" }, gauche, droite)];

  if (d.decision_disponible) {
    blocs.push(h("section", { class: "decision-card", id: "decision" },
      h("h3", {}, icon("check"), "Décision notifiée", decisionBadge(d.type_decision)),
      d.montant_degreve != null ? h("p", { class: "muted", style: "margin-top:6px" }, `Montant dégrevé : ${formatMoney(d.montant_degreve)} — notifiée le ${formatDate(d.date_decision)}`) : null,
      h("div", { class: "decision-text" }, d.decision || ""),
      h("div", { class: "no-print", style: "margin-top:16px" }, h("button", { class: "btn", type: "button", onclick: () => window.print() }, "Imprimer la décision"))));
    // accusé de lecture : le contribuable vient de consulter la décision
    api.post(`/reclamations/${encodeURIComponent(r)}/lu?cle=${encodeURIComponent(c)}`, undefined, { auth: false }).catch(() => {});
  } else {
    blocs.push(h("div", { class: "alert info", style: "margin-top:20px" }, icon("clock"),
      "Votre dossier est en cours d'instruction. Revenez sur cette page avec votre référence et votre code : la décision y sera publiée dès sa validation."));
  }
  resultat.replaceChildren(h("div", { class: "result-card" }, blocs));
  resultat.scrollIntoView({ behavior: "smooth", block: "start" });
}

if (params.get("ref")) form.querySelector("#cle")?.focus();
