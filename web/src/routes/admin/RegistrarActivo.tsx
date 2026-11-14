import { Check, ChevronDown, CircleAlert, Loader2, ScanBarcode, TriangleAlert } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { EncabezadoPagina, ErrorCarga } from '@/components/app/ConEstado'
import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useSimulacion } from '@/lib/simulacion'
import { cn } from '@/lib/utils'
import { ACTIVOS, CATEGORIAS, UBICACIONES, rutaUbicacion, type ActivoFicticio, UBICACIONES_API } from '@/mocks/datos-ficticios'

// Registrar activo desde administración (decisión del humano 2026-11-13; D3).
// R8: sin código de sticker no hay alta. Obligatorios: código, nombre, precio,
// categoría y ubicación; solo se teclean nombre y precio (lo demás se elige o
// se copia de un parecido). La validación definitiva es del servidor (spec 004).

type Campo = 'codigo' | 'confirmado' | 'nombre' | 'precio' | 'categoria' | 'ubicacion'
type Errores = Partial<Record<Campo, string>>

const PRECIO = /^(\d{1,3}(\.\d{3})*|\d+)(,\d{1,2})?$/

/** "389900.00" → "389.900" (texto del campo; decimales solo si no son cero). */
function precioParaCampo(valor: string): string {
  const [entero, dec = '00'] = valor.split('.')
  const agrupado = entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return dec === '00' ? agrupado : `${agrupado},${dec}`
}

function Campo({ id, etiqueta, error, ayuda, children, className }: { id: string; etiqueta: ReactNode; error?: string; ayuda?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <Label htmlFor={id}>{etiqueta}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-center gap-1.5 text-xs text-destructive">
          <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        ayuda && <p id={`${id}-ayuda`} className="text-xs text-muted-foreground">{ayuda}</p>
      )}
    </div>
  )
}

const Obligatorio = () => <span className="text-destructive" aria-hidden="true">*</span>

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

export default function RegistrarActivo() {
  const { estado } = useSimulacion()
  const [codigo, setCodigo] = useState('')
  const [confirmado, setConfirmado] = useState(false)
  const [nombre, setNombre] = useState('')
  const [precio, setPrecio] = useState('')
  const [categoria, setCategoria] = useState('')
  const [ubicacion, setUbicacion] = useState<string | undefined>()
  const [varias, setVarias] = useState(false)
  const [errores, setErrores] = useState<Errores>({})
  const [creado, setCreado] = useState<{ codigo: string; nombre: string; ubicacion: string } | null>(null)

  const existente = ACTIVOS.find((a) => a.codigo === codigo.trim())
  const guardando = estado === 'cargando'

  function copiar(a: ActivoFicticio) {
    setNombre(a.nombre)
    setPrecio(precioParaCampo(a.precio))
    setCategoria(a.categoria)
    setUbicacion(UBICACIONES.find((u) => rutaUbicacion(u.id) === a.ubicacion)?.id)
  }

  function validar(): Errores {
    const e: Errores = {}
    if (!codigo.trim()) e.codigo = 'Escanea o escribe el código del sticker'
    else if (existente) e.codigo = 'Ese código ya existe'
    else if (!confirmado) e.confirmado = 'Confirma que el código coincide con el sticker'
    if (!nombre.trim()) e.nombre = 'Escribe el nombre'
    if (!precio.trim()) e.precio = 'Escribe el precio'
    else if (!PRECIO.test(precio.trim())) e.precio = 'Escribe el precio en pesos, por ejemplo 389.900'
    if (!categoria) e.categoria = 'Elige la categoría'
    if (!ubicacion) e.ubicacion = 'Elige la ubicación'
    return e
  }

  function guardar(otro: boolean) {
    const e = validar()
    setErrores(e)
    if (Object.keys(e).length > 0) return
    const registro = { codigo: codigo.trim(), nombre: nombre.trim(), ubicacion: rutaUbicacion(ubicacion!) }
    if (otro || varias) {
      toast.success(`Activo creado: ${registro.nombre} · ${registro.codigo}`)
      setCodigo('')
      setConfirmado(false)
      return
    }
    setCreado(registro)
  }

  function otroMas() {
    setCreado(null)
    setCodigo('')
    setConfirmado(false)
    setNombre('')
    setPrecio('')
    setCategoria('')
    setUbicacion(undefined)
    setErrores({})
  }

  const describir = (campo: Campo, ayuda = false) => (errores[campo] ? `${campo}-error` : ayuda ? `${campo}-ayuda` : undefined)

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Registrar activo"
        descripcion="Una fila por unidad física. Cada activo necesita su sticker: escanéalo o escribe el código impreso."
      />

      {estado === 'error' && <ErrorCarga titulo="No se pudo guardar. Revisa la conexión." />}

      {creado ? (
        <Alert variant="success" role="status">
          <Check />
          <AlertTitle>Activo creado</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>
              {creado.nombre} · <span className="font-mono">{creado.codigo}</span> quedó registrado en {creado.ubicacion}.
            </span>
            <span className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
              <Button size="sm" onClick={otroMas}>Registrar otro</Button>
              <Button asChild size="sm" variant="outline">
                <Link to={`/admin/activos`}>Ver activos</Link>
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
          <Paso n={1} titulo="Código del sticker">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
              <Campo
                id="codigo"
                className="flex-1"
                etiqueta={<>Código del sticker <Obligatorio /></>}
                error={errores.codigo && errores.codigo !== 'Ese código ya existe' ? errores.codigo : undefined}
              >
                <Input
                  id="codigo"
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  inputMode="text"
                  autoComplete="off"
                  aria-invalid={Boolean(errores.codigo) || Boolean(existente)}
                  aria-describedby={describir('codigo') ?? 'codigo-estado'}
                  className="h-12 font-mono text-lg tracking-wider md:h-10"
                />
              </Campo>
              <Button type="button" variant="outline" className="h-12 sm:mt-[1.375rem] md:h-10" onClick={() => toast('La lectura con la cámara llega con la spec 004')}>
                <ScanBarcode />
                Escanear con la cámara
              </Button>
            </div>
            <div id="codigo-estado" className="flex flex-wrap items-center justify-between gap-3" aria-live="polite">
              {codigo.trim() &&
                (existente ? (
                  <span className="flex flex-wrap items-center gap-2 text-sm text-destructive">
                    <TriangleAlert className="size-4" aria-hidden="true" />
                    Ese código ya existe
                    <Button asChild size="sm" variant="outline" className="max-md:min-h-11">
                      <Link to={`/admin/activos/${existente.codigo}`}>Abrir activo</Link>
                    </Button>
                  </span>
                ) : (
                  <Badge variant="success">
                    <Check aria-hidden="true" />
                    Código libre
                  </Badge>
                ))}
              <div className="flex flex-col gap-1">
                <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-0">
                  <Checkbox
                    checked={confirmado}
                    onCheckedChange={(v) => setConfirmado(v === true)}
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
            <CopiarDeParecido onCopiar={copiar} />
            <div className="grid gap-4 md:grid-cols-2">
              <Campo id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre}>
                <Input id="nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} autoComplete="off" aria-invalid={Boolean(errores.nombre)} aria-describedby={describir('nombre')} className="max-md:h-11" />
              </Campo>
              <Campo id="precio" etiqueta={<>Precio de compra (COP) <Obligatorio /></>} error={errores.precio} ayuda="Solo lo ven los administradores.">
                <div className="relative">
                  <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" aria-hidden="true">$</span>
                  <Input id="precio" value={precio} onChange={(e) => setPrecio(e.target.value)} inputMode="decimal" autoComplete="off" aria-invalid={Boolean(errores.precio)} aria-describedby={describir('precio', true)} className="pl-7 tabular-nums max-md:h-11" />
                </div>
              </Campo>
              <Campo id="categoria" etiqueta={<>Categoría <Obligatorio /></>} error={errores.categoria} ayuda="Lista cerrada de la clínica.">
                <Select value={categoria} onValueChange={setCategoria}>
                  <SelectTrigger id="categoria" className="w-full max-md:h-11" aria-invalid={Boolean(errores.categoria)} aria-describedby={describir('categoria', true)}>
                    <SelectValue placeholder="Elige una categoría" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIAS.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Campo>
              <Campo id="ubicacion" etiqueta={<>Ubicación <Obligatorio /></>} error={errores.ubicacion} ayuda="Arriba aparece la última que usaste.">
                <LocationPicker id="ubicacion" ubicaciones={UBICACIONES_API} valor={ubicacion} ultimaUsada="c1b2" onChange={setUbicacion} className={cn(errores.ubicacion && 'border-destructive')} />
              </Campo>
            </div>
            <Collapsible className="rounded-lg border">
              <CollapsibleTrigger className="group flex min-h-11 w-full items-center justify-between gap-2 px-3 text-left text-sm font-medium md:min-h-10">
                <span className="flex min-w-0 items-center gap-2">
                  <ChevronDown className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
                  <span className="truncate">Más datos (opcional)</span>
                </span>
                <span className="hidden text-xs font-normal text-muted-foreground sm:inline">serial, marca, modelo, fecha de compra</span>
              </CollapsibleTrigger>
              <CollapsibleContent className="grid gap-4 border-t p-3 md:grid-cols-2">
                <Campo id="serial" etiqueta="Serial" ayuda="No tiene que ser único.">
                  <Input id="serial" className="font-mono max-md:h-11" />
                </Campo>
                <Campo id="marca" etiqueta="Marca">
                  <Input id="marca" className="max-md:h-11" />
                </Campo>
                <Campo id="modelo" etiqueta="Modelo">
                  <Input id="modelo" className="max-md:h-11" />
                </Campo>
                <Campo id="fecha" etiqueta="Fecha de compra">
                  <Input id="fecha" type="date" className="max-md:h-11" />
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
              <Button type="button" variant="outline" disabled={guardando} onClick={() => guardar(true)}>
                Guardar y registrar otro
              </Button>
              <Button type="submit" disabled={guardando}>
                {guardando ? (
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
    </div>
  )
}
