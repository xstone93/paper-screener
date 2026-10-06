# Screening CSEd papers for GenAI use

This workflow identifies use of GenAI by computing education researchers across the research process: literature review, methods, data collection, qualitative and quantitative analysis, writing, revision, and peer review. Papers whose research topic is AI are excluded from this review.

1. Download the paper PDFs from the digital library using the download links, and save them in conference subfolders under `ai-paper-screener/`. For paper downloading I've used the ``?download=1`` query parameter, e.g., https://dl.acm.org/doi/pdf/10.1145/3776542?download=true. Since ACM DL doesn't allow automated (systematic) downloads, check the JavaScript code under XXX which can provide some help here.  
2. Run `01_paper_pre_filtering.py` on one subfolder. Set `PAPERS_DIR` in the script to that folder first (currently `./ACE 2026/`). The script extracts text with PyMuPDF and searches every page for the keywords in [01_keywords.json](../01_keywords.json), ignoring case and matching word boundaries. It writes each filename and its matched keywords to `paper_screening_results.csv`; `-` means no keyword matched. Rename this output between conference runs because this first-stage script overwrites it.
3. From the keyword results, select candidate papers for LLM screening and put their local PDF paths into a text file, one per line. This selection is manual; the keyword CSV is not automatically passed to the LLM script. Relative paths are resolved from the text file's folder.
4. Run `02_screen_genai.py` on that list. It sends the full extracted text with PDF page numbers to the locally hosted **Qwen3.5 122B** model through **Ollama over Tailscale**. The configured model is `tailscale:qwen3.5:122b` (sent to Ollama as `qwen3.5:122b`), using temperature `0` and the prompt below.
5. Review the results: a CSV with PDF name, judgment (`-` or `Potential AI usage`), a short summary, and exact occurrences with physical PDF page numbers. New results append to existing output, and a companion JSON log records details. Check flagged passages and incomplete results manually against the PDFs.

Run from the project root:

```powershell
cd ai-paper-screener
python -m pip install -r requirements.txt
python -m pip install pandas
python 01_paper_pre_filtering.py
# After selecting candidates and saving their paths:
python 02_screen_genai.py --pdf-list papers-iticse.txt --output results.csv
```

Keyword matching is a preliminary filter, not evidence of researcher GenAI use. It can miss disclosures with other wording. The LLM script checks quotations against extracted text on the stated page, allowing whitespace differences only. If validation fails twice, the current implementation records an error and leaves the judgment blank; this is an incomplete screening, not a negative finding.

## ACM Download

Open ACM Digital Library, Click ``F12`` on your Browser, open the DevSettings and put this code in the Console. 

To avoid approving each and every single download, allow for multiple downloads in the browser settings. 

```javascript

const dois = [  
    "10.1145/3773911",
    "10.1145/3776542"
    // Add all DOIs
];

for (const doi of dois) {
  const url = `https://dl.acm.org/doi/pdf/${doi}?download=1`;

  const r = await fetch(url, {
    credentials: "include"
  });

  if (!r.ok) {
    console.warn("Failed:", doi, r.status);
    continue;
  }

  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = doi.replace("/", "_") + ".pdf";
  document.body.appendChild(a);
  a.click();
  a.remove();

  setTimeout(() => URL.revokeObjectURL(a.href), 5000);

  // Timer to relieve ACM a bit. :-) 
  await new Promise(r => setTimeout(r, 1500));
}

```

## Keyword list

All pre-filtering keywords are maintained in [01_keywords.json](./01_keywords.json).
The file contains a JSON array of strings. Keep at least one non-empty keyword and use valid JSON (double quotes, no comments or trailing commas).

`01_paper_pre_filtering.py` loads this file relative to its own location, independently of the working directory. Matching remains case-insensitive with word boundaries.
