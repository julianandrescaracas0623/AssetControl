import { RefreshCw } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { EstadoFoto } from '@/components/app/CampoFoto'
import {
  AvisoRegistrado,
  CampoCategoria,
  CampoCodigo,
  Etiqueta,
  MasDatos,
  NotaRegistrarOtro,
  Resumen,
  TarjetaCopiar,
  TarjetaFoto,
  TeclaBoton,
  VariasUnidades,
} from '@/components/app/FormularioAlta'
import { InputSugerido } from '@/components/app/InputSugerido'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Aviso, Boton, Campo, EncabezadoPagina, MarcaObligatorio, MarcoCampo, Panel } from '@/components/kit'
import { useIsMobile } from '@/hooks/use-mobile'
import type { Activo } from '@/lib/activos'
import { claseControlAlta, teclasDelAlta, useAltaActivo } from '@/lib/altaActivo'
import { useCategorias, useUbicaciones } from '@/lib/catalogo'
import { cn } from '@/lib/utils'
import { rutaActivo, rutaApp } from '@/lib/rutas'

// Registrar activo desde administración (decisión del humano 2026-11-13; D3; spec 004,
// T6). R8: sin código de sticker no hay alta. Obligatorios: código, nombre, precio,
// categoría y ubicación; solo se teclean nombre y precio (lo demás se elige o se copia
// de un parecido). La validación definitiva es del servidor.
// Spec 015, T10 (R11; Q9 = A; maqueta t10-registrar-A): dos columnas en escritorio (datos a
// la izquierda; copiar, foto y resumen a la derecha), «Más datos» a la vista, foco inicial
// en el código, Enter del lector pasa a Nombre, Enter guarda y Ctrl+Enter es «Guardar y
// registrar otro» (conserva categoría, ubicación, marca, modelo y subtipo).
// Spec 016, T8 (R2, R5, R10): presentación con el kit, como el alta de escritorio del
// conteo (T6): el formulario en un Panel con su pie de acciones (pegado abajo en el
// teléfono; sin el fondo de la barra lateral, Deuda T1 e), avisos y campos del kit, y la
// columna derecha con paneles. Mismos pasos, mismos campos, mismas llamadas e idempotencia.

const FORMULARIO = 'registrar-activo'

function Paso({ n, titulo, nota, children }: { n: number; titulo: string; nota?: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 border-b px-4 py-5 last:border-b-0 md:px-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex size-6 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-strong" aria-hidden="true">
            {n}
          </span>
          <h2 id={id} className="text-titulo-seccion">
            {titulo}
          </h2>
        </div>
        {nota && <p className="text-etiqueta font-normal text-muted-foreground">{nota}</p>}
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

  const encabezado = (
    <EncabezadoPagina
      titulo="Registrar activo"
      descripcion="Una fila por unidad física. Escanea el sticker con el lector o escribe el código impreso."
    />
  )

  if (alta.creado) {
    return (
      <div className="flex flex-col gap-6">
        {encabezado}
        <Aviso
          tono="exito"
          titulo="Activo creado"
          className="max-w-2xl"
          accion={
            <>
              <Boton
                onClick={() => {
                  setRegistrado(null)
                  alta.otro()
                }}
              >
                Registrar otro
              </Boton>
              <Boton asChild variante="secundario">
                <Link to={rutaActivo(alta.creado.codigo)}>Ver el activo</Link>
              </Boton>
            </>
          }
        >
          <div className="flex flex-col items-start gap-2">
            <span>
              {alta.creado.nombre} · <span className="font-mono">{alta.creado.codigo}</span> quedó registrado en {alta.creado.ubicacion.ruta}.
            </span>
            <EstadoFoto estado={alta.foto.estado} error={alta.foto.error} onReintentar={alta.reintentarFoto} />
          </div>
        </Aviso>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {encabezado}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-4">
          {registrado && <AvisoRegistrado activo={registrado} rutaActivo={rutaActivo} />}
          {alta.errorGeneral && (
            <Aviso
              tono="error"
              titulo="No se guardó"
              accion={
                alta.errorGeneral.reintentable && (
                  <Boton type="submit" form={FORMULARIO} variante="secundario" icono={<RefreshCw />}>
                    Reintentar
                  </Boton>
                )
              }
            >
              {alta.errorGeneral.mensaje}
            </Aviso>
          )}
          <form
            id={FORMULARIO}
            noValidate
            onSubmit={(evento) => {
              evento.preventDefault()
              guardar(false)
            }}
            onKeyDown={(e) => teclasDelAlta(e, { guardar: () => guardar(false), guardarYOtro: () => guardar(true), ocupado: alta.guardando })}
          >
            <Panel
              relleno={false}
              pieFijo
              pie={
                <>
                  <Boton asChild variante="fantasma" className="max-md:hidden">
                    <Link to={rutaApp('activos')}>Cancelar</Link>
                  </Boton>
                  <div className="flex w-full flex-col-reverse gap-separacion sm:ml-auto sm:w-auto sm:flex-row">
                    <Boton variante="secundario" disabled={alta.guardando} onClick={() => guardar(true)}>
                      Guardar y registrar otro
                      <TeclaBoton>Ctrl Enter</TeclaBoton>
                    </Boton>
                    <Boton type="submit" cargando={alta.guardando} textoCargando="Guardando…">
                      Guardar activo
                      <TeclaBoton oscura>Enter</TeclaBoton>
                    </Boton>
                  </div>
                </>
              }
            >
              <Paso n={1} titulo="Código del sticker">
                <CampoCodigo alta={alta} rutaActivo={rutaActivo} campoRef={codigoRef} />
              </Paso>

              <Paso n={2} titulo="Datos del activo" nota="Solo se teclean nombre y precio; lo demás se elige.">
                <div className="grid gap-4 md:grid-cols-2">
                  <MarcoCampo id="nombre" etiqueta="Nombre" obligatorio error={errores.nombre}>
                    <InputSugerido
                      campo="nombre"
                      id="nombre"
                      value={campos.nombre}
                      onChange={(e) => alta.cambiar('nombre', e.target.value)}
                      maxLength={120}
                      autoComplete="off"
                      aria-required
                      aria-invalid={Boolean(errores.nombre)}
                      aria-describedby={errores.nombre ? 'nombre-error' : undefined}
                      className={claseControlAlta(alta)}
                    />
                  </MarcoCampo>
                  <Campo
                    id="precio"
                    tipo="dinero"
                    etiqueta="Precio de compra (COP)"
                    obligatorio
                    error={errores.precio}
                    ayuda="Solo lo ven los administradores."
                    value={campos.precio}
                    onChange={(e) => alta.cambiar('precio', e.target.value)}
                    autoComplete="off"
                  />
                  <CampoCategoria alta={alta} categorias={categorias.data ?? []} cargando={categorias.isPending} ayuda="Lista cerrada de la clínica." />
                  <MarcoCampo id="ubicacion" etiqueta={<Etiqueta conserva>Ubicación <MarcaObligatorio /></Etiqueta>} error={errores.ubicacion} ayuda="Una sala o un box activos.">
                    <LocationPicker
                      id="ubicacion"
                      ubicaciones={ubicaciones.data ?? []}
                      cargando={ubicaciones.isPending}
                      valor={campos.ubicacion || undefined}
                      onChange={(v) => alta.cambiar('ubicacion', v)}
                      className={claseControlAlta(alta, 'ubicacion', cn('md:h-control', errores.ubicacion && 'border-destructive'))}
                    />
                  </MarcoCampo>
                </div>
                <MasDatos alta={alta} />
              </Paso>
            </Panel>
          </form>
        </div>

        <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-20">
          <TarjetaCopiar alta={alta} rol="admin" />
          <TarjetaFoto alta={alta} />
          <Resumen alta={alta} rol="admin" categorias={categorias.data ?? []} ubicaciones={ubicaciones.data ?? []}>
            {/* Con varias unidades se conservan nombre y precio: la nota no aplica. */}
            {!varias && <NotaRegistrarOtro />}
            <VariasUnidades activo={varias} onCambio={setVarias} />
          </Resumen>
        </aside>
      </div>
    </div>
  )
}
