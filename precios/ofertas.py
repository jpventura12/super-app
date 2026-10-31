#!/usr/bin/env python3
"""Busca en el catálogo público de Carrefour Argentina (VTEX) los productos de la lista
y devuelve los que tienen descuento. Uso: python3 ofertas.py items.json > deals.json
items.json: [{"t": "Ketchup", "q": "ketchup"}, ...]   (q opcional)"""
import json, re, sys, unicodedata, urllib.parse, urllib.request, datetime

BASE = "https://www.carrefour.com.ar/api/catalog_system/pub/products/search"
STOP = {"p","para","de","del","la","el","los","las","tipo","x","con","y","dc"}
# Búsquedas manuales para nombres de la heladera que no coinciden con el catálogo
# Ajustes para nombres de la heladera que no coinciden con el catálogo.
# q: qué buscar; need: palabras que tiene que tener el producto; first: la 1ra palabra de need
# tiene que ser la 1ra del nombre; anyof: al menos una; excl: descartar si aparece.
MANUAL = {
    # Aclarados por Juan el 26/10
    "arroz dc": {"q": "arroz doble carolina", "need": ["arroz"], "anyof": ["doble carolina", "carolina"], "pref": ["molinos ala"]},
    "brocoli": {"q": "brocoli", "need": ["brocoli"], "anyof": ["congelado", "bolsa"], "pref": ["granja del sol"]},
    "queso p/ rallar": {"q": "queso rallado", "need": ["queso", "rallado"], "first": False, "excl": ["alimento a base", "aderezo"]},
    "pastilla p/ inodoro": {"q": "pastilla inodoro", "need": ["inodoro"], "first": False,
                            "desc_any": ["mochila", "deposito", "tanque", "cisterna"], "excl": ["canasta", "con red"]},
    "liquido tipo vanish": {"q": "quitamanchas liquido", "need": ["quitamanchas"], "first": False, "excl": ["barra", "polvo", "jabon"]},
    "guantes p/ pelo roman": {"q": "guantes latex", "need": ["guante"], "anyof": ["latex", "multiuso", "nitrilo", "goma"], "excl": ["parrilla", "descartable", "jardin"]},
    "magiclick": {"q": "encendedor", "need": ["encendedor"], "anyof": ["magiclick", "flex", "reach", "mega", "electronico", "cocina", "volcano"], "excl": ["lampara", "12v"]},
    "alicate": {"q": "alicate", "need": ["alicate"], "first": False, "anyof": ["una", "cuticula", "manicur", "pedicur"]},
    "coca cola": {"q": "coca cola", "need": ["coca", "cola"], "first": False, "rx": r"sabor original (2 25|3) (l|lt|lts|litros)\b"},
    "pan lactal": {"q": "bimbo artesano", "need": ["artesano"], "first": False, "brand_any": ["artesano", "bimbo"], "excl": ["pancho", "hamburguesa", "budin"]},
    "cinta scotch": {"q": "cinta adhesiva transparente", "need": ["cinta"], "anyof": ["transparente", "invisible"], "excl": ["embalar", "papel", "padel", "protectora", "doble faz", "aisladora"]},
    # Ajustes de búsqueda
    "ayudin antihongos": {"q": "ayudin antihongos", "need": ["ayudin"], "first": False, "anyof": ["hongo", "moho"]},
    "biromes": {"q": "boligrafo"},
    "talitas": {"q": "talitas", "need": ["talita"], "first": False},
    "trapos de piso": {"q": "trapo piso", "need": ["trapo", "piso"], "first": False, "pref": ["bulnez"]},
    # Marcas sacadas de los tickets (confirmadas por Juan el 26/10)
    "ketchup": {"pref": ["heinz", "hellmann"]},
    "oregano": {"pref": ["alicante"]},
    "papel higienico": {"q": "papel higienico doble hoja", "need": ["papel", "higienico"], "first": False, "anyof": ["doble hoja"]},
    "rollo de cocina": {"q": "rollo de cocina", "need": ["rollo", "cocina"], "pref": ["sussex"], "any_brand": True},
    "queso untable": {"q": "queso untable", "need": ["untable"], "first": False, "pref": ["finlandia"]},
    "trapos rejilla": {"q": "rejilla", "need": ["rejilla"], "first": False, "excl": ["anafe", "lavatorio", "horno", "parrilla", "ventilacion", "cocina a gas", "auto", "palito", "saladix", "snack", "desague", "piso de ducha", "planchar"], "pref": ["bulnez"]},
}

def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9/ ]+", " ", s).strip()

def config_for(item):
    n = norm(item["t"])
    c = dict(MANUAL.get(n, {}))
    if item.get("q"): c["q"] = item["q"]
    if not c.get("q"): c["q"] = " ".join(w for w in n.replace("/", " ").split() if w not in STOP)
    if not c.get("need"): c["need"] = words(c["q"])
    c.setdefault("first", True)
    return c

def matches(p, c):
    """p: producto del catálogo (o un nombre suelto). c: configuración de búsqueda."""
    if isinstance(p, str): p = {"productName": p}
    nn = norm(p.get("productName", ""))
    toks = nn.split()
    if not all(w in nn for w in c["need"]): return False
    if c["first"] and c["need"] and not (toks and toks[0].startswith(c["need"][0])): return False
    if c.get("anyof") and not any(w in nn for w in c["anyof"]): return False
    if c.get("excl") and any(w in nn for w in c["excl"]): return False
    if c.get("rx") and not re.search(c["rx"], nn): return False
    if c.get("brand_any") and not any(b in norm(p.get("brand") or "") for b in c["brand_any"]): return False
    if c.get("desc_any"):
        d = norm(re.sub(r"<[^>]+>", " ", (p.get("description") or "") + " " + (p.get("metaTagDescription") or "")))
        if not any(w in d for w in c["desc_any"]): return False
    return True

def words(q):
    out = []
    for w in norm(q).split():
        if w in STOP or len(w) < 3: continue
        w = re.sub(r"(es|s)$", "", w) if len(w) > 4 else w
        out.append(w)
    return out

def fetch(q, n=40):
    url = BASE + "?ft=" + urllib.parse.quote(q) + "&_from=0&_to=" + str(n - 1)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

GENERIC = re.compile(r"tarjeta carrefour 15", re.I)
AR = datetime.timezone(datetime.timedelta(hours=-3))
TODAY = datetime.datetime.now(AR).date()
THURSDAY = TODAY + datetime.timedelta(days=(3 - TODAY.weekday()) % 7)   # el jueves de esta semana (hoy si es jueves)

def price_valid_until(v):
    """Último día (hora Argentina) en que vale el precio publicado, o None si no se informa."""
    if not v: return None
    try: t = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError: return None
    return (t.astimezone(AR) - datetime.timedelta(seconds=1)).date()

def ends_before_thursday(label):
    """True si la promo dice 'hasta el DD/MM' y esa fecha es anterior al jueves."""
    m = re.search(r"hasta el (\d{1,2})/(\d{1,2})", label)
    if not m: return False
    d, mo = int(m.group(1)), int(m.group(2))
    try: end = datetime.date(THURSDAY.year if mo >= THURSDAY.month - 6 else THURSDAY.year + 1, mo, d)
    except ValueError: return False
    return end < THURSDAY
DAYS = re.compile(r"(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)", re.I)
DAY_PROMOS = set()

def day_promo(name):
    """Promos de un medio de pago para un día (ej. 'Cuenta Digital Carrefour 15% Off Viernes')."""
    d = DAYS.search(name)
    if not d: return False
    pct = re.search(r"(\d+)\s*%", name)
    medio = re.sub(r"\d+\s*%|off|" + d.group(1), "", name, flags=re.I)
    medio = re.sub(r"\s+", " ", medio).strip(" -")
    day = d.group(1).capitalize().replace("Miercoles", "Miércoles").replace("Sabado", "Sábado")
    label = day + ": " + (pct.group(1) + "% off" if pct else "descuento") + " con " + medio
    DAY_PROMOS.add(label)
    return label

def clean_promo(name, minq=0):
    """Pasa el nombre interno de la promo a algo legible y aclara cuántas unidades hay que llevar.
    Devuelve (texto, etiqueta corta, ahorro efectivo en %)."""
    s = re.sub(r"^PROMO-?", "", name).strip()
    vig = re.search(r"(\d{1,2}\s*al\s*\d{1,2}[./]\d{1,2}|\d{1,2}/\d{1,2}\s*al\s*\d{1,2}/\d{1,2})", s)
    mic = " con Mi Carrefour" if re.search(r"mi\s*crf|mi\s*carrefour", s, re.I) else ""
    extra = " (podés combinar productos de la promo)" if re.search(r"combinable", s, re.I) else (" iguales" if re.search(r"iguales", s, re.I) else "")
    mx = re.search(r"max\.?\s*(\d+)\s*unidades", s, re.I)
    nth = re.search(r"(\d)\s*(?:do|da|ro|ra|to|ta)\s*(?:unidad\s*)?al\s*(\d+)\s*%?", s, re.I)
    nxm = re.search(r"\b(\d)\s*x\s*(\d)\b", s, re.I) or re.search(r"llev[aá]s?\s*(\d)\s*pag[aá]s?\s*(\d)", s, re.I)
    pct = re.search(r"(\d+)\s*%", s)
    if nth and int(nth.group(2)) >= 100:
        n = int(nth.group(1)); m = n - 1
        short = f"{n}x{m}"; eff = round(100 / n)
        label = f"{short}{mic} · llevando {n} pagás {m}{extra}"
    elif nth:
        n = int(nth.group(1)); x = int(nth.group(2))
        short = f"{n}{'da' if n == 2 else 'ra'} al {x}%"; eff = round(x / n)
        label = f"{n}{'da' if n == 2 else 'ra'} unidad al {x}%{mic} · llevando {n}{extra}"
    elif nxm and int(nxm.group(1)) > int(nxm.group(2)):
        n, m = int(nxm.group(1)), int(nxm.group(2))
        short = f"{n}x{m}"; eff = round((n - m) * 100 / n)
        label = f"{short}{mic} · llevando {n} pagás {m}{extra}"
    elif pct:
        cuant = f"llevando {minq} o más" if minq and minq > 1 else "comprando 1"
        short = f"{pct.group(1)}% off"; eff = int(pct.group(1))
        label = f"{short}{mic} · {cuant}"
    else:
        short = "Promo"; eff = 0
        label = s.split(" Max")[0][:50]
    if mx: label += f", máx. {mx.group(1)}"
    if vig: label += " · hasta el " + re.split(r"\s*al\s*", vig.group(1))[-1].replace(".", "/")
    return label, short, eff

def analyze(p):
    """Devuelve la oferta de un producto válida para el jueves, o None."""
    try: o = p["items"][0]["sellers"][0]["commertialOffer"]
    except Exception: return None
    if not o.get("IsAvailable"): return None
    price, lst = o.get("Price") or 0, max(o.get("ListPrice") or 0, o.get("PriceWithoutDiscount") or 0)
    if not price: return None
    promos, best_short, best_eff = [], "", 0
    raw = [(t.get("Name") or "", (t.get("Conditions") or {}).get("MinimumQuantity") or 0) for t in (o.get("PromotionTeasers") or [])]
    raw += [(h.get("<Name>k__BackingField") or h.get("Name") or "", 0) for h in (o.get("DiscountHighLight") or [])]
    for nm, minq in raw:
        if not nm or GENERIC.search(nm): continue
        dp = day_promo(nm)
        if dp:
            if dp.startswith("Jueves"): promos.append(dp)
            continue                      # promos de otros días no sirven: compran los jueves
        label, short, eff = clean_promo(nm, minq)
        if ends_before_thursday(label): continue
        promos.append(label)
        if eff > best_eff: best_short, best_eff = short, eff
    promos = list(dict.fromkeys(promos))
    off = round((1 - price / lst) * 100) if lst and price < lst else 0
    pv = price_valid_until(o.get("PriceValidUntil"))
    if off and pv and pv < THURSDAY:
        # el precio rebajado vence antes del jueves: ese día se paga el precio de lista
        if not promos: return None
        price, off = lst, 0
    if off < 5 and not promos: return None
    if off >= 5 and not any("off" in x for x in promos):
        promos.insert(0, "Precio rebajado · comprando 1")
    eff = max(off, best_eff)
    tag = f"{off}% off" if off >= best_eff and off >= 5 else (best_short or "Promo")
    hasta = pv.strftime("%d/%m") if off and pv and pv < THURSDAY + datetime.timedelta(days=60) else ""
    if hasta: promos = [x + f" · hasta el {hasta}" if x.startswith("Precio rebajado") else x for x in promos]
    return {"n": p.get("productName", ""), "p": round(price, 2), "l": round(lst, 2), "off": off, "eff": eff,
            "tag": tag, "promos": promos[:2], "url": p.get("link", "")}

def deals_for(item):
    c = config_for(item)
    q = c["q"]
    try: prods = fetch(q)
    except Exception as e: return {"t": item["t"], "q": q, "error": str(e)[:120], "deals": []}
    found = []
    for p in prods:
        if not matches(p, c): continue
        d = analyze(p)
        if not d: continue
        if c.get("pref"):
            d["mine"] = any(b in norm(p.get("productName", "") + " " + (p.get("brand") or "")) for b in c["pref"])
        found.append(d)
    found.sort(key=lambda d: (-d["eff"], -len(d["promos"]), d["p"]))
    if c.get("pref"):
        # Su marca primero; otras marcas solo si ahorran bastante más (15 puntos o más)
        mine = [d for d in found if d["mine"]]
        best = mine[0]["eff"] if mine else 0
        if c.get("any_brand"):   # su marca primero, pero cualquier otra también sirve
            others = [d for d in found if not d["mine"]]
        else:
            others = [d for d in found if not d["mine"] and d["eff"] >= max(20, best + 15)]
        sel = mine[:3] + others[:2]
    else:
        sel = found[:4]
    return {"t": item["t"], "q": q, "deals": sel, "total": len(found)}

# Categorías del súper para las ofertas destacadas (id de Carrefour, nombre corto)
TOP_CATS = [("Almacén", ["161"]), ("Desayuno y merienda", ["222"]), ("Bebidas", ["255"]),
            ("Lácteos y frescos", ["292"]), ("Carnes", ["321"]), ("Frutas y verduras", ["330"]),
            ("Panadería", ["336"]), ("Congelados", ["347"]), ("Limpieza", ["359"]),
            ("Perfumería", ["402/403", "402/412", "402/418", "402/422", "402/427", "402/435", "402/438", "402/443", "402/444"]),
            ("Bebés", ["451/452", "451/453", "451/458", "451/462"]),
            ("Mascotas", ["471/472", "471/474", "471/475"])]

def fetch_cat(path, order, n=50):
    url = f"{BASE}?fq=C:/{path}/&O={order}&_from=0&_to={n - 1}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def top_deals(per_cat=3, min_eff=25):
    out = []
    for cname, paths in TOP_CATS:
        seen, cands = set(), []
        n = 50 if len(paths) == 1 else 20
        for path in paths:
          for order in ("OrderByBestDiscountDESC", "OrderByTopSaleDESC"):
            try: prods = fetch_cat(path, order, n)
            except Exception: continue
            for rank, p in enumerate(prods):
                if p.get("productId") in seen: continue
                seen.add(p.get("productId"))
                d = analyze(p)
                if not d or d["eff"] < min_eff: continue
                # leve preferencia por lo más vendido a igual ahorro
                d["_k"] = d["eff"] + (8 if order == "OrderByTopSaleDESC" and rank < 20 else 0)
                cands.append(d)
        cands.sort(key=lambda d: -d["_k"])
        picks = []
        for d in cands:
            base = norm(d["n"]).split()[:2]
            if any(norm(x["n"]).split()[:2] == base for x in picks): continue   # no repetir el mismo producto en 3 tamaños
            d.pop("_k", None); picks.append(d)
            if len(picks) == per_cat: break
        if picks: out.append({"cat": cname, "items": picks})
    return out

# Otros súpers (misma plataforma que Carrefour). La prioridad sigue siendo Carrefour:
# "best" guarda, por producto, la mejor oferta entre todos los súpers (a igual ahorro gana Carrefour).
OTHERS = [("Día", "diaonline.supermercadosdia.com.ar", False), ("ChangoMás", "www.masonline.com.ar", False),
          ("Jumbo", "www.jumbo.com.ar", True), ("Disco", "www.disco.com.ar", True), ("Vea", "www.vea.com.ar", True),
          ("Coto", "www.coto.com.ar", "coto")]
_carrefour_fetch = fetch

def coto_promo(t):
    """Textos de Coto ('25%Dto', '70% 2da', '6x5') al formato que entiende clean_promo. '+10%' es extra para socios: se ignora."""
    t = (t or "").strip()
    if not t or t.startswith("+"): return ""
    m = re.match(r"(\d+)\s*%\s*2da", t, re.I)
    if m: return f"2do al {m.group(1)}%"
    m = re.match(r"(\d+)\s*%\s*dto", t, re.I)
    if m: return f"{m.group(1)}% off"
    return t

def coto_fetch(q, n=40):
    url = "https://www.coto.com.ar/sitios/cdigi/categoria?Ntt=" + urllib.parse.quote(q) + f"&Nrpp={n}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    recs = []
    def walk(o):
        if isinstance(o, dict):
            if "records" in o and "totalNumRecs" in o: recs.extend(o["records"] or []); return
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(data)
    return coto_records(recs)

def coto_records(recs):
    """Registros de Coto (Endeca) al mismo formato que los productos de VTEX."""
    prods = []
    for r in recs:
        try: a = r["records"][0]["attributes"]
        except Exception: continue
        g = lambda k: (a.get(k) or [""])[0]
        try: price = float(g("sku.activePrice"))
        except ValueError: continue
        teasers, lst = [], price
        try: dtos = json.loads(g("product.dtoDescuentos") or "[]")
        except ValueError: dtos = []
        for x in dtos:
            nm = coto_promo(x.get("textoDescuento"))
            if not nm: continue
            try: pd = float(x.get("precioDesc") or 0)
            except ValueError: pd = 0
            if nm.endswith("% off") and 0 < pd < price and lst == price:
                price = pd                     # descuento directo: se muestra el precio final
            else:
                teasers.append({"Name": nm})
        state = (r.get("detailsAction") or {}).get("recordState", "").split("?")[0]
        prods.append({"productName": g("sku.displayName") or g("product.displayName"), "brand": g("product.brand"),
                      "link": "https://www.coto.com.ar/productos" + state if state.startswith("/") else "",
                      "items": [{"sellers": [{"commertialOffer": {"IsAvailable": True, "Price": price, "ListPrice": lst,
                                                                   "PromotionTeasers": teasers}}]}]})
    return prods

def store_fetch(host, cenco):
    def f(q, n=40):
        url = f"https://{host}/api/catalog_system/pub/products/search?ft=" + urllib.parse.quote(q) + "&_from=0&_to=" + str(n - 1)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            prods = json.load(r)
        for p in prods:
            if not str(p.get("link", "")).startswith("https://"): p["link"] = f"https://{host}/{p.get('linkText', '')}/p"
            for it in p.get("items") or []:
                for s in it.get("sellers") or []:
                    o = s.get("commertialOffer") or {}
                    if cenco: o["ListPrice"] = o.get("PriceWithoutDiscount")   # en Jumbo/Disco/Vea el precio de lista viene inflado
        return prods
    return f

def best_across(items, carrefour):
    global fetch
    best = {}
    for it in items:
        for d in carrefour.get(it["t"], [])[:1]:
            best[it["t"]] = dict(d, s="Carrefour")
    for store, host, cenco in OTHERS:
        fetch = coto_fetch if cenco == "coto" else store_fetch(host, cenco)
        for it in items:
            try: r = deals_for(it)
            except Exception: continue
            for d in r["deals"][:1]:
                cur = best.get(it["t"])
                if not cur or d["eff"] > cur["eff"]: best[it["t"]] = dict(d, s=store)
    fetch = _carrefour_fetch
    return best

if __name__ == "__main__":
    items = json.load(open(sys.argv[1]))
    results = [deals_for(it) for it in items]
    out = {"checked": datetime.datetime.now(AR).strftime("%Y-%m-%d %H:%M"),
           "thursday": THURSDAY.isoformat(),
           "top": top_deals(),
           "days": sorted(d for d in DAY_PROMOS if d.startswith("Jueves")),
           "items": {r["t"]: r["deals"] for r in results if r["deals"]},
           "errors": [r["t"] for r in results if r.get("error")]}
    try: out["best"] = best_across(items, out["items"])
    except Exception: pass
    print(json.dumps(out, ensure_ascii=False))
