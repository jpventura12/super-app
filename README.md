# App del súper

App de listas del súper con comparación de precios de Carrefour, Día, ChangoMás, Coto, Jumbo, Disco y Vea.

## Etapa 1: precios (este repo, hoy)

Todas las madrugadas, GitHub Actions baja los catálogos de los 7 súpers y publica los archivos en GitHub Pages:

- `cat/index.json`: súpers, cantidad de productos, fecha de actualización.
- `cat/s000.json` … `cat/s127.json`: los productos, partidos por palabra para que cada celular baje solo lo que necesita.
- `bancos.json`: promos bancarias (se editan a mano en `datos/bancos.json`).

Cada producto es una fila: `[súper, nombre, precio, precio_lista, etiqueta, ahorro%, promo, link, precio_efectivo_1u, cantidad, unidad]`.
El link se guarda sin dominio; el dominio de cada súper está en `index.json` → `hosts`.

### Puesta en marcha

1. Crear el repo en GitHub (público, para que Actions y Pages sean gratis) y subir estos archivos.
2. En el repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. En **Actions → Precios del súper → Run workflow**, correrlo a mano la primera vez (tarda entre 6 y 10 minutos).
4. Cuando termine en verde, abrir `https://<usuario>.github.io/<repo>/cat/index.json`: tiene que mostrar los 7 súpers con miles de productos cada uno.

Si un súper viene en 0 o el paso **Verificar** falla, es probable que ese súper bloquee las consultas desde los servidores de GitHub.

## Próximas etapas

2. Proyecto Firebase y login con Google.
3. Listas compartidas con invitación por link de WhatsApp.
4. Comparación de precios, promos e historial de compras en la app nueva.
5. Mudanza desde las apps de Claude.
