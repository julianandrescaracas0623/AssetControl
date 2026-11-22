import { type QueryClient, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { type Activo, aPrecioCanonico, CLAVE_ACTIVOS, precioParaCampo } from '@/lib/activos'
import { api, ErrorApi, type Esquemas, mensajeDeError } from '@/lib/api/cliente'
import { useApiAutenticada } from '@/lib/sesion'

// Cambios sobre un activo existente e historial (spec 005, T5–T7). Toda escritura va
// con la `row_version` leída (If-Match): si otra persona cambió el activo, el servidor
// responde 412 con el vigente, que aquí se guarda en la caché para que la ficha lo
// muestre sin perder lo que la persona escribió en el formulario.

export type EventoActivo = Esquemas['EventoActivo']
export type MotivoBaja = Esquemas['BajaActivoBody']['motivo']
export type MotivoReactivar = NonNullable<Esquemas['EstadoActivoBody']['motivo']>

export const MOTIVOS_BAJA: { valor: MotivoBaja; etiqueta: string }[] = [
  { valor: 'danado_sin_reparacion', etiqueta: 'Dañado sin reparación' },
  { valor: 'perdido', etiqueta: 'Perdido' },
  { valor: 'vendido_o_donado', etiqueta: 'Vendido o donado' },
  { valor: 'obsoleto', etiqueta: 'Obsoleto' },
  { valor: 'otro', etiqueta: 'Otro' },
]
export const MOTIVOS_REACTIVAR: { valor: MotivoReactivar; etiqueta: string }[] = [
  { valor: 'encontrado', etiqueta: 'Apareció' },
  { valor: 'baja_por_error', etiqueta: 'Se dio de baja por error' },
  { valor: 'otro', etiqueta: 'Otro' },
]
export const etiquetaMotivo = (valor: unknown) =>
  [...MOTIVOS_BAJA, ...MOTIVOS_REACTIVAR].find((m) => m.valor === valor)?.etiqueta ?? String(valor ?? '')

/** El activo vigente que trae un `412 version_desactualizada`, o `null`. */
export function vigenteDe(error: unknown): Activo | null {
  if (!(error instanceof ErrorApi) || error.code !== 'version_desactualizada') return null
  return (error.cuerpo as { activo?: Activo } | undefined)?.activo ?? null
}

// Fusiona en vez de reemplazar (spec 015, R4): un campo que la respuesta no trae (p. ej.
// `foto`) nunca borra lo que la ficha ya conocía; lo que sí trae (incluso `null`) manda.
function guardarEnCache(cliente: QueryClient, activo: Activo) {
  const fusionar = (previo: Activo | undefined): Activo => (previo ? { ...previo, ...activo } : activo)
  cliente.setQueryData<Activo>([...CLAVE_ACTIVOS, 'codigo', activo.codigo], fusionar)
  cliente.setQueryData<Activo>([...CLAVE_ACTIVOS, 'id', activo.id], fusionar)
  void cliente.invalidateQueries({ queryKey: [...CLAVE_ACTIVOS, 'buscar'] })
  void cliente.invalidateQueries({ queryKey: [...CLAVE_ACTIVOS, 'historial', activo.id] })
}

type Cambio<C> = { activo: Activo; cuerpo: C }

function useCambio<C>(enviar: (token: string, id: string, version: number, cuerpo: C) => Promise<{ activo: Activo }>) {
  const conToken = useApiAutenticada()
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ activo, cuerpo }: Cambio<C>) => conToken((t) => enviar(t, activo.id, activo.row_version, cuerpo)),
    onSuccess: ({ activo }) => guardarEnCache(cliente, activo),
    onError: (error) => {
      const vigente = vigenteDe(error)
      if (vigente) guardarEnCache(cliente, vigente)
    },
  })
}

export const useEditarActivo = () => useCambio(api.editarActivo)
export const useMoverActivo = () => useCambio(api.moverActivo)
export const useCambiarEstado = () => useCambio(api.cambiarEstadoActivo)
export const useDarDeBaja = () => useCambio(api.darDeBajaActivo)

/** Aviso de un cambio fallido: un 412 pide revisar (la ficha ya muestra el vigente). */
export function avisarErrorDeCambio(error: unknown) {
  if (vigenteDe(error)) toast.error('Alguien cambió este activo. Revisa los datos actuales y vuelve a intentarlo.')
  else toast.error(mensajeDeError(error))
}

/**
 * `activo` ↔ `en_reparacion`. Spec 015 (T2, Q5 A): enviar a reparación pide confirmación
 * (`requiereConfirmacion`); volver a activo sigue en un toque.
 */
export function useAlternarReparacion(activo: Activo) {
  const cambiar = useCambiarEstado()
  const destino = activo.estado === 'en_reparacion' ? 'activo' : 'en_reparacion'
  return {
    etiqueta: destino === 'activo' ? 'Volver a activo' : 'Enviar a reparación',
    requiereConfirmacion: destino === 'en_reparacion',
    guardando: cambiar.isPending,
    alternar: () =>
      cambiar.mutate(
        { activo, cuerpo: { estado: destino } },
        {
          onSuccess: () => toast.success(destino === 'activo' ? 'El activo volvió a estar activo' : 'Marcado en reparación: sigue contando en el inventario'),
          onError: avisarErrorDeCambio,
        },
      ),
  }
}


export function useHistorial(id: string | undefined) {
  const conToken = useApiAutenticada()
  return useInfiniteQuery({
    queryKey: [...CLAVE_ACTIVOS, 'historial', id],
    enabled: Boolean(id),
    retry: false,
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam }) => conToken((t) => api.historialActivo(t, id!, pageParam)),
    getNextPageParam: (pagina) => pagina.siguiente ?? undefined,
  })
}

// --- Editar (T5) ------------------------------------------------------------------------

export type CampoEdicion = 'nombre' | 'precio' | 'categoria' | 'serial' | 'marca' | 'modelo' | 'subtipo' | 'fecha'
export type CamposEdicion = Record<CampoEdicion, string>
export type ErroresEdicion = Partial<Record<CampoEdicion, string>>

export const ETIQUETAS: Record<CampoEdicion, string> = {
  nombre: 'Nombre',
  precio: 'Precio de compra',
  categoria: 'Categoría',
  serial: 'Serial',
  marca: 'Marca',
  modelo: 'Modelo',
  subtipo: 'Subtipo',
  fecha: 'Fecha de compra',
}
const OPCIONALES = ['serial', 'marca', 'modelo', 'subtipo'] as const

export function camposDe(activo: Activo): CamposEdicion {
  return {
    nombre: activo.nombre,
    precio: activo.precio_compra ? precioParaCampo(activo.precio_compra) : '',
    categoria: activo.categoria.id,
    serial: activo.serial ?? '',
    marca: activo.marca ?? '',
    modelo: activo.modelo ?? '',
    subtipo: activo.subtipo ?? '',
    fecha: activo.fecha_compra ?? '',
  }
}

/** Campos cuyo valor guardado difiere entre dos versiones del mismo activo. */
export function camposCambiados(antes: Activo, despues: Activo): CampoEdicion[] {
  const a = camposDe(antes)
  const d = camposDe(despues)
  return (Object.keys(ETIQUETAS) as CampoEdicion[]).filter((c) => a[c] !== d[c])
}

/** Valida y arma el cuerpo con solo lo que la persona cambió respecto de `base`. */
export function cuerpoDeEdicion(
  base: Activo,
  campos: CamposEdicion,
): { errores: ErroresEdicion; cuerpo?: Esquemas['EditarActivoBody'] } {
  const e: ErroresEdicion = {}
  const nombre = campos.nombre.trim()
  const precio = aPrecioCanonico(campos.precio)
  if (!nombre) e.nombre = 'Escribe el nombre'
  if (!campos.precio.trim()) e.precio = 'Escribe el precio'
  else if (!precio) e.precio = 'Escribe el precio en pesos, por ejemplo 389.900'
  if (campos.fecha && campos.fecha > new Date().toISOString().slice(0, 10)) e.fecha = 'La fecha no puede ser futura'
  if (Object.keys(e).length > 0) return { errores: e }

  const cuerpo: Esquemas['EditarActivoBody'] = {}
  if (nombre !== base.nombre) cuerpo.nombre = nombre
  if (precio !== base.precio_compra) cuerpo.precio_compra = precio!
  if (campos.categoria !== base.categoria.id) cuerpo.categoria_id = campos.categoria
  for (const campo of OPCIONALES) {
    const valor = campos[campo].trim() || null
    if (valor !== (base[campo] ?? null)) cuerpo[campo] = valor
  }
  const fecha = campos.fecha || null
  if (fecha !== (base.fecha_compra ?? null)) cuerpo.fecha_compra = fecha
  return { errores: e, cuerpo }
}

/**
 * Estado del formulario de edición. `base` es el activo tal como se abrió (lo que la
 * persona ve como "antes"); `version` es contra la que se guarda. Ante un 412 se
 * conserva lo escrito, se avisa qué cambió otra persona y se puede reaplicar.
 */
export function useEdicionActivo(activo: Activo, alGuardar: (activo: Activo, sinCambios: boolean) => void) {
  const editar = useEditarActivo()
  const [base, setBase] = useState(activo)
  const [version, setVersion] = useState(activo.row_version)
  const [campos, setCampos] = useState(() => camposDe(activo))
  const [errores, setErrores] = useState<ErroresEdicion>({})
  const [conflicto, setConflicto] = useState<{ vigente: Activo; cambiados: CampoEdicion[] } | null>(null)
  const [errorGeneral, setErrorGeneral] = useState<{ mensaje: string; reintentable: boolean } | null>(null)

  function cambiar(campo: CampoEdicion, valor: string) {
    setCampos((actual) => ({ ...actual, [campo]: valor }))
  }

  function guardar() {
    const { errores: e, cuerpo } = cuerpoDeEdicion(base, campos)
    setErrores(e)
    setErrorGeneral(null)
    if (!cuerpo) return
    if (Object.keys(cuerpo).length === 0) {
      alGuardar(conflicto?.vigente ?? base, true)
      return
    }
    editar.mutate(
      { activo: { ...base, row_version: version }, cuerpo },
      {
        onSuccess: ({ activo: guardado }) => {
          setConflicto(null)
          alGuardar(guardado, false)
        },
        onError: (error) => {
          const vigente = vigenteDe(error)
          if (vigente) {
            setConflicto({ vigente, cambiados: camposCambiados(base, vigente) })
            setVersion(vigente.row_version)
            return
          }
          if (!(error instanceof ErrorApi)) {
            setErrorGeneral({ mensaje: 'Ocurrió un error inesperado. Intenta de nuevo.', reintentable: true })
          } else if (error.code === 'precio_invalido') setErrores({ precio: error.message })
          else if (error.status === 404) {
            setErrorGeneral({ mensaje: 'La categoría elegida ya no existe. Elige otra.', reintentable: false })
          } else {
            setErrorGeneral({ mensaje: error.message, reintentable: error.status === 0 || error.status >= 500 })
          }
        },
      },
    )
  }

  /** Deja de lado lo escrito y parte del activo vigente. */
  function descartar() {
    if (!conflicto) return
    setBase(conflicto.vigente)
    setVersion(conflicto.vigente.row_version)
    setCampos(camposDe(conflicto.vigente))
    setConflicto(null)
    setErrores({})
  }

  return { campos, cambiar, errores, guardar, descartar, conflicto, errorGeneral, guardando: editar.isPending }
}
