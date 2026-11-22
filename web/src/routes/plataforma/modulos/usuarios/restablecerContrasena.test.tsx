import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ErrorApi, type Esquemas } from '@/lib/api/cliente'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json } from '@/test/sesion'

import { CLAVE_SESION_PLATAFORMA } from '../../sesion'
import { errorDeContrasena } from './api'
import { RestablecerContrasena } from './RestablecerContrasena'

// Spec 017, C1b/T16 (R53–R60, R39; CU-14; A29 en la web): «Restablecer contraseña» por fila
// en Usuarios abre un diálogo centrado con la contraseña temporal y su confirmación. La
// contraseña no pasa por el estado de React, la caché de consultas, los registros, la URL ni
// el almacenamiento: se lee del formulario al confirmar y los campos se vacían al responder.

type Empresa = Esquemas['EmpresaPlataforma']
type Usuario = Esquemas['UsuarioPlataforma']

const DEV = { id: '00000000-0000-4000-8000-0000000000f1', email: 'dev@ejemplo.test', nombre: 'Daniela Ríos' }
const SESION = { access_token: 'jwt.plataforma', token_type: 'Bearer', expires_in: 600, desarrollador: DEV }
const MODULOS = [
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

const ANA: Usuario = { id: '00000000-0000-4000-8000-000000000a01', nombre: 'Ana Torres', email: 'ana@clinica.test', rol: 'admin', activa: true, debe_cambiar_password: false }
const LUIS: Usuario = { id: '00000000-0000-4000-8000-000000000c01', nombre: 'Luis Pérez', email: 'luis@clinica.test', rol: 'contador', activa: true, debe_cambiar_password: false }
const EVA: Usuario = { id: '00000000-0000-4000-8000-000000000c02', nombre: 'Eva Gil', email: 'eva@clinica.test', rol: 'contador', activa: false, debe_cambiar_password: false }
const USUARIOS = [ANA, LUIS, EVA]

// Valores sintéticos de prueba (nunca reales).
const CLAVE = 'Temporal-Prueba-2026'
const OTRA = 'Distinta-Prueba-2026'

type Manejador = (url: string, init: RequestInit) => Response | Promise<Response | undefined> | undefined

function abrir(path: string, { usuarios = USUARIOS, extra }: { usuarios?: Usuario[] | (() => Usuario[]); extra?: Manejador } = {}) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/plataforma/auth/refresh') return json(200, SESION)
    if (url === '/api/plataforma/modulos') return json(200, { modulos: MODULOS })
    if (url === '/api/plataforma/empresas?estado=todas') return json(200, { empresas: EMPRESAS })
    if (/^\/api\/plataforma\/empresas\/[^/]+\/usuarios$/.test(url) && (init.method ?? 'GET') === 'GET') {
      return json(200, { usuarios: typeof usuarios === 'function' ? usuarios() : usuarios })
    }
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
const rutaClave = (usuario: string, emp = ACTIVA) => `/api/plataforma/empresas/${emp}/usuarios/${usuario}/contrasena`
const listaUrl = `/api/plataforma/empresas/${ACTIVA}/usuarios`

const pidePost = (manejar: (init: RequestInit, n: number) => Response | Promise<Response>, usuario = LUIS.id): Manejador => {
  let n = 0
  return (url, init) => {
    if (url !== rutaClave(usuario) || init.method !== 'POST') return undefined
    n += 1
    return manejar(init, n)
  }
}

const sinCuerpo = () => new Response(null, { status: 204 })

async function abrirDialogo(nombre: string) {
  const boton = (await screen.findByRole('button', { name: `Restablecer la contraseña de ${nombre}` })) as HTMLButtonElement
  await waitFor(() => expect(boton.disabled).toBe(false))
  fireEvent.click(boton)
  return screen.findByRole('dialog')
}

const campoClave = (d: HTMLElement) => within(d).getByLabelText(/^Contraseña temporal/) as HTMLInputElement
const campoConfirmar = (d: HTMLElement) => within(d).getByLabelText(/^Confirmar contraseña/) as HTMLInputElement
const definir = (d: HTMLElement) => within(d).getByRole('button', { name: 'Definir contraseña' }) as HTMLButtonElement

function escribir(d: HTMLElement, clave = CLAVE, confirmacion = clave) {
  fireEvent.input(campoClave(d), { target: { value: clave } })
  fireEvent.input(campoConfirmar(d), { target: { value: confirmacion } })
}

/** Escribe, pulsa «Definir contraseña» y confirma. */
async function definirYConfirmar(d: HTMLElement, clave = CLAVE, confirmacion = clave) {
  escribir(d, clave, confirmacion)
  fireEvent.click(definir(d))
  const confirmar = await screen.findByRole('alertdialog')
  fireEvent.click(within(confirmar).getByRole('button', { name: 'Sí, definir la contraseña' }))
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
}

/** Ningún rastro del valor en DOM (valores y texto), almacenamiento, URL ni historial. */
function sinRastro(valor: string) {
  for (const campo of document.querySelectorAll('input, textarea')) expect((campo as HTMLInputElement).value).not.toContain(valor)
  expect(document.body.innerHTML).not.toContain(valor)
  expect(JSON.stringify({ ...localStorage })).not.toContain(valor)
  expect(JSON.stringify({ ...sessionStorage })).not.toContain(valor)
  expect(window.location.href).not.toContain(valor)
  expect(JSON.stringify(window.history.state ?? null)).not.toContain(valor)
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
  localStorage.clear()
  sessionStorage.clear()
})

describe('acción por fila (R60; CU-14)', () => {
  it('cada fila tiene «Restablecer contraseña» junto a Editar y Desactivar/Reactivar', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const tabla = await screen.findByRole('table', { name: 'Usuarios de Biotecnología Dental' })
    for (const u of USUARIOS) {
      const fila = within(tabla).getByText(u.nombre).closest('tr')!
      expect(within(fila).getByRole('button', { name: `Editar a ${u.nombre}` })).toBeTruthy()
      expect(within(fila).getByRole('button', { name: `Restablecer la contraseña de ${u.nombre}` }).textContent).toContain('Restablecer contraseña')
      expect(within(fila).getByRole('button', { name: `${u.activa ? 'Desactivar' : 'Reactivar'} a ${u.nombre}` })).toBeTruthy()
    }
  })

  it('a 375 px la tarjeta también la tiene', async () => {
    simularAncho({ movil: true })
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirDialogo('Luis Pérez')
    expect(within(dialogo).getByRole('heading', { name: 'Restablecer contraseña' })).toBeTruthy()
    // Cuadro centrado también en el teléfono (decisión del humano, T15b).
    expect(dialogo.getAttribute('data-forma')).toBe('centrado')
  })

  it('empresa desactivada: la acción queda deshabilitada con la explicación (como CU-07)', async () => {
    abrir(`/plataforma/usuarios?empresa=${INACTIVA}`, { usuarios: [ANA] })
    const boton = (await screen.findByRole('button', { name: 'Restablecer la contraseña de Ana Torres' })) as HTMLButtonElement
    await waitFor(() => expect(screen.getByText('Esta empresa está desactivada')).toBeTruthy())
    expect(boton.disabled).toBe(true)
    const explicacion = document.getElementById(boton.getAttribute('aria-describedby')!)!
    expect(explicacion.textContent).toMatch(/restablecer la contraseña/)
  })

  it('empresa aún desconocida (D23): también espera', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url) => (url === '/api/plataforma/empresas?estado=todas' ? new Promise<Response>(() => {}) : undefined),
    })
    const boton = (await screen.findByRole('button', { name: 'Restablecer la contraseña de Luis Pérez' })) as HTMLButtonElement
    expect(boton.disabled).toBe(true)
  })
})

describe('el diálogo (R58, R60, R39)', () => {
  it('nombra a la persona y la empresa, pide las dos contraseñas con la política y el efecto', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Luis Pérez')
    expect(d.textContent).toContain('Luis Pérez · Biotecnología Dental')
    for (const campo of [campoClave(d), campoConfirmar(d)]) {
      expect(campo.type).toBe('password')
      expect(campo.getAttribute('autocomplete')).toBe('new-password')
      expect(campo.maxLength).toBe(128)
      expect(campo.getAttribute('aria-required')).toBe('true')
      expect(campo.value).toBe('')
    }
    expect(d.textContent).toContain('Entre 10 y 128 caracteres. Evita contraseñas comunes.')
    expect(d.textContent).toContain('Luis Pérez deberá cambiarla al entrar y perderá su sesión abierta. No se vuelve a mostrar.')
    // Sin «Copiar» ni generador que exponga el valor (R39).
    expect(within(d).queryByRole('button', { name: /copiar|generar/i })).toBeNull()
  })

  it('mostrar/ocultar cambia el tipo; tras un error vuelve a oculto', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, { extra: pidePost(() => errorApi(422, 'contrasena_comun', 'Mensaje del servidor.')) })
    const d = await abrirDialogo('Luis Pérez')
    fireEvent.click(within(d).getByRole('button', { name: 'Mostrar la contraseña temporal' }))
    expect(campoClave(d).type).toBe('text')
    await definirYConfirmar(d)
    await within(d).findByText(/muy común/)
    expect(campoClave(d).type).toBe('password')
    expect(within(d).getByRole('button', { name: 'Mostrar la contraseña temporal' }).getAttribute('aria-pressed')).toBe('false')
  })

  it('una membresía desactivada lo dice (Q-P3: se permite)', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Eva Gil')
    expect(d.textContent).toContain('El acceso de Eva Gil a Biotecnología Dental está desactivado')
    expect(definir(d).disabled).toBe(false)
  })

  it('confirmación: nombra a la persona y la empresa, dice el efecto y no repite la contraseña (R60)', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Luis Pérez')
    escribir(d)
    fireEvent.click(definir(d))
    const confirmar = await screen.findByRole('alertdialog')
    expect(within(confirmar).getByRole('heading', { name: '¿Definir una contraseña temporal para Luis Pérez?' })).toBeTruthy()
    const texto = confirmar.textContent!
    expect(texto).toContain('Luis Pérez')
    expect(texto).toContain('Biotecnología Dental')
    expect(texto).toContain('Se cerrarán todas sus sesiones abiertas, también en otras empresas')
    expect(texto).toContain('deberá cambiar esta contraseña al entrar')
    expect(texto).toContain('No se vuelve a mostrar')
    // C1d (R65): la persona recibe un aviso por correo.
    expect(texto).toContain('Le enviaremos un aviso a su correo.')
    expect(texto).not.toContain(CLAVE)
    fireEvent.click(within(confirmar).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(llamadas(f, /\/contrasena$/)).toHaveLength(0)
  })
})

describe('validación en la web (sin enviar)', () => {
  it('corta: error en el campo, nada se envía y los campos se vacían', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Luis Pérez')
    escribir(d, 'corta')
    fireEvent.click(definir(d))
    expect(await within(d).findByText('Usa al menos 10 caracteres.')).toBeTruthy()
    expect(campoClave(d).getAttribute('aria-invalid')).toBe('true')
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(llamadas(f, /\/contrasena$/)).toHaveLength(0)
    expect(campoClave(d).value).toBe('')
    expect(campoConfirmar(d).value).toBe('')
    expect(d.textContent).toContain('Por seguridad, los dos campos se vaciaron')
  })

  it('confirmación distinta: error en Confirmar contraseña y nada se envía', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Luis Pérez')
    escribir(d, CLAVE, OTRA)
    fireEvent.click(definir(d))
    expect(await within(d).findByText('Las contraseñas no coinciden. Escríbelas de nuevo.')).toBeTruthy()
    expect(campoConfirmar(d).getAttribute('aria-invalid')).toBe('true')
    expect(llamadas(f, /\/contrasena$/)).toHaveLength(0)
    sinRastro(CLAVE)
    sinRastro(OTRA)
  })
})

describe('envío (R53, R58; A27)', () => {
  it('POST con exactamente {password, password_confirmacion}; 204 sin leer cuerpo; avisa y refresca la fila', async () => {
    let definida = false
    const json204 = vi.fn()
    const exito = toast.success
    const avisos = vi.spyOn(toast, 'success').mockImplementation((...args) => exito(...args))
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      usuarios: () => (definida ? [ANA, { ...LUIS, debe_cambiar_password: true }, EVA] : USUARIOS),
      extra: pidePost(() => {
        definida = true
        const r = sinCuerpo()
        // Un 204 no se lee como JSON.
        r.json = json204
        return r
      }),
    })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    await waitFor(() => expect(llamadas(f, rutaClave(LUIS.id), 'POST')).toHaveLength(1))
    const [, init] = llamadas(f, rutaClave(LUIS.id), 'POST')[0]
    const enviado = JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>
    expect(Object.keys(enviado).sort()).toEqual(['password', 'password_confirmacion'])
    expect(enviado).toEqual({ password: CLAVE, password_confirmacion: CLAVE })
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer jwt.plataforma')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(json204).not.toHaveBeenCalled()
    expect(avisos).toHaveBeenCalledTimes(1)
    expect(String(avisos.mock.calls[0][0])).toBe('Contraseña temporal definida')
    expect(JSON.stringify(avisos.mock.calls[0])).not.toContain(CLAVE)
    expect(JSON.stringify(avisos.mock.calls[0])).toContain('Luis Pérez')
    // La lista se vuelve a pedir y la fila muestra la marca que devuelve el servidor.
    await waitFor(() => expect(llamadas(f, listaUrl, 'GET').length).toBeGreaterThan(1))
    const fila = (await screen.findByText('Cambio de contraseña pendiente')).closest('tr')!
    expect(fila.textContent).toContain('Luis Pérez')
    sinRastro(CLAVE)
  })

  it('mientras se envía, el botón queda ocupado y no hay un segundo POST', async () => {
    let soltar: (r: Response) => void = () => {}
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, { extra: pidePost(() => new Promise<Response>((r) => (soltar = r))) })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    await waitFor(() => expect(llamadas(f, /\/contrasena$/, 'POST')).toHaveLength(1))
    const boton = within(d).getByRole('button', { name: /Definiendo/ }) as HTMLButtonElement
    expect(boton.getAttribute('aria-busy') === 'true' || boton.disabled).toBe(true)
    fireEvent.submit(d.querySelector('form')!)
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect((within(d).getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement).disabled).toBe(true)
    expect(campoClave(d).disabled).toBe(true)
    await act(async () => soltar(sinCuerpo()))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(llamadas(f, /\/contrasena$/, 'POST')).toHaveLength(1)
  })

  it('cancelar o cerrar vacía los campos (también al desmontar)', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Luis Pérez')
    escribir(d)
    const [a, b] = [campoClave(d), campoConfirmar(d)]
    fireEvent.click(within(d).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(a.value).toBe('')
    expect(b.value).toBe('')
    sinRastro(CLAVE)
  })
})

describe('rechazos del servidor (R55, R60): textos propios y campos vacíos', () => {
  it.each([
    ['contrasena_corta', 'password', 'Usa al menos 10 caracteres.'],
    ['contrasena_larga', 'password', 'Usa como máximo 128 caracteres.'],
    ['contrasena_comun', 'password', 'Es una contraseña muy común: elige otra más difícil de adivinar.'],
    ['contrasena_invalida', 'password', 'Esa contraseña no se puede usar. Elige otra.'],
    ['contrasenas_distintas', 'password_confirmacion', 'Las contraseñas no coinciden. Escríbelas de nuevo.'],
  ])('422 %s: error en su campo y campos vacíos', async (code, campo, texto) => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePost(() => json(422, { error: { code, message: 'Mensaje del servidor.', request_id: '00000000-0000-4000-8000-00000000e001', campo } })),
    })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    expect(await within(d).findByText(texto)).toBeTruthy()
    const conError = campo === 'password' ? campoClave(d) : campoConfirmar(d)
    expect(conError.getAttribute('aria-invalid')).toBe('true')
    expect(campoClave(d).value).toBe('')
    expect(campoConfirmar(d).value).toBe('')
    sinRastro(CLAVE)
  })

  it('409 empresa_inactiva: lo dice, no ofrece reintentar y refresca Empresas', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, { extra: pidePost(() => errorApi(409, 'empresa_inactiva')) })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    expect(await within(d).findByText('Esta empresa está desactivada')).toBeTruthy()
    expect(d.textContent).toContain('Reactiva Biotecnología Dental en Empresas')
    expect(d.textContent).toContain('No se cambió la contraseña')
    expect(definir(d).disabled).toBe(true)
    await waitFor(() => expect(llamadas(f, '/api/plataforma/empresas?estado=todas').length).toBeGreaterThan(1))
    sinRastro(CLAVE)
  })

  it('404: el usuario ya no está; refresca la lista y no ofrece reintentar', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, { extra: pidePost(() => errorApi(404, 'no_encontrado')) })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    expect(await within(d).findByText('Ese usuario ya no aparece en esta empresa')).toBeTruthy()
    expect(definir(d).disabled).toBe(true)
    await waitFor(() => expect(llamadas(f, listaUrl, 'GET').length).toBeGreaterThan(1))
  })

  it('503 con Retry-After: sin reintento automático; el botón espera y luego se vuelve a escribir', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePost((_, n) =>
        n === 1
          ? json(503, { error: { code: 'servicio_no_disponible', message: 'x', request_id: '00000000-0000-4000-8000-00000000e001' } }, { 'Retry-After': '2' })
          : sinCuerpo(),
      ),
    })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    expect(await within(d).findByText('El servicio no está disponible en este momento')).toBeTruthy()
    expect(d.textContent).toContain('No se cambió la contraseña. Espera 2 segundos, escríbela de nuevo e intenta otra vez.')
    expect(campoClave(d).value).toBe('')
    const espera = within(d).getByRole('button', { name: /Espera \d+ s/ }) as HTMLButtonElement
    expect(espera.disabled).toBe(true)
    // Un solo POST: nadie lo repite solo.
    await new Promise((r) => setTimeout(r, 300))
    expect(llamadas(f, /\/contrasena$/, 'POST')).toHaveLength(1)
    // Pasada la espera, se reintenta a mano.
    await waitFor(() => expect(definir(d).disabled).toBe(false), { timeout: 4000 })
    await definirYConfirmar(d)
    await waitFor(() => expect(llamadas(f, /\/contrasena$/, 'POST')).toHaveLength(2))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('429: dice cuánto esperar y no reintenta solo', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePost(() =>
        json(429, { error: { code: 'demasiados_intentos', message: 'x', request_id: '00000000-0000-4000-8000-00000000e001' } }, { 'Retry-After': '60' }),
      ),
    })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    expect(await within(d).findByText('Hiciste varias acciones seguidas')).toBeTruthy()
    expect(d.textContent).toContain('Espera 1 minuto')
    expect(within(d).getByRole('button', { name: /Espera \d+ s/ })).toBeTruthy()
    await new Promise((r) => setTimeout(r, 200))
    expect(llamadas(f, /\/contrasena$/, 'POST')).toHaveLength(1)
    sinRastro(CLAVE)
  })

  it('sin conexión: lo dice y los campos quedan vacíos', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, { extra: pidePost(() => Promise.reject(new TypeError('red'))) })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    expect(await within(d).findByText('Sin conexión con el servidor')).toBeTruthy()
    expect(campoClave(d).value).toBe('')
    sinRastro(CLAVE)
  })
})

describe('la contraseña no queda en la caché ni en los registros (R58; security-reviewer)', () => {
  function montar(respuesta: () => Response | Promise<Response>) {
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    cliente.setQueryData(CLAVE_SESION_PLATAFORMA, SESION)
    const f = vi.fn(async (entrada: RequestInfo | URL) => {
      if (String(entrada).endsWith('/contrasena')) return respuesta()
      return new Promise<Response>(() => {})
    })
    vi.stubGlobal('fetch', f)
    const consola = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m))
    const onCerrar = vi.fn()
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter>
          <RestablecerContrasena empresa={{ id: ACTIVA, nombre: 'Biotecnología Dental' }} usuario={LUIS} onCerrar={onCerrar} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    return { cliente, f, consola, onCerrar }
  }

  function cachesLimpias(cliente: QueryClient, consola: ReturnType<typeof vi.spyOn>[]) {
    expect(cliente.getMutationCache().getAll()).toHaveLength(0)
    const consultas = cliente.getQueryCache().getAll().map((q) => ({ clave: q.queryKey, datos: q.state.data, error: String(q.state.error) }))
    expect(JSON.stringify(consultas)).not.toContain(CLAVE)
    for (const espia of consola) expect(JSON.stringify(espia.mock.calls)).not.toContain(CLAVE)
  }

  it('tras el éxito', async () => {
    const { cliente, f, consola, onCerrar } = montar(sinCuerpo)
    const d = await screen.findByRole('dialog')
    await definirYConfirmar(d)
    await waitFor(() => expect(onCerrar).toHaveBeenCalled())
    expect(f).toHaveBeenCalledTimes(1)
    cachesLimpias(cliente, consola)
  })

  it('tras un error', async () => {
    const { cliente, consola } = montar(() => errorApi(422, 'contrasena_comun'))
    const d = await screen.findByRole('dialog')
    await definirYConfirmar(d)
    await within(d).findByText(/muy común/)
    cachesLimpias(cliente, consola)
    sinRastro(CLAVE)
  })
})

describe('errorDeContrasena', () => {
  it('toma el campo del código aunque el servidor no lo mande', () => {
    expect(errorDeContrasena(new ErrorApi(422, 'contrasenas_distintas', 'x'), 'E')).toMatchObject({ tipo: 'campo', campo: 'password_confirmacion' })
    expect(errorDeContrasena(new ErrorApi(422, 'contrasena_corta', 'x'), 'E')).toMatchObject({ tipo: 'campo', campo: 'password' })
  })

  it('400 y 413 no ofrecen reintentar; un error desconocido sí', () => {
    expect(errorDeContrasena(new ErrorApi(400, 'solicitud_invalida', 'x'), 'E')).toMatchObject({ tipo: 'general', bloquea: true })
    expect(errorDeContrasena(new Error('x'), 'E')).toMatchObject({ tipo: 'general', bloquea: false })
  })
})

describe('sesión que no se recupera (401; spec 017, C1b/T16; security-reviewer)', () => {
  function montar401(refresh: () => Response) {
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    cliente.setQueryData(CLAVE_SESION_PLATAFORMA, SESION)
    const f = vi.fn(async (entrada: RequestInfo | URL) => {
      const url = String(entrada)
      if (url.endsWith('/contrasena')) return errorApi(401, 'no_autenticado')
      if (url === '/api/plataforma/auth/refresh') return refresh()
      return new Promise<Response>(() => {})
    })
    vi.stubGlobal('fetch', f)
    const consola = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) => vi.spyOn(console, m))
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter>
          <RestablecerContrasena empresa={{ id: ACTIVA, nombre: 'Biotecnología Dental' }} usuario={LUIS} onCerrar={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    return { cliente, f, consola }
  }

  const posts = (f: ReturnType<typeof vi.fn>) => f.mock.calls.filter(([e]) => String(e).endsWith('/contrasena'))

  it('el reintento con token renovado vuelve a dar 401: avisa, vacía los campos y olvida la sesión', async () => {
    const { cliente, f, consola } = montar401(() => json(200, { ...SESION, access_token: 'jwt.renovado' }))
    const d = await screen.findByRole('dialog')
    await definirYConfirmar(d)
    expect(await within(d).findByText('Tu sesión expiró; entra de nuevo')).toBeTruthy()
    expect(d.textContent).toContain('No se cambió la contraseña')
    expect(posts(f)).toHaveLength(2)
    // La sesión queda anónima: el guard lleva a /plataforma/entrar.
    expect(cliente.getQueryData(CLAVE_SESION_PLATAFORMA)).toBeNull()
    expect(campoClave(d).value).toBe('')
    expect(campoConfirmar(d).value).toBe('')
    sinRastro(CLAVE)
    for (const espia of consola) expect(JSON.stringify(espia.mock.calls)).not.toContain(CLAVE)
  })

  it('renovación fallida: un solo POST con la contraseña, aviso y sin rastro', async () => {
    const { cliente, f } = montar401(() => errorApi(401, 'no_autenticado'))
    const d = await screen.findByRole('dialog')
    await definirYConfirmar(d)
    expect(await within(d).findByText('Tu sesión expiró; entra de nuevo')).toBeTruthy()
    expect(posts(f)).toHaveLength(1)
    const conClave = (f.mock.calls as unknown as [unknown, RequestInit | undefined][]).filter(([, init]) => String((init as RequestInit | undefined)?.body ?? '').includes(CLAVE))
    expect(conClave).toHaveLength(1)
    expect(cliente.getQueryData(CLAVE_SESION_PLATAFORMA)).toBeNull()
    expect(campoClave(d).value).toBe('')
    sinRastro(CLAVE)
  })

  it('en la consola, el segundo 401 lleva a /plataforma/entrar', async () => {
    const { f, router } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePost(() => errorApi(401, 'no_autenticado')),
    })
    const d = await abrirDialogo('Luis Pérez')
    await definirYConfirmar(d)
    await waitFor(() => expect(router.state.location.pathname).toBe('/plataforma/entrar'))
    expect(llamadas(f, rutaClave(LUIS.id), 'POST')).toHaveLength(2)
    sinRastro(CLAVE)
  })
})

describe('gestores de contraseñas (security-reviewer)', () => {
  it('los dos campos de la contraseña temporal piden a los gestores no guardarla', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const d = await abrirDialogo('Luis Pérez')
    for (const campo of [campoClave(d), campoConfirmar(d)]) {
      expect(campo.getAttribute('data-1p-ignore')).toBe('true')
      expect(campo.getAttribute('data-bwignore')).toBe('true')
      expect(campo.getAttribute('data-lpignore')).toBe('true')
      expect(campo.getAttribute('data-form-type')).toBe('other')
      expect(campo.getAttribute('autocomplete')).toBe('new-password')
    }
  })
})
