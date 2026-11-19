import { Download, Eye, EyeOff, MoreHorizontal, Plus, ScanBarcode } from 'lucide-react'
import { toast } from 'sonner'
import { useMemo, useState, type ReactNode } from 'react'

import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import {
  BarraAccion,
  Boton,
  Campo,
  Cifra,
  CifrasCongeladas,
  Confirmar,
  Dialogo,
  EncabezadoPagina,
  Filtro,
  Insignia,
  ListaDatos,
  Notificaciones,
  Panel,
  Pestanas,
  Progreso,
  TablaDatos,
  type ColumnaTabla,
  type OrdenTabla,
} from '@/components/kit'
import { formatCOP, formatEntero, formatUnidades } from '@/lib/format'
import { ACTIVOS, CATEGORIAS, RESUMEN, ULTIMO_INFORME, type ActivoFicticio } from '@/mocks/datos-ficticios'

// Spec 016, T3 (A7): galería de los primitivos B del kit con datos ficticios. Se monta
// dentro de /dev/componentes; cada bloque es una sección de la galería.

type SeccionProps = { Seccion: (p: { title: string; children: ReactNode }) => ReactNode }

const ACTIVO = ACTIVOS[11]

export function SuperficiesKit() {
  return (
    <>
      <Panel>
        <EncabezadoPagina
          migas={[{ etiqueta: 'Inventario' }, { etiqueta: 'Activos' }, { etiqueta: ACTIVO.nombre }]}
          titulo={ACTIVO.nombre}
          insignia={<EstadoActivoBadge estado={ACTIVO.estado} />}
          descripcion={
            <>
              Código <span className="font-mono">{ACTIVO.codigo}</span> · {ACTIVO.ubicacion}
            </>
          }
          acciones={
            <>
              <Boton variante="secundario">Mover</Boton>
              <Boton>Editar</Boton>
            </>
          }
        />
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel titulo="Datos del activo" descripcion="Vista del admin: incluye el precio." acciones={<Insignia tono="info">Admin</Insignia>}>
          <ListaDatos
            datos={[
              { rotulo: 'Código', valor: ACTIVO.codigo, tipo: 'codigo' },
              { rotulo: 'Categoría', valor: ACTIVO.categoria },
              { rotulo: 'Ubicación', valor: ACTIVO.ubicacion },
              { rotulo: 'Precio de compra', valor: formatCOP(ACTIVO.precio), tipo: 'cifra' },
            ]}
          />
        </Panel>
        <Panel
          titulo="Datos del activo"
          descripcion="Vista del contador: sin precio, sin hueco."
          acciones={<Insignia tono="neutro">Contador</Insignia>}
          pie={<p className="text-etiqueta font-normal text-muted-foreground">El servidor decide qué datos llegan.</p>}
        >
          <ListaDatos
            datos={[
              { rotulo: 'Código', valor: ACTIVO.codigo, tipo: 'codigo' },
              { rotulo: 'Categoría', valor: ACTIVO.categoria },
              { rotulo: 'Ubicación', valor: ACTIVO.ubicacion },
              { rotulo: 'Serial', valor: '', siVacio: 'Sin serial' },
            ]}
          />
        </Panel>
        <Panel titulo="Más datos" plegable>
          <ListaDatos
            disposicion="columnas"
            datos={[
              { rotulo: 'Marca', valor: 'Ergo Plus' },
              { rotulo: 'Modelo', valor: 'EP-200' },
              { rotulo: 'Serial', valor: 'SN-4471', tipo: 'codigo' },
              { rotulo: 'Registrado', valor: '12 nov 2026' },
            ]}
          />
        </Panel>
        <Panel>
          <p className="text-cuerpo text-muted-foreground">Panel sin título: solo la superficie blanca con borde y sombra mínima.</p>
        </Panel>
      </div>
    </>
  )
}

/** Campo con sufijo (spec 016, T4): mostrar u ocultar la contraseña sin salir del campo. */
export function CampoClave() {
  const [visible, setVisible] = useState(false)
  return (
    <Campo
      id="g-clave"
      etiqueta="Contraseña"
      type={visible ? 'text' : 'password'}
      defaultValue="clave-de-ejemplo"
      autoComplete="off"
      ayuda="Con sufijo: el botón vive dentro del campo."
      sufijo={
        <Boton
          variante="fantasma"
          soloIcono
          icono={visible ? <EyeOff /> : <Eye />}
          aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
          aria-pressed={visible}
          className="text-muted-foreground hover:bg-transparent hover:text-foreground"
          onClick={() => setVisible((v) => !v)}
        />
      }
    />
  )
}

export function CifrasKit({ Seccion }: SeccionProps) {
  return (
    <Seccion title="Cifras">
      <p className="text-cuerpo text-muted-foreground">
        La cifra llega del servidor ya formateada. «Informe congelado» y «Valor actual» nunca comparten tarjeta ni rótulo.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Cifra rotulo="Activos hoy" valor={formatEntero(RESUMEN.activosHoy)} contexto="Incluye 2 en reparación" />
        <Cifra rotulo="Discrepancias" valor="3" contexto="Sin resolver" tono="aviso" />
        <Cifra fuente="en_vivo" region rotulo="Valor actual" valor={formatCOP(RESUMEN.valorActual)} contexto={`COP · 219 activos · ${RESUMEN.consultadoA}`} />
        <Cifra rotulo="Sesiones cerradas" valor="—" estado="cargando" />
      </div>
      <CifrasCongeladas
        titulo="Último informe cerrado"
        meta={`${ULTIMO_INFORME.sesion} · corte ${ULTIMO_INFORME.corte}`}
        accion={<Boton variante="secundario">Ver informe</Boton>}
        cifras={[
          { rotulo: 'Encontrado', tono: 'exito', valor: formatCOP(ULTIMO_INFORME.encontrado.valor), detalle: formatUnidades(ULTIMO_INFORME.encontrado.unidades) },
          { rotulo: 'No encontrado', tono: 'error', valor: formatCOP(ULTIMO_INFORME.noEncontrado.valor), detalle: formatUnidades(ULTIMO_INFORME.noEncontrado.unidades) },
          { rotulo: 'Total registrado', valor: formatCOP(ULTIMO_INFORME.total.valor), detalle: formatUnidades(ULTIMO_INFORME.total.unidades) },
        ]}
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Cifra rotulo="Valor por ubicación" valor="—" estado="error" onReintentar={() => undefined} />
      </div>
      {/* Spec 016, T5: avance del conteo. El porcentaje sale de unidades del servidor. */}
      <div className="grid max-w-md gap-3 rounded-xl border bg-card p-4 shadow-xs">
        <span className="flex items-center justify-between text-etiqueta">
          Progreso · normal <span className="tabular-nums text-foreground">60 %</span>
        </span>
        <Progreso valor={60} etiqueta="Avance del conteo (ejemplo)" />
        <span className="flex items-center justify-between text-etiqueta">
          Progreso · fino <span className="tabular-nums text-foreground">25 %</span>
        </span>
        <Progreso valor={25} tamano="fino" etiqueta="Avance en Bodega (ejemplo)" />
      </div>
    </Seccion>
  )
}

export function DialogosKit({ Seccion }: SeccionProps) {
  const [centrado, setCentrado] = useState(false)
  const [lateral, setLateral] = useState(false)
  const [baja, setBaja] = useState(false)
  const [dandoDeBaja, setDandoDeBaja] = useState(false)
  const [categoria, setCategoria] = useState('mobiliario')

  function confirmarBaja() {
    // Demostración: la acción queda ocupada un momento, como mientras responde el servidor.
    setDandoDeBaja(true)
    window.setTimeout(() => {
      setDandoDeBaja(false)
      setBaja(false)
    }, 1200)
  }

  return (
    <Seccion title="Diálogos">
      <p className="text-cuerpo text-muted-foreground">
        Centrado desde md y hoja inferior en teléfono; lateral para editar sin perder la tabla. El foco vuelve al botón que lo abrió.
      </p>
      <div className="flex flex-wrap gap-separacion">
        <Boton variante="secundario" onClick={() => setCentrado(true)}>
          Editar ubicación
        </Boton>
        <Boton variante="secundario" onClick={() => setLateral(true)}>
          Editar activo
        </Boton>
        <Boton variante="peligro" onClick={() => setBaja(true)}>
          Dar de baja
        </Boton>
        <Boton variante="fantasma" onClick={() => toast.success('Ubicación guardada (ejemplo)')}>
          Mostrar notificación
        </Boton>
      </div>
      <Notificaciones />
      <Dialogo
        abierto={centrado}
        onAbiertoChange={setCentrado}
        titulo="Editar ubicación"
        descripcion="El nombre se ve en las listas y en el informe."
        pie={
          <>
            <Boton variante="secundario" onClick={() => setCentrado(false)}>
              Cancelar
            </Boton>
            <Boton onClick={() => setCentrado(false)}>Guardar</Boton>
          </>
        }
      >
        <Campo id="g-dlg-nombre" etiqueta="Nombre" obligatorio defaultValue="Consultorio 1 › Box 2" autoComplete="off" />
      </Dialogo>
      <Dialogo
        abierto={lateral}
        onAbiertoChange={setLateral}
        forma="lateral"
        titulo="Editar activo"
        descripcion={
          <>
            {ACTIVO.nombre} · <span className="font-mono">{ACTIVO.codigo}</span>
          </>
        }
        pie={
          <>
            <Boton variante="secundario" onClick={() => setLateral(false)}>
              Cancelar
            </Boton>
            <Boton onClick={() => setLateral(false)}>Guardar cambios</Boton>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Campo id="g-dlg-activo" etiqueta="Nombre" obligatorio defaultValue={ACTIVO.nombre} autoComplete="off" />
          <Campo
            id="g-dlg-categoria"
            etiqueta="Categoría"
            tipo="seleccion"
            obligatorio
            opciones={[
              { valor: 'mobiliario', etiqueta: 'Mobiliario' },
              { valor: 'computo', etiqueta: 'Cómputo' },
            ]}
            valor={categoria}
            onValorChange={setCategoria}
          />
        </div>
      </Dialogo>
      <Confirmar
        abierto={baja}
        onAbiertoChange={setBaja}
        titulo="¿Dar de baja el activo?"
        descripcion={`«${ACTIVO.nombre}» deja de contar en el inventario. Queda en el historial y se puede reactivar.`}
        textoConfirmar="Sí, dar de baja"
        textoConfirmando="Dando de baja…"
        peligro
        confirmando={dandoDeBaja}
        onConfirmar={confirmarBaja}
      />

      <div data-densidad="conteo" className="flex max-w-sm flex-col overflow-hidden rounded-xl border bg-page shadow-xs">
        <div className="flex h-72 flex-col overflow-y-auto">
          <div className="flex flex-1 flex-col gap-3 p-4">
            <p className="text-etiqueta text-muted-foreground">Barra de acción del conteo (sticky: no tapa el final)</p>
            <Panel titulo={ACTIVO.nombre} nivel={3}>
              <ListaDatos
                datos={[
                  { rotulo: 'Código', valor: ACTIVO.codigo, tipo: 'codigo' },
                  { rotulo: 'Ubicación esperada', valor: ACTIVO.ubicacion },
                  { rotulo: 'Categoría', valor: ACTIVO.categoria },
                ]}
              />
            </Panel>
          </div>
          <BarraAccion
            etiqueta="Acciones de la verificación"
            secundaria={<Boton variante="secundario">Está en otra ubicación</Boton>}
            principal={<Boton tamano="accion">Confirmar</Boton>}
          />
        </div>
      </div>
    </Seccion>
  )
}

type Vista = 'datos' | 'cargando' | 'vacio' | 'error'
const POR_PAGINA = 5
const OPCIONES_CATEGORIA = CATEGORIAS.map((c) => ({
  valor: c,
  etiqueta: c,
  conteo: ACTIVOS.filter((a) => a.categoria === c).length,
}))

export function TablasKit({ Seccion }: SeccionProps) {
  const [vista, setVista] = useState<Vista>('datos')
  const [texto, setTexto] = useState('')
  const [categorias, setCategorias] = useState<string[]>([])
  const [orden, setOrden] = useState<OrdenTabla>({ columna: 'codigo', direccion: 'asc' })
  const [pagina, setPagina] = useState(1)
  const [abierto, setAbierto] = useState<ActivoFicticio | null>(null)

  // Filtro y orden en cliente, como haría una pantalla con pocos datos. Precio sin ordenar:
  // es texto decimal del servidor y no se convierte a número.
  const filtradas = useMemo(() => {
    const q = texto.trim().toLocaleLowerCase('es-CO')
    const lista = ACTIVOS.filter(
      (a) =>
        (categorias.length === 0 || categorias.includes(a.categoria)) &&
        (!q || a.codigo.includes(q) || a.nombre.toLocaleLowerCase('es-CO').includes(q)),
    )
    const campo = orden.columna === 'nombre' ? 'nombre' : 'codigo'
    const signo = orden.direccion === 'asc' ? 1 : -1
    return [...lista].sort((x, y) => signo * x[campo].localeCompare(y[campo], 'es-CO'))
  }, [texto, categorias, orden])

  const total = filtradas.length
  const desde = total === 0 ? 0 : (pagina - 1) * POR_PAGINA + 1
  const hasta = Math.min(pagina * POR_PAGINA, total)
  const filas = filtradas.slice(desde - 1, hasta)
  const hayFiltros = texto !== '' || categorias.length > 0

  function limpiar() {
    setTexto('')
    setCategorias([])
    setPagina(1)
  }

  const columnas: ColumnaTabla<ActivoFicticio>[] = [
    { id: 'codigo', encabezado: 'Código', celda: (a) => a.codigo, tipo: 'codigo', ordenable: true },
    { id: 'nombre', encabezado: 'Nombre', celda: (a) => a.nombre, principal: true, ordenable: true, clase: 'min-w-48 whitespace-normal' },
    { id: 'categoria', encabezado: 'Categoría', celda: (a) => a.categoria },
    { id: 'ubicacion', encabezado: 'Ubicación', celda: (a) => a.ubicacion, clase: 'min-w-40 whitespace-normal text-muted-foreground' },
    { id: 'estado', encabezado: 'Estado', celda: (a) => <EstadoActivoBadge estado={a.estado} /> },
    { id: 'precio', encabezado: 'Precio de compra', celda: (a) => formatCOP(a.precio), tipo: 'cifra' },
  ]

  return (
    <Seccion title="Tablas">
      <p className="text-cuerpo text-muted-foreground">
        Sin <span className="font-mono">@tanstack/react-table</span>: la pantalla decide orden, filtro y paginación (cliente o servidor) y la tabla
        los presenta. En teléfono, una tarjeta por fila. Doble clic o Enter abre la fila.
      </p>
      <Pestanas
        etiqueta="Vista de la tabla"
        valor={vista}
        onValorChange={(v) => setVista(v as Vista)}
        pestanas={[
          { valor: 'datos', etiqueta: 'Con datos', conteo: ACTIVOS.length },
          { valor: 'cargando', etiqueta: 'Cargando' },
          { valor: 'vacio', etiqueta: 'Vacío' },
          { valor: 'error', etiqueta: 'Error' },
        ]}
      >
        <TablaDatos<ActivoFicticio>
          etiqueta="Activos de ejemplo"
          etiquetaCargando="Cargando activos de ejemplo"
          columnas={columnas}
          filas={vista === 'vacio' ? [] : vista === 'datos' ? filas : undefined}
          claveFila={(a) => a.codigo}
          cargando={vista === 'cargando'}
          error={vista === 'error' ? { titulo: 'No se pudieron cargar los activos', onReintentar: () => setVista('datos') } : null}
          vacio={
            hayFiltros
              ? { titulo: 'Nada coincide', descripcion: 'Prueba con otro código, nombre o categoría.', accion: <Boton variante="secundario" onClick={limpiar}>Limpiar filtros</Boton> }
              : {
                  titulo: 'Aún no hay activos',
                  descripcion: 'Escanea un sticker para crear el primero.',
                  accion: (
                    <>
                      <Boton icono={<Plus />}>Registrar activo</Boton>
                      <Boton variante="secundario" icono={<ScanBarcode />}>
                        Ir a escanear
                      </Boton>
                    </>
                  ),
                }
          }
          orden={orden}
          onOrdenChange={(o) => {
            setOrden(o)
            setPagina(1)
          }}
          onAbrirFila={setAbierto}
          accionesFila={(a) => (
            <Boton variante="fantasma" soloIcono aria-label={`Acciones de ${a.nombre} (${a.codigo})`} icono={<MoreHorizontal />} />
          )}
          barra={{
            busqueda: {
              valor: texto,
              onCambio: (v) => {
                setTexto(v)
                setPagina(1)
              },
              etiqueta: 'Buscar activos',
              placeholder: 'Código o nombre',
            },
            filtros: (
              <Filtro
                etiqueta="Categoría"
                opciones={OPCIONES_CATEGORIA}
                seleccion={categorias}
                onSeleccionChange={(s) => {
                  setCategorias(s)
                  setPagina(1)
                }}
              />
            ),
            hayFiltros,
            onLimpiar: limpiar,
            accion: (
              <>
                <Boton variante="secundario" icono={<Download />}>
                  Exportar
                </Boton>
                <Boton icono={<Plus />}>Registrar activo</Boton>
              </>
            ),
          }}
          paginacion={{
            desde,
            hasta,
            total,
            hayAnterior: pagina > 1,
            haySiguiente: hasta < total,
            onAnterior: () => setPagina((p) => p - 1),
            onSiguiente: () => setPagina((p) => p + 1),
          }}
        />
      </Pestanas>
      {abierto && (
        <p role="status" className="text-etiqueta text-muted-foreground">
          Abrir la ficha de {abierto.nombre} ({abierto.codigo})
        </p>
      )}
    </Seccion>
  )
}
