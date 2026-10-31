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

## Etapas 2 y 3: la app (web/)

App web sin build: HTML + JavaScript con Firebase por CDN. Se publica en GitHub Pages junto con los precios:
`https://jpventura12.github.io/super-app/`

- Login con Google (Firebase Authentication).
- Listas en Firestore: cada lista tiene dueño y miembros. El dueño invita con un link que se manda por WhatsApp
  (vence a los 7 días); quien lo abre entra con Google y queda en la lista.
- Agregar, tachar, cantidad, buscador, borrar, sacar los tachados. Todo en tiempo real y con caché local
  (funciona sin señal y se sincroniza después).
- `web/config.js`: datos del proyecto de Firebase (no son secretos).
- `firebase/firestore.rules`: reglas de la base. Se pegan en la consola: Firestore Database → Reglas → Publicar.
  Tests en `firebase/test` (ver `firebase/README.md`).

Cada cambio en `web/` se publica solo: el workflow reusa los precios ya publicados y no vuelve a consultar los súpers.

## Próximas etapas

4. Comparación de precios, promos e historial de compras en la app nueva.
5. Mudanza desde las apps de Claude.
