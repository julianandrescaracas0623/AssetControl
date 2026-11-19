import { CircleAlert, RefreshCw, X } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { CampoFoto, EstadoFoto } from '@/components/app/CampoFoto'
import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { CountShell } from '@/components/app/CountShell'
import {
  AvisoRegistrado,
  CampoCategoria,
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
import { Aviso, Boton, Campo, EncabezadoPagina, MarcaObligatorio, MarcoCampo, Panel } from '@/components/kit'
import { useDensidad } from '@/hooks/use-densidad'
import { useEsEscritorio } from '@/hooks/use-escritorio'
import type { Activo } from '@/lib/activos'
import { claseControlAlta, type ErroresAlta, teclasDelAlta, useAltaActivo } from '@/lib/altaActivo'
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
// Spec 016, T6 (R2, R4, R10): presentación con el kit. Teléfono: la BarraAccion del
// CountShell con «Guardar activo» como única principal (56 px) y «Guardar y registrar
// otro» encima; los datos en paneles blancos sobre la página; controles de 48 px.
// Escritorio: encabezado de página, el formulario en un panel con su pie de acciones y la
// columna derecha con paneles. Mismos pasos, mismos campos y las mismas llamadas.

const rutaActivo = (codigo: string) => `/contar/activo/${encodeURIComponent(codigo)}`

const aria = (errores: ErroresAlta, campo: keyof ErroresAlta) => ({
  'aria-invalid': errores[campo] ? true : undefined,
  'aria-describedby': errores[campo] ? `${campo}-error` : undefined,
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
    const creado = (
      <span>
        {alta.creado.nombre} · <span className="font-mono">{alta.creado.codigo}</span> quedó registrado en {alta.creado.ubicacion.ruta}.
      </span>
    )
    const foto = <EstadoFoto estado={alta.foto.estado} error={alta.foto.error} onReintentar={alta.reintentarFoto} />
    if (escritorio) {
      return (
        <MarcoEscritorio red="guardado">
          <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
            <EncabezadoPagina titulo="Registrar activo" />
            <Aviso
              tono="exito"
              titulo="Activo creado"
              accion={
                <>
                  <Boton asChild>
                    <Link to="/contar/escanear">Volver al conteo</Link>
                  </Boton>
                  <Boton
                    variante="secundario"
                    onClick={() => {
                      setRegistrado(null)
                      alta.otro()
                    }}
                  >
                    Registrar otro
                  </Boton>
                </>
              }
            >
              <div className="flex flex-col items-start gap-2">
                {creado}
                {foto}
              </div>
            </Aviso>
          </div>
        </MarcoEscritorio>
      )
    }
    return (
      <CountShell
        titulo="Registrar activo"
        volver="/contar"
        estadoRed="guardado"
        principal={
          <Boton asChild tamano="accion">
            <Link to="/contar/escanear">Escanear otro</Link>
          </Boton>
        }
      >
        <h1 className="sr-only">Registrar activo</h1>
        <Aviso tono="exito" titulo="Activo creado">
          <div className="flex flex-col items-start gap-2">
            {creado}
            {foto}
          </div>
        </Aviso>
      </CountShell>
    )
  }

  const ayudaUbicacion = sala && campos.ubicacion === sala ? 'Viene de la sala donde estás contando.' : 'Sala o box donde está el activo.'

  const avisos = (
    <>
      {registrado && <AvisoRegistrado activo={registrado} rutaActivo={rutaActivo} />}
      {alta.errorGeneral && (
        <Aviso
          tono="error"
          titulo="No se guardó"
          accion={
            alta.errorGeneral.reintentable && (
              <Boton type="submit" form="alta" variante="secundario" icono={<RefreshCw />}>
                Reintentar
              </Boton>
            )
          }
        >
          {alta.errorGeneral.mensaje}
        </Aviso>
      )}
      {alta.existente && (
        <Aviso
          tono="aviso"
          titulo="Ese código ya está registrado"
          accion={
            <Boton asChild variante="secundario">
              <Link to={rutaActivo(alta.existente.codigo)}>Abrir activo</Link>
            </Boton>
          }
        >
          Es {alta.existente.nombre}. Ábrelo en vez de crear otro.
        </Aviso>
      )}
    </>
  )

  const errorCodigo = errores.codigo && (
    <p id="codigo-error" className={cn('flex items-center gap-1.5 text-etiqueta font-normal text-destructive', escritorio && 'px-5 pt-3')}>
      <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
      {errores.codigo}
    </p>
  )

  const codigoFijo = escritorio ? (
    <>
      <div className="flex items-center gap-3 border-b bg-muted/40 px-5 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-etiqueta font-normal text-muted-foreground">Código del sticker · nuevo</p>
          <p className="font-mono text-lg tracking-wider break-all">{codigo}</p>
        </div>
        <Confirmacion alta={alta} texto="Coincide con el sticker" />
      </div>
      {errorCodigo}
    </>
  ) : (
    <Panel>
      <div className="flex flex-col gap-1">
        <p className="text-etiqueta font-normal text-muted-foreground">Código del sticker · nuevo</p>
        <p className="font-mono text-xl tracking-wider break-all">{codigo}</p>
        <Confirmacion alta={alta} texto="Coincide" />
        {errorCodigo}
      </div>
    </Panel>
  )

  const datos = (
    <>
      {duplicando ? (
        <Aviso
          tono="info"
          titulo={`Se copia de ${copiado!.nombre}`}
          className={escritorio ? 'md:col-span-2' : undefined}
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
              enterKeyHint="next"
              {...aria(errores, 'nombre')}
              className={claseControlAlta(alta, 'nombre')}
            />
          </MarcoCampo>
          <Campo
            id="precio"
            tipo="dinero"
            etiqueta="Precio de compra (COP)"
            obligatorio
            error={errores.precio}
            ayuda="Después de guardar, solo lo verán los administradores."
            value={campos.precio}
            onChange={(e) => alta.cambiar('precio', e.target.value)}
            autoComplete="off"
          />
          <CampoCategoria alta={alta} categorias={categorias.data ?? []} cargando={categorias.isPending} />
        </>
      )}
      <MarcoCampo id="ubicacion" etiqueta={<Etiqueta conserva>Ubicación <MarcaObligatorio /></Etiqueta>} error={errores.ubicacion} ayuda={ayudaUbicacion}>
        <LocationPicker
          id="ubicacion"
          ubicaciones={ubicaciones.data ?? []}
          cargando={ubicaciones.isPending}
          valor={campos.ubicacion || undefined}
          onChange={(v) => alta.cambiar('ubicacion', v)}
          className={claseControlAlta(alta, 'ubicacion', cn('md:h-control', errores.ubicacion && 'border-destructive'))}
        />
      </MarcoCampo>
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

  if (escritorio) {
    return (
      <MarcoEscritorio red="en_linea">
        <div className="flex flex-col gap-5">
          <EncabezadoPagina
            titulo="Registrar activo"
            descripcion={codigoEditable ? 'Escanea el sticker con el lector o escribe el código impreso.' : 'El sticker no está registrado. Completa lo obligatorio y guarda.'}
            acciones={
              <Boton asChild variante="secundario">
                <Link to="/contar/escanear">Volver al conteo</Link>
              </Boton>
            }
          />
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="flex min-w-0 flex-col gap-4">
              {avisos}
              <form id="alta" noValidate onSubmit={enviar} {...teclas}>
                <Panel
                  relleno={false}
                  pie={
                    <>
                      <Boton asChild variante="fantasma">
                        <Link to={salirDelAlta}>Cancelar</Link>
                      </Boton>
                      <div className="ml-auto flex flex-wrap gap-separacion">
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
                  {codigoEditable ? (
                    <div className="border-b px-5 py-5">
                      <CampoCodigo alta={alta} rutaActivo={rutaActivo} />
                    </div>
                  ) : (
                    codigoFijo
                  )}
                  <div className="grid gap-4 px-5 py-5 md:grid-cols-2">{datos}</div>
                  <div className="px-5 pb-5">
                    <MasDatos alta={alta} soloSerial={duplicando} />
                  </div>
                </Panel>
              </form>
            </div>
            <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-24">
              <TarjetaCopiar alta={alta} rol={rol} />
              <TarjetaFoto alta={alta} />
              <Resumen alta={alta} rol={rol} categorias={categorias.data ?? []} ubicaciones={ubicaciones.data ?? []}>
                {rol !== 'admin' && (
                  <p className="text-etiqueta font-normal text-muted-foreground">El precio no se muestra aquí; después de guardar, solo lo ven los administradores.</p>
                )}
                <NotaRegistrarOtro />
              </Resumen>
            </aside>
          </div>
        </div>
      </MarcoEscritorio>
    )
  }

  return (
    <CountShell
      titulo="Registrar activo"
      volver="/contar/escribir"
      estadoRed="en_linea"
      secundaria={
        <Boton variante="secundario" disabled={alta.guardando} onClick={() => guardar(true)}>
          Guardar y registrar otro
        </Boton>
      }
      principal={
        <Boton type="submit" form="alta" tamano="accion" cargando={alta.guardando} textoCargando="Guardando…">
          Guardar activo
        </Boton>
      }
    >
      <h1 className="sr-only">Registrar activo</h1>
      <form id="alta" noValidate onSubmit={enviar} {...teclas} className="flex flex-col gap-4">
        {avisos}
        {codigoEditable ? (
          <Panel>
            <CampoCodigo alta={alta} rutaActivo={rutaActivo} />
          </Panel>
        ) : (
          codigoFijo
        )}
        <CopiarDeParecido onCopiar={alta.copiar} copiado={copiado} className="h-control bg-card text-base md:h-control" />
        <Panel>
          <div className="flex flex-col gap-4">{datos}</div>
        </Panel>
        <MasDatos alta={alta} plegable soloSerial={duplicando} />
        <Panel>
          <CampoFoto archivo={alta.foto.archivo} onElegir={(f) => void alta.foto.elegir(f)} deshabilitado={alta.guardando} />
        </Panel>
      </form>
    </CountShell>
  )
}

/** Escritorio: la cabecera del conteo (sesión, sala, avance) y el contenido centrado. */
function MarcoEscritorio({ red, children }: { red: 'en_linea' | 'guardado'; children: ReactNode }) {
  const sesion = useSesionAbierta()
  // Spec 016, T6 (D6): el conteo, también en el computador, con objetivos de 48 px.
  useDensidad('conteo')
  return (
    <div data-densidad="conteo" className="flex min-h-svh flex-1 flex-col bg-page">
      <CabeceraEscritorio sesion={sesion.data ?? null} cargando={sesion.isPending} red={red} />
      <div className="mx-auto w-full max-w-[1320px] flex-1 px-6 py-6">{children}</div>
    </div>
  )
}
