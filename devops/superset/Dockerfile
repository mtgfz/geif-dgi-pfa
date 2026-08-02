# GEIF — Apache Superset avec support DuckDB
# ================================================
# Étend l'image officielle Superset en ajoutant le driver DuckDB
# (duckdb-engine), pour se connecter directement à nos fichiers .duckdb
# sans avoir besoin de migrer vers PostgreSQL.
FROM apache/superset:3.1.0

USER root
RUN pip install --no-cache-dir duckdb-engine==0.13.6
USER superset
