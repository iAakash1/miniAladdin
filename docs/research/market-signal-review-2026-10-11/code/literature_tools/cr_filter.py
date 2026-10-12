import json, sys, time, urllib.request, urllib.parse
UA = "omnisignal-literature-check/1.0 (research; no contact)"
SEL="DOI,title,container-title,issued,volume,issue,page,author,type,publisher"
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
    try:
        q=urllib.parse.urlencode({"filter":"doi:"+d,"rows":1,"select":SEL})
        items=json.loads(get("https://api.crossref.org/works?"+q))["message"]["items"]
        if not items: print(d,"NOT FOUND"); continue
        j=items[0]
        print(d,"|",(j.get("title") or [""])[0][:90],"|",(j.get("container-title") or [""])[0],"|",(j.get("issued",{}).get("date-parts") or [[None]])[0],"|",j.get("volume"),j.get("issue"),j.get("page"),"|",j.get("type"),"|",[x.get("family") for x in j.get("author",[])][:4])
    except Exception as e:
        print(d,"ERROR",repr(e)[:160])
