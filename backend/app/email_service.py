"""
Envoi d'e-mails réels (SMTP) au contribuable une fois la décision validée au
dernier niveau (chef de subdivision). Si SMTP n'est pas configuré, on ne
plante rien : on logue simplement que l'e-mail n'a pas pu partir.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import settings


def _mot_de_passe() -> str:
    """Gmail affiche les « mots de passe d'application » par groupes de 4 séparés par des espaces :
    on les retire (ils ne font pas partie du mot de passe)."""
    pwd = settings.SMTP_PASSWORD
    return pwd.replace(" ", "") if settings.SMTP_HOST.endswith("gmail.com") else pwd


def _ouvrir_smtp():
    """Port 465 = SSL dès la connexion (SMTP_SSL). Sinon connexion simple, puis STARTTLS SI le serveur le propose
    (un serveur de test local comme Mailpit ne le propose pas). Utiliser le mauvais mode donne l'erreur
    « Connection unexpectedly closed »."""
    if int(settings.SMTP_PORT) == 465:
        return smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    serveur = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    try:
        serveur.ehlo()
        if serveur.has_extn("starttls"):
            serveur.starttls()
            serveur.ehlo()
    except Exception:
        serveur.close()
        raise
    return serveur


def _authentifier(serveur) -> None:
    if settings.SMTP_USER:
        serveur.login(settings.SMTP_USER, _mot_de_passe())


def envoyer_email_confirmation_depot(destinataire: str, contribuable: str, rec_id: str, cle_verification: str) -> bool:
    """Envoyé immédiatement au dépôt de la réclamation (étape 1) — donne au
    contribuable sa référence et sa clé de vérification par e-mail tout de
    suite, sans attendre la décision finale. C'est ce couple référence+clé,
    reçu ici, qui sert ensuite de "connexion" sur l'onglet Suivi."""
    if not settings.email_configure():
        print(f"[EMAIL] Non configuré — confirmation de dépôt non envoyée pour {rec_id}.")
        return False
    if not destinataire:
        print(f"[EMAIL] Aucune adresse fournie pour {rec_id} — confirmation non envoyée.")
        return False

    sujet = f"DGI — Accusé de dépôt de votre réclamation {rec_id}"
    corps = f"""Bonjour {contribuable},

Votre réclamation a bien été enregistrée auprès de la Direction Générale des
Impôts sous la référence {rec_id}.

Conservez précieusement ces deux informations — elles vous serviront à
suivre votre dossier et consulter la décision finale sur le portail SIT,
onglet « Suivre ma réclamation » :
  - Référence : {rec_id}
  - Clé de vérification : {cle_verification}

Vous recevrez un nouvel e-mail dès qu'une décision finale aura été rendue.

Ce message est envoyé automatiquement, merci de ne pas y répondre directement.

Direction Générale des Impôts — Système GEIF
"""

    msg = MIMEMultipart()
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = destinataire
    msg["Subject"] = sujet
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    try:
        with _ouvrir_smtp() as serveur:
            _authentifier(serveur)
            serveur.sendmail(settings.SMTP_FROM, [destinataire], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Échec de l'envoi de la confirmation de dépôt pour {rec_id} vers {destinataire} : {e}")
        return False


def envoyer_email_decision(destinataire: str, contribuable: str, rec_id: str, cle_verification: str, decision: str, montant_degreve: float | None) -> bool:
    if not settings.email_configure():
        print(f"[EMAIL] Non configuré — e-mail non envoyé pour {rec_id} (destinataire prévu : {destinataire}).")
        return False
    if not destinataire:
        print(f"[EMAIL] Aucune adresse fournie pour {rec_id} — e-mail non envoyé.")
        return False

    sujet = f"DGI — Décision concernant votre réclamation {rec_id}"
    montant_ligne = f"Montant dégrevé : {montant_degreve:,.2f} DH\n".replace(",", " ") if montant_degreve else ""
    corps = f"""Bonjour,

La Direction Générale des Impôts a statué sur votre réclamation {rec_id} ({contribuable}).

Décision :
{decision}
{montant_ligne}
Vous pouvez consulter le détail complet et échanger avec votre gestionnaire
sur le portail SIT (Espace Contribuable), onglet « Suivre ma réclamation »,
en utilisant :
  - Référence : {rec_id}
  - Clé de vérification : {cle_verification}

Ce message est envoyé automatiquement, merci de ne pas y répondre directement
— utilisez l'espace de discussion du portail pour toute question.

Direction Générale des Impôts — Système GEIF
"""

    msg = MIMEMultipart()
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = destinataire
    msg["Subject"] = sujet
    msg.attach(MIMEText(corps, "plain", "utf-8"))

    try:
        with _ouvrir_smtp() as serveur:
            _authentifier(serveur)
            serveur.sendmail(settings.SMTP_FROM, [destinataire], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Échec de l'envoi pour {rec_id} vers {destinataire} : {e}")
        return False
