import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { catalogoDemo, sesionDe } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json, simularSesion } from '@/test/sesion'

// Spec 016, T7 (R3, R5, R7, R8, R9; R7 de docs/03): Inicio, Valor e Informe del admin con el kit.
// 1) Caracterización: lo que el rediseño no puede cambiar (textos, enlaces, reintentos,
//    rótulos de fuente, roles). Pasa antes y después de migrar.
// 2) Diseño: las piezas son del kit (Panel, Cifra, Estado, Aviso, Pestanas, TablaDatos,
//    Progreso) y la tabla del informe se desplaza en el teléfono con la primera columna fija.

afterEach(cleanup)

const SESION = '00000000-0000-4000-8000-0000000000e1'
const INFORME = `/admin/sesiones/${SESION}/informe`
const cop = (t: string | null | undefined) => (t ?? '').replace(/\s/g, ' ')

function abrir(path: string, catalogo = catalogoDemo('admin'), { movil = false, rol = 'admin' as Rol } = {}) {
  simularAncho({ movil })
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

/** Impresora verificada (1.390.000) y silla en reparación sin verificar (389.900), sesión cerrada. */
function cerrado() {
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora, silla] = catalogo.activos
  silla.estado = 'en_reparacion'
  catalogo.verificaciones.push({
    id: '00000000-0000-4000-8000-0000000000f1',
    sesion_id: SESION,
    activo: { id: impresora.id, codigo: impresora.codigo, nombre: impresora.nombre },
    ubicacion_esperada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    ubicacion_encontrada: { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta },
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    foto_id: null,
    seq: 1,
    precio_al_contar: impresora.precio_compra,
  })
  catalogo.cerrarSesion(SESION)
  return catalogo
}

const pestana = (nombre: RegExp | string) => fireEvent.mouseDown(screen.getByRole('tab', { name: nombre }), { button: 0 })

describe('caracterización del tablero (T7): lo que no cambia', () => {
  it('Inicio: mientras carga, cada parte se anuncia por separado', async () => {
    abrir('/admin')
    expect(await screen.findByRole('status', { name: 'Cargando los indicadores' })).toBeTruthy()
    expect(screen.getByRole('status', { name: 'Cargando las gráficas de valor' })).toBeTruthy()
    expect(screen.getByRole('status', { name: 'Cargando la evolución' })).toBeTruthy()
    expect(screen.getByRole('status', { name: 'Cargando la actividad' })).toBeTruthy()
    await screen.findByRole('link', { name: /Activos hoy/ })
  })

  it('Inicio: acciones del encabezado y enlace al valor actual desde la gráfica', async () => {
    abrir('/admin')
    await screen.findByRole('link', { name: /Activos hoy/ })
    const encabezado = document.querySelector('[data-kit=encabezado-pagina]') as HTMLElement
    expect(within(encabezado).getByRole('link', { name: 'Registrar activo' }).getAttribute('href')).toBe('/admin/activos/nuevo')
    expect(within(encabezado).getByRole('link', { name: 'Sesiones' }).getAttribute('href')).toBe('/admin/sesiones')
    expect(screen.getByRole('heading', { level: 1, name: 'Resumen' })).toBeTruthy()
    const figura = await screen.findByRole('figure', { name: 'Valor por categoría' })
    expect(within(figura).getByRole('link', { name: 'Ver valor actual' }).getAttribute('href')).toBe('/admin/valor')
  })

  it('Inicio: el valor actual se rotula en vivo y nunca como informe', async () => {
    abrir('/admin')
    const valor = await screen.findByRole('region', { name: /Valor actual/ })
    expect(within(valor).getByText('Tiempo real')).toBeTruthy()
    expect(valor.textContent).toContain('No es el informe')
    expect(valor.textContent).not.toMatch(/Informe congelado/)
  })

  it('Inicio: si falla la evolución, solo esa parte lo dice y se puede reintentar', async () => {
    const catalogo = catalogoDemo('admin')
    let fallo = true
    const base = catalogo.manejador
    catalogo.manejador = (url, init) => (fallo && url === '/api/inicio/evolucion' ? errorApi(500, 'error_interno', 'Algo falló.') : base(url, init))
    abrir('/admin', catalogo)
    expect(await screen.findByText('No se pudo cargar la evolución')).toBeTruthy()
    expect(screen.getByText('Algo falló.')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Activos hoy/ })).toBeTruthy()
    fallo = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Aún no hay conteos cerrados')).toBeTruthy()
  })

  it('Inicio: la actividad sin eventos lo dice', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/inicio/actividad', () => json(200, { eventos: [], siguiente: null }))
    abrir('/admin', catalogo)
    const seccion = await screen.findByRole('region', { name: 'Actividad reciente' })
    expect(await within(seccion).findByText('Aún no hay actividad')).toBeTruthy()
  })

  it('Inicio: la sesión abierta enlaza a su detalle con su avance', async () => {
    abrir('/admin', catalogoDemo('admin', { sesiones: [sesionDe()] }))
    const avance = await screen.findByRole('link', { name: /Conteo nov 2026.*Abierta/ })
    expect(within(avance).getByRole('progressbar', { name: 'Avance de Conteo nov 2026' })).toBeTruthy()
  })

  it('Informe: los no encontrados vacíos lo dicen; las cifras no mezclan el valor en vivo', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    for (const a of catalogo.activos) {
      catalogo.verificaciones.push({
        id: `00000000-0000-4000-8000-0000000000f${catalogo.verificaciones.length + 1}`,
        sesion_id: SESION,
        activo: { id: a.id, codigo: a.codigo, nombre: a.nombre },
        ubicacion_esperada: { id: a.ubicacion.id, ruta: a.ubicacion.ruta },
        ubicacion_encontrada: { id: a.ubicacion.id, ruta: a.ubicacion.ruta },
        estado_fisico: 'ok',
        nota: null,
        verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
        ocurrido_en: null,
        recibido_en: '2026-11-14T15:44:00+00:00',
        foto_id: null,
        seq: catalogo.verificaciones.length + 1,
        precio_al_contar: a.precio_compra,
      })
    }
    catalogo.cerrarSesion(SESION)
    abrir(INFORME, catalogo)
    await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })
    expect(screen.queryByText('Tiempo real')).toBeNull()
    expect(screen.queryByText(/No es (el|un) informe/)).toBeNull()
    pestana(/No encontrados/)
    expect(await screen.findByText('Se encontraron todos los activos')).toBeTruthy()
  })

  it('Informe: el error de carga ofrece reintentar', async () => {
    const catalogo = cerrado()
    let fallo = true
    const base = catalogo.manejador
    catalogo.manejador = (url, init) => (fallo && url === `/api/sesiones/${SESION}/informe` ? errorApi(500, 'error_interno', 'Algo falló.') : base(url, init))
    abrir(INFORME, catalogo)
    expect(await screen.findByText('No se pudo cargar el informe')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: 'Informe' })).toBeTruthy()
    fallo = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })).toBeTruthy()
  })

  it('Informe: una sesión inexistente lleva a Sesiones', async () => {
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000ff/informe')
    expect(await screen.findByText('Esa sesión no existe')).toBeTruthy()
    expect(screen.getByText('Puede que el enlace esté incompleto.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ver sesiones' }).getAttribute('href')).toBe('/admin/sesiones')
  })

  it('Informe en el teléfono: el desglose sigue siendo una tabla con su fila de total', async () => {
    abrir(INFORME, cerrado(), { movil: true })
    const tabla = await screen.findByRole('table')
    const filas = within(tabla).getAllByRole('row').map((r) => cop(r.textContent))
    expect(filas.at(-1)).toBe('Total$ 1.390.000,001$ 389.900,001$ 1.779.900,00250 %')
  })

  it('Valor: el pie con «Ver sesiones» y el total del servidor en la tabla', async () => {
    abrir('/admin/valor')
    const tabla = await screen.findByRole('table')
    expect(cop(within(tabla).getAllByRole('row').at(-1)?.textContent)).toBe('Total$ 1.779.900,002')
    expect(screen.getByRole('link', { name: 'Ver sesiones' }).getAttribute('href')).toBe('/admin/sesiones')
  })

  it.each([['/admin'], ['/admin/valor'], [INFORME]])('el contador no entra a %s ni pide cifras', async (ruta) => {
    const { f } = abrir(ruta, catalogoDemo('contador'), { rol: 'contador' })
    expect(await screen.findByText('No tienes permiso para ver esto')).toBeTruthy()
    const pedidas = f.mock.calls.map(([url]) => String(url))
    expect(pedidas.some((u) => u.startsWith('/api/valor-actual') || u.startsWith('/api/inicio') || u.includes('/informe'))).toBe(false)
    expect(document.body.textContent).not.toMatch(/\$/)
  })
})

describe('diseño del tablero (T7): piezas del kit', () => {
  const kit = (nombre: string) => document.querySelectorAll(`[data-kit=${nombre}]`)

  it('Inicio: cifras, último informe y actividad son del kit; el avance tiene su valor accesible', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    abrir('/admin', catalogo)
    const avance = await screen.findByRole('progressbar', { name: 'Avance de Conteo nov 2026' })
    expect(avance.getAttribute('aria-valuenow')).toBe('0')
    expect(avance.closest('[data-kit=progreso]')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Activos hoy/ }).getAttribute('data-kit')).toBe('cifra')
    const actividad = await screen.findByRole('region', { name: 'Actividad reciente' })
    expect(actividad.getAttribute('data-kit')).toBe('panel')
    expect(screen.getByRole('figure', { name: 'Valor por categoría' }).className).toContain('bg-card')
    expect(within(screen.getByRole('figure', { name: 'Valor por categoría' })).getByRole('link', { name: 'Ver valor actual' }).getAttribute('data-kit')).toBe('boton')
  })

  it('Inicio: el error de una parte es un aviso del kit con «Reintentar» del kit', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/inicio', () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir('/admin', catalogo)
    const titulo = await screen.findByText('No se pudieron cargar los indicadores')
    expect(titulo.closest('[data-kit=aviso]')?.getAttribute('data-tono')).toBe('error')
    expect(screen.getByRole('button', { name: 'Reintentar' }).getAttribute('data-kit')).toBe('boton')
  })

  it('Inicio: la evolución elige con un campo del kit', async () => {
    const catalogo = cerrado()
    abrir('/admin', catalogo)
    const figura = await screen.findByRole('figure', { name: 'Evolución entre conteos' })
    expect(within(figura).getByRole('combobox', { name: 'Ver' }).closest('[data-kit=campo]')).toBeTruthy()
  })

  it('Actividad: el enlace de cada evento cubre toda la fila (objetivo táctil)', async () => {
    abrir('/admin')
    const seccion = await screen.findByRole('region', { name: 'Actividad reciente' })
    const [item] = await within(seccion).findAllByRole('listitem')
    const enlace = within(item).getByRole('link')
    expect(item.getAttribute('data-actividad')).toBe('evento')
    expect(enlace.className).toContain('after:absolute')
    expect(enlace.className).toContain('after:inset-0')
  })

  it('Valor: cifras en vivo, pestañas y tabla del kit', async () => {
    abrir('/admin/valor')
    const region = await screen.findByRole('region', { name: /Valor actual/ })
    expect(region.getAttribute('data-fuente')).toBe('en_vivo')
    expect(kit('pestanas')).toHaveLength(1)
    expect(screen.getByRole('table').closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Actualizar' }).getAttribute('data-kit')).toBe('boton')
  })

  it('Valor: el error es el estado de error del kit', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.fallar('GET /api/valor-actual', () => errorApi(500, 'error_interno', 'Algo falló.'))
    abrir('/admin/valor', catalogo)
    const titulo = await screen.findByText('No se pudo calcular el valor actual')
    expect(titulo.closest('[data-kit=aviso]')).toBeTruthy()
  })

  it('Informe: insignia «Informe congelado», pestañas, tabla y exportar del kit', async () => {
    abrir(INFORME, cerrado())
    await screen.findByRole('heading', { level: 1, name: 'Informe · Conteo nov 2026' })
    const insignia = screen.getAllByText('Informe congelado').find((n) => n.closest('[data-kit=encabezado-pagina]'))
    expect(insignia?.closest('[data-kit=insignia]')).toBeTruthy()
    expect(kit('pestanas')).toHaveLength(1)
    expect(screen.getByRole('table').closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Exportar PDF' }).getAttribute('data-variante')).toBe('principal')
    expect(screen.getByRole('button', { name: 'Exportar Excel' }).getAttribute('data-variante')).toBe('secundario')
  })

  it('Informe en el teléfono: la tabla se desplaza con la primera columna fija (no son tarjetas)', async () => {
    abrir(INFORME, cerrado(), { movil: true })
    const tabla = await screen.findByRole('table')
    const primera = within(tabla).getAllByRole('row')[1].querySelector('td') as HTMLElement
    expect(primera.className).toContain('sticky')
    pestana(/No encontrados/)
    await waitFor(() => expect(within(screen.getByRole('table')).getByText('Silla ergonómica')).toBeTruthy())
    const codigo = within(screen.getByRole('table')).getByRole('link', { name: '000123' })
    expect(codigo.closest('td')?.className).toContain('sticky')
  })

  it('Informe: la sesión abierta es el estado vacío del kit', async () => {
    abrir(INFORME, catalogoDemo('admin', { sesiones: [sesionDe()] }))
    const titulo = await screen.findByText('Esta sesión sigue abierta')
    expect(titulo.closest('[data-kit=estado-vacio]')).toBeTruthy()
  })
})
