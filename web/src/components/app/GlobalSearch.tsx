import { LoaderCircle, Package } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { ADMIN_NAV } from '@/components/app/admin-nav'
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { useBuscarActivos } from '@/lib/activos'

// Buscador global (docs/08 §4.1, spec 001b T5): activos por código, nombre o serial y
// saltos a pantallas. Desde la spec 004 los activos los busca el servidor (por tenant,
// 300 ms después de escribir); las pantallas se filtran aquí.

const sinTildes = (texto: string) => texto.normalize('NFD').replace(/\p{Mn}/gu, '').toLowerCase()

export function GlobalSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const [consulta, setConsulta] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => {
    const reloj = setTimeout(() => setQ(consulta.trim()), 300)
    return () => clearTimeout(reloj)
  }, [consulta])
  const busqueda = useBuscarActivos({ q }, open && q !== '')
  const activos = q ? (busqueda.data?.activos ?? []).slice(0, 8) : []
  const pantallas = ADMIN_NAV.flatMap((grupo) => grupo.items).filter(
    (item) => !consulta.trim() || sinTildes(item.titulo).includes(sinTildes(consulta.trim())),
  )
  const buscando = q !== consulta.trim() || (q !== '' && busqueda.isFetching)

  function ir(ruta: string) {
    onOpenChange(false)
    setConsulta('')
    navigate(ruta)
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Buscar"
      description="Busca un activo por código o nombre, o salta a una pantalla."
      className="max-w-[calc(100%-2rem)] sm:max-w-lg"
    >
      <Command label="Buscar activo o pantalla" shouldFilter={false}>
        <CommandInput
          placeholder="Código o nombre del activo…"
          value={consulta}
          onValueChange={setConsulta}
        />
        <CommandList className="max-h-[min(60dvh,24rem)]">
          {buscando && activos.length === 0 && pantallas.length === 0 ? (
            <div role="status" className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Buscando…
            </div>
          ) : (
            <CommandEmpty>
              <span className="block truncate px-4">Sin resultados para «{consulta}»</span>
            </CommandEmpty>
          )}
          {activos.length > 0 && (
          <CommandGroup heading="Activos">
            {activos.map((activo) => (
              <CommandItem
                key={activo.id}
                value={`activo ${activo.id}`}
                onSelect={() => ir(`/admin/activos/${encodeURIComponent(activo.codigo)}`)}
                className="min-h-control"
              >
                <Package />
                <span className="min-w-0 flex-1 truncate">{activo.nombre}</span>
                <span className="font-mono text-xs text-muted-foreground">{activo.codigo}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          )}
          {activos.length > 0 && pantallas.length > 0 && <CommandSeparator />}
          {pantallas.length > 0 && (
          <CommandGroup heading="Ir a">
            {pantallas.map((item) => (
              <CommandItem
                key={item.ruta}
                value={`ir ${item.titulo}`}
                onSelect={() => ir(item.ruta)}
                className="min-h-control"
              >
                <item.icono />
                <span className="truncate">{item.titulo}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
