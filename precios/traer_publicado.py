#!/usr/bin/env python3
"""Baja el catálogo que ya está publicado en GitHub Pages (para republicar la app sin volver a consultar los súpers).
Uso: python3 traer_publicado.py URL_BASE SALIDA_DIR
Sale con código 1 si no lo encuentra completo."""
import json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

base, out = sys.argv[1].rstrip("/"), os.path.join(sys.argv[2], "cat")
os.makedirs(out, exist_ok=True)

def get(path):
    with urllib.request.urlopen(f"{base}/cat/{path}", timeout=60) as r:
        data = r.read()
    with open(os.path.join(out, path), "wb") as f:
        f.write(data)
    return data

try:
    idx = json.loads(get("index.json"))
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(get, [f"s{k:03d}.json" for k in range(idx.get("shards", 128))]))
except Exception as e:
    print(f"No se pudo bajar el catálogo publicado: {e}")
    sys.exit(1)
print(f"Catálogo publicado del {idx.get('checked')}: {idx.get('total')} productos")
