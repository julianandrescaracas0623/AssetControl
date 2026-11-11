## Qué cambia y por qué

<!-- Una o dos frases. Tarea de tasks.md o issue: Closes #N -->

## Criterio de aceptación

<!-- Qué se puede comprobar para saber que está terminado -->

## Cómo se verificó

<!-- Comando + resultado, y capturas a 375 px y 1440 px si toca la web -->

## Definición de terminado

- [ ] Pruebas que fallarían sin este cambio
- [ ] CI en verde
- [ ] Toda consulta nueva pasa por el filtro central de tenant, con prueba de aislamiento
- [ ] Rol verificado en el endpoint, con prueba `admin` / `contador`
- [ ] Dinero con `Decimal`; si toca informes, el total se compara con la suma de las partes
- [ ] Migración reversible (si hay cambio de esquema)
- [ ] `docs/03-modelo-datos.md` y OpenAPI actualizados (si cambia el modelo o el contrato)
- [ ] ADR incluido (si hay decisión de arquitectura)
- [ ] Sin secretos ni datos reales de la clínica
- [ ] Sin atribución de asistentes en los commits

## Pendiente a propósito

<!-- Lo que queda fuera de este PR -->
