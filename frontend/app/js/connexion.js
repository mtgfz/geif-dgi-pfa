import { api, session } from "../../assets/js/api.js";
import { HOME_PAGE } from "../../assets/js/config.js";
import { h, icon, ROLE_LABELS } from "../../assets/js/ui.js";

// Déjà connecté : on va directement à l'accueil
if (session.token && session.user) location.replace(HOME_PAGE);

const params = new URLSearchParams(location.search);
const next = (() => {
  const n = params.get("next") || "";
  return /^[a-z]+\.html(\?.*)?$/.test(n) ? n : HOME_PAGE; // jamais de redirection vers un autre site
})();

const errorBox = h("div", { class: "alert error", hidden: true, role: "alert" });
const showError = (msg) => { errorBox.replaceChildren(icon("alert"), msg); errorBox.hidden = false; };
const hideError = () => { errorBox.hidden = true; };

const user = h("input", { class: "input", id: "username", autocomplete: "username", required: true, minlength: "3", maxlength: "64" });
const pass = h("input", { class: "input", id: "password", type: "password", autocomplete: "current-password", required: true, minlength: "6" });
const role = h("select", { class: "input", id: "role" }, Object.entries(ROLE_LABELS).map(([v, l]) => h("option", { value: v }, l)));
const code = h("input", { class: "input", id: "code", autocomplete: "off", placeholder: "Code remis par l'administrateur" });
const codeHint = h("span", { class: "hint" }, "Obligatoire pour les chefs. Pour un gestionnaire, uniquement si votre administrateur en a défini un.");
const submit = h("button", { class: "btn btn-primary", type: "submit", style: "width:100%;padding:11px" }, "Se connecter");

let mode = "login";
const signupFields = h("div", { class: "form-stack", hidden: true },
  h("div", { class: "field" }, h("label", { for: "role" }, "Rôle"), role),
  h("div", { class: "field" }, h("label", { for: "code" }, "Code d'inscription"), code, codeHint));

const tabLogin = h("button", { type: "button", role: "tab", "aria-selected": "true" }, "Connexion");
const tabSignup = h("button", { type: "button", role: "tab", "aria-selected": "false" }, "Créer un compte");
function setMode(m) {
  mode = m; hideError();
  tabLogin.setAttribute("aria-selected", String(m === "login"));
  tabSignup.setAttribute("aria-selected", String(m === "signup"));
  signupFields.hidden = m === "login";
  pass.autocomplete = m === "login" ? "current-password" : "new-password";
  submit.textContent = m === "login" ? "Se connecter" : "Créer mon compte";
}
tabLogin.onclick = () => setMode("login");
tabSignup.onclick = () => setMode("signup");

async function login(username, password) {
  const r = await api.post("/auth/login", { username, password }, { auth: false });
  session.save(r.access_token, { username: r.username, role: r.role });
  location.replace(next);
}

const form = h("form", { class: "form-stack", novalidate: true },
  errorBox,
  h("div", { class: "field" }, h("label", { for: "username" }, "Nom d'utilisateur"), user),
  h("div", { class: "field" }, h("label", { for: "password" }, "Mot de passe"), pass),
  signupFields, submit);

form.addEventListener("submit", async (e) => {
  e.preventDefault(); hideError();
  if (!user.value.trim() || !pass.value) return showError("Renseignez le nom d'utilisateur et le mot de passe.");
  submit.disabled = true;
  try {
    if (mode === "signup") {
      await api.post("/auth/signup", {
        username: user.value.trim(), password: pass.value, role: role.value, registration_code: code.value.trim() || null,
      }, { auth: false });
    }
    await login(user.value.trim(), pass.value);
  } catch (err) {
    showError(err.message);
    submit.disabled = false;
  }
});

const feature = (ico, t, s) => h("li", {}, h("div", { class: "ico" }, icon(ico)), h("div", {}, h("strong", {}, t), h("span", {}, s)));

document.getElementById("root").append(h("div", { class: "auth-shell" },
  h("section", { class: "auth-brand" },
    h("div", { style: "position:relative;z-index:1" },
      h("div", { class: "brand" }, h("div", { class: "brand-mark" }, "G"),
        h("div", { class: "brand-text" }, h("strong", {}, "GEIF"), h("span", {}, "Direction Générale des Impôts"))),
      h("h1", {}, "Gestion électronique intelligente des flux fiscaux"),
      h("p", { class: "lead" }, "Traitement des réclamations : lecture des pièces, analyse du CGI et aide à la décision, avec validation hiérarchique."),
      h("ul", { class: "feature-list" },
        feature("file", "Lecture automatique des pièces", "OCR et extraction des champs clés."),
        feature("book", "Appui sur le Code Général des Impôts", "Articles pertinents retrouvés pour chaque dossier."),
        feature("shield", "Circuit de validation tracé", "Gestionnaire, Chef de Service, Chef de Subdivision."))),
    h("div", { class: "muted", style: "color:rgba(255,255,255,.55);font-size:12.5px;position:relative;z-index:1" },
      "Accès réservé aux agents habilités de la DGI.")),
  h("section", { class: "auth-panel" },
    h("div", { class: "card auth-card" },
      h("h2", {}, "Espace agents"),
      h("p", { class: "muted" }, "Connectez-vous pour accéder à vos dossiers."),
      h("div", { class: "tabs", role: "tablist" }, tabLogin, tabSignup),
      params.get("expired") ? h("div", { class: "alert warn", style: "margin-bottom:16px" }, icon("clock"), "Votre session a expiré. Reconnectez-vous.") : null,
      form,
      h("p", { class: "muted", style: "margin-top:22px;font-size:13px;text-align:center" },
        "Vous êtes contribuable ? ", h("a", { href: "../index.html" }, "Accéder au portail"))))));

document.title = "Connexion · GEIF";
user.focus();
