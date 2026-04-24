Run the FASTA architecture test with:

```bash
bash scripts/test_commands/run_fasta_architecture_test.sh
```

The script uses this interpreter by default:

```bash
/home/nghia/Desktop/BigData/.venv/bin/python
```

Override it if needed:

```bash
VENV_PYTHON=/path/to/venv/bin/python bash scripts/test_commands/run_fasta_architecture_test.sh
```

Run the full end-to-end FASTA verification flow with:

```bash
bash scripts/test_commands/run_fasta_e2e_verification.sh
```

This flow will:

```text
single FASTA -> /ingest-fasta-single -> process_fasta_batch.py -> /predict-csv
```

Useful overrides:

```bash
FASTA_PATH=/path/to/sample.fasta ANTIBIOTIC=ampicillin bash scripts/test_commands/run_fasta_e2e_verification.sh
BASE_URL=http://127.0.0.1:8000 bash scripts/test_commands/run_fasta_e2e_verification.sh
```
