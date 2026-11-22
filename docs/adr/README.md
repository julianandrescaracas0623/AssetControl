# Decisiones de arquitectura (ADR)

| ADR | Título | Estado |
|---|---|---|
| [ADR-001](ADR-001-stack.md) | Stack: Flask, PostgreSQL, React con Tailwind y shadcn/ui | Propuesta |
| [ADR-002](ADR-002-solo-online-cliente-web.md) | MVP solo online, con un cliente web | Propuesta |
| [ADR-003](ADR-003-verificacion-con-snapshot.md) | Verificación con copia de precio y totales congelados al cierre | Propuesta |
| [ADR-004](ADR-004-arnes-local-y-autoria-humana.md) | Arnés local y autoría humana | Propuesta |

## Plantilla

```markdown
# ADR-NNN: Título

- **Estado:** Propuesta | Aceptada | Reemplazada por ADR-XXX
- **Fecha:** AAAA-MM-DD

## Contexto
Qué problema hay y qué restricciones existen.

## Decisión
Qué se decide, en una o dos frases claras.

## Alternativas consideradas
Qué más se evaluó y por qué no.

## Consecuencias
Qué se gana, qué se paga, qué riesgos quedan.
```

Un ADR aceptado no se edita. Si la decisión cambia, se escribe uno nuevo que lo reemplaza.
