// Portail SIT — espace contribuable. Aucune authentification classique :
// la référence + la clé de vérification (envoyée par e-mail) tiennent lieu
// de secret partagé pour consulter la décision finale et discuter.

const SIT_MOTIFS = {
  IS: ["Erreur de calcul de la base imposable", "Charge déductible rejetée à tort", "Double imposition", "Délai de réclamation dépassé"],
  TVA: ["TVA déductible non prise en compte", "Opération exonérée taxée à tort", "Erreur sur le taux appliqué", "Délai de réclamation dépassé"],
  IR: ["Erreur sur le barème appliqué", "Déduction non prise en compte (charges, frais professionnels)", "Double imposition", "Délai de réclamation dépassé"],
};

const SIT_STATUS_LABEL = {
  nouvelle: "Reçue — en attente de traitement",
  attente: "Traitée — en attente de validation interne",
  attente_chef_secteur: "En cours de validation (chef de secteur)",
  attente_chef_subdivision: "En cours de validation (chef de subdivision)",
  validee_finale: "Décision finale rendue",
  rejetee: "Réclamation rejetée",
};

const DOC_TYPES_AUTORISES = ["application/pdf", "image/png", "image/jpeg"];
const DOC_MAX_OPTIONNELS = 5;

let sitReclamationId = null;
let sitCleVerification = null;
let sitOptionalDocs = [];
let sitEmailConfirmationEnvoye = false;

function renderSitPortal(tab = "depot") {
  const root = document.getElementById("root");
  root.innerHTML = `
    <div class="sit-shell">
      <div class="sit-header">
        <div class="eyebrow">Direction Générale des Impôts — Système d'Information des Taxes</div>
        <h1>Espace Contribuable</h1>
      </div>

      <div class="sit-tabs">
        <button id="tab-depot" class="${tab === "depot" ? "active" : ""}">Déposer une réclamation</button>
        <button id="tab-suivi" class="${tab === "suivi" ? "active" : ""}">Suivre ma réclamation</button>
      </div>

      <div class="sit-card" id="sit-content"></div>
    </div>

    <button id="sitAssistantToggle" class="sit-assistant-fab" title="Conseiller virtuel">💬</button>
    <div id="sitAssistantPanel" class="sit-assistant-panel" style="display:none;">
      <div class="sit-assistant-head">Conseiller virtuel <span class="sub" style="display:block; font-size:10px; font-weight:normal;">Aide générale — ne remplace pas votre gestionnaire</span></div>
      <div id="sitAssistantThread" class="sit-assistant-thread"><div class="sub" style="padding:10px;">Bonjour ! Une question sur les documents à fournir, les délais ou votre motif de réclamation ?</div></div>
      <div class="sit-assistant-input-row">
        <input id="sitAssistantInput" type="text" placeholder="Posez votre question…" maxlength="300">
        <button id="sitAssistantSend">➤</button>
      </div>
    </div>
  `;
  wireAssistant();
  document.getElementById("tab-depot").onclick = () => { sitReclamationId = null; sitCleVerification = null; sitOptionalDocs = []; sitEmailConfirmationEnvoye = false; renderSitPortal("depot"); };
  document.getElementById("tab-suivi").onclick = () => renderSitPortal("suivi");

  if (tab === "depot") renderDepotStep1();
  else renderSuiviForm();
}

function stepsHtml(current) {
  const steps = ["Informations", "Documents", "Confirmation"];
  return `<div class="sit-steps">${steps.map((label, i) => {
    const n = i + 1;
    const cls = n < current ? "done" : n === current ? "current" : "";
    return `<div class="sit-step ${cls}">${n}. ${label}</div>`;
  }).join("")}</div>`;
}

// ---------- Étape 1 : informations ----------

function renderDepotStep1() {
  const content = document.getElementById("sit-content");
  content.innerHTML = `
    ${stepsHtml(1)}
    <label>Raison sociale / Nom du contribuable</label>
    <input id="f-contrib" type="text" />

    <label>Identifiant Fiscal (IF)</label>
    <input id="f-ifn" type="text" />

    <label>Adresse e-mail (pour recevoir la décision et la clé de vérification)</label>
    <input id="f-email" type="email" placeholder="vous@exemple.com" />

    <div class="row2">
      <div>
        <label>Impôt concerné</label>
        <select id="f-tax">
          <option value="IS">IS</option>
          <option value="TVA">TVA</option>
          <option value="IR">IR</option>
        </select>
      </div>
      <div>
        <label>Montant émis (DH)</label>
        <input id="f-montant" type="number" min="0" step="0.01" />
      </div>
    </div>

    <label>Motif de la réclamation</label>
    <select id="f-motif"></select>

    <div class="row2">
      <div>
        <label>Date de mise en recouvrement</label>
        <input id="f-date-mer" type="date" />
      </div>
      <div>
        <label>Date de la réclamation</label>
        <input id="f-date-reclam" type="date" readonly />
      </div>
    </div>

    <button class="sit-submit" id="f-next">Continuer vers les documents →</button>
    <div class="auth-error" id="f-error"></div>
  `;

  // Date de la réclamation = date du jour, remplie automatiquement (c'est la
  // date d'envoi du dossier, pas une date que le contribuable choisit).
  document.getElementById("f-date-reclam").value = new Date().toISOString().slice(0, 10);

  const fillMotifs = () => {
    const tax = document.getElementById("f-tax").value;
    const sel = document.getElementById("f-motif");
    sel.innerHTML = SIT_MOTIFS[tax].map((m) => `<option value="${m}">${m}</option>`).join("");
  };
  document.getElementById("f-tax").onchange = fillMotifs;
  fillMotifs();

  document.getElementById("f-next").onclick = submitStep1;
}

async function submitStep1() {
  const btn = document.getElementById("f-next");
  if (btn.disabled) return; // clic déjà en cours de traitement — on ignore les clics suivants
  const errBox = document.getElementById("f-error");
  errBox.textContent = "";
  const payload = {
    contrib: document.getElementById("f-contrib").value.trim(),
    ifn: document.getElementById("f-ifn").value.trim(),
    email: document.getElementById("f-email").value.trim(),
    tax: document.getElementById("f-tax").value,
    motif: document.getElementById("f-motif").value,
    montant: parseFloat(document.getElementById("f-montant").value),
    date_mer: document.getElementById("f-date-mer").value,
    date_reclam: document.getElementById("f-date-reclam").value,
  };
  if (!payload.contrib || !payload.ifn || !payload.email || !payload.montant || !payload.date_mer || !payload.date_reclam) {
    errBox.textContent = "Merci de remplir tous les champs, y compris l'adresse e-mail.";
    return;
  }
  btn.disabled = true;
  btn.textContent = "Envoi en cours…";
  try {
    const res = await Api.creerReclamationPublique(payload);
    sitReclamationId = res.id;
    sitCleVerification = res.cle_verification;
    sitEmailConfirmationEnvoye = !!res.email_confirmation_envoye;
    renderDepotStep2(); // re-render → le bouton disparaît avec l'ancien DOM, pas besoin de le réactiver ici
  } catch (e) {
    errBox.textContent = e.message || "Une erreur est survenue lors du dépôt.";
    btn.disabled = false;
    btn.textContent = "Continuer vers les documents →";
  }
}

// ---------- Étape 2 : documents ----------

function renderDepotStep2() {
  const content = document.getElementById("sit-content");
  sitOptionalDocs = [];
  content.innerHTML = `
    ${stepsHtml(2)}
    <p class="sub" style="margin:0 0 14px;">Formats acceptés : PDF, PNG, JPG/JPEG (documents scannés). Taille max 10 Mo par fichier.</p>

    <div class="doc-upload-block required">
      <div class="doc-title-row"><b>Demande de dégrèvement (obligatoire)</b></div>
      <input id="doc-required-file" type="file" accept=".pdf,.png,.jpg,.jpeg" />
      <label style="margin-top:8px;">Description du document</label>
      <input id="doc-required-desc" type="text" maxlength="50" placeholder="Ex : demande de dégrèvement signée" />
      <div class="doc-char-count" id="doc-required-count">0 / 50</div>
    </div>

    <div id="optional-docs-list"></div>
    <button class="doc-add-btn" id="add-doc-btn">+ Ajouter un document (optionnel, max 5)</button>

    <button class="sit-submit" id="docs-submit" style="margin-top:18px;">Envoyer les documents et finaliser</button>
    <button class="sit-submit secondary" id="docs-back">← Retour aux informations</button>
    <div class="auth-error" id="docs-error"></div>
  `;

  document.getElementById("doc-required-desc").oninput = (e) => {
    document.getElementById("doc-required-count").textContent = `${e.target.value.length} / 50`;
  };
  document.getElementById("add-doc-btn").onclick = addOptionalDocRow;
  document.getElementById("docs-submit").onclick = submitStep2;
  document.getElementById("docs-back").onclick = () => renderDepotStep1();
}

function addOptionalDocRow() {
  if (sitOptionalDocs.length >= DOC_MAX_OPTIONNELS) return;
  sitOptionalDocs.push({ file: null, description: "" });
  renderOptionalDocsList();
}

function renderOptionalDocsList() {
  const list = document.getElementById("optional-docs-list");
  list.innerHTML = sitOptionalDocs.map((_, i) => `
    <div class="doc-upload-block">
      <div class="doc-title-row"><b>Document optionnel ${i + 1}</b><button class="doc-remove" data-i="${i}">retirer</button></div>
      <input type="file" accept=".pdf,.png,.jpg,.jpeg" data-role="file" data-i="${i}" />
      <label style="margin-top:8px;">Description du document</label>
      <input type="text" maxlength="50" data-role="desc" data-i="${i}" placeholder="Ex : facture, justificatif de paiement..." />
      <div class="doc-char-count" data-role="count" data-i="${i}">0 / 50</div>
    </div>
  `).join("");

  list.querySelectorAll('[data-role="file"]').forEach((el) => {
    el.onchange = (e) => { sitOptionalDocs[+e.target.dataset.i].file = e.target.files[0] || null; };
  });
  list.querySelectorAll('[data-role="desc"]').forEach((el) => {
    el.oninput = (e) => {
      const i = +e.target.dataset.i;
      sitOptionalDocs[i].description = e.target.value;
      list.querySelector(`[data-role="count"][data-i="${i}"]`).textContent = `${e.target.value.length} / 50`;
    };
  });
  list.querySelectorAll(".doc-remove").forEach((btn) => {
    btn.onclick = (e) => { sitOptionalDocs.splice(+e.target.dataset.i, 1); renderOptionalDocsList(); };
  });

  document.getElementById("add-doc-btn").disabled = sitOptionalDocs.length >= DOC_MAX_OPTIONNELS;
}

async function submitStep2() {
  const submitBtnGuard = document.getElementById("docs-submit");
  if (submitBtnGuard.disabled) return; // clic déjà en cours de traitement
  const errBox = document.getElementById("docs-error");
  errBox.textContent = "";

  const requiredFile = document.getElementById("doc-required-file").files[0];
  const requiredDesc = document.getElementById("doc-required-desc").value.trim();

  if (!requiredFile) { errBox.textContent = "La demande de dégrèvement est obligatoire."; return; }
  if (!DOC_TYPES_AUTORISES.includes(requiredFile.type)) { errBox.textContent = "Format non autorisé — PDF, PNG ou JPG uniquement."; return; }
  if (!requiredDesc) { errBox.textContent = "Merci de décrire le document obligatoire."; return; }

  for (const doc of sitOptionalDocs) {
    if (doc.file && !DOC_TYPES_AUTORISES.includes(doc.file.type)) { errBox.textContent = "Un document optionnel a un format non autorisé."; return; }
    if (doc.file && !doc.description) { errBox.textContent = "Chaque document optionnel ajouté doit avoir une description."; return; }
  }

  const validOptional = sitOptionalDocs.filter((d) => d.file);

  const formData = new FormData();
  formData.append("demande_degrevement", requiredFile);
  formData.append("description_demande", requiredDesc);
  validOptional.forEach((d) => formData.append("documents_optionnels", d.file));
  validOptional.forEach((d) => formData.append("descriptions_optionnelles", d.description));

  const submitBtn = document.getElementById("docs-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Envoi en cours…";
  try {
    await Api.deposerDocuments(sitReclamationId, formData);
    renderDepotConfirmation();
  } catch (e) {
    errBox.textContent = e.message || "Erreur lors de l'envoi des documents.";
    submitBtn.disabled = false;
    submitBtn.textContent = "Envoyer les documents et finaliser";
  }
}

function renderDepotConfirmation() {
  const content = document.getElementById("sit-content");
  content.innerHTML = `
    ${stepsHtml(3)}
    <div class="sit-confirm">
      <p>Votre réclamation et vos documents ont bien été enregistrés.</p>
      <div class="ref">${sitReclamationId}</div>
      <p class="sub" style="margin-bottom:14px;">Référence — à conserver pour le suivi.</p>
      <div class="ref" style="background:var(--sit-blue-soft); color:var(--sit-blue-deep); border-color:var(--sit-blue);">${sitCleVerification}</div>
      <p class="sub"><b>Clé de vérification</b> — conservez-la précieusement. ${sitEmailConfirmationEnvoye
        ? "Elle vient de vous être envoyée par e-mail également."
        : "⚠️ L'envoi par e-mail a échoué ou n'est pas configuré côté serveur — notez-la dès maintenant, elle ne sera plus réaffichée."}
      Elle est nécessaire pour consulter la décision finale et échanger avec votre gestionnaire.</p>
    </div>`;
}

// ---------- Suivi + chat ----------

function renderSuiviForm() {
  const content = document.getElementById("sit-content");
  content.innerHTML = `
    <label>Référence de la réclamation</label>
    <input id="s-ref" type="text" placeholder="REC-20260917..." />
    <label>Clé de vérification (reçue par e-mail, requise pour voir la décision)</label>
    <input id="s-cle" type="text" placeholder="XXXX-XXXX" />
    <button class="sit-submit" id="s-submit">Consulter le statut</button>
    <div class="auth-error" id="s-error"></div>
    <div class="sit-suivi-result" id="s-result"></div>
  `;
  document.getElementById("s-submit").onclick = submitSuivi;
}

async function submitSuivi() {
  const errBox = document.getElementById("s-error");
  const resBox = document.getElementById("s-result");
  errBox.textContent = ""; resBox.innerHTML = "";
  const ref = document.getElementById("s-ref").value.trim();
  const cle = document.getElementById("s-cle").value.trim();
  if (!ref) { errBox.textContent = "Merci de saisir votre référence."; return; }
  try {
    const d = await Api.suivreReclamation(ref, undefined, cle || undefined);
    sitReclamationId = ref;
    sitCleVerification = cle || null;

    let html = `
      <div class="field-box" style="margin-bottom:10px;"><div class="label">Statut</div><div class="value" style="font-size:13px;">${SIT_STATUS_LABEL[d.status] || d.status}</div></div>
      <div class="field-box" style="margin-bottom:10px;"><div class="label">Contribuable</div><div class="value" style="font-size:13px;">${d.contrib} — ${d.tax}</div></div>`;

    if (d.decision_disponible_mais_cle_requise) {
      html += `<p class="sub">La décision finale est disponible — saisissez votre clé de vérification (reçue par e-mail) pour l'afficher.</p>`;
    }
    if (d.montant_degreve != null) {
      html += `<div class="field-box" style="margin-bottom:10px;"><div class="label">Dégrèvement</div><div class="value" style="font-size:13px;">${d.montant_degreve.toLocaleString("fr-FR")} DH</div></div>`;
    }
    if (d.decision) {
      html += `<div class="doc-block"><div class="doc-title">Décision</div><div class="doc-body">${d.decision}</div></div>`;
      Api.marquerLu(ref, cle).catch(() => {});
      html += `<div id="chatSection"></div>`;
    }
    resBox.innerHTML = html;

    if (d.decision) renderChatSit(ref, cle, d.gestionnaire_choisi);
  } catch (e) {
    errBox.textContent = "Aucune réclamation ne correspond à cette référence.";
  }
}

async function renderChatSit(ref, cle, gestionnaireChoisi) {
  const box = document.getElementById("chatSection");
  box.innerHTML = `
    <div class="predict-panel">
      <h4>Espace de discussion</h4>
      <div id="sitChatThread"><div class="loading">…</div></div>
      ${!gestionnaireChoisi ? `<label style="margin-top:10px;">Choisir un gestionnaire</label><select id="sit-gest-select"></select>` : `<p class="sub">Échange avec : ${gestionnaireChoisi}</p>`}
      <textarea id="sitChatInput" placeholder="Votre message…" style="margin-top:8px; min-height:60px;"></textarea>
      <button class="sit-submit" id="sitChatSend" style="margin-top:8px;">Envoyer</button>
    </div>`;

  if (!gestionnaireChoisi) {
    try {
      const gests = await Api.listerGestionnaires();
      document.getElementById("sit-gest-select").innerHTML = gests.map((g) => `<option value="${g}">${g}</option>`).join("");
    } catch (e) { /* liste indisponible, on laissera le champ vide */ }
  }

  document.getElementById("sitChatSend").onclick = () => sendChatSit(ref, cle);
  loadChatSit(ref, cle);
}

async function loadChatSit(ref, cle) {
  const box = document.getElementById("sitChatThread");
  try {
    const msgs = await Api.listerMessagesPublic(ref, cle);
    box.innerHTML = msgs.length === 0
      ? '<div class="sub">Aucun message pour l\'instant — posez votre question ci-dessous.</div>'
      : msgs.map((m) => `<div style="margin-bottom:8px;">
          <b style="font-size:10.5px; color:${m.auteur === "contribuable" ? "var(--sit-blue)" : "var(--sit-purple)"};">${m.auteur === "contribuable" ? "Vous" : m.auteur_label}</b>
          <div style="font-size:12.5px;">${m.body}</div>
        </div>`).join("");
  } catch (e) { box.innerHTML = '<div class="sub">Fil indisponible.</div>'; }
}

async function sendChatSit(ref, cle) {
  const input = document.getElementById("sitChatInput");
  const body = input.value.trim();
  if (!body) return;
  const gestSelect = document.getElementById("sit-gest-select");
  const dest = gestSelect ? gestSelect.value : undefined;
  try {
    await Api.envoyerMessageContribuable(ref, cle, body, dest);
    input.value = "";
    await loadChatSit(ref, cle);
  } catch (e) { alert(e.message || "Erreur lors de l'envoi."); }
}

// ---------- Conseiller virtuel (Groq) — aide générale, disponible sur tout le portail ----------
let sitAssistantHistorique = [];

function wireAssistant() {
  const toggle = document.getElementById("sitAssistantToggle");
  const panel = document.getElementById("sitAssistantPanel");
  toggle.onclick = () => { panel.style.display = panel.style.display === "none" ? "flex" : "none"; };
  const envoyer = () => sendAssistantSit();
  document.getElementById("sitAssistantSend").onclick = envoyer;
  document.getElementById("sitAssistantInput").onkeydown = (e) => { if (e.key === "Enter") envoyer(); };
}

async function sendAssistantSit() {
  const input = document.getElementById("sitAssistantInput");
  const question = input.value.trim();
  if (!question) return;
  const thread = document.getElementById("sitAssistantThread");
  thread.innerHTML += `<div class="sit-assistant-msg user">${question}</div>`;
  input.value = "";
  thread.innerHTML += `<div class="sit-assistant-msg bot" id="sitAssistantLoading">…</div>`;
  thread.scrollTop = thread.scrollHeight;
  try {
    const res = await Api.assistantSit(question, sitAssistantHistorique);
    sitAssistantHistorique.push({ role: "user", content: question });
    sitAssistantHistorique.push({ role: "assistant", content: res.reponse });
    document.getElementById("sitAssistantLoading").outerHTML = `<div class="sit-assistant-msg bot">${res.reponse}</div>`;
  } catch (e) {
    document.getElementById("sitAssistantLoading").outerHTML = `<div class="sit-assistant-msg bot">Désolé, le conseiller est indisponible pour le moment.</div>`;
  }
  thread.scrollTop = thread.scrollHeight;
}
