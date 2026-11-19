import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { Insignia, ListaDatos, Panel } from '@/components/kit'
import { formatCOP } from '@/lib/format'
import type { Rol } from '@/lib/api/cliente'
import type { EstadoActivo } from '@/mocks/datos-ficticios'

// Tarjeta del activo (docs/08 §3.2). El precio solo existe para el admin
// (P13): para el contador no hay fila, hueco ni marcador. Es presentación; el
// servidor no envía el precio al contador.
// Spec 016, T5: título con la escala nombrada, código en mono, categoría y estado como
// insignias del kit, y los datos en un Panel con ListaDatos (que no pinta lo ausente).

export interface ActivoTarjeta {
  codigo: string
  nombre: string
  categoria: string
  ubicacion: string
  estado: EstadoActivo
  precio?: string
}

export function AssetCard({ activo, rol, titulo: Titulo = 'h2' }: { activo: ActivoTarjeta; rol: Rol; titulo?: 'h1' | 'h2' }) {
  const verPrecio = rol === 'admin' && activo.precio !== undefined
  return (
    <article className="flex min-w-0 flex-col gap-3">
      <div className="flex min-w-0 flex-col gap-2">
        <Titulo className="text-titulo-pagina break-words">{activo.nombre}</Titulo>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border bg-card px-2 py-0.5 font-mono text-codigo">{activo.codigo}</span>
          <Insignia tono="neutro">{activo.categoria}</Insignia>
          <EstadoActivoBadge estado={activo.estado} />
        </div>
      </div>
      <Panel relleno={false} className="px-4">
        <ListaDatos
          datos={[
            { rotulo: 'Ubicación esperada', valor: <span className="block truncate font-medium">{activo.ubicacion}</span> },
            verPrecio && { rotulo: 'Precio de referencia', valor: formatCOP(activo.precio!), tipo: 'cifra' },
          ]}
        />
      </Panel>
    </article>
  )
}
