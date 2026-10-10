"""
Constantes métier GEIF : rôles, statuts, types — source de vérité unique.
Les statuts sont stockés sous forme de clés techniques (sans accent) en base ;
les libellés français affichés viennent de STATUT_LABELS.
"""

# --- Rôles internes ---
GESTIONNAIRE = "gestionnaire"
CHEF_SERVICE = "chef_service"
CHEF_SUBDIVISION = "chef_subdivision"
ROLES = (GESTIONNAIRE, CHEF_SERVICE, CHEF_SUBDIVISION)
ROLE_LABELS = {
    GESTIONNAIRE: "Gestionnaire",
    CHEF_SERVICE: "Chef de Service",
    CHEF_SUBDIVISION: "Chef de Subdivision",
}

# --- Statuts d'une réclamation ---
NOUVELLE = "nouvelle"
EN_TRAITEMENT = "en_traitement"
ENVOYEE_CS = "envoyee_chef_service"
ENVOYEE_CSUB = "envoyee_chef_subdivision"
DECISION_ENVOYEE = "decision_envoyee"   # = Historique
RETOURNEE = "retournee"

STATUTS = (NOUVELLE, EN_TRAITEMENT, ENVOYEE_CS, ENVOYEE_CSUB, DECISION_ENVOYEE, RETOURNEE)

STATUT_LABELS = {
    NOUVELLE: "Nouvelle",
    EN_TRAITEMENT: "En traitement",
    ENVOYEE_CS: "Envoyée au Chef de Service",
    ENVOYEE_CSUB: "Envoyée au Chef de Subdivision",
    DECISION_ENVOYEE: "Décision envoyée",
    RETOURNEE: "Retournée",
}

# Libellés montrés au contribuable (sans détail du circuit interne)
STATUT_LABELS_PUBLIC = {
    NOUVELLE: "Réclamation déposée",
    EN_TRAITEMENT: "En cours d'instruction",
    ENVOYEE_CS: "En cours de validation",
    ENVOYEE_CSUB: "En cours de validation finale",
    DECISION_ENVOYEE: "Décision notifiée",
    RETOURNEE: "Complément d'instruction en cours",
}

# Étapes affichées dans la frise de suivi (la "Retournée" compte comme "En traitement")
ETAPES_SUIVI = (NOUVELLE, EN_TRAITEMENT, ENVOYEE_CS, ENVOYEE_CSUB, DECISION_ENVOYEE)

# Ce que chaque rôle voit sur sa page Accueil. Une réclamation terminée
# (DECISION_ENVOYEE) n'y apparaît jamais : elle vit dans Historique.
ACCUEIL_PAR_ROLE = {
    GESTIONNAIRE: (NOUVELLE, EN_TRAITEMENT, RETOURNEE),
    CHEF_SERVICE: (ENVOYEE_CS,),
    CHEF_SUBDIVISION: (ENVOYEE_CSUB,),
}

# Statut éditable (rapport/décision) par rôle
STATUT_EDITABLE_PAR_ROLE = {
    GESTIONNAIRE: EN_TRAITEMENT,
    CHEF_SERVICE: ENVOYEE_CS,
    CHEF_SUBDIVISION: ENVOYEE_CSUB,
}

TAX_TYPES = ("IS", "IR", "TVA")
TYPES_DECISION = ("Rejet", "Dégrèvement total", "Dégrèvement partiel")

# --- Migration des anciennes valeurs (versions précédentes de GEIF) ---
MIGRATION_STATUTS = {
    "attente": EN_TRAITEMENT,
    "attente_chef_secteur": ENVOYEE_CS,
    "attente_chef_subdivision": ENVOYEE_CSUB,
    "validee_finale": DECISION_ENVOYEE,
    "rejetee": RETOURNEE,   # ancien "rejeté" = dossier non abouti : on le rouvre
}
MIGRATION_ROLES = {"chef_secteur": CHEF_SERVICE}
