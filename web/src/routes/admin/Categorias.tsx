import { ListPlus, Pencil, Plus, Tags } from 'lucide-react'
import { type FormEvent, useDeferredValue, useId, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, type ColumnaTabla, Dialogo, EncabezadoPagina, Esqueleto, Estado, TablaDatos } from '@/components/kit'
import { type Categoria, ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import {
  CLAVE_CATEGORIAS,
  normalizarBusqueda,
  useCargarSugeridas,
  useCategorias,
  useCrearCategoria,
  useRenombrarCategoria,
} from '@/lib/catalogo'
import { formatEntero } from '@/lib/format'

// /admin/categorias (spec 003, T6; R3, R6; plan §5): lista cerrada de la clínica. Las 6
// sugeridas (P8) se cargan con un botón y repetirlo no duplica. No se borran.
// Spec 015, T6 (R12, Q10 = A): con muchas categorías, búsqueda sin tildes ni mayúsculas y
// paginación en el cliente (la API devuelve la lista completa); `?q=` y `?pagina=` en la URL.
// Spec 016, T9 (R2, R3, R5): presentación con el kit. TablaDatos con su búsqueda y su
// paginación (que también devuelve el foco al otro botón al llegar a un extremo), filas
// nombradas por la categoría, tarjetas en el teléfono y Dialogo con Campo.

const NOMBRE_MAX = 120
const POR_PAGINA = 25
const FORMULARIO = 'formulario-categoria'

function DialogoCategoria({
  categoria,
  onCerrar,
  onCreada,
}: {
  categoria: Categoria | null
  onCerrar: () => void
  onCreada: (creada: Categoria) => void
}) {
  const crear = useCrearCategoria()
  const renombrar = useRenombrarCategoria()
  const mutacion = categoria ? renombrar : crear
  const id = useId()

  const error = mutacion.error instanceof ErrorApi ? mutacion.error : null
  const errorCampo =
    error?.code === 'nombre_duplicado'
      ? 'Ya existe una categoría con ese nombre.'
      : error?.code === 'solicitud_invalida'
        ? `Revisa el nombre: usa letras o números, hasta ${NOMBRE_MAX} caracteres.`
        : null
  const errorGeneral = mutacion.isError && !errorCampo ? mensajeDeError(mutacion.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const nombre = String(new FormData(evento.currentTarget).get('nombre') ?? '').trim()
    if (categoria) renombrar.mutate({ id: categoria.id, nombre }, { onSuccess: onCerrar })
    // La lista ya se recargó (la mutación espera la invalidación) cuando llega onSuccess.
    else crear.mutate(nombre, { onSuccess: ({ categoria: creada }) => onCreada(creada) })
  }

  return (
    <Dialogo
      abierto
      onAbiertoChange={(abierto) => !abierto && onCerrar()}
      titulo={categoria ? 'Renombrar categoría' : 'Nueva categoría'}
      descripcion={categoria ? 'El cambio se ve en todos los activos de esta categoría.' : 'Úsala para agrupar activos parecidos en el informe.'}
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form={FORMULARIO} cargando={mutacion.isPending}>
            {categoria ? 'Guardar' : 'Crear'}
          </Boton>
        </>
      }
    >
      <form id={FORMULARIO} onSubmit={alEnviar} className="flex flex-col gap-4">
        {errorGeneral && <Aviso tono="error" titulo={errorGeneral} />}
        <Campo
          id={`${id}-nombre`}
          etiqueta="Nombre"
          name="nombre"
          required
          maxLength={NOMBRE_MAX}
          autoComplete="off"
          defaultValue={categoria?.nombre ?? ''}
          error={errorCampo ?? undefined}
        />
      </form>
    </Dialogo>
  )
}

const plural = (n: number) => (n === 1 ? 'categoría' : 'categorías')

const COLUMNAS: ColumnaTabla<Categoria>[] = [{ id: 'nombre', encabezado: 'Nombre', principal: true, clase: 'max-w-0 truncate', celda: (c) => c.nombre }]

export default function Categorias() {
  const consulta = useCategorias()
  const sugeridas = useCargarSugeridas()
  const [edicion, setEdicion] = useState<{ categoria: Categoria | null } | null>(null)
  const [params, setParams] = useSearchParams()
  const cliente = useQueryClient()
  // El campo guarda lo que se escribe; la URL lo refleja para volver con el mismo filtro.
  const [texto, setTexto] = useState(() => params.get('q') ?? '')
  const filtro = normalizarBusqueda(useDeferredValue(texto))

  const todas = consulta.data
  const encontradas = useMemo(
    () => (todas && filtro ? todas.filter((c) => normalizarBusqueda(c.nombre).includes(filtro)) : (todas ?? [])),
    [todas, filtro],
  )
  const paginas = Math.max(1, Math.ceil(encontradas.length / POR_PAGINA))
  const pedida = Number.parseInt(params.get('pagina') ?? '1', 10)
  const pagina = Number.isFinite(pedida) ? Math.min(Math.max(pedida, 1), paginas) : 1
  const visibles = encontradas.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA)
  const desde = encontradas.length > 0 ? (pagina - 1) * POR_PAGINA + 1 : 0
  const hasta = desde + visibles.length - (visibles.length > 0 ? 1 : 0)

  function buscar(valor: string) {
    setTexto(valor)
    const siguiente = new URLSearchParams(params)
    // En la URL va recortado; el campo conserva lo escrito tal cual.
    if (valor.trim()) siguiente.set('q', valor.trim())
    else siguiente.delete('q')
    siguiente.delete('pagina')
    setParams(siguiente, { replace: true })
  }

  function irA(destino: number) {
    const siguiente = new URLSearchParams(params)
    if (destino > 1) siguiente.set('pagina', String(destino))
    else siguiente.delete('pagina')
    setParams(siguiente, { replace: true })
  }

  function cargarSugeridas() {
    sugeridas.mutate(undefined, {
      onSuccess: ({ creadas }) =>
        toast.success(
          creadas === 0 ? 'Ya estaban todas las sugeridas' : `Se agregaron ${creadas} ${creadas === 1 ? 'categoría' : 'categorías'}`,
        ),
      onError: (error) => toast.error(mensajeDeError(error)),
    })
  }

  // La nueva puede quedar en otra página o fuera del filtro: se avisa, se quita el filtro y
  // se salta a su página según el orden que devolvió el servidor.
  function alCrear(creada: Categoria) {
    setEdicion(null)
    toast.success(`Categoría «${creada.nombre}» creada`)
    setTexto('')
    const lista = cliente.getQueryData<Categoria[]>(CLAVE_CATEGORIAS) ?? []
    const indice = lista.findIndex((c) => c.id === creada.id)
    const destino = indice >= 0 ? Math.floor(indice / POR_PAGINA) + 1 : 1
    const siguiente = new URLSearchParams(params)
    siguiente.delete('q')
    if (destino > 1) siguiente.set('pagina', String(destino))
    else siguiente.delete('pagina')
    setParams(siguiente, { replace: true })
  }

  const nueva = () => setEdicion({ categoria: null })
  const total = todas?.length ?? 0
  const hay = total > 0

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Categorías"
        descripcion="Lista cerrada de tu clínica para clasificar los activos. Cada nombre es único, sin importar mayúsculas ni tildes."
        acciones={
          <>
            {hay && (
              <Boton variante="secundario" icono={<ListPlus />} onClick={cargarSugeridas} cargando={sugeridas.isPending}>
                Cargar sugeridas
              </Boton>
            )}
            <Boton icono={<Plus />} onClick={nueva}>
              Nueva categoría
            </Boton>
          </>
        }
      />

      {consulta.isPending ? (
        <Estado.Cargando etiqueta="Cargando categorías" className="max-w-2xl">
          <Esqueleto className="h-48 rounded-xl" />
        </Estado.Cargando>
      ) : consulta.isError ? (
        <Estado.Error
          titulo="No se pudieron cargar las categorías"
          descripcion={mensajeDeError(consulta.error)}
          onReintentar={() => void consulta.refetch()}
          reintentando={consulta.isFetching}
        />
      ) : !hay ? (
        <Estado.Vacio
          icono={<Tags />}
          titulo="Aún no hay categorías"
          descripcion="Empieza con las 6 sugeridas (Mobiliario, Electrónica, CPU, Periféricos, Electrodomésticos y Biomédicos) o crea las tuyas."
          accion={
            <>
              <Boton icono={<ListPlus />} onClick={cargarSugeridas} cargando={sugeridas.isPending}>
                Cargar las 6 sugeridas
              </Boton>
              <Boton variante="secundario" onClick={nueva}>
                Crear una
              </Boton>
            </>
          }
        />
      ) : (
        <TablaDatos
          etiqueta="Categorías"
          className="max-w-2xl"
          columnas={COLUMNAS}
          filas={visibles}
          claveFila={(c) => c.id}
          nombrarFilas
          barra={{
            busqueda: { valor: texto, onCambio: buscar, etiqueta: 'Buscar categorías', placeholder: 'Buscar por nombre', maxLength: NOMBRE_MAX },
            filtros: (
              <p role="status" className="text-etiqueta font-normal text-muted-foreground tabular-nums">
                <span>
                  {filtro
                    ? `${formatEntero(encontradas.length)} de ${formatEntero(total)} ${plural(total)}`
                    : `${formatEntero(total)} ${plural(total)}`}
                </span>
                {paginas > 1 && <span className="sr-only">{`. Página ${pagina} de ${paginas}`}</span>}
              </p>
            ),
          }}
          vacio={{
            titulo: 'Ninguna categoría coincide',
            descripcion: 'Prueba con otra parte del nombre. No importan las mayúsculas ni las tildes.',
            accion: (
              <Boton variante="secundario" onClick={() => buscar('')}>
                Limpiar búsqueda
              </Boton>
            ),
          }}
          accionesFila={(c) => (
            <Boton variante="fantasma" soloIcono aria-label={`Renombrar ${c.nombre}`} icono={<Pencil />} onClick={() => setEdicion({ categoria: c })} />
          )}
          paginacion={
            paginas > 1
              ? {
                  desde,
                  hasta,
                  total: encontradas.length,
                  hayAnterior: pagina > 1,
                  haySiguiente: pagina < paginas,
                  onAnterior: () => irA(pagina - 1),
                  onSiguiente: () => irA(pagina + 1),
                }
              : undefined
          }
        />
      )}

      {edicion && <DialogoCategoria categoria={edicion.categoria} onCerrar={() => setEdicion(null)} onCreada={alCrear} />}
    </div>
  )
}
