import type { Categoria, Rol, Ubicacion } from '@/lib/api/cliente'
import type { Activo } from '@/lib/activos'
import type { FilaDesglose, Informe, ValorEnVivo } from '@/lib/informe'
import type { EventoActividad, Evolucion, Indicadores } from '@/lib/inicio'
import type { SesionConteo, Verificacion } from '@/lib/sesiones'
import { errorApi, json, type Manejador } from './sesion'

// API del catálogo simulada en memoria (spec 003): responde como el backend lo
// esencial (crear, listar, renombrar, activar) para probar las pantallas con
// `simularSesion(rol, catalogo.manejador)`. Los errores puntuales se fuerzan con
// `catalogo.fallar(ruta, respuesta)`.

/** Lo que el servidor deja editar al contador (spec 020, R7; `EDITABLES_CONTADOR`). */
const EDITABLES_CONTADOR = ['nombre', 'categoria_id', 'marca', 'modelo', 'subtipo', 'serial', 'fecha_compra']

export function crearCatalogo(
  inicial: {
    ubicaciones?: Ubicacion[]
    categorias?: Categoria[]
    activos?: Activo[]
    rol?: Rol
    sesiones?: SesionConteo[]
    /** Spec 020 (regresión): `false` simula un servidor que sí le enviara el precio al contador. */
    filtraPrecio?: boolean
  } = {},
) {
  const ubicaciones = [...(inicial.ubicaciones ?? [])]
  const categorias = [...(inicial.categorias ?? [])]
  const activos = [...(inicial.activos ?? [])]
  const sesiones = [...(inicial.sesiones ?? [])]
  const verificaciones: Verificacion[] = []
  const resoluciones = new Map<string, { tipo: 'aplicada' | 'descartada'; en: string }>()
  const rol = inicial.rol ?? 'admin'
  // Quién recibe precios del doble: el admin y, si `filtraPrecio` es false, cualquiera.
  const conPrecios = rol === 'admin' || inicial.filtraPrecio === false
  const sinPrecio = (a: Activo) => {
    if (conPrecios) return { ...a }
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
  const eventos: { seq: number; tipo: string; datos: Record<string, unknown>; activo: string; foto_id?: string }[] = []
  let siguiente = 1
  const nuevoId = () => `00000000-0000-4000-8000-${String(siguiente++).padStart(12, '0')}`
  const cuerpo = (init: RequestInit) => JSON.parse(String(init.body ?? '{}')) as Record<string, unknown>
  // Dinero en centavos enteros, como el Decimal del servidor (sin float).
  const centavos = (texto: string) => Math.round(Number(texto) * 100)
  const dinero = (c: number) => `${Math.trunc(c / 100)}.${String(c % 100).padStart(2, '0')}`
  const informes = new Map<string, Informe>()
  // Spec 012: foto principal por activo y fotos guardadas (id → bytes).
  const fotos = new Map<string, Uint8Array>()
  const principales = new Map<string, { id: string; creada_en: string; ancho: number; alto: number }>()
  const conFoto = (a: Activo) => ({ ...sinPrecio(a), foto: principales.get(a.id) ?? null })
  const fotoId = (init: RequestInit) => {
    const form = init.body instanceof FormData ? init.body : null
    return { id: String(form?.get('foto_id') ?? ''), archivo: form?.get('archivo') }
  }

  /** Universo U del cierre (R4 de docs/03): la misma regla que el servidor, en pequeño. */
  function calcularInforme(sesion: SesionConteo): Informe {
    const vigentes = new Map<string, Verificacion>()
    for (const v of verificaciones.filter((x) => x.sesion_id === sesion.id)) vigentes.set(v.activo.id, v)
    const filas = activos.flatMap((a) => {
      const v = vigentes.get(a.id)
      if (v) return [{ a, encontrado: true, precio: centavos(v.precio_al_contar ?? a.precio_compra ?? '0'), ubicacion: v.ubicacion_esperada }]
      if (a.estado === 'dado_de_baja') return []
      return [{ a, encontrado: false, precio: centavos(a.precio_compra ?? '0'), ubicacion: { id: a.ubicacion.id, ruta: a.ubicacion.ruta } }]
    })
    const agrupar = (clave: (f: (typeof filas)[number]) => { id: string; etiqueta: string }): FilaDesglose[] => {
      const grupos = new Map<string, { etiqueta: string; e: number; n: number; ue: number; un: number }>()
      for (const f of filas) {
        const { id, etiqueta } = clave(f)
        const g = grupos.get(id) ?? { etiqueta, e: 0, n: 0, ue: 0, un: 0 }
        if (f.encontrado) {
          g.e += f.precio
          g.ue += 1
        } else {
          g.n += f.precio
          g.un += 1
        }
        grupos.set(id, g)
      }
      return [...grupos.entries()]
        .sort(([, x], [, y]) => x.etiqueta.localeCompare(y.etiqueta))
        .map(([id, g]) => ({
          id,
          etiqueta: g.etiqueta,
          total_encontrado: dinero(g.e),
          total_no_encontrado: dinero(g.n),
          total_registrado: dinero(g.e + g.n),
          unidades_encontrado: g.ue,
          unidades_no_encontrado: g.un,
          unidades_registrado: g.ue + g.un,
        }))
    }
    const suma = (encontrado: boolean) => filas.filter((f) => f.encontrado === encontrado).reduce((n, f) => n + f.precio, 0)
    const ue = filas.filter((f) => f.encontrado).length
    return {
      sesion: { ...sesion },
      // Spec 013: datos de la empresa congelados al cierre (la API simulada no los edita).
      empresa: {
        nombre: 'Clínica de prueba',
        direccion: null,
        nit: null,
        telefono: null,
        correo: null,
        logo: null,
        vigente: false,
      },
      detalle_disponible: true,
      totales: {
        encontrado: dinero(suma(true)),
        no_encontrado: dinero(suma(false)),
        registrado: dinero(suma(true) + suma(false)),
        unidades_encontrado: ue,
        unidades_no_encontrado: filas.length - ue,
        unidades_registrado: filas.length,
      },
      desglose: {
        categorias: agrupar((f) => ({ id: f.a.categoria.id, etiqueta: f.a.categoria.nombre })),
        ubicaciones: agrupar((f) => ({ id: f.ubicacion.id, etiqueta: f.ubicacion.ruta })),
      },
      no_encontrados: filas
        .filter((f) => !f.encontrado)
        .map((f) => ({
          activo_id: f.a.id,
          codigo: f.a.codigo,
          nombre: f.a.nombre,
          categoria: { ...f.a.categoria },
          ubicacion: { ...f.ubicacion },
          precio: dinero(f.precio),
          en_reparacion: f.a.estado === 'en_reparacion',
        })),
    }
  }

  function cerrar(sesion: SesionConteo): Informe {
    if (sesion.estado === 'abierta') {
      sesion.estado = 'cerrada'
      sesion.cerrada_en = '2026-11-14T16:00:00+00:00'
      sesion.cerrada_por = { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' }
    }
    if (!informes.has(sesion.id)) informes.set(sesion.id, calcularInforme(sesion))
    return informes.get(sesion.id)!
  }

  function valorActual(): ValorEnVivo {
    const vigentes = activos.filter((a) => a.estado !== 'dado_de_baja')
    const agrupar = (clave: (a: Activo) => { id: string; etiqueta: string }) => {
      const grupos = new Map<string, { etiqueta: string; c: number; u: number }>()
      for (const a of vigentes) {
        const { id, etiqueta } = clave(a)
        const g = grupos.get(id) ?? { etiqueta, c: 0, u: 0 }
        g.c += centavos(a.precio_compra ?? '0')
        g.u += 1
        grupos.set(id, g)
      }
      return [...grupos.entries()]
        .sort(([, x], [, y]) => x.etiqueta.localeCompare(y.etiqueta))
        .map(([id, g]) => ({ id, etiqueta: g.etiqueta, valor: dinero(g.c), unidades: g.u }))
    }
    const reparacion = vigentes.filter((a) => a.estado === 'en_reparacion')
    return {
      total: dinero(vigentes.reduce((n, a) => n + centavos(a.precio_compra ?? '0'), 0)),
      unidades: vigentes.length,
      en_reparacion: { valor: dinero(reparacion.reduce((n, a) => n + centavos(a.precio_compra ?? '0'), 0)), unidades: reparacion.length },
      por_categoria: agrupar((a) => ({ id: a.categoria.id, etiqueta: a.categoria.nombre })),
      por_ubicacion: agrupar((a) => ({ id: a.ubicacion.id, etiqueta: a.ubicacion.ruta })),
      calculado_en: '2026-11-14T17:30:00+00:00',
    }
  }

  // Spec 010: Inicio, con las mismas reglas que el servidor en pequeño.
  const porcentajeTexto = (parte: number, total: number) => (total === 0 ? '0.0' : (Math.round((parte * 1000) / total) / 10).toFixed(1))
  const cerradas = () =>
    sesiones.filter((x) => x.estado === 'cerrada' && x.tipo === 'conteo').sort((x, y) => String(y.cerrada_en).localeCompare(String(x.cerrada_en)))
  function vigentesDe(sesionId: string) {
    const v = new Map<string, Verificacion>()
    for (const x of verificaciones.filter((y) => y.sesion_id === sesionId)) v.set(x.activo.id, x)
    return v
  }
  function indicadores(): Indicadores {
    const hoy = activos.filter((a) => a.estado !== 'dado_de_baja')
    const abierta = sesiones.find((x) => x.estado === 'abierta') ?? null
    let sesion_abierta: Indicadores['sesion_abierta'] = null
    if (abierta) {
      const v = vigentesDe(abierta.id)
      const verificados = hoy.filter((a) => v.has(a.id)).length
      sesion_abierta = {
        id: abierta.id,
        nombre: abierta.nombre,
        fecha_corte: abierta.fecha_corte,
        avance: { total: hoy.length, verificados, pendientes: hoy.length - verificados, porcentaje: porcentajeTexto(verificados, hoy.length) },
      }
    }
    const datos: Indicadores = {
      activos_hoy: { unidades: hoy.length, en_reparacion: hoy.filter((a) => a.estado === 'en_reparacion').length },
      sesion_abierta,
    }
    // Spec 020, T6: con `filtraPrecio: false` el doble también le manda el valor al contador.
    if (!conPrecios) return datos
    const ultima = cerradas()[0] ?? null
    const ref = abierta ?? ultima
    const valor = valorActual()
    datos.valor_actual = { total: valor.total, unidades: valor.unidades, calculado_en: valor.calculado_en }
    const v = ref ? vigentesDe(ref.id) : new Map<string, Verificacion>()
    datos.discrepancias = ref
      ? {
          por_resolver: [...v.values()].filter((x) => x.ubicacion_encontrada.id !== x.ubicacion_esperada.id && !resoluciones.has(x.id)).length,
          sesion: { id: ref.id, nombre: ref.nombre },
        }
      : null
    const reparacion = new Set(hoy.filter((a) => a.estado === 'en_reparacion').map((a) => a.id))
    const danados = new Set([...v.values()].filter((x) => x.estado_fisico === 'danado' && hoy.some((a) => a.id === x.activo.id)).map((x) => x.activo.id))
    datos.danados = {
      total: new Set([...reparacion, ...danados]).size,
      en_reparacion: reparacion.size,
      danados: danados.size,
      sesion: ref ? { id: ref.id, nombre: ref.nombre } : null,
    }
    datos.ultimo_informe = ultima ? (({ sesion, totales }) => ({ sesion, totales }))(cerrar(ultima)) : null
    return datos
  }
  function evolucion(): Evolucion {
    const lista = cerradas().slice(0, 12).reverse()
    const porCategoria = new Map<string, Evolucion['por_categoria'][number]>()
    const puntos = lista.map((x) => {
      const inf = cerrar(x)
      for (const f of inf.desglose.categorias) {
        const c = porCategoria.get(f.id) ?? { categoria_id: f.id, etiqueta: f.etiqueta, puntos: [] }
        c.etiqueta = f.etiqueta
        c.puntos.push({ sesion_id: x.id, total_registrado: f.total_registrado, unidades_registrado: f.unidades_registrado })
        porCategoria.set(f.id, c)
      }
      const t = inf.totales
      return {
        sesion: { id: x.id, nombre: x.nombre, fecha_corte: x.fecha_corte, cerrada_en: x.cerrada_en },
        total_registrado: t.registrado,
        unidades_registrado: t.unidades_registrado,
        unidades_encontrado: t.unidades_encontrado,
        porcentaje_encontrado: porcentajeTexto(t.unidades_encontrado, t.unidades_registrado),
      }
    })
    return { sesiones: puntos, por_categoria: [...porCategoria.values()].sort((x, y) => x.etiqueta.localeCompare(y.etiqueta)) }
  }
  function actividad(): EventoActividad[] {
    const todos = [
      ...eventos,
      ...activos.map((a, i) => ({ seq: i + 1, tipo: 'creado', datos: { codigo: a.codigo, nombre: a.nombre, precio_compra: a.precio_compra } as Record<string, unknown>, activo: a.id })),
    ]
    return todos
      .filter((e) => conPrecios || e.tipo !== 'precio_cambiado')
      .sort((x, y) => y.seq - x.seq)
      .slice(0, 20)
      .map((e) => {
        const a = activos.find((x) => x.id === e.activo)!
        return {
          seq: e.seq,
          tipo: e.tipo as EventoActividad['tipo'],
          ocurrido_en: '2026-11-14T15:30:00+00:00',
          autor: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' },
          datos: (conPrecios ? e.datos : Object.fromEntries(Object.entries(e.datos).filter(([k]) => !k.includes('precio')))) as EventoActividad['datos'],
          activo: { id: a.id, codigo: a.codigo, nombre: a.nombre },
        }
      })
  }

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
      return a ? json(200, { activo: conFoto(a) }) : errorApi(404, 'no_encontrado', 'El recurso no existe.')
    }
    if (ruta0 === '/api/activos/sugerencias' && metodo === 'GET') {
      const campo = q.get('campo') as 'nombre' | 'marca' | 'modelo' | 'subtipo'
      const texto = (q.get('q') ?? '').toLowerCase()
      const valores = [...new Set(activos.map((a) => a[campo]).filter((v): v is string => Boolean(v)))]
      return json(200, { valores: valores.filter((v) => v.toLowerCase().includes(texto)).slice(0, 8) })
    }
    // Spec 015, T4: el servidor arma el Excel con los filtros; aquí basta un binario con nombre.
    if (ruta0 === '/api/activos/exportar' && metodo === 'GET') {
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
      const nombre = 'activos-20261118.xlsx'
      return new Response('PK', {
        status: 200,
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': `attachment; filename="${nombre}"; filename*=UTF-8''${nombre}`,
        },
      })
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
      return a ? json(200, { activo: conFoto(a) }) : errorApi(404, 'no_encontrado', 'El recurso no existe.')
    }
    // Spec 012: fotos (ambos roles).
    const fot = ruta0.match(/^\/api\/activos\/([0-9a-f-]{36})\/foto$/)
    if (fot && (metodo === 'PUT' || metodo === 'DELETE')) {
      const a = activos.find((x) => x.id === fot[1])
      if (!a) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const anterior = principales.get(a.id)
      if (metodo === 'DELETE') {
        if (!anterior) return errorApi(404, 'sin_foto', 'No hay foto.')
        principales.delete(a.id)
        fotos.delete(anterior.id)
        eventos.unshift({ seq: eventos.length + 100, tipo: 'foto_retirada', datos: { foto_id: anterior.id }, activo: a.id })
        return new Response(null, { status: 204 })
      }
      const { id } = fotoId(init)
      if (anterior?.id === id) return json(200, { foto: anterior })
      const foto = { id, creada_en: '2026-11-15T12:00:00+00:00', ancho: 1600, alto: 1200 }
      principales.set(a.id, foto)
      fotos.set(id, new Uint8Array([0xff, 0xd8, 0xff]))
      if (anterior) fotos.delete(anterior.id)
      eventos.unshift({
        seq: eventos.length + 100,
        tipo: anterior ? 'foto_cambiada' : 'foto_agregada',
        datos: anterior ? { antes: anterior.id, despues: id } : { foto_id: id },
        activo: a.id,
      })
      return json(201, { foto })
    }
    const fotv = ruta0.match(/^\/api\/sesiones\/([0-9a-f-]{36})\/verificaciones\/([0-9a-f-]{36})\/foto$/)
    if (fotv && metodo === 'PUT') {
      const v = verificaciones.find((x) => x.id === fotv[2])
      if (!v) return errorApi(404, 'no_encontrado', 'La verificación no existe.')
      const { id } = fotoId(init)
      if (v.foto_id === id) return json(200, { foto: { id, creada_en: '2026-11-15T12:00:00+00:00', ancho: 1600, alto: 1200 } })
      if (v.foto_id) return errorApi(409, 'foto_existente', 'Esta verificación ya tiene foto.')
      v.foto_id = id
      fotos.set(id, new Uint8Array([0xff, 0xd8, 0xff]))
      return json(201, { foto: { id, creada_en: '2026-11-15T12:00:00+00:00', ancho: 1600, alto: 1200 } })
    }
    const ver = ruta0.match(/^\/api\/fotos\/([0-9a-f-]{36})$/)
    if (ver && metodo === 'GET') {
      const bytes = fotos.get(ver[1])
      if (!bytes) return errorApi(404, 'sin_foto', 'No hay foto.')
      return new Response(bytes.slice(), { status: 200, headers: { 'Content-Type': 'image/jpeg' } })
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
    if (ruta0 === '/api/inicio' && metodo === 'GET') return json(200, indicadores())
    if (ruta0 === '/api/inicio/actividad' && metodo === 'GET') return json(200, { eventos: actividad(), siguiente: null })
    if (ruta0 === '/api/inicio/evolucion' && metodo === 'GET') {
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
      return json(200, evolucion())
    }
    // Spec 008: cierre, informe congelado y valor actual (solo admin).
    if (ruta0 === '/api/valor-actual' && metodo === 'GET') {
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
      return json(200, valorActual())
    }
    const cie = ruta0.match(/^\/api\/sesiones\/([0-9a-f-]{36})\/(cerrar|informe|informe\/excel|informe\/pdf)$/)
    if (cie) {
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
      const sesion = sesiones.find((x) => x.id === cie[1])
      if (!sesion) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      if (cie[2] === 'cerrar' && metodo === 'POST') return json(200, cerrar(sesion))
      if (cie[2].startsWith('informe') && metodo === 'GET') {
        if (sesion.estado === 'abierta') return errorApi(409, 'sesion_abierta', 'La sesión sigue abierta: el informe se genera al cerrarla.')
        if (cie[2] === 'informe') return json(200, cerrar(sesion))
        // Spec 009: el archivo lo arma el servidor; aquí basta un binario con su nombre.
        const pdf = cie[2].endsWith('pdf')
        const nombre = `informe-conteo-nov-2026-corte-${sesion.fecha_corte}.${pdf ? 'pdf' : 'xlsx'}`
        return new Response(pdf ? '%PDF-1.4' : 'PK', {
          status: 200,
          headers: {
            'Content-Type': pdf ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': `attachment; filename="${nombre}"; filename*=UTF-8''${nombre}`,
          },
        })
      }
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
      // Spec 020, T2 (R8): la lista es de los dos roles; aplicar y descartar, solo del admin.
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
              // Regresión (spec 020, T6): un servidor que se equivocara y mandara el precio.
              ...(inicial.filtraPrecio === false ? { precio_al_contar: v.precio_al_contar } : {}),
            }
          })
          .filter((d) => filtro === 'todas' || (filtro === 'resueltas') === (d.estado === 'aplicada' || d.estado === 'descartada'))
        return json(200, { discrepancias: items })
      }
      if (rol !== 'admin') return errorApi(403, 'prohibido', 'No tienes permiso.')
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
        // Regresión (spec 020, T6): con `filtraPrecio: false`, un valor que el servidor no manda.
        const valor = inicial.filtraPrecio === false ? { valor_verificado: '1390000.00' } : {}
        return json(200, { sesion, avance: { total, verificados, pendientes: total - verificados, por_ubicacion, ...valor } })
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
          foto_id: null,
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
      // Spec 020 (T1, R7): el contador solo edita los campos descriptivos; mover, estado y
      // baja siguen siendo del admin. Un campo fuera de su lista es 400 sin tocar nada.
      if (rol !== 'admin' && cambio[2]) return errorApi(403, 'prohibido', 'No tienes permiso.')
      if (rol !== 'admin' && Object.keys(cuerpo(init)).some((k) => !EDITABLES_CONTADOR.includes(k))) {
        return errorApi(400, 'solicitud_invalida', 'La solicitud no es válida.')
      }
      const a = activos.find((x) => x.id === cambio[1])
      if (!a) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const version = new Headers(init.headers).get('If-Match')?.replace(/"/g, '')
      if (!version) return errorApi(428, 'falta_version', 'Falta la versión del activo.')
      if (Number(version) !== a.row_version) {
        return json(412, {
          error: { code: 'version_desactualizada', message: 'Alguien cambió este activo.', request_id: 'r' },
          activo: conFoto(a),
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
      // Spec 015 (R4): la escritura (y el 412) traen la ficha con su foto, como el servidor.
      return json(200, { activo: conFoto(a) }, { ETag: `"${a.row_version}"` })
    }
    const his = ruta0.match(/^\/api\/activos\/([0-9a-f-]{36})\/historial$/)
    if (his && metodo === 'GET') {
      const a = activos.find((x) => x.id === his[1])
      if (!a) return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      const propios = [
        ...eventos.filter((e) => e.activo === a.id),
        { seq: 1, tipo: 'creado', datos: { codigo: a.codigo, nombre: a.nombre, precio_compra: a.precio_compra }, activo: a.id },
      ]
        .filter((e) => conPrecios || e.tipo !== 'precio_cambiado')
        .map(({ seq, tipo, datos, ...resto }) => ({
          seq,
          tipo,
          ocurrido_en: '2026-11-14T15:30:00+00:00',
          autor: { id: '00000000-0000-4000-8000-00000000000a', nombre: 'Ana Torres' },
          datos: conPrecios ? datos : Object.fromEntries(Object.entries(datos).filter(([k]) => !k.includes('precio'))),
          ...('foto_id' in resto && resto.foto_id ? { foto_id: resto.foto_id } : {}),
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
    fotos,
    principales,
    sesiones,
    verificaciones,
    /** Resoluciones de discrepancias (verificación → aplicada o descartada). */
    resoluciones,
    eventos,
    /** Cierra como lo haría otra persona (el informe queda congelado igual que en el servidor). */
    cerrarSesion(id: string) {
      cerrar(sesiones.find((y) => y.id === id)!)
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
export function catalogoDemo(rol: Rol = 'admin', opciones: { sesiones?: SesionConteo[]; filtraPrecio?: boolean } = {}) {
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
  return crearCatalogo({ ubicaciones, categorias, activos, rol, sesiones: opciones.sesiones, filtraPrecio: opciones.filtraPrecio })
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
