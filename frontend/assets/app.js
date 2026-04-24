const state = {
  models: [],
  currentBatchId: "",
  currentStatus: null,
  currentManifest: null,
};

const healthStatus = document.querySelector("#health-status");
const healthDetail = document.querySelector("#health-detail");
const scopeSelect = document.querySelector("#scope-select");
const antibioticSelect = document.querySelector("#antibiotic-select");
const modelsGrid = document.querySelector("#models-grid");
const ingestOutput = document.querySelector("#ingest-output");
const statusOutput = document.querySelector("#status-output");
const manifestOutput = document.querySelector("#manifest-output");
const processCommand = document.querySelector("#process-command");
const processBatchButton = document.querySelector("#process-batch-button");
const processResult = document.querySelector("#process-result");
const predictSummary = document.querySelector("#predict-summary");
const predictionTableBody = document.querySelector("#prediction-table tbody");

processBatchButton.disabled = true;

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.json();
}

function renderHealth(health) {
  healthStatus.textContent = health.status === "ok" ? "Online" : health.status;
  healthDetail.textContent = `${health.loaded_model_count} models loaded from ${health.artifact_root}`;
}

function renderModels(models) {
  state.models = models;
  const scopes = [...new Set(models.map((model) => model.scope))];
  scopeSelect.innerHTML = scopes.map((scope) => `<option value="${scope}">${scope}</option>`).join("");

  updateAntibiotics(scopeSelect.value || scopes[0] || "");

  if (!models.length) {
    modelsGrid.innerHTML = '<div class="empty-state">No models loaded.</div>';
    return;
  }

  const template = document.querySelector("#model-card-template");
  modelsGrid.innerHTML = "";

  for (const model of models) {
    const fragment = template.content.cloneNode(true);
    fragment.querySelector(".model-scope").textContent = model.scope;
    fragment.querySelector(".model-name").textContent = model.antibiotic;
    fragment.querySelector(".model-features").textContent = model.n_features;
    fragment.querySelector(".model-samples").textContent = model.n_samples ?? "Unknown";
    modelsGrid.appendChild(fragment);
  }
}

function updateAntibiotics(selectedScope) {
  const filtered = state.models.filter((model) => model.scope === selectedScope);
  antibioticSelect.innerHTML = filtered
    .map((model) => `<option value="${model.antibiotic}">${model.antibiotic}</option>`)
    .join("");
}

function renderStatusCard(status) {
  const statusClass = ["status-pill", status.status].join(" ");
  return `
    <div class="${statusClass}">${status.status}</div>
    <p><strong>Batch ID:</strong> ${status.batch_id}</p>
    <p><strong>Created:</strong> ${status.created_at ?? "N/A"}</p>
    <p><strong>Updated:</strong> ${status.updated_at ?? "N/A"}</p>
    ${status.next_step ? `<p><strong>Next step:</strong> ${status.next_step}</p>` : ""}
  `;
}

function buildProcessingCommand(batchId, manifest, status) {
  const bronzeInputDir = status?.bronze_input_dir || manifest?.bronze_input_dir || `data/bronze/fasta_batches/${batchId}`;
  const scope = manifest?.scope || scopeSelect.value || "all";
  const antibiotic = manifest?.antibiotic || antibioticSelect.value || "ampicillin";
  return [
    "python scripts/process_fasta_batch.py \\",
    `  --input-dir ${bronzeInputDir} \\`,
    `  --scope ${scope} \\`,
    `  --antibiotic "${antibiotic}" \\`,
    `  --batch-id ${batchId}`,
  ].join("\n");
}

async function loadStatusAndManifest(batchId) {
  const [status, manifest] = await Promise.all([
    getJson(`/status/${encodeURIComponent(batchId)}`),
    getJson(`/manifest/${encodeURIComponent(batchId)}`),
  ]);

  state.currentBatchId = batchId;
  state.currentStatus = status;
  state.currentManifest = manifest;
  statusOutput.textContent = formatJson(status);
  manifestOutput.textContent = formatJson(manifest);
  processCommand.textContent = buildProcessingCommand(batchId, manifest, status);
  processBatchButton.disabled = false;
  return { status, manifest };
}

async function triggerBatchProcessing(batchId) {
  return getJson("/process-fasta-batch", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      batch_id: batchId,
      scope: scopeSelect.value || "all",
      antibiotic: antibioticSelect.value,
    }),
  });
}

async function initialize() {
  try {
    const [health, models] = await Promise.all([getJson("/health"), getJson("/models")]);
    renderHealth(health);
    renderModels(models);
  } catch (error) {
    healthStatus.textContent = "Unavailable";
    healthDetail.textContent = error.message;
    modelsGrid.innerHTML = `<div class="empty-state">${error.message}</div>`;
  }
}

scopeSelect.addEventListener("change", (event) => {
  updateAntibiotics(event.target.value);
});

document.querySelector("#ingest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);

  try {
    const response = await getJson("/ingest-fasta-single", {
      method: "POST",
      body: formData,
    });

    ingestOutput.classList.remove("empty-state");
    ingestOutput.innerHTML = `
      ${renderStatusCard(response)}
      <p><strong>Biosample:</strong> ${response.biosample}</p>
      <p><strong>Stored FASTA:</strong> ${response.stored_fasta_path}</p>
      <p><strong>Manifest:</strong> ${response.manifest_path}</p>
    `;

    document.querySelector('#lookup-form input[name="batch_id"]').value = response.batch_id;
    await loadStatusAndManifest(response.batch_id);
    processResult.classList.add("empty-state");
    processResult.textContent = "FASTA ingested. Press Start processing when you are ready.";
  } catch (error) {
    ingestOutput.classList.remove("empty-state");
    ingestOutput.textContent = error.message;
  }
});

document.querySelector("#lookup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const batchId = new FormData(event.currentTarget).get("batch_id");

  try {
    await loadStatusAndManifest(String(batchId).trim());
    processResult.classList.add("empty-state");
    processResult.textContent = "Batch loaded. You can trigger processing from the button above.";
  } catch (error) {
    statusOutput.textContent = error.message;
    manifestOutput.textContent = error.message;
    processCommand.textContent = "Unable to generate processing command for this batch.";
    processBatchButton.disabled = true;
    processResult.classList.remove("empty-state");
    processResult.textContent = error.message;
  }
});

processBatchButton.addEventListener("click", async () => {
  const batchId =
    state.currentBatchId ||
    String(new FormData(document.querySelector("#lookup-form")).get("batch_id") || "").trim();

  if (!batchId) {
    processResult.classList.remove("empty-state");
    processResult.textContent = "Load or ingest a batch first.";
    return;
  }

  try {
    processBatchButton.disabled = true;
    processResult.classList.remove("empty-state");
    processResult.textContent = "Starting background processing...";
    const response = await triggerBatchProcessing(batchId);
    await loadStatusAndManifest(batchId);
    processResult.innerHTML = `
      <div class="${["status-pill", response.status].join(" ")}">${response.status}</div>
      <p><strong>Scope:</strong> ${response.scope}</p>
      <p><strong>Antibiotic:</strong> ${response.antibiotic}</p>
      <p>${response.message}</p>
    `;
  } catch (error) {
    processResult.textContent = error.message;
  } finally {
    processBatchButton.disabled = false;
  }
});

document.querySelector("#predict-csv-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);

  try {
    const response = await getJson("/predict-csv", {
      method: "POST",
      body: formData,
    });

    predictSummary.classList.remove("empty-state");
    predictSummary.innerHTML = `
      <p><strong>Scope:</strong> ${response.scope}</p>
      <p><strong>Antibiotic:</strong> ${response.antibiotic}</p>
      <p><strong>Rows:</strong> ${response.row_count}</p>
      <p><strong>Feature count:</strong> ${response.feature_count}</p>
    `;

    predictionTableBody.innerHTML = response.rows
      .map(
        (row) => `
          <tr>
            <td>${row.biosample}</td>
            <td>${Number(row.probability_resistant).toFixed(4)}</td>
            <td>${row.predicted_label}</td>
          </tr>
        `
      )
      .join("");
  } catch (error) {
    predictSummary.classList.remove("empty-state");
    predictSummary.textContent = error.message;
    predictionTableBody.innerHTML = '<tr><td colspan="3" class="table-empty">Prediction failed.</td></tr>';
  }
});

initialize();
