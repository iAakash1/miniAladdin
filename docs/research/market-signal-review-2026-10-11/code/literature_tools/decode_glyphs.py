import re, sys, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
t = src.read_text(encoding="utf-8")
def dec(m):
    v = int(m.group(1), 16) + 29
    return chr(v) if 32 <= v < 127 else {0x1e: " "}.get(v, "?")
# glyph ids: /G31 ... ; ligature-like "._" markers are dropped
t2 = re.sub(r"/G([0-9a-fA-F]{1,2})", dec, t).replace("._", "")
dst.write_text(t2, encoding="utf-8")
print(len(t2))
