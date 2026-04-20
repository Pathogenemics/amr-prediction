# Workflow And Results Notes

## 1. Project Goal

The goal of the project was to build antibiotic-specific AMR prediction datasets and compare several genotype-to-phenotype connection strategies in a way that is both biologically interpretable and empirically testable.

The work ended with three connection tiers:

- `strict`
- `broad`
- `all`

Each tier was turned into prepared model-input tables, then one model was trained per antibiotic within each tier and the results were compared.


## 2. Starting Data

The project used three main inputs:

- phenotype data from NCBI
- genotype data from NCBI
- antibiotic grouping information from `Antibiotic-Group.md`

The phenotype data contained:

- `BioSample`
- `Antibiotic`
- `Resistance phenotype`
- MIC-related fields

The genotype data contained:

- `BioSample`
- `Element symbol`
- `Subtype`
- `Class`
- `Subclass`
- `Method`
- `% Coverage of reference`
- `% Identity to reference`


## 3. Cohort Alignment

Before meaningful exploration, both phenotype and genotype were restricted to the shared isolate cohort.

That means:

- keep only isolates present in both tables

This was necessary so that all downstream summaries and model inputs would reflect the actual usable dataset rather than raw downloaded counts that do not overlap.


## 4. Phenotype Processing

Phenotype cleaning was done first because the final modeling problem starts from phenotype:

- keep rows with required fields present
- keep only `susceptible` and `resistant`
- remove `(BioSample, Antibiotic)` pairs that contain both labels
- if duplicate rows remain for the same `(BioSample, Antibiotic)`, keep the row with the lowest MIC
  - with measurement-sign ordering handled explicitly

After cleaning, antibiotic-level phenotype summaries were created:

- total records per antibiotic
- `susceptible` count
- `resistant` count
- resistance fraction

Antibiotics were then filtered using:

- `MIN_ANTIBIOTIC_ROWS`
- `MIN_CLASS_COUNT`

The final project default became:

- `MIN_ANTIBIOTIC_ROWS = 500`
- `MIN_CLASS_COUNT = 100`

This was chosen because `100` per class is a much more defensible modeling threshold than a very permissive value like `20`.


## 5. Phenotype Grouping

Antibiotics were grouped using the hierarchy from `Antibiotic-Group.md`.

This grouping was used for:

- organizing phenotype summaries
- understanding the antibiotic family structure
- later defining genotype-to-phenotype connection rules

This also highlighted an important biological issue:

- some antibiotics belong to families where genotype relevance is not limited to the exact drug token
- especially beta-lactams and some combination drugs


## 6. Genotype Processing

Genotype processing was done in several stages.

### 6.1 Exact row deduplication

First, exact duplicate genotype rows were removed.

### 6.2 Gene-level collapse

Then genotype was collapsed to one row per:

- `(BioSample, Element symbol)`

This was necessary because the same gene element in the same isolate can appear multiple times with different detection methods.

The selected row was chosen using method priority and tie-breaking rules.

### 6.3 Method priority

The final method-family ranking was:

- `EXACT`
- `ALLELE`
- `BLAST`
- `POINT`
- `PARTIAL`
- `PARTIAL_CONTIG_END`
- `HMM`

Tie-breaking also used:

- `Subtype`
- `P` versus `X`
- `% Coverage of reference`
- `% Identity to reference`

This made the collapsed genotype table biologically cleaner and prevented one gene from being counted multiple times simply because AMRFinder reported it under multiple methods.


## 7. Genotype Exploration Before Connection

Several exploratory checks were done before building final model inputs:

- method count summaries
- method co-occurrence matrices for the same gene in the same isolate
- class and subclass count tables
- audit tables to check whether normalization accidentally dropped subclass tokens

These steps were important because they revealed:

- which methods co-occur
- which class/subclass patterns are simple
- which patterns are ambiguous
- whether any subclass tokens disappeared during normalization

At the end of this phase, subclass token auditing confirmed that nothing was disappearing silently after normalization.


## 8. Class And Subclass Normalization

The raw genotype `Class` and `Subclass` values were not ready for direct use because they contained:

- multiple subclasses in one field
- multiple classes in one field
- `MULTIDRUG`
- ambiguous combinations

Normalization therefore included:

- lower-casing labels
- splitting combined subclass values
- splitting combined class values
- using observed single-class rows to build a subclass-to-class registry
- using `Antibiotic-Group.md` as a supporting reference
- assigning unresolved values to `unknown` only when necessary

This normalized table became the basis for phenotype-genotype connection.

Two concrete examples help illustrate what this means in practice.

### Example A: Combined subclasses under one class

Suppose a normalized raw genotype row looks like this:

- `Class = PHENICOL`
- `Subclass = CHLORAMPHENICOL/FLORFENICOL`

This is relatively easy to normalize because there is only one class.

After normalization, this becomes two rows:

- `class = phenicol`, `subclass = chloramphenicol`
- `class = phenicol`, `subclass = florfenicol`

The key point is that the single gene element is still the same gene, but it is now attached to two subclass labels that can be matched separately later.

### Example B: Combined classes and combined subclasses

Suppose a raw genotype row looks like this:

- `Class = AMINOGLYCOSIDE/QUINOLONE`
- `Subclass = AMIKACIN/KANAMYCIN/QUINOLONE/TOBRAMYCIN`

This is harder because both class and subclass are multi-valued.

The normalization logic first splits the classes, then uses the observed subclass-to-class registry to decide which subclass belongs to which class.

That means the row is interpreted as something like:

- `class = aminoglycoside`, `subclass = amikacin`
- `class = aminoglycoside`, `subclass = kanamycin`
- `class = aminoglycoside`, `subclass = tobramycin`
- `class = quinolone`, `subclass = quinolone`

The important idea is that the split is not done blindly. It uses the registry built from simpler rows plus the antibiotic grouping reference.


## 9. Manual Mapping For Known Edge Cases

Even after registry-based normalization, a few biologically meaningful cases still needed manual help because they were not resolved well by the observed data alone.

Manual subclass-to-class mapping was added for:

- `rifampin -> rifamycin`
- `clindamycin -> lincosamide`
- `trimethoprim-sulfamethoxazole -> trimethoprim + sulfonamide`

This was added before fallback to `unknown`.

That step prevented rare but important subclasses from being left unresolved simply because they did not have enough support in the observed single-class genotype rows.

One simple example is:

- raw subclass token: `rifampin`

Without manual support, this could remain unmatched and fall into `unknown`.

With manual mapping, it becomes:

- `class = rifamycin`
- `subclass = rifampin`

Another example is:

- raw subclass token: `trimethoprim-sulfamethoxazole`

Instead of treating it as an opaque single label, it is manually recognized as belonging to:

- `trimethoprim`
- `sulfonamide`


## 10. Building Antibiotic-Specific Model Inputs

The final input-building process started from phenotype, not genotype.

For each eligible antibiotic:

1. build the phenotype table for that antibiotic
2. keep one row per `BioSample`
3. encode the target
4. connect the relevant genotype rows
5. pivot genotype into a model-ready feature table

The final label encoding became:

- `resistant = 1`
- `susceptible = 0`

This was chosen so that:

- recall
- precision
- average precision

would all naturally refer to resistance, which is the clinically important class.


## 11. Feature Engineering

For each antibiotic-specific table, genotype rows were aggregated by:

- `BioSample`
- `Element symbol`

The resulting features included:

- gene presence
- `{element}_coverage`
- `{element}_identity`
- lineage-match feature

This means the final model inputs were not just raw gene presence matrices. They also retained quantitative genotype evidence through coverage and identity, and they kept connection-scope information through lineage matching.


## 12. Three Connection Tiers

The main modeling experiment compared three genotype-connection tiers.

### 12.1 Strict

`strict` only keeps genotype rows whose normalized `subclass` matches the antibiotic’s lineage tokens.

This is the narrowest and most biologically specific tier.

Example:

- phenotype antibiotic: `ceftriaxone`
- strict lineage tokens: `ceftriaxone`, `cephalosporins`, `beta-lactam`

Under `strict`, a genotype row with:

- `class = beta-lactam`
- `subclass = cephalosporin`

can match if its normalized subclass falls within the lineage token set, but a sibling branch that is only class-related and not lineage-matched is excluded.

### 12.2 Broad

`broad` keeps genotype rows whose normalized `class` matches the antibiotic’s allowed broad class set.

This is less restrictive and captures broader within-class resistance mechanisms.

Example:

- phenotype antibiotic: `amoxicillin-clavulanic acid`
- broad scope class: `beta-lactam`

Under `broad`, genotype rows from multiple beta-lactam subclasses can be used, such as:

- `class = beta-lactam`, `subclass = penicillin`
- `class = beta-lactam`, `subclass = cephalosporin`

This is exactly the kind of expansion that helped the beta-lactam antibiotics compared with the strict tier.

### 12.3 All

`all` keeps all genotype rows for isolates appearing in that antibiotic’s phenotype table.

This is the widest connection tier and guarantees that every antibiotic-specific table can use the full genotype signal available for its isolate set.

Example:

- phenotype antibiotic: `ampicillin`

Under `all`, every normalized genotype row for the isolates in the ampicillin phenotype table is available, even if the row belongs to an unrelated class such as:

- `aminoglycoside`
- `quinolone`
- `tetracycline`

That is why `all` removes the zero-feature problem entirely, but it is also the least biologically constrained tier.


## 13. Special Handling For Trimethoprim-Sulfamethoxazole

`trimethoprim-sulfamethoxazole` was the most difficult special case.

It required two separate adjustments:

### 13.1 Broad-scope override

For broad matching, its phenotype-side scope classes were manually set to:

- `trimethoprim`
- `sulfonamide`

### 13.2 Strict-lineage override

For strict matching, the lineage tokens were manually expanded to:

- `trimethoprim-sulfamethoxazole`
- `trimethoprim`
- `sulfamethoxazole`
- `sulfonamide`

Without these overrides, the combination drug either remained empty or was treated too literally, which would have made both strict and broad artificially weak.

One way to visualize the difference is:

- before patching strict:
  - phenotype drug = `trimethoprim-sulfamethoxazole`
  - strict tried to match only the literal combination token
  - result: no genotype features
- after patching strict:
  - the same drug is allowed to match component-level subclass tokens
  - `trimethoprim`
  - `sulfamethoxazole`
  - `sulfonamide`

So the strict tier for this drug became “component-aware strict” rather than “literal-string strict”.


## 14. Prepared Model Inputs

The final prepared model-input tables were written into:

- `data/model_inputs/strict/`
- `data/model_inputs/broad/`
- `data/model_inputs/all/`

Each file contains one antibiotic-specific dataset.

This separation made the training step simple and reproducible:

- no more raw-data transformation inside the CLI
- only prepared-input training remained


## 15. Model Training

One binary model was trained per antibiotic per connection tier.

The training pipeline now operates only on prepared model-input tables.

Outputs are written directly into:

- `outputs/strict/`
- `outputs/broad/`
- `outputs/all/`

Each scope output includes:

- `metrics.csv`
- `dataset_summary.json`
- `run_config.json`


## 16. Metric Interpretation

The final metric priority for interpretation became:

1. `recall`
2. `precision`
3. `roc_auc`

This choice was made because the project is closer to a resistance-detection problem than a generic balanced classification problem.

The reasoning was:

- `recall` is the most clinically important because missing resistant isolates is the risky error
- `precision` matters because a model can inflate recall by predicting resistance too often
- `roc_auc` is useful as a supporting ranking metric

`accuracy` was kept only as secondary context.

It is not a good primary metric here because class imbalance can make it look strong even when resistance detection is poor.


## 17. Final Results

The comparison across the three connection tiers was coherent and biologically explainable.

### 17.1 Average scope performance

Across trained antibiotics:

| Scope | Recall | Precision | ROC-AUC | Accuracy | Avg feature count | Avg zero-feature rows |
|---|---:|---:|---:|---:|---:|---:|
| `all` | `0.9743` | `0.9662` | `0.9884` | `0.9875` | `503.1` | `0.0` |
| `broad` | `0.9746` | `0.9719` | `0.9841` | `0.9880` | `77.1` | `3790.5` |
| `strict` | `0.8653` | `0.7436` | `0.8417` | `0.8223` | `43.4` | `4461.1` |

### 17.2 What this means

- `all` is the strongest global default
  - best overall ROC-AUC
  - zero all-zero rows
  - very strong recall
- `broad` is the best biologically constrained alternative
  - often very competitive
  - clearly better than strict on antibiotics where sibling or family-level genotype relevance matters
- `strict` is too brittle to serve as the final default
  - it still works very well for some antibiotics
  - but it fails badly for others because it leaves too many isolates with all-zero genotype vectors

### 17.3 Best scope by antibiotic

Using the final ranking rule:

1. recall
2. precision
3. ROC-AUC

the best scopes were:

| Antibiotic | Best scope |
|---|---|
| amoxicillin-clavulanic acid | `all` |
| ampicillin | `broad` |
| cefoxitin | `all` |
| ceftiofur | `broad` |
| ceftriaxone | `broad` |
| chloramphenicol | `strict` |
| ciprofloxacin | `strict` |
| gentamicin | `broad` |
| kanamycin | `broad` |
| nalidixic acid | `all` |
| streptomycin | `broad` |
| sulfisoxazole | `strict` |
| tetracycline | `all` |
| trimethoprim-sulfamethoxazole | `all` |


## 18. Final Conclusion

The final results are defensible because they come from explicit and traceable feature engineering:

- phenotype cleaning was explicit
- genotype deduplication was explicit
- normalization was explicit
- subclass auditing confirmed that tokens were not silently lost
- special-case mappings were documented
- connection tiers were intentionally designed and compared

The project therefore ends in a good state:

- the code path is stable enough
- the results are explainable
- the tradeoffs between `strict`, `broad`, and `all` are visible rather than hidden

If one tier must be chosen globally:

- use `all` for strongest predictive performance

If a more biologically constrained default is preferred:

- use `broad`

And keep `strict` as the narrow reference baseline rather than the final default.
