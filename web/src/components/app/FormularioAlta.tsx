import { Camera, Check, ChevronDown, CircleCheck, Pin, TriangleAlert, Usb } from 'lucide-react'
import { type ReactNode, type RefObject, useEffect, useId, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { CampoFoto } from '@/components/app/CampoFoto'
import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { Escaner } from '@/components/app/Escaner'
import { InputSugerido } from '@/components/app/InputSugerido'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { type Activo, aPrecioCanonico, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import type { Categoria, Rol, Ubicacion } from '@/lib/api/cliente'
import { type AltaActivo, type CampoAlta, claseConservado } from '@/lib/altaActivo'
import { rutaDe } from '@/lib/catalogo'
import { formatCOP } from '@/lib/format'
import { cn } from '@/lib/utils'

// Piezas comunes de «Registrar activo» (spec 015, T10; R11; Q9 = A; maquetas t10-*): las
// usan el alta de administración y la del modo conteo. Teclado: el `Enter` del lector USB
// en el código pasa a Nombre (no guarda); `Enter` en los demás campos de texto guarda;
// `Ctrl+Enter` (o `Cmd+Enter`) es «Guardar y registrar otro». El estado y el envío siguen
// en `useAltaActivo` (UUID del cliente, idempotente); aquí no se decide nada de dominio.

export const NOTA_REGISTRAR_OTRO = 'Conserva categoría, ubicación, marca, modelo y subtipo. Borra código, nombre, serial, precio y foto.'

/** Pasa al primer dato después del código (Nombre o, si se duplica, Ubicación). */
function siguienteDespuesDelCodigo() {
  ;(document.getElementById('nombre') ?? document.getElementById('ubicacion'))?.focus()
}

/** Marca «se conserva» junto a la etiqueta de un campo que conserva «registrar otro». */
export function SeConserva() {
  return (
    <span className="ml-auto inline-flex items-center gap-1 text-[11px] font-normal text-muted-foreground" title="Se conserva al registrar otro">
      <Pin className="size-3" aria-hidden="true" />
      se conserva
    </span>
  )
}

/** Etiqueta con la marca «se conserva» (dentro de la etiqueta para que se anuncie). */
export function Etiqueta({ children, conserva = false }: { children: ReactNode; conserva?: boolean }) {
  return (
    <span className="flex w-full items-center gap-1.5">
      <span>{children}</span>
      {conserva && <SeConserva />}
    </span>
  )
}

/** Atajo de teclado en un botón (solo visible en escritorio; no cambia el nombre accesible). */
export function TeclaBoton({ children, oscura = false }: { children: ReactNode; oscura?: boolean }) {
  return (
    <kbd
      aria-hidden="true"
      className={cn(
        'ml-1 hidden rounded border px-1 font-mono text-[10px] leading-4 font-normal lg:inline-block',
        oscura ? 'border-primary-foreground/20 bg-primary-foreground/10 text-primary-foreground' : 'bg-muted text-muted-foreground',
      )}
    >
      {children}
    </kbd>
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

/** Código del sticker editable: lector USB, teclado o cámara a pedido. */
export function CampoCodigo({
  alta,
  rutaActivo,
  campoRef,
  className,
}: {
  alta: AltaActivo
  rutaActivo: (codigo: string) => string
  campoRef?: RefObject<HTMLInputElement | null>
  className?: string
}) {
  const { campos, errores } = alta
  const [escaneando, setEscaneando] = useState(false)
  const enPausa = useCodigoEnPausa(campos.codigo)
  // Solo vale si sigue siendo el código del campo (tras «registrar otro» el campo queda
  // vacío antes de que termine la pausa y el código anterior ya existe).
  const codigoEnPausa = enPausa && enPausa === normalizarCodigo(campos.codigo) ? enPausa : null
  const revision = useActivoPorCodigo(codigoEnPausa)
  const existente = alta.existente ?? (codigoEnPausa && revision.data ? { id: revision.data.id, codigo: revision.data.codigo, nombre: revision.data.nombre } : null)
  const errorCodigo = errores.codigo && !alta.existente ? errores.codigo : undefined

  return (
    <div className="flex flex-col gap-3">
      <Campo id="codigo" etiqueta={<>Código del sticker <Obligatorio /></>} error={errorCodigo}>
        <Input
          ref={campoRef}
          id="codigo"
          value={campos.codigo}
          onChange={(e) => alta.cambiar('codigo', e.target.value)}
          onKeyDown={(e) => {
            // El lector USB termina cada lectura con Enter: pasa a Nombre, no guarda.
            if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
              e.preventDefault()
              e.stopPropagation()
              siguienteDespuesDelCodigo()
            }
          }}
          inputMode="text"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          maxLength={40}
          enterKeyHint="next"
          aria-invalid={Boolean(errorCodigo) || Boolean(existente)}
          aria-describedby={errorCodigo ? 'codigo-error' : 'codigo-estado'}
          className={cn('h-12 font-mono text-lg tracking-wider uppercase md:h-11', className)}
        />
      </Campo>
      <p className="-mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="hidden items-center gap-1.5 md:flex">
          <Usb className="size-3.5 text-success" aria-hidden="true" />
          El cursor empieza aquí. El lector USB escribe el código y su Enter pasa a Nombre (no guarda).
        </span>
        <button
          type="button"
          className="inline-flex min-h-11 items-center gap-1 text-brand-strong underline underline-offset-4 md:min-h-0"
          onClick={() => setEscaneando(true)}
        >
          <Camera className="size-3.5" aria-hidden="true" />
          Usar la cámara
        </button>
      </p>
      <div id="codigo-estado" className="flex flex-wrap items-center justify-between gap-3" aria-live="polite">
        {codigoEnPausa &&
          !revision.isPending &&
          (existente ? (
            <span className="flex flex-wrap items-center gap-2 text-sm text-destructive">
              <TriangleAlert className="size-4" aria-hidden="true" />
              Ese código ya existe: {existente.nombre}
              <Link to={rutaActivo(existente.codigo)} className="text-brand-strong underline underline-offset-4">
                Abrir activo
              </Link>
            </span>
          ) : revision.data === null ? (
            <Badge variant="success">
              <Check aria-hidden="true" />
              Código libre
            </Badge>
          ) : null)}
        <Confirmacion alta={alta} texto="Revisé que coincide con el sticker: no se puede cambiar después" />
      </div>
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

/** Casilla «coincide con el sticker» (el código no se puede cambiar después). */
export function Confirmacion({ alta, texto }: { alta: AltaActivo; texto: string }) {
  const { errores } = alta
  return (
    <div className="flex flex-col gap-1">
      <label className="flex min-h-11 items-center gap-2 text-sm md:min-h-0">
        <Checkbox
          checked={alta.confirmado}
          onCheckedChange={(v) => alta.setConfirmado(v === true)}
          aria-invalid={Boolean(errores.confirmado)}
          aria-describedby={errores.confirmado ? 'confirmado-error' : undefined}
        />
        {texto}
      </label>
      {errores.confirmado && (
        <p id="confirmado-error" className="text-xs text-destructive">
          {errores.confirmado}
        </p>
      )}
    </div>
  )
}

/** Serial, marca, modelo, subtipo y fecha. Abiertos (escritorio) o plegados (teléfono). */
export function MasDatos({
  alta,
  plegable = false,
  soloSerial = false,
  claseControl,
}: {
  alta: AltaActivo
  plegable?: boolean
  /** Al duplicar (contador), lo demás lo copia el servidor. */
  soloSerial?: boolean
  claseControl?: string
}) {
  const { campos, errores } = alta
  const control = (campo: CampoAlta, extra?: string) => cn('max-md:h-11', claseControl, claseConservado(alta, campo), extra)
  const campos_ = (
    <>
      {!soloSerial && (
        <>
          <Campo id="marca" etiqueta={<Etiqueta conserva>Marca</Etiqueta>}>
            <InputSugerido campo="marca" id="marca" value={campos.marca} onChange={(e) => alta.cambiar('marca', e.target.value)} maxLength={120} autoComplete="off" className={control('marca')} />
          </Campo>
          <Campo id="modelo" etiqueta={<Etiqueta conserva>Modelo</Etiqueta>}>
            <InputSugerido campo="modelo" id="modelo" value={campos.modelo} onChange={(e) => alta.cambiar('modelo', e.target.value)} maxLength={120} autoComplete="off" className={control('modelo')} />
          </Campo>
          <Campo id="subtipo" etiqueta={<Etiqueta conserva>Subtipo</Etiqueta>} ayuda="Por ejemplo: computador, fuente, video.">
            <InputSugerido campo="subtipo" id="subtipo" value={campos.subtipo} onChange={(e) => alta.cambiar('subtipo', e.target.value)} maxLength={120} autoComplete="off" aria-describedby="subtipo-ayuda" className={control('subtipo')} />
          </Campo>
        </>
      )}
      <Campo id="serial" etiqueta="Serial" ayuda="No tiene que ser único.">
        <Input id="serial" value={campos.serial} onChange={(e) => alta.cambiar('serial', e.target.value)} maxLength={120} autoComplete="off" aria-describedby="serial-ayuda" className={control('serial', 'font-mono')} />
      </Campo>
      {!soloSerial && (
        <Campo id="fecha" etiqueta="Fecha de compra" error={errores.fecha}>
          <Input id="fecha" type="date" value={campos.fecha} onChange={(e) => alta.cambiar('fecha', e.target.value)} aria-invalid={Boolean(errores.fecha)} aria-describedby={errores.fecha ? 'fecha-error' : undefined} className={control('fecha')} />
        </Campo>
      )}
    </>
  )

  if (plegable) {
    return (
      <Collapsible className="rounded-lg border">
        <CollapsibleTrigger className="group flex min-h-12 w-full items-center gap-2 px-3 text-left text-[15px] font-medium">
          <ChevronDown className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
          <span className="truncate">Más datos (opcional)</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="flex flex-col gap-4 border-t p-3">{campos_}</CollapsibleContent>
      </Collapsible>
    )
  }
  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3 md:p-4">
      <p className="flex items-center justify-between text-sm font-medium">
        Más datos <span className="text-xs font-normal text-muted-foreground">opcional</span>
      </p>
      <div className="grid gap-4 md:grid-cols-3">{campos_}</div>
    </div>
  )
}

function Tarjeta({ titulo, children, className }: { titulo: ReactNode; children: ReactNode; className?: string }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className={cn('flex flex-col gap-2 rounded-xl border bg-card p-4', className)}>
      <h2 id={id} className="flex items-center gap-2 text-sm font-semibold">
        {titulo}
      </h2>
      {children}
    </section>
  )
}

/** «Copiar de un parecido» en la columna derecha. El contador no ve el precio copiado (P13). */
export function TarjetaCopiar({ alta, rol, claseBoton }: { alta: AltaActivo; rol: Rol; claseBoton?: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card p-4">
      <CopiarDeParecido onCopiar={alta.copiar} copiado={alta.copiado} className={claseBoton} />
      <p className="text-xs text-muted-foreground">
        {rol === 'admin'
          ? 'Copia nombre, categoría, marca, modelo, subtipo y precio; el código nunca.'
          : 'Al copiar, el precio lo copia el servidor y no se muestra.'}
      </p>
    </div>
  )
}

/** Foto opcional: arrastrar o elegir; se sube después de guardar. */
export function TarjetaFoto({ alta }: { alta: AltaActivo }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <CampoFoto
        zona
        etiqueta="Foto (opcional)"
        ayuda="Se sube después de guardar el activo, sin la ubicación del teléfono."
        archivo={alta.foto.archivo}
        onElegir={(f) => void alta.foto.elegir(f)}
        deshabilitado={alta.guardando}
      />
    </div>
  )
}

/** Resumen de lo que se va a guardar. El precio solo aparece para el admin (P13). */
export function Resumen({
  alta,
  rol,
  categorias,
  ubicaciones,
  children,
}: {
  alta: AltaActivo
  rol: Rol
  categorias: Categoria[]
  ubicaciones: Ubicacion[]
  children?: ReactNode
}) {
  const { campos, copiado, duplicando } = alta
  const precio = aPrecioCanonico(campos.precio)
  const filas: [string, ReactNode][] = [
    ['Código', <span className="font-mono">{normalizarCodigo(campos.codigo) ?? '—'}</span>],
    ['Nombre', (duplicando ? copiado?.nombre : campos.nombre.trim()) || '—'],
    ['Categoría', (duplicando ? copiado?.categoria.nombre : categorias.find((c) => c.id === campos.categoria)?.nombre) || '—'],
    ['Ubicación', (campos.ubicacion && rutaDe(ubicaciones, campos.ubicacion)) || '—'],
  ]
  if (rol === 'admin') filas.push(['Precio', <span className="tabular-nums">{precio ? formatCOP(precio) : '—'}</span>])
  return (
    <Tarjeta titulo="Resumen">
      <dl className="divide-y text-sm">
        {filas.map(([dt, dd]) => (
          <div key={dt} className="flex justify-between gap-3 py-1.5">
            <dt className="text-muted-foreground">{dt}</dt>
            <dd className="min-w-0 truncate text-right">{dd}</dd>
          </div>
        ))}
      </dl>
      {children}
    </Tarjeta>
  )
}

/** Nota de lo que conserva «Guardar y registrar otro». */
export function NotaRegistrarOtro() {
  return (
    <div className="rounded-lg bg-muted px-3 py-2 text-xs">
      <p className="flex items-center gap-1.5 font-medium">
        <Pin className="size-3.5" aria-hidden="true" />
        «Guardar y registrar otro»
      </p>
      <p className="text-muted-foreground">{NOTA_REGISTRAR_OTRO}</p>
    </div>
  )
}

/** Aviso tras «Guardar y registrar otro»: el activo quedó y se sigue con el siguiente. */
export function AvisoRegistrado({ activo, rutaActivo }: { activo: Activo; rutaActivo: (codigo: string) => string }) {
  return (
    <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl border border-success-border bg-success-soft px-4 py-3 text-sm">
      <CircleCheck className="size-5 shrink-0 text-success" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <b className="font-semibold">Activo creado:</b> {activo.nombre} · <span className="font-mono">{activo.codigo}</span> en {activo.ubicacion.ruta}. Ahora
        escanea el siguiente sticker.
      </span>
      <Link to={rutaActivo(activo.codigo)} className="text-brand-strong underline underline-offset-4">
        Ver el activo
      </Link>
    </div>
  )
}
