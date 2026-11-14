import { Check, ChevronsUpDown, MapPin } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { UBICACIONES, rutaUbicacion } from '@/mocks/datos-ficticios'

// Selector jerárquico sede › sala › box con "Última usada" arriba (docs/08
// §3.2). Lista cerrada: cero digitación, solo se escribe para filtrar.
export function LocationPicker({
  id,
  valor,
  ultimaUsada,
  onChange,
  className,
}: {
  id?: string
  valor?: string
  ultimaUsada?: string
  onChange: (id: string) => void
  className?: string
}) {
  const [abierto, setAbierto] = useState(false)
  const opciones = UBICACIONES.filter((u) => u.tipo !== 'sede')

  function elegir(nuevo: string) {
    onChange(nuevo)
    setAbierto(false)
  }

  function opcion(ubicacionId: string, sangria = true) {
    const u = UBICACIONES.find((x) => x.id === ubicacionId)!
    return (
      <CommandItem key={u.id} value={`${u.id} ${rutaUbicacion(u.id)}`} onSelect={() => elegir(u.id)} className="min-h-11 md:min-h-8">
        <span className={cn('min-w-0 flex-1 truncate', sangria && u.tipo === 'box' && 'pl-4')}>{rutaUbicacion(u.id)}</span>
        {valor === u.id && <Check className="text-brand" aria-hidden="true" />}
      </CommandItem>
    )
  }

  return (
    <Popover open={abierto} onOpenChange={setAbierto}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={abierto}
          className={cn('h-11 w-full justify-between border-input font-normal md:h-9', className)}
        >
          <span className="flex min-w-0 items-center gap-2">
            <MapPin className="text-muted-foreground" aria-hidden="true" />
            <span className="truncate">{valor ? rutaUbicacion(valor) : 'Elige una ubicación'}</span>
          </span>
          <ChevronsUpDown className="text-muted-foreground" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) min-w-64 p-0" align="start">
        <Command label="Buscar ubicación">
          <CommandInput placeholder="Buscar sala o box…" />
          <CommandList className="max-h-[min(50dvh,18rem)]">
            <CommandEmpty>Sin ubicaciones con ese nombre</CommandEmpty>
            {ultimaUsada && (
              <CommandGroup heading="Última usada">
                {opcion(ultimaUsada, false)}
              </CommandGroup>
            )}
            <CommandGroup heading="Sede Principal">
              {opciones
                .filter((u) => u.id !== ultimaUsada)
                .map((u) => opcion(u.id))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
