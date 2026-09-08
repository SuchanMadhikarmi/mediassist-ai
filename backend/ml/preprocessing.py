"""
ml/preprocessing.py
───────────────────
Builds the feature-transformation pipeline.

STEP 2 of the ML pipeline (after splitting — see train.py for the split).

CONCEPT (why preprocess at all):
Most ML models work on NUMBERS. Our features are a mix of:
  - categorical ('job' = technician/management/...), and
  - numeric ('balance' = 2143, 'campaign' = 1, ...)
We must convert categories to numbers (one-hot encoding) and scale
numbers, so the model can actually learn from them.

CONCEPT (DATA LEAKAGE — the core ML rule):
A model must learn ONLY from training data. If we fit our transformers
using the WHOLE dataset (train+test), the model has effectively "seen"
the test set's statistics during training. That inflates test scores and
makes them dishonest — the model looks great in the lab but fails on
truly new data in production.

THE FIX (a pattern you will reuse forever):
  encoder/scaler .fit(X_TRAIN)   # learn parameters from TRAIN ONLY
  X_train = .transform(X_train)
  X_test  = .transform(X_test)    # same fitted object, just applied

We use a ColumnTransformer so both the one-hot encoder and the scaler
live in ONE object, fit together on train, and transform both splits.
"""

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler


# ── Feature column lists (from inspecting the data) ─────────────
# These are OUR choices about what is categorical vs numeric. This is
# domain knowledge: 'job' is clearly categorical text; 'age' is clearly a
# number. Getting this split right matters.
NUMERIC_COLUMNS = [
    "age", "balance", "day", "duration", "campaign", "pdays", "previous"
]

CATEGORICAL_COLUMNS = [
    "job", "marital", "education", "default",
    "housing", "loan", "contact", "month", "poutcome",
]


def build_preprocessor() -> ColumnTransformer:
    """Build a ColumnTransformer: one-hot categories + scale numbers.

    Returns a single transformer object. YOU must .fit() it on the
    TRAINING data only, then .transform() both train and test.

    CONCEPT (OneHotEncoder):
    Turns one categorical column into N binary columns (one per unique
    value), e.g. contact='cellular' -> contact_cellular=1, contact_telephone=0.
    Why not just label as 1,2,3? Because that would imply an ORDER
    (cellular < telephone < unknown) which doesn't exist. One-hot adds no
    fake ordering.

    CONCEPT (StandardScaler):
    Rescales numeric columns to mean=0, std=1. Prevents a big column
    (balance ~ thousands) from dominating a small one (campaign ~ 1)
    purely because of its magnitude.

    CONCEPT (ColumnTransformer):
    Lets us apply DIFFERENT transforms to DIFFERENT columns in one object,
    so we can fit/transform everything in one call instead of juggling
    several pipelines.

    Argument order matters: transformers = [(name, transformer, columns)].
    """
    numeric_pipeline = StandardScaler()
    categorical_pipeline = OneHotEncoder(handle_unknown="ignore")

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUMERIC_COLUMNS),
            ("cat", categorical_pipeline, CATEGORICAL_COLUMNS),
        ]
    )
    return preprocessor


if __name__ == "__main__":
    # Quick self-check: does it build?
    p = build_preprocessor()
    print("Preprocessor built OK:")
    print(p)
