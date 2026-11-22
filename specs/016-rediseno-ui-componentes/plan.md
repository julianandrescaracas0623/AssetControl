# Plan 016 — Rediseño visual con biblioteca propia de componentes

## 1. Arquitectura

Solo web (`web/src`). Tres capas, de abajo hacia arriba:

```
index.css (tokens)  ->  components/ui (shadcn, intacto)  ->  components/kit (propio, genérico)
                                                          ->  components/app (dominio, usa kit)
                                                          ->  routes/** (pantallas, solo kit + app)
```

- **Tokens** en `web/src/index.css`: único archivo con literales. Se añaden variables semánticas (`--page`, `--ink`, `--control-h`, `--fila-h`, escala tipográfica) y se exponen a Tailwind con `@theme inline` (p. ej. `bg-page`, `text-titulo-pagina`, `h-control`).
- **Densidad por modo**: `--control-h` y `--fila-h` cambian con una clase de contexto (`data-densidad="conteo|admin"`) puesta por `CountShell` y `AdminShell`, y con el breakpoint `md`; un solo componente sirve a las dos densidades.
- **`components/ui/`** no se reescribe a mano (web-ui). Si un componente shadcn falta, se añade con `npx shadcn@latest add` solo si no arrastra dependencias nuevas; si las arrastra, queda como mejora futura.
- **`components/kit/`** (nuevo): un archivo por componente, `index.ts` que reexporta, pruebas junto al archivo, tipos estrictos, variantes con `class-variance-authority` (ya instalada).
- **`components/app/`**: se conserva la API pública de cada componente de dominio; por dentro compone `kit`. Los componentes que quedan sin consumidores se eliminan en T10.
- **Galería** `/dev/componentes` (ya existe): documenta kit completo en todos sus estados.
- **Guardia**: `web/src/components/kit/kit.node.test.ts` recorre `routes/**` y falla si importa `components/ui/*` fuera de una lista de excepciones (`EXCEPCIONES` con las pantallas aún no migradas; cada tarea de pantallas la reduce; T10 la deja vacía).

Sin cambios en `backend/`, `openapi.yaml`, `lib/api`, `package.json`, rutas ni claves de caché.

## 2. Tablas, endpoints, permisos, migraciones

- Tablas afectadas: ninguna. Endpoints: ninguno nuevo ni modificado. Permisos y roles: sin cambio (se siguen verificando en servidor; los guardas de ruta `RequiereAdmin`/`RequiereSesion` no se tocan). Migraciones: ninguna.
- Dependencias nuevas: ninguna (D5/D11 de la spec). Sin `shadcn add` que instale paquetes.

## 3. Tokens (valores decididos)

Contrastes calculados con la fórmula WCAG; la prueba de nodo de T1 los recalcula.

| Token | Valor | Uso | Contraste |
|---|---|---|---|
| `--page` | `#F6F6F7` | Fondo de página | texto `#09090B` ≈ 18:1 |
| `--background`/`--card`/`--popover` | `#FFFFFF` | Superficies y campos | — |
| `--foreground` | `#09090B` | Texto | 19:1 s/blanco |
| `--muted-foreground` | `#52525B` | Secundario | 7,7:1 s/blanco; ≈ 7:1 s/`--page` |
| `--primary` / `-foreground` | `#2B50E0` / `#FFFFFF` | Botón principal, selección fuerte | 6,3:1 |
| `--primary-hover` (= `--brand-strong`) | `#2443C4` | Hover/pulsado | 8,1:1 |
| `--ink` | `#18181B` | Botón fuerte, texto de cifras | 17:1 |
| `--brand-soft` / `--brand-border` | `#EEF1FD` / `#C9D3FA` | Info, ítem activo, selección | texto `--brand-strong` ≥ 7:1 |
| `--success`/`--warning`/`--destructive` | `#15803D`/`#B45309`/`#B91C1C` | Estado (texto e ícono) | ≥ 4,5:1 s/blanco y s/su fondo suave (se verifica en T1) |
| `--border` | `#E4E4E7` | Contornos decorativos | no exigido |
| `--input` | `#8A8A93` | Contorno de controles (siempre sobre blanco) | 3,4:1 |
| `--ring` | `#2B50E0` | Foco, anillo 2 px + 2 px | 6,3:1 |
| `--sidebar` | `#FFFFFF` | Barra lateral | — |
| `--radius` | `0.625rem` | Base | — |

Escala tipográfica (tokens `--text-*` en `@theme`; móvil / escritorio):

| Token | Móvil | Escritorio | Peso |
|---|---|---|---|
| `titulo-pagina` | 20 px | 24 px, `tracking-tight` | 600 |
| `titulo-seccion` | 16 px | 16 px | 600 |
| `cuerpo` | 16 px | 14 px | 400 |
| `etiqueta` | 14 px | 13 px | 500, `--muted-foreground` |
| `cifra` | 28 px | 30 px, `tabular-nums` | 600 |
| `codigo` | 18 px mono | 13 px mono | 500 |

Tamaños de imagen (D13, por defecto por indicación del humano): logo de empresa 160 × 64 px `object-contain`; logo en cabecera 32 px de alto, máx. 120 px de ancho; foto de ficha máx. 320 × 240 px (200 px de alto a 375 px), `object-cover`. Nota: T8/T9 los centralizan en constantes (o un `MarcoImagen` en `kit` con prop `variante: logo | logoCabecera | foto`) para no repetir clases; solo presentación, sin tocar el servidor.

Densidad: `--control-h` 48 px (conteo, admin < `md`) / 36 px (admin ≥ `md`); `--fila-h` 56 / 44 px; botón principal de conteo 56 px; separación entre objetivos ≥ 8 px.

## 4. Orden de migración y qué toca cada tarea

| Tarea | Familia | Pantallas / archivos principales |
|---|---|---|
| T1 | Tokens y base | `index.css`, pruebas de tema, galería (tokens) |
| T2 | Primitivos A | `kit/Boton, Campo, Insignia, Aviso, Estado` |
| T3 | Primitivos B | `kit/Panel, EncabezadoPagina, ListaDatos, Cifra, Dialogo, Confirmar, BarraAccion, Pestanas, Filtro, TablaDatos` |
| T4 | Shells y acceso | `AdminShell`, `CountShell`, `MenuCuenta`, `GlobalSearch`, `MarcoAcceso`, `Login`, `Invitacion`, `SinPermiso`, `SinConexion`, `NoEncontrado`, `PantallaCarga` |
| T5 | `/contar` lectura y captura | `contar/Inicio`, `Escanear`, `Escribir`, `Verificar`, `Pendientes`, `Historial`, `NetworkStatus`, `Escaner`, `AssetCard`, `PendingList`, `LineaDeTiempo` |
| T6 | `/contar` alta y escritorio | `contar/Alta`, `FormularioAlta`, `CampoFoto`, `CopiarDeParecido`, `InputSugerido`, `LocationPicker`, `contar/Escritorio` |
| T7 | `/admin` tablero e informe | `admin/Inicio`, `Valor`, `Informe`, `FigureCards`, `Barras`, `ActividadReciente` |
| T8 | `/admin` activos | `admin/Activos`, `FichaActivo`, `EditarActivo`, `AccionesActivo`, `FotoActivo`, `RegistrarActivo` |
| T9 | `/admin` gestión | `Sesiones`, `DetalleSesion`, `Discrepancias`, `Ubicaciones`, `Categorias`, `Usuarios`, `Empresa`, `Pendiente` |
| T10 | Pulido y cierre | borrar duplicados, excepciones vacías, galería final, axe global, 48 combinaciones, cambios de docs/08 |

Los nombres de archivo son probables, no vinculantes; el implementer confirma con `Glob`.

## 5. Estrategia de pruebas

- **Tests primero** por tarea: para cada componente del kit, pruebas de render por variante, estados (cargando/vacío/error con callback de reintento), teclado, `aria-*` y foco; para cada pantalla migrada, se escriben antes las pruebas de **caracterización** que falten (roles, nombres accesibles, foco, ausencia de precio para el contador) y se comprueba que pasan **contra la pantalla actual** antes de reescribirla. Luego se migra y deben seguir verdes sin cambio.
- Pruebas de nodo: `theme.node.test.ts` (ampliada: tokens nuevos, hex de 6 dígitos, contraste por cálculo, sin literales), `kit.node.test.ts` (guardia R7).
- axe-core en las pruebas ya existentes donde hay `axe`; si no está instalado en el repo no se añade (sin dependencias nuevas): la verificación axe se hace en el navegador real con la herramienta de que disponga el entorno y se anota el resultado; la prueba de contraste por cálculo cubre la parte de color.
- QA en navegador real (skill `browser-qa`): ruta, consola, red, captura a **375** y **1440 px**, caso feliz, vacío y error; el e2e Playwright existente (`npm run e2e`) se ejecuta al cierre de T5, T6 y T10.
- Definición de «terminado» por tarea: (1) pruebas nuevas primero y en verde; (2) `cd web && npm test` completa en verde (≥ 546); (3) `npm run lint` y `npm run typecheck` limpios; (4) capturas 375/1440 de cada pantalla tocada en `specs/016-rediseno-ui-componentes/capturas/`, consola limpia; (5) lista de excepciones de `kit.node.test.ts` reducida; (6) `git diff --stat` sin `backend/`, `docs/`, `lib/api/`, `package.json`; (7) revisión del `reviewer` (y `domain-guardian` en T5, T7 y T8 por cifras, precios y verificación; `security-reviewer` no aplica salvo que el reviewer detecte contacto con auth/roles).

## 6. Riesgos

Ver spec. Adicional: **tareas que crezcan** (T8, T9). Salida: separar con `/sdd-change`, no meter pantallas de más.

## 7. Alternativa descartada

**Instalar otra librería de componentes (Mantine, MUI, Ant) o `@tanstack/react-table`/`recharts` para el rediseño.** Descartada: ADR-001 y docs/08 fijan Tailwind + shadcn/ui, la petición prohíbe dependencias nuevas, y el valor está en la capa propia coherente, no en más paquetes. Segunda alternativa descartada: **reescribir `components/ui/` a mano** para cambiar el estilo; se rompe la convención de web-ui y dificulta actualizar shadcn: el estilo se cambia por tokens y por envoltorios en `kit`.
