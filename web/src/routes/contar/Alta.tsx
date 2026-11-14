import { Check, ChevronDown, CircleAlert, Info } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'

import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { CountShell } from '@/components/app/CountShell'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useEnlace, useSimulacion } from '@/lib/simulacion'
import { CATEGORIAS, UBICACIONES, rutaUbicacion, type ActivoFicticio } from '@/mocks/datos-ficticios'

// Alta por escaneo (docs/08 §7.3, CU-CAT-02/03) a 375 px, en una columna.
// El código llega del sticker y es fijo. Obligatorios: nombre, precio,
// categoría y ubicación. El contador escribe el precio y después no lo ve;
// si copia de un parecido, el precio lo copia el servidor y no se muestra (P13).

type Errores = Partial<Record<'confirmado' | 'nombre' | 'precio' | 'categoria' | 'ubicacion', string>>
const PRECIO = /^(\d{1,3}(\.\d{3})*|\d+)(,\d{1,2})?$/

function Campo({ id, etiqueta, error, ayuda, children }: { id: string; etiqueta: ReactNode; error?: string; ayuda?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className="text-[15px]">{etiqueta}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-center gap-1.5 text-sm text-destructive">
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        ayuda && <p id={`${id}-ayuda`} className="text-sm text-muted-foreground">{ayuda}</p>
      )}
    </div>
  )
}

const Obligatorio = () => <span className="text-destructive" aria-hidden="true">*</span>

export default function Alta() {
  const [params] = useSearchParams()
  const codigo = params.get('codigo') ?? ''
  const { rol } = useSimulacion()
  const enlace = useEnlace()
  const [confirmado, setConfirmado] = useState(false)
  const [nombre, setNombre] = useState('')
  const [precio, setPrecio] = useState('')
  const [precioCopiado, setPrecioCopiado] = useState(false)
  const [categoria, setCategoria] = useState('')
  const [ubicacion, setUbicacion] = useState<string | undefined>()
  const [errores, setErrores] = useState<Errores>({})
  const [creado, setCreado] = useState(false)

  function copiar(a: ActivoFicticio) {
    setNombre(a.nombre)
    setCategoria(a.categoria)
    setUbicacion(UBICACIONES.find((u) => rutaUbicacion(u.id) === a.ubicacion)?.id)
    if (rol === 'contador') {
      setPrecio('')
      setPrecioCopiado(true)
    } else {
      setPrecio(a.precio.split('.')[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.'))
    }
  }

  function guardar(evento: React.FormEvent) {
    evento.preventDefault()
    const e: Errores = {}
    if (codigo && !confirmado) e.confirmado = 'Confirma que el código coincide con el sticker'
    if (!nombre.trim()) e.nombre = 'Escribe el nombre'
    if (!precioCopiado) {
      if (!precio.trim()) e.precio = 'Escribe el precio'
      else if (!PRECIO.test(precio.trim())) e.precio = 'Escribe el precio en pesos, por ejemplo 389.900'
    }
    if (!categoria) e.categoria = 'Elige la categoría'
    if (!ubicacion) e.ubicacion = 'Elige la ubicación'
    setErrores(e)
    if (Object.keys(e).length === 0) setCreado(true)
  }

  if (creado) {
    return (
      <CountShell titulo="Registrar activo" subtitulo="Conteo nov 2026" volver={enlace('/contar')} estadoRed="guardado"
        acciones={
          <Button asChild className="min-h-14 font-semibold">
            <Link to={enlace('/contar/escanear')}>Escanear otro</Link>
          </Button>
        }
      >
        <h1 className="sr-only">Registrar activo</h1>
        <Alert variant="success">
          <Check />
          <AlertTitle>Activo creado</AlertTitle>
          <AlertDescription>
            {nombre} · <span className="font-mono">{codigo}</span> quedó registrado en {rutaUbicacion(ubicacion!)}.
          </AlertDescription>
        </Alert>
      </CountShell>
    )
  }

  return (
    <CountShell
      titulo="Registrar activo"
      subtitulo="Conteo nov 2026"
      volver={enlace('/contar/escribir')}
      estadoRed="en_linea"
      acciones={
        <Button type="submit" form="alta" className="min-h-14 font-semibold">
          Guardar activo
        </Button>
      }
    >
      <h1 className="sr-only">Registrar activo</h1>
      <form id="alta" noValidate onSubmit={guardar} className="flex flex-col gap-4">
        <div className="flex items-center gap-3 rounded-xl border bg-muted/50 px-3 py-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs text-muted-foreground">Código del sticker · nuevo</p>
            <p className="font-mono text-lg tracking-wider">{codigo || '—'}</p>
          </div>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <Checkbox checked={confirmado} onCheckedChange={(v) => setConfirmado(v === true)} aria-invalid={Boolean(errores.confirmado)} aria-describedby={errores.confirmado ? 'confirmado-error' : undefined} />
            Coincide
          </label>
        </div>
        {errores.confirmado && (
          <p id="confirmado-error" className="-mt-2 flex items-center gap-1.5 text-sm text-destructive">
            <CircleAlert className="size-4" aria-hidden="true" />
            {errores.confirmado}
          </p>
        )}
        <CopiarDeParecido onCopiar={copiar} className="h-12 text-base md:h-12" />
        <Campo id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre}>
          <Input id="nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} autoComplete="off" enterKeyHint="next" aria-invalid={Boolean(errores.nombre)} aria-describedby={errores.nombre ? 'nombre-error' : undefined} className="h-12 text-base" />
        </Campo>
        {precioCopiado ? (
          <Alert variant="info">
            <Info />
            <AlertDescription className="text-foreground">El precio se copia del activo parecido. Solo lo ven los administradores.</AlertDescription>
          </Alert>
        ) : (
          <Campo id="precio" etiqueta={<>Precio de compra (COP) <Obligatorio /></>} error={errores.precio} ayuda="Después de guardar, solo lo verán los administradores.">
            <div className="relative">
              <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" aria-hidden="true">$</span>
              <Input id="precio" value={precio} onChange={(e) => setPrecio(e.target.value)} inputMode="decimal" autoComplete="off" aria-invalid={Boolean(errores.precio)} aria-describedby={errores.precio ? 'precio-error' : 'precio-ayuda'} className="h-12 pl-7 text-base tabular-nums" />
            </div>
          </Campo>
        )}
        <Campo id="categoria" etiqueta={<>Categoría <Obligatorio /></>} error={errores.categoria}>
          <Select value={categoria} onValueChange={setCategoria}>
            <SelectTrigger id="categoria" className="h-12! w-full text-base" aria-invalid={Boolean(errores.categoria)} aria-describedby={errores.categoria ? 'categoria-error' : undefined}>
              <SelectValue placeholder="Elige una categoría" />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIAS.map((c) => (
                <SelectItem key={c} value={c} className="min-h-11">{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Campo>
        <Campo id="ubicacion" etiqueta={<>Ubicación <Obligatorio /></>} error={errores.ubicacion} ayuda="Arriba aparece la sala donde estás contando.">
          <LocationPicker id="ubicacion" valor={ubicacion} ultimaUsada="administracion" onChange={setUbicacion} className="h-12 text-base md:h-12" />
        </Campo>
        <Collapsible className="rounded-lg border">
          <CollapsibleTrigger className="group flex min-h-12 w-full items-center gap-2 px-3 text-left text-[15px] font-medium">
            <ChevronDown className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
            <span className="truncate">Más datos (opcional)</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex flex-col gap-4 border-t p-3">
            <Campo id="serial" etiqueta="Serial"><Input id="serial" className="h-12 font-mono text-base" /></Campo>
            <Campo id="marca" etiqueta="Marca"><Input id="marca" className="h-12 text-base" /></Campo>
            <Campo id="modelo" etiqueta="Modelo"><Input id="modelo" className="h-12 text-base" /></Campo>
            <Campo id="fecha" etiqueta="Fecha de compra"><Input id="fecha" type="date" className="h-12 text-base" /></Campo>
          </CollapsibleContent>
        </Collapsible>
      </form>
    </CountShell>
  )
}
