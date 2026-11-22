import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ErrorApi, nombreDeArchivo, pedir, TIEMPO_MAXIMO_MS } from './cliente'
import { apiPlataforma } from './plataforma'

// Spec 002b, T2 (plan §3): cliente tipado con el contrato. Sin red real.

function responder(status: number, cuerpo?: unknown, tipo = 'application/json') {
  const fetchSimulado = vi.fn(async () =>
    cuerpo === undefined
      ? new Response(null, { status })
      : new Response(typeof cuerpo === 'string' ? cuerpo : JSON.stringify(cuerpo), {
          status,
          headers: { 'Content-Type': tipo },
        }),
  )
  vi.stubGlobal('fetch', fetchSimulado)
  return fetchSimulado
}

function peticion(fetchSimulado: ReturnType<typeof responder>) {
  const [url, init] = fetchSimulado.mock.calls[0] as unknown as [string, RequestInit]
  return { url, init, headers: new Headers(init.headers) }
}

const SESION = {
  access_token: 'jwt.sintetico',
  token_type: 'Bearer',
  expires_in: 900,
  usuario: { id: '00000000-0000-4000-8000-000000000001', email: 'ana@ejemplo.test', nombre: 'Ana' },
  tenant: { id: '00000000-0000-4000-8000-0000000000a1', nombre: 'Clínica Demo' },
  rol: 'admin',
}

afterEach(() => vi.unstubAllGlobals())

describe('pedir', () => {
  it('llama a /api con JSON, mismo origen y sin cabeceras de sesión por defecto', async () => {
    const f = responder(200, SESION)
    const sesion = await api.login({ email: 'ana@ejemplo.test', password: 'secreto-sintetico' })
    expect(sesion.rol).toBe('admin')
    const { url, init, headers } = peticion(f)
    expect(url).toBe('/api/auth/login')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.has('Authorization')).toBe(false)
    expect(headers.has('X-AssetControl-CSRF')).toBe(false)
    expect(JSON.parse(String(init.body))).toEqual({ email: 'ana@ejemplo.test', password: 'secreto-sintetico' })
  })

  it('manda el token como Bearer y sin cuerpo en un GET', async () => {
    const f = responder(200, { usuario: SESION.usuario, tenant: SESION.tenant, rol: 'contador' })
    await api.me('jwt.sintetico')
    const { url, init, headers } = peticion(f)
    expect(url).toBe('/api/auth/me')
    expect(init.method).toBe('GET')
    expect(init.body).toBeUndefined()
    expect(headers.get('Authorization')).toBe('Bearer jwt.sintetico')
    expect(headers.has('Content-Type')).toBe(false)
  })

  it('refresh y logout llevan la cabecera CSRF; logout 204 devuelve undefined', async () => {
    let f = responder(200, SESION)
    await api.refresh()
    expect(peticion(f).headers.get('X-AssetControl-CSRF')).toBe('1')
    expect(peticion(f).url).toBe('/api/auth/refresh')

    f = responder(204)
    await expect(api.logout()).resolves.toBeUndefined()
    expect(peticion(f).headers.get('X-AssetControl-CSRF')).toBe('1')
  })

  it('las invitaciones usan sus rutas y cuerpos', async () => {
    let f = responder(201, { invitacion: {}, enlace: '/invitacion#tok' })
    await api.crearInvitacion('jwt.sintetico', { email: 'nuevo@ejemplo.test', rol: 'contador' })
    expect(peticion(f).url).toBe('/api/invitaciones')
    expect(peticion(f).headers.get('Authorization')).toBe('Bearer jwt.sintetico')

    f = responder(200, { vigente: true })
    await expect(api.validarInvitacion('tok')).resolves.toEqual({ vigente: true })
    expect(JSON.parse(String(peticion(f).init.body))).toEqual({ token: 'tok' })

    f = responder(201, SESION)
    await api.aceptarInvitacion({ token: 'tok', nombre: 'Ana', password: 'secreto-sintetico' })
    expect(peticion(f).url).toBe('/api/invitaciones/aceptar')
  })
})

describe('catálogo (spec 003)', () => {
  it('rellena el id de la ruta y usa PATCH', async () => {
    const f = responder(200, { ubicacion: {} })
    await api.actualizarUbicacion('jwt.sintetico', 'a b/c', { activa: false })
    const { url, init, headers } = peticion(f)
    expect(url).toBe('/api/ubicaciones/a%20b%2Fc')
    expect(init.method).toBe('PATCH')
    expect(headers.get('Authorization')).toBe('Bearer jwt.sintetico')
    expect(JSON.parse(String(init.body))).toEqual({ activa: false })
  })

  it('cargar sugeridas es un POST sin cuerpo', async () => {
    const f = responder(200, { categorias: [], creadas: 0 })
    await api.cargarCategoriasSugeridas('jwt.sintetico')
    expect(peticion(f).url).toBe('/api/categorias/sugeridas')
    expect(peticion(f).init.body).toBeUndefined()
  })

  it('sin el parámetro de ruta falla antes de llamar', async () => {
    const f = responder(200, {})
    await expect(pedir('patch', '/categorias/{id}', { cuerpo: { nombre: 'x' } })).rejects.toThrow(/id/)
    expect(f).not.toHaveBeenCalled()
  })
})

describe('errores', () => {
  it('un error de la API se vuelve ErrorApi con su código, mensaje y request_id', async () => {
    responder(401, {
      error: { code: 'credenciales_invalidas', message: 'Correo o contraseña incorrectos.', request_id: 'r-1' },
    })
    const error = await api.login({ email: 'a@b.c', password: 'x' }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ErrorApi)
    expect(error).toMatchObject({
      status: 401,
      code: 'credenciales_invalidas',
      message: 'Correo o contraseña incorrectos.',
      requestId: 'r-1',
    })
  })

  it('sin red es sin_conexion', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    await expect(api.refresh()).rejects.toMatchObject({ status: 0, code: 'sin_conexion' })
  })

  it('una respuesta que no es JSON de la API (proxy sin backend) es sin_conexion', async () => {
    responder(502, '<html>Bad gateway</html>', 'text/html')
    await expect(api.refresh()).rejects.toMatchObject({ status: 502, code: 'sin_conexion' })
  })

  it('un JSON con otra forma es error_interno', async () => {
    responder(500, { mensaje: 'otra cosa' })
    await expect(api.refresh()).rejects.toMatchObject({ status: 500, code: 'error_interno' })
  })

  it('si la API no responde a tiempo es sin_conexion', async () => {
    vi.useFakeTimers()
    try {
      vi.stubGlobal(
        'fetch',
        vi.fn(
          (_url: string, init: RequestInit) =>
            new Promise<Response>((_, rechazar) =>
              init.signal?.addEventListener('abort', () => rechazar(new DOMException('plazo', 'TimeoutError'))),
            ),
        ),
      )
      const promesa = api.refresh()
      const verificacion = expect(promesa).rejects.toMatchObject({ status: 0, code: 'sin_conexion' })
      await vi.advanceTimersByTimeAsync(TIEMPO_MAXIMO_MS + 1)
      await verificacion
    } finally {
      vi.useRealTimers()
    }
  })

  it('propaga la cancelación', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new DOMException('abortado', 'AbortError'))))
    const control = new AbortController()
    control.abort()
    await expect(pedir('post', '/auth/refresh', { csrf: true, signal: control.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
})

describe('recuperar contraseña (spec 014, T5)', () => {
  const TOKEN = 'a'.repeat(64)
  const error = (code: string, message: string) => ({ error: { code, message, request_id: 'r-9' } })

  it('solicitarRecuperacion: POST con CSRF, cuerpo JSON, mismo origen y sin sesión; 202 devuelve el mensaje', async () => {
    const f = responder(202, { mensaje: 'Si existe una cuenta, te enviamos un enlace.' })
    await expect(api.solicitarRecuperacion({ email: 'ana@ejemplo.test' })).resolves.toEqual({
      mensaje: 'Si existe una cuenta, te enviamos un enlace.',
    })
    const { url, init, headers } = peticion(f)
    expect(url).toBe('/api/auth/recuperar')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(headers.get('X-AssetControl-CSRF')).toBe('1')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.has('Authorization')).toBe(false)
    expect(JSON.parse(String(init.body))).toEqual({ email: 'ana@ejemplo.test' })
  })

  it('restablecerContrasena: POST con CSRF y el token solo en el cuerpo; 204 devuelve undefined', async () => {
    const f = responder(204)
    await expect(api.restablecerContrasena({ token: TOKEN, password: 'nueva-clave-sintetica' })).resolves.toBeUndefined()
    const { url, init, headers } = peticion(f)
    expect(url).toBe('/api/auth/restablecer')
    expect(url).not.toContain(TOKEN)
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(headers.get('X-AssetControl-CSRF')).toBe('1')
    expect(headers.has('Authorization')).toBe(false)
    expect(JSON.parse(String(init.body))).toEqual({ token: TOKEN, password: 'nueva-clave-sintetica' })
  })

  it('mapea enlace_invalido y contrasena_* a ErrorApi con su código y mensaje', async () => {
    responder(400, error('enlace_invalido', 'Enlace vencido o ya usado.'))
    await expect(api.restablecerContrasena({ token: TOKEN, password: 'x' })).rejects.toMatchObject({
      status: 400,
      code: 'enlace_invalido',
      message: 'Enlace vencido o ya usado.',
      requestId: 'r-9',
    })

    for (const code of ['contrasena_corta', 'contrasena_larga', 'contrasena_comun', 'contrasena_invalida']) {
      responder(400, error(code, 'La contraseña no cumple la política.'))
      await expect(api.restablecerContrasena({ token: TOKEN, password: 'x' })).rejects.toMatchObject({ status: 400, code })
    }
  })

  it('429 trae los segundos de Retry-After; sin la cabecera queda undefined', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify(error('demasiadas_solicitudes', 'Demasiados intentos.')), {
            status: 429,
            headers: { 'Content-Type': 'application/json', 'Retry-After': '120' },
          }),
      ),
    )
    const conCabecera = await api.solicitarRecuperacion({ email: 'a@b.c' }).catch((e: unknown) => e)
    expect(conCabecera).toBeInstanceOf(ErrorApi)
    expect(conCabecera).toMatchObject({ status: 429, code: 'demasiadas_solicitudes', reintentarEn: 120 })

    responder(429, error('demasiadas_solicitudes', 'Demasiados intentos.'))
    const sinCabecera = await api.restablecerContrasena({ token: TOKEN, password: 'x' }).catch((e: unknown) => e)
    expect(sinCabecera).toMatchObject({ status: 429, reintentarEn: undefined })
  })

  it('503 es servicio_no_disponible', async () => {
    responder(503, error('servicio_no_disponible', 'El servicio no está disponible.'))
    await expect(api.solicitarRecuperacion({ email: 'a@b.c' })).rejects.toMatchObject({
      status: 503,
      code: 'servicio_no_disponible',
    })
  })

  it('el token nunca se escribe en console (éxito ni error)', async () => {
    const espias = (['log', 'info', 'warn', 'error', 'debug'] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => {}),
    )
    try {
      responder(204)
      await api.restablecerContrasena({ token: TOKEN, password: 'nueva-clave-sintetica' })
      responder(400, error('enlace_invalido', 'Enlace vencido o ya usado.'))
      await api.restablecerContrasena({ token: TOKEN, password: 'nueva-clave-sintetica' }).catch(() => undefined)
      vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
      await api.restablecerContrasena({ token: TOKEN, password: 'nueva-clave-sintetica' }).catch(() => undefined)
      for (const espia of espias) expect(espia).not.toHaveBeenCalled()
    } finally {
      for (const espia of espias) espia.mockRestore()
    }
  })
})

describe('tipos (los comprueba npm run typecheck)', () => {
  it('rechaza rutas, métodos y cuerpos fuera del contrato', () => {
    const nunca = () => {
      // @ts-expect-error ruta que no existe en el contrato
      void pedir('get', '/no/existe')
      // @ts-expect-error /auth/login solo admite POST
      void pedir('get', '/auth/login')
      // @ts-expect-error falta password
      void api.login({ email: 'a@b.c' })
      // @ts-expect-error rol fuera de la lista cerrada
      void api.crearInvitacion('t', { email: 'a@b.c', rol: 'superadmin' })
      // @ts-expect-error restablecer exige token y password
      void api.restablecerContrasena({ password: 'x' })
    }
    expect(typeof nunca).toBe('function')
  })
})

describe('nombreDeArchivo (spec 009)', () => {
  it.each([
    [`attachment; filename="informe.xlsx"; filename*=UTF-8''informe-a%C3%B1o.xlsx`, 'informe-año.xlsx'],
    ['attachment; filename="informe-corte.pdf"', 'informe-corte.pdf'],
    [`attachment; filename="simple.pdf"; filename*=UTF-8''%E0%A4`, 'simple.pdf'],
    [null, 'informe.pdf'],
    ['attachment', 'informe.pdf'],
  ])('%s → %s', (cabecera, esperado) => expect(nombreDeArchivo(cabecera, 'informe.pdf')).toBe(esperado))
})

describe('exportarActivos (spec 015, T4)', () => {
  const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  const pedida = (f: ReturnType<typeof responder>) => peticion(f).url

  it('manda solo los filtros con valor, en la consulta', async () => {
    let f = responder(200, 'xlsx', XLSX)
    await api.exportarActivos('jwt.sintetico', { estado: 'en_reparacion' })
    expect(pedida(f)).toBe('/api/activos/exportar?estado=en_reparacion')
    expect(peticion(f).headers.get('Authorization')).toBe('Bearer jwt.sintetico')

    f = responder(200, 'xlsx', XLSX)
    await api.exportarActivos('jwt.sintetico', { q: 'silla & mesa', estado: undefined, ubicacion_id: '' as never })
    expect(pedida(f)).toBe('/api/activos/exportar?q=silla+%26+mesa')

    f = responder(200, 'xlsx', XLSX)
    await api.exportarActivos('jwt.sintetico', {})
    expect(pedida(f)).toBe('/api/activos/exportar')
  })

  it('no depende de URLSearchParams.size (navegadores sin esa propiedad)', async () => {
    const original = Object.getOwnPropertyDescriptor(URLSearchParams.prototype, 'size')
    Object.defineProperty(URLSearchParams.prototype, 'size', { configurable: true, get: () => undefined })
    try {
      const f = responder(200, 'xlsx', XLSX)
      await api.exportarActivos('jwt.sintetico', { q: 'silla', ubicacion_id: '00000000-0000-4000-8000-0000000000a4' })
      expect(pedida(f)).toBe('/api/activos/exportar?q=silla&ubicacion_id=00000000-0000-4000-8000-0000000000a4')
    } finally {
      if (original) Object.defineProperty(URLSearchParams.prototype, 'size', original)
      else delete (URLSearchParams.prototype as { size?: number }).size
    }
  })
})

describe('sin redirecciones solo al restablecer desde la consola (spec 017, C1b/T16; security-reviewer)', () => {
  it('restablecerContrasenaUsuario va con redirect: error', async () => {
    const f = responder(204)
    await apiPlataforma.restablecerContrasenaUsuario('jwt.sintetico', 'e1', 'u1', { password: 'Sintetica-Prueba-1', password_confirmacion: 'Sintetica-Prueba-1' })
    const { url, init } = peticion(f)
    expect(url).toBe('/api/plataforma/empresas/e1/usuarios/u1/contrasena')
    expect(init.redirect).toBe('error')
  })

  it('el resto de peticiones no fija redirect (sigue igual)', async () => {
    const f = responder(200, SESION)
    await api.login({ email: 'ana@ejemplo.test', password: 'secreto-sintetico' })
    await api.restablecerContrasena({ token: 't', password: 'x', password_confirmacion: 'x' } as never).catch(() => undefined)
    await apiPlataforma.listarEmpresas('jwt.sintetico').catch(() => undefined)
    for (const [, init] of f.mock.calls as unknown as [string, RequestInit][]) {
      expect('redirect' in init).toBe(false)
    }
  })

  it('una redirección es sin_conexion, sin reintento ni segundo POST', async () => {
    const f = vi.fn(async () => {
      throw new TypeError('Failed to fetch: redirect mode is set to error')
    })
    vi.stubGlobal('fetch', f)
    const error = await apiPlataforma
      .restablecerContrasenaUsuario('jwt.sintetico', 'e1', 'u1', { password: 'Sintetica-Prueba-1', password_confirmacion: 'Sintetica-Prueba-1' })
      .catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ErrorApi)
    expect((error as ErrorApi).code).toBe('sin_conexion')
    expect(JSON.stringify(error)).not.toContain('Sintetica-Prueba-1')
    expect((error as ErrorApi).message).not.toContain('Sintetica-Prueba-1')
    expect(f).toHaveBeenCalledTimes(1)
  })
})
