#!/usr/bin/env python3
"""Baja el catálogo de súper COMPLETO (precios de todo, con y sin oferta) de Carrefour, Día, ChangoMás, Coto, Jumbo, Disco y Vea
para la app "Ofertas del súper", partido en 128 archivos por palabra para que cada celular baje solo
lo que necesita para su lista.
Uso: python3 catalogo_app.py SALIDA_DIR      (necesita ofertas.py en la misma carpeta)
Escribe SALIDA_DIR/cat/index.json y SALIDA_DIR/cat/s000.json … s127.json.
Fila: [súper, nombre, precio, precio_lista, etiqueta, ahorro%, promo, url, precio_efectivo_1u, cantidad, unidad]"""
import json, os, re, sys, datetime, importlib.util, urllib.parse, urllib.request, threading, unicodedata
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("of", os.path.join(HERE, "ofertas.py"))
of = importlib.util.module_from_spec(spec); spec.loader.exec_module(of)
of.THURSDAY = of.TODAY            # vale lo vigente hoy

STORES = ["Carrefour", "Día", "ChangoMás", "Coto", "Jumbo", "Disco", "Vea"]
VTEX = [(0, "www.carrefour.com.ar"), (1, "diaonline.supermercadosdia.com.ar"), (2, "www.masonline.com.ar"),
        (4, "www.jumbo.com.ar"), (5, "www.disco.com.ar"), (6, "www.vea.com.ar")]
# Jumbo, Disco y Vea (Cencosud): el catálogo trae el precio real, pero "ListPrice" es el precio SIN IVA x 100
# (no un precio anterior) y las ofertas no vienen por producto; se cargan solo con precio, sin etiqueta de oferta.
CENCOSUD = {4, 5, 6}
HOSTS = {i: h for i, h in VTEX}; HOSTS[3] = "www.coto.com.ar"
GROCERY = re.compile(r"almac|bebida|l[aá]cte|fresc|carn|fruta|verdu|panad|congel|limpie|perfum|beb[eé]|mascota|desayuno|queso|fiambre|farmacia", re.I)
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
NSHARDS = 128

_local = threading.local()
_orig_day_promo = of.day_promo
_days_lock = threading.Lock()
DAY_SETS = {}
def _day_promo(name):
    r = _orig_day_promo(name)
    si = getattr(_local, "si", None)
    if r and si is not None:
        with _days_lock: DAY_SETS.setdefault(si, set()).add(r)
    return r
of.day_promo = _day_promo

def get(url, timeout=60, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1: raise

def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

UNITS = {"kg": ("g", 1000), "kgs": ("g", 1000), "kilo": ("g", 1000), "kilos": ("g", 1000), "k": ("g", 1000),
         "g": ("g", 1), "gr": ("g", 1), "grs": ("g", 1), "gramos": ("g", 1), "grm": ("g", 1),
         "l": ("ml", 1000), "lt": ("ml", 1000), "lts": ("ml", 1000), "litro": ("ml", 1000), "litros": ("ml", 1000), "ltr": ("ml", 1000),
         "ml": ("ml", 1), "cc": ("ml", 1), "cm3": ("ml", 1)}
SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kgs?|kilos?|k|grs?|gramos|grm|g|lts?|litros?|ltr|l|ml|cc|cm3)\b", re.I)
def size_of(name):
    """Tamaño del envase sacado del nombre: (cantidad, 'g'|'ml') o (0, '')."""
    m = None
    for m in SIZE.finditer(name): pass          # el último suele ser el del envase
    if not m: return 0, ""
    try: q = float(m.group(1).replace(",", "."))
    except ValueError: return 0, ""
    u, f = UNITS.get(m.group(2).lower(), ("", 0))
    if not u or q <= 0: return 0, ""
    q *= f
    pack = re.search(r"\b(\d{1,2})\s*x\s*\d", name, re.I) or re.search(r"\bx\s*(\d{1,2})\s*(?:u|un|uni|unid|unidades)\b", name, re.I)
    if pack and 1 < int(pack.group(1)) <= 24: q *= int(pack.group(1))
    return round(q), u

def make_row(si, p):
    """Fila para un producto del catálogo (formato VTEX), con o sin oferta."""
    try: o = p["items"][0]["sellers"][0]["commertialOffer"]
    except Exception: return None
    if not o.get("IsAvailable"): return None
    price = o.get("Price") or 0
    if not price: return None
    name = re.sub(r"\s+", " ", p.get("productName") or "").strip()
    if not name: return None
    _local.si = si
    d = None if si in CENCOSUD else of.analyze(p)
    if d:
        p_, l_, tag, eff, promo = d["p"], d["l"], d["tag"], d["eff"], (d["promos"] or [""])[0]
        pe = p_
        # promo de 1 unidad que no viene descontada en el precio (ej. "35% off con Mi Carrefour · comprando 1")
        if l_ <= p_ and tag.endswith("% off") and "comprando 1" in promo: pe = p_ * (1 - eff / 100)
    else:
        p_, l_, tag, eff, promo, pe = price, (price if si in CENCOSUD else max(price, o.get("ListPrice") or 0)), "", 0, "", price
        if l_ > p_ * 3: l_ = p_                    # precios de lista inflados
    q, u = size_of(name)
    link = p.get("link", "") or ""
    base = "https://" + HOSTS[si]
    if link.startswith(base + "/"): link = link[len(base):]     # el link se guarda sin el dominio (la app lo arma)
    return [si, name, round(p_), round(l_), tag, eff, promo, link, round(pe), q, u]

def vtex_store(si, host):
    out, seen = [], set()
    try: tree = get(f"https://{host}/api/catalog_system/pub/category/tree/3")
    except Exception as e:
        print(f"{host}: {e}", file=sys.stderr); return out
    def page(path, frm):
        try: return get(f"https://{host}/api/catalog_system/pub/products/search?fq=C:{path}&_from={frm}&_to={frm + 49}") or []
        except Exception: return []
    def crawl(node, path):
        path = path + str(node["id"]) + "/"
        got = 0
        for frm in range(0, 2550, 50):
            if frm > 2500: break
            ps = page(path, frm)
            for p in ps:
                pid = p.get("productId")
                if pid in seen: continue
                seen.add(pid)
                r = make_row(si, p)
                if r: out.append(r)
            got += len(ps)
            if len(ps) < 50: return
        # más de 2500 productos: bajar por subcategorías
        for ch in node.get("children") or []: crawl(ch, path)
    tops = [c for c in tree if GROCERY.search(c["name"])]
    jobs = []
    for t in tops:
        for ch in (t.get("children") or [t]):
            jobs.append((ch, "/" + str(t["id"]) + "/" if ch is not t else "/"))
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda j: crawl(*j), jobs))
    return out

COTO_ROOT = "https://www.coto.com.ar/sitios/cdigi/categoria?Nrpp=1&format=json"
COTO_CATS = re.compile(r"^(almac[eé]n|bebidas|frescos|congelados|limpieza|perfumer[ií]a)$", re.I)
def coto_store(si=3):
    out, seen = [], set()
    try: base = get(COTO_ROOT, 90)
    except Exception as e:
        print(f"coto: {e}", file=sys.stderr); return out
    cats = []
    def walk(o):
        if isinstance(o, dict):
            lab, st = (o.get("label") or "").strip(), o.get("navigationState") or ""
            if st and "count" in o and COTO_CATS.match(lab): cats.append(st.split("?")[0])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(base)
    def fetch_page(st, no):
        try: data = get(f"https://www.coto.com.ar/sitios/cdigi/categoria{urllib.parse.quote(st, safe='/_-')}?Nrpp=200&No={no}&format=json", 90)
        except Exception: return [], 0
        recs, total = [], [0]
        def w2(o):
            if isinstance(o, dict):
                if "records" in o and "totalNumRecs" in o: recs.extend(o["records"] or []); total[0] = o["totalNumRecs"]; return
                for v in o.values(): w2(v)
            elif isinstance(o, list):
                for v in o: w2(v)
        w2(data)
        return recs, total[0]
    for st in dict.fromkeys(cats):
        recs, total = fetch_page(st, 0)
        pages = [recs]
        with ThreadPoolExecutor(4) as ex:
            pages += [r for r, _ in ex.map(lambda no: fetch_page(st, no), range(200, total, 200))]
        for recs in pages:
            for p in of.coto_records(recs):
                key = p["link"] or p["productName"]
                if key in seen: continue
                seen.add(key)
                r = make_row(si, p)
                if r: out.append(r)
    return out

def shard_of(prefix):
    h = 0
    for c in prefix: h = (h * 31 + ord(c)) % 1000003
    return h % NSHARDS

if __name__ == "__main__":
    outdir = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "cat")
    os.makedirs(outdir, exist_ok=True)
    with ThreadPoolExecutor(7) as ex:
        parts = list(ex.map(lambda f: f(), [lambda h=h: vtex_store(*h) for h in VTEX] + [coto_store]))
    rows = [r for part in parts for r in part]
    shards = [[] for _ in range(NSHARDS)]
    for i, r in enumerate(rows):
        ks = {shard_of(w[:2]) for w in norm(r[1]).split() if len(w) >= 3 and not w.isdigit()}
        for k in ks: shards[k].append(i)
    for k in range(NSHARDS):
        with open(os.path.join(outdir, f"s{k:03d}.json"), "w", encoding="utf8") as f:
            json.dump([rows[i] for i in shards[k]], f, ensure_ascii=False, separators=(",", ":"))
    counts = {s: sum(1 for r in rows if r[0] == i) for i, s in enumerate(STORES)}
    with open(os.path.join(outdir, "index.json"), "w", encoding="utf8") as f:
        json.dump({"checked": datetime.datetime.now(of.AR).strftime("%Y-%m-%d %H:%M"), "stores": STORES,
                   "counts": counts, "offers": {s: sum(1 for r in rows if r[0] == i and r[4]) for i, s in enumerate(STORES)},
                   "days": {s: sorted(DAY_SETS.get(i, ())) for i, s in enumerate(STORES)}, "shards": NSHARDS, "total": len(rows),
                   "hosts": {str(i): "https://" + h for i, h in HOSTS.items()}}, f, ensure_ascii=False)
    print(" ".join(f"{s}: {c}" for s, c in counts.items()), "total:", len(rows), file=sys.stderr)
