import json, sys, time, urllib.request, urllib.parse, re
UA = "omnisignal-literature-check/1.0 (research; no contact)"
SEL="DOI,title,container-title,issued,volume,issue,page,author,type,abstract,is-referenced-by-count"
def get(url, tries=6):
    last=None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=60) as r: return r.read()
        except Exception as e:
            last=e; time.sleep(2*(i+1))
    raise last
out=[]
for q in sys.argv[1:]:
    try:
        qs=urllib.parse.urlencode({"query.bibliographic":q,"rows":6,"select":SEL})
        items=json.loads(get("https://api.crossref.org/works?"+qs))["message"]["items"]
        print("### ",q)
        for j in items:
            ab=re.sub(r"<[^>]+>"," ",j.get("abstract") or "")
            ab=re.sub(r"\s+"," ",ab).strip()
            print(" -",j.get("DOI"),"|",(j.get("title") or [""])[0][:110],"|",(j.get("container-title") or [""])[0][:50],"|",(j.get("issued",{}).get("date-parts") or [[None]])[0][0],"|",j.get("volume"),j.get("issue"),j.get("page"),"|",[x.get("family") for x in j.get("author",[])][:3],"| cited",j.get("is-referenced-by-count"))
            if ab: print("     abstract:",ab[:420])
    except Exception as e:
        print("### ",q,"ERROR",repr(e)[:150])
    time.sleep(0.5)
