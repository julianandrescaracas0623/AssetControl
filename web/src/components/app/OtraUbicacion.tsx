import { ArrowLeftRight, Check } from 'lucide-react'
import type { RefObject } from 'react'

import { Aviso, Dialogo } from '@/components/kit'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import type { Ubicacion } from '@/lib/api/cliente'
import { opcionesDeSelector, rutaDe } from '@/lib/catalogo'
import { cn } from '@/lib/utils'

// «¿Dónde lo encontraste?» (spec 006, T7; R6). Elegir otra ubicación cambia solo esta
// verificación: es una observación y el activo no se mueve hasta que el admin aplique
// la discrepancia. Spec 016, T5: hoja inferior del Dialogo del kit (foco atrapado y
// devuelto a quien lo abrió), opciones de 48 px y el efecto explicado con un Aviso.
// Spec 016, T6: `devolverFocoA` deja el foco donde siguen los atajos (el panel
// «Verificación» del conteo de escritorio), también si se abrió con el botón.

export function OtraUbicacion({
  abierto,
  onAbierto,
  esperada,
  ubicaciones,
  actual,
  onElegir,
  devolverFocoA,
}: {
  abierto: boolean
  onAbierto: (v: boolean) => void
  esperada: string
  ubicaciones: Ubicacion[]
  actual: string | undefined
  onElegir: (id: string) => void
  /** Dónde poner el foco al cerrar (por defecto, quien lo abrió). */
  devolverFocoA?: RefObject<HTMLElement | null>
}) {
  return (
    <Dialogo
      abierto={abierto}
      onAbiertoChange={onAbierto}
      forma="inferior"
      devolverFocoA={devolverFocoA}
      titulo="¿Dónde lo encontraste?"
      descripcion={`Esperada: ${esperada}`}
      className="mx-auto max-w-[480px]"
      pie={
        <Aviso tono="aviso" rol="status" icono={<ArrowLeftRight aria-hidden="true" />} titulo="Se registra como diferencia.">
          El activo no se mueve hasta que el administrador lo aplique.
        </Aviso>
      }
    >
      <Command label="Buscar ubicación" className="-mx-2 h-auto min-h-0 flex-1 bg-transparent">
        <CommandInput placeholder="Buscar sala o box…" />
        <CommandList className="max-h-[min(55dvh,26rem)] overflow-y-auto">
          <CommandEmpty>Sin ubicaciones con ese nombre</CommandEmpty>
          {opcionesDeSelector(ubicaciones).map(({ sede, opciones }) => (
            <CommandGroup key={sede.id} heading={sede.nombre}>
              {opciones.map((u) => (
                <CommandItem
                  key={u.id}
                  value={`${u.id} ${rutaDe(ubicaciones, u.id)}`}
                  onSelect={() => onElegir(u.id)}
                  className={cn('min-h-control text-base', actual === u.id && 'font-semibold')}
                >
                  <span className="min-w-0 flex-1 truncate">{rutaDe(ubicaciones, u.id)}</span>
                  {actual === u.id && <Check className="text-brand" aria-hidden="true" />}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>
      </Command>
    </Dialogo>
  )
}
