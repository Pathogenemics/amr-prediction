**`Type = AMR`** - The MicroBIGG-E table contains three gene types: `AMR`, `Stress`, and `Virulence`
- Only `AMR` genes are retained because the prediction task is antibiotic resistance phenotype
- `Stress` genes confer tolerance to disinfectants and environmental conditions, not antibiotics
- `Virulence` genes affect how severely the bacteria causes disease, not whether a drug will stop it. Including either would add features that predict the wrong biological outcome.

**`Scope = core`** - Within AMR genes, NCBI distinguishes `core` (genes with strong, direct evidence for predicting resistance phenotype) from `plus` (genes deemed unlikely to be informative about phenotype - including ubiquitous housekeeping genes, general efflux pumps present in nearly all isolates, and AMR genes whose presence does not reliably distinguish resistant from susceptible isolates). Only `core` is retained to ensure every feature in the matrix carries genuine predictive signal.

**`Method ≠ INTERNAL_STOP`** - The `Method` column describes how AMRFinderPlus detected a gene. Of the 14 detection methods present in the data, 13 represent genuine functional detections and are retained. Only `INTERNAL_STOP` is excluded.
- `EXACTP` / `EXACTX` - perfect 100% match to a known reference at protein or nucleotide level; highest confidence detection, always retained
- `ALLELEP` / `ALLELEX` - exact match to a specific known allele; used primarily for POINT mutations, always retained
- `BLASTP` / `BLASTX` - similarity-based match at protein or nucleotide level; confidence controlled downstream by `% Coverage` and `% Identity` thresholds, retained
- `POINTP` / `POINTX` - detected a specific point mutation against a known resistance allele, retained
- `PARTIALP` / `PARTIALX` - gene detected but incomplete; coverage controlled by the `% Coverage` threshold rather than a hard method filter, retained
- `PARTIAL_CONTIG_ENDP` / `PARTIAL_CONTIG_ENDX` - gene truncated at a contig boundary due to assembly artifact, not a biological truncation; the gene is likely complete in the real genome, retained
- `HMM` - detected via a statistical sequence profile; lower specificity than sequence matching but still represents a valid homolog detection, retained
- `INTERNAL_STOP` - the gene sequence contains a premature stop codon, causing the ribosome to terminate translation early and produce a truncated protein. A truncated resistance protein loses its functional structure and almost certainly cannot perform the enzymatic or structural role that confers resistance. Despite the gene being nominally detected, the isolate does not carry a functional copy. Encoding these rows as present (1) would tell the model a working resistance gene exists when it does not, introducing systematic label noise.

___

**`Testing standard = CLSI or NARMS`** - NCBI's AST data contains phenotype labels produced under three different standards: `CLSI`, `NARMS`, and `EUCAST`
- `CLSI` and `NARMS` share the same breakpoint framework and are both US-based foodborne surveillance standards, making them directly comparable.
- `EUCAST` uses independently derived breakpoints that differ numerically for many drugs - the same MIC value can produce a different resistant/susceptible label under `EUCAST` than under `CLSI`. Mixing standards would make training labels internally inconsistent
- Rows with no recorded standard are also dropped as their labels cannot be interpreted reliably

**`Resistance phenotype = SUSCEPTIBLE or RESISTANT`** - The AST table contains five phenotype values
- Only `SUSCEPTIBLE` (label = 0) and `RESISTANT` (label = 1) represent unambiguous breakpoint-based classifications and are retained for binary model training
- `INTERMEDIATE` is excluded because the MIC falls within the grey zone at the breakpoint boundary - forcing an arbitrary binary label at this position would inject noise precisely where the model's decision boundary sits
- `NOT DEFINED` is excluded because no clinical breakpoint exists for that drug-organism pair, meaning the label was never validly assigned
- `NONSUSCEPTIBLE` is excluded because it indicates only the absence of confirmed susceptibility without confirming resistance, making it an unreliable positive label