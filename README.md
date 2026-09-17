# GEIF — Gestion Électronique Intelligente des Flux fiscaux

Projet PFA 2ème année — Data & Software Sciences, ENSIAS.
Stage : Direction Régionale des Impôts (DRI) de Rabat, Subdivision Fiscalité des Personnes Morales.

## 🎯 Objectif

Automatiser le traitement documentaire fiscal (lecture, classification, validation, détection
d'anomalies) et anticiper la charge de travail du service via la prévision de volume — et,
plus récemment, automatiser le traitement de premier niveau des réclamations fiscales (IS, IR,
TVA) en s'appuyant sur une recherche réelle dans le Code Général des Impôts (CGI), avec
validation humaine systématique avant toute décision finale.

Ce projet a été conçu pour rassembler, de façon **cohérente et honnête** (pas superficielle),
les principaux domaines étudiés cette année en Data & Software Sciences.

## 🏛️ Les piliers du projet

| # | Pilier                        | Où                                     | Ce que ça fait |
|---|-------------------------------|-----------------------------------------|-----------------|
| 1 | **Computer Vision**            | `cv_ocr/`                               | OCR (Tesseract) sur documents scannés + extraction de champs |
| 2 | **Machine Learning**            | `ml_classification/`                    | Classification de type de document (TF-IDF + LogReg) + détection d'anomalies (z-score) |
| 3 | **Deep Learning**               | `deep_learning/`                        | CNN de classification visuelle (mise en page du document), complémentaire au ML texte |
| 4 | **Time Series**                 | `time_series/`                          | Prévision du volume mensuel de documents par type d'impôt (baseline saisonnière + SARIMAX) |
| 5 | **Full Stack + DevOps**         | `backend/`, `dashboard/`, `devops/`      | API FastAPI, dashboard Streamlit, Docker, CI GitHub Actions |
| 6 | **Données Marché (AMMC)**       | `market_data/`                          | Scraping réel de 7 banques marocaines cotées (ammc.ma) → parsing PDF → validation comptable → DuckDB → Superset |
| 7 | **Réclamations automatisées (RAG + LLM + apprentissage)** | `rag/`, `backend/reclamations_api.py` | Traitement automatique des réclamations IS/IR/TVA : recherche réelle dans le CGI (RAG local, ChromaDB), génération du rapport/décision par LLM (Groq), apprentissage bayésien (bandit Beta-Bernoulli) sur la confiance par règle à partir des validations du gestionnaire |

**Sur le choix "pas de RL" de la version précédente** : le pilier 7 introduit un bandit
Beta-Bernoulli pour ajuster la confiance de chaque règle CGI selon les décisions du
gestionnaire (accepter / modifier / rejeter) — une vraie technique de RL (simple, mais
authentique), avec un usage naturel identifié a posteriori. À assumer comme une évolution
du projet, pas une incohérence cachée.

## 📂 Structure du repo

```
geif-dgi-pfa/
├── data/
│   ├── generators/          # Scripts de génération de données synthétiques
│   ├── raw/                  # (vide, réservé à d'éventuelles données réelles anonymisées)
│   └── processed/            # Données générées (ignorées par git, reproductibles via scripts)
├── cv_ocr/                   # Pilier 1 — OCR + extraction de champs
├── ml_classification/        # Pilier 2 — Classification ML + anomalies
├── deep_learning/            # Pilier 3 — CNN de classification visuelle
├── time_series/              # Pilier 4 — Prévision de volume
├── backend/                  # Pilier 5 — API FastAPI (+ reclamations_api.py, pilier 7)
├── dashboard/                 # Pilier 5 — Dashboard Streamlit
├── devops/                    # Pilier 5 — Dockerfile, docker-compose
├── market_data/                # Pilier 6 — Scraper AMMC, parsing PDF, chargement DuckDB
│   ├── scraper/
│   ├── parsing/
│   └── analytics/
├── rag/                        # Pilier 7 — Ingestion du CGI, base vectorielle (ChromaDB)
│   ├── ingest_pdfs.py
│   └── data/CGI.pdf
├── .github/workflows/          # CI (tests automatiques à chaque push)
├── docs/                        # Rapport, diagrammes
└── notebooks/                    # Exploration ponctuelle (EDA, prototypage)
```

## 🚀 Reproduire le pipeline complet

```powershell
pip install -r requirements.txt

# 1. Générer les données synthétiques (piliers 1-4)
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

# 4. Pilier 6 — Marché AMMC
cd ../market_data/scraper
python ammc_scraper.py
cd ../parsing
python financial_pdf_parser.py
cd ../analytics
python load_to_duckdb.py

# 5. Pilier 7 — RAG sur le CGI (une fois, ou après mise à jour du PDF)
cd ../../rag
python ingest_pdfs.py --cgi data\CGI.pdf

# 6. Lancer les APIs + le dashboard
cd ../backend
uvicorn main:app --reload --port 8000
# dans un autre terminal : le moteur de réclamations (pilier 7)
uvicorn reclamations_api:app --port 8010
# dans un autre terminal : le dashboard
cd ../dashboard
streamlit run app.py
```

## ⚠️ Confidentialité

Aucune donnée réelle de contribuable n'est utilisée pour les piliers 1-4 (données synthétiques,
scripts dans `data/generators/`). Les données du pilier 6 (AMMC) sont des états financiers
publics de sociétés cotées, pas des données de contribuables. Le pilier 7 (réclamations) traite
des cas fictifs à ce stade — aucun dossier réel de contribuable n'y a été introduit.

## 🔬 Limites connues (à assumer dans le rapport, pas à cacher)

- **CNN visuel** : entraîné sur peu d'images synthétiques dans le POC — accuracy monte
  progressivement avec plus de données/epochs, ce qui est normal et attendu pour un DL from-scratch.
- **Time series** : la saisonnalité est simulée de façon simplifiée ; en conditions réelles,
  d'autres facteurs (jours fériés, campagnes de relance) influenceraient le volume.
- **Big Data** : l'architecture est pensée pour être compatible avec un traitement par batch à
  plus grande échelle, mais le volume actuel reste un POC, pas un vrai big data.
- **Marché AMMC (pilier 6)** : sur 42 rapports annuels collectés, seuls 9 exercices sont validés
  avec certitude par le contrôle comptable automatique (Total Actif = Total Passif) ; les autres
  échouent surtout sur des structures de rapport non standard (ex. Attijariwafa, rapport
  consolidé sur 100+ pages).
- **RAG / réclamations (pilier 7)** : le retrieval sémantique sur le CGI est solide sur les cas
  testés pour le délai de réclamation et les charges déductibles IS, mais reste imparfait sur
  certaines questions TVA (articles noyés parmi des mentions lexicalement proches). C'est
  pourquoi la validation humaine du gestionnaire reste obligatoire avant toute décision finale —
  ce n'est pas un système entièrement autonome.

## 📈 Extensions possibles

- Étendre le retrieval RAG avec un modèle de ré-classement (cross-encoder) pour améliorer la
  précision sur les cas ambigus (TVA notamment).
- Étendre la couverture AMMC aux 33 exercices restants.
- Étendre le moteur de réclamations à TP/TSC/TL (régis par la loi 47-06, pas le CGI — corpus
  RAG séparé à construire).
- Intégration réelle avec un système comme SIT/SIMPL (voir chapitre 1 du rapport).
