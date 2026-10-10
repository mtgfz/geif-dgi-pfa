// Client API : ajoute le JWT, convertit les erreurs en messages lisibles, gère l'expiration de session.
import { API_BASE, LOGIN_PAGE } from "./config.js";

const TOKEN_KEY = "geif_token";
const USER_KEY = "geif_user";

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  get user() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; }
  },
  save(token, user) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, JSON.stringify(user)); },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); },
};

export function goToLogin(reason) {
  const next = encodeURIComponent(location.pathname.split("/").pop() + location.search);
  location.replace(`${LOGIN_PAGE}?${reason ? reason + "=1&" : ""}next=${next}`);
}

function messageFrom(data, status) {
  const d = data && data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => {
      const champ = Array.isArray(e.loc) ? e.loc.filter((x) => x !== "body" && x !== "query").join(".") : "";
      return (champ ? champ + " : " : "") + (e.msg || "valeur invalide").replace(/^Value error, /, "");
    }).join(" · ");
  }
  if (status === 429) return "Trop de tentatives. Réessayez dans un instant.";
  if (status === 403) return "Action non autorisée.";
  if (status >= 500) return "Erreur du serveur. Réessayez ou contactez l'administrateur.";
  return "La requête a échoué.";
}

async function request(method, path, { params, body, auth = true, raw = false } = {}) {
  const url = new URL(API_BASE + path);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && session.token) headers["Authorization"] = "Bearer " + session.token;

  let res;
  try {
    res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, "Serveur injoignable. Vérifiez que l'API GEIF est démarrée.");
  }
  if (res.status === 401 && auth) {
    session.clear();
    goToLogin("expired");
    throw new ApiError(401, "Session expirée.");
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* corps non JSON */ }
    throw new ApiError(res.status, messageFrom(data, res.status));
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export const api = {
  get: (path, params) => request("GET", path, { params }),
  post: (path, body, opts) => request("POST", path, { body, ...opts }),
  patch: (path, body) => request("PATCH", path, { body }),
  blob: async (path) => (await request("GET", path, { raw: true })).blob(),
};
