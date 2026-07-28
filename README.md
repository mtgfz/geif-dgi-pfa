# GEIF — Gestion Électronique Intelligente des Flux fiscaux

Projet PFA 2ème année — Data & Software Sciences, ENSIAS.
Stage : Direction Régionale des Impôts (DRI) de Rabat, Subdivision Fiscalité des Personnes Morales.

## 🎯 Objectif

Automatiser le traitement documentaire fiscal (lecture, classification, validation, détection
d'anomalies) et anticiper la charge de travail du service via la prévision de volume.

Ce projet a été conçu pour rassembler, de façon **cohérente et honnête** (pas superficielle),
les principaux domaines étudiés cette année en Data & Software Sciences.

## 🏛️ Les 5 piliers du projet

| # | Pilier | Où | Ce que ça fait |
|---|---|---|---|
| 1 | **Computer Vision** | `cv_ocr/` | OCR (Tesseract) sur documents scannés + extraction de champs |
| 2 | **Machine Learning** | `ml_classification/` | Classification de type de document (TF-IDF + LogReg) + détection d'anomalies (z-score) |
| 3 | **Deep Learning** | `deep_learning/` | CNN de classification visuelle (mise en page du document), complémentaire au ML texte |
| 4 | **Time Series** | `time_series/` | Prévision du volume mensuel de documents par type d'impôt (baseline saisonnière + SARIMAX) |
| 5 | **Full Stack + DevOps** | `backend/`, `dashboard/`, `devops/` | API FastAPI, dashboard Streamlit, Docker, CI GitHub Actions |

**Choix assumé :** pas de Reinforcement Learning (pas d'usage naturel identifié — mieux vaut
5 piliers solides qu'un 6ème forcé). Le "Big Data" est traité comme un choix d'architecture
scalable plutôt qu'un vrai volume massif (le dataset est synthétique, à échelle raisonnable
pour un POC d'un mois).

## 📂 Structure du repo

```
geif-dgi-pfa/
├── data/
│   ├── generators/        # Scripts de génération de données synthétiques
│   ├── raw/                # (vide, réservé à d'éventuelles données réelles anonymisées)
│   └── processed/          # Données générées (ignorées par git, reproductibles via scripts)
├── cv_ocr/                 # Pilier 1 — OCR + extraction de champs
├── ml_classification/      # Pilier 2 — Classification ML + anomalies
├── deep_learning/          # Pilier 3 — CNN de classification visuelle
├── time_series/            # Pilier 4 — Prévision de volume
├── backend/                # Pilier 5 — API FastAPI
├── dashboard/               # Pilier 5 — Dashboard Streamlit
├── devops/                  # Pilier 5 — Dockerfile, docker-compose
├── .github/workflows/       # CI (tests automatiques à chaque push)
├── docs/                    # Rapport, diagrammes
└── notebooks/                # Exploration ponctuelle (EDA, prototypage)
```

## 🚀 Reproduire le pipeline complet

```bash
pip install -r requirements.txt

# 1. Générer les données synthétiques
cd data/generators
python generate_documents.py --n 200 --out ../processed/synthetic_dataset
python generate_fiscal_timeseries.py --years 3 --out ../processed/fiscal_timeseries.csv
python build_training_corpus.py --dataset ../processed/synthetic_dataset --out ../processed/training_corpus.json

# 2. Entraîner les modèles
cd ../../ml_classification
python classifier.py train --corpus ../data/processed/training_corpus.json --model ./model.joblib

cd ../deep_learning
python train_cnn_classifier.py --dataset ../data/processed/synthetic_dataset --epochs 15

# 3. Prévision de volume
cd ../time_series
python forecast_volume.py --tax-type TVA --horizon 6

# 4. Lancer l'API + le dashboard
cd ../backend
uvicorn main:app --reload --port 8000
# (dans un autre terminal)
cd ../dashboard
streamlit run app.py
```

## ⚠️ Confidentialité

Aucune donnée réelle de contribuable n'est utilisée. Toutes les données (documents,
historique temporel) sont générées synthétiquement via les scripts de `data/generators/`.

## 🔬 Limites connues (à assumer dans le rapport, pas à cacher)

- **CNN visuel** : entraîné sur peu d'images synthétiques dans le POC — accuracy monte
  progressivement avec plus de données/epochs, ce qui est normal et attendu pour un DL from-scratch.
- **Time series** : la saisonnalité est simulée de façon simplifiée ; en conditions réelles,
  d'autres facteurs (jours fériés, campagnes de relance) influenceraient le volume.
- **Big Data** : l'architecture est pensée pour être compatible avec un traitement par batch à
  plus grande échelle, mais le volume actuel reste un POC, pas un vrai big data.

## 📈 Extensions possibles

- Réutiliser les modèles BiLSTM/N-BEATS/TiDE du projet AIOps pour la prévision (au lieu de
  SARIMAX) si le temps le permet.
- RAG/chatbot pour les questions fréquentes des contribuables.
- Intégration réelle avec un système comme SIT/SIMPL (voir chapitre 1 du rapport).
