import { Archive, ArchiveRestore, Download, Eye, MapPin, MoreHorizontal, Pencil, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Boton, type ColumnaTabla, EncabezadoPagina, Menu, type OpcionMenu, Pestanas, TablaDatos } from '@/components/kit'
import { type Activo, useBuscarActivos, useExportarActivos } from '@/lib/activos'
import { mensajeDeError } from '@/lib/api/cliente'
import { rutaDe, useUbicaciones } from '@/lib/catalogo'
import { formatCOP, formatEntero } from '@/lib/format'
import { guardarArchivo } from '@/lib/informe'

// Activos (docs/08 §4.3, §7.7; spec 004, T9): búsqueda por código, nombre o serial,
// filtro por estado y paginación en el servidor (25 por página). Spec 005, T8: el menú
// de cada fila abre la ficha con la acción (editar, mover, dar de baja o reactivar) y
// la lista filtra por ubicación (`?ubicacion=`; llega desde el aviso "tiene activos").
// Spec 016, T8 (R2, R5): presentación con el kit. Pestañas de estado subrayadas, la
// TablaDatos con la búsqueda y el filtro de ubicación en su barra, menú ⋯ del kit y, por
// debajo de md, una tarjeta por activo. El filtro de ubicación sigue siendo el
// LocationPicker (con buscador): el Filtro del kit no busca y las salas pueden ser muchas
// (Deuda T3 g). Mismas llamadas, mismos filtros (los aplica el servidor) y mismos textos.

type Pestaña = 'todos' | Activo['estado']

const PESTANAS: { valor: Pestaña; etiqueta: string }[] = [
  { valor: 'todos', etiqueta: 'Todos' },
  { valor: 'activo', etiqueta: 'Activos' },
  { valor: 'en_reparacion', etiqueta: 'En reparación' },
  { valor: 'dado_de_baja', etiqueta: 'Dados de baja' },
]

const ficha = (a: Activo) => `/admin/activos/${encodeURIComponent(a.codigo)}`

function opcionesDe(activo: Activo): OpcionMenu[] {
  const ver: OpcionMenu = { etiqueta: 'Ver ficha', icono: <Eye />, href: ficha(activo) }
  if (activo.estado === 'dado_de_baja') {
    return [ver, { etiqueta: 'Reactivar', icono: <ArchiveRestore />, href: `${ficha(activo)}?accion=reactivar` }]
  }
  return [
    ver,
    { etiqueta: 'Editar', icono: <Pencil />, href: `${ficha(activo)}?accion=editar` },
    { etiqueta: 'Mover', icono: <MapPin />, href: `${ficha(activo)}?accion=mover` },
    { etiqueta: 'Dar de baja', icono: <Archive />, href: `${ficha(activo)}?accion=baja`, peligro: true, separadorAntes: true },
  ]
}

function AccionesFila({ activo }: { activo: Activo }) {
  return (
    <Menu
      rotulo={activo.codigo}
      opciones={opcionesDe(activo)}
      disparador={
        <Boton
          variante="fantasma"
          soloIcono
          icono={<MoreHorizontal />}
          aria-label={`Acciones de ${activo.nombre} (${activo.codigo})`}
          className="text-muted-foreground hover:text-foreground"
        />
      }
    />
  )
}

/** Tarjeta del teléfono: nombre (enlace a la ficha), código · categoría · ubicación, estado y precio. */
function TarjetaActivo({ activo: a }: { activo: Activo }) {
  return (
    <Link
      to={ficha(a)}
      className="-m-1 flex min-w-0 flex-col gap-1.5 rounded-lg p-1 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <span className="text-cuerpo font-medium break-words">{a.nombre}</span>
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-etiqueta font-normal text-muted-foreground">
        <span className="font-mono text-foreground">{a.codigo}</span>· {a.categoria.nombre} · <span className="min-w-0 break-words">{a.ubicacion.ruta}</span>
      </span>
      <span className="flex flex-wrap items-center gap-2">
        <EstadoActivoBadge estado={a.estado} />
        {a.precio_compra && <span className="text-cuerpo font-medium tabular-nums">{formatCOP(a.precio_compra)}</span>}
      </span>
    </Link>
  )
}

function useRetrasado(valor: string, ms = 300) {
  const [retrasado, setRetrasado] = useState(valor)
  useEffect(() => {
    const reloj = setTimeout(() => setRetrasado(valor), ms)
    return () => clearTimeout(reloj)
  }, [valor, ms])
  return retrasado
}

export default function Activos() {
  const [params, setParams] = useSearchParams()
  // Spec 010: el Inicio enlaza a «en reparación» con ?estado=.
  const [pestaña, setPestaña] = useState<Pestaña>(() => {
    const estado = params.get('estado')
    return estado === 'activo' || estado === 'en_reparacion' || estado === 'dado_de_baja' ? estado : 'todos'
  })
  const [texto, setTexto] = useState('')
  const [pagina, setPagina] = useState(1)
  const ubicacion = params.get('ubicacion') ?? ''
  const ubicaciones = useUbicaciones()
  const q = useRetrasado(texto.trim())
  const busqueda = useBuscarActivos({
    q: q || undefined,
    estado: pestaña === 'todos' ? undefined : pestaña,
    ubicacion_id: ubicacion || undefined,
    pagina,
  })

  // Spec 015, T4 (R1): el archivo lleva los mismos filtros que la lista (sin la página);
  // lo arma el servidor, que también decide quién puede exportar.
  const exportar = useExportarActivos()
  function exportarLista() {
    exportar.mutate(
      { q: q || undefined, estado: pestaña === 'todos' ? undefined : pestaña, ubicacion_id: ubicacion || undefined },
      {
        onSuccess: (archivo) => {
          guardarArchivo(archivo)
          toast.success(`Se descargó «${archivo.nombre}»`)
        },
        onError: (error) => toast.error(`No se pudo exportar: ${mensajeDeError(error)}`),
      },
    )
  }

  // Spec 015, T4 (R2): doble clic o Enter en la fila abre la ficha. Lo que nace en un
  // enlace, un botón o el menú de acciones (portal) no la abre: lo resuelve TablaDatos.
  const navigate = useNavigate()

  function filtrarUbicacion(id: string) {
    if (id) params.set('ubicacion', id)
    else params.delete('ubicacion')
    setParams(params, { replace: true })
    setPagina(1)
  }
  function limpiar() {
    setTexto('')
    setPestaña('todos')
    filtrarUbicacion('')
  }

  const datos = busqueda.data
  const activos = datos?.activos ?? []
  const desde = datos && datos.total > 0 ? (datos.pagina - 1) * datos.por_pagina + 1 : 0
  const hasta = datos ? desde + activos.length - (activos.length > 0 ? 1 : 0) : 0
  const hayMas = datos ? datos.pagina * datos.por_pagina < datos.total : false
  const filtrando = q !== '' || pestaña !== 'todos' || ubicacion !== ''
  const rutaFiltro = rutaDe(ubicaciones.data ?? [], ubicacion)

  const columnas: ColumnaTabla<Activo>[] = [
    { id: 'codigo', encabezado: 'Código', tipo: 'codigo', celda: (a) => a.codigo },
    {
      id: 'nombre',
      encabezado: 'Nombre',
      principal: true,
      clase: 'min-w-48 whitespace-normal',
      celda: (a) => (
        <Link
          to={ficha(a)}
          className="rounded-sm hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {a.nombre}
        </Link>
      ),
    },
    { id: 'categoria', encabezado: 'Categoría', celda: (a) => a.categoria.nombre },
    { id: 'ubicacion', encabezado: 'Ubicación', clase: 'min-w-40 whitespace-normal text-muted-foreground', celda: (a) => a.ubicacion.ruta },
    { id: 'estado', encabezado: 'Estado', celda: (a) => <EstadoActivoBadge estado={a.estado} /> },
    { id: 'precio', encabezado: 'Precio de compra', tipo: 'cifra', celda: (a) => (a.precio_compra ? formatCOP(a.precio_compra) : '—') },
  ]

  const filtroUbicacion = ubicacion ? (
    <Boton
      variante="secundario"
      icono={<MapPin />}
      className="max-w-full border-brand-border bg-brand-soft hover:bg-brand-soft/70"
      onClick={() => filtrarUbicacion('')}
      aria-label={`Quitar el filtro de ubicación ${rutaFiltro}`}
    >
      <span className="truncate">{rutaFiltro || 'Ubicación'}</span>
      <X aria-hidden="true" className="size-4 text-muted-foreground" />
    </Boton>
  ) : (
    <div className="w-full md:w-60">
      <LocationPicker
        id="filtro-ubicacion"
        ubicaciones={ubicaciones.data ?? []}
        cargando={ubicaciones.isPending}
        onChange={filtrarUbicacion}
        etiqueta="Todas las ubicaciones"
        nombre="Filtrar por ubicación"
        className="h-control bg-card md:h-control"
      />
    </div>
  )

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Activos"
        descripcion={datos ? `${formatEntero(datos.total)} ${filtrando ? 'encontrados' : 'registrados'} · una fila por unidad física` : 'Una fila por unidad física'}
        claseAcciones="max-sm:w-full max-sm:[&>*]:flex-1"
        acciones={
          <>
            <Boton variante="secundario" icono={<Download />} cargando={exportar.isPending} textoCargando="Exportando…" onClick={exportarLista}>
              Exportar
            </Boton>
            <Boton asChild>
              <Link to="/admin/activos/nuevo">
                <Plus aria-hidden="true" />
                Registrar activo
              </Link>
            </Boton>
          </>
        }
      />
      <Pestanas
        etiqueta="Filtrar por estado"
        pestanas={PESTANAS}
        valor={pestaña}
        onValorChange={(v) => {
          setPestaña(v as Pestaña)
          setPagina(1)
        }}
        className="gap-4"
      >
        <TablaDatos<Activo>
          etiqueta="Activos"
          columnas={columnas}
          filas={busqueda.isPending || busqueda.isError ? undefined : activos}
          claveFila={(a) => a.id}
          cargando={busqueda.isPending}
          error={
            busqueda.isError
              ? { titulo: 'No se pudieron cargar los activos', descripcion: mensajeDeError(busqueda.error), onReintentar: () => void busqueda.refetch(), reintentando: busqueda.isFetching }
              : null
          }
          vacio={
            filtrando
              ? {
                  titulo: 'Nada coincide',
                  descripcion: 'Prueba con otro código, nombre, serial, estado o ubicación.',
                  accion: (
                    <Boton variante="secundario" onClick={limpiar}>
                      Limpiar filtros
                    </Boton>
                  ),
                }
              : {
                  titulo: 'Aún no hay activos',
                  descripcion: 'Escanea un sticker para crear el primero.',
                  accion: (
                    <>
                      <Boton asChild>
                        <Link to="/admin/activos/nuevo">Registrar activo</Link>
                      </Boton>
                      <Boton asChild variante="secundario">
                        <Link to="/contar/escanear">Ir a escanear</Link>
                      </Boton>
                    </>
                  ),
                }
          }
          onAbrirFila={(a) => void navigate(ficha(a))}
          accionesFila={(a) => <AccionesFila activo={a} />}
          tarjeta={(a) => <TarjetaActivo activo={a} />}
          barra={{
            busqueda: {
              valor: texto,
              onCambio: (v) => {
                setTexto(v)
                setPagina(1)
              },
              etiqueta: 'Buscar activos',
              placeholder: 'Código, nombre o serial',
              maxLength: 120,
            },
            filtros: filtroUbicacion,
            // Sin resultados, «Limpiar filtros» ya está en el vacío: no se repite.
            hayFiltros: filtrando && activos.length > 0,
            onLimpiar: limpiar,
          }}
          paginacion={
            datos
              ? {
                  desde,
                  hasta,
                  total: datos.total,
                  hayAnterior: pagina > 1,
                  haySiguiente: hayMas,
                  onAnterior: () => setPagina((p) => p - 1),
                  onSiguiente: () => setPagina((p) => p + 1),
                  ocupado: busqueda.isFetching,
                }
              : undefined
          }
        />
      </Pestanas>
    </div>
  )
}
