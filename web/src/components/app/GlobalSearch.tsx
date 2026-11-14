import { Package } from 'lucide-react'
import { useState } from 'react'
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
import { ACTIVOS } from '@/mocks/datos-ficticios'

// Buscador global (docs/08 §4.1, spec 001b T5): activos por código o nombre y
// saltos a pantallas. En la maqueta filtra datos ficticios en el cliente; con
// la API la búsqueda la resolverá el servidor, filtrada por tenant.

export function GlobalSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const [consulta, setConsulta] = useState('')

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
      <Command>
        <CommandInput
          placeholder="Código o nombre del activo…"
          value={consulta}
          onValueChange={setConsulta}
          aria-label="Buscar"
        />
        <CommandList className="max-h-[min(60dvh,24rem)]">
          <CommandEmpty>
            <span className="block truncate px-4">Sin resultados para «{consulta}»</span>
          </CommandEmpty>
          <CommandGroup heading="Activos">
            {ACTIVOS.map((activo) => (
              <CommandItem
                key={activo.codigo}
                value={`${activo.codigo} ${activo.nombre}`}
                onSelect={() => ir(`/admin/activos/${activo.codigo}`)}
                className="min-h-11 md:min-h-8"
              >
                <Package />
                <span className="min-w-0 flex-1 truncate">{activo.nombre}</span>
                <span className="font-mono text-xs text-muted-foreground">{activo.codigo}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Ir a">
            {ADMIN_NAV.flatMap((grupo) => grupo.items).map((item) => (
              <CommandItem
                key={item.ruta}
                value={`ir ${item.titulo}`}
                onSelect={() => ir(item.ruta)}
                className="min-h-11 md:min-h-8"
              >
                <item.icono />
                <span className="truncate">{item.titulo}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
