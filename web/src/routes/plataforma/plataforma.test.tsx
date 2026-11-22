import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Esquemas } from '@/lib/api/cliente'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json, sesionDe } from '@/test/sesion'

// Spec 017, T8 (R11–R14, R38; A1, A14; CU-01, CU-02, CU-09): login, guard, shell y
// registro de módulos de la consola de plataforma, montando las rutas reales.

type SesionPlataforma = Esquemas['SesionPlataforma']
type Modulo = Esquemas['ModuloPlataforma']

const DEV = { id: '00000000-0000-4000-8000-0000000000f1', email: 'dev@ejemplo.test', nombre: 'Daniela Ríos' }
const OTRA = { id: '00000000-0000-4000-8000-0000000000f2', email: 'otra@ejemplo.test', nombre: 'Óscar Lima' }

function sesionPlataforma(desarrollador = DEV, token = 'jwt.plataforma'): SesionPlataforma {
  return { access_token: token, token_type: 'Bearer', expires_in: 600, desarrollador }
}

const PRUEBA: Modulo = { id: 'prueba', titulo: 'Módulo de prueba', orden: 90 }

type Opciones = {
  /** Sesión que devuelve el refresh; `null` = 401; `'apagada'` = 404 (consola apagada). */
  sesion?: SesionPlataforma | null | 'apagada'
  modulos?: Modulo[]
  extra?: (url: string, init: RequestInit) => Response | Promise<Response> | undefined
}

function simular({ sesion = sesionPlataforma(), modulos = [PRUEBA], extra }: Opciones = {}) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/plataforma/auth/refresh') {
      if (sesion === 'apagada') return errorApi(404, 'no_encontrado', 'El recurso no existe.')
      return sesion ? json(200, sesion) : errorApi(401, 'no_autenticado')
    }
    if (url === '/api/plataforma/auth/logout') return new Response(null, { status: 204 })
    if (url === '/api/plataforma/modulos') return json(200, { modulos })
    // Lado tenant (para las pruebas de separación).
    if (url === '/api/auth/refresh') return json(200, sesionDe('admin'))
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', f)
  return f
}

function abrir(path: string, opciones?: Opciones, state?: unknown) {
  const f = simular(opciones)
  const router = createMemoryRouter(routes, { initialEntries: [{ pathname: path, state }] })
  render(<RouterProvider router={router} />)
  return { router, f }
}

const llamadas = (f: ReturnType<typeof simular>, url: string) => f.mock.calls.filter(([e]) => String(e) === url)
const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name })

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('guard de plataforma', () => {
  it.each(['/plataforma', '/plataforma/prueba', '/plataforma/empresas'])('sin sesión %s lleva a /plataforma/entrar', async (path) => {
    const { router } = abrir(path, { sesion: null })
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/plataforma/entrar')
    expect(router.state.location.state).toEqual({ desde: path })
  })

  it('mientras renueva muestra «Comprobando la sesión»', async () => {
    abrir('/plataforma', {
      extra: (url) => (url === '/api/plataforma/auth/refresh' ? new Promise<Response>(() => {}) : undefined),
    })
    expect(await screen.findByRole('status', { name: 'Comprobando la sesión' })).toBeTruthy()
  })

  it('con la consola apagada (404) muestra «No disponible» y no ofrece login (A1)', async () => {
    const { f } = abrir('/plataforma/prueba', { sesion: 'apagada' })
    await h1('No disponible')
    expect(screen.queryByLabelText('Contraseña')).toBeNull()
    expect(llamadas(f, '/api/plataforma/modulos')).toHaveLength(0)
  })

  it('/plataforma/entrar con la consola apagada también dice «No disponible»', async () => {
    abrir('/plataforma/entrar', { sesion: 'apagada' })
    await h1('No disponible')
    expect(screen.getByText('AssetControl').parentElement?.textContent).toBe('AssetControl Dev')
    expect(screen.queryByText('Plataforma')).toBeNull()
  })

  it('si la API no responde ofrece reintentar', async () => {
    let intentos = 0
    abrir('/plataforma', {
      extra: (url) => {
        if (url !== '/api/plataforma/auth/refresh') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(200, sesionPlataforma())
      },
    })
    await h1('No se pudo conectar')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await h1('Módulo de prueba')
  })

  it('el refresh de plataforma lleva CSRF y la cookie del mismo origen', async () => {
    const { f } = abrir('/plataforma')
    await h1('Módulo de prueba')
    const [, init] = llamadas(f, '/api/plataforma/auth/refresh')[0]
    expect(init?.method).toBe('POST')
    expect(new Headers(init?.headers).get('X-AssetControl-CSRF')).toBe('1')
    expect(init?.credentials).toBe('same-origin')
  })

  it('las páginas de la consola piden no indexarse', async () => {
    abrir('/plataforma/entrar', { sesion: null })
    await h1('Iniciar sesión')
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex, nofollow')
  })
})

describe('Entrar (CU-01)', () => {
  it('muestra la marca «AssetControl Dev», correo y contraseña oculta', async () => {
    abrir('/plataforma/entrar', { sesion: null })
    await h1('Iniciar sesión')
    expect(screen.getByText('AssetControl').parentElement?.textContent).toBe('AssetControl Dev')
    expect(screen.queryByText('Plataforma')).toBeNull()
    expect(screen.queryByText(/solo para desarrolladores/)).toBeNull()
    const correo = screen.getByLabelText('Correo') as HTMLInputElement
    const clave = screen.getByLabelText('Contraseña') as HTMLInputElement
    expect(correo.type).toBe('email')
    expect(correo.autocomplete).toBe('username')
    // MEMORY: el `Campo` del kit descartaba `type`; aquí debe quedar oculta.
    expect(clave.type).toBe('password')
    expect(clave.autocomplete).toBe('current-password')
  })

  it('el formulario es POST y el envío no navega (D20: la contraseña nunca va en la URL)', async () => {
    abrir('/plataforma/entrar', { sesion: null })
    await h1('Iniciar sesión')
    const form = screen.getByRole('button', { name: 'Entrar' }).closest('form')!
    expect(form.getAttribute('method')).toBe('post')
    // `fireEvent.submit` devuelve false si el manejador llamó a preventDefault.
    expect(fireEvent.submit(form)).toBe(false)
  })

  it('entra, deja el botón ocupado mientras envía y lleva a donde iba', async () => {
    let soltar: (r: Response) => void = () => {}
    const { router, f } = abrir(
      '/plataforma/entrar',
      {
        sesion: null,
        extra: (url) =>
          url === '/api/plataforma/auth/login' ? new Promise<Response>((r) => (soltar = r)) : undefined,
      },
      { desde: '/plataforma/prueba' },
    )
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'dev@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'una-clave-larga-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    const boton = await screen.findByRole('button', { name: /Entrando/ })
    expect((boton as HTMLButtonElement).disabled).toBe(true)
    const [, init] = llamadas(f, '/api/plataforma/auth/login')[0]
    expect(JSON.parse(String(init?.body))).toEqual({ email: 'dev@ejemplo.test', password: 'una-clave-larga-1234' })
    soltar(json(200, sesionPlataforma()))
    await h1('Módulo de prueba')
    expect(router.state.location.pathname).toBe('/plataforma/prueba')
  })

  it('un `desde` fuera de la consola no se sigue (sin redirección abierta)', async () => {
    const { router } = abrir(
      '/plataforma/entrar',
      { sesion: null, extra: (url) => (url === '/api/plataforma/auth/login' ? json(200, sesionPlataforma()) : undefined) },
      { desde: '/admin/usuarios' },
    )
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'dev@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await h1('Módulo de prueba')
    expect(router.state.location.pathname).toBe('/plataforma/prueba')
  })

  it.each([
    [errorApi(401, 'credenciales_invalidas', 'Texto del servidor'), 'Correo o contraseña incorrectos.'],
    [errorApi(429, 'demasiadas_solicitudes'), 'Demasiados intentos, espera unos minutos e intenta de nuevo.'],
    [errorApi(503, 'servicio_no_disponible'), 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.'],
  ])('muestra el error del login en español (%#)', async (respuesta, mensaje) => {
    abrir('/plataforma/entrar', {
      sesion: null,
      extra: (url) => (url === '/api/plataforma/auth/login' ? respuesta.clone() : undefined),
    })
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'dev@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'mala' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText(mensaje)).toBeTruthy()
    // El correo se conserva; la contraseña se borra para reescribirla.
    expect((screen.getByLabelText('Correo') as HTMLInputElement).value).toBe('dev@ejemplo.test')
    expect((screen.getByLabelText('Contraseña') as HTMLInputElement).value).toBe('')
  })

  it('un 429 con Retry-After dice cuánto esperar', async () => {
    abrir('/plataforma/entrar', {
      sesion: null,
      extra: (url) =>
        url === '/api/plataforma/auth/login'
          ? json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '900' })
          : undefined,
    })
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'dev@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('Demasiados intentos, espera 15 minutos e intenta de nuevo.')).toBeTruthy()
  })

  it('un 404 al entrar (consola apagada después de abrir) muestra «No disponible»', async () => {
    abrir('/plataforma/entrar', {
      sesion: null,
      extra: (url) => (url === '/api/plataforma/auth/login' ? errorApi(404, 'no_encontrado') : undefined),
    })
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'dev@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await h1('No disponible')
  })

  it('con sesión vigente, /plataforma/entrar lleva al panel', async () => {
    const { router } = abrir('/plataforma/entrar')
    await h1('Módulo de prueba')
    expect(router.state.location.pathname).toBe('/plataforma/prueba')
  })

  it('la contraseña no queda en el almacenamiento del navegador', async () => {
    abrir('/plataforma/entrar', {
      sesion: null,
      extra: (url) => (url === '/api/plataforma/auth/login' ? json(200, sesionPlataforma()) : undefined),
    })
    await h1('Iniciar sesión')
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'dev@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'secreto-de-prueba-123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await h1('Módulo de prueba')
    const guardado = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie
    expect(guardado).not.toContain('secreto-de-prueba-123')
    expect(guardado).not.toContain('jwt.plataforma')
  })
})

describe('shell de plataforma (CU-02)', () => {
  it('muestra la marca, el nombre, «Cerrar sesión» y la navegación del registro', async () => {
    abrir('/plataforma/prueba')
    await h1('Módulo de prueba')
    const barra = screen.getByRole('navigation', { name: 'Módulos de la consola' })
    const enlace = within(barra).getByRole('link', { name: 'Módulo de prueba' })
    expect(enlace.getAttribute('href')).toBe('/plataforma/prueba')
    expect(enlace.getAttribute('aria-current')).toBe('page')
    expect(screen.getByText('AssetControl Dev')).toBeTruthy()
    expect(screen.queryByText('Solo desarrolladores')).toBeNull()
    expect(screen.queryByText('Plataforma')).toBeNull()
    expect(screen.getByText('Daniela Ríos')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeTruthy()
  })

  it('/plataforma abre el primer módulo visible', async () => {
    const { router } = abrir('/plataforma')
    await h1('Módulo de prueba')
    expect(router.state.location.pathname).toBe('/plataforma/prueba')
  })

  it('no muestra módulos del servidor que la web no conoce ni los que el servidor no declara', async () => {
    abrir('/plataforma', { modulos: [{ id: 'desconocido', titulo: 'Desconocido', orden: 1 }] })
    await screen.findByText('Sin módulos disponibles')
    const barra = screen.getByRole('navigation', { name: 'Módulos de la consola' })
    expect(within(barra).queryAllByRole('link')).toHaveLength(0)
    expect(screen.queryByText('Desconocido')).toBeNull()
    expect(screen.queryByText('Módulo de prueba')).toBeNull()
  })

  it('el módulo del registro que el servidor no habilita muestra «No disponible» dentro del shell', async () => {
    abrir('/plataforma/prueba', { modulos: [] })
    await h1('No disponible')
    expect(screen.getByRole('navigation', { name: 'Módulos de la consola' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Volver al inicio de la consola' }).getAttribute('href')).toBe('/plataforma')
  })

  it('una ruta de módulo que nadie registra muestra «No disponible»', async () => {
    abrir('/plataforma/no-existe/algo')
    await h1('No disponible')
  })

  it('el módulo carga su propia subruta', async () => {
    abrir('/plataforma/prueba/detalle')
    expect(await screen.findByText('Subruta del módulo de prueba')).toBeTruthy()
  })

  it('si no se pueden leer los módulos ofrece reintentar', async () => {
    let intentos = 0
    const { f } = abrir('/plataforma/prueba', {
      extra: (url) => {
        if (url !== '/api/plataforma/modulos') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(400, 'solicitud_invalida') : json(200, { modulos: [PRUEBA] })
      },
    })
    expect(await screen.findByText('No se pudieron cargar los módulos')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await h1('Módulo de prueba')
    expect(llamadas(f, '/api/plataforma/modulos')).toHaveLength(2)
  })

  it('los módulos se piden con el token de plataforma', async () => {
    const { f } = abrir('/plataforma')
    await h1('Módulo de prueba')
    const [, init] = llamadas(f, '/api/plataforma/modulos')[0]
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer jwt.plataforma')
  })

  it('un 401 en los módulos renueva una vez y repite con el token nuevo', async () => {
    let refrescos = 0
    const { f } = abrir('/plataforma', {
      extra: (url, init) => {
        if (url === '/api/plataforma/auth/refresh') {
          refrescos += 1
          return json(200, sesionPlataforma(DEV, `jwt.plataforma.${refrescos}`))
        }
        if (url === '/api/plataforma/modulos') {
          const auth = new Headers(init.headers).get('Authorization')
          return auth === 'Bearer jwt.plataforma.1' ? errorApi(401, 'no_autenticado') : json(200, { modulos: [PRUEBA] })
        }
        return undefined
      },
    })
    await h1('Módulo de prueba')
    expect(refrescos).toBe(2)
    const tokens = llamadas(f, '/api/plataforma/modulos').map(([, i]) => new Headers(i?.headers).get('Authorization'))
    expect(tokens).toEqual(['Bearer jwt.plataforma.1', 'Bearer jwt.plataforma.2'])
  })

  it('si la renovación también falla, vuelve a /plataforma/entrar', async () => {
    let refrescos = 0
    const { router } = abrir('/plataforma', {
      extra: (url) => {
        if (url === '/api/plataforma/auth/refresh') {
          refrescos += 1
          return refrescos === 1 ? json(200, sesionPlataforma()) : errorApi(401, 'no_autenticado')
        }
        if (url === '/api/plataforma/modulos') return errorApi(401, 'no_autenticado')
        return undefined
      },
    })
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/plataforma/entrar')
  })

  it('a 375 px la navegación va en un menú', async () => {
    simularAncho({ movil: true })
    abrir('/plataforma/prueba')
    await h1('Módulo de prueba')
    expect(screen.queryByRole('navigation', { name: 'Módulos de la consola' })).toBeNull()
    const boton = screen.getByRole('button', { name: 'Menú' })
    fireEvent.click(boton)
    const dialogo = await screen.findByRole('dialog', { name: 'Menú' })
    const nav = within(dialogo).getByRole('navigation', { name: 'Módulos de la consola' })
    expect(within(nav).getByRole('link', { name: 'Módulo de prueba' })).toBeTruthy()
    expect(within(dialogo).getByText('Daniela Ríos')).toBeTruthy()
    expect(within(dialogo).getByRole('button', { name: 'Cerrar sesión' })).toBeTruthy()
  })

  it('a 375 px elegir un módulo cierra el menú', async () => {
    simularAncho({ movil: true })
    abrir('/plataforma/prueba')
    await h1('Módulo de prueba')
    fireEvent.click(screen.getByRole('button', { name: 'Menú' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Menú' })
    fireEvent.click(within(dialogo).getByRole('link', { name: 'Módulo de prueba' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Menú' })).toBeNull())
  })
})

describe('cerrar sesión de plataforma', () => {
  it('cierra en el servidor con CSRF, vacía la caché y vuelve a entrar', async () => {
    let sesion: SesionPlataforma | null = sesionPlataforma()
    let modulos: Modulo[] = [PRUEBA]
    const { router, f } = abrir('/plataforma', {
      extra: (url) => {
        if (url === '/api/plataforma/auth/refresh') return sesion ? json(200, sesion) : errorApi(401, 'no_autenticado')
        if (url === '/api/plataforma/auth/login') return json(200, sesionPlataforma(OTRA, 'jwt.otra'))
        if (url === '/api/plataforma/modulos') return json(200, { modulos })
        return undefined
      },
    })
    await h1('Módulo de prueba')
    sesion = null
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await h1('Iniciar sesión')
    expect(router.state.location.pathname).toBe('/plataforma/entrar')
    const [, init] = llamadas(f, '/api/plataforma/auth/logout')[0]
    expect(new Headers(init?.headers).get('X-AssetControl-CSRF')).toBe('1')

    // Otra persona entra en la misma pestaña: los módulos se piden de nuevo con su token.
    modulos = []
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'otra@ejemplo.test' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    // D24: bajo carga el segundo login y los módulos pueden pasar de los 3 s globales (setup.ts);
    // 8 s, por debajo del testTimeout de 15 s: un fallo real sigue fallando.
    await screen.findByText('Sin módulos disponibles', {}, { timeout: 8000 })
    expect(screen.getByText('Óscar Lima')).toBeTruthy()
    const ultimas = llamadas(f, '/api/plataforma/modulos')
    expect(new Headers(ultimas[ultimas.length - 1][1]?.headers).get('Authorization')).toBe('Bearer jwt.otra')
  })

  it('si el servidor no cierra, avisa y la sesión sigue', async () => {
    abrir('/plataforma', {
      extra: (url) => (url === '/api/plataforma/auth/logout' ? errorApi(503, 'servicio_no_disponible') : undefined),
    })
    await h1('Módulo de prueba')
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByText('No se pudo cerrar la sesión. Intenta de nuevo.')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: 'Módulo de prueba' })).toBeTruthy()
  })
})

describe('separación de la sesión del tenant', () => {
  it('la consola no toca la sesión ni el token de la clínica', async () => {
    const { f } = abrir('/plataforma/prueba')
    await h1('Módulo de prueba')
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(0)
    for (const [entrada, init] of f.mock.calls) {
      const url = String(entrada)
      expect(url.startsWith('/api/plataforma/')).toBe(true)
      expect(new Headers(init?.headers).get('Authorization') ?? '').not.toContain('jwt.admin')
    }
  })

  it('la app de la clínica no toca la sesión de plataforma', async () => {
    const f = simular()
    const router = createMemoryRouter(routes, { initialEntries: ['/admin/usuarios'] })
    render(<RouterProvider router={router} />)
    await waitFor(() => expect(llamadas(f, '/api/auth/refresh')).toHaveLength(1))
    expect(f.mock.calls.some(([e]) => String(e).startsWith('/api/plataforma/'))).toBe(false)
    for (const [, init] of f.mock.calls) {
      expect(new Headers(init?.headers).get('Authorization') ?? '').not.toContain('jwt.plataforma')
    }
  })
})
