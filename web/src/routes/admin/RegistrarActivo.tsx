import { RefreshCw, X } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'

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
import { type Activo, normalizarCodigo } from '@/lib/activos'
import { claseControlAlta, teclasDelAlta, useAltaActivo } from '@/lib/altaActivo'
import { useCategorias, useUbicaciones } from '@/lib/catalogo'
import { useSalaDeTrabajo } from '@/lib/conteo'
import { cn } from '@/lib/utils'
import { rutaActivo, rutaApp } from '@/lib/rutas'
import { useRol } from '@/lib/sesion'

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
// Spec 020, T5 (R6; P13): en el computador es el alta de los dos roles (el conteo de
// escritorio enlaza aquí con `?codigo=` y /contar/nuevo redirige con su query). El código
// de la URL llega cargado y el cursor empieza en Nombre; la ubicación empieza en la sala
// donde se está contando, si hay una. El contador escribe el precio y después no lo ve:
// no está en el resumen ni en «Activo creado»; al copiar de un parecido lo copia el
// servidor (con nombre y categoría) y aquí solo se elige la ubicación y el serial, como en
// el alta del conteo. «Varias unidades iguales» deja el precio a la vista: solo el admin.
// Solo un código válido de la URL entra al campo. Si se llegó desde el conteo (state
// `{ desde: 'conteo' }`), «Volver al conteo» sustituye a «Cancelar» y sale en «Activo creado».

const FORMULARIO = 'registrar-activo'
const RUTA_CONTEO = '/contar/escanear'

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
  const rol = useRol()
  const [params] = useSearchParams()
  const codigoInicial = normalizarCodigo(params.get('codigo') ?? '') ?? ''
  const { state } = useLocation()
  const desdeConteo = (state as { desde?: unknown } | null)?.desde === 'conteo'
  const { sala } = useSalaDeTrabajo()
  const alta = useAltaActivo({ rol, codigoInicial, ubicacionPorDefecto: sala })
  const categorias = useCategorias()
  const ubicaciones = useUbicaciones()
  const movil = useIsMobile()
  const [varias, setVarias] = useState(false)
  const [registrado, setRegistrado] = useState<Activo | null>(null)
  const codigoRef = useRef<HTMLInputElement>(null)
  const { campos, errores, copiado, duplicando } = alta
  const esAdmin = rol === 'admin'
  const conVarias = esAdmin && varias

  // Foco en el código al abrir (en el teléfono no, para no tapar el formulario con el
  // teclado) y cada vez que el formulario queda listo para el siguiente sticker. Si el
  // código llegó en la URL, el cursor empieza en Nombre (como tras el Enter del lector).
  const enfocar = !movil || alta.ronda > 0
  const empiezaEnNombre = Boolean(codigoInicial) && alta.ronda === 0
  useEffect(() => {
    if (!enfocar) return
    if (empiezaEnNombre) document.getElementById('nombre')?.focus()
    else codigoRef.current?.focus()
  }, [enfocar, empiezaEnNombre, alta.ronda])

  function guardar(otro: boolean) {
    alta.enviar({
      alCrear:
        otro || conVarias
          ? (activo: Activo) => {
              setRegistrado(activo)
              if (conVarias) alta.siguienteUnidad()
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
              {desdeConteo && (
                <Boton asChild variante="secundario">
                  <Link to={RUTA_CONTEO}>Volver al conteo</Link>
                </Boton>
              )}
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
                    {desdeConteo ? <Link to={RUTA_CONTEO}>Volver al conteo</Link> : <Link to={rutaApp('activos')}>Cancelar</Link>}
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
                  {duplicando ? (
                    <Aviso
                      tono="info"
                      titulo={`Se copia de ${copiado!.nombre}`}
                      className="md:col-span-2"
                      accion={
                        <Boton variante="fantasma" icono={<X />} className="-ml-2 px-2 text-brand-strong" onClick={alta.quitarCopia}>
                          Quitar la copia
                        </Boton>
                      }
                    >
                      Nombre, categoría ({copiado!.categoria.nombre}), marca, modelo y precio se copian del original. El precio solo lo ven los administradores.
                    </Aviso>
                  ) : (
                    <>
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
                        ayuda={esAdmin ? 'Solo lo ven los administradores.' : 'Después de guardar, solo lo verán los administradores.'}
                        value={campos.precio}
                        onChange={(e) => alta.cambiar('precio', e.target.value)}
                        autoComplete="off"
                      />
                      <CampoCategoria alta={alta} categorias={categorias.data ?? []} cargando={categorias.isPending} ayuda="Lista cerrada de la clínica." />
                    </>
                  )}
                  <MarcoCampo
                    id="ubicacion"
                    etiqueta={<Etiqueta conserva>Ubicación <MarcaObligatorio /></Etiqueta>}
                    error={errores.ubicacion}
                    ayuda={sala && campos.ubicacion === sala ? 'Viene de la sala donde estás contando.' : 'Una sala o un box activos.'}
                  >
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
                <MasDatos alta={alta} soloSerial={duplicando} />
              </Paso>
            </Panel>
          </form>
        </div>

        <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-20">
          <TarjetaCopiar alta={alta} rol={rol} />
          <TarjetaFoto alta={alta} />
          <Resumen alta={alta} rol={rol} categorias={categorias.data ?? []} ubicaciones={ubicaciones.data ?? []}>
            {!esAdmin && (
              <p className="text-etiqueta font-normal text-muted-foreground">El precio no se muestra aquí; después de guardar, solo lo ven los administradores.</p>
            )}
            {/* Con varias unidades se conservan nombre y precio: la nota no aplica. */}
            {!conVarias && <NotaRegistrarOtro />}
            {esAdmin && <VariasUnidades activo={varias} onCambio={setVarias} />}
          </Resumen>
        </aside>
      </div>
    </div>
  )
}
