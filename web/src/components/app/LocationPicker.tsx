import { Check, ChevronsUpDown, MapPin } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { Ubicacion } from '@/lib/api/cliente'
import { opcionesDeSelector, rutaDe } from '@/lib/catalogo'
import { cn } from '@/lib/utils'

// Selector jerárquico sede › sala › box con "Última usada" arriba (docs/08
// §3.2). Lista cerrada: cero digitación, solo se escribe para filtrar. Recibe las
// ubicaciones por prop (spec 003, T7): las de la API o, en maquetas, las ficticias.
// Se eligen salas y boxes activos, agrupados por su sede.
export function LocationPicker({
  id,
  ubicaciones,
  valor,
  ultimaUsada,
  onChange,
  className,
  cargando = false,
  etiqueta: vacio = 'Elige una ubicación',
  nombre,
}: {
  id?: string
  ubicaciones: Ubicacion[]
  valor?: string
  ultimaUsada?: string
  onChange: (id: string) => void
  className?: string
  cargando?: boolean
  /** Texto del botón sin nada elegido. */
  etiqueta?: string
  /** Nombre accesible cuando no hay un <Label> asociado. */
  nombre?: string
}) {
  const [abierto, setAbierto] = useState(false)
  const grupos = opcionesDeSelector(ubicaciones)
  const ultima = ultimaUsada ? ubicaciones.find((u) => u.id === ultimaUsada && u.activa && u.tipo !== 'sede') : undefined

  function elegir(nuevo: string) {
    onChange(nuevo)
    setAbierto(false)
  }

  function opcion(u: Ubicacion, sangria = true) {
    const ruta = rutaDe(ubicaciones, u.id)
    return (
      <CommandItem key={u.id} value={`${u.id} ${ruta}`} onSelect={() => elegir(u.id)} className="min-h-11 md:min-h-8">
        <span className={cn('min-w-0 flex-1 truncate', sangria && u.tipo === 'box' && 'pl-4')}>{ruta}</span>
        {valor === u.id && <Check className="text-brand" aria-hidden="true" />}
      </CommandItem>
    )
  }

  const etiqueta = cargando ? 'Cargando ubicaciones…' : valor ? rutaDe(ubicaciones, valor) || vacio : vacio

  return (
    <Popover open={abierto} onOpenChange={setAbierto}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={abierto}
          aria-label={nombre}
          disabled={cargando}
          className={cn('h-11 w-full justify-between border-input font-normal focus-visible:border-foreground focus-visible:ring-0 focus-visible:ring-offset-0 md:h-9', className)}
        >
          <span className="flex min-w-0 items-center gap-2">
            <MapPin className="text-muted-foreground" aria-hidden="true" />
            <span className="truncate">{etiqueta}</span>
          </span>
          <ChevronsUpDown className="text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-64 p-0" align="start">
        <Command label="Buscar ubicación">
          <CommandInput placeholder="Buscar sala o box…" />
          <CommandList className="max-h-[min(50dvh,18rem)]">
            <CommandEmpty>Sin ubicaciones con ese nombre</CommandEmpty>
            {ultima && <CommandGroup heading="Última usada">{opcion(ultima, false)}</CommandGroup>}
            {grupos.map(({ sede, opciones }) => (
              <CommandGroup key={sede.id} heading={sede.nombre}>
                {opciones.filter((u) => u.id !== ultima?.id).map((u) => opcion(u))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
