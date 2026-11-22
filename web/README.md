# web

Cliente web React responsive de AssetControl (Vite, TypeScript estricto, Tailwind CSS v4, shadcn/ui).

## Arranque

```sh
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b + vite build
npm run typecheck
```

La web llama a la API por `/api/*`; en desarrollo el proxy de Vite lo reenvía sin el prefijo (`/api/health` → `<API>/health`). El destino sale de `VITE_API_PROXY_TARGET` (en `web/.env.local`, ignorado por git); sin ella se usa `http://localhost:5000` (API de `docker compose up`).

## Probar la cámara en un teléfono (spec 004)

La cámara del navegador exige HTTPS (en el computador basta `localhost`). Para escanear stickers reales con un teléfono en la misma red wifi:

```sh
VITE_HTTPS=1 npm run dev     # en Windows (PowerShell): $env:VITE_HTTPS=1; npm run dev
```

Vite muestra una dirección `https://<ip-del-computador>:5173`. Ábrela en el teléfono, acepta el aviso del certificado de desarrollo (no es de confianza a propósito; solo sirve en tu red), inicia sesión y entra a **Contar → Escanear**. La API sigue detrás del proxy de Vite, así que el teléfono no necesita llegar al puerto 5000. Si el teléfono no carga la página, revisa que el firewall del computador permita el puerto 5173.

## shadcn/ui

Inicializado con la CLI fijada en `shadcn@4.23.0`:

```sh
npx shadcn@4.23.0 init -t vite -b radix -p nova --no-monorepo --yes
npx shadcn@4.23.0 add card badge
```

El preset `nova` instala la fuente Geist; se quitó (`@fontsource-variable/geist`) y se usa la fuente del sistema hasta aprobar la fuente de la marca (`docs/08-diseno-visual.md`).
