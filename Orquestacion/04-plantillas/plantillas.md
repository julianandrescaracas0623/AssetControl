# Plantillas

> Copiar, completar y borrar lo que no aplique. Una plantilla vacía no es documentación.

---

## 1. PRD de feature

```markdown
# PRD — <nombre>

## Problema
<Quién sufre qué, con evidencia.>

## Usuario
<Administrador / contador.>

## Resultado esperado
<Qué cambia en la operación, medible.>

## Alcance
- Incluye:
- No incluye:

## Requisitos (EARS)
1. Cuando <evento>, el sistema debe <comportamiento>.
2. ...

## Reglas de dominio
<Enlaces a docs/03; no redefinir.>

## Métrica de éxito
<Métrica, meta y ventana.>

## Riesgos
<Riesgo → mitigación.>

## Decisiones abiertas
- [ ] <pregunta> — dueño: <quién> — fecha límite: <fecha>
```

---

## 2. ADR

```markdown
# ADR-NNN: <título>

- **Estado:** Propuesta | Aceptada | Reemplazada por ADR-XXX
- **Fecha:** AAAA-MM-DD

## Contexto
<Problema y restricciones.>

## Decisión
<Qué se decide, en una o dos frases.>

## Alternativas consideradas
<Qué más se evaluó y por qué no.>

## Consecuencias
<Qué se gana, qué se paga, qué riesgos quedan.>
```

Un ADR aceptado no se edita; se reemplaza. Se añade a la tabla de `docs/adr/README.md`.

---

## 3. Runbook

```markdown
# Runbook — <operación>

## Cuándo se usa
<Disparador.>

## Requisitos
<Accesos, herramientas, permisos.>

## Pasos
1. ...

## Verificación
<Cómo se sabe que salió bien.>

## Reversa
<Cómo se deshace.>

## Última revisión
YYYY-MM-DD
```

---

## 4. Revisión de PR

```markdown
## Qué cambia
<Resumen en 2 líneas.>

## Por qué
<Tarea de tasks.md o issue.>

## Cómo se verificó
- [ ] `uv run pytest`
- [ ] `npm test`
- [ ] Capturas a 375 px y 1440 px
- [ ] Prueba de aislamiento entre tenants
- [ ] Total comparado con la suma de las partes (si toca informes)

## Riesgos
<Qué puede romper.>

## Pendiente
<Lo que queda fuera a propósito.>
```

---

## 5. Informe de incidente

```markdown
# Incidente — <fecha>

## Qué pasó
<Hechos, no interpretación.>

## Impacto
<Clínicas afectadas, datos, duración.>

## Causa
<Raíz técnica u operativa.>

## Detección
<Cómo se detectó y cuánto tardó.>

## Corrección
<Qué se hizo.>

## Prevención
<Prueba, alerta o cambio de proceso.>

## Estado
Abierto | Mitigado | Cerrado
```

---

## 6. Onboarding de una clínica

```markdown
# Onboarding — <clínica>

## Antes
- [ ] Responsable y administradores
- [ ] Lista de ubicaciones (sedes, salas, boxes)
- [ ] Categorías acordadas
- [ ] Stickers de código de barras comprados y pegados
- [ ] Teléfonos con navegador reciente y permiso de cámara probado

## Sesión (90 min)
1. Crear el tenant y el primer admin (script).
2. Cargar ubicaciones y categorías.
3. Dar de alta tres activos por escaneo; medir el tiempo.
4. Invitar a un contador con el enlace de un solo uso.
5. Abrir una sesión de conteo y verificar una sala completa.
6. Cerrar la sesión y revisar el informe.

## Después
- [ ] Primer conteo real acompañado
- [ ] Revisión a los 7 días

## Fricciones observadas
<...>
```

---

## 7. Guion de prueba del piloto

```markdown
# Guion de piloto — <fecha>

## Criterio 1 — Conteo
- [ ] Una sala completa verificada desde el teléfono, escaneando.
- [ ] Se cortó la red a mitad del conteo: la app avisó y el reintento no duplicó.

## Criterio 2 — Informe
- [ ] Total del informe = suma de los activos de la sesión (diferencia: $___).

## Criterio 3 — Historial
- [ ] Un activo muestra quién lo verificó y cuándo.

## Criterio 4 — Alta
- [ ] Alta de un activo por escaneo en ___ s (meta: < 30 s).

## Firma
Responsable de la clínica: ______  Fecha: ______
```
