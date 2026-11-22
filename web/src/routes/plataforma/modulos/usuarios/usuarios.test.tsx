import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ErrorApi, type Esquemas } from '@/lib/api/cliente'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json } from '@/test/sesion'

import { empresaDeConsulta, errorDeCambio } from './api'

// Spec 017, T10 (R29–R31, R38, R40; A14, A17; CU-07): módulo Usuarios de la consola,
// montando las rutas reales con la API simulada.

type Empresa = Esquemas['EmpresaPlataforma']
type Usuario = Esquemas['UsuarioPlataforma']
type Modulo = Esquemas['ModuloPlataforma']

const DEV = { id: '00000000-0000-4000-8000-0000000000f1', email: 'dev@ejemplo.test', nombre: 'Daniela Ríos' }
const SESION = { access_token: 'jwt.plataforma', token_type: 'Bearer', expires_in: 600, desarrollador: DEV }
const MODULOS: Modulo[] = [
  { id: 'empresas', titulo: 'Empresas', orden: 10 },
  { id: 'usuarios', titulo: 'Usuarios', orden: 20 },
  { id: 'actividad', titulo: 'Actividad', orden: 30 },
]

const ACTIVA = 'a0b1c2d3-0000-4000-8000-0000000001ab'
const INACTIVA = '00000000-0000-4000-8000-000000000102'

function empresa(id: string, nombre: string, activa = true): Empresa {
  return { id, nombre, activa, creado_en: '2026-11-10T15:00:00+00:00', tiene_logo: false, n_membresias_activas: 2, n_admins_activos: 1 }
}
const EMPRESAS = [empresa(ACTIVA, 'Biotecnología Dental'), empresa(INACTIVA, 'Sonrisas del Valle', false)]

const ANA: Usuario = { id: '00000000-0000-4000-8000-000000000a01', nombre: 'Ana Torres', email: 'ana@clinica.test', rol: 'admin', activa: true, debe_cambiar_password: true }
const LUIS: Usuario = { id: '00000000-0000-4000-8000-000000000c01', nombre: 'Luis Pérez', email: 'luis@clinica.test', rol: 'contador', activa: true, debe_cambiar_password: false }
const EVA: Usuario = { id: '00000000-0000-4000-8000-000000000c02', nombre: 'Eva Gil', email: 'eva@clinica.test', rol: 'contador', activa: false, debe_cambiar_password: false }
const USUARIOS = [ANA, LUIS, EVA]

type Manejador = (url: string, init: RequestInit) => Response | Promise<Response | undefined> | undefined

function abrir(path: string, { usuarios = USUARIOS, empresas = EMPRESAS, extra }: { usuarios?: Usuario[]; empresas?: Empresa[] | Response; extra?: Manejador } = {}) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/plataforma/auth/refresh') return json(200, SESION)
    if (url === '/api/plataforma/modulos') return json(200, { modulos: MODULOS })
    if (url === '/api/plataforma/empresas?estado=todas') return empresas instanceof Response ? empresas.clone() : json(200, { empresas })
    if (/^\/api\/plataforma\/empresas\/[^/]+\/usuarios$/.test(url) && (init.method ?? 'GET') === 'GET') return json(200, { usuarios })
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', f)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

const llamadas = (f: ReturnType<typeof vi.fn>, url: string | RegExp, metodo?: string) =>
  f.mock.calls.filter(
    ([e, init]) =>
      (typeof url === 'string' ? String(e) === url : url.test(String(e))) &&
      (!metodo || ((init as RequestInit | undefined)?.method ?? 'GET') === metodo),
  )
const cuerpo = (init: unknown) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>
const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name })
const rutaPatch = (empresa: string, usuario: string) => `/api/plataforma/empresas/${empresa}/usuarios/${usuario}`
const tabla = (empresaNombre = 'Biotecnología Dental') => screen.findByRole('table', { name: `Usuarios de ${empresaNombre}` })

async function pedirCambio(nombre: string, verbo: 'Desactivar' | 'Reactivar') {
  fireEvent.click(await screen.findByRole('button', { name: `${verbo} a ${nombre}` }))
  return screen.findByRole('alertdialog')
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('elegir la empresa (CU-07; ?empresa=)', () => {
  it('aparece en el menú; sin empresa pide elegir una y no pide usuarios', async () => {
    const { f } = abrir('/plataforma/usuarios')
    await h1('Usuarios')
    expect(screen.getByRole('link', { name: 'Usuarios' }).getAttribute('aria-current')).toBe('page')
    expect(await screen.findByText('Elige una empresa')).toBeTruthy()
    expect(llamadas(f, /\/usuarios$/)).toHaveLength(0)
  })

  it('lee ?empresa= y muestra sus usuarios', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    await tabla()
    expect(llamadas(f, `/api/plataforma/empresas/${ACTIVA}/usuarios`)).toHaveLength(1)
    expect(screen.getByRole('combobox', { name: 'Empresa' }).textContent).toContain('Biotecnología Dental')
  })

  it.each([
    ['no es un UUID', 'abc'],
    ['en mayúsculas (no canónico)', ACTIVA.toUpperCase()],
    ['el UUID nulo', '00000000-0000-0000-0000-000000000000'],
    ['con ruta inyectada', `${ACTIVA}/../x`],
    ['vacío', ''],
  ])('ignora ?empresa= %s: sin redirigir ni pedir nada', async (_, valor) => {
    const { f, router } = abrir(`/plataforma/usuarios?empresa=${encodeURIComponent(valor)}`)
    expect(await screen.findByText('Elige una empresa')).toBeTruthy()
    expect(router.state.location.pathname).toBe('/plataforma/usuarios')
    expect(llamadas(f, /\/usuarios$/)).toHaveLength(0)
  })

  it('elegir en el selector deja la empresa en la URL y carga sus usuarios', async () => {
    const { f, router } = abrir('/plataforma/usuarios')
    await screen.findByText('Elige una empresa')
    const selector = screen.getByRole('combobox', { name: 'Empresa' })
    await waitFor(() => expect(selector.hasAttribute('disabled')).toBe(false))
    fireEvent.click(selector)
    const opciones = within(await screen.findByRole('listbox')).getAllByRole('option')
    // Por nombre, y la desactivada lo dice.
    expect(opciones.map((o) => o.textContent)).toEqual(['Biotecnología Dental', 'Sonrisas del Valle (desactivada)'])
    fireEvent.click(opciones[0])
    await tabla()
    expect(router.state.location.search).toBe(`?empresa=${ACTIVA}`)
    expect(llamadas(f, `/api/plataforma/empresas/${ACTIVA}/usuarios`)).toHaveLength(1)
  })

  it('una empresa que no existe (404) lo dice sin romper', async () => {
    const otra = '00000000-0000-4000-8000-000000000999'
    abrir(`/plataforma/usuarios?empresa=${otra}`, {
      extra: (url) => (url === `/api/plataforma/empresas/${otra}/usuarios` ? errorApi(404, 'no_encontrado', 'La empresa no existe.') : undefined),
    })
    expect(await screen.findByText('No encontramos esa empresa')).toBeTruthy()
    expect(screen.getByRole('combobox', { name: 'Empresa' })).toBeTruthy()
  })

  it('sin empresas lo dice y lleva a Empresas', async () => {
    abrir('/plataforma/usuarios', { empresas: [] })
    expect(await screen.findByText('Aún no hay empresas')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a Empresas' }).getAttribute('href')).toBe('/plataforma/empresas')
  })
})

describe('lista de usuarios (R29; A17)', () => {
  it('muestra nombre, correo, rol, estado y «Cambio de contraseña pendiente», sin fecha de alta', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const filas = within(await tabla()).getAllByRole('row').slice(1)
    expect(filas).toHaveLength(3)
    expect(within(filas[0]).getByText('Ana Torres')).toBeTruthy()
    expect(within(filas[0]).getByText('ana@clinica.test')).toBeTruthy()
    expect(within(filas[0]).getByText('Admin')).toBeTruthy()
    expect(within(filas[0]).getByText('Activo')).toBeTruthy()
    expect(within(filas[0]).getByText('Cambio de contraseña pendiente')).toBeTruthy()
    expect(within(filas[1]).getByText('Contador')).toBeTruthy()
    expect(within(filas[1]).queryByText('Cambio de contraseña pendiente')).toBeNull()
    expect(within(filas[2]).getByText('Desactivado')).toBeTruthy()
    expect(within(filas[2]).getByRole('button', { name: 'Reactivar a Eva Gil' })).toBeTruthy()
    expect(screen.getByText(/3 usuarios · 2 activos/)).toBeTruthy()
    expect(screen.queryByRole('columnheader', { name: /alta/i })).toBeNull()
  })

  it('nombres y correos se pintan como texto, nunca como HTML', async () => {
    const raro = { ...LUIS, nombre: '<img src=x onerror=alert(1)>', email: '<b>x</b>@clinica.test' }
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, { usuarios: [raro] })
    await tabla()
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeTruthy()
    expect(screen.getByText('<b>x</b>@clinica.test')).toBeTruthy()
    expect(document.querySelector('img[src="x"]')).toBeNull()
  })

  it('a 375 px la lista son tarjetas con su acción (A14)', async () => {
    simularAncho({ movil: true })
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const lista = await screen.findByRole('list', { name: 'Usuarios de Biotecnología Dental' })
    expect(within(lista).getAllByRole('listitem')).toHaveLength(3)
    expect(within(lista).getByRole('button', { name: 'Desactivar a Luis Pérez' })).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('vacía, cargando y con error que se reintenta', async () => {
    let intentos = 0
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url) => {
        if (url !== `/api/plataforma/empresas/${ACTIVA}/usuarios`) return undefined
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible', 'El servicio no está disponible.') : json(200, { usuarios: [] })
      },
    })
    expect(await screen.findByRole('status', { name: 'Cargando usuarios' })).toBeTruthy()
    expect(await screen.findByText('No se pudieron cargar los usuarios')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Esta empresa aún no tiene usuarios')).toBeTruthy()
  })
})

describe('desactivar y reactivar (R30, R40)', () => {
  it('desactivar confirma con persona, empresa, efecto y la sesión abierta; cancelar no envía', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    expect(within(dialogo).getByRole('heading', { name: '¿Desactivar a Luis Pérez?' })).toBeTruthy()
    expect(dialogo.textContent).toContain('Luis Pérez no podrá entrar a Biotecnología Dental.')
    expect(dialogo.textContent).toContain('Si tiene una sesión abierta, se cierra en su siguiente acción. No se borra nada')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(llamadas(f, /\/usuarios\//, 'PATCH')).toHaveLength(0)
  })

  it('al confirmar envía {activa: false} con el token de plataforma y la fila queda «Desactivado»', async () => {
    let hecho = false
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) => {
        if (url === rutaPatch(ACTIVA, LUIS.id) && init.method === 'PATCH') {
          hecho = true
          return json(200, { id: LUIS.id, activa: false })
        }
        if (url === `/api/plataforma/empresas/${ACTIVA}/usuarios` && hecho) {
          return json(200, { usuarios: USUARIOS.map((u) => (u.id === LUIS.id ? { ...u, activa: false } : u)) })
        }
        return undefined
      },
    })
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    await waitFor(() => expect(llamadas(f, rutaPatch(ACTIVA, LUIS.id), 'PATCH')).toHaveLength(1))
    const [, init] = llamadas(f, rutaPatch(ACTIVA, LUIS.id), 'PATCH')[0]
    expect(cuerpo(init)).toEqual({ activa: false })
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer jwt.plataforma')
    const fila = screen.getByText('Luis Pérez').closest('tr')!
    await waitFor(() => expect(within(fila).getByText('Desactivado')).toBeTruthy())
    expect(within(fila).getByRole('button', { name: 'Reactivar a Luis Pérez' })).toBeTruthy()
    // Los conteos de Empresas cambian: se vuelve a pedir la lista.
    await waitFor(() => expect(llamadas(f, '/api/plataforma/empresas?estado=todas').length).toBeGreaterThan(1))
  })

  it('reactivar confirma y envía {activa: true}; otra membresía activa en otra empresa no se bloquea en la web', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) => (url === rutaPatch(ACTIVA, EVA.id) && init.method === 'PATCH' ? json(200, { id: EVA.id, activa: true }) : undefined),
    })
    const dialogo = await pedirCambio('Eva Gil', 'Reactivar')
    expect(within(dialogo).getByRole('heading', { name: '¿Reactivar a Eva Gil?' })).toBeTruthy()
    expect(dialogo.textContent).toContain('Eva Gil podrá volver a entrar a Biotecnología Dental')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, reactivar' }))
    await waitFor(() => expect(llamadas(f, rutaPatch(ACTIVA, EVA.id), 'PATCH')).toHaveLength(1))
    expect(cuerpo(llamadas(f, rutaPatch(ACTIVA, EVA.id), 'PATCH')[0][1])).toEqual({ activa: true })
  })

  it('409 ultimo_admin: «No se puede desactivar al último admin activo de la empresa» y nada cambia', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) =>
        url === rutaPatch(ACTIVA, ANA.id) && init.method === 'PATCH'
          ? errorApi(409, 'ultimo_admin', 'No se puede desactivar al último admin activo de la empresa.')
          : undefined,
    })
    const dialogo = await pedirCambio('Ana Torres', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    const aviso = (await screen.findByText('No se puede desactivar al último admin activo de la empresa')).closest('[data-kit=aviso]')!
    expect(aviso.textContent).toContain('Biotecnología Dental necesita al menos un admin activo.')
    // Repetirlo no serviría: sin «Reintentar».
    expect(within(aviso as HTMLElement).queryByRole('button', { name: 'Reintentar' })).toBeNull()
    const fila = screen.getByText('Ana Torres').closest('tr')!
    expect(within(fila).getByText('Activo')).toBeTruthy()
  })

  it('503: lo explica y «Reintentar» repite el mismo PATCH (idempotente)', async () => {
    let intentos = 0
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) => {
        if (url !== rutaPatch(ACTIVA, LUIS.id) || init.method !== 'PATCH') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible', 'No disponible.') : json(200, { id: LUIS.id, activa: false })
      },
    })
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    expect(await screen.findByText('El servicio no está disponible en este momento')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(llamadas(f, rutaPatch(ACTIVA, LUIS.id), 'PATCH')).toHaveLength(2))
    for (const [, init] of llamadas(f, rutaPatch(ACTIVA, LUIS.id), 'PATCH')) expect(cuerpo(init)).toEqual({ activa: false })
    await waitFor(() => expect(screen.queryByText('El servicio no está disponible en este momento')).toBeNull())
  })

  it('429: dice cuánto esperar', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) =>
        url === rutaPatch(ACTIVA, LUIS.id) && init.method === 'PATCH'
          ? json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '120' })
          : undefined,
    })
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    expect(await screen.findByText('Hiciste varias acciones seguidas')).toBeTruthy()
    expect(screen.getByText('Espera 2 minutos e intenta de nuevo.')).toBeTruthy()
  })

  it('404 del PATCH: el usuario ya no es de la empresa; se refresca la lista', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) =>
        url === rutaPatch(ACTIVA, LUIS.id) && init.method === 'PATCH' ? errorApi(404, 'no_encontrado', 'Ese usuario no pertenece a esta empresa.') : undefined,
    })
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    expect(await screen.findByText('Ese usuario ya no aparece en esta empresa')).toBeTruthy()
    await waitFor(() => expect(llamadas(f, `/api/plataforma/empresas/${ACTIVA}/usuarios`, 'GET').length).toBe(2))
  })

  it('401 con renovación rechazada: lleva a /plataforma/entrar sin aviso de error', async () => {
    let renovaciones = 0
    const { router } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) => {
        if (url === '/api/plataforma/auth/refresh') {
          renovaciones += 1
          return renovaciones === 1 ? json(200, SESION) : errorApi(401, 'no_autenticado', 'Debes iniciar sesión.')
        }
        if (url === rutaPatch(ACTIVA, LUIS.id) && init.method === 'PATCH') return errorApi(401, 'no_autenticado', 'Debes iniciar sesión.')
        return undefined
      },
    })
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/plataforma/entrar'))
    expect(screen.queryByText('No se pudo cambiar el usuario')).toBeNull()
  })
})

describe('empresa desactivada (R31, D9)', () => {
  it('las acciones quedan deshabilitadas con la explicación', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${INACTIVA}`)
    await tabla('Sonrisas del Valle')
    expect(screen.getByText('Esta empresa está desactivada')).toBeTruthy()
    const boton = screen.getByRole('button', { name: 'Desactivar a Luis Pérez' }) as HTMLButtonElement
    expect(boton.disabled).toBe(true)
    const explicacion = document.getElementById(boton.getAttribute('aria-describedby')!)!
    expect(explicacion.textContent).toContain('primero reactiva la empresa en Empresas')
    expect((screen.getByRole('button', { name: 'Reactivar a Eva Gil' }) as HTMLButtonElement).disabled).toBe(true)
    expect(llamadas(f, /\/usuarios\//, 'PATCH')).toHaveLength(0)
  })

  it('409 empresa_inactiva (la desactivaron en otra parte): lo explica y vuelve a pedir las empresas', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) =>
        url === rutaPatch(ACTIVA, LUIS.id) && init.method === 'PATCH'
          ? errorApi(409, 'empresa_inactiva', 'La empresa está desactivada. Reactívala antes de cambiar sus usuarios.')
          : undefined,
    })
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    expect(await screen.findByText('La empresa está desactivada')).toBeTruthy()
    expect(screen.getByText(/Reactiva Biotecnología Dental en Empresas antes de cambiar sus usuarios/)).toBeTruthy()
    await waitFor(() => expect(llamadas(f, '/api/plataforma/empresas?estado=todas').length).toBe(2))
  })
})

describe('estado de la empresa aún desconocido (D23)', () => {
  it('mientras cargan las empresas, las acciones quedan deshabilitadas con su estado', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url) => (url === '/api/plataforma/empresas?estado=todas' ? new Promise<Response>(() => {}) : undefined),
    })
    const boton = (await screen.findByRole('button', { name: 'Desactivar a Luis Pérez' })) as HTMLButtonElement
    expect(boton.disabled).toBe(true)
    expect((screen.getByRole('button', { name: 'Reactivar a Eva Gil' }) as HTMLButtonElement).disabled).toBe(true)
    const estado = document.getElementById(boton.getAttribute('aria-describedby') ?? '')
    expect(estado?.textContent).toMatch(/Comprobando el estado de la empresa/)
    expect(estado?.closest('[role="status"]') ?? estado?.getAttribute('role')).toBeTruthy()
    fireEvent.click(boton)
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(screen.queryByText(/esta empresa/)).toBeNull()
    expect(llamadas(f, /\/usuarios\//, 'PATCH')).toHaveLength(0)
  })

  it('si fallan las empresas, lo dice con «Reintentar»; al cargar se habilitan y nombran la empresa real', async () => {
    let intentos = 0
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url) => {
        if (url !== '/api/plataforma/empresas?estado=todas') return undefined
        intentos += 1
        // 400: sin reintentos automáticos de la consulta (como en Empresas).
        return intentos === 1 ? errorApi(400, 'solicitud_invalida', 'La solicitud no es válida.') : json(200, { empresas: EMPRESAS })
      },
    })
    const aviso = (await screen.findByText('No se pudo cargar la lista de empresas')).closest('[data-kit="aviso"], [role="alert"], [role="status"]') ?? document.body
    const boton = (await screen.findByRole('button', { name: 'Desactivar a Luis Pérez' })) as HTMLButtonElement
    expect(boton.disabled).toBe(true)
    expect(document.getElementById(boton.getAttribute('aria-describedby') ?? '')?.textContent).toMatch(/No se pudo cargar la lista de empresas/)
    fireEvent.click(within(aviso as HTMLElement).getByRole('button', { name: 'Reintentar' }))
    await tabla()
    await waitFor(() => expect((screen.getByRole('button', { name: 'Desactivar a Luis Pérez' }) as HTMLButtonElement).disabled).toBe(false))
    const dialogo = await pedirCambio('Luis Pérez', 'Desactivar')
    expect(dialogo.textContent).toContain('Biotecnología Dental')
    expect(dialogo.textContent).not.toContain('esta empresa')
  })
})

describe('reglas del módulo (api.ts)', () => {
  it('empresaDeConsulta solo acepta un UUID canónico no nulo', () => {
    expect(empresaDeConsulta(ACTIVA)).toBe(ACTIVA)
    expect(empresaDeConsulta(null)).toBeNull()
    expect(empresaDeConsulta('')).toBeNull()
    expect(empresaDeConsulta(ACTIVA.toUpperCase())).toBeNull()
    expect(empresaDeConsulta(`{${ACTIVA}}`)).toBeNull()
    expect(empresaDeConsulta(ACTIVA.replace(/-/g, ''))).toBeNull()
    expect(empresaDeConsulta(` ${ACTIVA}`)).toBeNull()
    expect(empresaDeConsulta('00000000-0000-0000-0000-000000000000')).toBeNull()
  })

  it('errorDeCambio traduce los códigos del contrato', () => {
    const e = (status: number, code: string) => new ErrorApi(status, code as never, 'mensaje')
    expect(errorDeCambio(e(409, 'ultimo_admin'), ANA, 'X').reintentar).toBe(false)
    expect(errorDeCambio(e(409, 'empresa_inactiva'), ANA, 'X').titulo).toBe('La empresa está desactivada')
    expect(errorDeCambio(e(404, 'no_encontrado'), ANA, 'X').reintentar).toBe(false)
    expect(errorDeCambio(e(503, 'servicio_no_disponible'), ANA, 'X').reintentar).toBe(true)
    expect(errorDeCambio(e(0, 'sin_conexion'), ANA, 'X')).toMatchObject({ titulo: 'Sin conexión con el servidor', reintentar: true })
    expect(errorDeCambio(new Error('x'), ANA, 'X').reintentar).toBe(true)
  })
})
