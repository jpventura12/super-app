#!/usr/bin/env python3
"""Controla el catálogo recién armado antes de publicarlo.
Uso: python3 verificar.py SALIDA_DIR
Falla (código 1) si faltan archivos o hay pocos productos; avisa si un súper vino vacío."""
import json, os, sys

out = os.path.join(sys.argv[1] if len(sys.argv) > 1 else ".", "cat")
idx = json.load(open(os.path.join(out, "index.json"), encoding="utf8"))
faltan = [f"s{k:03d}.json" for k in range(idx.get("shards", 128)) if not os.path.exists(os.path.join(out, f"s{k:03d}.json"))]
total = idx.get("total", 0)
vacios = [s for s, n in (idx.get("counts") or {}).items() if not n]
print(f"Total: {total} productos · " + " · ".join(f"{s}: {n}" for s, n in idx["counts"].items()))
errores = []
if faltan: errores.append(f"faltan {len(faltan)} archivos ({', '.join(faltan[:5])}…)")
if total < 40000: errores.append(f"solo {total} productos (se esperan más de 40.000)")
if len(vacios) > 1: errores.append("vinieron vacíos: " + ", ".join(vacios))
if vacios and not errores:
    print(f"::warning::Vino vacío {vacios[0]}; se publica igual con el resto.")
if errores:
    for e in errores: print(f"::error::{e}")
    sys.exit(1)
