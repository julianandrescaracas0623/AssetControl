import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Empresa, Rol } from '@/lib/api/cliente'
import type { Verificacion } from '@/lib/sesiones'
import { routes } from '@/router'
import { catalogoDemo, crearCatalogo, sesionDe, ub } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json, type Manejador, simularSesion } from '@/test/sesion'

import Pendiente from './Pendiente'

// Spec 016, T9 (R2, R3, R5, R8, R11; D13; A9): pantallas de gestión del admin con el kit
// (Sesiones y su detalle, Discrepancias, Ubicaciones, Categorías, Usuarios, Empresa y
// Pendiente).
// 1) Caracterización: lo que el rediseño no puede cambiar (textos, estados, reglas de
//    cierre y discrepancias, roles, el enlace de invitación). Pasa antes y después.
// 2) Diseño: las piezas son del kit (EncabezadoPagina, TablaDatos, Panel, Dialogo,
//    Confirmar, Estado, Campo, Casilla, Interruptor, Menu, Progreso, MarcoImagen) y el
//    logo de la empresa tiene la caja de D13.

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const SESION = '00000000-0000-4000-8000-0000000000e1'
const clases = (el: Element | null | undefined) => (el?.getAttribute('class') ?? '').split(/\s+/)

function abrir(path: string, manejador: Manejador, { movil = false, rol = 'admin' as Rol } = {}) {
  simularAncho({ movil })
  const f = simularSesion(rol, manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

/** La impresora se vio en el box (una discrepancia) y la silla sigue pendiente: 1 de 2. */
function conVerificacion() {
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora] = catalogo.activos
  catalogo.verificaciones.push(verificacion('00000000-0000-4000-8000-0000000000f1', impresora, { id: impresora.ubicacion.id, ruta: impresora.ubicacion.ruta }, BOX2))
  return catalogo
}

const ADMINISTRACION = { id: '00000000-0000-4000-8000-0000000000a2', ruta: 'Administración' }
const BOX2 = { id: '00000000-0000-4000-8000-0000000000a4', ruta: 'Consultorio 1 › Box 2' }

function verificacion(id: string, activo: { id: string; codigo: string; nombre: string }, esperada: typeof BOX2, encontrada: typeof BOX2): Verificacion {
  return {
    id,
    sesion_id: SESION,
    activo: { id: activo.id, codigo: activo.codigo, nombre: activo.nombre },
    ubicacion_esperada: esperada,
    ubicacion_encontrada: encontrada,
    estado_fisico: 'ok',
    nota: null,
    verificado_por: { id: '00000000-0000-4000-8000-00000000000b', nombre: 'Luis Pérez' },
    ocurrido_en: null,
    recibido_en: '2026-11-14T15:44:00+00:00',
    foto_id: null,
    seq: 1,
    precio_al_contar: '1.00',
  }
}

/** Falla una sola vez la primera petición que cumpla `prueba`. */
function fallarUnaVez(manejador: Manejador, prueba: (url: string, metodo: string) => boolean, respuesta = () => errorApi(503, 'no_disponible', 'El servidor no responde.')): Manejador {
  let pendiente = true
  return (url, init) => {
    if (pendiente && prueba(url, init.method ?? 'GET')) {
      pendiente = false
      return respuesta()
    }
    return manejador(url, init)
  }
}

// ---------------------------------------------------------------------------
// Sesiones y detalle
// ---------------------------------------------------------------------------

describe('caracterización de Sesiones (T9): lo que no cambia', () => {
  it('mientras carga se anuncia «Cargando sesiones»', async () => {
    abrir('/admin/sesiones', catalogoDemo('admin').manejador)
    expect(await screen.findByRole('status', { name: 'Cargando sesiones' })).toBeTruthy()
  })

  it('un error lo dice y «Reintentar» vuelve a pedir', async () => {
    const catalogo = catalogoDemo('admin')
    abrir('/admin/sesiones', fallarUnaVez(catalogo.manejador, (u, m) => u === '/api/sesiones' && m === 'GET'))
    expect(await screen.findByText('No se pudieron cargar las sesiones')).toBeTruthy()
    expect(screen.getByText('El servidor no responde.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Aún no hay conteos')).toBeTruthy()
  })

  it('abrir sin nombre lo marca en el campo y no llama a la API', async () => {
    const { f } = abrir('/admin/sesiones', catalogoDemo('admin').manejador)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Abrir sesión' }))[0])
    const dialogo = await screen.findByRole('dialog', { name: 'Abrir sesión de conteo' })
    fireEvent.change(within(dialogo).getByLabelText(/Nombre/), { target: { value: '   ' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Abrir sesión' }))
    expect(await within(dialogo).findByText('Escribe el nombre')).toBeTruthy()
    expect(within(dialogo).getByLabelText(/Nombre/).getAttribute('aria-invalid')).toBe('true')
    expect(within(dialogo).getByLabelText(/Nombre/).getAttribute('aria-describedby')).toBe('sesion-nombre-error')
    expect(f.mock.calls.some(([u, i]) => u === '/api/sesiones' && i?.method === 'POST')).toBe(false)
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('el cierre dice su efecto: informe congelado, sin reabrir ni seguir contando', async () => {
    abrir(`/admin/sesiones/${SESION}`, conVerificacion().manejador)
    fireEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = await screen.findByRole('dialog', { name: '¿Cerrar «Conteo nov 2026»?' })
    expect(
      within(dialogo).getByText('Al cerrar se calcula el informe una sola vez y queda congelado. No se puede reabrir ni seguir contando en esta sesión.'),
    ).toBeTruthy()
    expect(within(dialogo).getByRole('list', { name: 'Lo que queda al cerrar' })).toBeTruthy()
    expect(within(dialogo).getByRole('button', { name: 'Seguir contando' })).toBeTruthy()
  })

  it('el detalle de la abierta muestra el avance con su barra nombrada y «no es el informe»', async () => {
    abrir(`/admin/sesiones/${SESION}`, conVerificacion().manejador)
    expect(await screen.findByRole('progressbar', { name: 'Avance del conteo' })).toBeTruthy()
    expect(screen.getByRole('progressbar', { name: 'Avance en Administración' })).toBeTruthy()
    expect(screen.getByText('Información de trabajo: no es el informe. El informe se calcula una sola vez, al cerrar.')).toBeTruthy()
  })

  it('el detalle que no carga ofrece «Reintentar»', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
    abrir(`/admin/sesiones/${SESION}`, fallarUnaVez(catalogo.manejador, (u, m) => u === `/api/sesiones/${SESION}` && m === 'GET'))
    expect(await screen.findByText('No se pudo cargar la sesión')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Conteo nov 2026' })).toBeTruthy()
  })

  it('una sesión que no existe enlaza a «Ver sesiones»', async () => {
    abrir('/admin/sesiones/00000000-0000-4000-8000-0000000000ff', catalogoDemo('admin').manejador)
    expect(await screen.findByText('Puede que el enlace esté incompleto.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ver sesiones' }).getAttribute('href')).toBe('/admin/sesiones')
  })

  it('el contador no entra', async () => {
    abrir('/admin/sesiones', catalogoDemo('contador').manejador, { rol: 'contador' })
    expect(await screen.findByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeTruthy()
  })
})

describe('diseño de Sesiones (T9): kit', () => {
  it('encabezado del kit con «Abrir sesión» como acción principal y estado vacío del kit', async () => {
    abrir('/admin/sesiones', catalogoDemo('admin').manejador)
    const vacio = (await screen.findByText('Aún no hay conteos')).closest('[data-kit=estado-vacio]')
    expect(vacio).toBeTruthy()
    const h1 = screen.getByRole('heading', { level: 1, name: 'Sesiones' })
    expect(h1.closest('[data-kit=encabezado-pagina]')).toBeTruthy()
  })

  it('el error es un aviso del kit', async () => {
    const catalogo = catalogoDemo('admin')
    abrir('/admin/sesiones', fallarUnaVez(catalogo.manejador, (u, m) => u === '/api/sesiones' && m === 'GET'))
    expect((await screen.findByText('No se pudieron cargar las sesiones')).closest('[data-kit=aviso]')).toBeTruthy()
  })

  it('la abierta: panel del kit, insignia «Abierta», barra con aria-valuenow (Progreso) y «Contar» principal', async () => {
    const catalogo = conVerificacion()
    catalogo.sesiones.push(sesionDe({ id: '00000000-0000-4000-8000-0000000000e2', nombre: 'Conteo may 2026', estado: 'cerrada', cerrada_en: '2026-05-20T15:00:00+00:00' }))
    abrir('/admin/sesiones', catalogo.manejador)
    const enCurso = await screen.findByRole('region', { name: 'En curso' })
    expect(within(enCurso).getByText('Abierta').closest('[data-kit=insignia]')).toBeTruthy()
    expect(enCurso.querySelector('[data-kit=panel]')).toBeTruthy()
    const barra = await within(enCurso).findByRole('progressbar', { name: 'Avance del conteo' })
    expect(barra.getAttribute('aria-valuenow')).toBe('50')
    expect(within(enCurso).getByRole('link', { name: 'Contar' }).getAttribute('data-variante')).toBe('principal')
    expect(within(enCurso).getByRole('link', { name: 'Ver avance' }).getAttribute('data-variante')).toBe('secundario')
    const cerradas = screen.getByRole('region', { name: 'Cerradas' })
    expect(within(cerradas).getByRole('table').closest('[data-kit=tabla-datos]')).toBeTruthy()
  })

  it('en el teléfono las cerradas son tarjetas con su enlace al informe', async () => {
    const catalogo = catalogoDemo('admin', { sesiones: [sesionDe({ estado: 'cerrada', cerrada_en: '2026-11-14T16:00:00+00:00' })] })
    abrir('/admin/sesiones', catalogo.manejador, { movil: true })
    const cerradas = await screen.findByRole('region', { name: 'Cerradas' })
    expect(within(cerradas).queryByRole('table')).toBeNull()
    expect(within(cerradas).getByRole('link', { name: 'Ver informe de Conteo nov 2026' }).getAttribute('href')).toBe(`/admin/sesiones/${SESION}/informe`)
  })

  it('abrir sesión es un Dialogo del kit con Campo del kit (sin el selector de compatibilidad)', async () => {
    abrir('/admin/sesiones', catalogoDemo('admin').manejador)
    fireEvent.click((await screen.findAllByRole('button', { name: 'Abrir sesión' }))[0])
    const dialogo = await screen.findByRole('dialog', { name: 'Abrir sesión de conteo' })
    expect(dialogo.getAttribute('data-kit')).toBe('dialogo')
    const campos = dialogo.querySelectorAll('[data-kit=campo]')
    expect(campos).toHaveLength(2)
    expect(dialogo.querySelector('[data-controles-sobre-blanco]')).toBeNull()
    expect(within(dialogo).getByRole('button', { name: 'Abrir sesión' }).getAttribute('data-variante')).toBe('principal')
  })

  it('el detalle: barras del kit con aria-valuenow, tablas del kit y cierre con botón de peligro', async () => {
    abrir(`/admin/sesiones/${SESION}`, conVerificacion().manejador)
    const barra = await screen.findByRole('progressbar', { name: 'Avance del conteo' })
    expect(barra.closest('[data-kit=progreso]')).toBeTruthy()
    expect(barra.getAttribute('aria-valuenow')).toBe('50')
    expect(screen.getByRole('progressbar', { name: 'Avance en Administración' }).getAttribute('aria-valuenow')).toBe('100')
    expect(screen.getByRole('region', { name: 'Avance' }).getAttribute('data-kit')).toBe('panel')
    const pendientes = (await screen.findByRole('heading', { level: 2, name: 'Pendientes por verificar' })).parentElement!
    expect(pendientes.querySelector('[data-kit=tabla-datos]')).toBeTruthy()
    const insignia = screen.getAllByText('Abierta').find((el) => el.closest('[data-kit=encabezado-pagina]'))
    expect(insignia?.closest('[data-kit=insignia]')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = await screen.findByRole('dialog', { name: '¿Cerrar «Conteo nov 2026»?' })
    expect(dialogo.getAttribute('data-kit')).toBe('dialogo')
    expect(within(dialogo).getByRole('button', { name: 'Cerrar y ver informe' }).getAttribute('data-variante')).toBe('peligro')
    expect(within(dialogo).getByRole('button', { name: 'Seguir contando' }).getAttribute('data-variante')).toBe('secundario')
  })

  it('la cerrada: panel del kit con «Ver informe»', async () => {
    const catalogo = conVerificacion()
    catalogo.cerrarSesion(SESION)
    abrir(`/admin/sesiones/${SESION}`, catalogo.manejador)
    const cerrada = await screen.findByRole('region', { name: 'Sesión cerrada' })
    expect(cerrada.getAttribute('data-kit')).toBe('panel')
    expect(within(cerrada).getByRole('link', { name: 'Ver informe' }).getAttribute('data-kit')).toBe('boton')
  })
})

// ---------------------------------------------------------------------------
// Discrepancias
// ---------------------------------------------------------------------------

const V1 = '00000000-0000-4000-8000-0000000000f1'
const V2 = '00000000-0000-4000-8000-0000000000f2'

function conDiscrepancias() {
  const catalogo = catalogoDemo('admin', { sesiones: [sesionDe()] })
  const [impresora, silla] = catalogo.activos
  catalogo.verificaciones.push(verificacion(V1, impresora, ADMINISTRACION, BOX2), verificacion(V2, silla, BOX2, ADMINISTRACION))
  return catalogo
}

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)
const postsDiscrepancias = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => String(url).includes('/discrepancias/') && init?.method === 'POST')

describe('caracterización de Discrepancias (T9): lo que no cambia', () => {
  it('si no cargan lo dice y «Reintentar» vuelve a pedir', async () => {
    const catalogo = conDiscrepancias()
    abrir('/admin/discrepancias', fallarUnaVez(catalogo.manejador, (u) => u.startsWith(`/api/sesiones/${SESION}/discrepancias?`)))
    expect(await screen.findByText('No se pudieron cargar las discrepancias')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(filas()).toHaveLength(2))
  })

  it('la sesión se elige con un campo «Sesión»', async () => {
    abrir('/admin/discrepancias', conDiscrepancias().manejador)
    expect(await screen.findByRole('combobox', { name: 'Sesión' })).toBeTruthy()
  })

  it('el desfase explica que ya se movió y «Dejar como está» no aplica', async () => {
    const catalogo = conDiscrepancias()
    const { f } = abrir('/admin/discrepancias', catalogo.manejador)
    await waitFor(() => expect(filas()).toHaveLength(2))
    catalogo.activos[1].ubicacion = { id: '00000000-0000-4000-8000-0000000000a3', nombre: 'Consultorio 1', ruta: 'Consultorio 1' }
    fireEvent.click(within(filas().find((r) => r.textContent?.includes('Silla'))!).getByRole('button', { name: 'Aplicar' }))
    const dialogo = await screen.findByRole('alertdialog', { name: 'Ese activo ya se movió' })
    expect(dialogo.textContent).toContain('Desde que se contó, cambió de ubicación por otra vía. Si aplicas, pasa a donde se vio en el conteo.')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Dejar como está' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(postsDiscrepancias(f)).toHaveLength(1)
    expect(catalogo.activos[1].ubicacion.id).toBe('00000000-0000-4000-8000-0000000000a3')
  })

  it('sin resueltas lo dice', async () => {
    abrir('/admin/discrepancias', conDiscrepancias().manejador)
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Resueltas' }), { button: 0 })
    expect(await screen.findByText('Aún no se ha resuelto ninguna')).toBeTruthy()
  })

  it('el contador no entra', async () => {
    abrir('/admin/discrepancias', catalogoDemo('contador').manejador, { rol: 'contador' })
    expect(await screen.findByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeTruthy()
  })
})

describe('diseño de Discrepancias (T9): kit', () => {
  it('pestañas, tabla, casillas, insignias y acciones del kit', async () => {
    abrir('/admin/discrepancias', conDiscrepancias().manejador)
    await waitFor(() => expect(filas()).toHaveLength(2))
    expect(screen.getByRole('tablist').getAttribute('data-kit')).toBe('pestanas')
    expect(screen.getByRole('table').closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: 'Seleccionar todas' }).closest('[data-kit=casilla]')).toBeTruthy()
    const impresora = filas().find((r) => r.textContent?.includes('Impresora'))!
    expect(within(impresora).getByRole('checkbox', { name: 'Seleccionar Impresora multifuncional' }).closest('[data-kit=casilla]')).toBeTruthy()
    expect(within(impresora).getByText('Por resolver').closest('[data-kit=insignia]')).toBeTruthy()
    expect(within(impresora).getByRole('button', { name: 'Aplicar' }).getAttribute('data-kit')).toBe('boton')
    expect(screen.getByRole('combobox', { name: 'Sesión' }).closest('[data-kit=campo]')).toBeTruthy()
  })

  it('el lote: una sola acción principal «Aplicar» para las seleccionadas', async () => {
    abrir('/admin/discrepancias', conDiscrepancias().manejador)
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar todas' }))
    const grupo = screen.getByRole('group', { name: 'Acciones sobre las seleccionadas' })
    expect(within(grupo).getByRole('button', { name: 'Aplicar' }).getAttribute('data-variante')).toBe('principal')
    expect(within(grupo).getByRole('button', { name: 'Descartar' }).getAttribute('data-variante')).toBe('secundario')
  })

  it('el desfase es un Confirmar del kit', async () => {
    const catalogo = conDiscrepancias()
    abrir('/admin/discrepancias', catalogo.manejador)
    await waitFor(() => expect(filas()).toHaveLength(2))
    catalogo.activos[1].ubicacion = { id: '00000000-0000-4000-8000-0000000000a3', nombre: 'Consultorio 1', ruta: 'Consultorio 1' }
    fireEvent.click(within(filas().find((r) => r.textContent?.includes('Silla'))!).getByRole('button', { name: 'Aplicar' }))
    expect((await screen.findByRole('alertdialog')).getAttribute('data-kit')).toBe('confirmar')
  })

  it('en el teléfono: tarjetas con casilla por discrepancia y «Seleccionar todas» también', async () => {
    const { f } = abrir('/admin/discrepancias', conDiscrepancias().manejador, { movil: true })
    const casilla = await screen.findByRole('checkbox', { name: 'Seleccionar Silla ergonómica' })
    expect(screen.queryByRole('table')).toBeNull()
    expect(casilla.closest('[data-kit=casilla]')?.className).toContain('size-control')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Seleccionar todas' }))
    const grupo = screen.getByRole('group', { name: 'Acciones sobre las seleccionadas' })
    expect(grupo.textContent).toContain('2 seleccionadas')
    fireEvent.click(within(grupo).getByRole('button', { name: 'Descartar' }))
    expect(await screen.findByText('No hay diferencias por resolver')).toBeTruthy()
    expect(postsDiscrepancias(f)).toHaveLength(1)
  })
})

// ---------------------------------------------------------------------------
// Ubicaciones
// ---------------------------------------------------------------------------

const UBICACIONES = () => [ub('n', 'Sede Norte', 'sede', null), ub('c', 'Consultorios', 'sala', 'n'), ub('v', 'Vieja', 'sala', 'n', false)]

describe('caracterización de Ubicaciones (T9): lo que no cambia', () => {
  it('mientras carga se anuncia «Cargando ubicaciones»', async () => {
    abrir('/admin/ubicaciones', crearCatalogo({ ubicaciones: UBICACIONES() }).manejador)
    expect(await screen.findByRole('status', { name: 'Cargando ubicaciones' })).toBeTruthy()
  })

  it('«Cancelar» cierra el diálogo sin crear nada', async () => {
    const { f } = abrir('/admin/ubicaciones', crearCatalogo({ ubicaciones: UBICACIONES() }).manejador)
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva sede' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Nueva sede' })
    expect(within(dialogo).getByText('Así la verán quienes cuentan al elegir dónde están.')).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(f.mock.calls.some(([u, i]) => u === '/api/ubicaciones' && i?.method === 'POST')).toBe(false)
  })

  it('desactivar avisa que no se borra (baja lógica)', async () => {
    abrir('/admin/ubicaciones', crearCatalogo({ ubicaciones: UBICACIONES() }).manejador)
    await screen.findByRole('listitem', { name: 'Consultorios' })
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Consultorios' }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Desactivar' }))
    const confirmar = await screen.findByRole('alertdialog', { name: '¿Desactivar «Consultorios»?' })
    expect(within(confirmar).getByText(/No se borra: puedes reactivarla cuando quieras\./)).toBeTruthy()
  })
})

describe('diseño de Ubicaciones (T9): kit', () => {
  it('menú del kit en cada fila, interruptor del kit e insignia «Inactiva»', async () => {
    abrir('/admin/ubicaciones', crearCatalogo({ ubicaciones: UBICACIONES() }).manejador)
    const disparador = await screen.findByRole('button', { name: 'Acciones de Sede Norte' })
    expect(disparador.getAttribute('data-kit')).toBe('boton')
    fireEvent.keyDown(disparador, { key: 'Enter' })
    const menu = await screen.findByRole('menu')
    expect(menu.getAttribute('data-kit')).toBe('menu')
    fireEvent.keyDown(menu, { key: 'Escape' })
    const sw = screen.getByRole('switch', { name: 'Mostrar inactivas' })
    expect(sw.closest('[data-kit=interruptor]')).toBeTruthy()
    fireEvent.click(sw)
    expect((await screen.findByText('Inactiva')).closest('[data-kit=insignia]')).toBeTruthy()
  })

  it('crear es un Dialogo con Campo del kit y desactivar un Confirmar de peligro', async () => {
    abrir('/admin/ubicaciones', crearCatalogo({ ubicaciones: UBICACIONES() }).manejador)
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva sede' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Nueva sede' })
    expect(dialogo.getAttribute('data-kit')).toBe('dialogo')
    expect(within(dialogo).getByLabelText('Nombre').closest('[data-kit=campo]')).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Consultorios' }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Desactivar' }))
    const confirmar = await screen.findByRole('alertdialog')
    expect(confirmar.getAttribute('data-kit')).toBe('confirmar')
    expect(within(confirmar).getByRole('button', { name: 'Desactivar' }).getAttribute('data-variante')).toBe('peligro')
  })

  it('vacío y error con los estados del kit', async () => {
    abrir('/admin/ubicaciones', crearCatalogo().manejador)
    expect((await screen.findByText('Aún no hay ubicaciones')).closest('[data-kit=estado-vacio]')).toBeTruthy()
    cleanup()
    const catalogo = crearCatalogo()
    catalogo.fallar('GET /api/ubicaciones', () => errorApi(500, 'error_interno', 'Error.'))
    abrir('/admin/ubicaciones', catalogo.manejador)
    expect((await screen.findByText('No se pudieron cargar las ubicaciones')).closest('[data-kit=aviso]')).toBeTruthy()
  })

  it('en el teléfono el botón de acciones mide un control (48 px)', async () => {
    abrir('/admin/ubicaciones', crearCatalogo({ ubicaciones: UBICACIONES() }).manejador, { movil: true })
    expect(clases(await screen.findByRole('button', { name: 'Acciones de Sede Norte' }))).toContain('size-control')
  })
})

// ---------------------------------------------------------------------------
// Categorías
// ---------------------------------------------------------------------------

describe('caracterización de Categorías (T9): lo que no cambia', () => {
  it('mientras carga se anuncia «Cargando categorías»', async () => {
    abrir('/admin/categorias', crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }).manejador)
    expect(await screen.findByRole('status', { name: 'Cargando categorías' })).toBeTruthy()
  })

  it('un error lo dice y «Reintentar» vuelve a pedir', async () => {
    const catalogo = crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] })
    catalogo.fallar('GET /api/categorias', () => errorApi(500, 'error_interno', 'Error.'))
    abrir('/admin/categorias', catalogo.manejador)
    expect(await screen.findByText('No se pudieron cargar las categorías')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('row', { name: 'CPU' })).toBeTruthy()
  })

  it('el diálogo de nueva categoría explica para qué sirve', async () => {
    abrir('/admin/categorias', crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }).manejador)
    fireEvent.click(await screen.findByRole('button', { name: 'Nueva categoría' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Nueva categoría' })
    expect(within(dialogo).getByText('Úsala para agrupar activos parecidos en el informe.')).toBeTruthy()
  })
})

describe('diseño de Categorías (T9): kit', () => {
  const muchas = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `c${i + 1}`, nombre: `Categoría ${String(i + 1).padStart(3, '0')}` }))

  it('TablaDatos con búsqueda y paginación del kit; renombrar es un Boton', async () => {
    abrir('/admin/categorias', crearCatalogo({ categorias: muchas(30) }).manejador)
    const fila = await screen.findByRole('row', { name: 'Categoría 001' })
    expect(fila.closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('searchbox', { name: 'Buscar categorías' }).closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Paginación de categorías' })).toBeTruthy()
    expect(within(fila).getByRole('button', { name: 'Renombrar Categoría 001' }).getAttribute('data-kit')).toBe('boton')
    expect(screen.getByRole('button', { name: 'Nueva categoría' }).getAttribute('data-variante')).toBe('principal')
    expect(screen.getByRole('button', { name: 'Cargar sugeridas' }).getAttribute('data-variante')).toBe('secundario')
  })

  it('el diálogo es del kit y vacío sin categorías con su estado del kit', async () => {
    abrir('/admin/categorias', crearCatalogo().manejador)
    expect((await screen.findByText('Aún no hay categorías')).closest('[data-kit=estado-vacio]')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Crear una' }))
    expect((await screen.findByRole('dialog', { name: 'Nueva categoría' })).getAttribute('data-kit')).toBe('dialogo')
  })
})

// ---------------------------------------------------------------------------
// Usuarios
// ---------------------------------------------------------------------------

const CREADA = {
  invitacion: { id: '00000000-0000-4000-8000-00000000f001', email: 'nuevo@ejemplo.test', rol: 'contador', expira_en: '2026-11-17T15:30:00+00:00' },
  enlace: '/invitacion#tok_sintetico',
}
const invitar: Manejador = (url) => (url === '/api/invitaciones' ? json(201, CREADA) : undefined)

async function crearInvitacion() {
  await screen.findByRole('heading', { level: 1, name: 'Usuarios' })
  fireEvent.change(screen.getByLabelText('Correo de la persona'), { target: { value: 'nuevo@ejemplo.test' } })
  fireEvent.click(screen.getByRole('button', { name: 'Crear invitación' }))
  return (await screen.findByLabelText('Enlace de invitación')) as HTMLInputElement
}

describe('caracterización de Usuarios (T9): lo que no cambia', () => {
  it('el enlace no se escribe en la consola ni se guarda en el navegador', async () => {
    const espias = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m))
    abrir('/admin/usuarios', invitar)
    await crearInvitacion()
    const escrito = espias.flatMap((s) => s.mock.calls).map((args) => args.map(String).join(' '))
    expect(escrito.some((t) => t.includes('tok_sintetico'))).toBe(false)
    const guardado = [...Object.values(localStorage), ...Object.values(sessionStorage)].join(' ')
    expect(guardado).not.toContain('tok_sintetico')
  })

  it('después de crearla vuelve al formulario solo con «Invitar a otra persona» (el enlace no se vuelve a mostrar)', async () => {
    abrir('/admin/usuarios', invitar)
    await crearInvitacion()
    expect(screen.queryByRole('button', { name: 'Crear invitación' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Invitar a otra persona' }))
    expect(screen.queryByText(/tok_sintetico/)).toBeNull()
    expect(screen.queryByDisplayValue(/tok_sintetico/)).toBeNull()
  })

  it('el contador no entra', async () => {
    abrir('/admin/usuarios', invitar, { rol: 'contador' })
    expect(await screen.findByRole('heading', { level: 1, name: 'No tienes permiso para ver esto' })).toBeTruthy()
  })
})

describe('diseño de Usuarios (T9): kit', () => {
  it('formulario en un Panel del kit con Campo y la acción principal', async () => {
    abrir('/admin/usuarios', invitar)
    const panel = await screen.findByRole('region', { name: 'Invitar a una persona' })
    expect(panel.getAttribute('data-kit')).toBe('panel')
    expect(within(panel).getByLabelText('Correo de la persona').closest('[data-kit=campo]')).toBeTruthy()
    expect(within(panel).getByRole('button', { name: 'Crear invitación' }).getAttribute('data-variante')).toBe('principal')
    expect(screen.getByRole('region', { name: 'Personas con acceso' }).getAttribute('data-kit')).toBe('panel')
  })

  it('la invitación creada es un aviso de éxito y el enlace un Campo del kit en mono', async () => {
    abrir('/admin/usuarios', invitar)
    const enlace = await crearInvitacion()
    expect(screen.getByText('Invitación creada').closest('[data-kit=aviso]')?.getAttribute('data-tono')).toBe('exito')
    expect(enlace.closest('[data-kit=campo]')).toBeTruthy()
    expect(clases(enlace)).toContain('font-mono')
    expect(screen.getByRole('button', { name: 'Copiar enlace' }).getAttribute('data-variante')).toBe('principal')
    expect(screen.getByRole('button', { name: 'Invitar a otra persona' }).getAttribute('data-variante')).toBe('secundario')
  })
})

// ---------------------------------------------------------------------------
// Empresa
// ---------------------------------------------------------------------------

function apiEmpresa(inicial: Partial<Empresa> = {}) {
  let empresa: Empresa = { nombre: 'Clínica sintética', direccion: 'Calle 1', nit: null, telefono: null, correo: null, logo: null, completa: true, ...inicial }
  const manejador: Manejador = (url, init) => {
    if (url === '/api/empresa' && (init.method ?? 'GET') === 'GET') return json(200, { empresa })
    if (url === '/api/empresa/logo' && init.method === 'PUT') {
      const id = String((init.body as FormData).get('logo_id'))
      empresa = { ...empresa, logo: { id } }
      return json(201, { logo: { id, ancho: 600, alto: 600 } })
    }
    if (url === '/api/empresa/logo' && init.method === 'DELETE') {
      empresa = { ...empresa, logo: null }
      return new Response(null, { status: 204 })
    }
    if (url.startsWith('/api/empresa/logo/')) return new Response('png', { status: 200, headers: { 'Content-Type': 'image/png' } })
    return undefined
  }
  return manejador
}

const png = () => new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'logo.png', { type: 'image/png' })

describe('caracterización de Empresa (T9): lo que no cambia', () => {
  it('mientras carga se anuncia «Cargando datos de la empresa»', async () => {
    abrir('/admin/empresa', apiEmpresa())
    expect(await screen.findByLabelText('Cargando datos de la empresa')).toBeTruthy()
  })

  // El error de carga de Empresa no se prueba aquí: useEmpresa reintenta con la espera por
  // defecto de TanStack Query (1 s, 2 s, 4 s) y no se toca lib/ en esta spec.
  it('explica qué sale en los informes y qué conservan los ya cerrados', async () => {
    abrir('/admin/empresa', apiEmpresa())
    expect(
      await screen.findByText(
        'Los datos y el logo salen en el encabezado del Excel y del PDF de los informes que cierres desde ahora. Los informes ya cerrados conservan los datos que tenían.',
      ),
    ).toBeTruthy()
    expect(screen.getByText('Nombre y dirección son obligatorios; lo demás, si lo tienes.')).toBeTruthy()
    expect(screen.getByText('Opcional. Imagen horizontal de 160 × 64 px. Sale arriba a la izquierda en el Excel y en el PDF.')).toBeTruthy()
  })

  it('un NIT inválido se marca en su campo, lleva el foco al primer error y no se envía', async () => {
    const f = simularSesion('admin', apiEmpresa({ direccion: null, completa: false }))
    simularAncho({ movil: false })
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/empresa'] })} />)
    const nit = (await screen.findByRole('textbox', { name: /NIT/ })) as HTMLInputElement
    fireEvent.change(nit, { target: { value: '900123456-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar datos' }))
    expect(await screen.findByText(/El NIT no es válido/)).toBeTruthy()
    expect(nit.getAttribute('aria-invalid')).toBe('true')
    expect(nit.getAttribute('aria-describedby')).toBe('empresa-nit-error')
    expect(document.activeElement?.id).toBe('empresa-direccion')
    expect(f.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  })

  it('el logo admite PNG, JPG o WebP y el texto de ayuda no cambia', async () => {
    abrir('/admin/empresa', apiEmpresa())
    await screen.findByRole('button', { name: 'Subir logo' })
    expect(screen.getByTestId('entrada-logo').getAttribute('accept')).toBe('image/png,image/jpeg,image/webp')
    expect(screen.getByText(/Horizontal, de 160 × 64 px\. PNG, JPG o WebP de hasta \d+ MB/)).toBeTruthy()
  })
})

describe('diseño de Empresa (T9; D13, R11, A9): kit y caja del logo', () => {
  it('dos Panel del kit con Campo del kit (sin el selector de compatibilidad)', async () => {
    abrir('/admin/empresa', apiEmpresa())
    const datos = await screen.findByRole('region', { name: 'Datos de la empresa' })
    expect(datos.getAttribute('data-kit')).toBe('panel')
    expect(screen.getByRole('region', { name: 'Logo' }).getAttribute('data-kit')).toBe('panel')
    const nombre = await within(datos).findByRole('textbox', { name: /Nombre o razón social/ })
    expect(nombre.closest('[data-kit=campo]')).toBeTruthy()
    expect(datos.querySelector('[data-controles-sobre-blanco]')).toBeNull()
    expect(within(datos).getByRole('button', { name: 'Guardar datos' }).getAttribute('data-variante')).toBe('principal')
  })

  it('sin logo: «Sin logo» dentro de la caja fija de 160 × 64 px', async () => {
    abrir('/admin/empresa', apiEmpresa())
    const vacio = await screen.findByText('Sin logo')
    const caja = vacio.closest('[data-kit=marco-imagen]')
    expect(caja?.getAttribute('data-variante')).toBe('logo')
    expect(clases(caja)).toEqual(expect.arrayContaining(['w-40', 'h-16', 'bg-muted', 'overflow-hidden', 'max-w-full']))
  })

  it('con logo (grande o pequeño): la misma caja de 160 × 64 px, object-contain y sin medidas propias', async () => {
    abrir('/admin/empresa', apiEmpresa())
    const subir = await screen.findByRole('button', { name: 'Subir logo' })
    await waitFor(() => expect((subir as HTMLButtonElement).disabled).toBe(false))
    fireEvent.change(screen.getByTestId('entrada-logo'), { target: { files: [png()] } })
    const img = await screen.findByRole('img', { name: 'Logo de Clínica sintética' })
    expect(clases(img)).toEqual(expect.arrayContaining(['size-full', 'object-contain']))
    expect(img.getAttribute('width')).toBeNull()
    expect(img.getAttribute('height')).toBeNull()
    expect(img.getAttribute('style')).toBeNull()
    const caja = img.closest('[data-kit=marco-imagen]')
    expect(caja?.getAttribute('data-variante')).toBe('logo')
    expect(clases(caja)).toEqual(expect.arrayContaining(['w-40', 'h-16', 'bg-muted']))
  })

  it('quitar el logo es un Confirmar del kit; la subida fallida un aviso con «Reintentar»', async () => {
    abrir('/admin/empresa', apiEmpresa({ logo: { id: '00000000-0000-4000-8000-00000000a001' } }))
    fireEvent.click(await screen.findByRole('button', { name: 'Quitar logo' }))
    expect((await screen.findByRole('alertdialog', { name: '¿Quitar el logo?' })).getAttribute('data-kit')).toBe('confirmar')
    cleanup()
    abrir(
      '/admin/empresa',
      fallarUnaVez(apiEmpresa(), (u, m) => u === '/api/empresa/logo' && m === 'PUT', () => errorApi(415, 'tipo_no_admitido', 'Solo se admiten fotos JPEG, PNG o WebP.')),
    )
    const subir = await screen.findByRole('button', { name: 'Subir logo' })
    await waitFor(() => expect((subir as HTMLButtonElement).disabled).toBe(false))
    fireEvent.change(screen.getByTestId('entrada-logo'), { target: { files: [png()] } })
    const aviso = (await screen.findByText(/Solo se admiten/)).closest('[data-kit=aviso]')
    expect(aviso?.getAttribute('data-tono')).toBe('error')
    expect(within(aviso as HTMLElement).getByRole('button', { name: 'Reintentar' })).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Pendiente (pantalla en preparación)
// ---------------------------------------------------------------------------

describe('Pendiente (T9): kit', () => {
  it('título en el encabezado del kit y el aviso como estado vacío del kit', () => {
    render(
      <MemoryRouter initialEntries={['/admin/usuarios']}>
        <Pendiente />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Usuarios' }).closest('[data-kit=encabezado-pagina]')).toBeTruthy()
    const vacio = screen.getByText('Pantalla en preparación').closest('[data-kit=estado-vacio]')
    expect(vacio?.textContent).toContain('Llega con invitar en la spec 002b; lista de usuarios en una spec posterior.')
  })
})
