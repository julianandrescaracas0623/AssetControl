import { Camera, Check, Pin, TriangleAlert, Usb } from 'lucide-react'
import { type ReactNode, type RefObject, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { CampoFoto } from '@/components/app/CampoFoto'
import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { Escaner } from '@/components/app/Escaner'
import { InputSugerido } from '@/components/app/InputSugerido'
import { Aviso, Boton, Dialogo, Insignia, ListaDatos, MarcaObligatorio, MarcoCampo, Panel, Tecla } from '@/components/kit'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { type Activo, aPrecioCanonico, normalizarCodigo, useActivoPorCodigo } from '@/lib/activos'
import type { Categoria, Rol, Ubicacion } from '@/lib/api/cliente'
import { type AltaActivo, claseControlAlta } from '@/lib/altaActivo'
import { rutaDe } from '@/lib/catalogo'
import { formatCOP } from '@/lib/format'
import { cn } from '@/lib/utils'

// Piezas comunes de «Registrar activo» (spec 015, T10; R11; Q9 = A; maquetas t10-*): las
// usan el alta de administración y la del modo conteo. Teclado: el `Enter` del lector USB
// en el código pasa a Nombre (no guarda); `Enter` en los demás campos de texto guarda;
// `Ctrl+Enter` (o `Cmd+Enter`) es «Guardar y registrar otro». El estado y el envío siguen
// en `useAltaActivo` (UUID del cliente, idempotente); aquí no se decide nada de dominio.
// Spec 016, T6: presentación con el kit. Marco de campo del kit (etiqueta, ayuda y error
// con los mismos ids), controles sobre blanco con la altura de la densidad (48 px en el
// conteo y en admin < md, 36 px en admin ≥ md), paneles del kit en la columna derecha,
// avisos del kit y teclas del kit (la del botón principal sin relleno: Deuda T1 b).

export const NOTA_REGISTRAR_OTRO = 'Conserva categoría, ubicación, marca, modelo y subtipo. Borra código, nombre, serial, precio y foto.'

/** Pasa al primer dato después del código (Nombre o, si se duplica, Ubicación). */
function siguienteDespuesDelCodigo() {
  ;(document.getElementById('nombre') ?? document.getElementById('ubicacion'))?.focus()
}

/** Marca «se conserva» junto a la etiqueta de un campo que conserva «registrar otro». */
export function SeConserva() {
  return (
    <span className="ml-auto inline-flex items-center gap-1 text-xs font-normal text-muted-foreground" title="Se conserva al registrar otro">
      <Pin className="size-3" aria-hidden="true" />
      se conserva
    </span>
  )
}

/** Etiqueta con la marca «se conserva» (dentro de la etiqueta para que se anuncie). */
export function Etiqueta({ children, conserva = false }: { children: ReactNode; conserva?: boolean }) {
  return (
    <span className="flex w-full items-center gap-1.5">
      <span className="flex items-center gap-2">{children}</span>
      {conserva && <SeConserva />}
    </span>
  )
}

/** Atajo de teclado en un botón (solo visible en escritorio; no cambia el nombre accesible). */
export function TeclaBoton({ children, oscura = false }: { children: ReactNode; oscura?: boolean }) {
  return (
    <Tecla soloEscritorio tono={oscura ? 'sobrePrincipal' : 'normal'} className="ml-1">
      {children}
    </Tecla>
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
      <MarcoCampo id="codigo" etiqueta="Código del sticker" obligatorio error={errorCodigo}>
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
          className={cn(claseControlAlta(alta), 'font-mono text-lg tracking-wider uppercase md:text-base', className)}
        />
      </MarcoCampo>
      <p className="-mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-etiqueta font-normal text-muted-foreground">
        <span className="hidden items-center gap-1.5 md:flex">
          <Usb className="size-3.5 shrink-0 text-success" aria-hidden="true" />
          El cursor empieza aquí. El lector USB escribe el código y su Enter pasa a Nombre (no guarda).
        </span>
        <Boton variante="fantasma" icono={<Camera />} className="-ml-2 px-2 text-brand-strong" onClick={() => setEscaneando(true)}>
          Usar la cámara
        </Boton>
      </p>
      <div id="codigo-estado" className="flex flex-wrap items-center justify-between gap-3" aria-live="polite">
        {codigoEnPausa &&
          !revision.isPending &&
          (existente ? (
            <span className="flex flex-wrap items-center gap-2 text-etiqueta text-destructive">
              <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
              Ese código ya existe: {existente.nombre}
              <Link
                to={rutaActivo(existente.codigo)}
                className="rounded-sm text-brand-strong underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                Abrir activo
              </Link>
            </span>
          ) : revision.data === null ? (
            <Insignia tono="exito" icono={<Check aria-hidden="true" />}>
              Código libre
            </Insignia>
          ) : null)}
        <Confirmacion alta={alta} texto="Revisé que coincide con el sticker: no se puede cambiar después" />
      </div>
      <Dialogo abierto={escaneando} onAbiertoChange={setEscaneando} forma="centrado" titulo="Escanear el sticker" descripcion="Apunta la cámara al código de barras; se lee solo.">
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
      </Dialogo>
    </div>
  )
}

/** Casilla «coincide con el sticker» (el código no se puede cambiar después). */
export function Confirmacion({ alta, texto }: { alta: AltaActivo; texto: string }) {
  const { errores } = alta
  return (
    <div className="flex flex-col gap-1">
      <label className="flex min-h-control cursor-pointer items-center gap-2.5 text-cuerpo">
        <Checkbox
          checked={alta.confirmado}
          onCheckedChange={(v) => alta.setConfirmado(v === true)}
          aria-invalid={Boolean(errores.confirmado)}
          aria-describedby={errores.confirmado ? 'confirmado-error' : undefined}
          className="size-5 bg-card"
        />
        {texto}
      </label>
      {errores.confirmado && (
        <p id="confirmado-error" className="text-etiqueta font-normal text-destructive">
          {errores.confirmado}
        </p>
      )}
    </div>
  )
}

/** Categoría: lista cerrada de la clínica (cero digitación); resalta si se conservó. */
export function CampoCategoria({
  alta,
  categorias,
  cargando,
  ayuda,
}: {
  alta: AltaActivo
  categorias: Categoria[]
  cargando: boolean
  ayuda?: string
}) {
  const { campos, errores } = alta
  const describedBy = errores.categoria ? 'categoria-error' : ayuda ? 'categoria-ayuda' : undefined
  return (
    <MarcoCampo id="categoria" etiqueta={<Etiqueta conserva>Categoría <MarcaObligatorio /></Etiqueta>} error={errores.categoria} ayuda={ayuda}>
      <Select value={campos.categoria} onValueChange={(v) => alta.cambiar('categoria', v)} disabled={cargando}>
        <SelectTrigger
          id="categoria"
          aria-invalid={errores.categoria ? true : undefined}
          aria-describedby={describedBy}
          className={claseControlAlta(alta, 'categoria', 'w-full data-[size=default]:h-control')}
        >
          <SelectValue placeholder={cargando ? 'Cargando…' : 'Elige una categoría'} />
        </SelectTrigger>
        <SelectContent>
          {categorias.map((c) => (
            <SelectItem key={c.id} value={c.id} className="min-h-control md:min-h-8">
              {c.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </MarcoCampo>
  )
}

/** Serial, marca, modelo, subtipo y fecha. Abiertos (escritorio) o plegados (teléfono). */
export function MasDatos({
  alta,
  plegable = false,
  soloSerial = false,
}: {
  alta: AltaActivo
  plegable?: boolean
  /** Al duplicar (contador), lo demás lo copia el servidor. */
  soloSerial?: boolean
}) {
  const { campos, errores } = alta
  const campos_ = (
    <>
      {!soloSerial && (
        <>
          <MarcoCampo id="marca" etiqueta={<Etiqueta conserva>Marca</Etiqueta>}>
            <InputSugerido campo="marca" id="marca" value={campos.marca} onChange={(e) => alta.cambiar('marca', e.target.value)} maxLength={120} autoComplete="off" className={claseControlAlta(alta, 'marca')} />
          </MarcoCampo>
          <MarcoCampo id="modelo" etiqueta={<Etiqueta conserva>Modelo</Etiqueta>}>
            <InputSugerido campo="modelo" id="modelo" value={campos.modelo} onChange={(e) => alta.cambiar('modelo', e.target.value)} maxLength={120} autoComplete="off" className={claseControlAlta(alta, 'modelo')} />
          </MarcoCampo>
          <MarcoCampo id="subtipo" etiqueta={<Etiqueta conserva>Subtipo</Etiqueta>} ayuda="Por ejemplo: computador, fuente, video.">
            <InputSugerido campo="subtipo" id="subtipo" value={campos.subtipo} onChange={(e) => alta.cambiar('subtipo', e.target.value)} maxLength={120} autoComplete="off" aria-describedby="subtipo-ayuda" className={claseControlAlta(alta, 'subtipo')} />
          </MarcoCampo>
        </>
      )}
      <MarcoCampo id="serial" etiqueta="Serial" ayuda="No tiene que ser único.">
        <Input id="serial" value={campos.serial} onChange={(e) => alta.cambiar('serial', e.target.value)} maxLength={120} autoComplete="off" aria-describedby="serial-ayuda" className={claseControlAlta(alta, 'serial', 'font-mono')} />
      </MarcoCampo>
      {!soloSerial && (
        <MarcoCampo id="fecha" etiqueta="Fecha de compra" error={errores.fecha}>
          <Input id="fecha" type="date" value={campos.fecha} onChange={(e) => alta.cambiar('fecha', e.target.value)} aria-invalid={Boolean(errores.fecha)} aria-describedby={errores.fecha ? 'fecha-error' : undefined} className={claseControlAlta(alta, 'fecha')} />
        </MarcoCampo>
      )}
    </>
  )

  if (plegable) {
    return (
      <Panel plegable titulo="Más datos (opcional)">
        <div className="flex flex-col gap-4">{campos_}</div>
      </Panel>
    )
  }
  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/40 p-3 md:p-4">
      <p className="flex items-center justify-between text-etiqueta text-foreground">
        Más datos <span className="font-normal text-muted-foreground">opcional</span>
      </p>
      <div className="grid gap-4 md:grid-cols-3">{campos_}</div>
    </div>
  )
}

/** «Copiar de un parecido» en la columna derecha. El contador no ve el precio copiado (P13). */
export function TarjetaCopiar({ alta, rol, claseBoton }: { alta: AltaActivo; rol: Rol; claseBoton?: string }) {
  return (
    <Panel>
      <div className="flex flex-col gap-2">
        <CopiarDeParecido onCopiar={alta.copiar} copiado={alta.copiado} className={cn('h-control bg-card md:h-control', claseBoton)} />
        <p className="text-etiqueta font-normal text-muted-foreground">
          {rol === 'admin'
            ? 'Copia nombre, categoría, marca, modelo, subtipo y precio; el código nunca.'
            : 'Al copiar, el precio lo copia el servidor y no se muestra.'}
        </p>
      </div>
    </Panel>
  )
}

/** Foto opcional: arrastrar o elegir; se sube después de guardar. */
export function TarjetaFoto({ alta }: { alta: AltaActivo }) {
  return (
    <Panel>
      <CampoFoto
        zona
        etiqueta="Foto (opcional)"
        ayuda="Se sube después de guardar el activo, sin la ubicación del teléfono."
        archivo={alta.foto.archivo}
        onElegir={(f) => void alta.foto.elegir(f)}
        deshabilitado={alta.guardando}
      />
    </Panel>
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
  return (
    <Panel titulo="Resumen">
      <div className="flex flex-col gap-3">
        <ListaDatos
          className="-mt-2 [&>div]:min-h-0 [&>div]:py-2"
          datos={[
            { rotulo: 'Código', valor: normalizarCodigo(campos.codigo) ?? '—', tipo: 'codigo' },
            { rotulo: 'Nombre', valor: <span className="block truncate">{(duplicando ? copiado?.nombre : campos.nombre.trim()) || '—'}</span> },
            { rotulo: 'Categoría', valor: (duplicando ? copiado?.categoria.nombre : categorias.find((c) => c.id === campos.categoria)?.nombre) || '—' },
            { rotulo: 'Ubicación', valor: <span className="block truncate">{(campos.ubicacion && rutaDe(ubicaciones, campos.ubicacion)) || '—'}</span> },
            // El contador no recibe el rótulo ni un hueco (P13).
            rol === 'admin' && { rotulo: 'Precio', valor: precio ? formatCOP(precio) : '—', tipo: 'cifra' },
          ]}
        />
        {children}
      </div>
    </Panel>
  )
}

/** Nota de lo que conserva «Guardar y registrar otro». */
export function NotaRegistrarOtro() {
  return (
    <div className="rounded-lg bg-muted px-3 py-2 text-etiqueta font-normal">
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
    <Aviso
      tono="exito"
      titulo="Activo creado"
      accion={
        <Boton asChild variante="secundario">
          <Link to={rutaActivo(activo.codigo)}>Ver el activo</Link>
        </Boton>
      }
    >
      <span>
        {activo.nombre} · <span className="font-mono">{activo.codigo}</span> en {activo.ubicacion.ruta}. Ahora escanea el siguiente sticker.
      </span>
    </Aviso>
  )
}
