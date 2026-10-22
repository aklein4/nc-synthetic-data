# ApproximationBench: in-context function approximation benchmarks

Four benchmark ideas measuring few-to-many-shot in-context learning in small
(~1B) models. Unlike `systems_bench.py`, test inputs never match training
inputs, so lookup fails; the model must generalize from the similarity/smooth
structure of a hidden mapping. No arithmetic anywhere — all inputs and outputs
are qualitative labels, with ordered *word* scales (trace / light / moderate /
heavy) where order matters.

## Shared rules

- **No prior knowledge**: structure is sampled randomly, independent of the
  language dressing; every direction of effect is coin-flipped per world, so
  zero-shot performance is at chance.
- **Test novelty**: no test input configuration appears in training.
- **Inferability**: instead of logical entailment, require *recoverability by a
  simple learner* — accept a test item only if k-nearest-neighbor (k=3, ordinal
  or Hamming distance over the hidden tuples) predicts the gold label from the
  training examples. This certifies that implicit similarity-based
  generalization suffices; no deduction or constraint solving needed.
- **Scoring**: accuracy against a closed label set (multiple choice or scored
  generation); ordinal benchmarks also report mean ordinal error.
- Reuse the systems_bench pipeline: seeded structural sampling, LLM calls only
  for dressing, verification, caching, private structure metadata.

## 1. Qualitative response surfaces

2–4 ordinal inputs (4–5 ordered word levels each) map to an ordinal outcome via
a hidden monotone surface (generator-side: weighted sum of level indices,
directions coin-flipped, quantile-bucketed into outcome levels; optionally one
interaction). Training examples tile the grid sparsely; test items are unseen
grid cells. The model succeeds by implicit interpolation: nearby inputs give
nearby outputs. Difficulty knobs: number of inputs, interaction, and distance
from the nearest training cell (accuracy vs. distance is the headline plot —
graceful decay means function approximation, a cliff means fuzzy retrieval).

## 2. Prototype categories

Entities have 4–6 unordered qualitative features; K = 3–4 hidden categories are
defined by prototypes (Hamming distance ≥ 3 apart); an entity is a prototype
with 0–2 features perturbed, labeled by nearest prototype. Train on labeled
entity descriptions; test on novel feature bundles. This mirrors the human
implicit category-learning literature, which supplies a validated difficulty
ladder (single-feature rule → prototype similarity → conjunctive/XOR-like).
Include never-seen prototypes as test items: genuine category learners score
*highest* on them (prototype enhancement), which retrieval cannot produce.
Chance = 1/K.

## 3. Latent dose-response shapes

One ordinal dose input (6–8 levels) plus a context input that selects a hidden
qualitative *shape* from a small family: rising, plateau, peak, threshold
(orientations coin-flipped). Training observes each shape at roughly half the
dose levels (always bracketing any knee/peak/jump); test asks about unsampled
levels. Rewards recognizing the curve as a gestalt. Peak and threshold shapes
are built-in prior killers — "more is more" intuition scores below chance.
Interpolation items need only the k-NN filter; extrapolation items are accepted
only when every shape in the family consistent with the samples agrees at the
queried level.

## 4. Modal-outcome (frequency) learning

Take benchmark 1's smooth surface but make observations noisy: each training
observation reports the cell's modal outcome with probability ~0.7, otherwise a
random other outcome. Test asks for the *usual* outcome of an unseen cell
("batches like this most often came out — ?"), scored against the latent mode.
Copying the single most similar example is now a losing strategy; pooling the
neighborhood wins — realize the noise so that the 1-NN baseline is wrong on
≥ 40% of test items while the k=5 majority is always right, and report both
baselines next to model accuracy. Frequency estimation is native next-token
territory, making this the most 1B-friendly of the four, with the slow
many-shot climb characteristic of statistical learning.

## Suggested build order

1 (minimal version of the paradigm) → 2 (adds Hamming/tier machinery) →
4 (adds noise on top of 1) → 3 (adds the shape family and consistency check).
