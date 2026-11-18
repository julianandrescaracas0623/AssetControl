import { Check, CircleAlert, Loader2, RefreshCw } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { EstadoFoto } from '@/components/app/CampoFoto'
import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { EncabezadoPagina } from '@/components/app/ConEstado'
import {
  AvisoRegistrado,
  CampoCodigo,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useIsMobile } from '@/hooks/use-mobile'
import type { Activo } from '@/lib/activos'
import { claseConservado, type ErroresAlta, teclasDelAlta, useAltaActivo } from '@/lib/altaActivo'
import { useCategorias, useUbicaciones } from '@/lib/catalogo'
import { cn } from '@/lib/utils'

// Registrar activo desde administración (decisión del humano 2026-11-13; D3; spec 004,
// T6). R8: sin código de sticker no hay alta. Obligatorios: código, nombre, precio,
// categoría y ubicación; solo se teclean nombre y precio (lo demás se elige o se copia
// de un parecido). La validación definitiva es del servidor.
// Spec 015, T10 (R11; Q9 = A; maqueta t10-registrar-A): dos columnas en escritorio (datos a
// la izquierda; copiar, foto y resumen a la derecha), «Más datos» a la vista, foco inicial
// en el código, Enter del lector pasa a Nombre, Enter guarda y Ctrl+Enter es «Guardar y
// registrar otro» (conserva categoría, ubicación, marca, modelo y subtipo).

const rutaActivo = (codigo: string) => `/admin/activos/${encodeURIComponent(codigo)}`

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
  const alta = useAltaActivo({ rol: 'admin' })
  const categorias = useCategorias()
  const ubicaciones = useUbicaciones()
  const movil = useIsMobile()
  const [varias, setVarias] = useState(false)
  const [registrado, setRegistrado] = useState<Activo | null>(null)
  const codigoRef = useRef<HTMLInputElement>(null)
  const { campos, errores } = alta

  // Foco en el código al abrir (en el teléfono no, para no tapar el formulario con el
  // teclado) y cada vez que el formulario queda listo para el siguiente sticker.
  const enfocar = !movil || alta.ronda > 0
  useEffect(() => {
    if (enfocar) codigoRef.current?.focus()
  }, [enfocar, alta.ronda])

  function guardar(otro: boolean) {
    alta.enviar({
      alCrear:
        otro || varias
          ? (activo: Activo) => {
              setRegistrado(activo)
              if (varias) alta.siguienteUnidad()
              else alta.registrarOtro()
            }
          : undefined,
    })
  }

  const describir = (campo: keyof ErroresAlta, ayuda = false) => (errores[campo] ? `${campo}-error` : ayuda ? `${campo}-ayuda` : undefined)

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Registrar activo"
        descripcion="Una fila por unidad física. Escanea el sticker con el lector o escribe el código impreso."
      />

      {alta.creado ? (
        <Alert variant="success" role="status">
          <Check />
          <AlertTitle>Activo creado</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>
              {alta.creado.nombre} · <span className="font-mono">{alta.creado.codigo}</span> quedó registrado en {alta.creado.ubicacion.ruta}.
            </span>
            <EstadoFoto estado={alta.foto.estado} error={alta.foto.error} onReintentar={alta.reintentarFoto} />
            <span className="flex flex-wrap gap-2 [&_[data-slot=button]]:max-md:min-h-11">
              <Button
                size="sm"
                onClick={() => {
                  setRegistrado(null)
                  alta.otro()
                }}
              >
                Registrar otro
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to={rutaActivo(alta.creado.codigo)}>Ver el activo</Link>
              </Button>
            </span>
          </AlertDescription>
        </Alert>
      ) : (
        <>
          {registrado && <AvisoRegistrado activo={registrado} rutaActivo={rutaActivo} />}
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <form
              noValidate
              className="flex flex-col rounded-xl border bg-card"
              onSubmit={(evento) => {
                evento.preventDefault()
                guardar(false)
              }}
              onKeyDown={(e) => teclasDelAlta(e, { guardar: () => guardar(false), guardarYOtro: () => guardar(true), ocupado: alta.guardando })}
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
                <CampoCodigo alta={alta} rutaActivo={rutaActivo} campoRef={codigoRef} />
              </Paso>

              <Paso n={2} titulo="Datos del activo" nota="Solo se teclean nombre y precio; lo demás se elige.">
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
                  <Campo id="categoria" etiqueta={<Etiqueta conserva>Categoría <Obligatorio /></Etiqueta>} error={errores.categoria} ayuda="Lista cerrada de la clínica.">
                    <Select value={campos.categoria} onValueChange={(v) => alta.cambiar('categoria', v)} disabled={categorias.isPending}>
                      <SelectTrigger id="categoria" className={cn('w-full max-md:h-11', claseConservado(alta, 'categoria'))} aria-invalid={Boolean(errores.categoria)} aria-describedby={describir('categoria', true)}>
                        <SelectValue placeholder={categorias.isPending ? 'Cargando…' : 'Elige una categoría'} />
                      </SelectTrigger>
                      <SelectContent>
                        {(categorias.data ?? []).map((c) => (
                          <SelectItem key={c.id} value={c.id}>{c.nombre}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Campo>
                  <Campo id="ubicacion" etiqueta={<Etiqueta conserva>Ubicación <Obligatorio /></Etiqueta>} error={errores.ubicacion} ayuda="Una sala o un box activos.">
                    <LocationPicker
                      id="ubicacion"
                      ubicaciones={ubicaciones.data ?? []}
                      cargando={ubicaciones.isPending}
                      valor={campos.ubicacion || undefined}
                      onChange={(v) => alta.cambiar('ubicacion', v)}
                      className={cn(errores.ubicacion && 'border-destructive', claseConservado(alta, 'ubicacion'))}
                    />
                  </Campo>
                </div>
                <MasDatos alta={alta} />
              </Paso>

              <div className="flex flex-col-reverse gap-2 rounded-b-xl border-t bg-sidebar px-4 py-3 max-md:sticky max-md:bottom-0 max-md:z-20 max-md:bg-background sm:flex-row sm:items-center sm:justify-between md:px-6 [&_[data-slot=button]]:max-md:min-h-11">
                <Button asChild variant="ghost" className="max-md:hidden">
                  <Link to="/admin/activos">Cancelar</Link>
                </Button>
                <div className="flex flex-col-reverse gap-2 sm:flex-row">
                  <Button type="button" variant="outline" disabled={alta.guardando} onClick={() => guardar(true)}>
                    Guardar y registrar otro
                    <TeclaBoton>Ctrl Enter</TeclaBoton>
                  </Button>
                  <Button type="submit" disabled={alta.guardando}>
                    {alta.guardando ? (
                      <>
                        <Loader2 className="animate-spin" aria-hidden="true" />
                        Guardando…
                      </>
                    ) : (
                      <>
                        Guardar activo
                        <TeclaBoton oscura>Enter</TeclaBoton>
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </form>

            <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-20">
              <TarjetaCopiar alta={alta} rol="admin" />
              <TarjetaFoto alta={alta} />
              <Resumen alta={alta} rol="admin" categorias={categorias.data ?? []} ubicaciones={ubicaciones.data ?? []}>
                {/* Con varias unidades se conservan nombre y precio: la nota no aplica. */}
                {!varias && <NotaRegistrarOtro />}
                <label className="flex items-start justify-between gap-3 border-t pt-3 text-sm">
                  <span>
                    <span className="block font-medium">Varias unidades iguales</span>
                    <span className="block text-xs text-muted-foreground">Al guardar, conserva todo menos código y serial (también nombre y precio).</span>
                  </span>
                  <Switch checked={varias} onCheckedChange={setVarias} className="mt-0.5" />
                </label>
              </Resumen>
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
