# Plan 001b — Sistema de diseño y app shell

> **Estado:** Aprobada (G1–G3, 2026-11-13) por el humano, con D1–D5 decididos según la recomendación. Fecha: 2026-11-13. Referencia visual: lienzo aprobado enlazado en el encabezado de `docs/08`.

## 1. Enfoque

Primero el tema (sin él nada se ve como el diseño), luego los componentes base de shadcn/ui con ese tema, el enrutado y los dos shells, después los componentes propios y al final las maquetas con datos ficticios. Todo vive en `web/`; **no hay cambios en backend, base de datos, migraciones, auth ni roles**. Cada tarea termina con pruebas en verde y, si tiene pantalla, capturas a 375 px y 1440 px.

## 2. Tema (`web/src/index.css`)

Se reemplazan las variables por defecto de shadcn (`baseColor` pasa de `neutral` a `zinc` en `components.json`) por las de `docs/08` §2.1:

| Variable | Valor | Variable | Valor |
|---|---|---|---|
| `--background`, `--card`, `--popover` | `#FFFFFF` | `--sidebar` | `#FAFAFA` |
| `--foreground` | `#09090B` | `--muted-foreground` | `#52525B` |
| `--muted`, `--accent`, `--secondary` | `#F4F4F5` | `--border` | `#E4E4E7` |
| `--input` | `#8A8A93` | `--primary` | `#18181B` |
| `--primary-foreground` | `#FAFAFA` | `--ring`, `--brand` | `#2B50E0` |
| `--brand-soft` / `--brand-border` / `--brand-strong` | `#EEF1FD` / `#C9D3FA` / `#2443C4` | `--destructive` | `#B91C1C` |
| `--success` (+ soft/border) | `#15803D` (`#F0FDF4` / `#BBF7D0`) | `--warning` (+ soft/border) | `#B45309` (`#FFFBEB` / `#FDE68A`) |
| `--radius` | `0.5rem` | `--font-sans` / `--font-mono` | Geist / Geist Mono con pila del sistema de respaldo |
| `--sidebar-accent` | `#F0F0F2` (hover y entrada activa de la barra lateral) | `--destructive-soft` / `--destructive-border` | `#FEF2F2` / `#FECACA` |

Variables propias (`--brand*`, `--success*`, `--warning*`) se exponen a Tailwind con `@theme inline` (`bg-success-soft`, `text-warning`, etc.). Las gráficas quedan para la spec 010: T1 retira las variables `--chart-*` de shadcn y la 010 debe volver a declararlas (en `:root` y en `@theme inline`) con colores del tema.

**Foco (R14):** el anillo se pinta opaco. La base usa `outline-ring` sin transparencia y, en T2, los componentes usan un anillo sólido de 2 px con 2 px de separación sobre `--background` (`ring-2 ring-ring ring-offset-2 ring-offset-background`), de modo que el par que cuenta es `--ring` sobre `--background` (6,3 : 1) incluso en el botón principal oscuro, donde el cobalto directo daría 2,81 : 1.

**Pares de contraste que prueba A2:** `foreground`/`background`, `muted-foreground`/`background`, `muted-foreground`/`sidebar`, `primary-foreground`/`primary`, `brand`/`background`, `brand-strong`/`brand-soft`, `success`/`success-soft`, `warning`/`warning-soft`, `destructive`/`background`, `input`/`background` (≥ 3 : 1).

## 3. Dependencias nuevas (requieren aprobación, D1)

| Paquete | Versión exacta | Para qué |
|---|---|---|
| `@fontsource-variable/geist` | 5.3.0 | Fuente de interfaz autoalojada |
| `@fontsource-variable/geist-mono` | 5.3.0 | Códigos de sticker |
| `react-router` | 8.5.1 | Rutas `/admin/**`, `/contar/**`, `/login` |
| `cmdk` | 1.1.1 | Componente `command` (buscador global, `LocationPicker`) |
| `sonner` | 2.0.8 | Componente `sonner` (avisos breves) |

Ya instaladas y suficientes: `radix-ui` 1.8.1, `lucide-react` 1.72.0, `class-variance-authority`, `tailwindcss`. Componentes shadcn que se añaden con `npx shadcn@4.23.0 add`: `sidebar`, `sheet`, `tooltip`, `separator`, `avatar`, `breadcrumb`, `dropdown-menu`, `input`, `label`, `select`, `textarea`, `dialog`, `alert-dialog`, `tabs`, `skeleton`, `alert`, `sonner`, `command`, `popover`, `table`, `checkbox`, `switch`, `progress`, `collapsible`. Si la CLI instala un paquete que no esté en esta tabla, la tarea se detiene y se pregunta. Versiones verificadas con `npm view` el 2026-11-13; se fijan sin `^` ni `~` y deben coincidir con `package-lock.json`.

Fuera de esta spec: `recharts` (010), `@tanstack/react-table` y `@tanstack/react-query` (primera pantalla con datos), `@zxing/*` (004), Playwright (spec del flujo de conteo).

## 4. Estructura de la web

```text
web/src/
├── index.css                 tema (único lugar con colores)
├── main.tsx                  router
├── routes/
│   ├── admin/                Inicio, Activos, RegistrarActivo, Informe (maquetas)
│   ├── contar/               Inicio, Escanear, EscribirCodigo, Verificar, Verificado, NoConfirmado, Alta
│   ├── Login.tsx             marcador para 002b
│   ├── SinPermiso.tsx, NoEncontrado.tsx
├── components/
│   ├── ui/                   shadcn (CLI, sin reescribir)
│   └── app/                  AdminShell, CountShell, NetworkStatus, StatCard, ThreeFiguresCard,
│                             LiveValueCard, AssetCard, LocationPicker, PendingList, EmptyState, GlobalSearch
├── mocks/datos-ficticios.ts  "Clínica Demo": activos, ubicaciones, sesiones (cifras que cuadran)
└── lib/format.ts             dinero es-CO (`Intl.NumberFormat`), fechas; solo presentación
```

- El rol simulado (`admin` | `contador`) y el estado de cada maqueta (cargando, vacío, error, éxito) se eligen con parámetros de la URL (`?rol=contador&estado=vacio`) para revisar sin tocar código.
- Banda "Datos ficticios" visible en todas las maquetas.
- `/health` se conserva como ruta de diagnóstico.

## 5. Anti-desborde (R12)

Reglas aprendidas en el lienzo, aplicadas en los componentes propios y en las clases de las maquetas: `min-w-0` en hijos flexibles y celdas de grid; texto de selectores y botones con `truncate`; tablas dentro de un contenedor con `overflow-x-auto` y texto que baja de línea salvo cifras y códigos (`whitespace-nowrap`); diálogos con `max-h-[calc(100dvh-2rem)]` y cuerpo con scroll propio; `sheet` inferior de conteo con lista desplazable y botón fijo; formularios móviles en una sola columna.

## 6. Permisos

No aplica: sin endpoints. Las rutas `/admin/**` solo esconden la navegación según el rol simulado; la autorización real llega con 002b (servidor). Ninguna maqueta muestra o recibe datos reales.

## 7. Pruebas

- **Vitest + Testing Library** (ya instalados): tema (A1, A2), shells (A4), buscador (A5), `NetworkStatus` (A6), tarjetas y precio por rol (A7), estados (A9).
- **Navegador real** (skill `browser-qa`): capturas a 375 px y 1440 px por pantalla, con modales y `sheet` abiertos; comprobación de `scrollWidth` (A8); Lighthouse para contraste y accesibilidad.
- CI: los flujos existentes de `ci-web.yml` (`lint`, `typecheck`, `test`, `build`) cubren esta spec sin cambios.

## 8. Orden y reversa

Orden de `tasks.md` (T1 → T10), una a la vez. Reversa: revertir los commits de la spec; no hay migraciones ni datos.

## 9. Alternativas descartadas

- **CSS propio como el del lienzo:** descartado; ADR-001 fija Tailwind + shadcn/ui y la hoja del lienzo era solo para la maqueta.
- **Fuente del sistema:** descartada por el diseño aprobado; la pila del sistema queda como respaldo en `--font-sans`.
- **Inter:** se evaluó junto a Geist; el diseño aprobado eligió Geist (y Geist Mono para códigos).
- **Fuente desde Google Fonts:** descartada; filtra visitas y depende de red externa (`docs/08` §2.3).
