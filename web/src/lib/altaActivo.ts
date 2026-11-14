import { useRef, useState } from 'react'

import { type Activo, aPrecioCanonico, type CuerpoAlta, normalizarCodigo, precioParaCampo, useCrearActivo } from '@/lib/activos'
import { ErrorApi, type Rol } from '@/lib/api/cliente'

// Estado y envío del formulario de alta (spec 004, T6; R3, R4, R6, Q3): lo comparten el
// alta del modo conteo y la de administración, cada una con su diseño.
// - El `id` del activo se genera al abrir el formulario y se reutiliza en cada
//   reintento: reenviar nunca duplica (R4). Cambia solo al empezar otro activo.
// - Copiar de un parecido: el contador duplica (`copiar_de`: el servidor copia el precio
//   sin mostrárselo y no deja cambiar nombre ni categoría); el admin recibe los datos en
//   el formulario, incluido el precio, y puede editarlos.

export type CampoAlta =
  | 'codigo'
  | 'nombre'
  | 'precio'
  | 'categoria'
  | 'ubicacion'
  | 'serial'
  | 'marca'
  | 'modelo'
  | 'subtipo'
  | 'fecha'
export type ErroresAlta = Partial<Record<CampoAlta | 'confirmado', string>>
export type ActivoResumen = { id: string; codigo: string; nombre: string }

const VACIO: Record<CampoAlta, string> = {
  codigo: '',
  nombre: '',
  precio: '',
  categoria: '',
  ubicacion: '',
  serial: '',
  marca: '',
  modelo: '',
  subtipo: '',
  fecha: '',
}

const opcional = (texto: string) => texto.trim() || null

export function useAltaActivo({
  rol,
  codigoInicial = '',
  ubicacionInicial = '',
}: {
  rol: Rol
  codigoInicial?: string
  ubicacionInicial?: string
}) {
  const crear = useCrearActivo()
  const id = useRef(crypto.randomUUID())
  const [campos, setCampos] = useState({ ...VACIO, codigo: codigoInicial, ubicacion: ubicacionInicial })
  const [confirmado, setConfirmado] = useState(false)
  const [copiado, setCopiado] = useState<Activo | null>(null)
  const [errores, setErrores] = useState<ErroresAlta>({})
  const [creado, setCreado] = useState<Activo | null>(null)
  const [existente, setExistente] = useState<ActivoResumen | null>(null)
  const [errorGeneral, setErrorGeneral] = useState<{ mensaje: string; reintentable: boolean } | null>(null)

  const duplicando = copiado !== null && rol === 'contador'

  function cambiar(campo: CampoAlta, valor: string) {
    setCampos((actual) => ({ ...actual, [campo]: valor }))
    if (campo === 'codigo') setExistente(null)
  }

  function copiar(activo: Activo) {
    setCopiado(activo)
    setCampos((actual) => ({
      ...actual,
      nombre: activo.nombre,
      categoria: activo.categoria.id,
      ubicacion: actual.ubicacion || activo.ubicacion.id,
      marca: activo.marca ?? '',
      modelo: activo.modelo ?? '',
      subtipo: activo.subtipo ?? '',
      precio: activo.precio_compra ? precioParaCampo(activo.precio_compra) : '',
    }))
  }

  function quitarCopia() {
    setCopiado(null)
    if (rol === 'contador') setCampos((actual) => ({ ...actual, nombre: '', categoria: '', marca: '', modelo: '', subtipo: '' }))
  }

  function validar(confirmarCodigo: boolean): { errores: ErroresAlta; cuerpo?: CuerpoAlta } {
    const e: ErroresAlta = {}
    const codigo = normalizarCodigo(campos.codigo)
    if (!campos.codigo.trim()) e.codigo = 'Escanea o escribe el código del sticker'
    else if (!codigo) e.codigo = 'El código usa letras sin tilde, números o - . / _, sin espacios (máximo 40)'
    else if (confirmarCodigo && !confirmado) e.confirmado = 'Confirma que el código coincide con el sticker'
    if (!campos.ubicacion) e.ubicacion = 'Elige la ubicación'
    if (duplicando) {
      if (Object.keys(e).length > 0) return { errores: e }
      return {
        errores: e,
        cuerpo: { id: id.current, codigo: codigo!, copiar_de: copiado!.id, ubicacion_id: campos.ubicacion, serial: opcional(campos.serial) },
      }
    }
    const precio = aPrecioCanonico(campos.precio)
    if (!campos.nombre.trim()) e.nombre = 'Escribe el nombre'
    if (!campos.precio.trim()) e.precio = 'Escribe el precio'
    else if (!precio) e.precio = 'Escribe el precio en pesos, por ejemplo 389.900'
    if (!campos.categoria) e.categoria = 'Elige la categoría'
    if (campos.fecha && campos.fecha > new Date().toISOString().slice(0, 10)) e.fecha = 'La fecha no puede ser futura'
    if (Object.keys(e).length > 0) return { errores: e }
    return {
      errores: e,
      cuerpo: {
        id: id.current,
        codigo: codigo!,
        nombre: campos.nombre.trim(),
        precio_compra: precio!,
        categoria_id: campos.categoria,
        ubicacion_id: campos.ubicacion,
        serial: opcional(campos.serial),
        marca: opcional(campos.marca),
        modelo: opcional(campos.modelo),
        subtipo: opcional(campos.subtipo),
        fecha_compra: campos.fecha || null,
      },
    }
  }

  function enviar({
    confirmarCodigo = true,
    alCrear,
  }: { confirmarCodigo?: boolean; alCrear?: (activo: Activo) => void } = {}) {
    const { errores: e, cuerpo } = validar(confirmarCodigo)
    setErrores(e)
    setErrorGeneral(null)
    if (!cuerpo) return
    crear.mutate(cuerpo, {
      onSuccess: ({ activo }) => (alCrear ? alCrear(activo) : setCreado(activo)),
      onError: (error) => {
        if (!(error instanceof ErrorApi)) {
          setErrorGeneral({ mensaje: 'Ocurrió un error inesperado. Intenta de nuevo.', reintentable: true })
          return
        }
        if (error.code === 'codigo_existente') {
          const cuerpoError = error.cuerpo as { activo?: ActivoResumen } | undefined
          setExistente(cuerpoError?.activo ?? null)
          setErrores({ codigo: error.message })
        } else if (error.code === 'codigo_invalido') setErrores({ codigo: error.message })
        else if (error.code === 'precio_invalido') setErrores({ precio: error.message })
        else if (error.code === 'ubicacion_invalida') setErrores({ ubicacion: error.message })
        else if (error.status === 404) {
          setErrorGeneral({
            mensaje: 'La categoría, la ubicación o el activo copiado ya no existe. Vuelve a elegirlos.',
            reintentable: false,
          })
        } else if (error.code === 'solicitud_invalida') {
          setErrorGeneral({ mensaje: `${error.message} Revisa los datos opcionales.`, reintentable: false })
        } else {
          setErrorGeneral({ mensaje: error.message, reintentable: error.status === 0 || error.status >= 500 })
        }
      },
    })
  }

  function otro({ conservarUbicacion = true }: { conservarUbicacion?: boolean } = {}) {
    id.current = crypto.randomUUID()
    setCampos((actual) => ({ ...VACIO, ubicacion: conservarUbicacion ? actual.ubicacion : '' }))
    setConfirmado(false)
    setCopiado(null)
    setErrores({})
    setCreado(null)
    setExistente(null)
    setErrorGeneral(null)
    crear.reset()
  }

  /** Otra unidad igual: conserva los datos y limpia código y serial (nuevo `id`). */
  function siguienteUnidad() {
    id.current = crypto.randomUUID()
    setCampos((actual) => ({ ...actual, codigo: '', serial: '' }))
    setConfirmado(false)
    setErrores({})
    setExistente(null)
    setErrorGeneral(null)
    crear.reset()
  }

  return {
    siguienteUnidad,
    campos,
    cambiar,
    confirmado,
    setConfirmado,
    copiado,
    copiar,
    quitarCopia,
    duplicando,
    errores,
    enviar,
    guardando: crear.isPending,
    creado,
    existente,
    errorGeneral,
    otro,
  }
}
