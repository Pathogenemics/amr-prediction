# AMR CLI

This project uses the CLI only for model training from prepared input tables. Data exploration and input construction live in notebooks.

Use the module directly:

```powershell
$env:PYTHONPATH='d:\Projects\amr-prediction\src'
& 'd:\Projects\amr-prediction\.venv\Scripts\python.exe' -m cli --help
```

If the package is installed into the virtual environment, the script entrypoint also works:

```powershell
amr --help
```

## Train

Train one prepared-input scope:

```powershell
$env:PYTHONPATH='d:\Projects\amr-prediction\src'
& 'd:\Projects\amr-prediction\.venv\Scripts\python.exe' -m cli --prepared-input-dir data/model_inputs/broad --output-dir outputs
```

Train all scopes into `outputs/strict`, `outputs/broad`, and `outputs/all`:

```powershell
$env:PYTHONPATH='d:\Projects\amr-prediction\src'
& 'd:\Projects\amr-prediction\.venv\Scripts\python.exe' -m cli --prepared-input-root data/model_inputs --output-dir outputs
```

Train only selected antibiotics:

```powershell
$env:PYTHONPATH='d:\Projects\amr-prediction\src'
& 'd:\Projects\amr-prediction\.venv\Scripts\python.exe' -m cli --prepared-input-dir data/model_inputs/strict --antibiotic ciprofloxacin --antibiotic ceftriaxone --output-dir outputs/strict
```

Useful training flags:

- `--prepared-input-dir`: one scope folder such as `data/model_inputs/broad`
- `--prepared-input-root`: parent folder containing multiple scope folders such as `strict`, `broad`, `all`
- `--antibiotic`: restrict training to selected antibiotics
- `--cv-folds`: number of stratified CV folds
- `--no-progress`: disable antibiotic progress bars
- `--progress-folds`: show fold-level progress within each antibiotic

Training outputs:

- `metrics.csv`: per-antibiotic model metrics
- `dataset_summary.json`: prepared-input summary for the run
- `run_config.json`: model run configuration

When `--prepared-input-root data/model_inputs --output-dir outputs` is used, the CLI updates:

- `outputs/strict/`
- `outputs/broad/`
- `outputs/all/`

## Explore

Use the notebook instead of terminal output:

- `notebook/data_exploration.ipynb`

The notebook builds the cleaned phenotype/genotype views and writes prepared model inputs into `data/model_inputs/strict`, `data/model_inputs/broad`, and `data/model_inputs/all`.

## Recommendation

Use the notebook to prepare inputs.
Use the CLI to train each scope into `outputs/`.
Use the output notebook to compare scopes by reading those per-scope folders.
