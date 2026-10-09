// Écran de connexion / inscription — affiché tant qu'aucun token valide n'est en mémoire.

function renderAuthScreen(mode = "login") {
  const root = document.getElementById("root");
  const isSignup = mode === "signup";

  root.innerHTML = `
    <div class="auth-screen">
      <div class="auth-card">
        <div class="eyebrow">DGI — GEIF</div>
        <h1>${isSignup ? "Créer un compte gestionnaire" : "Connexion"}</h1>

        <label>Identifiant</label>
        <input id="auth-username" type="text" autocomplete="username" />

        <label>Mot de passe</label>
        <input id="auth-password" type="password" autocomplete="${isSignup ? "new-password" : "current-password"}" />

        ${isSignup ? `
          <label>Rôle</label>
          <select id="auth-role">
            <option value="gestionnaire">Gestionnaire</option>
            <option value="chef_secteur">Chef de secteur</option>
            <option value="chef_subdivision">Chef de subdivision</option>
          </select>
          <div id="auth-code-wrap" style="display:none;">
            <label>Code d'inscription (fourni par l'administrateur)</label>
            <input id="auth-code" type="text" autocomplete="off" />
          </div>
        ` : ""}

        <button class="submit" id="auth-submit">${isSignup ? "Créer le compte" : "Se connecter"}</button>
        <div class="auth-error" id="auth-error"></div>

        <div class="switch">
          ${isSignup
            ? `Déjà un compte ? <a id="auth-switch">Se connecter</a>`
            : `Pas encore de compte ? <a id="auth-switch">En créer un</a>`}
        </div>
      </div>
    </div>
  `;

  document.getElementById("auth-switch").onclick = () => renderAuthScreen(isSignup ? "login" : "signup");
  document.getElementById("auth-submit").onclick = () => (isSignup ? handleSignup() : handleLogin());

  if (isSignup) {
    const roleSel = document.getElementById("auth-role");
    const codeWrap = document.getElementById("auth-code-wrap");
    const toggleCode = () => { codeWrap.style.display = roleSel.value === "gestionnaire" ? "none" : "block"; };
    roleSel.onchange = toggleCode;
    toggleCode();
  }

  // Entrée = valider le formulaire
  root.querySelectorAll("#auth-username,#auth-password").forEach((el) => {
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") (isSignup ? handleSignup() : handleLogin());
    });
  });
}

async function handleLogin() {
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const errBox = document.getElementById("auth-error");
  errBox.textContent = "";
  if (!username || !password) {
    errBox.textContent = "Identifiant et mot de passe requis.";
    return;
  }
  try {
    const res = await Api.login(username, password);
    setSession(res.access_token, res.role);
    renderDashboard();
  } catch (e) {
    errBox.textContent = e.message || "Échec de connexion.";
  }
}

async function handleSignup() {
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const role = document.getElementById("auth-role").value;
  const code = document.getElementById("auth-code") ? document.getElementById("auth-code").value.trim() : "";
  const errBox = document.getElementById("auth-error");
  errBox.textContent = "";
  if (!username || !password) {
    errBox.textContent = "Identifiant et mot de passe requis.";
    return;
  }
  if (password.length < 6) {
    errBox.textContent = "Le mot de passe doit faire au moins 6 caractères.";
    return;
  }
  if (role !== "gestionnaire" && !code) {
    errBox.textContent = "Le code d'inscription est requis pour ce rôle.";
    return;
  }
  try {
    await Api.signup(username, password, role, code || undefined);
    // Connexion automatique après inscription
    const res = await Api.login(username, password);
    setSession(res.access_token, res.role);
    renderDashboard();
  } catch (e) {
    errBox.textContent = e.message || "Échec de l'inscription.";
  }
}

function handleLogout() {
  clearSession();
  renderAuthScreen("login");
}
