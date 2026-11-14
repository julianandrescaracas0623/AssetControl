import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ErrorApi, pedir, TIEMPO_MAXIMO_MS } from './cliente'

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
    }
    expect(typeof nunca).toBe('function')
  })
})
