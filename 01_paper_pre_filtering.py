from pathlib import Path
import json
import re
import pandas as pd
import pymupdf
import argparse

parser = argparse.ArgumentParser(description="Select the directory containing the papers.")
parser.add_argument("papers_dir", type=Path, help="Path to the directory containing the papers.")
args = parser.parse_args()

PAPERS_DIR = args.papers_dir

KEYWORDS_FILE = Path(__file__).resolve().parent / "01_keywords.json"


def load_keywords(path):
    with path.open(encoding="utf-8-sig") as handle:
        keywords = json.load(handle)
    if not isinstance(keywords, list) or not keywords or not all(
        isinstance(keyword, str) and keyword.strip() for keyword in keywords
    ):
        raise ValueError(f"{path} must contain a non-empty JSON list of non-empty strings")
    return keywords


SEARCH_WORDS = load_keywords(KEYWORDS_FILE)

def find_keywords_in_pdf(pdf_path):
    found_keywords = set()

    with pymupdf.open(pdf_path) as pdf:
        for page in pdf:
            text = page.get_text()

            for keyword in SEARCH_WORDS:
                pattern = re.compile(
                    rf"(?<!\w){re.escape(keyword)}(?!\w)",
                    re.IGNORECASE
                )

                if pattern.search(text):
                    found_keywords.add(keyword)

    return sorted(found_keywords)


results = []

for pdf_path in PAPERS_DIR.glob("*.pdf"):

    print(f"Checking {pdf_path.name}...")

    try:
        found = find_keywords_in_pdf(pdf_path)

        results.append(
            {
                "file": pdf_path.name,
                "keywords_found": "; ".join(found) if found else "-"
            }
        )

    except Exception as e:
        print(f"ERROR in {pdf_path.name}: {e}")

        results.append(
            {
                "file": pdf_path.name,
                "keywords_found": "ERROR"
            }
        )

df = pd.DataFrame(results)

df.to_csv(
    "paper_screening_results.csv",
    index=False
)

print("\nFinished.")
print(df)