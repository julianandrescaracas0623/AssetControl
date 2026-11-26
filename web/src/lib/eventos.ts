import { Archive, ArchiveRestore, ArrowLeftRight, Camera, Check, CircleDollarSign, FileInput, MapPin, Pencil, Plus, Tag, Wrench, X } from 'lucide-react'
import type { ComponentType } from 'react'

import type { Rol } from '@/lib/api/cliente'
import { type EventoActivo, etiquetaMotivo } from '@/lib/cambiosActivo'
import { formatCOP } from '@/lib/format'

// Cómo se lee cada evento de un activo (spec 005; compartido con la actividad del Inicio,
// spec 010). Muestra lo que manda el servidor: al contador ya le llega sin precios (P13).
// Spec 020, T4: defensa en dos capas; `paraRol` quita los precios a quien no es admin
// aunque el servidor los mandara (el servidor sigue siendo la barrera).

const NOMBRES_CAMPO: Record<string, string> = {
  nombre: 'Nombre',
  serial: 'Serial',
  marca: 'Marca',
  modelo: 'Modelo',
  subtipo: 'Subtipo',
  fecha_compra: 'Fecha de compra',
}
const ESTADOS: Record<string, string> = { activo: 'activo', en_reparacion: 'en reparación', dado_de_baja: 'dado de baja' }

export type Tono = 'neutro' | 'marca' | 'exito' | 'aviso' | 'peligro'
export const TONOS: Record<Tono, string> = {
  neutro: 'bg-background text-foreground border-border',
  marca: 'bg-brand-soft text-brand-strong border-brand-border',
  exito: 'bg-success-soft text-success border-success-border',
  aviso: 'bg-warning-soft text-warning border-warning-border',
  peligro: 'bg-destructive/10 text-destructive border-destructive/30',
}

export type Vista = { icono: ComponentType<{ className?: string }>; tono: Tono; titulo: string; detalle?: string }

const texto = (v: unknown) => (v === null || v === undefined || v === '' ? 'vacío' : String(v))
const precio = (v: unknown) => (typeof v === 'string' ? formatCOP(v) : texto(v))
const ruta = (v: unknown) => (v && typeof v === 'object' ? texto((v as { ruta?: unknown }).ruta) : texto(v))
const nombreDe = (v: unknown) => (v && typeof v === 'object' ? texto((v as { nombre?: unknown }).nombre) : texto(v))

const sinPrecio = (o: object) => Object.fromEntries(Object.entries(o).filter(([k]) => !k.includes('precio')))

/**
 * Eventos tal como los ve el rol: sin «Precio cambiado» ni datos de precio salvo para el
 * admin (también los anidados en `datos.campos` de «Datos editados»).
 */
export function paraRol<E extends { tipo: string; datos?: unknown }>(eventos: E[], rol: Rol): E[] {
  if (rol === 'admin') return eventos
  return eventos
    .filter((e) => e.tipo !== 'precio_cambiado')
    .map((e) => {
      if (!e.datos || typeof e.datos !== 'object') return e
      const datos = sinPrecio(e.datos)
      if (datos.campos && typeof datos.campos === 'object') datos.campos = sinPrecio(datos.campos)
      return { ...e, datos }
    })
}

export function vista(evento: Pick<EventoActivo, 'tipo' | 'datos'>): Vista {
  const d = evento.datos as Record<string, unknown>
  switch (evento.tipo) {
    case 'creado': {
      const partes = [d.copiado_de ? 'Duplicado de un activo parecido' : 'Registrado con el sticker']
      if (typeof d.precio_compra === 'string') partes.push(formatCOP(d.precio_compra))
      return { icono: Plus, tono: 'marca', titulo: 'Activo creado', detalle: partes.join(' · ') }
    }
    case 'importado':
      return { icono: FileInput, tono: 'marca', titulo: 'Importado' }
    case 'verificado': {
      const esperada = d.ubicacion_esperada as { id?: string } | undefined
      const encontrada = d.ubicacion_encontrada as { id?: string } | undefined
      const otra = Boolean(esperada?.id && encontrada?.id && esperada.id !== encontrada.id)
      const partes = [
        d.sesion ? String(d.sesion) : null,
        `en ${ruta(d.ubicacion_encontrada)}${otra ? ` (esperada ${ruta(d.ubicacion_esperada)})` : ''}`,
        d.estado_fisico === 'danado' ? 'dañado' : 'ok',
        d.nota ? `«${String(d.nota)}»` : null,
      ].filter(Boolean)
      return {
        icono: otra ? ArrowLeftRight : Check,
        tono: otra || d.estado_fisico === 'danado' ? 'aviso' : 'exito',
        titulo: otra ? 'Verificado en otra ubicación' : 'Verificado',
        detalle: partes.join(' · '),
      }
    }
    case 'precio_cambiado':
      return { icono: CircleDollarSign, tono: 'neutro', titulo: 'Precio cambiado', detalle: `${precio(d.antes)} → ${precio(d.despues)}` }
    case 'categoria_cambiada':
      return { icono: Tag, tono: 'neutro', titulo: 'Categoría cambiada', detalle: `${nombreDe(d.antes)} → ${nombreDe(d.despues)}` }
    case 'datos_cambiados': {
      const campos = (d.campos ?? {}) as Record<string, { antes?: unknown; despues?: unknown }>
      const detalle = Object.entries(campos)
        .map(([campo, c]) => `${NOMBRES_CAMPO[campo] ?? campo}: ${texto(c.antes)} → ${texto(c.despues)}`)
        .join(' · ')
      return { icono: Pencil, tono: 'neutro', titulo: 'Datos editados', detalle }
    }
    case 'ubicacion_cambiada':
      return d.origen === 'discrepancia'
        ? { icono: MapPin, tono: 'neutro', titulo: 'Movido por el conteo', detalle: `${ruta(d.antes)} → ${ruta(d.despues)}${d.sesion ? ` · ${String(d.sesion)}` : ''}` }
        : { icono: MapPin, tono: 'neutro', titulo: 'Ubicación cambiada', detalle: `${ruta(d.antes)} → ${ruta(d.despues)}` }
    case 'discrepancia_descartada':
      return {
        icono: X,
        tono: 'neutro',
        titulo: 'Diferencia descartada',
        detalle: `Se vio en ${ruta(d.encontrada)}; sigue en ${ruta(d.esperada)}${d.sesion ? ` · ${String(d.sesion)}` : ''}`,
      }
    case 'estado_cambiado': {
      if (d.antes === 'dado_de_baja') {
        const nota = d.nota ? ` · «${String(d.nota)}»` : ''
        return { icono: ArchiveRestore, tono: 'exito', titulo: 'Reactivado', detalle: `${etiquetaMotivo(d.motivo)}${nota}` }
      }
      if (d.despues === 'en_reparacion') return { icono: Wrench, tono: 'aviso', titulo: 'Enviado a reparación' }
      if (d.antes === 'en_reparacion') return { icono: Check, tono: 'exito', titulo: 'Volvió de reparación' }
      return { icono: Check, tono: 'exito', titulo: `Pasó a ${ESTADOS[String(d.despues)] ?? texto(d.despues)}` }
    }
    case 'dado_de_baja': {
      const nota = d.nota ? ` · «${String(d.nota)}»` : ''
      return { icono: Archive, tono: 'peligro', titulo: 'Dado de baja', detalle: `${etiquetaMotivo(d.motivo)}${nota}` }
    }
    // Spec 012: la imagen anterior se borra al cambiar o quitar (Q2 B); queda el registro.
    case 'foto_agregada':
      return { icono: Camera, tono: 'neutro', titulo: 'Foto agregada' }
    case 'foto_cambiada':
      return { icono: Camera, tono: 'neutro', titulo: 'Foto cambiada', detalle: 'La foto anterior se borró.' }
    case 'foto_retirada':
      return { icono: Camera, tono: 'neutro', titulo: 'Foto quitada', detalle: 'La imagen se borró.' }
    default:
      return { icono: Pencil, tono: 'neutro', titulo: 'Cambio' }
  }
}
