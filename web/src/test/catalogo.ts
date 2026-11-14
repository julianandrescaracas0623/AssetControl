import type { Categoria, Rol, Ubicacion } from '@/lib/api/cliente'
import type { Activo } from '@/lib/activos'
import type { SesionConteo, Verificacion } from '@/lib/sesiones'
import { errorApi, json, type Manejador } from './sesion'

// API del catálogo simulada en memoria (spec 003): responde como el backend lo
// esencial (crear, listar, renombrar, activar) para probar las pantallas con
// `simularSesion(rol, catalogo.manejador)`. Los errores puntuales se fuerzan con
// `catalogo.fallar(ruta, respuesta)`.

export function crearCatalogo(
  inicial: {
    ubicaciones?: Ubicacion[]
    categorias?: Categoria[]
    activos?: Activo[]
    rol?: Rol
    sesiones?: SesionConteo[]
  } = {},
) {
  const ubicaciones = [...(inicial.ubicaciones ?? [])]
  const categorias = [...(inicial.categorias ?? [])]
  const activos = [...(inicial.activos ?? [])]
  const sesiones = [...(inicial.sesiones ?? [])]
  const verificaciones: Verificacion[] = []
  const resoluciones = new Map<string, { tipo: 'aplicada' | 'descartada'; en: string }>()
  const rol = inicial.rol ?? 'admin'
  const sinPrecio = (a: Activo) => {
    if (rol === 'admin') return { ...a }
    const resto: Partial<Activo> = { ...a }
    delete resto.precio_compra
    return resto
  }
  const ruta = (id: string) => {
    const u = ubicaciones.find((x) => x.id === id)
    if (!u) return ''
    const sala = u.tipo === 'box' && u.padre_id ? ubicaciones.find((x) => x.id === u.padre_id) : undefined
    return sala ? `${sala.nombre} › ${u.nombre}` : u.nombre
  }
  const fallos = new Map<string, () => Response>()
  const eventos: { seq: number; tipo: string; datos: Record<string, unknown>; activo: string }[] = []
  let siguiente = 1
  const nuevoId = () => `00000000-0000-4000-8000-${String(siguiente++).padStart(12, '0')}`
  const cuerpo = (init: RequestInit) => JSON.parse(String(init.body ?? '{}')) as Record<string, unknown>

  const manejador: Manejador = (url, init) => {
    const metodo = (init.method ?? 'GET').toUpperCase()
    const forzado = fallos.get(`${metodo} ${url}`)
    if (forzado) {
      fallos.delete(`${metodo} ${url}`)
      return forzado()
    }
    if (url === '/api/ubicaciones' && metodo === 'GET') return json(200, { ubicaciones })
    if (url === '/api/ubicaciones' && metodo === 'POST') {
      const b = cuerpo(init)
      const u: Ubicacion = {
        id: nuevoId(),
        nombre: String(b.nombre).trim(),
        tipo: b.tipo as Ubicacion['tipo'],
        padre_id: (b.padre_id as string | undefined) ?? null,
        activa: true,
      }
      ubicaciones.push(u)
      return json(201, { ubicacion: u })
    }
    const ubi = url.match(/^\/api\/ubicaciones\/(.+)$/)
    if (ubi && metodo === 'PATCH') {
      const u = ubicaciones.find((x) => x.id === decodeURIComponent(ubi[1]))
      if (!u) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      Object.assign(u, cuerpo(init))
      return json(200, { ubicacion: u })
    }
    const [ruta0, consulta = ''] = url.split('?')
    const q = new URLSearchParams(consulta)
    if (ruta0 === '/api/activos/por-codigo' && metodo === 'GET') {
      const codigo = (q.get('codigo') ?? '').trim().toUpperCase()
      const a = activos.find((x) => x.codigo === codigo)
      return a ? json(200, { activo: sinPrecio(a) }) : errorApi(404, 'no_encontrado', 'El recurso no existe.')
    }
    if (ruta0 === '/api/activos/sugerencias' && metodo === 'GET') {
      const campo = q.get('campo') as 'nombre' | 'marca' | 'modelo' | 'subtipo'
      const texto = (q.get('q') ?? '').toLowerCase()
      const valores = [...new Set(activos.map((a) => a[campo]).filter((v): v is string => Boolean(v)))]
      return json(200, { valores: valores.filter((v) => v.toLowerCase().includes(texto)).slice(0, 8) })
    }
    if (ruta0 === '/api/activos' && metodo === 'GET') {
      const texto = (q.get('q') ?? '').toLowerCase()
      const ubicacionId = q.get('ubicacion_id')
      const estado = q.get('estado')
      const encontrados = activos.filter(
        (a) =>
          (!texto || a.codigo.toLowerCase().includes(texto) || a.nombre.toLowerCase().includes(texto)) &&
          (!ubicacionId || a.ubicacion.id === ubicacionId) &&
          (!estado || a.estado === estado),
      )
      const pagina = Number(q.get('pagina') ?? '1')
      return json(200, {
        activos: encontrados.slice((pagina - 1) * 25, pagina * 25).map(sinPrecio),
        total: encontrados.length,
        pagina,
        por_pagina: 25,
      })
    }
    const act = ruta0.match(/^\/api\/activos\/([0-9a-f-]{36})$/)
    if (act && metodo === 'GET') {
      const a = activos.find((x) => x.id === act[1])
      return a ? json(200, { activo: sinPrecio(a) }) : errorApi(404, 'no_encontrado', 'El recurso no existe.')
    }
    // Spec 006: sesiones y verificaciones.
    if (ruta0 === '/api/sesiones' && metodo === 'GET') return json(200, { sesiones })
    if (ruta0 === '/api/sesiones/abierta' && metodo === 'GET') {
      return json(200, { sesion: sesiones.find((x) => x.estado === 'abierta') ?? null })
    }
    if (ruta0 === '/api/sesiones' && metodo === 'POST') {
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
      if (sesiones.some((x) => x.estado === 'abierta')) {
        return errorApi(409, 'sesion_abierta_existente', 'Ya hay una sesión de conteo abierta. Ciérrala antes de abrir otra.')
      }
      const b = cuerpo(init)
      const nueva: SesionConteo = {
        id: nuevoId(),
        nombre: String(b.nombre).trim(),
        tipo: 'conteo',
        estado: 'abierta',
        fecha_corte: String(b.fecha_corte),
        abierta_por: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' },
        abierta_en: '2026-11-14T13:00:00+00:00',
        cerrada_por: null,
        cerrada_en: null,
      }
      sesiones.unshift(nueva)
      return json(201, { sesion: nueva })
    }
    const dis = ruta0.match(/^\/api\/sesiones\/([0-9a-f-]{36})\/(discrepancias(?:\/aplicar|\/descartar)?|pendientes)$/)
    if (dis) {
      const sesion = sesiones.find((x) => x.id === dis[1])
      if (!sesion) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const vigentes = new Map<string, Verificacion>()
      for (const v of verificaciones.filter((x) => x.sesion_id === sesion.id)) vigentes.set(v.activo.id, v)
      const estadoDe = (v: Verificacion) => {
        const r = resoluciones.get(v.id)
        if (r) return r.tipo
        const a = activos.find((x) => x.id === v.activo.id)!
        return a.ubicacion.id === v.ubicacion_esperada.id ? 'pendiente' : 'desfasada'
      }
      if (dis[2] === 'pendientes' && metodo === 'GET') {
        const ubicacionId = q.get('ubicacion_id')
        const lista = activos.filter(
          (a) => a.estado !== 'dado_de_baja' && !vigentes.has(a.id) && (!ubicacionId || a.ubicacion.id === ubicacionId),
        )
        return json(200, {
          activos: lista.map((a) => ({ id: a.id, codigo: a.codigo, nombre: a.nombre, categoria: a.categoria, ubicacion: { id: a.ubicacion.id, ruta: a.ubicacion.ruta }, estado: a.estado })),
          total: lista.length,
          pagina: 1,
          por_pagina: 50,
        })
      }
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
      if (dis[2] === 'discrepancias' && metodo === 'GET') {
        const filtro = q.get('estado') ?? 'por_resolver'
        const items = [...vigentes.values()]
          .filter((v) => v.ubicacion_encontrada.id !== v.ubicacion_esperada.id)
          .map((v) => {
            const a = activos.find((x) => x.id === v.activo.id)!
            const estado = estadoDe(v)
            const r = resoluciones.get(v.id)
            return {
              verificacion_id: v.id,
              activo: { ...v.activo, estado: a.estado },
              ubicacion_esperada: v.ubicacion_esperada,
              ubicacion_encontrada: v.ubicacion_encontrada,
              ubicacion_actual: { id: a.ubicacion.id, ruta: a.ubicacion.ruta },
              verificado_por: v.verificado_por,
              recibido_en: v.recibido_en,
              estado,
              resolucion: r ? { tipo: r.tipo, por: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' }, en: r.en } : null,
            }
          })
          .filter((d) => filtro === 'todas' || (filtro === 'resueltas') === (d.estado === 'aplicada' || d.estado === 'descartada'))
        return json(200, { discrepancias: items })
      }
      if (metodo === 'POST') {
        const b = cuerpo(init)
        const aplicar = dis[2].endsWith('aplicar')
        const resultados = (b.verificaciones as string[]).map((id) => {
          const v = verificaciones.find((x) => x.id === id && x.sesion_id === sesion.id)
          if (!v) return { verificacion_id: id, resultado: 'no_encontrada' }
          const a = activos.find((x) => x.id === v.activo.id)!
          const activo = () => ({ id: a.id, codigo: a.codigo, nombre: a.nombre, ubicacion: { id: a.ubicacion.id, ruta: a.ubicacion.ruta } })
          if (resoluciones.has(id)) return { verificacion_id: id, resultado: 'ya_resuelta', activo: activo() }
          if (vigentes.get(a.id)?.id !== id) return { verificacion_id: id, resultado: 'ya_no_es_discrepancia', activo: activo() }
          if (!aplicar) {
            resoluciones.set(id, { tipo: 'descartada', en: '2026-11-14T17:00:00+00:00' })
            return { verificacion_id: id, resultado: 'descartada', activo: activo() }
          }
          if (a.ubicacion.id !== v.ubicacion_esperada.id) {
            if (a.ubicacion.id === v.ubicacion_encontrada.id) return { verificacion_id: id, resultado: 'ya_en_la_encontrada', activo: activo() }
            if (!b.confirmar_desfase) return { verificacion_id: id, resultado: 'desfasada', activo: activo() }
          }
          a.ubicacion = { id: v.ubicacion_encontrada.id, nombre: ubicaciones.find((u) => u.id === v.ubicacion_encontrada.id)?.nombre ?? '', ruta: v.ubicacion_encontrada.ruta }
          a.row_version += 1
          resoluciones.set(id, { tipo: 'aplicada', en: '2026-11-14T17:00:00+00:00' })
          return { verificacion_id: id, resultado: 'aplicada', activo: activo() }
        })
        return json(200, { resultados })
      }
    }
    const ses = ruta0.match(/^\/api\/sesiones\/([0-9a-f-]{36})(\/verificaciones)?$/)
    if (ses) {
      const sesion = sesiones.find((x) => x.id === ses[1])
      if (!sesion) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const conPrecio = (v: Verificacion) => {
        if (rol === 'admin') return v
        const resto: Partial<Verificacion> = { ...v }
        delete resto.precio_al_contar
        return resto
      }
      if (!ses[2] && metodo === 'GET') {
        const grupos = new Map<string, { ruta: string; total: number; verificados: number }>()
        for (const a of activos.filter((x) => x.estado !== 'dado_de_baja')) {
          const g = grupos.get(a.ubicacion.id) ?? { ruta: a.ubicacion.ruta, total: 0, verificados: 0 }
          g.total += 1
          if (verificaciones.some((v) => v.sesion_id === sesion.id && v.activo.id === a.id)) g.verificados += 1
          grupos.set(a.ubicacion.id, g)
        }
        const por_ubicacion = [...grupos.entries()].map(([id, g]) => ({
          ubicacion: { id, ruta: g.ruta },
          total: g.total,
          verificados: g.verificados,
          pendientes: g.total - g.verificados,
        }))
        const total = por_ubicacion.reduce((n, f) => n + f.total, 0)
        const verificados = por_ubicacion.reduce((n, f) => n + f.verificados, 0)
        return json(200, { sesion, avance: { total, verificados, pendientes: total - verificados, por_ubicacion } })
      }
      if (ses[2] && metodo === 'GET') {
        const ultima = verificaciones.filter((v) => v.sesion_id === sesion.id && v.activo.id === q.get('activo_id')).at(-1)
        return json(200, { verificacion: ultima ? conPrecio(ultima) : null })
      }
      if (ses[2] && metodo === 'POST') {
        const b = cuerpo(init)
        const previa = verificaciones.find((v) => v.id === b.id)
        if (previa) return json(200, { verificacion: conPrecio(previa) })
        if (sesion.estado !== 'abierta') return errorApi(409, 'sesion_cerrada', 'La sesión se cerró: esta verificación no se guardó.')
        const a = activos.find((x) => x.id === b.activo_id)
        if (!a) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
        if (a.estado === 'dado_de_baja') return errorApi(409, 'activo_dado_de_baja', 'El activo está dado de baja: no se puede verificar.')
        const encontrada = String(b.ubicacion_encontrada_id)
        const v: Verificacion = {
          id: String(b.id),
          sesion_id: sesion.id,
          activo: { id: a.id, codigo: a.codigo, nombre: a.nombre },
          ubicacion_esperada: { id: a.ubicacion.id, ruta: a.ubicacion.ruta },
          ubicacion_encontrada: { id: encontrada, ruta: ruta(encontrada) },
          estado_fisico: b.estado_fisico as Verificacion['estado_fisico'],
          nota: (b.nota as string | null | undefined) ?? null,
          verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: rol === 'admin' ? 'Ana Torres' : 'Luis Pérez' },
          ocurrido_en: (b.ocurrido_en as string | null | undefined) ?? null,
          recibido_en: '2026-11-14T15:44:00+00:00',
          seq: verificaciones.length + 1,
          precio_al_contar: a.precio_compra,
        }
        verificaciones.push(v)
        return json(201, { verificacion: conPrecio(v) })
      }
    }
    // Spec 005: cambios con If-Match (412 con el vigente) e historial.
    const cambio = ruta0.match(/^\/api\/activos\/([0-9a-f-]{36})(?:\/(mover|estado|baja))?$/)
    if (cambio && (metodo === 'PATCH' || (metodo === 'POST' && cambio[2]))) {
      const a = activos.find((x) => x.id === cambio[1])
      if (!a) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const version = new Headers(init.headers).get('If-Match')?.replace(/"/g, '')
      if (!version) return errorApi(428, 'falta_version', 'Falta la versión del activo.')
      if (Number(version) !== a.row_version) {
        return json(412, {
          error: { code: 'version_desactualizada', message: 'Alguien cambió este activo.', request_id: 'r' },
          activo: { ...a },
        })
      }
      const b = cuerpo(init)
      const reactivar = cambio[2] === 'estado' && a.estado === 'dado_de_baja' && b.estado === 'activo'
      if (a.estado === 'dado_de_baja' && !reactivar) {
        return errorApi(409, 'activo_dado_de_baja', 'El activo está dado de baja: solo se puede reactivar.')
      }
      const evento = (tipo: string, datos: Record<string, unknown>) =>
        eventos.unshift({ seq: eventos.length + 100, tipo, datos, activo: a.id })
      if (metodo === 'PATCH') {
        if ('nombre' in b) a.nombre = String(b.nombre)
        if ('precio_compra' in b) {
          evento('precio_cambiado', { antes: a.precio_compra, despues: b.precio_compra })
          a.precio_compra = String(b.precio_compra)
        }
        if ('categoria_id' in b) {
          const c = categorias.find((x) => x.id === b.categoria_id)!
          a.categoria = { id: c.id, nombre: c.nombre }
        }
        for (const campo of ['serial', 'marca', 'modelo', 'subtipo', 'fecha_compra'] as const) {
          if (campo in b) a[campo] = (b[campo] as string | null) ?? null
        }
      } else if (cambio[2] === 'mover') {
        const destino = String(b.ubicacion_id)
        evento('ubicacion_cambiada', { antes: { id: a.ubicacion.id, ruta: a.ubicacion.ruta }, despues: { id: destino, ruta: ruta(destino) } })
        a.ubicacion = { id: destino, nombre: ubicaciones.find((u) => u.id === destino)?.nombre ?? '', ruta: ruta(destino) }
      } else if (cambio[2] === 'estado') {
        evento('estado_cambiado', { antes: a.estado, despues: b.estado, ...(b.motivo ? { motivo: b.motivo } : {}) })
        a.estado = b.estado as Activo['estado']
      } else {
        evento('dado_de_baja', { motivo: b.motivo, ...(b.nota ? { nota: b.nota } : {}) })
        a.estado = 'dado_de_baja'
      }
      a.row_version += 1
      return json(200, { activo: { ...a } }, { ETag: `"${a.row_version}"` })
    }
    const his = ruta0.match(/^\/api\/activos\/([0-9a-f-]{36})\/historial$/)
    if (his && metodo === 'GET') {
      const a = activos.find((x) => x.id === his[1])
      if (!a) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const propios = [
        ...eventos.filter((e) => e.activo === a.id),
        { seq: 1, tipo: 'creado', datos: { codigo: a.codigo, nombre: a.nombre, precio_compra: a.precio_compra }, activo: a.id },
      ]
        .filter((e) => rol === 'admin' || e.tipo !== 'precio_cambiado')
        .map(({ seq, tipo, datos }) => ({
          seq,
          tipo,
          ocurrido_en: '2026-11-14T15:30:00+00:00',
          autor: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' },
          datos: rol === 'admin' ? datos : Object.fromEntries(Object.entries(datos).filter(([k]) => !k.includes('precio'))),
        }))
      return json(200, { eventos: propios, siguiente: null })
    }
    if (ruta0 === '/api/activos' && metodo === 'POST') {
      const b = cuerpo(init)
      const codigo = String(b.codigo ?? '').trim().toUpperCase()
      const previo = activos.find((x) => x.id === b.id)
      if (previo) return json(200, { activo: sinPrecio(previo) })
      const otro = activos.find((x) => x.codigo === codigo)
      if (otro) {
        return json(409, {
          error: { code: 'codigo_existente', message: 'Ese código ya está registrado en otro activo.', request_id: 'r' },
          activo: { id: otro.id, codigo: otro.codigo, nombre: otro.nombre },
        })
      }
      const origen = b.copiar_de ? activos.find((x) => x.id === b.copiar_de) : undefined
      const categoriaId = String(origen?.categoria.id ?? b.categoria_id)
      const ubicacionId = String(b.ubicacion_id ?? origen?.ubicacion.id)
      const nuevo: Activo = {
        id: String(b.id),
        codigo,
        nombre: String(origen?.nombre ?? b.nombre),
        categoria: { id: categoriaId, nombre: categorias.find((c) => c.id === categoriaId)?.nombre ?? '' },
        ubicacion: {
          id: ubicacionId,
          nombre: ubicaciones.find((u) => u.id === ubicacionId)?.nombre ?? '',
          ruta: ruta(ubicacionId),
        },
        serial: (b.serial as string | null) ?? null,
        marca: (origen?.marca ?? b.marca ?? null) as string | null,
        modelo: (origen?.modelo ?? b.modelo ?? null) as string | null,
        subtipo: (origen?.subtipo ?? b.subtipo ?? null) as string | null,
        fecha_compra: (b.fecha_compra as string | null) ?? null,
        estado: 'activo',
        row_version: 1,
        creado_en: '2026-11-14T12:00:00+00:00',
        precio_compra: String(b.precio_compra ?? origen?.precio_compra ?? '0.00'),
      }
      activos.unshift(nuevo)
      return json(201, { activo: sinPrecio(nuevo) })
    }
    if (url === '/api/categorias' && metodo === 'GET') return json(200, { categorias })
    if (url === '/api/categorias' && metodo === 'POST') {
      const c = { id: nuevoId(), nombre: String(cuerpo(init).nombre).trim() }
      categorias.push(c)
      return json(201, { categoria: c })
    }
    const cat = url.match(/^\/api\/categorias\/([^/]+)$/)
    if (cat && cat[1] !== 'sugeridas' && metodo === 'PATCH') {
      const c = categorias.find((x) => x.id === decodeURIComponent(cat[1]))
      if (!c) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      c.nombre = String(cuerpo(init).nombre)
      return json(200, { categoria: c })
    }
    if (url === '/api/categorias/sugeridas' && metodo === 'POST') {
      const antes = categorias.length
      for (const nombre of ['Mobiliario', 'Electrónica', 'CPU', 'Periféricos', 'Electrodomésticos', 'Biomédicos']) {
        if (!categorias.some((c) => c.nombre.toLowerCase() === nombre.toLowerCase())) {
          categorias.push({ id: nuevoId(), nombre })
        }
      }
      return json(200, { categorias, creadas: categorias.length - antes })
    }
    return undefined
  }

  return {
    ubicaciones,
    categorias,
    activos,
    manejador,
    fallar(clave: string, respuesta: () => Response) {
      fallos.set(clave, respuesta)
    },
    sesiones,
    verificaciones,
    /** El cierre llega con la 008: aquí se simula. */
    cerrarSesion(id: string) {
      const x = sesiones.find((y) => y.id === id)!
      x.estado = 'cerrada'
      x.cerrada_en = '2026-11-14T16:00:00+00:00'
      x.cerrada_por = x.abierta_por
    },
    /** Otra persona cambia el activo: sube su versión sin que la pantalla lo sepa. */
    cambiarPorOtro(id: string, cambios: Partial<Activo>) {
      const a = activos.find((x) => x.id === id)!
      Object.assign(a, cambios)
      a.row_version += 1
    },
  }
}

export const ub = (id: string, nombre: string, tipo: Ubicacion['tipo'], padre_id: string | null, activa = true): Ubicacion => ({
  id,
  nombre,
  tipo,
  padre_id,
  activa,
})

export function activoDe(
  datos: Partial<Activo> & Pick<Activo, 'id' | 'codigo' | 'nombre'>,
  catalogo: { categoria: Categoria; ubicacion: Ubicacion; ruta?: string },
): Activo {
  return {
    categoria: { id: catalogo.categoria.id, nombre: catalogo.categoria.nombre },
    ubicacion: { id: catalogo.ubicacion.id, nombre: catalogo.ubicacion.nombre, ruta: catalogo.ruta ?? catalogo.ubicacion.nombre },
    serial: null,
    marca: null,
    modelo: null,
    subtipo: null,
    fecha_compra: null,
    estado: 'activo',
    row_version: 1,
    creado_en: '2026-11-01T12:00:00+00:00',
    precio_compra: '1390000.00',
    ...datos,
  }
}

/** Catálogo pequeño para las pruebas de pantallas de activos (spec 004). */
export function catalogoDemo(rol: Rol = 'admin', opciones: { sesiones?: SesionConteo[] } = {}) {
  const ubicaciones = [
    ub('00000000-0000-4000-8000-0000000000a1', 'Sede Principal', 'sede', null),
    ub('00000000-0000-4000-8000-0000000000a2', 'Administración', 'sala', '00000000-0000-4000-8000-0000000000a1'),
    ub('00000000-0000-4000-8000-0000000000a3', 'Consultorio 1', 'sala', '00000000-0000-4000-8000-0000000000a1'),
    ub('00000000-0000-4000-8000-0000000000a4', 'Box 2', 'box', '00000000-0000-4000-8000-0000000000a3'),
  ]
  const categorias = [
    { id: '00000000-0000-4000-8000-0000000000c1', nombre: 'Electrónica' },
    { id: '00000000-0000-4000-8000-0000000000c2', nombre: 'Mobiliario' },
  ]
  const activos = [
    activoDe(
      { id: '00000000-0000-4000-8000-0000000000d1', codigo: '000215', nombre: 'Impresora multifuncional', precio_compra: '1390000.00' },
      { categoria: categorias[0], ubicacion: ubicaciones[1] },
    ),
    activoDe(
      { id: '00000000-0000-4000-8000-0000000000d2', codigo: '000123', nombre: 'Silla ergonómica', precio_compra: '389900.00', marca: 'Rimax' },
      { categoria: categorias[1], ubicacion: ubicaciones[3], ruta: 'Consultorio 1 › Box 2' },
    ),
  ]
  return crearCatalogo({ ubicaciones, categorias, activos, rol, sesiones: opciones.sesiones })
}

export function sesionDe(datos: Partial<SesionConteo> = {}): SesionConteo {
  return {
    id: '00000000-0000-4000-8000-0000000000e1',
    nombre: 'Conteo nov 2026',
    tipo: 'conteo',
    estado: 'abierta',
    fecha_corte: '2026-11-30',
    abierta_por: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' },
    abierta_en: '2026-11-14T13:00:00+00:00',
    cerrada_por: null,
    cerrada_en: null,
    ...datos,
  }
}
