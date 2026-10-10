"""
Diagnostic e-mail : teste le serveur SMTP ÉTAPE PAR ÉTAPE et dit où ça bloque.

    cd backend
    python diag_email.py                       # teste la connexion et l'authentification (n'envoie rien)
    python diag_email.py --send moi@gmail.com  # envoie en plus un vrai message de test
"""
import smtplib
import socket
import sys
from email.mime.text import MIMEText

from app.config import settings
from app.email_service import _mot_de_passe


def etape(ok, texte):
    print(("  ✅ " if ok else "  ❌ ") + texte)
    return ok


def tester(host, port, user, pwd, envoyer_a=None):
    ssl_direct = int(port) == 465
    print(f"\n--- Test {host}:{port} ({'SSL direct' if ssl_direct else 'STARTTLS'}) ---")
    try:
        ips = {a[4][0] for a in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        etape(True, f"Nom de serveur résolu : {', '.join(sorted(ips))}")
    except OSError as e:
        etape(False, f"Nom de serveur introuvable ({e}) → vérifie SMTP_HOST et ta connexion Internet.")
        return False
    try:
        socket.create_connection((host, int(port)), timeout=10).close()
        etape(True, "Connexion réseau au port établie")
    except OSError as e:
        etape(False, f"Port inaccessible ({e}) → pare-feu, antivirus ou fournisseur d'accès qui bloque ce port.")
        return False
    try:
        srv = smtplib.SMTP_SSL(host, int(port), timeout=15) if ssl_direct else smtplib.SMTP(host, int(port), timeout=15)
        etape(True, "Le serveur répond (message d'accueil reçu)")
    except smtplib.SMTPServerDisconnected as e:
        etape(False, f"Le serveur coupe la connexion dès l'accueil ({e}).")
        print("     → Cause fréquente : un ANTIVIRUS qui analyse les e-mails (Kaspersky, ESET, Avast, Bitdefender…)\n"
              "       ou un pare-feu/réseau (école, entreprise) : désactive l'analyse « courrier / SMTP » ou change de réseau\n"
              "       (partage de connexion du téléphone) et réessaie.")
        return False
    try:
        if not ssl_direct:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            etape(True, "Chiffrement STARTTLS activé")
        code, _ = srv.login(user, pwd)
        etape(True, f"Authentification réussie (code {code})")
        if envoyer_a:
            m = MIMEText("Test GEIF : si tu lis ce message, l'envoi d'e-mails fonctionne.", "plain", "utf-8")
            m["From"], m["To"], m["Subject"] = settings.SMTP_FROM or user, envoyer_a, "Test GEIF"
            srv.sendmail(settings.SMTP_FROM or user, [envoyer_a], m.as_string())
            etape(True, f"Message de test envoyé à {envoyer_a}")
        srv.quit()
        return True
    except smtplib.SMTPAuthenticationError as e:
        etape(False, f"Mot de passe refusé ({e.smtp_code}).")
        print("     → Gmail : il faut un « mot de passe d'application » (16 caractères), PAS ton mot de passe habituel.\n"
              "       Compte Google → Sécurité → Validation en 2 étapes → Mots de passe des applications.")
    except smtplib.SMTPServerDisconnected as e:
        etape(False, f"Connexion coupée pendant le chiffrement/l'authentification ({e}) → antivirus ou réseau, voir ci-dessus.")
    except Exception as e:  # noqa: BLE001
        etape(False, f"{type(e).__name__} : {e}")
    return False


def main():
    envoyer_a = sys.argv[sys.argv.index("--send") + 1] if "--send" in sys.argv else None
    print("=" * 60 + "\nDIAGNOSTIC E-MAIL GEIF\n" + "=" * 60)
    if not settings.email_configure():
        print("SMTP non configuré : renseigne SMTP_HOST, SMTP_USER et SMTP_PASSWORD dans backend/.env (voir .env.example).")
        return 1
    pwd = _mot_de_passe()
    print(f"Serveur : {settings.SMTP_HOST}   Port : {settings.SMTP_PORT}   Utilisateur : {settings.SMTP_USER}")
    print(f"Mot de passe : {len(pwd)} caractères" + ("  (⚠ Gmail attend 16 caractères)" if settings.SMTP_HOST.endswith("gmail.com") and len(pwd) != 16 else ""))
    ok = tester(settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER, pwd, envoyer_a)
    if not ok:
        autre = 465 if int(settings.SMTP_PORT) != 465 else 587
        print(f"\nEssai automatique avec l'autre port ({autre}) pour aider au diagnostic :")
        if tester(settings.SMTP_HOST, autre, settings.SMTP_USER, pwd, envoyer_a):
            print(f"\n👉 Ça marche avec le port {autre} : mets SMTP_PORT={autre} dans backend/.env puis redémarre l'API.")
            return 0
    else:
        print("\n👉 L'envoi d'e-mails fonctionne.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
