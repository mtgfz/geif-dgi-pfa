# Apache Superset — Guide de configuration (GEIF)

Ce guide remplace le dashboard Streamlit par Apache Superset, un vrai outil de BI
professionnel. La partie "clic dans l'interface" doit être faite par toi (je ne
peux pas cliquer dans un navigateur depuis mon environnement) — mais tout le
reste (config, données) est déjà prêt et testé.

## 1. Préparer les données (une seule fois, ou après chaque régénération)

Depuis la racine du projet :

```powershell
cd data\generators
python generate_fiscal_timeseries.py --years 3 --out ../processed/fiscal_timeseries.csv
python generate_large_scale_facts.py --n 500000 --warehouse ../../data_engineering/fiscal_warehouse.duckdb --out ../processed/fact_transactions.parquet

cd ..\..\data_engineering
python build_mock_warehouse.py --n 20000 --out ./fiscal_warehouse.duckdb
python load_irs_data.py --csv ../data/raw/irs_soi/22zpallagi.csv --duckdb ../data/processed/irs_warehouse.duckdb
python build_analytics_duckdb.py --out ./analytics.duckdb
```

Ça crée `data_engineering/analytics.duckdb`, un seul fichier avec toutes les tables
(fact_transactions, dim_contribuables, irs_zip_income, fiscal_timeseries).

## 2. Lancer Superset (Docker Desktop requis)

```powershell
cd devops
docker compose up -d --build
```

Premier lancement : ça peut prendre 3-5 minutes (téléchargement de l'image + build).

## 3. Se connecter à l'interface

Ouvre http://localhost:8088 dans ton navigateur.

- **Utilisateur :** `admin`
- **Mot de passe :** `admin2026`

## 4. Ajouter la connexion à notre base DuckDB

1. Menu en haut à droite → **Settings** → **Database Connections**
2. **+ Database**
3. Choisis **"Other"** comme type de base (DuckDB n'est pas dans la liste déroulante par défaut)
4. Dans **SQLAlchemy URI**, mets :
   ```
   duckdb:////app/geif_warehouse/analytics.duckdb
   ```
5. Teste la connexion (**Test Connection**) — doit afficher "Connexion réussie"
6. Valide

## 5. Créer tes premiers datasets

1. Menu **Datasets** → **+ Dataset**
2. Choisis la base DuckDB créée à l'étape 4
3. Sélectionne une table (ex : `fact_transactions`)
4. Répète pour `irs_zip_income`, `fiscal_timeseries`, `dim_contribuables`

## 6. Créer des graphiques (Charts)

Idées de graphiques à recréer (équivalents à ce qu'on avait dans Streamlit, en mieux) :

| Graphique | Table source | Type de chart Superset |
|---|---|---|
| Volume de transactions par type d'impôt | `fact_transactions` | Bar Chart |
| Évolution du volume dans le temps | `fiscal_timeseries` | Line Chart (time series) |
| Répartition des anomalies | `fact_transactions` (filtre `is_anomaly`) | Pie Chart |
| Carte des ZIP codes atypiques (IRS) | `irs_zip_income` | Table ou Big Number |
| Top contribuables par valeur locative | `dim_contribuables` | Bar Chart horizontal |

## 7. Assembler un Dashboard

Menu **Dashboards** → **+ Dashboard** → glisse-dépose les charts créés à l'étape 6.

## Dépannage

- **"Connection failed" à l'étape 4** : vérifie que les fichiers sont bien montés — dans le conteneur, le chemin est `/app/geif_warehouse/analytics.duckdb` (mappé depuis `data_engineering/` sur ta machine, voir `docker-compose.yml`)
- **Superset très lent au démarrage** : normal la première fois (il initialise sa propre base de métadonnées), les lancements suivants sont plus rapides
- **Je change mes données et Superset ne les voit pas** : rafraîchis le dataset dans Superset (bouton "Refresh" sur le dataset), ou relance `build_analytics_duckdb.py` puis redémarre le conteneur Superset
