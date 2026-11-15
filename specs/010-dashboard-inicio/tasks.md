# Tasks 010 — Dashboard (Inicio)

> **Estado:** Aprobadas (G1–G3, 2026-11-15). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | `GET /inicio` (indicadores por rol); contrato; pruebas de cifras, vacíos, roles, tenant y respuesta del contador sin dinero | backend: `pytest`, `ruff`; web `api:types` | aprobación |
| T2 | `GET /inicio/actividad` (filtro de precio común con el historial); contrato; pruebas | igual que T1 | aprobación |
| T3 | `GET /inicio/evolucion` (máx. 12, % en unidades); contrato; igualdad punto a punto con el informe | igual que T1 | aprobación |
| T4 | Web: gráficas de barras accesibles (Q1) | web: `test`, `lint`, `typecheck`, `build` | aprobación |
| T5 | Web: indicadores y último informe reales en `/admin`, fallas aisladas | igual que T4 | T1 |
| T6 | Web: gráficas por categoría y ubicación y evolución en `/admin` | igual que T4 | T3, T4 |
| T7 | Web: actividad reciente (admin y contador) | igual que T4 | T2 |
| T8 | Web: Inicio del contador (Q3) | igual que T4 | T1, T7 |
| T9 | Navegador real, revisión de seguridad y de dominio | skill `browser-qa` | T5–T8 |

## Notas por tarea
- **T1 (hecha, 2026-11-15):** `GET /inicio` (blueprint `inicio`, ambos roles) en `app/inicio/indicadores.py`, reutilizando lo que ya calcula cada cifra: activos hoy (`activo` + `en_reparacion`) y sesión abierta con su avance (`service.avance`, % en texto con un decimal); solo admin: valor actual (`valor.valor_actual`), discrepancias por resolver (`discrepancias.listar`) y dañados o en reparación de la **sesión de referencia** (la abierta o, sin ella, la última cerrada; P26: en reparación ∪ `estado_fisico=danado` en la verificación vigente, sin dados de baja, con la sesión nombrada) y el último informe (`cierre.informe`: sesión y tres cifras). Para el contador esas claves no existen. Contrato `Inicio`, `RefSesion`, `Porcentaje`; roles. `test_inicio_api.py` (4): tenant vacío, cifras exactas con y sin sesión abierta (último informe = informe del cierre), contador sin dinero (barrido de `precio|valor|total_|registrado|0.00`), tenant y 401.
- **T2 (hecha, 2026-11-15):** `GET /inicio/actividad` (ambos roles, 20 por página, cursor `antes_de`). El historial (005) se partió en `_pagina` (filtro de `precio_cambiado` en la consulta para el contador, cursor por `seq`, autores del tenant) y `_evento` (sin claves de precio para el contador), que comparten `leer` (un activo) y el nuevo `leer_tenant` (todo el tenant, con `activo {id, codigo, nombre}`). Contrato `Actividad`/`EventoActividad`; roles. `test_inicio_actividad.py` (4): orden por `seq`, activo y autor, contador sin `precio_cambiado` ni la palabra «precio», páginas de 20, cursor inválido `400`, tenant y 401; el historial sigue en verde.
