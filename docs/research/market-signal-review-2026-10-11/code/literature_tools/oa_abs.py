import json, sys, time, urllib.request, urllib.parse, re
UA = "omnisignal-literature-check/1.0 (research; no contact)"
def get(url, tries=4):
    last=None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=60) as r: return r.read()
        except Exception as e:
            last=e; time.sleep(2*(i+1))
    raise last
def inv(ix):
    if not ix: return ""
    words=[]
    for w,pos in ix.items():
        for p in pos: words.append((p,w))
    return " ".join(w for _,w in sorted(words))
for d in sys.argv[1:]:
    try:
        j=json.loads(get("https://api.openalex.org/works/doi:"+d+"?select=id,doi,title,publication_year,type,abstract_inverted_index,primary_location,authorships,cited_by_count"))
        print("##",d,"|",j.get("title"),"|",j.get("publication_year"),"|",j.get("type"),"| cited",j.get("cited_by_count"),"|",[a["author"]["display_name"] for a in j.get("authorships",[])][:4])
        print("   venue:",(j.get("primary_location") or {}).get("source",{}) and (j["primary_location"]["source"] or {}).get("display_name"))
        print("   abstract:",inv(j.get("abstract_inverted_index"))[:1800] or "[none in OpenAlex]")
    except Exception as e:
        print("##",d,"ERROR",repr(e)[:160])
    time.sleep(0.5)
