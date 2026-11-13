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

## shadcn/ui

Inicializado con la CLI fijada en `shadcn@4.23.0`:

```sh
npx shadcn@4.23.0 init -t vite -b radix -p nova --no-monorepo --yes
npx shadcn@4.23.0 add card badge
```

El preset `nova` instala la fuente Geist; se quitó (`@fontsource-variable/geist`) y se usa la fuente del sistema hasta aprobar la fuente de la marca (`docs/08-diseno-visual.md`).
