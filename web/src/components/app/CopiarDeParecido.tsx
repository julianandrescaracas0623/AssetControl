import { ChevronDown, Copy, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { type Activo, useBuscarActivos } from '@/lib/activos'
import { cn } from '@/lib/utils'

// "Copiar de un parecido" (CU-CAT-03): busca en los activos reales (spec 004) y copia
// categoría, nombre, marca, modelo, subtipo, ubicación y precio. Para el contador el
// precio lo copia el servidor y no se muestra (P13). Lo usan las dos altas.

function useRetrasado(valor: string, ms = 250): string {
  const [retrasado, setRetrasado] = useState(valor)
  useEffect(() => {
    const reloj = setTimeout(() => setRetrasado(valor), ms)
    return () => clearTimeout(reloj)
  }, [valor, ms])
  return retrasado
}

export function CopiarDeParecido({
  onCopiar,
  copiado,
  className,
}: {
  onCopiar: (a: Activo) => void
  copiado?: Activo | null
  className?: string
}) {
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const q = useRetrasado(texto.trim())
  const busqueda = useBuscarActivos({ q }, abierto)
  const etiquetaId = useId()
  const activos = busqueda.data?.activos ?? []

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span id={etiquetaId} className="text-sm font-medium">
        Copiar de un parecido <span className="font-normal text-muted-foreground">(opcional)</span>
      </span>
      <Popover open={abierto} onOpenChange={setAbierto}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={abierto} aria-labelledby={etiquetaId} className={cn('h-11 w-full justify-between border-input font-normal focus-visible:border-foreground focus-visible:ring-0 focus-visible:ring-offset-0 md:h-9', className)}>
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
          <Command label="Buscar activo parecido" shouldFilter={false}>
            <CommandInput placeholder="Nombre o código…" value={texto} onValueChange={setTexto} />
            <CommandList className="max-h-[min(50dvh,18rem)]">
              {busqueda.isFetching && activos.length === 0 ? (
                <div role="status" className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  Buscando…
                </div>
              ) : (
                <CommandEmpty>{busqueda.isError ? 'No se pudo buscar. Intenta de nuevo.' : 'Sin activos con ese nombre o código'}</CommandEmpty>
              )}
              {activos.length > 0 && (
                <CommandGroup heading="Copia categoría, nombre, marca, modelo, ubicación y precio">
                  {activos.map((a) => (
                    <CommandItem
                      key={a.id}
                      value={a.id}
                      onSelect={() => {
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
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}
