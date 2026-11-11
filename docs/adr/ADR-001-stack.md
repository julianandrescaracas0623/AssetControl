# ADR-001: Stack: Flask, PostgreSQL, React con Tailwind y shadcn/ui

- **Estado:** Propuesta
- **Fecha:** 2026-11-09

## Contexto

Sistema pequeño (una clínica, cientos de activos, pocos usuarios), mantenido por un equipo reducido, multi-tenant desde el inicio. Se trabajará con Tailwind CSS y shadcn/ui.

## Decisión

- **Cliente:** una aplicación web, React + TypeScript + Vite, Tailwind CSS, shadcn/ui y TanStack Query. Escaneo con una librería basada en ZXing sobre la cámara del navegador.
- **Backend:** Python + Flask, SQLAlchemy y Alembic. Un solo servicio (monolito modular).
- **Base de datos:** PostgreSQL alojado en Supabase (solo como infraestructura administrada), esquema compartido con `tenant_id`. Sin Supabase Auth ni su API automática; Flask es el único acceso a los datos.
- **Fotos:** almacenamiento de objetos compatible con S3, alojado en Supabase Storage (mismas condiciones: solo infraestructura; el acceso lo hace Flask).
- **Contrato:** OpenAPI publicado por el backend; tipos TypeScript generados desde ahí.
- **CI/CD:** GitHub Actions.

## Alternativas consideradas

- **App móvil con Expo:** mejor escaneo y base para offline, pero exige builds, distribución (en iOS, cuenta Apple de USD 99/año y TestFlight) y un segundo cliente. shadcn/ui no aplica. Se descarta para el MVP; ver [ADR-002](ADR-002-solo-online-cliente-web.md).
- **Microservicios / colas (Celery):** innecesarios a este volumen; la importación y los PDF se generan de forma síncrona.
- **Plantillas Jinja + HTMX:** menos piezas, pero se decidió Tailwind + shadcn/ui y habrá interacciones ricas (edición en línea de la revisión de importación).
- **Base por tenant:** más aislamiento, mucha más operación. No se justifica con un cliente.

## Consecuencias

- Un solo cliente que mantener y desplegar; sin tiendas de aplicaciones.
- Requiere HTTPS en todos los entornos por el acceso a la cámara.
- La versión mayor de PostgreSQL local (Docker) debe coincidir con la de Supabase `[PENDIENTE: confirmar versión]`.
- El aislamiento entre tenants depende del código: filtro centralizado y prueba por endpoint. Postgres RLS queda como defensa adicional opcional.
