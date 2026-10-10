// URL de l'API GEIF. Modifiable sans toucher au code :
//   localStorage.setItem("geif_api", "http://mon-serveur:8010")   (console du navigateur)
export const API_BASE = (window.GEIF_API_BASE || localStorage.getItem("geif_api") || "http://localhost:8010").replace(/\/$/, "");
export const LOGIN_PAGE = "connexion.html";
export const HOME_PAGE = "accueil.html";
export const POLL_MS = 20000; // rafraîchissement automatique des files d'attente
