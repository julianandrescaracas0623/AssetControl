import { Check, ChevronDown, CircleAlert, Loader2, RefreshCw, ScanBarcode, TriangleAlert } from 'lucide-react'
import { useEffect, useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { EncabezadoPagina } from '@/components/app/ConEstado'
import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { Escaner } from '@/components/app/Escaner'
import { InputSugerido } from '@/components/app/InputSugerido'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { type Activo, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import { type ErroresAlta, useAltaActivo } from '@/lib/altaActivo'
import { useCategorias, useUbicaciones } from '@/lib/catalogo'
import { cn } from '@/lib/utils'

// Registrar activo desde administración (decisión del humano 2026-11-13; D3; spec 004,
// T6). R8: sin código de sticker no hay alta. Obligatorios: código, nombre, precio,
// categoría y ubicación; solo se teclean nombre y precio (lo demás se elige o se copia
// de un parecido). La validación definitiva es del servidor.

function Paso({ n, titulo, nota, children }: { n: number; titulo: string; nota?: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 border-b px-4 py-5 last:border-b-0 md:px-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex size-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground" aria-hidden="true">{n}</span>
          <h2 id={id} className="font-semibold">{titulo}</h2>
        </div>
        {nota && <p className="text-xs text-muted-foreground">{nota}</p>}
      </div>
      {children}
    </section>
  )
}

/** Código normalizado después de una pausa al escribir (para avisar si ya existe). */
function useCodigoEnPausa(texto: string): string | null {
  const [codigo, setCodigo] = useState<string | null>(null)
  useEffect(() => {
    const reloj = setTimeout(() => setCodigo(normalizarCodigo(texto)), 400)
    return () => clearTimeout(reloj)
  }, [texto])
  return codigo
}

export default function RegistrarActivo() {
  const alta = useAltaActivo({ rol: 'admin' })
  const categorias = useCategorias()
  const ubicaciones = useUbicaciones()
  const [varias, setVarias] = useState(false)
  const [escaneando, setEscaneando] = useState(false)
  const { campos, errores } = alta
  const codigoEnPausa = useCodigoEnPausa(campos.codigo)
  const revision = useActivoPorCodigo(codigoEnPausa)
  const existente = alta.existente ?? (revision.data ? { id: revision.data.id, codigo: revision.data.codigo, nombre: revision.data.nombre } : null)

  function guardar(otro: boolean) {
    alta.enviar({
      alCrear:
        otro || varias
          ? (activo: Activo) => {
              toast.success(`Activo creado: ${activo.nombre} · ${activo.codigo}`)
              if (varias) alta.siguienteUnidad()
              else alta.otro()
            }
          : undefined,
    })
  }

  const describir = (campo: keyof ErroresAlta, ayuda = false) => (errores[campo] ? `${campo}-error` : ayuda ? `${campo}-ayuda` : undefined)
  const errorCodigo = errores.codigo && !alta.existente ? errores.codigo : undefined

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Registrar activo"
        descripcion="Una fila por unidad física. Cada activo necesita su sticker: escanéalo o escribe el código impreso."
      />

      {alta.creado ? (
        <Alert variant="success" role="status">
          <Check />
          <AlertTitle>Activo creado</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>
              {alta.creado.nombre} · <span className="font-mono">{alta.creado.codigo}</span> quedó registrado en {alta.creado.ubicacion.ruta}.
            </span>
            <span className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
              <Button size="sm" onClick={() => alta.otro()}>Registrar otro</Button>
              <Button asChild size="sm" variant="outline">
                <Link to={`/admin/activos/${encodeURIComponent(alta.creado.codigo)}`}>Ver el activo</Link>
              </Button>
            </span>
          </AlertDescription>
        </Alert>
      ) : (
        <form
          noValidate
          className="flex flex-col rounded-xl border"
          onSubmit={(evento) => {
            evento.preventDefault()
            guardar(false)
          }}
        >
          {alta.errorGeneral && (
            <div className="px-4 pt-4 md:px-6">
              <Alert variant="destructive">
                <CircleAlert />
                <AlertTitle>No se guardó</AlertTitle>
                <AlertDescription className="flex flex-col items-start gap-3">
                  {alta.errorGeneral.mensaje}
                  {alta.errorGeneral.reintentable && (
                    <Button type="submit" size="sm" variant="outline" className="max-md:min-h-11">
                      <RefreshCw />
                      Reintentar
                    </Button>
                  )}
                </AlertDescription>
              </Alert>
            </div>
          )}
          <Paso n={1} titulo="Código del sticker">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
              <Campo id="codigo" className="flex-1" etiqueta={<>Código del sticker <Obligatorio /></>} error={errorCodigo}>
                <Input
                  id="codigo"
                  value={campos.codigo}
                  onChange={(e) => alta.cambiar('codigo', e.target.value)}
                  inputMode="text"
                  autoCapitalize="characters"
                  autoComplete="off"
                  spellCheck={false}
                  maxLength={40}
                  aria-invalid={Boolean(errorCodigo) || Boolean(existente)}
                  aria-describedby={describir('codigo') ?? 'codigo-estado'}
                  className="h-12 font-mono text-lg tracking-wider uppercase md:h-10"
                />
              </Campo>
              <Button type="button" variant="outline" className="h-12 sm:mt-[1.375rem] md:h-10" onClick={() => setEscaneando(true)}>
                <ScanBarcode />
                Escanear con la cámara
              </Button>
            </div>
            <div id="codigo-estado" className="flex flex-wrap items-center justify-between gap-3" aria-live="polite">
              {codigoEnPausa &&
                !revision.isPending &&
                (existente ? (
                  <span className="flex flex-wrap items-center gap-2 text-sm text-destructive">
                    <TriangleAlert className="size-4" aria-hidden="true" />
                    Ese código ya existe: {existente.nombre}
                    <Button asChild size="sm" variant="outline" className="max-md:min-h-11">
                      <Link to={`/admin/activos/${encodeURIComponent(existente.codigo)}`}>Abrir activo</Link>
                    </Button>
                  </span>
                ) : revision.data === null ? (
                  <Badge variant="success">
                    <Check aria-hidden="true" />
                    Código libre
                  </Badge>
                ) : null)}
              <div className="flex flex-col gap-1">
                <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-0">
                  <Checkbox
                    checked={alta.confirmado}
                    onCheckedChange={(v) => alta.setConfirmado(v === true)}
                    aria-invalid={Boolean(errores.confirmado)}
                    aria-describedby={errores.confirmado ? 'confirmado-error' : undefined}
                  />
                  Revisé que coincide con el sticker: no se puede cambiar después
                </label>
                {errores.confirmado && (
                  <p id="confirmado-error" className="flex items-center gap-1.5 text-xs text-destructive">
                    <CircleAlert className="size-3.5" aria-hidden="true" />
                    {errores.confirmado}
                  </p>
                )}
              </div>
            </div>
          </Paso>

          <Paso n={2} titulo="Datos del activo" nota="Solo se teclean nombre y precio; lo demás se elige.">
            <CopiarDeParecido onCopiar={alta.copiar} copiado={alta.copiado} />
            <div className="grid gap-4 md:grid-cols-2">
              <Campo id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre}>
                <InputSugerido campo="nombre" id="nombre" value={campos.nombre} onChange={(e) => alta.cambiar('nombre', e.target.value)} maxLength={120} autoComplete="off" aria-invalid={Boolean(errores.nombre)} aria-describedby={describir('nombre')} className="max-md:h-11" />
              </Campo>
              <Campo id="precio" etiqueta={<>Precio de compra (COP) <Obligatorio /></>} error={errores.precio} ayuda="Solo lo ven los administradores.">
                <div className="relative">
                  <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" aria-hidden="true">$</span>
                  <Input id="precio" value={campos.precio} onChange={(e) => alta.cambiar('precio', e.target.value)} inputMode="decimal" autoComplete="off" aria-invalid={Boolean(errores.precio)} aria-describedby={describir('precio', true)} className="pl-7 tabular-nums max-md:h-11" />
                </div>
              </Campo>
              <Campo id="categoria" etiqueta={<>Categoría <Obligatorio /></>} error={errores.categoria} ayuda="Lista cerrada de la clínica.">
                <Select value={campos.categoria} onValueChange={(v) => alta.cambiar('categoria', v)} disabled={categorias.isPending}>
                  <SelectTrigger id="categoria" className="w-full max-md:h-11" aria-invalid={Boolean(errores.categoria)} aria-describedby={describir('categoria', true)}>
                    <SelectValue placeholder={categorias.isPending ? 'Cargando…' : 'Elige una categoría'} />
                  </SelectTrigger>
                  <SelectContent>
                    {(categorias.data ?? []).map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.nombre}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Campo>
              <Campo id="ubicacion" etiqueta={<>Ubicación <Obligatorio /></>} error={errores.ubicacion} ayuda="Una sala o un box activos.">
                <LocationPicker
                  id="ubicacion"
                  ubicaciones={ubicaciones.data ?? []}
                  cargando={ubicaciones.isPending}
                  valor={campos.ubicacion || undefined}
                  onChange={(v) => alta.cambiar('ubicacion', v)}
                  className={cn(errores.ubicacion && 'border-destructive')}
                />
              </Campo>
            </div>
            <Collapsible className="rounded-lg border">
              <CollapsibleTrigger className="group flex min-h-11 w-full items-center justify-between gap-2 px-3 text-left text-sm font-medium md:min-h-10">
                <span className="flex min-w-0 items-center gap-2">
                  <ChevronDown className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
                  <span className="truncate">Más datos (opcional)</span>
                </span>
                <span className="hidden text-xs font-normal text-muted-foreground sm:inline">serial, marca, modelo, subtipo, fecha de compra</span>
              </CollapsibleTrigger>
              <CollapsibleContent className="grid gap-4 border-t p-3 md:grid-cols-2">
                <Campo id="serial" etiqueta="Serial" ayuda="No tiene que ser único.">
                  <Input id="serial" value={campos.serial} onChange={(e) => alta.cambiar('serial', e.target.value)} maxLength={120} autoComplete="off" className="font-mono max-md:h-11" />
                </Campo>
                <Campo id="marca" etiqueta="Marca">
                  <InputSugerido campo="marca" id="marca" value={campos.marca} onChange={(e) => alta.cambiar('marca', e.target.value)} maxLength={120} autoComplete="off" className="max-md:h-11" />
                </Campo>
                <Campo id="modelo" etiqueta="Modelo">
                  <InputSugerido campo="modelo" id="modelo" value={campos.modelo} onChange={(e) => alta.cambiar('modelo', e.target.value)} maxLength={120} autoComplete="off" className="max-md:h-11" />
                </Campo>
                <Campo id="subtipo" etiqueta="Subtipo" ayuda="Por ejemplo: computador, fuente, video.">
                  <InputSugerido campo="subtipo" id="subtipo" value={campos.subtipo} onChange={(e) => alta.cambiar('subtipo', e.target.value)} maxLength={120} autoComplete="off" className="max-md:h-11" />
                </Campo>
                <Campo id="fecha" etiqueta="Fecha de compra" error={errores.fecha}>
                  <Input id="fecha" type="date" value={campos.fecha} onChange={(e) => alta.cambiar('fecha', e.target.value)} aria-invalid={Boolean(errores.fecha)} aria-describedby={describir('fecha')} className="max-md:h-11" />
                </Campo>
              </CollapsibleContent>
            </Collapsible>
          </Paso>

          <Paso n={3} titulo="Varias unidades iguales">
            <label className="flex min-h-11 items-center justify-between gap-4 text-sm">
              <span>Al guardar, conservar estos datos para escanear el siguiente sticker</span>
              <Switch checked={varias} onCheckedChange={setVarias} />
            </label>
          </Paso>

          <div className="flex flex-col-reverse gap-2 rounded-b-xl border-t bg-sidebar px-4 py-3 sm:flex-row sm:items-center sm:justify-between md:px-6 [&_[data-slot=button]]:max-md:min-h-11">
            <Button asChild variant="ghost">
              <Link to="/admin/activos">Cancelar</Link>
            </Button>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="outline" disabled={alta.guardando} onClick={() => guardar(true)}>
                Guardar y registrar otro
              </Button>
              <Button type="submit" disabled={alta.guardando}>
                {alta.guardando ? (
                  <>
                    <Loader2 className="animate-spin" aria-hidden="true" />
                    Guardando…
                  </>
                ) : (
                  'Guardar activo'
                )}
              </Button>
            </div>
          </div>
        </form>
      )}

      <Dialog open={escaneando} onOpenChange={setEscaneando}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Escanear el sticker</DialogTitle>
            <DialogDescription>Apunta la cámara al código de barras; se lee solo.</DialogDescription>
          </DialogHeader>
          {escaneando && (
            <Escaner
              className="min-h-[280px]"
              onLectura={(texto) => {
                alta.cambiar('codigo', normalizarCodigo(texto) ?? texto)
                setEscaneando(false)
                toast.success('Código leído: revisa que coincida con el sticker')
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
