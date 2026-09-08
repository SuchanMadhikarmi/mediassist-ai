"""
ml/data_loader.py
─────────────────
Loads and inspects the Bank Marketing dataset.

STEP 1 of the ML pipeline. Everything downstream depends on getting this
right: if we misread the file (wrong separator, wrong columns), every
model we train later is garbage. So we load carefully and check.

CONCEPT (what a DataFrame is):
A pandas DataFrame is a 2-D labeled table (rows = observations, columns =
features). Think of it as a smart spreadsheet you can slice, filter, and
plot in code. Almost every tabular ML project starts by importing data
into one.

CONCEPT (why read the file format correctly):
This file uses:
  - ';' as the column separator (European CSV convention — US CSVs use ',')
  - a quoted header row (values wrapped in quotes)
We MUST tell pandas these details, or it will parse every row as ONE
column. Reading the documentation (bank-names.txt) first is how we know.
"""

import os

import pandas as pd

# Path to the raw data file, relative to this module.
# __file__ is the absolute path of this .py file; its parent is the ml/
# dir; from there we go up one to backend/, then into data/.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
RAW_CSV = os.path.join(DATA_DIR, "bank_marketing", "bank-full.csv")


def load_data() -> pd.DataFrame:
    """Load the raw CSV into a pandas DataFrame, with sanity checks.

    Returns:
        The full 45,211-row DataFrame (16 features + target `y`).
    """
    if not os.path.exists(RAW_CSV):
        raise FileNotFoundError(
            f"Dataset not found at {RAW_CSV}. Download bank-full.csv from "
            "the UCI Bank Marketing repository into data/bank_marketing/."
        )

    # Read the file, telling pandas exactly how it's formatted.
    df = pd.read_csv(
        RAW_CSV,
        sep=";",          # column separator
        quotechar='"',    # values are wrapped in double quotes
        header=0,         # first row is the column names
    )

    return df


def inspect_data(df: pd.DataFrame) -> dict:
    """Print + return a short summary of the dataset.

    CONCEPT (EDA — Exploratory Data Analysis):
    Before training anything, look at the data. We care about:
      1. shape          — how many rows/columns?
      2. dtypes         — which columns are numbers vs categories?
      3. missing values — are any cells empty?
      4. target balance — is the 'yes' class rare? (class imbalance)

    These four answers shape every later decision (preprocessing, which
    metrics to look at, etc.). It's a mistake to skip this.
    """
    summary = {
        "shape": df.shape,
        "columns": list(df.columns),
        "missing": df.isna().sum().sum(),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
    }

    # Target distribution (always worth checking first — it defines the problem).
    print("=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)
    print(f"Shape (rows, columns): {df.shape}")
    print(f"Missing values total:  {df.isna().sum().sum()}")
    print("\nTarget variable 'y' distribution:")
    print(df["y"].value_counts(normalize=True).to_string())
    print("\nColumn dtypes:")
    print(df.dtypes.to_string())
    print("=" * 60)

    return summary


if __name__ == "__main__":
    # Allow running directly:  python ml/data_loader.py
    data = load_data()
    inspect_data(data)
