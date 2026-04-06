# Team 1 - Antibiotic Resistance Prediction

## Project Overview

Team 1 builds a supervised machine learning pipeline that predicts whether a *Salmonella enterica* isolate is resistant or susceptible to a given antibiotic, using resistance genes detected from the isolate's assembled genome as features. The pipeline starts from assembled genome files (FASTA), runs resistance gene detection, constructs a feature matrix, trains a classifier per antibiotic class, and evaluates prediction quality.

The central biological question is: **can the presence of known resistance genes in a genome reliably predict whether that bacterium will survive antibiotic treatment in the lab?** The answer is not always yes - and understanding *why* the prediction sometimes fails is as important as achieving high accuracy.

---

## Data Sources

All data originates from **NCBI Pathogen Detection** (https://www.ncbi.nlm.nih.gov/pathogens/), working exclusively with *Salmonella enterica* isolates. The universal join key across every table and file is `BioSample` - a unique identifier per isolate (format: `SAMN########`).

### FASTA Files - Assembled Genomes

**Sources:**
- **NCBI SRA** (https://www.ncbi.nlm.nih.gov/sra) - search by BioSample ID or SRA accession (`SRR#######`) and download FASTA directly
- **NCBI Datasets Genome** (https://www.ncbi.nlm.nih.gov/datasets/genome/) - alternative source for pre-assembled genomes linked to the same BioSample IDs

**What:** One assembled genome per isolate (~5 MB each). The reconstructed DNA sequence of a single *Salmonella enterica* isolate.  
**Role:** Starting point for resistance gene detection. AMRFinderPlus scans these files to identify which resistance genes are present in each genome.

### Isolates Metadata Table

**Source:** NCBI Pathogen Detection → Isolates Browser → Download as TSV  
**What:** One row per isolate. Provides geographic, temporal, and biological context.

| Column | Description | Importance |
|---|---|---|
| `BioSample` | Universal identifier per isolate | Primary join key linking this table to MicroBIGG-E and the AST table |
| `AMR genotypes` | Quick summary of resistance genes detected per isolate | Useful for a fast per-isolate overview; MicroBIGG-E provides the full per-gene detail needed for the feature matrix |
| `Location` | Geographic origin | Enables geographic resistance trend analysis - e.g., is a drug class becoming more prevalent in a specific region? |
| `Create date` | Collection/submission date | Enables temporal trend analysis - e.g., is resistance to a drug class increasing over time? |
| `Isolation source` | Sample origin (e.g., chicken breast, clinical swab) | Supports subgroup analysis by source type, relevant when comparing food vs. clinical isolates |
| `Isolation type` | Clinical / food / environmental | Coarser version of isolation source; useful for stratifying model performance across surveillance contexts |
| `Serovar` | Subspecies classification (e.g., Typhimurium, Enteritidis) | Relevant for per-serovar model analysis - resistance gene prevalence varies significantly across serovars |

### MicroBIGG-E AMR Gene Table

**Source:** NCBI Pathogens → MicroBIGG-E → search `taxgroup_name:"Salmonella enterica"` → filter Type = AMR → Download TSV (~600 MB)  
**What:** One row per resistance gene detected per isolate. This is the **primary feature source** for the ML model. NCBI generated this table by running AMRFinderPlus on all assembled genomes - Team 1 reproduces a subset of this process on prototype FASTA files as pipeline validation.

| Column | Description | Importance |
|---|---|---|
| `BioSample` | Join key | Links gene-level features to isolate metadata and AST labels |
| `Element symbol` | Gene or mutation name (e.g., `blaTEM-1`, `gyrA_D87Y`) | Becomes the column name in the feature matrix - one column per unique gene across all isolates |
| `Class` | Broad drug resistance category (e.g., `AMINOGLYCOSIDE`, `BETA-LACTAM`, `QUINOLONE`, `TETRACYCLINE`) | Defines the prediction target - each ML model is trained to predict resistance for one drug class |
| `Subclass` | More specific drug category within Class (e.g., `STREPTOMYCIN`, `CEPHALOSPORIN`, `TRIMETHOPRIM`, `KANAMYCIN`) | Allows finer-grained prediction targets; useful when a broad Class contains clinically distinct sub-drugs |
| `Subtype` | Detection category: `AMR` (intact resistance gene), `POINT` (point mutation in a native gene), `POINT_DISRUPT` (disruptive point mutation, rare) | Decides how to split the feature space - `POINT` genes represent a different resistance mechanism from `AMR` genes and may warrant separate treatment |
| `Method` | How the gene was detected. Suffix `P` = protein-based, `X` = nucleotide-based. Prefixes: `EXACT`, `BLAST`, `ALLELE` (whole-gene methods), `POINT` (mutation), `PARTIAL`, `PARTIAL_CONTIG_END` (incomplete detections), `INTERNAL_STOP` (premature stop codon - gene likely non-functional), `HMM` (distant homolog) | Determines which rows to filter out before building the feature matrix - `INTERNAL_STOP` should be excluded as the gene is likely non-functional; `PARTIAL*` rows should be filtered by coverage threshold |
| `% Coverage` | Fraction of the reference gene sequence present in this isolate | Used to set a minimum completeness threshold; low coverage may indicate a degraded or partial gene that provides unreliable resistance |
| `% Identity` | Sequence similarity to the database reference | Used to set a minimum confidence threshold; low identity may indicate a divergent gene variant with uncertain function |
| `Scope` | `core` (well-established) or `plus` (accessory, weaker evidence) | Decides the feature inclusion boundary - starting with `core` only is the conservative choice; adding `plus` is an explicit engineering decision to test |

### AST Table - Antibiotic Susceptibility Tests

**Source:** NCBI Pathogens → AST Browser (https://www.ncbi.nlm.nih.gov/pathogens/ast) → filter *Salmonella enterica* → Download TSV  
**What:** Lab-confirmed resistance test results. One row per (isolate × antibiotic) combination. This is the **ground truth label** for supervised learning.

| Column | Description | Importance |
|---|---|---|
| `BioSample` | Join key | Links lab phenotype labels back to the gene-level features in MicroBIGG-E |
| `Antibiotic` | Drug tested (e.g., `ciprofloxacin`, `ampicillin`) | Determines which subset of rows is used to train each per-antibiotic model |
| `Resistance phenotype` | Lab result: `susceptible` / `resistant` / `intermediate` | The prediction target (Y) - the core label the ML model learns from |
| `MIC (mg/L)` | Minimum Inhibitory Concentration - quantitative resistance measure | Optional regression target for a more nuanced model: instead of predicting resistant/susceptible, predict the exact drug concentration needed to inhibit growth |
| `Testing standard` | Interpretation standard used (CLSI or EUCAST) | Relevant when interpreting borderline phenotype calls - the same MIC value may be classified differently under CLSI vs. EUCAST cutoffs |

**Important limitation:** Not all isolates have AST records. After joining MicroBIGG-E with the AST table on `BioSample`, expect a significant reduction in dataset size - lab phenotyping is not performed for every isolate in a surveillance program.

---

## Pipeline

### Step 1 - Resistance Gene Detection (FASTA → Gene Table)

**Tool:** AMRFinderPlus (https://github.com/ncbi/amr)  
**What it does:** Scans each assembled FASTA genome against NCBI's curated database of known resistance genes and mutations. For each isolate, it outputs a table listing every detected resistance gene with its drug class, detection method, coverage, and identity score.  
**Why run it if MicroBIGG-E already exists:** Running AMRFinderPlus on the prototype FASTA files and comparing the output against MicroBIGG-E for the same isolates is the pipeline validation step. Since NCBI used AMRFinderPlus to generate MicroBIGG-E, outputs should match near-perfectly. Any discrepancy reveals database version differences and is itself a meaningful finding. This step ensures Team 1 understands the origin of their feature data - not just that genes are present, but how they were detected and what that detection means.  
**Database:** The AMRFinderPlus reference database (~500 MB) is downloaded once via `amrfinder --update` and reused for all isolates.  
**Output per isolate:** A TSV file listing detected genes with columns matching MicroBIGG-E structure.

### Step 2 - Feature Matrix Construction (Gene Table → Binary Matrix)

**Tool:** pandas  
**What it does:** Transforms per-isolate gene detection outputs into a structured binary matrix. Each row is one isolate (`BioSample`). Each column is one detected gene or mutation. Cell value is 1 (gene present) or 0 (absent).  
**Source for full training:** The full MicroBIGG-E table is used for ML training, not only the prototype subset. The prototype AMRFinderPlus run validates the pipeline; MicroBIGG-E provides the scale needed for robust model training.

**Feature engineering decisions and biological justification:**

- **Binary encoding (1/0):** A resistance gene either provides resistance function or it does not - the count of gene copies rarely matters in a haploid bacterial genome. Binary representation is biologically appropriate, not a simplification.

- **`Scope` filter:** `core` genes are well-established, peer-reviewed resistance determinants. `plus` genes are accessory with weaker evidence. Whether to include `plus` genes is a deliberate engineering choice: they may add predictive signal for some antibiotics but introduce noise for others. This should be tested and justified per drug class.

- **`Subtype` split - `AMR` vs. `POINT`:** `AMR` rows represent intact resistance genes - dedicated proteins evolved to confer resistance (e.g., a beta-lactamase enzyme that degrades the antibiotic). `POINT` rows represent single amino acid substitutions in otherwise normal genes that happen to block antibiotic binding (e.g., a mutation in DNA gyrase that prevents fluoroquinolone attachment). These are fundamentally different biological mechanisms. The engineered decision is whether to keep them in the same feature space, separate them into feature groups, or train separate models per subtype. Treating them identically ignores a meaningful biological distinction.

- **`Method` filtering:** `INTERNAL_STOP` rows indicate a gene carrying a premature stop codon - the gene sequence is present in the genome but the encoded protein is likely truncated and non-functional. Including these as positive resistance features would be biologically incorrect. `PARTIAL` and `PARTIAL_CONTIG_END` rows indicate incomplete gene detections, often artifacts of assembly contig boundaries. Setting minimum thresholds on `% Coverage` and `% Identity` filters these out. The chosen thresholds (e.g., ≥80% coverage, ≥90% identity) define what "gene present" biologically means - a deliberate engineering decision.

- **Individual gene features vs. class-level features:** Multiple genes can confer resistance to the same drug class (e.g., `blaTEM-1`, `blaCTX-M-15`, and `blaSHV-1` all confer beta-lactam resistance). The feature matrix can use individual gene columns (high dimensionality, mechanism-level interpretability) or collapse to drug-class presence columns (lower dimensionality, loses gene identity). The trade-off is between model interpretability and generalization across serovars.

### Step 3 - Label Construction and Dataset Join

**Tool:** pandas  
**What it does:** Loads the AST table, filters for one target antibiotic at a time, maps `resistant` → 1 and `susceptible` → 0 (`intermediate` is excluded or treated as a third class depending on experimental design), then performs an inner join with the feature matrix on `BioSample`.  
**Result:** A supervised dataset where each row is one isolate with its full gene presence vector (X) and a binary resistance label (Y) for one antibiotic.  
**One model per antibiotic:** Training per antibiotic ensures each model learns the correct gene-to-drug relationship, rather than conflating unrelated resistance mechanisms across drug classes.

### Step 4 - Model Training and Evaluation

**Tool:** XGBoost (primary), scikit-learn (evaluation and comparison)  
**What it does:** Trains a binary classifier on the feature matrix and resistance labels. Evaluates performance using k-fold cross-validation (k=5).

**Why XGBoost:**
- Robust to sparse binary feature matrices - the isolate × gene matrix is highly sparse since most isolates carry only a small fraction of all known resistance genes
- Built-in feature importance scores map directly to which genes drive resistance predictions per drug - a biologically interpretable output
- Handles class imbalance better than logistic regression for the skewed resistant/susceptible ratios common in surveillance data

**Evaluation metrics:**
- AUC-ROC per antibiotic (primary - accounts for class imbalance)
- Precision and recall (false negatives mean prescribing an ineffective antibiotic)
- Feature importance: which genes contribute most to resistance prediction per drug class?

**Biological interpretation of feature importance:** If `gyrA_D87Y` has the highest importance score for ciprofloxacin, that is not a statistical artifact - it directly reflects that this point mutation in the DNA gyrase gene physically blocks ciprofloxacin from binding its target. Feature importance is readable as a mechanism map. This is what separates this work from a generic ML classification task.

### Step 5 - Validation Against MicroBIGG-E Ground Truth

**What:** Compare AMRFinderPlus output on prototype FASTA files against the corresponding MicroBIGG-E rows for the same BioSample IDs.  
**Expected result:** Near-complete agreement on detected gene names and drug class assignments, since NCBI generated MicroBIGG-E using the same tool. Any discrepancy is attributable to database version differences.  
**Why this matters:** It proves the pipeline produces correct output before scaling to full training data. It demonstrates that the feature data is reproducible - not a black-box download but a verifiable detection process.

---

## The Genotype–Phenotype Gap (Why Prediction Is Not Perfect)

The central biological challenge is that genomic presence of a resistance gene does not guarantee phenotypic resistance in the lab. Several mechanisms explain prediction failures:

- **Gene expression variation:** A resistance gene that is present but silenced by a regulatory mutation produces no resistance phenotype. The genome says "resistant"; the lab says "susceptible."
- **Compensatory mutations:** Some resistance mutations reduce bacterial fitness. Clinical isolates may carry counter-mutations that partially restore susceptibility while retaining the resistance gene.
- **Epistasis:** Two genes that individually confer resistance may cancel each other out when present together. Gene presence alone does not capture interaction effects between genes.
- **Plasmid loss during lab culture:** Resistance genes carried on plasmids (mobile genetic elements) can be lost during the subculturing steps before AST testing, producing a "susceptible" phenotype from a genome where resistance genes are still detectable.

These failures are not model failures - they are biological limits on the predictability of phenotype from genotype. Discussing them with reference to specific examples (which gene, which mechanism, which antibiotic class) is what demonstrates biological understanding rather than pure ML competency.

---

## Tools Summary

| Tool | Purpose | Install |
|---|---|---|
| AMRFinderPlus | Resistance gene detection from FASTA | `conda install -c bioconda ncbi-amrfinderplus` |
| pandas | Feature matrix construction, data joining | `pip install pandas` |
| XGBoost | ML classifier | `pip install xgboost` |
| scikit-learn | Evaluation, cross-validation, comparison models | `pip install scikit-learn` |
| matplotlib / seaborn | Feature importance charts, confusion matrices, heatmaps | `pip install matplotlib seaborn` |

