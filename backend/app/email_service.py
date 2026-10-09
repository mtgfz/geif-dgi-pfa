"""
Envoi d'e-mails réels (SMTP) au contribuable une fois la décision validée au
dernier niveau (chef de subdivision). Si SMTP n'est pas configuré, on ne
plante rien : on logue simplement que l'e-mail n'a pas pu partir.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import settings


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
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as serveur:
            serveur.starttls()
            serveur.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
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
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as serveur:
            serveur.starttls()
            serveur.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            serveur.sendmail(settings.SMTP_FROM, [destinataire], msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] Échec de l'envoi pour {rec_id} vers {destinataire} : {e}")
        return False
