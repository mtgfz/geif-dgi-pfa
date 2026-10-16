#!/usr/bin/env python3
"""
Contrôles statiques du frontend (aucune dépendance, lancé aussi par la CI) :
  1. chaque fichier local référencé par une page HTML (script, feuille de style) existe ;
  2. chaque import JavaScript relatif (import … from "./x.js") pointe vers un fichier existant ;
  3. chaque entrée du menu de l'application (NAV dans layout.js) a sa page ;
  4. aucune initialisation (init(...)) n'est appelée AVANT une déclaration const/let du même fichier
     (erreur « Cannot access 'x' before initialization » : page blanche) ;
  5. la syntaxe de tous les scripts est valide (si Node.js est installé).

    python scripts/check_frontend.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent / "frontend"
ANCIEN_RACINE = {"sit.html", "Uniform_V2.html", "js", "css"}  # ancienne interface (remplacée par portail/ et app/)
IGNORES_PARTOUT = {"node_modules", "vendor"}                  # bibliothèques tierces
erreurs: list[str] = []


def ignore(chemin: Path) -> bool:
    parties = chemin.relative_to(RACINE).parts
    return parties[0] in ANCIEN_RACINE or bool(IGNORES_PARTOUT & set(parties))


pages = [p for p in RACINE.rglob("*.html") if not ignore(p)]
scripts = [p for p in RACINE.rglob("*.js") if not ignore(p)]

# 1. références HTML
for page in pages:
    for ref in re.findall(r'(?:src|href)="([^"#?]+)', page.read_text(encoding="utf-8")):
        if re.match(r"^(https?:|mailto:|//|data:)", ref):
            continue
        if not (page.parent / ref).resolve().exists():
            erreurs.append(f"{page.relative_to(RACINE)} : fichier introuvable « {ref} »")

# 2. imports relatifs
for js in scripts:
    for ref in re.findall(r'from\s+"(\.[^"]+)"', js.read_text(encoding="utf-8")):
        if not (js.parent / ref).resolve().exists():
            erreurs.append(f"{js.relative_to(RACINE)} : import introuvable « {ref} »")

# 3. entrées du menu
layout = RACINE / "assets" / "js" / "layout.js"
if layout.exists():
    for href in re.findall(r'href:\s*"([a-z]+\.html)"', layout.read_text(encoding="utf-8")):
        if not (RACINE / "app" / href).exists():
            erreurs.append(f"menu : la page app/{href} n'existe pas")

# 4. ordre d'initialisation
for js in scripts:
    lignes = js.read_text(encoding="utf-8").split("\n")
    appels = [i for i, l in enumerate(lignes) if re.match(r"^(if \(.*\) |else )?init\(", l)]
    if appels:
        apres = [i + 1 for i, l in enumerate(lignes) if i > appels[0] and re.match(r"^(const|let) ", l)]
        if apres:
            erreurs.append(f"{js.relative_to(RACINE)} : init() ligne {appels[0] + 1} appelé avant la déclaration ligne {apres[0]} (déplacer l'appel en fin de fichier)")

# 5. syntaxe
if shutil.which("node"):
    for js in scripts:
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        if r.returncode:
            erreurs.append(f"{js.relative_to(RACINE)} : erreur de syntaxe — {r.stderr.strip().splitlines()[0] if r.stderr else ''}")

print(f"{len(pages)} pages HTML, {len(scripts)} scripts contrôlés.")
for e in erreurs:
    print("  ✘", e)
print("OK : frontend cohérent." if not erreurs else f"{len(erreurs)} problème(s).")
sys.exit(1 if erreurs else 0)
