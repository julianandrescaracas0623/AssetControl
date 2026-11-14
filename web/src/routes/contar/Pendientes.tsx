import { ChevronRight, ScanBarcode } from 'lucide-react'
import { Link } from 'react-router'

import { CountShell } from '@/components/app/CountShell'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useEnlace } from '@/lib/simulacion'
import { ACTIVOS, RESUMEN } from '@/mocks/datos-ficticios'

// Pendientes por ubicación (docs/08 §6.1, CU-VER-04): activos sin verificar
// en la sesión. Con la API, la lista la entrega el servidor por ubicación.

export default function Pendientes() {
  const enlace = useEnlace()
  const c = RESUMEN.conteoAbierto
  return (
    <CountShell
      titulo="Pendientes"
      subtitulo={`${c.pendientes} sin verificar`}
      volver={enlace('/contar')}
      estadoRed="en_linea"
      acciones={
        <Button asChild className="min-h-14 font-semibold">
          <Link to={enlace('/contar/escanear')}>
            <ScanBarcode className="size-5" />
            Escanear
          </Link>
        </Button>
      }
    >
      <h1 className="text-xl font-semibold tracking-tight">Pendientes</h1>
      <Tabs defaultValue={c.pendientesPorUbicacion[1].ubicacion} className="gap-2">
        <TabsList className="h-auto w-full justify-start overflow-x-auto bg-transparent p-0 [scrollbar-width:none]">
          {c.pendientesPorUbicacion.map((p) => (
            <TabsTrigger
              key={p.ubicacion}
              value={p.ubicacion}
              className="min-h-11 flex-none rounded-full border px-3.5 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
            >
              {p.ubicacion} · {p.pendientes}
            </TabsTrigger>
          ))}
        </TabsList>
        {c.pendientesPorUbicacion.map((p) => {
          const lista = ACTIVOS.filter((a) => a.conteo === 'pendiente' && a.ubicacion.startsWith(p.ubicacion))
          return (
            <TabsContent key={p.ubicacion} value={p.ubicacion}>
              <ul className="divide-y">
                {lista.map((a) => (
                  <li key={a.codigo}>
                    <Link to={enlace(`/contar/activo/${a.codigo}`)} className="flex min-h-16 items-center gap-3 py-2">
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium break-words">{a.nombre}</span>
                        <span className="text-sm text-muted-foreground">
                          <span className="font-mono">{a.codigo}</span> · {a.categoria}
                        </span>
                      </span>
                      <ChevronRight className="size-5 text-muted-foreground" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
              <p className="py-3 text-center text-sm text-muted-foreground">
                {lista.length < p.pendientes ? `y ${p.pendientes - lista.length} más en ${p.ubicacion} (maqueta)` : 'No quedan más pendientes aquí'}
              </p>
            </TabsContent>
          )
        })}
      </Tabs>
    </CountShell>
  )
}
