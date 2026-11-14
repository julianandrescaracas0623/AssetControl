import { ChevronDown, Copy } from 'lucide-react'
import { useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { ACTIVOS, type ActivoFicticio } from '@/mocks/datos-ficticios'

// "Copiar de un parecido" (CU-CAT-03): copia categoría, nombre, marca, modelo,
// ubicación y precio. Para el contador el precio lo copia el servidor y no se
// muestra (P13). Lo usan el alta de administración y la de conteo.

export function CopiarDeParecido({ onCopiar, className }: { onCopiar: (a: ActivoFicticio) => void; className?: string }) {
  const [abierto, setAbierto] = useState(false)
  const [copiado, setCopiado] = useState<ActivoFicticio | null>(null)
  const etiquetaId = useId()
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span id={etiquetaId} className="text-sm font-medium">
        Copiar de un parecido <span className="font-normal text-muted-foreground">(opcional)</span>
      </span>
      <Popover open={abierto} onOpenChange={setAbierto}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={abierto} aria-labelledby={etiquetaId} className={cn('h-11 w-full justify-between border-input font-normal md:h-9', className)}>
            <span className="flex min-w-0 items-center gap-2">
              <Copy className="text-muted-foreground" aria-hidden="true" />
              <span className="truncate">
                {copiado ? `${copiado.nombre} · ${copiado.codigo}` : 'Busca un activo parecido para copiar sus datos'}
              </span>
            </span>
            <ChevronDown className="text-muted-foreground" aria-hidden="true" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-(--radix-popover-trigger-width) min-w-64 p-0" align="start">
          <Command label="Buscar activo parecido">
            <CommandInput placeholder="Nombre o código…" />
            <CommandList className="max-h-[min(50dvh,18rem)]">
              <CommandEmpty>Sin activos con ese nombre</CommandEmpty>
              <CommandGroup heading="Copia categoría, nombre, marca, modelo, ubicación y precio">
                {ACTIVOS.map((a) => (
                  <CommandItem
                    key={a.codigo}
                    value={`${a.nombre} ${a.codigo}`}
                    onSelect={() => {
                      setCopiado(a)
                      setAbierto(false)
                      onCopiar(a)
                    }}
                    className="min-h-11 md:min-h-8"
                  >
                    <span className="min-w-0 flex-1 truncate">{a.nombre}</span>
                    <span className="font-mono text-xs text-muted-foreground">{a.codigo}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}

