from __future__ import annotations

import json
from io import BytesIO, StringIO
from pathlib import Path
from urllib import error, parse, request

import pandas as pd
import streamlit as st


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_FASTA_PATH = Path(__file__).resolve().parent / "data" / "GCA_032124935.1_PDT001903532.1_genomic.fna"


def http_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict | list:
    req = request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach backend: {exc.reason}") from exc


def encode_multipart(fields: dict[str, str], file_field: str, file_name: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----amrstreamlitboundary"
    lines: list[bytes] = []

    for key, value in fields.items():
        lines.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                f"{value}\r\n".encode(),
            ]
        )

    lines.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    body = b"".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


def ingest_fasta(base_url: str, batch_id: str, biosample: str, file_name: str, file_bytes: bytes) -> dict:
    body, content_type = encode_multipart(
        {k: v for k, v in {"batch_id": batch_id, "biosample": biosample}.items() if v},
        "file",
        file_name,
        file_bytes,
    )
    return http_json(
        f"{base_url.rstrip('/')}/ingest-fasta-single",
        method="POST",
        data=body,
        headers={"Content-Type": content_type},
    )


def predict_csv(base_url: str, scope: str, antibiotic: str, threshold: float, file_name: str, file_bytes: bytes) -> dict:
    body, content_type = encode_multipart(
        {"scope": scope, "antibiotic": antibiotic, "threshold": str(threshold)},
        "file",
        file_name,
        file_bytes,
    )
    return http_json(
        f"{base_url.rstrip('/')}/predict-csv",
        method="POST",
        data=body,
        headers={"Content-Type": content_type},
    )


def trigger_processing(base_url: str, batch_id: str, scope: str, antibiotic: str) -> dict:
    body = json.dumps(
        {
            "batch_id": batch_id,
            "scope": scope,
            "antibiotic": antibiotic,
        }
    ).encode("utf-8")
    return http_json(
        f"{base_url.rstrip('/')}/process-fasta-batch",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )


def build_process_command(batch_id: str, status_payload: dict | None, manifest_payload: dict | None) -> str:
    bronze_input_dir = (
        (status_payload or {}).get("bronze_input_dir")
        or (manifest_payload or {}).get("bronze_input_dir")
        or f"data/bronze/fasta_batches/{batch_id}"
    )
    scope = (manifest_payload or {}).get("scope") or "all"
    antibiotic = (manifest_payload or {}).get("antibiotic") or "ampicillin"
    return "\n".join(
        [
            "python scripts/process_fasta_batch.py \\",
            f"  --input-dir {bronze_input_dir} \\",
            f"  --scope {scope} \\",
            f'  --antibiotic "{antibiotic}" \\',
            f"  --batch-id {batch_id}",
        ]
    )


def render_status_badge(status: str) -> str:
    palette = {
        "ingested": "#856404",
        "processing": "#8b3d06",
        "completed": "#1f5f3b",
        "failed": "#9a1f2b",
    }
    background = {
        "ingested": "#fff3cd",
        "processing": "#ffe0c2",
        "completed": "#d8f3dc",
        "failed": "#ffd6db",
    }
    return (
        f"<span style='display:inline-block;padding:0.35rem 0.75rem;border-radius:999px;"
        f"background:{background.get(status, '#e9ecef')};color:{palette.get(status, '#333')};"
        "font-weight:700;text-transform:uppercase;letter-spacing:0.08em;font-size:0.75rem;'>"
        f"{status}</span>"
    )


st.set_page_config(
    page_title="AMR Pipeline Console",
    page_icon="🧬",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp {
        background:
          radial-gradient(circle at top left, rgba(159, 61, 34, 0.14), transparent 28%),
          radial-gradient(circle at 85% 10%, rgba(88, 107, 49, 0.12), transparent 24%),
          linear-gradient(180deg, #faf6eb 0%, #f1ede2 100%);
      }
      .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
      }
      .amr-hero {
        padding: 1.5rem 1.75rem;
        border-radius: 24px;
        background: rgba(255, 251, 243, 0.84);
        border: 1px solid rgba(25, 33, 25, 0.08);
        box-shadow: 0 18px 44px rgba(25, 33, 25, 0.08);
        margin-bottom: 1rem;
      }
      .amr-kicker {
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: #9f3d22;
        font-size: 0.72rem;
        margin-bottom: 0.4rem;
        font-weight: 700;
      }
      .amr-title {
        margin: 0;
        font-size: 2.6rem;
        line-height: 1;
        color: #182018;
        font-family: "Iowan Old Style", "Palatino Linotype", serif;
      }
      .amr-lead {
        color: #5f6558;
        margin-top: 0.8rem;
        max-width: 70ch;
      }
      div[data-testid="stMetric"] {
        background: rgba(255, 251, 243, 0.82);
        border: 1px solid rgba(25, 33, 25, 0.08);
        border-radius: 18px;
        padding: 0.7rem 1rem;
      }
      div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 20px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if "last_batch_id" not in st.session_state:
    st.session_state.last_batch_id = ""

st.markdown(
    """
    <div class="amr-hero">
      <div class="amr-kicker">AMR Prediction Pipeline</div>
      <h1 class="amr-title">Streamlit console for ingestion, tracking, and serving</h1>
      <p class="amr-lead">
        This app matches the staged micro-batch architecture now implemented in the backend:
        ingest raw FASTA, track the batch lifecycle, run external processing, and serve
        predictions from feature-ready input.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Connection")
    base_url = st.text_input("Backend base URL", value=DEFAULT_BASE_URL)
    st.caption("Run FastAPI first, then point Streamlit at the same host.")

try:
    health = http_json(f"{base_url.rstrip('/')}/health")
    models = http_json(f"{base_url.rstrip('/')}/models")
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

health_cols = st.columns(3)
health_cols[0].metric("Backend", health["status"])
health_cols[1].metric("Loaded models", health["loaded_model_count"])
health_cols[2].metric("Artifact root", health["artifact_root"].split("/")[-1])

scope_options = sorted({model["scope"] for model in models}) or ["all"]
default_scope = scope_options[0]
selected_scope = st.selectbox("Model scope", scope_options, index=scope_options.index(default_scope))
scope_models = [model for model in models if model["scope"] == selected_scope]
antibiotic_options = [model["antibiotic"] for model in scope_models]
selected_antibiotic = st.selectbox("Antibiotic", antibiotic_options, index=0 if antibiotic_options else None)

tab_ingest, tab_batch, tab_predict, tab_models = st.tabs(
    ["Ingest FASTA", "Batch tracking", "Predict from CSV", "Model registry"]
)

with tab_ingest:
    st.subheader("Step 1: Ingest FASTA into bronze")
    with st.form("ingest_form"):
        batch_id = st.text_input("Batch ID", value=st.session_state.last_batch_id, help="Leave blank to auto-generate.")
        biosample = st.text_input("Biosample", value="")
        fasta_upload = st.file_uploader("FASTA file", type=["fa", "faa", "fasta", "fna"])
        submitted = st.form_submit_button("Ingest FASTA")

    if submitted:
        if not fasta_upload:
            st.error("Upload a FASTA file first.")
        else:
            try:
                payload = ingest_fasta(
                    base_url,
                    batch_id.strip(),
                    biosample.strip(),
                    fasta_upload.name,
                    fasta_upload.getvalue(),
                )
                st.session_state.last_batch_id = payload["batch_id"]
                st.success("FASTA ingested into bronze storage.")
                st.markdown(render_status_badge(payload["status"]), unsafe_allow_html=True)
                st.json(payload)
            except RuntimeError as exc:
                st.error(str(exc))

    if DEFAULT_FASTA_PATH.exists():
        st.caption(
            f"Sample FASTA available locally at `{DEFAULT_FASTA_PATH}` if you want a ready-made demo input."
        )

with tab_batch:
    st.subheader("Step 2: Track batch lifecycle")
    batch_lookup = st.text_input("Batch ID to inspect", value=st.session_state.last_batch_id)
    action_cols = st.columns([1, 1, 3])
    lookup_clicked = action_cols[0].button("Fetch status and manifest")
    process_clicked = action_cols[1].button("Start processing", type="primary")

    status_payload = None
    manifest_payload = None
    if (lookup_clicked or process_clicked) and not batch_lookup.strip():
        st.error("Enter a batch ID first.")
    if (lookup_clicked or process_clicked) and batch_lookup.strip():
        try:
            if process_clicked:
                trigger_response = trigger_processing(
                    base_url=base_url,
                    batch_id=batch_lookup.strip(),
                    scope=selected_scope,
                    antibiotic=selected_antibiotic,
                )
                st.success(trigger_response["message"])

            status_payload = http_json(f"{base_url.rstrip('/')}/status/{parse.quote(batch_lookup.strip())}")
            manifest_payload = http_json(f"{base_url.rstrip('/')}/manifest/{parse.quote(batch_lookup.strip())}")
            st.markdown(render_status_badge(status_payload["status"]), unsafe_allow_html=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Status**")
                st.json(status_payload)
            with col_b:
                st.markdown("**Manifest**")
                st.json(manifest_payload)

            with st.expander("Advanced fallback: shell command", expanded=False):
                st.code(build_process_command(batch_lookup.strip(), status_payload, manifest_payload), language="bash")
        except RuntimeError as exc:
            st.error(str(exc))

with tab_predict:
    st.subheader("Step 3: Serve predictions from feature-ready CSV")
    threshold = st.slider("Prediction threshold", min_value=0.0, max_value=1.0, value=0.5, step=0.01)
    csv_upload = st.file_uploader("Feature-ready CSV", type=["csv"], key="csv_predict")

    if st.button("Run predict-csv"):
        if not csv_upload:
            st.error("Upload a feature-ready CSV first.")
        else:
            try:
                response = predict_csv(
                    base_url,
                    selected_scope,
                    selected_antibiotic,
                    threshold,
                    csv_upload.name,
                    csv_upload.getvalue(),
                )
                st.success("Prediction complete.")
                metric_cols = st.columns(4)
                metric_cols[0].metric("Rows", response["row_count"])
                metric_cols[1].metric("Features", response["feature_count"])
                metric_cols[2].metric("Scope", response["scope"])
                metric_cols[3].metric("Antibiotic", response["antibiotic"])
                st.dataframe(pd.DataFrame(response["rows"]), use_container_width=True)
            except RuntimeError as exc:
                st.error(str(exc))

with tab_models:
    st.subheader("Loaded model bundles")
    if scope_models:
        st.dataframe(pd.DataFrame(scope_models), use_container_width=True)
    else:
        st.info("No models loaded for this scope.")
