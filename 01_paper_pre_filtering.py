from pathlib import Path
import json
import re
import pandas as pd
import pymupdf
import argparse
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from html_fulltext import extract_fulltext, match_keywords

parser = argparse.ArgumentParser(description="Select the directory containing the papers.")
parser.add_argument("papers_dir", type=Path, nargs="?", help="Path to the directory containing the papers.")
parser.add_argument("--doi-list", type=Path, help="File with one DOI or direct PDF URL per line")
parser.add_argument("--format", choices=("pdf", "html"), default="pdf", help="Online full-text format")
parser.add_argument("--limit", type=int, help="Process only the first N papers")
parser.add_argument("--output", type=Path, default=Path("paper_screening_results.csv"))
parser.add_argument("--delay", type=float, default=2, help="Seconds between online requests")
args = parser.parse_args()
if (args.papers_dir is None) == (args.doi_list is None):
    parser.error("Specify either papers_dir or --doi-list")
if args.limit is not None and args.limit < 1:
    parser.error("--limit must be positive")
if args.delay < 0:
    parser.error("--delay must be nonnegative")
if args.papers_dir is not None and not args.papers_dir.is_dir():
    parser.error("papers_dir must be an existing directory")

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



def find_keywords_in_pdf(pdf_path=None, data=None):
    found_keywords = set()
    characters = 0

    # Dateiinhalt prüfen, nicht nur die Dateiendung
    if data is None:
        data = Path(pdf_path).read_bytes()

    # Prüfen, ob es sich tatsächlich um eine PDF-Datei handelt
    if b"%PDF-" not in data[:1024]:
        raise ValueError(
            "NOT_PDF: File is not a real PDF "
            "(possibly an HTML landing page saved as PDF)"
        )

    with pymupdf.open(stream=data, filetype="pdf") as pdf:

        if not pdf.is_pdf:
            raise ValueError(
                "NOT_PDF: PyMuPDF identified a different file format"
            )

        if pdf.needs_pass:
            raise ValueError("PDF is password protected")

        if pdf.page_count == 0:
            raise ValueError("PDF contains no pages")

        for page in pdf:
            text = page.get_text()
            characters += len(text.strip())

            for keyword in SEARCH_WORDS:
                pattern = re.compile(
                    rf"(?<!\w){re.escape(keyword)}(?!\w)",
                    re.IGNORECASE
                )

                if pattern.search(text):
                    found_keywords.add(keyword)

    if characters == 0:
        raise ValueError(
            "NO_TEXT: PDF contains no extractable text; "
            "OCR may be required"
        )

    return sorted(found_keywords)


def online_pdf_url(entry):
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", entry, flags=re.I)
    if doi.startswith("10.1145/"):
        return "https://dl.acm.org/doi/pdf/" + doi
    if doi.startswith("10."):
        return "https://doi.org/" + doi
    if entry.startswith(("https://", "http://")):
        return entry
    raise ValueError("Expected a DOI, DOI URL, or direct PDF URL")


def find_keywords_online(url):
    request = Request(url, headers={"User-Agent": "PaperKeywordScreening/1.0",
                                    "Accept": "application/pdf"})
    with urlopen(request, timeout=30) as response:
        data = response.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise ValueError("PDF exceeds the 50 MiB memory limit")
    if b"%PDF-" not in data[:1024]:
        raise ValueError("Response is not a PDF full text (landing page or access restriction)")
    return find_keywords_in_pdf(data=data)


def online_html_url(entry):
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", entry, flags=re.I)
    if doi.startswith("10.1145/"):
        return "https://dl.acm.org/doi/full/" + doi
    if doi.startswith("10."):
        return "https://doi.org/" + doi
    if entry.startswith(("https://", "http://")):
        return entry
    raise ValueError("Expected a DOI or HTML URL")


def find_keywords_in_html(url):
    request = Request(url, headers={"User-Agent": "PaperKeywordScreening/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=30) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("HTML exceeds the 10 MiB limit")
    return match_keywords(extract_fulltext(data), SEARCH_WORDS)


results = []

if args.doi_list:
    papers = list(dict.fromkeys(line.strip() for line in
                  args.doi_list.read_text(encoding="utf-8-sig").splitlines()
                  if line.strip() and not line.lstrip().startswith("#")))
else:
    papers = sorted(PAPERS_DIR.glob("*.pdf"))
if args.limit:
    papers = papers[:args.limit]

for index, pdf_path in enumerate(papers):
    if args.doi_list and index:
        time.sleep(args.delay)

    name = str(pdf_path) if args.doi_list else pdf_path.name
    source_url = ""
    is_html = bool(args.doi_list and args.format == "html")

    print(f"Checking {name}...", flush=True)

    try:
        if args.doi_list:
            if is_html:
                source_url = online_html_url(str(pdf_path))
                found = find_keywords_in_html(source_url)
            else:
                source_url = online_pdf_url(str(pdf_path))
                found = find_keywords_online(source_url)
        else:
            found = find_keywords_in_pdf(pdf_path)

        results.append({
            "file": name,
            "pdf_readable": "N/A" if is_html else True,
            "keywords_found": "; ".join(found) if found else "-",
            "status": "OK",
            "source_url": source_url,
            "error": ""
        })


    except Exception as e:
        print(f"ERROR in {name}: {e}")

        error_message = str(e)

        if isinstance(e, HTTPError) and e.code in (401, 403):
            status = "ACCESS_DENIED"
        elif error_message.startswith("NOT_PDF:"):
            status = "NOT_PDF"
        elif error_message.startswith("NO_TEXT:"):
            status = "NO_TEXT"
        else:
            status = "ERROR"

        results.append({
            "file": name,
            "pdf_readable": False if not is_html else "N/A",
            "keywords_found": "ERROR",
            "status": status,
            "source_url": source_url,
            "error": error_message
        })

    # Save after each paper
    pd.DataFrame(results).to_csv(args.output, index=False)

df = pd.DataFrame(
    results,
    columns=[ "file", "pdf_readable", "keywords_found", "status", "source_url", "error" ]
)

df.to_csv(args.output, index=False)

print("\nFinished.")
print(df)
