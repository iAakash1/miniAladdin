import json, sys, time, urllib.request, urllib.parse, re
UA = "omnisignal-literature-check/1.0 (research; no contact)"
def get(url, tries=6):
    last=None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=60) as r: return r.read()
        except Exception as e:
            last=e; time.sleep(2*(i+1))
    raise last
for d in sys.argv[1:]:
    q=urllib.parse.urlencode({"filter":"doi:"+d,"rows":1,"select":"DOI,title,container-title,issued,volume,issue,page,author,abstract,type"})
    items=json.loads(get("https://api.crossref.org/works?"+q))["message"]["items"]
    j=items[0]
    ab=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",j.get("abstract") or "")).strip()
    print("##",d,"|",(j.get("title") or [""])[0],"|",(j.get("container-title") or [""])[0],j.get("volume"),j.get("issue"),j.get("page"),"|",[ (x.get("family"),x.get("given")) for x in j.get("author",[])])
    print(ab[:2500]); print()
