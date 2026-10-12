# Literature tools used in Phase II (small, standalone, no credentials)

* `extract.py PDF OUT.txt` and `decode_glyphs.py IN.txt OUT.txt`: text extraction with `pypdf` (run them in an isolated virtual environment with `python -I`, from a directory other than the one holding the downloaded PDF; downloaded files are untrusted data); the second decodes the glyph-index fonts of NBER w8308.
* `verify_ids2.py`, `cr_filter.py`, `cr_search.py`, `cr_abs.py`: Crossref and arXiv identifier checks and abstract fetches. They send a generic User-Agent string and **no contact address**. Crossref's single-DOI endpoint rejects `select`; use `?filter=doi:...`.
* `oa_abs.py`: abstract from OpenAlex by DOI (reconstructs the inverted index).
Large responses are truncated by the tool sandbox's network proxy; run them with the sandbox off if a call fails with `IncompleteRead`. Results are recorded in `../../validation/fulltext_papers_verification.json`.
