import { Check, CircleAlert, Info, RefreshCw, X } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { CampoFoto, EstadoFoto } from '@/components/app/CampoFoto'
import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { CountShell } from '@/components/app/CountShell'
import {
  AvisoRegistrado,
  CampoCodigo,
  Confirmacion,
  Etiqueta,
  MasDatos,
  NotaRegistrarOtro,
  Resumen,
  TarjetaCopiar,
  TarjetaFoto,
  TeclaBoton,
} from '@/components/app/FormularioAlta'
import { InputSugerido } from '@/components/app/InputSugerido'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import type { Activo } from '@/lib/activos'
import { claseConservado, type ErroresAlta, teclasDelAlta, useAltaActivo } from '@/lib/altaActivo'
import { useCategorias, useUbicaciones } from '@/lib/catalogo'
import { useSalaDeTrabajo } from '@/lib/conteo'
import { useRol } from '@/lib/sesion'
import { useSesionAbierta } from '@/lib/sesiones'
import { cn } from '@/lib/utils'

import { CabeceraEscritorio } from './Escritorio'

// Alta por escaneo (docs/08 §7.3, CU-CAT-02/03) a 375 px, en una columna (spec 004,
// T6). El código llega del sticker y es fijo. Obligatorios: nombre, precio, categoría
// y ubicación. El contador escribe el precio y después no lo ve; si copia de un
// parecido, el servidor copia el precio sin mostrarlo (P13, Q3).
// Spec 015, T10 (R11; Q9 = A; maqueta t10-contar-nuevo): en escritorio (≥ 1024 px y puntero
// fino), la cabecera del conteo y dos columnas (datos / copiar, foto y resumen sin precio
// para el contador), foco en Nombre, Enter guarda y Ctrl+Enter es «Guardar y registrar
// otro». En el teléfono, una columna como antes y «Guardar y registrar otro» en el pie.
// Tras «registrar otro» (o sin código en la URL) el código se escribe o se escanea. La
// ubicación empieza en la sala de trabajo del conteo, si hay una.

const rutaActivo = (codigo: string) => `/contar/activo/${encodeURIComponent(codigo)}`

function Campo({
  id,
  etiqueta,
  error,
  ayuda,
  compacto,
  children,
}: {
  id: string
  etiqueta: ReactNode
  error?: string
  ayuda?: string
  compacto: boolean
  children: ReactNode
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className={compacto ? undefined : 'text-[15px]'}>{etiqueta}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className={cn('flex items-center gap-1.5 text-destructive', compacto ? 'text-xs' : 'text-sm')}>
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        ayuda && <p id={`${id}-ayuda`} className={cn('text-muted-foreground', compacto ? 'text-xs' : 'text-sm')}>{ayuda}</p>
      )}
    </div>
  )
}

const Obligatorio = () => <span className="text-destructive" aria-hidden="true">*</span>
const aria = (errores: ErroresAlta, campo: keyof ErroresAlta, ayuda = false) => ({
  'aria-invalid': errores[campo] ? true : undefined,
  'aria-describedby': errores[campo] ? `${campo}-error` : ayuda ? `${campo}-ayuda` : undefined,
})

export default function Alta() {
  const [params] = useSearchParams()
  const rol = useRol()
  const escritorio = useEsEscritorio()
  const { sala } = useSalaDeTrabajo()
  const codigo = (params.get('codigo') ?? '').trim().toUpperCase()
  const alta = useAltaActivo({ rol, codigoInicial: codigo, ubicacionInicial: params.get('ubicacion') ?? '', ubicacionPorDefecto: sala })
  const categorias = useCategorias()
  const ubicaciones = useUbicaciones()
  const [registrado, setRegistrado] = useState<Activo | null>(null)
  const { campos, errores, copiado, duplicando } = alta
  // Sin código en la URL, o ya en el siguiente activo, el código se escribe o se escanea.
  const codigoEditable = !codigo || alta.ronda > 0

  // Foco inicial (solo en escritorio: en el teléfono el teclado taparía el formulario).
  // En una tarea aparte del render: el foco dispara el `onFocus` de las sugerencias (estado)
  // y React no puede procesarlo dentro de un efecto.
  useEffect(() => {
    if (!escritorio) return
    const reloj = setTimeout(() => (document.getElementById(codigoEditable ? 'codigo' : 'nombre') ?? document.getElementById('ubicacion'))?.focus(), 0)
    return () => clearTimeout(reloj)
  }, [escritorio, codigoEditable, alta.ronda])

  function guardar(otro: boolean) {
    alta.enviar({
      alCrear: otro
        ? (activo: Activo) => {
            setRegistrado(activo)
            alta.registrarOtro()
          }
        : undefined,
    })
  }

  const salirDelAlta = escritorio ? '/contar/escanear' : '/contar'

  if (alta.creado) {
    const aviso = (
      <Alert variant="success">
        <Check />
        <AlertTitle>Activo creado</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-2">
          <span>
            {alta.creado.nombre} · <span className="font-mono">{alta.creado.codigo}</span> quedó registrado en{' '}
            {alta.creado.ubicacion.ruta}.
          </span>
          <EstadoFoto estado={alta.foto.estado} error={alta.foto.error} onReintentar={alta.reintentarFoto} />
        </AlertDescription>
      </Alert>
    )
    if (escritorio) {
      return (
        <MarcoEscritorio red="guardado">
          <div className="flex flex-col gap-4 rounded-xl border bg-card p-6">
            <h1 className="text-xl font-semibold tracking-tight">Registrar activo</h1>
            {aviso}
            <div className="flex gap-2">
              <Button asChild>
                <Link to="/contar/escanear">Volver al conteo</Link>
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setRegistrado(null)
                  alta.otro()
                }}
              >
                Registrar otro
              </Button>
            </div>
          </div>
        </MarcoEscritorio>
      )
    }
    return (
      <CountShell titulo="Registrar activo" volver="/contar" estadoRed="guardado"
        acciones={
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar/escanear">Escanear otro</Link>
          </Button>
        }
      >
        <h1 className="sr-only">Registrar activo</h1>
        {aviso}
      </CountShell>
    )
  }

  const control = escritorio ? undefined : 'h-12 text-base'
  const ayudaUbicacion = sala && campos.ubicacion === sala ? 'Viene de la sala donde estás contando.' : 'Sala o box donde está el activo.'

  const avisos = (
    <>
      {registrado && <AvisoRegistrado activo={registrado} rutaActivo={rutaActivo} />}
      {alta.errorGeneral && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>No se guardó</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {alta.errorGeneral.mensaje}
            {alta.errorGeneral.reintentable && (
              <Button type="submit" form="alta" variant="outline" className="min-h-11 md:min-h-0">
                <RefreshCw />
                Reintentar
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}
      {alta.existente && (
        <Alert variant="warning">
          <Info />
          <AlertTitle>Ese código ya está registrado</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            Es {alta.existente.nombre}. Ábrelo en vez de crear otro.
            <Button asChild variant="outline" className="min-h-11 md:min-h-0">
              <Link to={rutaActivo(alta.existente.codigo)}>Abrir activo</Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}
    </>
  )

  const codigoFijo = (
    <>
      <div className={cn('flex items-center gap-3 bg-muted/50', escritorio ? 'border-b px-6 py-3' : 'rounded-xl border px-3 py-2')}>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-muted-foreground">Código del sticker · nuevo</p>
          <p className="font-mono text-lg tracking-wider break-all">{codigo}</p>
        </div>
        <Confirmacion alta={alta} texto={escritorio ? 'Coincide con el sticker' : 'Coincide'} />
      </div>
      {errores.codigo && (
        <p id="codigo-error" className={cn('flex items-center gap-1.5 text-sm text-destructive', escritorio ? 'px-6 pt-3' : '-mt-2')}>
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          {errores.codigo}
        </p>
      )}
    </>
  )

  const datos = (
    <>
      {duplicando ? (
        <Alert variant="info" className={escritorio ? 'md:col-span-2' : undefined}>
          <Info />
          <AlertTitle>Se copia de {copiado!.nombre}</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2 text-foreground">
            Nombre, categoría ({copiado!.categoria.nombre}), marca, modelo y precio se copian del original. El precio solo lo
            ven los administradores.
            <Button type="button" variant="ghost" className="min-h-11 px-1 text-brand-strong md:min-h-0" onClick={alta.quitarCopia}>
              <X />
              Quitar la copia
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <Campo compacto={escritorio} id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre}>
            <InputSugerido campo="nombre" id="nombre" value={campos.nombre} onChange={(e) => alta.cambiar('nombre', e.target.value)} maxLength={120} autoComplete="off" enterKeyHint="next" {...aria(errores, 'nombre')} className={control} />
          </Campo>
          <Campo compacto={escritorio} id="precio" etiqueta={<>Precio de compra (COP) <Obligatorio /></>} error={errores.precio} ayuda="Después de guardar, solo lo verán los administradores.">
            <div className="relative">
              <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" aria-hidden="true">$</span>
              <Input id="precio" value={campos.precio} onChange={(e) => alta.cambiar('precio', e.target.value)} inputMode="decimal" autoComplete="off" {...aria(errores, 'precio', true)} className={cn('pl-7 tabular-nums', control)} />
            </div>
          </Campo>
          <Campo compacto={escritorio} id="categoria" etiqueta={<Etiqueta conserva>Categoría <Obligatorio /></Etiqueta>} error={errores.categoria}>
            <Select value={campos.categoria} onValueChange={(v) => alta.cambiar('categoria', v)} disabled={categorias.isPending}>
              <SelectTrigger id="categoria" className={cn('w-full', !escritorio && 'h-12! text-base', claseConservado(alta, 'categoria'))} {...aria(errores, 'categoria')}>
                <SelectValue placeholder={categorias.isPending ? 'Cargando…' : 'Elige una categoría'} />
              </SelectTrigger>
              <SelectContent>
                {(categorias.data ?? []).map((c) => (
                  <SelectItem key={c.id} value={c.id} className="min-h-11 md:min-h-8">{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Campo>
        </>
      )}
      <Campo compacto={escritorio} id="ubicacion" etiqueta={<Etiqueta conserva>Ubicación <Obligatorio /></Etiqueta>} error={errores.ubicacion} ayuda={ayudaUbicacion}>
        <LocationPicker
          id="ubicacion"
          ubicaciones={ubicaciones.data ?? []}
          cargando={ubicaciones.isPending}
          valor={campos.ubicacion || undefined}
          onChange={(v) => alta.cambiar('ubicacion', v)}
          className={cn(!escritorio && 'h-12 text-base md:h-12', claseConservado(alta, 'ubicacion'))}
        />
      </Campo>
    </>
  )

  const teclas = {
    onKeyDown: (e: KeyboardEvent<HTMLFormElement>) =>
      teclasDelAlta(e, { guardar: () => guardar(false), guardarYOtro: () => guardar(true), ocupado: alta.guardando }),
  }
  const enviar = (evento: FormEvent) => {
    evento.preventDefault()
    guardar(false)
  }
  const textoGuardar = alta.guardando ? 'Guardando…' : 'Guardar activo'

  if (escritorio) {
    return (
      <MarcoEscritorio red="en_linea">
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="flex min-w-0 flex-col gap-4">
            {avisos}
            <form id="alta" noValidate onSubmit={enviar} {...teclas} className="flex flex-col rounded-xl border bg-card">
              <div className="flex items-center justify-between gap-3 border-b px-6 py-4">
                <div>
                  <h1 className="text-xl font-semibold tracking-tight">Registrar activo</h1>
                  <p className="text-sm text-muted-foreground">
                    {codigoEditable ? 'Escanea el sticker con el lector o escribe el código impreso.' : 'El sticker no está registrado. Completa lo obligatorio y guarda.'}
                  </p>
                </div>
                <Link to="/contar/escanear" className="text-sm text-brand-strong underline underline-offset-4">
                  Volver al conteo
                </Link>
              </div>
              {codigoEditable ? (
                <div className="border-b px-6 py-5">
                  <CampoCodigo alta={alta} rutaActivo={rutaActivo} />
                </div>
              ) : (
                codigoFijo
              )}
              <div className="grid gap-4 px-6 py-5 md:grid-cols-2">{datos}</div>
              <div className="px-6 pb-5">
                <MasDatos alta={alta} soloSerial={duplicando} />
              </div>
              <div className="flex items-center justify-between gap-2 rounded-b-xl border-t bg-sidebar px-6 py-3">
                <Button asChild variant="ghost">
                  <Link to={salirDelAlta}>Cancelar</Link>
                </Button>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" disabled={alta.guardando} onClick={() => guardar(true)}>
                    Guardar y registrar otro
                    <TeclaBoton>Ctrl Enter</TeclaBoton>
                  </Button>
                  <Button type="submit" disabled={alta.guardando}>
                    {textoGuardar}
                    {!alta.guardando && <TeclaBoton oscura>Enter</TeclaBoton>}
                  </Button>
                </div>
              </div>
            </form>
          </div>
          <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-24">
            <TarjetaCopiar alta={alta} rol={rol} />
            <TarjetaFoto alta={alta} />
            <Resumen alta={alta} rol={rol} categorias={categorias.data ?? []} ubicaciones={ubicaciones.data ?? []}>
              {rol !== 'admin' && <p className="text-xs text-muted-foreground">El precio no se muestra aquí; después de guardar, solo lo ven los administradores.</p>}
              <NotaRegistrarOtro />
            </Resumen>
          </aside>
        </div>
      </MarcoEscritorio>
    )
  }

  return (
    <CountShell
      titulo="Registrar activo"
      volver="/contar/escribir"
      estadoRed="en_linea"
      acciones={
        <>
          <Button type="button" variant="outline" disabled={alta.guardando} onClick={() => guardar(true)}>
            Guardar y registrar otro
          </Button>
          <Button type="submit" form="alta" className="min-h-14 font-semibold" disabled={alta.guardando}>
            {textoGuardar}
          </Button>
        </>
      }
    >
      <h1 className="sr-only">Registrar activo</h1>
      <form id="alta" noValidate onSubmit={enviar} {...teclas} className="flex flex-col gap-4">
        {avisos}
        {codigoEditable ? <CampoCodigo alta={alta} rutaActivo={rutaActivo} /> : codigoFijo}
        <CopiarDeParecido onCopiar={alta.copiar} copiado={copiado} className="h-12 text-base md:h-12" />
        {datos}
        <MasDatos alta={alta} plegable soloSerial={duplicando} claseControl="h-12 text-base" />
        <CampoFoto archivo={alta.foto.archivo} onElegir={(f) => void alta.foto.elegir(f)} deshabilitado={alta.guardando} />
      </form>
    </CountShell>
  )
}

/** Escritorio: la cabecera del conteo (sesión, sala, avance) y el contenido centrado. */
function MarcoEscritorio({ red, children }: { red: 'en_linea' | 'guardado'; children: ReactNode }) {
  const sesion = useSesionAbierta()
  return (
    <div className="flex min-h-svh flex-1 flex-col bg-sidebar">
      <CabeceraEscritorio sesion={sesion.data ?? null} cargando={sesion.isPending} red={red} />
      <div className="mx-auto w-full max-w-[1320px] flex-1 px-6 py-6">{children}</div>
    </div>
  )
}
