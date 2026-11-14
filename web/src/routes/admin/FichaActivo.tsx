import { SearchX } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { ACTIVOS } from '@/mocks/datos-ficticios'

// Ficha mínima del activo (destino del buscador). La ficha completa, con
// historial y edición, llega con la spec 005.
export default function FichaActivo() {
  const { codigo } = useParams()
  const activo = ACTIVOS.find((a) => a.codigo === codigo)
  if (!activo) {
    return (
      <div className="flex flex-col items-start gap-3">
        <span className="flex size-10 items-center justify-center rounded-lg bg-muted" aria-hidden="true">
          <SearchX className="size-5" />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight">No encontramos ese código</h1>
        <p className="text-sm text-muted-foreground">
          El código <span className="font-mono">{codigo}</span> no existe en esta clínica.
        </p>
        <Button asChild variant="outline">
          <Link to="/admin/activos">Ver activos</Link>
        </Button>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold tracking-tight">{activo.nombre}</h1>
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span className="rounded bg-muted px-2 py-0.5 font-mono text-foreground">{activo.codigo}</span>
        <span>{activo.categoria}</span>
        <span aria-hidden="true">·</span>
        <span>{activo.ubicacion}</span>
      </p>
      <p className="text-sm text-muted-foreground">La ficha completa, con historial y edición, llega con la spec 005.</p>
    </div>
  )
}
