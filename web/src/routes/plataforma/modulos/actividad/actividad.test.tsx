import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Esquemas } from '@/lib/api/cliente'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json } from '@/test/sesion'

import { ACCIONES, diaColombia, errorDeRango, fechaColombia, textoAccion } from './api'

// Spec 017, T10 (R32–R34, R38; A14, A18; CU-08): módulo Actividad de la consola,
// montando las rutas reales con la API simulada.

type Registro = Esquemas['RegistroActividad']
type Modulo = Esquemas['ModuloPlataforma']
type Empresa = Esquemas['EmpresaPlataforma']

const DEV = { id: '00000000-0000-4000-8000-0000000000f1', email: 'dev@ejemplo.test', nombre: 'Daniela Ríos' }
const SESION = { access_token: 'jwt.plataforma', token_type: 'Bearer', expires_in: 600, desarrollador: DEV }
const MODULOS: Modulo[] = [
  { id: 'empresas', titulo: 'Empresas', orden: 10 },
  { id: 'usuarios', titulo: 'Usuarios', orden: 20 },
  { id: 'actividad', titulo: 'Actividad', orden: 30 },
]
const EMP = 'a0b1c2d3-0000-4000-8000-0000000001ab'
const EMPRESAS: Empresa[] = [
  { id: EMP, nombre: 'Biotecnología Dental', activa: true, creado_en: '2026-11-10T15:00:00+00:00', tiene_logo: false, n_membresias_activas: 2, n_admins_activos: 1 },
]

function registro(n: number, extra: Partial<Registro> = {}): Registro {
  return {
    id: `00000000-0000-4000-8000-0000000002${String(n).padStart(2, '0')}`,
    fecha: '2026-11-21T03:30:00+00:00',
    accion: 'empresa_creada',
    resultado: 'ok',
    desarrollador_nombre: 'Daniela Ríos',
    empresa_id: EMP,
    empresa_nombre: 'Biotecnología Dental',
    objeto_id: EMP,
    ...extra,
  }
}

const PAGINA = [
  registro(1, { accion: 'usuario_desactivado' }),
  registro(2, { accion: 'desarrollador_creado', desarrollador_nombre: 'Operador', empresa_id: null, empresa_nombre: null }),
]

type Manejador = (url: string, init: RequestInit) => Response | Promise<Response | undefined> | undefined

function abrir({ paginas, extra }: { paginas?: (url: URL) => Response | undefined; extra?: Manejador } = {}) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/plataforma/auth/refresh') return json(200, SESION)
    if (url === '/api/plataforma/modulos') return json(200, { modulos: MODULOS })
    if (url === '/api/plataforma/empresas?estado=todas') return json(200, { empresas: EMPRESAS })
    if (url.startsWith('/api/plataforma/actividad')) {
      const respuesta = paginas?.(new URL(url, 'http://x'))
      return respuesta ?? json(200, { actividad: PAGINA, siguiente: null })
    }
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', f)
  const router = createMemoryRouter(routes, { initialEntries: ['/plataforma/actividad'] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

const pedidas = (f: ReturnType<typeof vi.fn>) =>
  f.mock.calls.map(([e]) => String(e)).filter((u) => u.startsWith('/api/plataforma/actividad')).map((u) => new URL(u, 'http://x').searchParams)
const tabla = () => screen.findByRole('table', { name: 'Actividad' })

async function elegirEnFiltro(filtro: string, opcion: string | RegExp) {
  fireEvent.click(screen.getByRole('button', { name: filtro }))
  fireEvent.click(await screen.findByRole('radio', { name: opcion }))
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('lista de actividad (CU-08; R32)', () => {
  it('aparece en el menú y pide la primera página sin filtros ni cursor', async () => {
    const { f } = abrir()
    await screen.findByRole('heading', { level: 1, name: 'Actividad' })
    expect(screen.getByRole('link', { name: 'Actividad' }).getAttribute('aria-current')).toBe('page')
    await tabla()
    expect([...pedidas(f)[0].keys()]).toEqual([])
  })

  it('muestra la acción en español, fecha en hora de Colombia, resultado, quién y empresa', async () => {
    abrir()
    const filas = within(await tabla()).getAllByRole('row').slice(1)
    expect(filas).toHaveLength(2)
    expect(within(filas[0]).getByText('Usuario desactivado')).toBeTruthy()
    expect(within(filas[0]).getByText('Hecho')).toBeTruthy()
    expect(within(filas[0]).getByText('Daniela Ríos')).toBeTruthy()
    expect(within(filas[0]).getByText('Biotecnología Dental')).toBeTruthy()
    // 03:30 UTC del 21 = 22:30 del 20 en Colombia (UTC−5).
    const hora = within(filas[0]).getByText(/^20\D+nov/)
    expect(hora.textContent).toMatch(/10:30/)
    expect(hora.getAttribute('dateTime')).toBe('2026-11-21T03:30:00+00:00')
    expect(within(filas[1]).getByText('Desarrollador creado')).toBeTruthy()
    expect(within(filas[1]).getByText('Operador')).toBeTruthy()
    expect(within(filas[1]).getByText('—')).toBeTruthy()
  })

  it('a 375 px la lista son tarjetas (A14)', async () => {
    simularAncho({ movil: true })
    abrir()
    const lista = await screen.findByRole('list', { name: 'Actividad' })
    expect(within(lista).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('vacía: «Aún no hay actividad»', async () => {
    abrir({ paginas: () => json(200, { actividad: [], siguiente: null }) })
    expect(await screen.findByText('Aún no hay actividad')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Cargar más' })).toBeNull()
  })

  it('con error lo dice y se reintenta', async () => {
    let intentos = 0
    abrir({
      paginas: () => {
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible', 'El servicio no está disponible.') : undefined
      },
    })
    expect(await screen.findByText('No se pudo cargar la actividad')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await tabla()).toBeTruthy()
  })

  it('nombres como texto, nunca HTML', async () => {
    abrir({ paginas: () => json(200, { actividad: [registro(1, { desarrollador_nombre: '<b>x</b>', empresa_nombre: '<img src=x>' })], siguiente: null }) })
    await tabla()
    expect(screen.getByText('<b>x</b>')).toBeTruthy()
    expect(screen.getByText('<img src=x>')).toBeTruthy()
    expect(document.querySelector('img[src="x"]')).toBeNull()
  })
})

describe('cargar más por cursor (R32; A18)', () => {
  it('pide la siguiente con el cursor del servidor y conserva lo cargado', async () => {
    const { f } = abrir({
      paginas: (url) =>
        url.searchParams.get('cursor') === 'c1'
          ? json(200, { actividad: [registro(3, { accion: 'login_ok', empresa_id: null, empresa_nombre: null })], siguiente: null })
          : json(200, { actividad: PAGINA, siguiente: 'c1' }),
    })
    await tabla()
    expect(screen.getByText('2 registros cargados')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByText('Inicio de sesión')).toBeTruthy()
    expect(within(screen.getByRole('table', { name: 'Actividad' })).getAllByRole('row').slice(1)).toHaveLength(3)
    expect(pedidas(f)[1].get('cursor')).toBe('c1')
    expect(screen.getByText('3 registros · no hay más')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Cargar más' })).toBeNull()
  })

  it('si falla la siguiente página, lo ya cargado queda y se puede reintentar', async () => {
    let fallos = 0
    abrir({
      paginas: (url) => {
        if (url.searchParams.get('cursor') !== 'c1') return json(200, { actividad: PAGINA, siguiente: 'c1' })
        fallos += 1
        return fallos === 1 ? errorApi(503, 'servicio_no_disponible', 'El servicio no está disponible.') : json(200, { actividad: [registro(3)], siguiente: null })
      },
    })
    await tabla()
    fireEvent.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByText('No se pudieron cargar más registros')).toBeTruthy()
    expect(within(screen.getByRole('table', { name: 'Actividad' })).getAllByRole('row').slice(1)).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(within(screen.getByRole('table', { name: 'Actividad' })).getAllByRole('row').slice(1)).toHaveLength(3))
  })
})

describe('filtros (R32; A18)', () => {
  it('empresa y acción viajan al servidor y empiezan desde la primera página', async () => {
    const { f } = abrir()
    await tabla()
    await elegirEnFiltro('Empresa', 'Biotecnología Dental')
    await waitFor(() => expect(pedidas(f).at(-1)?.get('empresa_id')).toBe(EMP))
    await elegirEnFiltro('Acción', 'Usuario desactivado')
    await waitFor(() => expect(pedidas(f).at(-1)?.get('accion')).toBe('usuario_desactivado'))
    const ultima = pedidas(f).at(-1)!
    expect(ultima.get('empresa_id')).toBe(EMP)
    expect(ultima.has('cursor')).toBe(false)
  })

  it.each([
    ['Empresa editada', 'empresa_editada'],
    ['Logo reemplazado', 'empresa_logo_reemplazado'],
    ['Usuario editado', 'usuario_editado'],
    ['Contraseña temporal definida', 'usuario_contrasena_restablecida'],
  ])('C1/C1b: la acción «%s» está en el filtro y viaja como %s (A26, A29)', async (etiqueta, accion) => {
    const { f } = abrir()
    await tabla()
    await elegirEnFiltro('Acción', etiqueta)
    await waitFor(() => expect(pedidas(f).at(-1)?.get('accion')).toBe(accion))
  })

  it('la lista de acciones es la cerrada de R33 más las tres de C1 y la de C1b, en español', async () => {
    abrir()
    await tabla()
    fireEvent.click(screen.getByRole('button', { name: 'Acción' }))
    const radios = await screen.findAllByRole('radio')
    expect(radios).toHaveLength(15)
    for (const nombre of ['Empresa editada', 'Logo reemplazado', 'Usuario editado', 'Contraseña temporal definida']) expect(screen.getByRole('radio', { name: nombre })).toBeTruthy()
    expect(screen.getByRole('radio', { name: 'Contraseña de desarrollador restablecida' })).toBeTruthy()
  })

  it('las fechas se eligen con el calendario del kit y viajan como AAAA-MM-DD', async () => {
    // Mediodía: el mismo día en Colombia y en la zona del equipo de pruebas («Hoy» del kit
    // usa la fecha local y el tope, la de Colombia).
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-21T17:00:00Z'))
    const { f } = abrir()
    await tabla()
    fireEvent.click(screen.getByLabelText('Desde'))
    const dialogo = await screen.findByRole('dialog', { name: 'Elige una fecha' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Hoy' }))
    await waitFor(() => expect(pedidas(f).at(-1)?.get('desde')).toMatch(/^\d{4}-\d{2}-\d{2}$/))
    expect(pedidas(f).at(-1)?.has('hasta')).toBe(false)
  })

  it('el tope de «Desde» y «Hasta» es el día de Colombia, no el del navegador (D22)', async () => {
    // 20:00 UTC del 21: en Tokio ya es el 22 (05:00); en Colombia sigue el 21 (15:00).
    // `vi.stubEnv` cambia `process.env.TZ` y Node aplica la zona nueva al instante.
    vi.stubEnv('TZ', 'Asia/Tokyo')
    try {
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-11-21T20:00:00Z'))
      expect(new Date().getDate()).toBe(22)
      abrir()
      await tabla()
      for (const campo of ['Desde', 'Hasta']) {
        fireEvent.click(screen.getByLabelText(campo))
        const dialogo = await screen.findByRole('dialog', { name: 'Elige una fecha' })
        expect(dialogo.querySelector<HTMLButtonElement>('[data-dia="2026-11-21"]')?.disabled).toBe(false)
        expect(dialogo.querySelector<HTMLButtonElement>('[data-dia="2026-11-22"]')?.disabled).toBe(true)
        fireEvent.keyDown(dialogo, { key: 'Escape' })
        await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
      }
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('con filtros sin resultados: «No hay actividad con estos filtros» y limpiar', async () => {
    const { f } = abrir({ paginas: (url) => (url.searchParams.has('accion') ? json(200, { actividad: [], siguiente: null }) : undefined) })
    await tabla()
    await elegirEnFiltro('Acción', 'Logo subido')
    expect(await screen.findByText('No hay actividad con estos filtros')).toBeTruthy()
    fireEvent.click(screen.getAllByRole('button', { name: 'Limpiar filtros' })[0])
    await tabla()
    expect([...pedidas(f).at(-1)!.keys()]).toEqual([])
  })
})

describe('reglas del módulo (api.ts)', () => {
  it('fechaColombia usa UTC−5 sin depender de la zona del navegador', () => {
    expect(fechaColombia('2026-01-01T04:59:00Z')).toMatch(/^31\D+dic\D+2025\D+11:59\D+p/)
    expect(fechaColombia('2026-07-01T05:00:00Z')).toMatch(/^1\D+jul\D+2026\D+12:00\D+a/)
  })

  it('diaColombia da el día de Colombia (UTC−5) cerca de medianoche', () => {
    expect(diaColombia(new Date('2026-11-22T04:59:00Z'))).toBe('2026-11-21')
    expect(diaColombia(new Date('2026-11-22T05:00:00Z'))).toBe('2026-11-22')
    expect(diaColombia(new Date('2026-01-01T03:00:00Z'))).toBe('2025-12-31')
  })

  it('textoAccion cubre las 15 acciones (con las tres de C1 y la de C1b) y deja una desconocida como texto', () => {
    expect(Object.keys(ACCIONES)).toHaveLength(15)
    expect(textoAccion('empresa_logo_subido')).toBe('Logo subido')
    // C1 (A26): las tres acciones nuevas, en español.
    expect(textoAccion('empresa_editada')).toBe('Empresa editada')
    expect(textoAccion('empresa_logo_reemplazado')).toBe('Logo reemplazado')
    expect(textoAccion('usuario_editado')).toBe('Usuario editado')
    // C1b (A29): la contraseña temporal de un usuario.
    expect(textoAccion('usuario_contrasena_restablecida')).toBe('Contraseña temporal definida')
    // Cada acción relacionada queda junto a la suya en el filtro.
    const orden = Object.keys(ACCIONES)
    expect(orden.indexOf('empresa_editada')).toBe(orden.indexOf('empresa_creada') + 1)
    expect(orden.indexOf('empresa_logo_reemplazado')).toBe(orden.indexOf('empresa_logo_subido') + 1)
    expect(orden.indexOf('usuario_editado')).toBe(orden.indexOf('usuario_reactivado') + 1)
    expect(orden.indexOf('usuario_contrasena_restablecida')).toBe(orden.indexOf('usuario_editado') + 1)
    expect(textoAccion('otra_cosa')).toBe('otra_cosa')
  })

  it('errorDeRango: hasta no antes de desde, formato AAAA-MM-DD', () => {
    expect(errorDeRango('', '')).toBeNull()
    expect(errorDeRango('2026-11-01', '2026-11-01')).toBeNull()
    expect(errorDeRango('2026-11-02', '2026-11-01')).toMatch(/no puede ser antes/)
    expect(errorDeRango('01/11/2026', '')).toMatch(/AAAA-MM-DD/)
  })
})
