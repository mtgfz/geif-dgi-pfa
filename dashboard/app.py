"""
GEIF - Dashboard de suivi
============================
Interface de supervision pour les agents/responsables : volumes traités,
répartition par type, taux d'anomalies, et détail des documents flagués.

Lancer :
    streamlit run app.py
"""
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

API_URL = "http://localhost:8000"

st.set_page_config(page_title="GEIF — Tableau de bord", page_icon="🗂️", layout="wide")

st.title("🗂️ GEIF — Gestion Electronique Intelligente des Flux fiscaux")
st.caption("Direction Régionale des Impôts — Tableau de bord de supervision du traitement documentaire")


@st.cache_data(ttl=10)
def fetch_stats():
    try:
        r = requests.get(f"{API_URL}/stats", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Impossible de contacter l'API GEIF ({API_URL}). Est-elle lancée ? Détail : {e}")
        return None


@st.cache_data(ttl=10)
def fetch_documents():
    try:
        r = requests.get(f"{API_URL}/documents", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


stats = fetch_stats()
documents = fetch_documents()

if stats is None:
    st.stop()

# --- KPIs ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Documents traités", stats["total_documents"])
col2.metric("Documents flagués", stats["flagged_documents"])
col3.metric("Taux de flag", f"{stats['flagged_rate']*100:.1f}%")
col4.metric("Types de documents", len(stats["documents_by_type"]))

st.divider()

# --- Répartition par type ---
col_left, col_right = st.columns([1, 1])

with col_left:
    st.subheader("Répartition par type de document")
    if stats["documents_by_type"]:
        df_types = pd.DataFrame(
            list(stats["documents_by_type"].items()), columns=["Type", "Nombre"]
        )
        fig = px.pie(df_types, names="Type", values="Nombre", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucun document traité pour le moment.")

with col_right:
    st.subheader("Documents nécessitant une vérification")
    if documents:
        df_docs = pd.DataFrame(documents)
        flagged_df = df_docs[df_docs["is_flagged"] == True] if "is_flagged" in df_docs else pd.DataFrame()
        if not flagged_df.empty:
            display_df = flagged_df[["id", "filename", "predicted_type", "prediction_confidence"]].copy()
            display_df.columns = ["ID", "Fichier", "Type prédit", "Confiance"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.success("Aucun document flagué actuellement.")
    else:
        st.info("Aucun document traité pour le moment.")

st.divider()

# --- Prévision de volume (pilier Time Series) ---
st.subheader("📈 Prévision du volume de documents (Time Series)")
col_fc1, col_fc2 = st.columns([1, 3])
with col_fc1:
    tax_type_fc = st.selectbox("Type d'impôt", ["TVA", "IS", "IR", "TP"])
    horizon_fc = st.slider("Horizon (mois)", 1, 12, 6)

try:
    fc_resp = requests.get(f"{API_URL}/forecast/{tax_type_fc}", params={"horizon": horizon_fc}, timeout=10)
    fc_resp.raise_for_status()
    fc_data = fc_resp.json()

    hist_df = pd.DataFrame(list(fc_data["historical"].items()), columns=["date", "volume"])
    hist_df["date"] = pd.to_datetime(hist_df["date"])
    hist_df["serie"] = "Historique"

    base_df = pd.DataFrame(list(fc_data["forecast_baseline_saisonnier"].items()), columns=["date", "volume"])
    base_df["date"] = pd.to_datetime(base_df["date"])
    base_df["serie"] = "Prévision (baseline saisonnière)"

    frames = [hist_df, base_df]
    if fc_data.get("forecast_sarimax"):
        sar_df = pd.DataFrame(list(fc_data["forecast_sarimax"].items()), columns=["date", "volume"])
        sar_df["date"] = pd.to_datetime(sar_df["date"])
        sar_df["serie"] = "Prévision (SARIMAX)"
        frames.append(sar_df)

    combined = pd.concat(frames)
    fig_fc = px.line(combined, x="date", y="volume", color="serie", markers=True)
    with col_fc2:
        st.plotly_chart(fig_fc, use_container_width=True)
except Exception as e:
    with col_fc2:
        st.info(f"Prévision indisponible pour le moment ({e}). Vérifie que fiscal_timeseries.csv existe.")

st.divider()

# --- Upload interactif ---
st.subheader("📤 Traiter un nouveau document")
uploaded_file = st.file_uploader("Dépose un document scanné (image)", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    if st.button("Lancer le traitement", type="primary"):
        with st.spinner("OCR → Classification → Validation → Détection d'anomalies..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
            try:
                resp = requests.post(f"{API_URL}/documents/upload", files=files, timeout=30)
                resp.raise_for_status()
                result = resp.json()

                st.success(f"Document classifié : **{result['predicted_type']}** (confiance {result['confidence']*100:.0f}%)")

                if result.get("cnn_prediction") and "error" not in result["cnn_prediction"]:
                    cnn = result["cnn_prediction"]
                    agree_icon = "✅ d'accord" if cnn["agrees_with_text_model"] else "⚠️ en désaccord"
                    st.caption(f"🧠 Modèle visuel (CNN) : **{cnn['predicted_type']}** (confiance {cnn['confidence']*100:.0f}%) — {agree_icon} avec le modèle texte")

                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Champs extraits :**")
                    st.json(result["extracted_fields"])
                with c2:
                    if result["missing_fields"]:
                        st.warning(f"Champs manquants : {', '.join(result['missing_fields'])}")
                    if result["anomalies"]:
                        st.error(f"⚠️ Anomalies détectées : {result['anomalies']}")
                    if not result["missing_fields"] and not result["anomalies"]:
                        st.success("✅ Document conforme, aucune anomalie détectée.")

                st.cache_data.clear()
            except Exception as e:
                st.error(f"Erreur lors du traitement : {e}")

st.divider()

# --- Tableau complet ---
st.subheader("📋 Historique complet des documents traités")
if documents:
    df_all = pd.DataFrame(documents)
    cols_to_show = [c for c in ["id", "filename", "predicted_type", "prediction_confidence", "is_flagged", "processed_at"] if c in df_all.columns]
    st.dataframe(df_all[cols_to_show], use_container_width=True, hide_index=True)
else:
    st.info("Aucun document dans l'historique.")
