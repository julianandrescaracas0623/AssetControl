import { Link, Route, Routes } from 'react-router'

import { EncabezadoPagina, Panel } from '@/components/kit'

// Módulo de prueba de la consola (spec 017, T8; R13): demuestra que un módulo nuevo es
// solo una entrada del registro (modulos.ts) y esta carpeta; el shell no cambia. Solo en
// desarrollo y pruebas: no entra en el build de producción y el servidor real no lo declara.

function Inicio() {
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Módulo de prueba"
        descripcion="Pantalla de ejemplo para comprobar el registro de módulos. No trae datos."
      />
      <Panel titulo="Cómo se añade un módulo">
        <ol className="flex list-decimal flex-col gap-2 pl-5 text-cuerpo">
          <li>Registrar su entrada en el servidor (registro de módulos de la API).</li>
          <li>Registrar su entrada en la web (modulos.ts) con su carpeta.</li>
          <li>El menú y la ruta aparecen solos; el shell no se toca.</li>
        </ol>
        <p className="mt-4 text-cuerpo">
          <Link
            to="detalle"
            className="inline-flex min-h-11 items-center rounded-sm font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring md:min-h-0"
          >
            Abrir una subruta del módulo
          </Link>
        </p>
      </Panel>
    </div>
  )
}

function Detalle() {
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Detalle de prueba"
        migas={[{ etiqueta: 'Módulo de prueba', href: '/plataforma/prueba' }, { etiqueta: 'Detalle' }]}
      />
      <p className="text-cuerpo">Subruta del módulo de prueba</p>
    </div>
  )
}

export default function Prueba() {
  return (
    <Routes>
      <Route index element={<Inicio />} />
      <Route path="detalle" element={<Detalle />} />
    </Routes>
  )
}
