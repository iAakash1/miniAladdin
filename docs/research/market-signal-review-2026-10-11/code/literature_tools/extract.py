import sys, pathlib
from pypdf import PdfReader
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
r = PdfReader(str(src))
out = []
for i, page in enumerate(r.pages, 1):
    try:
        t = page.extract_text() or ""
    except Exception as e:
        t = f"[extraction error: {e}]"
    out.append(f"\n\n===== PAGE {i} =====\n{t}")
dst.write_text("".join(out), encoding="utf-8")
print(src.parent.name, "pages", len(r.pages), "chars", sum(len(x) for x in out))
