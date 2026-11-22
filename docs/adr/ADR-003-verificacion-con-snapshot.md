# ADR-003: Verificación con copia de precio y totales congelados al cierre

- **Estado:** Propuesta
- **Fecha:** 2026-11-09

## Contexto

Las sesiones cerradas son inmutables, pero el precio de un activo puede corregirse después. Si el informe de una sesión suma el precio *vigente*, el mismo informe cambia con el tiempo. El Excel actual ya mostró cómo un total que no coincide con la suma real destruye la confianza (diferencia de ~$4,8 M).

## Decisión

- Cada `verificacion` guarda `precio_al_contar` y `categoria_al_contar`, copiados del activo al momento de contar.
- Al **cerrar** una sesión se calculan y guardan `total_encontrado`, `total_no_encontrado` y `total_registrado` (reglas R3 y R4 de [03-modelo-datos.md](../03-modelo-datos.md)).
- El informe de una sesión lee esos valores. El valor "en tiempo real" es otra consulta, claramente rotulada.
- Para cada `(sesión, activo)` cuenta una verificación: la de mayor `seq`.

## Alternativas consideradas

- **Sumar el precio vigente al generar el informe:** simple, pero el informe no es reproducible.
- **Versionar el precio en una tabla de historial y consultar "precio a la fecha":** correcto pero más complejo; el snapshot por verificación da lo mismo para este caso.

## Consecuencias

- Un informe de sesión cerrada siempre da el mismo número.
- Hay duplicación deliberada de dos campos por verificación.
- El criterio de éxito 2 ("cero diferencias") se prueba como: `total_registrado` = suma de los activos verificados y no encontrados al cierre.
- Corregir un precio después del cierre no altera sesiones pasadas; queda en la línea de tiempo del activo.

## Actualización 2026-11-11 (autorizada por el humano)

- Al **cerrar** una sesión, el servidor también congela, en la misma transacción, el **desglose por categoría y por ubicación** (encontrado, no encontrado y total registrado en COP y en unidades), en la tabla `sesion_desglose` (regla R9 de [03-modelo-datos.md](../03-modelo-datos.md)).
- Razón: lo "no encontrado" no tiene verificación y, por tanto, no tiene snapshot de precio, categoría ni ubicación. Si el desglose se recalculara después, cambiaría al corregir un precio o una categoría, mover un activo o darlo de baja, y el informe dejaría de ser reproducible.
- El informe de sesión, su exportación y la evolución entre conteos del Inicio **leen** ese desglose congelado; no lo recalculan.
- En la misma transacción también se congela la **lista por activo de los no encontrados**, con su marca "en reparación", en la tabla `sesion_no_encontrado` (regla R9a de [03-modelo-datos.md](../03-modelo-datos.md)); el informe de sesión y su exportación la leen y no la reconstruyen.
- La prueba de "cero diferencias" se amplía: para cada dimensión, la suma de sus filas es igual a las tres cifras congeladas de la sesión.
- Esta nota no cambia el estado del ADR ni el resto de la decisión.
