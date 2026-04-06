# Team 1 - Feature Engineering: Biological Complexity

This document explains why feature engineering for AMR prediction is biologically non-trivial. Each section covers one feature or concept, what the biological challenge is, and why it matters for model quality.

---

## Labels: `Resistance phenotype` and `MIC`

### What MIC is

MIC (Minimum Inhibitory Concentration) is the lowest drug concentration that stops a bacterium from visibly growing in a lab test. The lab exposes bacteria to the drug at doubling concentrations (0.25, 0.5, 1, 2, 4, 8... mg/L) and records the lowest concentration where no growth occurs.
- Low MIC = the drug works at a small dose = bacteria is easy to kill
- High MIC = the drug needs a high concentration to work = bacteria is harder to kill

### What `Resistance phenotype` is

`Resistance phenotype` is not an independent measurement. It is the MIC converted into a category by applying a breakpoint rule:
- MIC > breakpoint → "resistant"
- MIC ≤ breakpoint → "susceptible"
- MIC ≈ breakpoint → "intermediate"

The two columns live in the same AST table row because NCBI stores both the raw measurement (MIC) and the derived label (phenotype) together. They are not two separate pieces of evidence - one is derived from the other.

### What a breakpoint is

A breakpoint answers one practical clinical question: can we safely give the patient enough of this drug to exceed the bacteria's MIC?

Every drug has a maximum dose a human can tolerate before side effects become dangerous. From that dose, pharmacologists calculate the realistic drug concentration achievable at the infection site in a patient's body. That concentration becomes the breakpoint.
- MIC below breakpoint → the drug can reach levels that kill the bacteria at a safe dose → susceptible
- MIC above breakpoint → no safe dose can kill the bacteria → resistant

The breakpoint is therefore not a biological property of the bacteria. It is a statement about what is achievable in a human patient.

### Why CLSI and EUCAST differ

Two major standards organizations (CLSI in the US, EUCAST in Europe) set different breakpoints for the same drug because they model slightly different patient populations, dosing regimens, and definitions of acceptable clinical outcome. The same isolate with the same MIC can receive a different label depending on which standard the lab used. NCBI's AST data mixes both standards with no consistent flag. This means the training labels are not internally consistent.

### Why MIC is more informative than the binary label

Consider two isolates, both labeled "susceptible" against a breakpoint of 2 mg/L:
- Isolate A: MIC = 0.5 mg/L - the drug is effective at one-quarter of the achievable dose. Large safety margin.
- Isolate B: MIC = 1.9 mg/L - the drug is barely effective. Any small mutation during treatment or variation in drug absorption could push this isolate over the breakpoint.

Both are label = 0. The model cannot distinguish them. In clinical reality, a doctor treating Isolate B should be more cautious. This is the core reason MIC carries more information than the binary label.

### MIC structure: doubling dilutions

MIC values are reported only at doubling steps: 0.125, 0.25, 0.5, 1, 2, 4, 8, 16, 32... This is not a continuous linear scale. If MIC is used as a regression target, this ordinal structure must be handled explicitly - the gap between 1 and 2 is not biologically equivalent to the gap between 32 and 33.

---

## `Class` - prediction target granularity

The `Class` column groups drugs by family (e.g., BETA-LACTAM, AMINOGLYCOSIDE, QUINOLONE). Predicting resistance at the class level hides an important asymmetry: **the clinical consequence of a wrong prediction is not equal across drug classes.**
- **Carbapenem resistance** is rare (<1% of Salmonella isolates) but catastrophic. Carbapenems are last-resort antibiotics - when a bacterium is resistant to them, very few treatment options remain. A false negative (predicting susceptible when actually resistant) means the patient receives a treatment that will not work, with potentially fatal consequences.
- **Ampicillin resistance** is extremely common (~70–80% of Salmonella isolates). Predicting it incorrectly is far less dangerous because many alternative drugs remain available.

Standard metrics like accuracy and AUC-ROC treat both errors symmetrically. Biologically they are not - carbapenem predictions warrant asymmetric loss weighting in the model.

Additionally, grouping at the class level merges drugs with different clinical roles. QUINOLONE includes both nalidixic acid (older, weaker, rarely used clinically now) and ciprofloxacin (frontline treatment for Salmonella infections). Resistance to nalidixic acid alone has a very different clinical implication from resistance to all fluoroquinolones. A class-level model cannot make this distinction.

---

## `Element symbol` - individual gene features

Each gene detected by AMRFinderPlus becomes a binary feature column (1 = present, 0 = absent). Three biological challenges are hidden inside this simple encoding.

### 1. Genes travel in groups (co-occurrence on mobile elements)

Bacteria exchange DNA through mobile genetic elements - pieces of DNA that copy themselves between bacteria. These elements often carry multiple resistance genes simultaneously. For example, `aadA1` and
`sul1` almost always appear together because they are physically located on the same mobile element.

The model will learn that `sul1` correlates with aminoglycoside resistance. But `sul1` does not cause aminoglycoside resistance - it provides sulfonamide resistance. It just happens to always travel next to `aadA1`, which does. The model learned a false association caused by the physical geography of bacterial DNA, not by biological mechanism.

### 2. Same gene family, different resistance profile

`blaTEM-1` and `blaTEM-52` both belong to the TEM beta-lactamase family. `blaTEM-1` breaks down penicillins only. `blaTEM-52` is an extended-spectrum variant (ESBL) that also breaks down cephalosporins - a stronger drug class. Using the full `Element symbol` name keeps them as separate features correctly. Collapsing to gene family level loses the distinction and the model cannot tell a less dangerous variant from a more dangerous one.

### 3. Gene copy number is invisible

Binary encoding records only presence or absence. If a resistance gene is present in five copies rather than one, the bacterium produces more of the resistance protein and achieves a higher MIC. Two isolates both get feature = 1 but one is substantially more resistant than the other. The binary feature cannot capture this.

---

## `Subtype` - AMR vs. POINT

AMRFinderPlus assigns each detected element a subtype:
- **AMR**: The bacterium acquired a foreign gene it did not originally have - typically via mobile genetic elements from another bacterium. It now produces a new protein that destroys or neutralizes the antibiotic.
- **POINT**: The bacterium's own existing gene mutated - a single DNA letter change altered one amino acid in a protein, and that protein no longer binds the antibiotic effectively.

### Why POINT mutations are harder to model

POINT mutations are allele-specific. `gyrA_D87Y` and `gyrA_D87N` are two different mutations at the same position in the same gene - one substitutes tyrosine, the other asparagine. Both reduce fluoroquinolone
binding but to different degrees. The model needs enough training examples of each allele to learn them separately. Rarer alleles are underrepresented in training data and are likely mispredicted.

### The mixed-population problem

When a patient's sample is sequenced, the sequencer processes millions of bacterial cells together. If 90% of cells lack a resistance mutation and 10% carry it, the assembled genome represents the majority - the
mutation does not appear in AMRFinderPlus output. The label says susceptible. The model predicts susceptible. But when the antibiotic is administered, the 10% resistant cells survive, multiply, and the treatment fails. This failure mode is invisible to any genotype-based model.

---

## `% Coverage` and `% Identity`

Coverage measures how much of the known reference gene was detected in the isolate. Identity measures how similar the detected sequence is to the reference.

### Threshold interpretation is gene-specific

- Some resistance enzymes (e.g., beta-lactamases) require their full active site to be intact to function. A 60% coverage hit that truncates the catalytic region is non-functional - the gene is present but the bacterium is not actually resistant.
- Other resistance proteins (e.g., some efflux pumps) can tolerate partial truncation and still function.

A single universal coverage cutoff (e.g., ≥80%) is biologically correct for some genes and incorrect for others. The right threshold is gene-specific, but applying gene-specific rules requires curating the biology of each gene individually - a practical reason the universal approximation is used despite its known limitations.

Identity near threshold is similarly ambiguous: a gene at 85% identity might be a novel functional variant of the reference, or a diverged homolog that has lost resistance function. Without experimental validation, sequence similarity alone cannot determine which.

---

## `Scope` - core vs. plus

AMRFinderPlus marks each detected element with a scope:
- **core**: well-established resistance genes with strong evidence from multiple independent studies.
- **plus**: weaker evidence - often stress response or metal tolerance genes.

### The confounding environment problem

`plus` genes appear more frequently in resistant isolates not because they cause resistance, but because resistant bacteria often inhabit environments - large food production facilities - where disinfectants and heavy metals are used regularly. These environments co-select for both resistance genes and stress/metal tolerance genes simultaneously.

If `plus` features are included, the model may learn "stress gene X predicts resistance to drug Y" - statistically true in training data from these environments, but not causally true. The model learned an environmental correlation. When applied to isolates from environments without this co-selection pressure, the prediction fails.

---

## Class imbalance across drug classes

Resistance prevalence varies enormously across antibiotics in the NCBI dataset:
- Ampicillin resistance: ~70–80% of Salmonella isolates
- Carbapenem resistance: <1% of isolates

For carbapenem, 99% of training labels are "susceptible." A model that predicts "susceptible" for every single isolate achieves 99% accuracy while having learned nothing useful. Standard accuracy metrics will report this as a high-performing model.

AUC-ROC handles this better - it measures whether the model can rank resistant isolates higher than susceptible ones, regardless of the final label. But even AUC-ROC does not solve the root problem: for extremely rare resistance classes, the model simply has very few positive training examples to learn the resistance pattern from in the first place.