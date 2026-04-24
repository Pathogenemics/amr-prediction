# Architecture Handoff

This file summarizes only the architecture-related changes that should be carried forward on the Ubuntu machine.

## Current state

The repository currently has a working FastAPI serving layer with these characteristics:

- Model artifacts are saved under `artifacts/`
- The API can load models and serve predictions
- The API currently supports:
  - `/health`
  - `/models`
  - `/predict`
  - `/predict-csv`
  - `/predict-fasta`
  - `/predict-fasta-single`

The important issue is architectural, not functional:

- FASTA preprocessing is currently happening inside the serving request path
- The serving layer is directly responsible for:
  - receiving FASTA
  - running `AMRFinderPlus`
  - parsing gene calls
  - mapping features
  - running model inference

This works for a prototype, but it is not the architecture we want to keep.

## Architectural problem

The current backend mixes two different responsibilities:

1. **Processing responsibility**
   - biological preprocessing
   - FASTA handling
   - `AMRFinderPlus`
   - feature construction

2. **Serving responsibility**
   - model registry
   - inference API
   - prediction response

These should be separated.

## Target architecture

The target architecture is:

**single-node, layered, micro-batch architecture**

This does **not** require multiple physical machines.
It only requires clearer logical separation between layers.

## Intended layers

### 1. Ingestion layer

Purpose:

- receive new incoming batch data
- place raw inputs into a controlled input area

Expected examples:

- `data/bronze/fasta_batches/batch_001/`
- `data/bronze/incoming_csv_batches/batch_001/`

### 2. Processing layer

Purpose:

- process raw FASTA or raw batch input
- run `AMRFinderPlus`
- parse AMR output
- normalize gene calls
- map genes to feature schema
- build feature-ready tables

Expected outputs:

- `data/silver/...` for intermediate processed outputs
- `data/gold/...` for final feature-ready tables

This layer should run as:

- batch script
- worker
- or micro-batch job

It should **not** run inside FastAPI request handlers.

### 3. Serving layer

Purpose:

- load model artifacts
- expose inference endpoints
- serve predictions from feature-ready input
- expose health/model metadata

FastAPI should remain here.

Serving should ideally accept:

- feature-ready JSON
- feature-ready CSV
- optionally identifiers for already processed batches

Serving should **not** be responsible for raw FASTA preprocessing.

### 4. Results / metadata layer

Purpose:

- store prediction outputs
- store batch manifests
- store job metadata
- store processing status

Examples:

- `data/results/batch_predictions/...`
- `data/results/manifests/...`
- `data/results/status/...`

## Recommended storage layout

The exact naming can vary, but the intended staged storage is:

```text
data/
  bronze/
    fasta_batches/
  silver/
    amrfinder_outputs/
    normalized_gene_calls/
  gold/
    feature_ready_batches/
  results/
    predictions/
    manifests/
    status/
artifacts/
  models/
  schemas/
  metadata/
```

## What should change

### A. Remove FASTA processing from FastAPI request path

The endpoints `/predict-fasta` and `/predict-fasta-single` may currently work, but architecturally they are doing the wrong job in the wrong layer.

The FASTA-to-feature logic should be moved out of request-time serving and into the processing layer.

### B. Introduce a proper micro-batch processing entrypoint

We need a clear processing entrypoint such as:

- `scripts/process_incoming_batch.py`
- or `scripts/process_fasta_batch.py`

Its job should be:

1. read a batch folder
2. run `AMRFinderPlus`
3. normalize outputs
4. build feature-ready tables
5. save feature-ready data into `gold`
6. write batch metadata

### C. Keep FastAPI focused on serving

FastAPI should mainly do:

- health check
- model listing
- prediction from feature-ready input
- possibly prediction result lookup
- possibly job status lookup

### D. Add batch-level metadata

Each processed batch should have metadata such as:

- `batch_id`
- input path
- output path
- timestamp
- row/sample counts
- scope used
- processing status

This can be file-based JSON for now.
No database is required at this stage.

## Why this is more aligned with Big Data

The goal is to move away from:

```text
FASTA -> API -> AMRFinder -> feature mapping -> prediction
```

and toward:

```text
Incoming batch -> ingestion -> processing layer -> staged storage -> serving layer -> prediction/result access
```

This is more suitable for a Big Data course project because:

- it separates processing from serving
- it supports micro-batch data flow
- it creates staged storage layers
- it looks like a pipeline, not a single monolithic API

## Clarification about CSV and RAM

The current serving layer also reads CSV into memory and builds aligned feature tables in RAM for each request.

This is acceptable for the prototype, but it is not a strong architecture for performance claims.

For now, this is not the primary refactor target.
The primary refactor target is to remove FASTA preprocessing from the serving path.

Later improvements may include:

- reducing `pandas` overhead in serving
- using `numpy` for aligned feature arrays
- precomputing schema index maps

But those are optimization steps, not the first architectural correction.

## Database decision

At this stage, a database is **not required**.

Rationale:

- the AMR prediction workflow is batch-oriented
- file-based staged storage is sufficient for the prototype
- metadata can be stored in JSON manifest files

Database support can be added later if needed for:

- job tracking
- history lookup
- result indexing

If later added, `SQLite` is the preferred lightweight option.

## Short version

The required architecture change is:

- keep FastAPI as the serving layer
- move FASTA preprocessing into a separate processing layer
- organize raw, intermediate, feature-ready, and result data into staged storage
- treat incoming data as micro-batches
- keep metadata per batch in structured files

This is the refactor direction to implement next.
