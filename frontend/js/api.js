// Petite couche d'accès à l'API — centralise l'URL de base et le token JWT
// (gardé en mémoire seulement, jamais dans localStorage : plus résistant au XSS).
const API_BASE = window.GEIF_API_BASE || "http://localhost:8010";

let authToken = null;
let currentRole = null;

function setSession(token, role) {
  authToken = token;
  currentRole = role;
}

function clearSession() {
  authToken = null;
  currentRole = null;
}

function isAuthenticated() {
  return !!authToken;
}

async function apiFetch(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    if (!authToken) throw new Error("Non authentifié.");
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

async function apiFetchMultipart(path, formData, { auth = false } = {}) {
  const headers = {};
  if (auth) {
    if (!authToken) throw new Error("Non authentifié.");
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  const resp = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: formData });
  if (!resp.ok) {
    let detail = resp.statusText;
    try { const data = await resp.json(); detail = data.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return resp.json();
}

const Api = {
  signup: (username, password, role, registration_code) =>
    apiFetch("/auth/signup", { method: "POST", body: { username, password, role, registration_code } }),
  login: (username, password) =>
    apiFetch("/auth/login", { method: "POST", body: { username, password } }),
  me: () => apiFetch("/auth/me", { auth: true }),
  health: () => apiFetch("/health"),

  listerReclamations: (status) => apiFetch(`/reclamations${status ? `?status=${encodeURIComponent(status)}` : ""}`, { auth: true }),
  obtenirReclamation: (id) => apiFetch(`/reclamations/${id}`, { auth: true }),
  traiterReclamation: (id) => apiFetch(`/reclamations/${id}/traiter`, { method: "POST", auth: true }),
  validerReclamation: (id, outcome) =>
    apiFetch(`/reclamations/${id}/decision`, { method: "POST", auth: true, body: { outcome } }),
  deciderSecteur: (id, outcome) =>
    apiFetch(`/reclamations/${id}/decision-secteur`, { method: "POST", auth: true, body: { outcome } }),
  deciderSubdivision: (id, outcome) =>
    apiFetch(`/reclamations/${id}/decision-subdivision`, { method: "POST", auth: true, body: { outcome } }),
  sauvegarderBrouillon: (id, rapport_finale, decision_finale) =>
    apiFetch(`/reclamations/${id}/brouillon`, { method: "POST", auth: true, body: { outcome: "accept", rapport_finale, decision_finale } }),
  reformuler: (id, instruction) =>
    apiFetch(`/reclamations/${id}/reformuler`, { method: "POST", auth: true, body: { instruction } }),
  assistantSit: (question, historique) =>
    apiFetch(`/assistant/sit`, { method: "POST", auth: false, body: { question, historique } }),

  // Chat interne (gestionnaire/chefs)
  listerMessagesInternes: (id) => apiFetch(`/reclamations/${id}/messages`, { auth: true }),
  envoyerMessageInterne: (id, body) =>
    apiFetch(`/reclamations/${id}/messages/interne`, { method: "POST", auth: true, body: { body } }),

  statistiques: () => apiFetch("/statistiques"),
  marcheAmmc: () => apiFetch("/marche-ammc"),

  previsionVolume: (tax, horizon_jours) =>
    apiFetch("/predictions/volume", { method: "POST", auth: true, body: { tax, horizon_jours } }),
  predictionIssue: (payload) =>
    apiFetch("/predictions/outcome", { method: "POST", auth: true, body: payload }),
  courbeApprentissage: (ruleId) => apiFetch(`/predictions/learning-curve/${ruleId}`, { auth: true }),

  // Portail SIT (public, aucun token)
  creerReclamationPublique: (payload) => apiFetch("/reclamations", { method: "POST", body: payload }),
  deposerDocuments: (recId, formData) => apiFetchMultipart(`/reclamations/${recId}/documents`, formData),
  listerDocuments: (recId) => apiFetch(`/reclamations/${recId}/documents`, { auth: true }),
  suivreReclamation: (id, ifn, cle) => {
    const params = new URLSearchParams();
    if (ifn) params.set("ifn", ifn);
    if (cle) params.set("cle", cle);
    const qs = params.toString();
    return apiFetch(`/reclamations/suivi/${id}${qs ? `?${qs}` : ""}`);
  },
  marquerLu: (id, cle) => apiFetch(`/reclamations/${id}/lu?cle=${encodeURIComponent(cle)}`, { method: "POST" }),
  listerGestionnaires: () => apiFetch("/auth/gestionnaires"),
  envoyerMessageContribuable: (id, cle, body, gestionnaire_destinataire) =>
    apiFetch(`/reclamations/${id}/messages/contribuable?cle=${encodeURIComponent(cle)}`, {
      method: "POST", body: { body, gestionnaire_destinataire },
    }),
  listerMessagesPublic: (id, cle) => apiFetch(`/reclamations/${id}/messages?cle=${encodeURIComponent(cle)}`),
};
