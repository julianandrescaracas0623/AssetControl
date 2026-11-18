import { CircleAlert, Loader2, RefreshCw, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'

import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { InputSugerido } from '@/components/app/InputSugerido'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { Activo } from '@/lib/activos'
import { type CampoEdicion, camposDe, ETIQUETAS, useEdicionActivo } from '@/lib/cambiosActivo'
import { useCategorias } from '@/lib/catalogo'
import { formatCOP } from '@/lib/format'

// Editar un activo desde su ficha (spec 005, T5; CU-CAT-05). Los mismos campos del
// alta, sin el código (inmutable). Si otra persona lo cambió mientras tanto (412), se
// conserva lo escrito, se marcan los campos que cambió y se elige: guardar lo mío sobre
// la versión nueva o descartarlo. Spec 015 (T2): diálogo centrado de dos columnas (una en
// teléfono) con el cuerpo desplazable y el pie fijo, en vez del panel lateral.

export function EditarActivo({
  activo,
  abierto,
  onAbierto,
  onCloseAutoFocus,
}: {
  activo: Activo
  abierto: boolean
  onAbierto: (v: boolean) => void
  /** A dónde vuelve el foco al cerrar (el botón que lo abrió). */
  onCloseAutoFocus?: (evento: Event) => void
}) {
  return (
    <Dialog open={abierto} onOpenChange={onAbierto}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col gap-0 p-0 sm:max-w-2xl" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader className="border-b p-4 pr-12">
          <DialogTitle>Editar activo</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{activo.codigo}</span> · el código del sticker no se cambia.
          </DialogDescription>
        </DialogHeader>
        {abierto && <Formulario activo={activo} cerrar={() => onAbierto(false)} />}
      </DialogContent>
    </Dialog>
  )
}

function valorVisible(activo: Activo, campo: CampoEdicion): string {
  if (campo === 'precio') return activo.precio_compra ? formatCOP(activo.precio_compra) : '—'
  if (campo === 'categoria') return activo.categoria.nombre
  return camposDe(activo)[campo] || 'vacío'
}

function Formulario({ activo, cerrar }: { activo: Activo; cerrar: () => void }) {
  const categorias = useCategorias()
  const edicion = useEdicionActivo(activo, (_guardado, sinCambios) => {
    toast.success(sinCambios ? 'Sin cambios que guardar' : 'Cambios guardados')
    cerrar()
  })
  const { campos, errores, conflicto } = edicion
  const otro = (campo: CampoEdicion) =>
    conflicto?.cambiados.includes(campo) ? `Otra persona lo cambió a «${valorVisible(conflicto.vigente, campo)}»` : undefined
  const ayuda = (campo: CampoEdicion, normal?: string) => otro(campo) ?? normal
  const describir = (campo: CampoEdicion, conAyuda: boolean) =>
    errores[campo] ? `${campo}-error` : conAyuda || otro(campo) ? `${campo}-ayuda` : undefined

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(evento) => {
        evento.preventDefault()
        edicion.guardar()
      }}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        {conflicto && (
          <Alert variant="warning" role="alert">
            <TriangleAlert />
            <AlertTitle>Alguien cambió este activo mientras editabas</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-3 text-foreground">
              {conflicto.cambiados.length > 0
                ? `Cambió: ${conflicto.cambiados.map((c) => ETIQUETAS[c].toLowerCase()).join(', ')}. Tus datos siguen aquí.`
                : 'Cambió su estado o su ubicación. Tus datos siguen aquí.'}
              <span className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
                <Button type="submit" size="sm" disabled={edicion.guardando}>
                  Guardar mis cambios
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={edicion.descartar}>
                  Descartar los míos
                </Button>
              </span>
            </AlertDescription>
          </Alert>
        )}
        {edicion.errorGeneral && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertTitle>No se guardó</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-3">
              {edicion.errorGeneral.mensaje}
              {edicion.errorGeneral.reintentable && (
                <Button type="submit" size="sm" variant="outline" className="max-md:min-h-11">
                  <RefreshCw />
                  Reintentar
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <Campo id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre} ayuda={ayuda('nombre')}>
            <InputSugerido campo="nombre" id="nombre" value={campos.nombre} onChange={(e) => edicion.cambiar('nombre', e.target.value)} maxLength={120} autoComplete="off" aria-invalid={Boolean(errores.nombre)} aria-describedby={describir('nombre', false)} className="max-md:h-11" />
          </Campo>
          <Campo id="precio" etiqueta={<>Precio de compra (COP) <Obligatorio /></>} error={errores.precio} ayuda={ayuda('precio', 'Cambiarlo deja el antes y el después en el historial.')}>
            <div className="relative">
              <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" aria-hidden="true">$</span>
              <Input id="precio" value={campos.precio} onChange={(e) => edicion.cambiar('precio', e.target.value)} inputMode="decimal" autoComplete="off" aria-invalid={Boolean(errores.precio)} aria-describedby={describir('precio', true)} className="pl-7 tabular-nums max-md:h-11" />
            </div>
          </Campo>
          <Campo id="categoria" etiqueta={<>Categoría <Obligatorio /></>} ayuda={ayuda('categoria')}>
            <Select value={campos.categoria} onValueChange={(v) => edicion.cambiar('categoria', v)} disabled={categorias.isPending}>
              <SelectTrigger id="categoria" className="w-full max-md:h-11" aria-describedby={describir('categoria', false)}>
                <SelectValue placeholder={categorias.isPending ? 'Cargando…' : 'Elige una categoría'} />
              </SelectTrigger>
              <SelectContent>
                {(categorias.data ?? []).map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Campo>
          <Campo id="serial" etiqueta="Serial" ayuda={ayuda('serial')}>
            <Input id="serial" value={campos.serial} onChange={(e) => edicion.cambiar('serial', e.target.value)} maxLength={120} autoComplete="off" aria-describedby={describir('serial', false)} className="font-mono max-md:h-11" />
          </Campo>
          <Campo id="marca" etiqueta="Marca" ayuda={ayuda('marca')}>
            <InputSugerido campo="marca" id="marca" value={campos.marca} onChange={(e) => edicion.cambiar('marca', e.target.value)} maxLength={120} autoComplete="off" aria-describedby={describir('marca', false)} className="max-md:h-11" />
          </Campo>
          <Campo id="modelo" etiqueta="Modelo" ayuda={ayuda('modelo')}>
            <InputSugerido campo="modelo" id="modelo" value={campos.modelo} onChange={(e) => edicion.cambiar('modelo', e.target.value)} maxLength={120} autoComplete="off" aria-describedby={describir('modelo', false)} className="max-md:h-11" />
          </Campo>
          <Campo id="subtipo" etiqueta="Subtipo" ayuda={ayuda('subtipo')}>
            <InputSugerido campo="subtipo" id="subtipo" value={campos.subtipo} onChange={(e) => edicion.cambiar('subtipo', e.target.value)} maxLength={120} autoComplete="off" aria-describedby={describir('subtipo', false)} className="max-md:h-11" />
          </Campo>
          <Campo id="fecha" etiqueta="Fecha de compra" error={errores.fecha} ayuda={ayuda('fecha')}>
            <Input id="fecha" type="date" value={campos.fecha} onChange={(e) => edicion.cambiar('fecha', e.target.value)} aria-invalid={Boolean(errores.fecha)} aria-describedby={describir('fecha', false)} className="max-md:h-11" />
          </Campo>
        </div>
      </div>
      <DialogFooter className="mx-0 mb-0 flex-row justify-end [&_[data-slot=button]]:max-md:min-h-11">
        <Button type="button" variant="ghost" onClick={cerrar}>
          Cancelar
        </Button>
        <Button type="submit" disabled={edicion.guardando}>
          {edicion.guardando ? (
            <>
              <Loader2 className="animate-spin" aria-hidden="true" />
              Guardando…
            </>
          ) : (
            'Guardar cambios'
          )}
        </Button>
      </DialogFooter>
    </form>
  )
}
