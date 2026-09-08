# ML Model Evaluation — MediAssist AI

> **Why this document exists:** the university Track B requirement is
> "baseline + 2 models compared, precision/recall/F1, confusion matrix,
> bias discussion". This doc records the **real, measured numbers** (read
> live from the `model_registry` table in PostgreSQL) and — just as
> important — the honest *limitations* and *bias* of the setup.
>
> Every claim below traces back to an artifact: `backend/ml/models/`,
> `backend/ml/train.py`, and the registry row.

## 1. Task & dataset

- **Task (binary classification):** will this client **subscribe to a
  premium service**? (`y ∈ {yes, no}`)
- **Dataset:** UCI *Bank Marketing* (`bank-full.csv`), **45,211 rows**,
  16 input features (age, job, marital, education, balance, loan,
  duration, previous campaign outcome, …).
- **Target imbalance:** **88% no / 12% yes** — this is *real-world* and
  shapes every methodological choice below.

## 2. Protocol (why the numbers can be trusted)

```
raw CSV (45,211)
   → stratified 70 / 15 / 15  split        # train / val / test, class balance preserved
   → preprocessor fitted on TRAIN only     # ⚠ no label/data leakage from val/test
   → SMOTE applied on TRAIN only           # balance classes for the learner, NEVER for eval
   → train LR (baseline) + XGBoost (boosted tree)
   → evaluate on the untouched 15% test set → metrics → joblib artifacts
   → both models registered in model_registry (xgboost = ACTIVE)
```

**Why SMOTE on train only:** the test set must resemble real, unbalanced
data — if we oversampled the test set too, the metrics would report
fiction. Augmenting the *learner's* view of the minority class while
evaluating on reality is the correct split.

## 3. Results (test set — real values from `model_registry`)

| Metric | Logistic Regression (baseline) | **XGBoost (active)** |
|--------|:------------------------------:|:--------------------:|
| ROC-AUC | 0.9010 | **0.9236** |
| Accuracy | 0.8421 | **0.8508** |
| Precision (macro) | 0.6891 | **0.7047** |
| Recall (macro) | 0.8209 | **0.8548** |
| F1 (macro) | 0.7224 | **0.7418** |

### Confusion matrices (test set, 5989 `no` / 793 `yes`)

Rows = actual, columns = predicted — layout `[[TN, FP], [FN, TP]]`.

**Logistic Regression:**
```
                 predicted
                no       yes
   actual no   5082      907     (FP = 907 promo shown to non-subscribers)
   actual yes   164      629     (FN = 164 subscribers missed)
```

**XGBoost:**
```
                 predicted
                no       yes
   actual no   5088      901     (FP = 901)
   actual yes   111      682     (FN = 111 subscribers missed)
```

### Reading the numbers (the viva-ready interpretation)

- **AUC ↑ (0.9236)** — XGBoost ranks a random *yes* example above a random
  *no* example ~92% of the time; it is the better model wall-to-wall.
- **Accuracy is the trap:** with 88% negatives, *always predicting "no"*
  scores 88% accuracy with zero skill. **That is why we report macro
  recall/F1 and the confusion matrix**, not just accuracy.
- **FN vs FP is a business trade-off:** an FN (a subscriber we predicted
  "no") is lost revenue; an FP (we predicted "yes" and they decline) only
  wastes a follow-up call. XGBoost cuts missed subscribers **164 → 111
  (−32%)** for almost the same FP. Depending on cost per campaign this
  might justify lowering the decision threshold below the default 0.5.

## 4. Class-level detail (XGBoost)

| Class | Precision | Recall | F1 |
|-------|----------:|-------:|----:|
| `no`  (majority) | 0.9787 | 0.8495 | 0.9095 |
| `yes` (minority) | 0.4308 | 0.8600 | 0.5741 |

Minority-class recall stays high (0.86) — the SMOTE-on-train training and
`scale_pos_weight` build a model that actually *finds* subscribers instead
of hedging into the majority class.

## 5. Bias & limitations (the honest section)

1. **Domain-transfer bias.** This is a 2008 Portuguese retail-bank
   marketing dataset used as a *learning vehicle*. It says nothing valid
   about a real clinic's premium-subscription behaviour, and we never
   claim otherwise. The **pattern** (split → fit → evaluate → registry →
   logged inference) transfers to any domain; the learned weights do not.
2. **Geographic / temporal bias.** Single country, single campaign era.
   Any deployment would need retraining on local, current data.
3. **No protected-attribute analysis.** Age/education/job exist in the
   features but we have not run fairness audits (e.g. demographic parity
   by age band). For a *clinical* deployment this would be required.
4. **Measurement/feedback bias.** The ground-truth "subscribed?" label is
   the campaign's own follow-up record — historical campaign contact
   patterns shape what the labels look like.
5. **Class imbalance encoded in thresholds.** Defaulting to a 0.5 decision
   threshold optimises nothing in particular; choosing it by the
   business-cost ratio (FN vs FP) is the correct, explicit step.
6. **Lineage controls.** `model_registry.training_data_hash` + 
   `trained_at` + `trained_by` record provenance for every artifact, so
   "which model ran on which data" is always auditable.

## 6. Production deployment (inference + audit)

- Artifacts: `backend/ml/models/` (joblib `.pkl`).
- `POST /api/predict` validates input (Pydantic = 422 gate) → lazy-loads
  the active model → returns `{output, confidence, model, version}` while
  writing an audit row.
- **Every prediction is logged to `predictions`** (input, output,
  confidence, model_version, user_id, inference_time_ms, timestamp) **and
  `audit_log`** — the Track B "every prediction logged" requirement is
  verified live (valid request → row; invalid request → no row).
- Expert review (`/review`) lets an expert override a prediction; the
  override itself is auditable.

## 7. Reproduce

```bash
cd backend/ml
../.venv/bin/python train.py      # re-runs the full pipeline, writes artifacts + registry
../.venv/bin/python predictor.py   # smoke-test inference against the saved artifact
```

Registry: `SELECT model_name, is_active, metrics FROM model_registry;`
(active model: **xgboost**).