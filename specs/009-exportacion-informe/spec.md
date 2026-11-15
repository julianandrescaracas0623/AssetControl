# Spec 009 — Exportar el informe a Excel y PDF

> **Estado:** Implementada (T1–T5, 2026-11-15). Aprobada (G1–G3, 2026-11-15) con Q1–Q3 en la opción recomendada. Depende de la 008 (cierre e informe, hecha). Módulo M7 (CU-INF-03) de `docs/07`. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

El informe congelado ya se ve en pantalla, pero la clínica lo necesita fuera de AssetControl: para archivarlo, enviarlo a contabilidad o imprimirlo. Hoy eso obliga a copiar cifras a mano a un Excel, que es justo donde nacieron las diferencias del Excel original (~$4,8 M). Esta spec genera en el servidor un Excel y un PDF del informe de una sesión cerrada con **exactamente** las mismas cifras que la pantalla, leídas de lo congelado al cierre.

## Usuarios

- **Admin:** descarga el informe de una sesión cerrada en Excel o PDF.
- **Contador:** no exporta (P5, P13); el servidor responde `403`.

## Alcance

- Dentro: `GET /sesiones/{id}/informe/excel` y `GET /sesiones/{id}/informe/pdf` (solo admin, solo sesiones cerradas) y los botones «Exportar Excel» y «Exportar PDF» en la pantalla del informe.
- Fuera: exportar el valor actual, exportar sesiones abiertas o el avance, enviar por correo, plantillas personalizables, logo de la clínica, firma digital.

## Requisitos (EARS)

1. **R1 Misma fuente (R8 de `docs/03`).** Cuando el admin pida un archivo, el sistema debe generarlo a partir del mismo informe que devuelve `GET /sesiones/{id}/informe` (la función `cierre.informe`), sin recalcular ni volver a leer `activo`, `verificacion` o el universo U.
2. **R2 Contenido.** Cada archivo debe traer: nombre de la sesión, fecha de corte, quién y cuándo cerró, «Informe congelado», las tres cifras con sus unidades y el % de unidades encontradas; el desglose por categoría y por ubicación (encontrado, no encontrado y total registrado en COP y unidades, % encontrado y la fila de total); y la lista de no encontrados (código, activo, categoría, ubicación esperada, marca «En reparación» y precio, con su total).
3. **R3 Igualdad (C2).** Cada cifra exportada debe ser idéntica, al centavo, a la del informe en JSON; el formato visible en COP debe coincidir con el de la pantalla (`$ 1.390.000,50`).
4. **R4 Sin datos.** Si la sesión se cerró sin activos, el archivo debe generarse con ceros y tablas vacías, no con error (CU-INF-03).
5. **R5 Errores.** Una sesión abierta debe responder `409 sesion_abierta`; una inexistente o de otro tenant, `404`; el contador, `403`.
6. **R6 Descarga segura.** La respuesta debe llevar el tipo correcto, `Content-Disposition: attachment` con un nombre de archivo seguro (sin la sesión ni datos de la clínica en la URL), `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`. Ningún texto del informe debe interpretarse como fórmula en Excel (inyección CSV/fórmulas). Los registros del servidor no deben contener cifras ni nombres del informe.
7. **R7 Web.** En el informe, «Exportar Excel» y «Exportar PDF» deben descargar el archivo con el nombre que manda el servidor, mostrar que está en curso y explicar el error si falla; la web no arma el archivo ni suma.

## Criterios de aceptación

- A1: pruebas de API: los dos formatos de una sesión con encontrados, no encontrados (con y sin «en reparación») y varias categorías y ubicaciones; las cifras leídas del archivo (Excel con un lector independiente, PDF extrayendo su texto) son iguales a las del JSON del informe; sesión en ceros; abierta `409`; inexistente y de otro tenant `404`; contador `403`; cabeceras de R6; un nombre que empieza por `=` queda como texto en Excel.
- A2: el informe exportado no cambia si después se corrige un precio, se mueve un activo o se renombra una categoría (lee lo congelado).
- A3: contrato OpenAPI de los dos endpoints (respuesta binaria con su tipo y errores JSON) ejercitado.
- A4: navegador real (1440 y 375 px): descargar los dos archivos desde el informe; abrirlos y comprobar que las tres cifras coinciden con la pantalla; error visible si falla; axe 0 y consola limpia.

## Decisiones ya tomadas

R8 (una sola fuente de cálculo), R9 y R9a (desglose y lista congelados), ADR-003, P5 y P13 (solo admin; precios solo admin), CU-INF-03 (el servidor genera el archivo; sin datos → ceros). Dinero en `NUMERIC(14,2)`/`Decimal`/texto, nunca `float` en el cálculo. Dependencias nuevas solo las que apruebe G1, con versión fijada.

## Riesgos

- **Dos formatos que divergen de la pantalla:** los dos archivos se arman de un mismo «documento» intermedio construido desde `cierre.informe`; las pruebas comparan contra el JSON.
- **Excel muestra números en coma flotante:** en el XML del `.xlsx` el número se escribe desde el `Decimal` exacto; Excel lo muestra con dos decimales. Con montos de hasta `NUMERIC(14,2)` la representación es exacta a la vista (≤ 15 dígitos significativos).
- **Caracteres fuera de Latin-1 en el PDF** (nombres en otros alfabetos): las fuentes estándar del PDF no los dibujan. Para una clínica en Colombia es improbable; se reemplazan por «?» y se anota. Incrustar una fuente Unicode sería otra dependencia.
- **Informes grandes:** ~300 activos son unas pocas páginas; se genera en memoria.

## Decisiones de G1 (humano, 2026-11-15)

| Pregunta | Decisión |
|---|---|
| Q1 Librerías | `xlsxwriter==3.3.1` y `reportlab==5.1.0` en producción; `openpyxl==3.1.5` y `pypdf==7.1.0` solo en pruebas. |
| Q2 Dinero en el Excel | Números con formato COP y dos decimales, sin fórmulas. |
| Q3 Papel del PDF | Carta horizontal. |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 Librerías | A: `XlsxWriter` (Excel, sin dependencias) y `reportlab` (PDF) en producción; `openpyxl` y `pypdf` solo en pruebas, como lectores independientes. B: `openpyxl` para escribir y leer el Excel y `reportlab` para el PDF; `pypdf` en pruebas. C: generar los archivos en el navegador. | **A.** XlsxWriter está mantenido y no arrastra nada; reportlab es el estándar en Python para PDF. Leer con otra librería prueba la igualdad sin confiar en quien escribió. C contradice CU-INF-03 (lo genera el servidor). |
| Q2 Dinero en el Excel | A: números con formato COP y dos decimales, sin fórmulas (los totales son los del servidor). B: texto exacto. C: números con fórmulas `SUMA` en los totales. | **A.** Contabilidad puede ordenar y sumar; los totales siguen siendo los del cierre. C recalcularía fuera del servidor (R8). |
| Q3 Papel del PDF | A: Carta horizontal. B: Carta vertical. C: A4 horizontal. | **A.** Carta es el tamaño común en Colombia; horizontal hace caber las 8 columnas del desglose sin cortar. |
