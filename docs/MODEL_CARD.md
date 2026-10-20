# Model card — fusion-gru-v1

## Intended use

Research and learning about candidate-service ranking, model evaluation, and evidence-backed AI applications. Not an autonomous incident responder and not a validated production root-cause detector.

## Model

The shipped model has 6,349 learned parameters. For each candidate service it combines a 24-step, six-metric sequence processed by a GRU; a 64-dimensional stateless hashed bag-of-word/bigram log vector processed by a learned linear layer; and 20 numerical/statistical features processed by a second learned layer. A shared scoring head produces a candidate logit. Softmax is applied across services in the incident.

The log features are **not pretrained semantic embeddings**. A learned projection of hashed textual features is used. No foundation model was trained or fine-tuned. Service names are removed from text features; names, incident IDs, titles, labels, split assignments and experiment IDs are not neural inputs. The shared scoring network is equivariant to candidate ordering.

## Training

Cross-entropy against the labeled initiating service, AdamW, gradient clipping, dropout, deterministic CPU algorithms, seed 42. Training candidates remain grouped by incident. Training and validation contain whole experiment groups, never individual overlapping rows from the same experiment. Early stopping uses validation loss only. The exported model is the full-feature architecture specified in the experiment, not whichever variant looks best on test.

Only the full neural model is shipped for serving. Baselines and ablations are trained and evaluated by `train.py`; they are not serialized as unsafe pickles. The NumPy state dictionary is loaded with `allow_pickle=False`, checked against its SHA-256 manifest, and loaded into an explicit architecture. A checksum is an integrity check, not a signature or a defense against an attacker who can modify both files.

## Data and split

720 synthetic observations from 360 experiment groups. 374 train / 98 validation / 104 test / 144 challenge observations. The challenge partition reserves six service/fault combinations. It does **not** reserve entirely novel fault mechanisms. The generator contains noise, propagated symptoms, concurrent distracting symptoms and partial visibility, but its assumptions still make this much easier than real operations.

Two observations in an experiment share the cause/service family and stay in the same partition. The confidence intervals bootstrap whole experiment groups. They measure sampling variability conditional on this generator and fitted model, not training-seed variability or deployment uncertainty.

## Evaluation interpretation

The complete results are in `reports/evaluation.json`. The no-graph ablation slightly outperforms the full model on test and challenge. This is a useful negative result about the synthetic dependency features; it is not evidence that dependency information never helps in real systems.

Validation selected a small temperature on a grid (the value is stored in `artifacts/model.json`). A small validation set with few errors can yield overconfident probabilities. Temperature fitting and threshold selection do not make a model trustworthy under distribution shift. Top-3 is also easier with only six candidates. Treat the high synthetic scores as an engineering smoke test, not a business outcome.

The API marks imported/OTLP telemetry outside the calibrated domain and forces an inconclusive status. Sparse evidence and low-signal windows also trigger abstention. This is a conservative policy, not an independently trained out-of-distribution detector.

## Known limitations

- Only one generating process and one training seed are included.
- Metric inputs are aligned and have an assumed early baseline window.
- The training command currently requires a fixed number of candidates across incidents; inference supports variable candidate counts.
- Missing metrics are not yet modeled with explicit missingness masks. OTLP conversion fills unknown resource metrics with zero and flags the domain mismatch.
- Candidate probabilities depend on the candidate set; they are not independent probabilities of fault.
- References can be structurally valid while the interpretation is wrong. No automatic entailment or causal-identification guarantee is made.
- The model can confidently misrank a service; inspect the held-out errors in `reports/heldout-predictions.json`.
- The hosted investigator has only mock-provider validation, not accuracy measurements on real hosted responses.

## Highest-value next experiment

Import a documented benchmark with permission, preserve labels outside the public schema, add an explicit missingness channel, and evaluate several seeds with service/fault/system-level splits. Compare log-only, metrics-only, graph-only and fused variants against existing published baselines. Do not merge benchmark and synthetic results into a single headline number.
