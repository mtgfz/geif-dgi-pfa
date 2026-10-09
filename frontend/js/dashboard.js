// Tableau de bord principal — affiché une fois authentifié. Le contenu de
// la file et les actions disponibles dépendent du rôle connecté.

const MOTIFS = {
  IS: ["Erreur de calcul de la base imposable", "Charge déductible rejetée à tort", "Double imposition", "Délai de réclamation dépassé"],
  TVA: ["TVA déductible non prise en compte", "Opération exonérée taxée à tort", "Erreur sur le taux appliqué", "Délai de réclamation dépassé"],
  IR: ["Erreur sur le barème appliqué", "Déduction non prise en compte (charges, frais professionnels)", "Double imposition", "Délai de réclamation dépassé"],
};

const STATUS_LABELS = {
  nouvelle: "Nouvelle",
  attente: "Traitée · en attente du gestionnaire",
  attente_chef_secteur: "En attente du chef de secteur",
  attente_chef_subdivision: "En attente du chef de subdivision",
  validee_finale: "Validée — décision finale envoyée",
  rejetee: "Rejetée",
};

const STATUS_BY_ROLE = {
  gestionnaire: "nouvelle,attente",
  chef_secteur: "attente_chef_secteur",
  chef_subdivision: "attente_chef_subdivision",
};

let dossiers = [];
let regles = [];
let activeId = null;
let activeDocuments = [];
let queueSearchTerm = "";

function statusClass(s) { return (s || "nouvelle").replace(/_/g, "-"); }
function statusLabel(s) { return STATUS_LABELS[s] || s; }
function fmtDate(s) { if (!s) return ""; const [y, m, d] = s.split("-"); return `${d}/${m}/${y}`; }
function escapeHtmlDoc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>"); }
const SEND_LABEL = {
  gestionnaire: "Envoyer au chef de secteur",
  chef_secteur: "Envoyer au chef de subdivision",
  chef_subdivision: "Valider — envoyer au contribuable",
};

function renderDashboard() {
  const root = document.getElementById("root");
  root.className = "dash-shell";
  root.innerHTML = `
    <header class="top">
      <div class="top-row-header">
        <img src="assets/logos/DGI.png" alt="DGI" class="top-logo" onerror="this.style.display='none'">
        <div style="flex:1;">
          <div class="eyebrow">GEIF — Gestion Électronique Intelligente des Flux fiscaux</div>
          <h1>Traitement Automatique des Réclamations</h1>
        </div>
        <div class="user-badge">
          <a href="sit.html" target="_blank" style="font-size:10.5px; color:var(--blue); text-decoration:underline;">Portail SIT (aperçu contribuable) ↗</a>
          <span class="role-pill">${currentRole || ""}</span>
          <button id="logout-btn">Déconnexion</button>
        </div>
      </div>
      <p class="sub">${roleDescription()}</p>
      <div class="api-status"><span class="dot" id="apiDot"></span><span id="apiText">Connexion à l'API…</span></div>
      <div class="api-status"><span class="dot" id="emailDot"></span><span id="emailText">E-mail : vérification…</span></div>
      <div class="api-status"><span class="dot" id="ocrDot"></span><span id="ocrText">OCR : vérification…</span></div>
    </header>

    <div class="layout">
      <div class="queue-col">
        <h2>File des réclamations <span id="queueCount">0</span></h2>
        <p class="sub" style="margin:-4px 0 10px;">${queueDescription()}</p>
        <input type="text" id="queueSearch" class="queue-search" placeholder="Rechercher : nom, référence, motif, impôt…">
        <div id="queueList"><div class="loading">Chargement…</div></div>
        ${currentRole === "gestionnaire" ? '<button class="treat-all" id="treatAll">▶ Traiter automatiquement les nouvelles réclamations</button>' : ""}
      </div>

      <div class="detail-col" id="detailCol">
        <div class="empty-state">Sélectionnez une réclamation.</div>
      </div>

      <div class="rl-col">
        <div class="panel-tabs">
          <button class="ptab active" data-panel="apprentissage">Apprentissage</button>
          <button class="ptab" data-panel="stats">Statistiques</button>
          <button class="ptab" data-panel="previsions">Prévisions</button>
          <button class="ptab" data-panel="marche">Marché</button>
        </div>

        <div id="panel-apprentissage">
          <select id="ruleSelect" class="queue-search" style="margin-bottom:10px;"></select>
          <div id="rlList"><div class="loading">…</div></div>
        </div>

        <div id="panel-stats" style="display:none;">
          <p class="sub">Indicateurs calculés en direct sur MongoDB — aucune valeur simulée.</p>
          <div id="statsContent"><div class="loading">…</div></div>
        </div>

        <div id="panel-previsions" style="display:none;">
          <p class="sub">Prévision de charge (régression sur l'historique réel) et probabilité d'issue apprise pour chaque règle.</p>
          <div class="predict-panel">
            <h4>Volume attendu — 7 prochains jours</h4>
            <div id="volumeForecast"><div class="loading">…</div></div>
          </div>
          <div class="predict-panel">
            <h4>Probabilité d'acceptation par règle</h4>
            <p class="sub" style="margin:-2px 0 8px;">= confiance apprise actuelle de chaque règle.</p>
            <div id="outcomeByRule"><div class="loading">…</div></div>
          </div>
        </div>

        <div id="panel-marche" style="display:none;">
          <p class="sub">Référentiel sectoriel — bilans réels de banques marocaines cotées (source AMMC, Pilier 9).</p>
          <div id="marcheContent"><div class="loading">…</div></div>
          <div class="rl-note">Contexte consultable uniquement : n'intervient pas dans le calcul des décisions de réclamation.</div>
        </div>
      </div>
    </div>

    <div class="toast" id="toast"></div>
  `;

  document.getElementById("logout-btn").onclick = handleLogout;
  if (currentRole === "gestionnaire") document.getElementById("treatAll").onclick = traiterTout;
  document.querySelectorAll(".ptab").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".ptab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const cible = btn.dataset.panel;
      ["apprentissage", "stats", "previsions", "marche"].forEach((p) => {
        document.getElementById(`panel-${p}`).style.display = p === cible ? "block" : "none";
      });
      if (cible === "stats") loadStats();
      if (cible === "previsions") loadPrevisions();
      if (cible === "marche") loadMarche();
    };
  });

  document.getElementById("queueSearch").oninput = (e) => {
    queueSearchTerm = e.target.value.trim().toLowerCase();
    renderQueue();
  };

  checkApi();
  loadQueue();
  loadRules();
}

function roleDescription() {
  if (currentRole === "chef_secteur") return "File des dossiers traités par les gestionnaires, en attente de votre validation avant transmission au chef de subdivision.";
  if (currentRole === "chef_subdivision") return "Dernier niveau de validation — une fois validé ici, la décision est finale et envoyée automatiquement au contribuable.";
  return "File de réclamations traitées automatiquement (rapport + décision motivés par le CGI, retrouvé par RAG, rédigés par le LLM) puis validées par le gestionnaire. Périmètre : IS, IR, TVA.";
}

function queueDescription() {
  if (currentRole === "chef_secteur") return "Dossiers en attente de votre décision (secteur).";
  if (currentRole === "chef_subdivision") return "Dossiers en attente de votre décision finale (subdivision).";
  return "Les réclamations proviennent du portail SIT (espace contribuable) — aucune saisie manuelle ici.";
}

async function checkApi() {
  try {
    const h = await Api.health();
    document.getElementById("apiDot").className = "dot ok";
    document.getElementById("apiText").textContent = "Système connecté";

    const emailOk = h.email && h.email.ok;
    document.getElementById("emailDot").className = "dot " + (emailOk ? "ok" : "ko");
    document.getElementById("emailText").textContent = "E-mail : " + (h.email ? h.email.message : "statut inconnu");

    const ocrOk = h.ocr && h.ocr.ok;
    document.getElementById("ocrDot").className = "dot " + (ocrOk ? "ok" : "ko");
    document.getElementById("ocrText").textContent = "OCR : " + (h.ocr ? h.ocr.message : "statut inconnu");
  } catch (e) {
    document.getElementById("apiDot").className = "dot ko";
    document.getElementById("apiText").textContent = "Système hors ligne";
    document.getElementById("emailDot").className = "dot ko";
    document.getElementById("emailText").textContent = "E-mail : API injoignable";
    document.getElementById("ocrDot").className = "dot ko";
    document.getElementById("ocrText").textContent = "OCR : API injoignable";
  }
}

async function loadQueue() {
  const statusFilter = STATUS_BY_ROLE[currentRole] || "";
  try { dossiers = await Api.listerReclamations(statusFilter); } catch (e) { dossiers = []; }
  renderQueue();
}

async function loadRules() {
  try { regles = await Api.statistiques().then((s) => s.regles); } catch (e) { regles = []; }
  renderRL();
}

function renderQueue() {
  const list = document.getElementById("queueList");
  const terme = (queueSearchTerm || "").toLowerCase();
  const visibles = !terme ? dossiers : dossiers.filter((d) =>
    [d.contrib, d.id, d.motif, d.tax, d.ifn].filter(Boolean).some((v) => String(v).toLowerCase().includes(terme))
  );
  document.getElementById("queueCount").textContent = terme ? `${visibles.length}/${dossiers.length}` : dossiers.length;
  if (dossiers.length === 0) { list.innerHTML = '<div class="loading">Aucune réclamation.</div>'; return; }
  if (visibles.length === 0) { list.innerHTML = '<div class="loading">Aucun résultat pour cette recherche.</div>'; return; }
  list.innerHTML = "";
  visibles.forEach((d) => {
    const el = document.createElement("div");
    el.className = "dossier-card" + (d.id === activeId ? " active" : "");
    el.onclick = () => {
      activeId = d.id; renderDetail(); renderQueue(); loadDocumentsForDetail(d.id);
      if (d.status === "nouvelle" && currentRole === "gestionnaire") traiterUn(d.id);
    };
    el.innerHTML = `<div class="top-row"><span class="tax-tag ${d.tax}">${d.tax}</span><span class="ref">${d.id.slice(-8)}</span></div>
      <h3>${d.contrib}</h3><div class="motif">${d.motif}</div>
      <span class="status-pill ${statusClass(d.status)}">${statusLabel(d.status)}</span>`;
    list.appendChild(el);
  });
}

async function loadDocumentsForDetail(id) {
  try { activeDocuments = await Api.listerDocuments(id); } catch (e) { activeDocuments = []; }
  const box = document.getElementById("documentsBox");
  if (box) box.innerHTML = renderDocumentsHtml();
}

function renderDocumentsHtml() {
  if (!activeDocuments || activeDocuments.length === 0) return '<div class="sub">Aucun document déposé.</div>';
  return activeDocuments.map((doc) => `
    <div class="predict-row" style="align-items:flex-start;">
      <span>${doc.obligatoire ? "📎<b>" : "📎"} ${doc.description}${doc.obligatoire ? "</b>" : ""} <span style="opacity:.6;">(${doc.filename})</span></span>
    </div>
    <div class="sub" style="margin:2px 0 10px; font-size:10.5px; max-height:60px; overflow-y:auto; background:var(--paper); padding:6px; border-radius:2px;">${escapeHtmlDoc((doc.texte_ocr || "").slice(0, 300))}</div>
  `).join("");
}

function renderDetail() {
  const d = dossiers.find((x) => x.id === activeId);
  const col = document.getElementById("detailCol");
  if (!d) { col.innerHTML = '<div class="empty-state">Sélectionnez une réclamation.</div>'; return; }

  const estNouvelle = d.status === "nouvelle";
  const estFinal = d.status === "validee_finale" || d.status === "rejetee";
  const monNiveau =
    (currentRole === "gestionnaire" && d.status === "attente") ||
    (currentRole === "chef_secteur" && d.status === "attente_chef_secteur") ||
    (currentRole === "chef_subdivision" && d.status === "attente_chef_subdivision");

  col.innerHTML = `
    <div class="dossier-head">
      <div><div class="id-line">${d.id} · IF ${d.ifn}</div><h2>${d.contrib}</h2>
      <div class="meta">${d.tax} — ${d.motif} · Émis le ${fmtDate(d.date_mer)}</div></div>
      <div class="seal ${!estNouvelle ? "stamped" : ""}">TRAITÉ<br>AUTOMAT.</div>
    </div>
    <div class="field-grid">
      <div class="field-box"><div class="label">Montant émis</div><div class="value">${d.montant.toLocaleString("fr-FR")} DH</div></div>
      <div class="field-box"><div class="label">Date réclamation</div><div class="value">${fmtDate(d.date_reclam)}</div></div>
      <div class="field-box"><div class="label">Statut</div><div class="value" style="font-size:12px;">${statusLabel(d.status)}</div></div>
      ${estFinal ? `<div class="field-box"><div class="label">Lecture contribuable</div><div class="value" style="font-size:12px;">${d.lu_par_contribuable ? "✓ Lu le " + fmtDate((d.date_lecture || "").slice(0, 10)) : "Non lu"}</div></div>` : ""}
    </div>

    <div class="predict-panel">
      <h4>Pièces jointes (portail SIT)</h4>
      <div id="documentsBox">${renderDocumentsHtml()}</div>
    </div>

    ${estNouvelle && currentRole === "gestionnaire" ? `
      <div class="loading">⏳ Traitement automatique en cours (appel LLM)…</div>
      <button class="predict-outcome-btn" id="btn-predict-outcome">◆ Prédire l'issue avant traitement</button>
      <div id="outcome-preview"></div>
    ` : ""}

    ${!estNouvelle ? `
      <span class="source-tag ${d.source_texte === "groq_llm" ? "groq" : "repli"}">${d.source_texte === "groq_llm" ? "✓ Généré par le LLM (Groq)" : "⚠ Texte de repli (pas de clé Groq / échec appel)"}</span>
      ${d.retrieval_score !== undefined && d.retrieval_score < 2 ? `<span class="source-tag faible">⚠ Citation CGI peu fiable — vérification manuelle recommandée</span>` : ""}

      <div class="doc-block" id="rapportBlock">
        <div class="doc-title">Rapport d'instruction <span class="art">${d.article || ""}</span></div>
        <div class="doc-body" id="rapportView">${escapeHtmlDoc(d.rapport || "")}</div>
        <textarea id="rapportEdit" class="doc-edit-area" style="display:none;">${d.rapport || ""}</textarea>
      </div>
      <div class="doc-block" id="decisionBlock">
        <div class="doc-title">Décision <span class="art">${d.article || ""}</span></div>
        <div class="doc-body" id="decisionView">${escapeHtmlDoc(d.decision || "")}</div>
        <textarea id="decisionEdit" class="doc-edit-area" style="display:none;">${d.decision || ""}</textarea>
      </div>
      <div class="toolbar-group">
        <button class="add-btn" style="width:auto; padding:7px 14px;" id="btn-print">🖨 Rapport d'instruction (document)</button>
        <button class="add-btn" style="width:auto; padding:7px 14px;" id="btn-print-officiel">📄 Décision</button>
      </div>

      ${monNiveau ? `
        ${currentRole === "chef_subdivision" ? '<div class="rl-note">Valider ici envoie automatiquement la décision au contribuable par e-mail et ouvre l\'espace de discussion.</div>' : ""}
        <div class="action-row">
          <button class="modify" id="btn-modify">✎ Modifier le rapport et la décision</button>
          <button class="save-modif" id="saveModifBtn" style="display:none;">💾 Enregistrer</button>
          <button class="save-modif" id="cancelModifBtn" style="display:none; background:transparent; color:var(--ink-soft);">Annuler</button>
        </div>
        <div class="ai-assist-row" id="aiAssistRow" style="display:none;">
          <input type="text" id="aiAssistInput" placeholder="Ex : sois plus ferme sur le délai, ou cite l'article 235…" maxlength="300">
          <button id="aiAssistBtn">🤖 Reformuler avec l'IA</button>
        </div>
        <div class="action-row">
          <button class="accept" id="btn-accept">✓ ${SEND_LABEL[currentRole] || "Valider"}</button>
          <button class="reject" id="btn-reject">✕ Rejeter</button>
        </div>` : !estFinal ? `<div style="font-size:11.5px; color:var(--ink-soft); font-family:var(--mono);">Dossier clos pour votre rôle — ${statusLabel(d.status)}</div>` : ""}

      ${estFinal ? `<div id="chatPanel" class="predict-panel" style="margin-top:16px;"><h4>Espace de discussion avec le contribuable</h4><div id="chatThread"><div class="loading">…</div></div>
        <textarea id="chatInput" placeholder="Répondre au contribuable…" style="margin-top:8px; min-height:60px;"></textarea>
        <button class="add-btn" style="width:auto; padding:7px 14px; margin-top:6px;" id="btn-chat-send">Envoyer</button></div>` : ""}
    ` : ""}
  `;

  if (estNouvelle && currentRole === "gestionnaire") {
    document.getElementById("btn-predict-outcome").onclick = () => predireIssue(d);
  }
  if (!estNouvelle) {
    document.getElementById("btn-print").onclick = () => imprimerDocument(d);
    document.getElementById("btn-print-officiel").onclick = () => imprimerLettreOfficielle(d);
    if (monNiveau) {
      document.getElementById("btn-accept").onclick = () => deciderDossier(d.id, "accept");
      document.getElementById("btn-reject").onclick = () => deciderDossier(d.id, "reject");
      document.getElementById("btn-modify").onclick = () => toggleEditMode(true);
      document.getElementById("cancelModifBtn").onclick = () => toggleEditMode(false);
      document.getElementById("saveModifBtn").onclick = () => saveModif(d.id);
      document.getElementById("aiAssistBtn").onclick = () => reformulerAvecIA(d.id);
    }
    if (estFinal) {
      loadChat(d.id);
      document.getElementById("btn-chat-send").onclick = () => sendChatInterne(d.id);
    }
  }
}

function toggleEditMode(on) {
  ["rapport", "decision"].forEach((k) => {
    document.getElementById(k + "View").style.display = on ? "none" : "";
    document.getElementById(k + "Edit").style.display = on ? "" : "none";
  });
  document.getElementById("btn-modify").style.display = on ? "none" : "";
  document.getElementById("saveModifBtn").style.display = on ? "" : "none";
  document.getElementById("cancelModifBtn").style.display = on ? "" : "none";
  document.getElementById("aiAssistRow").style.display = on ? "flex" : "none";
}

async function reformulerAvecIA(id) {
  const input = document.getElementById("aiAssistInput");
  const instruction = input.value.trim();
  if (!instruction) { showToast("Décris d'abord ce que l'IA doit changer."); return; }
  const btn = document.getElementById("aiAssistBtn");
  btn.disabled = true; btn.textContent = "⏳ En cours…";
  try {
    const res = await Api.reformuler(id, instruction);
    document.getElementById("rapportEdit").value = res.rapport;
    document.getElementById("decisionEdit").value = res.decision;
    showToast("Proposition générée — relisez avant d'enregistrer.");
  } catch (e) {
    showToast(e.message || "Assistant IA indisponible.");
  }
  btn.disabled = false; btn.textContent = "🤖 Reformuler avec l'IA";
}

function apiDeciderPourRole(id, outcome) {
  if (currentRole === "gestionnaire") return Api.validerReclamation(id, outcome);
  if (currentRole === "chef_secteur") return Api.deciderSecteur(id, outcome);
  if (currentRole === "chef_subdivision") return Api.deciderSubdivision(id, outcome);
  return Promise.reject(new Error("Rôle inconnu."));
}

async function saveModif(id) {
  const rapport = document.getElementById("rapportEdit").value;
  const decision = document.getElementById("decisionEdit").value;
  try {
    await Api.sauvegarderBrouillon(id, rapport, decision);
    showToast("Modifications enregistrées.");
    await refreshAfterDecision();
    toggleEditMode(false);
  } catch (e) { showToast(e.message || "Erreur lors de l'enregistrement."); }
}

async function deciderDossier(id, outcome) {
  try {
    const res = await apiDeciderPourRole(id, outcome);
    showToast(res && res.email_envoye ? "Décision finale envoyée au contribuable par e-mail." : outcome === "accept" ? (SEND_LABEL[currentRole] || "Dossier transmis") + " ✓" : "Dossier rejeté.");
    await refreshAfterDecision();
  } catch (e) { showToast(e.message || "Erreur lors de la validation."); }
}

async function refreshAfterDecision() {
  await loadQueue(); await loadRules(); renderDetail();
  if (document.getElementById("panel-stats").style.display !== "none") loadStats();
  if (document.getElementById("panel-previsions").style.display !== "none") loadPrevisions();
}

async function traiterUn(id) {
  showToast("Appel au LLM en cours…");
  try {
    await Api.traiterReclamation(id);
    await loadQueue();
    renderDetail();
    showToast("Dossier traité automatiquement.");
  } catch (e) { showToast(e.message || "Erreur lors du traitement."); }
}

async function traiterTout() {
  const nouvelles = dossiers.filter((d) => d.status === "nouvelle");
  if (nouvelles.length === 0) { showToast("Aucune nouvelle réclamation."); return; }
  document.getElementById("treatAll").disabled = true;
  for (const d of nouvelles) {
    try { await Api.traiterReclamation(d.id); } catch (e) { /* on continue les autres */ }
  }
  document.getElementById("treatAll").disabled = false;
  await loadQueue();
  if (activeId) renderDetail();
  showToast(`${nouvelles.length} dossier(s) traité(s).`);
}

// ---------- Chat interne (gestionnaire/chefs) ----------

async function loadChat(id) {
  const box = document.getElementById("chatThread");
  try {
    const msgs = await Api.listerMessagesInternes(id);
    box.innerHTML = msgs.length === 0
      ? '<div class="sub">Aucun message pour l\'instant.</div>'
      : msgs.map((m) => `<div class="predict-row" style="display:block; margin-bottom:6px;">
          <b style="font-size:10.5px; color:${m.auteur === "contribuable" ? "var(--blue)" : "var(--ink-soft)"};">${m.auteur === "contribuable" ? m.auteur_label + " (contribuable)" : m.auteur_label}</b>
          <div style="font-size:12px;">${escapeHtmlDoc(m.body)}</div>
        </div>`).join("");
  } catch (e) { box.innerHTML = '<div class="loading">Fil indisponible.</div>'; }
}

async function sendChatInterne(id) {
  const input = document.getElementById("chatInput");
  const body = input.value.trim();
  if (!body) return;
  try {
    await Api.envoyerMessageInterne(id, body);
    input.value = "";
    await loadChat(id);
  } catch (e) { showToast(e.message || "Erreur lors de l'envoi."); }
}

// ---------- Prédiction d'issue ----------

async function predireIssue(d) {
  const box = document.getElementById("outcome-preview");
  box.innerHTML = '<div class="loading">Calcul de la prédiction…</div>';
  try {
    const p = await Api.predictionIssue({ tax: d.tax, motif: d.motif, montant: d.montant, date_mer: d.date_mer, date_reclam: d.date_reclam });
    if (!p.disponible) { box.innerHTML = `<div class="loading">${p.message}</div>`; return; }
    box.innerHTML = `
      <div class="predict-panel">
        <div class="predict-row"><span>Probabilité d'acceptation</span><span>${Math.round(p.proba_acceptation * 100)}%</span></div>
        <div class="predict-row"><span>Dégrèvement attendu</span><span>${p.montant_degreve_attendu.toLocaleString("fr-FR")} DH</span></div>
        <div class="predict-row"><span>Fiabilité de la prédiction</span><span>${p.confiance_qualitative}</span></div>
      </div>`;
  } catch (e) { box.innerHTML = `<div class="loading">Prédiction indisponible.</div>`; }
}

// ---------- Impression : rapport interne (audit) ----------

function parseRapportSections(rapportTexte) {
  const texte = rapportTexte || "";
  const marks = [
    ["motifs", /I\.\s*Motifs et analyse de la demande/i],
    ["elements", /II\.\s*Éléments? de l'enquête[^\n]*/i],
    ["instruction", /III\.\s*Instruction et argumentation/i],
    ["avis", /IV\.\s*Avis de l'inspecteur[^\n]*/i],
  ];
  const hits = marks.map(([key, re]) => ({ key, m: texte.match(re) })).filter((h) => h.m);
  if (hits.length < 2) return { instruction: texte };
  hits.sort((a, b) => a.m.index - b.m.index);
  const out = {};
  hits.forEach((h, i) => {
    const start = h.m.index + h.m[0].length;
    const end = i + 1 < hits.length ? hits[i + 1].m.index : texte.length;
    out[h.key] = texte.slice(start, end).trim();
  });
  return out;
}

function imprimerDocument(d) {
  const solde = (d.montant - (d.montant_degreve || 0)).toLocaleString("fr-FR");
  const sec = parseRapportSections(d.rapport);
  const rapportHtml = sec.motifs !== undefined ? `
      <p class="sect-title">I. Motifs et analyse de la demande</p><p class="body-text">${escapeHtmlDoc(sec.motifs || "")}</p>
      <p class="sect-title">II. Éléments de l'enquête et renseignements tirés des documents d'assiette</p><p class="body-text">${escapeHtmlDoc(sec.elements || "")}</p>
      <p class="sect-title">III. Instruction et argumentation</p>
      <span class="article-tag">${escapeHtmlDoc(d.article || "")}</span>
      <p class="body-text">${escapeHtmlDoc(sec.instruction || "")}</p>
      <p class="sect-title">IV. Avis de l'inspecteur — révision proposée</p><p class="body-text">${escapeHtmlDoc(sec.avis || "")}</p>` : `
      <p class="sect-title">II. Instruction</p>
      <span class="article-tag">${escapeHtmlDoc(d.article || "")}</span>
      <p class="body-text">${escapeHtmlDoc(sec.instruction || "")}</p>`;
  const docHtml = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>${d.id} — ${d.contrib}</title>
  <style>
    body{ font-family:"Segoe UI",Arial,sans-serif; margin:0; background:#eee; }
    .doc-page{ max-width:800px; margin:24px auto; background:#fff; padding:40px 50px; box-shadow:0 0 8px rgba(0,0,0,.15); }
    .doc-page h2.dtitle{ text-align:center; font-size:20px; margin:0 0 10px; background:#7C9FD9; color:#fff; padding:10px; }
    .doc-page p.dline{ text-align:center; font-size:14.5px; margin:0 0 2px; font-weight:bold; }
    .doc-page ul.infolist{ list-style:disc; padding-left:22px; margin:16px 0; font-size:15px; }
    .doc-page .sect-title{ font-weight:bold; font-size:15px; margin:18px 0 8px; background:#EAF1FB; padding:7px 10px; border-left:4px solid #7C9FD9; }
    .doc-page p.body-text{ font-size:15px; text-align:justify; margin:0 0 10px; white-space:pre-line; }
    .doc-page table.doc-table{ width:100%; border-collapse:collapse; margin:8px 0 14px; font-size:13.5px; }
    .doc-page table.doc-table th, .doc-page table.doc-table td{ border:1px solid #000; padding:6px 8px; text-align:center; }
    .doc-page .article-tag{ font-size:12px; color:#8B6D1F; background:#F3E9CC; display:inline-block; padding:2px 8px; border-radius:2px; margin-bottom:14px; }
    .sig-table{ width:100%; border-collapse:collapse; margin-top:30px; }
    .sig-table td{ width:33.33%; text-align:center; border:none; padding-top:55px; font-weight:bold; }
    .print-bar{ max-width:800px; margin:16px auto 0; text-align:right; }
    .print-bar button{ padding:8px 16px; background:#152233; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:13px; }
    @media print{ .print-bar{ display:none; } .doc-page{ box-shadow:none; margin:0; max-width:100%; } }
  </style></head>
  <body>
    <div class="print-bar"><button onclick="window.print()">Imprimer / Exporter en PDF</button></div>
    <div class="doc-page">
      <h2 class="dtitle">Rapport d'Instruction &amp; Décision (usage interne)</h2>
      <p class="dline">Subdivision de la Fiscalité — DRI Rabat</p>
      <ul class="infolist">
        <li><b>Référence dossier :</b> ${d.id}</li>
        <li><b>Raison sociale :</b> ${escapeHtmlDoc(d.contrib)}</li>
        <li><b>Identifiant Fiscal :</b> ${escapeHtmlDoc(d.ifn)}</li>
        <li><b>Type d'impôt :</b> ${escapeHtmlDoc(d.tax)}</li>
        <li><b>Date de mise en recouvrement :</b> ${fmtDate(d.date_mer)}</li>
        <li><b>Date de la réclamation :</b> ${fmtDate(d.date_reclam)}</li>
      </ul>
      ${rapportHtml}
      <p class="sect-title">Montants</p>
      <table class="doc-table"><thead><tr><th>Désignation</th><th>Montant (DH)</th></tr></thead>
        <tbody>
          <tr><td>Montant émis</td><td>${d.montant.toLocaleString("fr-FR")}</td></tr>
          <tr><td>Dégrèvement proposé</td><td>${(d.montant_degreve || 0).toLocaleString("fr-FR")}</td></tr>
          <tr><td>Solde exigible</td><td>${solde}</td></tr>
        </tbody></table>
      <p class="sect-title">Décision</p><p class="body-text">${escapeHtmlDoc(d.decision || "")}</p>
      <table class="sig-table"><tbody><tr><td>Gestionnaire</td><td>Chef de Secteur</td><td>Chef de Subdivision</td></tr></tbody></table>
    </div>
  </body></html>`;
  const w = window.open("", "_blank");
  w.document.open(); w.document.write(docHtml); w.document.close();
}

// ---------- Impression : lettre officielle bilingue (modèle AJC012B/AJC001B) ----------

function parseArticleNumber(article) {
  const m = (article || "").match(/\d+/);
  return m ? m[0] : (article || ".......");
}

async function imprimerLettreOfficielle(d) {
  let descPieces = "votre demande de dégrèvement et des pièces justificatives fournies";
  try {
    const docs = await Api.listerDocuments(d.id);
    const req = docs.find((x) => x.obligatoire);
    if (req) descPieces = req.description;
  } catch (e) { /* on garde le texte par défaut */ }

  const estRejet = !d.montant_degreve || d.montant_degreve <= 0;
  const estTotal = !estRejet && d.montant_degreve >= d.montant;
  const kind = estRejet ? "rejet" : (estTotal ? "total" : "partiel");

  const META = {
    partiel: { modele: "AJC012B-25I", objetFr: "Lettre d'information au sujet d'un dégrèvement partiel", objetAr: "رسالة إعلام بإسقاط جزئي للضريبة", hasRecours: true },
    total: { modele: "AJC012B-25I", objetFr: "Lettre d'information au sujet d'un dégrèvement total", objetAr: "رسالة إعلام بإسقاط كلي للضريبة", hasRecours: false },
    rejet: { modele: "AJC001B-25I", objetFr: "Lettre d'information au sujet du rejet de votre réclamation", objetAr: "رسالة إعلام برفض مطالبتكم", hasRecours: true },
  };
  const meta = META[kind];
  const articleNum = parseArticleNumber(d.article);
  const fondementFr = `l'Article ${articleNum} du Code Général des Impôts (CGI)`;
  const fondementAr = `المادة ${articleNum} من المدونة العامة للضرائب`;

  const infoRow = (labelFr, value, labelAr) =>
    `<div class="rg-info-row"><div class="fr-lbl">${labelFr}</div><div class="val">${value || '<span style="display:inline-block; min-width:90px; border-bottom:1px solid #000;">&nbsp;</span>'}</div><div class="ar-lbl">${labelAr}</div></div>`;

  let middle;
  if (estRejet) {
    middle = `
      <div class="bi-paragraph">
        <div class="fr">J'ai l'honneur de vous faire connaître que les droits visés en objet ont été établis conformément aux dispositions de ${fondementFr}.</div>
        <div class="ar">يشرفني أن أحيطكم علما أن الواجبات المشار إليها في المرجع قد تم فرضها طبقا لأحكام ${fondementAr}.</div>
      </div>
      <div class="bi-paragraph">
        <div class="fr">En conséquence, il n'a pas été possible de réserver une suite favorable à votre demande.</div>
        <div class="ar">وفقا لذلك، لم يكن من الممكن إصدار قرار إيجابي في طلبكم.</div>
      </div>`;
  } else {
    middle = `
      <div class="bi-paragraph">
        <div class="fr">J'ai l'honneur de vous faire connaître qu'en application des dispositions de ${fondementFr} et eu égard à ${escapeHtmlDoc(descPieces)}, il a été décidé de vous accorder les dégrèvements suivants :</div>
        <div class="ar">يشرفني أن أحيطكم علما أنه طبقا لأحكام ${fondementAr} ونظرا إلى الحجج المدلى بها، فقد تقرر منحكم الإسقاطات التالية :</div>
      </div>
      <table class="doc-table"><thead><tr><th>Année</th><th>Type d'impôt</th><th>Montant (DH)</th></tr></thead>
        <tbody><tr><td>${fmtDate(d.date_reclam).slice(-4)}</td><td>${d.tax}</td><td>${d.montant_degreve.toLocaleString("fr-FR")}</td></tr></tbody></table>`;
  }

  const recours = meta.hasRecours ? `
    <div class="bi-paragraph">
      <div class="fr">Si vous n'acceptez pas cette décision, vous pouvez saisir le tribunal compétent dans le délai de trente (30) jours suivant la date de la notification de la présente lettre et ce, conformément aux dispositions législatives en vigueur.</div>
      <div class="ar">في حالة عدم قبولكم لهذا القرار، يمكنكم الطعن فيه أمام المحكمة المختصة داخل أجل الثلاثين (30) يوما الموالية لتاريخ تبليغه، وذلك طبقا للمقتضيات التشريعية الجاري بها العمل.</div>
    </div>` : "";

  const body = `
    <div class="doc-header"><img src="assets/logos/entete.jpeg" class="doc-entete" alt="Entête DGI" onerror="this.style.display='none'"></div>
    <div class="doc-model-ref">Modèle ${meta.modele} <span style="direction:rtl; font-family:Arial, sans-serif;">نموذج</span></div>
    <table class="rg-header-table"><tbody><tr>
      <td class="rg-left"><table class="rg-inner">
        <tr><td class="fr-lbl">Direction régionale, provinciale ou (inter) préfectorale de</td><td class="ar-lbl">المديرية الجهوية أو الإقليمية</td></tr>
        <tr><td colspan="2" class="rg-val">Rabat</td></tr>
        <tr><td class="fr-lbl">Service régional ou (inter) préfectoral de</td><td class="ar-lbl">المصلحة الجهوية أو الإقليمية</td></tr>
        <tr><td colspan="2" class="rg-val">Service Préfectoral des Personnes Morales</td></tr>
        <tr><td class="fr-lbl">Adresse</td><td class="ar-lbl">العنوان</td></tr>
        <tr><td colspan="2" class="rg-val">Avenue Hassan II Immeuble des Impôts - Rabat</td></tr>
      </table></td>
      <td class="rg-right"><table class="rg-inner">
        <tr><td class="fr-lbl">A</td><td class="ar-lbl">إلى</td></tr>
        <tr><td class="fr-lbl">M/Mme</td><td class="ar-lbl">السيد(ة)</td></tr>
        <tr><td colspan="2" class="rg-val">Le gérant de la société<br><b>${escapeHtmlDoc(d.contrib)}</b></td></tr>
      </table></td>
    </tr></tbody></table>
    <div class="rg-info-row"><div class="fr-lbl" style="text-align:left; flex:1;"><b><u>Objet</u> : ${meta.objetFr}</b></div><div class="ar-lbl" style="text-align:right; flex:1;"><b><u>الموضوع</u> : ${meta.objetAr}</b></div></div>
    ${infoRow(estRejet ? "En date du" : "Votre réclamation en date du", fmtDate(d.date_reclam), estRejet ? "بتاريخ" : "مطالبتكم بتاريخ")}
    <div style="height:8px;"></div>
    ${infoRow("Affaire n° / année", d.id, "رقم الملف / السنة")}
    ${infoRow("Nature des droits, impôts ou taxes", d.tax, "نوعية الواجبات أو الضرائب أو الرسوم")}
    ${infoRow("N° d'identification fiscale", escapeHtmlDoc(d.ifn), "رقم التعريف الضريبي")}
    <div style="height:10px;"></div>
    ${middle}
    ${recours}
    <div class="bi-closing">
      <div class="fr">Veuillez agréer l'expression de ma considération distinguée.</div>
      <div class="ar">وتفضلوا بقبول فائق التقدير.</div>
    </div>
    <div class="bi-dateline">Fait à Rabat, le</div>
    <div class="bi-sigline">Signature et visa de l'administration fiscale <span class="ar-inline">إمضاء وخاتم إدارة الضرائب</span></div>
    <div class="footer-dgi-logo"><img src="assets/logos/DGI.png" alt="DGI" onerror="this.style.display='none'"></div>`;

  const css = `
    body{ font-family:"Segoe UI",Arial,sans-serif; margin:0; background:#eee; }
    .doc-page{ max-width:800px; margin:24px auto; background:#fff; padding:40px 50px; box-shadow:0 0 8px rgba(0,0,0,.15); }
    .doc-header{ text-align:center; margin-bottom:10px; }
    .doc-entete{ max-width:100%; }
    .doc-model-ref{ text-align:right; font-size:13px; font-weight:bold; margin:0 0 4px; }
    table.rg-header-table{ width:100%; border-collapse:collapse; border:1px solid #000; margin:8px 0 14px; font-size:13px; }
    .rg-header-table > tbody > tr > td{ vertical-align:top; padding:6px 10px; }
    .rg-header-table > tbody > tr > td.rg-left{ width:56%; border-right:1px solid #000; }
    .rg-header-table table.rg-inner{ width:100%; border-collapse:collapse; }
    .rg-header-table table.rg-inner td{ padding:1px 0; font-size:13px; }
    .rg-header-table table.rg-inner td.fr-lbl{ text-align:left; font-weight:bold; }
    .rg-header-table table.rg-inner td.ar-lbl{ text-align:right; direction:rtl; font-family:Arial, sans-serif; font-weight:bold; }
    .rg-header-table table.rg-inner td.rg-val{ text-align:center; padding:2px 0 6px; }
    .rg-info-row{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; margin:4px 0; font-size:14px; }
    .rg-info-row .fr-lbl{ flex:1 1 0; text-align:left; font-weight:bold; }
    .rg-info-row .val{ flex:0 1 auto; text-align:center; font-weight:bold; padding:0 10px; white-space:nowrap; }
    .rg-info-row .ar-lbl{ flex:1 1 0; text-align:right; direction:rtl; font-family:Arial, sans-serif; font-weight:bold; }
    .bi-paragraph{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin:14px 0; }
    .bi-paragraph .fr{ font-size:14.5px; text-align:justify; }
    .bi-paragraph .ar{ font-size:14.5px; text-align:justify; direction:rtl; font-family:Arial, sans-serif; }
    .bi-closing{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin:14px 0; font-size:14.5px; }
    .bi-closing .ar{ direction:rtl; text-align:right; font-family:Arial, sans-serif; }
    .bi-dateline{ text-align:center; font-size:14.5px; margin:26px 0 6px; }
    .bi-sigline{ text-align:center; font-weight:bold; font-size:14.5px; margin:6px 0 40px; }
    .bi-sigline .ar-inline{ direction:rtl; font-family:Arial, sans-serif; margin-left:10px; }
    .footer-dgi-logo{ text-align:right; margin-top:20px; }
    .footer-dgi-logo img{ height:46px; }
    table.doc-table{ width:100%; border-collapse:collapse; margin:8px 0 14px; font-size:13.5px; }
    table.doc-table th, table.doc-table td{ border:1px solid #000; padding:6px 8px; text-align:center; }
    .print-bar{ max-width:800px; margin:16px auto 0; text-align:right; }
    .print-bar button{ padding:8px 16px; background:#152233; color:#fff; border:none; border-radius:4px; cursor:pointer; font-size:13px; }
    @media print{ .print-bar{ display:none; } .doc-page{ box-shadow:none; margin:0; max-width:100%; } }`;

  const fullHtml = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><title>${d.id} — Décision officielle</title><style>${css}</style></head>
    <body><div class="print-bar"><button onclick="window.print()">Imprimer / Exporter en PDF</button></div><div class="doc-page">${body}</div></body></html>`;

  const w = window.open("", "_blank");
  w.document.open(); w.document.write(fullHtml); w.document.close();
}

// ---------- Apprentissage (RL) : un menu déroulant, une règle à la fois, un vrai graphe ----------

let selectedRuleId = null;

function renderRL() {
  const select = document.getElementById("ruleSelect");
  if (!regles || regles.length === 0) { select.innerHTML = '<option>Chargement…</option>'; return; }
  select.innerHTML = regles.map((r) => `<option value="${r.id}">${r.tax} — ${r.motif} (${Math.round(r.confiance * 100)}%)</option>`).join("");
  if (!selectedRuleId || !regles.some((r) => r.id === selectedRuleId)) selectedRuleId = regles[0].id;
  select.value = selectedRuleId;
  select.onchange = () => { selectedRuleId = select.value; afficherRegleSelectionnee(); };
  afficherRegleSelectionnee();
}

async function afficherRegleSelectionnee() {
  const el = document.getElementById("rlList");
  const r = regles.find((x) => x.id === selectedRuleId);
  if (!r) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <div class="rule-row ${r.tax}">
      <div class="rname">${r.motif}</div>
      <div class="rmeta"><span>${r.id}</span><span>${Math.round(r.confiance * 100)}%</span></div>
      <div class="bar"><i style="width:${Math.round(r.confiance * 100)}%"></i></div>
    </div>
    <div id="curveGraph"><div class="loading">Chargement du graphe…</div></div>`;
  try {
    const res = await Api.courbeApprentissage(r.id);
    const pts = res.courbe;
    const box = document.getElementById("curveGraph");
    if (!pts || pts.length <= 1) { box.innerHTML = '<p class="sub" style="padding:6px 2px;">Pas encore de corrections sur cette règle.</p>'; return; }
    box.innerHTML = svgCourbe(pts) + `
      <div class="predict-row"><span>Point de départ</span><span>${Math.round(pts[0].confiance * 100)}%</span></div>
      <div class="predict-row"><span>Confiance actuelle</span><span>${Math.round(pts[pts.length - 1].confiance * 100)}%</span></div>
      <div class="predict-row"><span>Corrections prises en compte</span><span>${pts.length - 1}</span></div>`;
  } catch (e) { document.getElementById("curveGraph").innerHTML = '<p class="sub">Courbe indisponible.</p>'; }
}

function svgCourbe(pts) {
  const w = 320, h = 90, pad = 6;
  const max = Math.max(...pts.map((p) => p.confiance), 0.01);
  const min = Math.min(...pts.map((p) => p.confiance));
  const span = Math.max(0.05, max - min);
  const xStep = (w - pad * 2) / Math.max(1, pts.length - 1);
  const coord = (p, i) => [pad + i * xStep, h - pad - ((p.confiance - min) / span) * (h - pad * 2)];
  const path = pts.map((p, i) => coord(p, i)).map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const dots = pts.map((p, i) => {
    const [x, y] = coord(p, i);
    const couleur = p.outcome === "reject" ? "var(--sit-seal, #8B2A2A)" : p.outcome === "modify" ? "var(--sit-blue, #1E6FB8)" : "var(--sit-green, #2F7A4F)";
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${couleur}"><title>Étape ${p.etape} (${p.outcome}) : ${Math.round(p.confiance * 100)}%</title></circle>`;
  }).join("");
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%; height:${h}px; margin:6px 0;">
    <path d="${path}" fill="none" stroke="var(--sit-purple, #7C5CBF)" stroke-width="2"/>${dots}</svg>`;
}

let toastTimer;
function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

async function loadStats() {
  const el = document.getElementById("statsContent");
  try {
    const s = await Api.statistiques();
    const tauxAcc = s.taux_acceptation_sans_modification !== null ? Math.round(s.taux_acceptation_sans_modification * 100) + "%" : "—";

    let html = `
      <div class="stat-big"><div class="lab">Réclamations traitées</div>
        <div class="val">${s.traitees} / ${s.total_reclamations}</div>
        <div class="sub2">${s.total_reclamations - s.traitees} en attente de traitement</div></div>
      <div class="stat-big"><div class="lab">Validées sans modification</div>
        <div class="val">${tauxAcc}</div>
        <div class="sub2">indicateur de qualité du moteur</div></div>
      <div class="stat-big"><div class="lab">Montant dégrevé</div>
        <div class="val">${Math.round(s.montant_total_degreve).toLocaleString("fr-FR")} DH</div>
        <div class="sub2">sur ${Math.round(s.montant_total_emis).toLocaleString("fr-FR")} DH émis</div></div>
      <div class="stat-section">Par statut</div>`;

    Object.entries(s.par_statut).forEach(([k, v]) => { html += `<div class="stat-row"><span>${STATUS_LABELS[k] || k}</span><span>${v}</span></div>`; });

    html += `<div class="stat-section">Par impôt</div>`;
    s.par_impot.forEach((i) => { html += `<div class="stat-row"><span>${i.tax}</span><span>${i.nombre} · ${Math.round(i.montant_degreve).toLocaleString("fr-FR")} DH</span></div>`; });

    html += `<div class="stat-section">Motifs les plus fréquents</div>`;
    s.par_motif.slice(0, 5).forEach((m) => { html += `<div class="stat-row"><span style="max-width:200px;">${m.motif}</span><span>${m.nombre}</span></div>`; });

    html += `<div class="stat-section">Fiabilité & apprentissage</div>
      <div class="stat-row"><span>Citations CGI peu fiables</span><span>${s.dossiers_retrieval_faible}</span></div>
      <div class="stat-row"><span>Corrections enregistrées</span><span>${s.nombre_corrections_enregistrees}</span></div>`;

    const sl = s.stats_lecture || {};
    const tauxLect = sl.taux_lecture !== null && sl.taux_lecture !== undefined ? Math.round(sl.taux_lecture * 100) + "%" : "—";
    html += `<div class="stat-section">Lecture & engagement contribuable</div>
      <div class="stat-row"><span>Décisions envoyées</span><span>${sl.decisions_envoyees ?? 0}</span></div>
      <div class="stat-row"><span>Lues par le contribuable</span><span>${sl.decisions_lues ?? 0} (${tauxLect})</span></div>
      <div class="stat-row"><span>Ont répondu dans le chat</span><span>${sl.contribuables_ayant_repondu ?? 0}</span></div>`;

    el.innerHTML = html;
  } catch (e) { el.innerHTML = '<div class="loading">Statistiques indisponibles (API injoignable).</div>'; }
}

async function loadPrevisions() {
  const volBox = document.getElementById("volumeForecast");
  const ruleBox = document.getElementById("outcomeByRule");
  try {
    const v = await Api.previsionVolume(null, 7);
    if (!v.disponible) {
      volBox.innerHTML = `<div class="loading">${v.message}</div>`;
    } else {
      const max = Math.max(...v.previsions.map((p) => p.volume_prevu), 1);
      const bars = v.previsions.map((p) => `<div class="bar" style="height:${Math.max(4, (p.volume_prevu / max) * 40)}px" title="${p.date} : ${p.volume_prevu}"></div>`).join("");
      volBox.innerHTML = `
        <div class="predict-row"><span>Tendance</span><span class="trend-badge ${v.tendance}">${v.tendance}</span></div>
        <div class="predict-row"><span>Basé sur</span><span>${v.historique_points} jours d'historique</span></div>
        <div class="mini-forecast">${bars}</div>`;
    }
  } catch (e) { volBox.innerHTML = '<div class="loading">Prévision indisponible.</div>'; }

  if (!regles || regles.length === 0) { ruleBox.innerHTML = '<div class="loading">…</div>'; return; }
  ruleBox.innerHTML = regles
    .map((r) => `<div class="predict-row"><span>${r.motif} (${r.tax})</span><span>${Math.round(r.confiance * 100)}% · n=${r.observations}</span></div>`)
    .join("");
}

async function loadMarche() {
  const el = document.getElementById("marcheContent");
  try {
    const m = await Api.marcheAmmc();
    if (!m.disponible) { el.innerHTML = `<div class="loading" style="text-align:left; line-height:1.6;">${m.message}</div>`; return; }
    let html = `
      <div class="stat-big"><div class="lab">Exercices validés</div>
        <div class="val">${m.exercices_valides} / ${m.total_exercices}</div>
        <div class="sub2">${m.banques.length} banques · contrôle comptable automatique</div></div>
      <div class="stat-section">Registre par banque</div>`;
    let banqueActuelle = null;
    m.donnees.forEach((d) => {
      if (d.bank !== banqueActuelle) { banqueActuelle = d.bank; html += `<div class="stat-section" style="margin-top:10px; color:var(--ink);">${d.bank}</div>`; }
      const actif = d.total_actif_current != null ? Math.round(d.total_actif_current).toLocaleString("fr-FR") : "N/A";
      const badge = d.validated ? "✓" : "⚠";
      const couleur = d.validated ? "var(--green)" : "var(--seal)";
      html += `<div class="stat-row"><span>${d.year} <span style="color:${couleur};">${badge}</span></span><span>${actif}</span></div>`;
    });
    el.innerHTML = html;
  } catch (e) { el.innerHTML = '<div class="loading">Données marché indisponibles (API injoignable).</div>'; }
}
