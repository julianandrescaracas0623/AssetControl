import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { act, render, renderHook, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { ErrorApi, type Sesion } from '@/lib/api/cliente'
import { CLAVE_SESION, destinoTrasLogin, etiquetaRol, iniciales, inicioDeRol, useApiAutenticada, useSesion } from '@/lib/sesion'
import { errorApi, json, llamadas, sesionDe, simularSesion } from '@/test/sesion'

// Spec 002b, T3 (R3, R5; plan §4): destino por rol y renovación ante 401.

describe('destino tras iniciar sesión', () => {
  it('cada rol va a su inicio (spec 020: el admin y el contador en computador, en /app)', () => {
    expect(inicioDeRol('admin')).toBe('/app')
    expect(inicioDeRol('admin', true)).toBe('/app')
    expect(inicioDeRol('contador')).toBe('/contar')
    expect(inicioDeRol('contador', true)).toBe('/app')
    expect(destinoTrasLogin('admin')).toBe('/app')
    expect(destinoTrasLogin('contador')).toBe('/contar')
  })

  it('vuelve a la ruta pedida solo si el rol puede abrirla', () => {
    expect(destinoTrasLogin('admin', '/admin/activos?estado=vacio')).toBe('/admin/activos?estado=vacio')
    expect(destinoTrasLogin('admin', '/app/activos?estado=vacio')).toBe('/app/activos?estado=vacio')
    expect(destinoTrasLogin('admin', '/contar/escanear')).toBe('/contar/escanear')
    expect(destinoTrasLogin('contador', '/contar/pendientes')).toBe('/contar/pendientes')
    // El marco es de los dos roles; las pantallas exclusivas las guarda RequiereAdmin.
    expect(destinoTrasLogin('contador', '/app/activos?q=silla')).toBe('/app/activos?q=silla')
    expect(destinoTrasLogin('contador', '/admin/usuarios')).toBe('/contar')
  })

  it('ignora destinos externos o desconocidos (sin redirección abierta)', () => {
    for (const desde of ['//malo.example/admin', '//malo.example/app', 'https://malo.example', '/administrar', '/apps', '/login', 42, null]) {
      expect(destinoTrasLogin('admin', desde)).toBe('/app')
    }
  })

  it('rechaza puntos, barras invertidas, puntos codificados y caracteres de control (spec 020, T3)', () => {
    const malos = [
      '/contar/../x',
      '/app/..//evil.com',
      '/app/../admin',
      '/contar\\x',
      '/\\evil',
      '/app/%2e%2e//x',
      '/app/%2E%2E/x',
      '/app/%2e./x',
      '/app/.%2E/x',
      '/app/activos\n//evil.com',
      '/app/activos\r',
      '/app/\tactivos',
      '/app/activos\u0000',
      '/app/activos\u007f',
      '//evil.com',
      '/app/activos?q=..\\x',
      '/app/.',
      '/app/./x',
      '/contar/./x',
    ]
    for (const desde of malos) {
      expect(destinoTrasLogin('admin', desde), JSON.stringify(desde)).toBe('/app')
      expect(destinoTrasLogin('contador', desde), JSON.stringify(desde)).toBe('/contar')
    }
  })

  it('los destinos internos válidos siguen igual (con query, hash y códigos codificados)', () => {
    expect(destinoTrasLogin('admin', '/app/activos/A%2FB?q=x#h')).toBe('/app/activos/A%2FB?q=x#h')
    expect(destinoTrasLogin('contador', '/contar/activo/000123')).toBe('/contar/activo/000123')
    expect(destinoTrasLogin('contador', '/app/sesiones/00000000-0000-4000-8000-0000000000e1')).toBe(
      '/app/sesiones/00000000-0000-4000-8000-0000000000e1',
    )
    expect(destinoTrasLogin('admin', '/app/activos?q=silla.roja')).toBe('/app/activos?q=silla.roja')
  })

  it('iniciales y etiqueta de rol', () => {
    expect(iniciales('Ana Torres')).toBe('AT')
    expect(iniciales('  luis  ')).toBe('L')
    expect(iniciales('María José de la Peña')).toBe('MP')
    expect(etiquetaRol('admin')).toBe('Admin')
    expect(etiquetaRol('contador')).toBe('Contador')
  })
})

function conSesion(token = 'jwt.viejo') {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  cliente.setQueryData(CLAVE_SESION, sesionDe('admin', token))
  const envoltura = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={cliente}>{children}</QueryClientProvider>
  )
  return { cliente, envoltura }
}

const NO_AUTENTICADO = new ErrorApi(401, 'no_autenticado', 'Debes iniciar sesión.')

// Datos de negocio de la persona A en la caché (lista de activos con precio).
const CLAVE_ACTIVOS_A = ['activos', 'lista', {}] as const
const ACTIVOS_DE_A = { activos: [{ codigo: '000123', nombre: 'Silla ergonómica', precio_compra: '389900.00' }] }

describe('useApiAutenticada', () => {
  it('pasa el token de la sesión', async () => {
    simularSesion('admin')
    const { envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    const llamar = vi.fn(async (token: string) => token)
    await expect(result.current(llamar)).resolves.toBe('jwt.viejo')
  })

  it('ante 401 renueva una sola vez para varias llamadas y repite con el token nuevo', async () => {
    const f = simularSesion(null, (url) => (url === '/api/auth/refresh' ? json(200, sesionDe('admin', 'jwt.nuevo')) : undefined))
    const { cliente, envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    const llamar = vi.fn(async (token: string) => {
      if (token === 'jwt.viejo') throw NO_AUTENTICADO
      return token
    })
    const resultados = await act(() => Promise.all([result.current(llamar), result.current(llamar)]))
    expect(resultados).toEqual(['jwt.nuevo', 'jwt.nuevo'])
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(1)
    expect(cliente.getQueryData(CLAVE_SESION)).toMatchObject({ access_token: 'jwt.nuevo' })
  })

  it('si la renovación responde 401 la sesión queda anónima y el error sube', async () => {
    simularSesion(null)
    const { cliente, envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    await expect(result.current(async () => Promise.reject(NO_AUTENTICADO))).rejects.toBe(NO_AUTENTICADO)
    await waitFor(() => expect(cliente.getQueryData(CLAVE_SESION)).toBeNull())
  })

  it('otros errores no renuevan', async () => {
    const f = simularSesion('admin')
    const { envoltura } = conSesion()
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    const prohibido = new ErrorApi(403, 'prohibido', 'No tienes permiso para esta acción.')
    await expect(result.current(async () => Promise.reject(prohibido))).rejects.toBe(prohibido)
    expect(llamadas(f, '/api/auth/refresh')).toHaveLength(0)
  })

  it('si la renovación responde 401 se vacían los datos de negocio de la caché', async () => {
    simularSesion(null)
    const { cliente, envoltura } = conSesion()
    cliente.setQueryData(CLAVE_ACTIVOS_A, ACTIVOS_DE_A)
    const { result } = renderHook(() => useApiAutenticada(), { wrapper: envoltura })
    await expect(result.current(async () => Promise.reject(NO_AUTENTICADO))).rejects.toBe(NO_AUTENTICADO)
    await waitFor(() => expect(cliente.getQueryData(CLAVE_SESION)).toBeNull())
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
  })

  it('sin sesión responde no_autenticado sin llamar', async () => {
    simularSesion(null, () => errorApi(500, 'error_interno'))
    const cliente = new QueryClient()
    const { result } = renderHook(() => useApiAutenticada(), {
      wrapper: ({ children }) => <QueryClientProvider client={cliente}>{children}</QueryClientProvider>,
    })
    const llamar = vi.fn()
    await expect(result.current(llamar)).rejects.toMatchObject({ code: 'no_autenticado' })
    expect(llamar).not.toHaveBeenCalled()
  })
})

// Spec 020, T3 (endurecimiento): la caché de TanStack Query no pasa de una persona a otra
// en la misma pestaña. Si la sesión de A caduca (renovación 401) y B inicia sesión, o si
// llega una sesión de otro usuario u otra clínica, B no ve nada de lo que A tenía en caché.
describe('caché entre personas en la misma pestaña', () => {
  const OTRO_TENANT = { id: '00000000-0000-4000-8000-0000000000d2', nombre: 'Otra Clínica' }

  function montar(previa: Sesion | null) {
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    cliente.setQueryData(CLAVE_SESION, previa)
    cliente.setQueryData(CLAVE_ACTIVOS_A, ACTIVOS_DE_A)
    const envoltura = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={cliente}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
    const { result } = renderHook(() => ({ sesion: useSesion(), conToken: useApiAutenticada() }), { wrapper: envoltura })
    return { cliente, result }
  }

  it('A caduca (renovación 401) y B, contador, inicia sesión: B no ve los activos con precio de A', async () => {
    simularSesion(null)
    const { cliente, result } = montar(sesionDe('admin'))
    await expect(result.current.conToken(async () => Promise.reject(NO_AUTENTICADO))).rejects.toBe(NO_AUTENTICADO)
    await waitFor(() => expect(result.current.sesion.estado).toBe('anonima'))
    act(() => result.current.sesion.iniciar(sesionDe('contador')))
    await waitFor(() => expect(result.current.sesion.sesion?.rol).toBe('contador'))
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
    expect(cliente.getQueryCache().getAll().map((q) => q.queryKey)).toEqual([CLAVE_SESION])
  })

  it('A caduca y B, de otra clínica, inicia sesión: nada de A queda en caché', async () => {
    simularSesion(null)
    const { cliente, result } = montar(sesionDe('admin'))
    await expect(result.current.conToken(async () => Promise.reject(NO_AUTENTICADO))).rejects.toBe(NO_AUTENTICADO)
    await waitFor(() => expect(result.current.sesion.estado).toBe('anonima'))
    act(() => result.current.sesion.iniciar({ ...sesionDe('admin'), tenant: OTRO_TENANT }))
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
  })

  it('una sesión nueva de otro usuario sobre la de A vacía la caché de negocio', async () => {
    simularSesion('admin')
    const { cliente, result } = montar(sesionDe('admin'))
    act(() => result.current.sesion.iniciar(sesionDe('contador')))
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
    await waitFor(() => expect(result.current.sesion.sesion?.usuario.id).toBe(sesionDe('contador').usuario.id))
  })

  it('el mismo usuario en otra clínica también vacía la caché de negocio', async () => {
    simularSesion('admin')
    const { cliente, result } = montar(sesionDe('admin'))
    act(() => result.current.sesion.iniciar({ ...sesionDe('admin'), tenant: OTRO_TENANT }))
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
    await waitFor(() => expect(result.current.sesion.sesion?.tenant.id).toBe(OTRO_TENANT.id))
  })

  it('el mismo usuario y la misma clínica (p. ej. tras cambiar la contraseña) conservan la caché', async () => {
    simularSesion('admin')
    const { cliente, result } = montar(sesionDe('admin'))
    act(() => result.current.sesion.iniciar(sesionDe('admin', 'jwt.otro')))
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toEqual(ACTIVOS_DE_A)
    await waitFor(() => expect(result.current.sesion.sesion?.access_token).toBe('jwt.otro'))
  })
})


// Spec 020, T3 (hallazgo del security-reviewer): la cookie de refresh es compartida entre
// pestañas. Si en otra pestaña A cierra sesión y entra B, la renovación de esta pestaña
// responde 200 con la sesión de B: la caché de negocio de A no debe pasar a B.
describe('renovación que trae otra persona u otra clínica', () => {
  const OTRO_TENANT = { id: '00000000-0000-4000-8000-0000000000d2', nombre: 'Otra Clínica' }
  const CLAVE_PLATAFORMA = ['plataforma', 'sesion'] as const
  const CLAVE_EMPRESAS = ['plataforma', 'empresas'] as const

  function montar(previa: Sesion | null) {
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    cliente.setQueryData(CLAVE_SESION, previa)
    cliente.setQueryData(CLAVE_ACTIVOS_A, ACTIVOS_DE_A)
    const envoltura = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={cliente}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
    const { result } = renderHook(() => ({ sesion: useSesion(), conToken: useApiAutenticada() }), { wrapper: envoltura })
    return { cliente, result }
  }

  function refrescaCon(nueva: Sesion) {
    return simularSesion(null, (url) => (url === '/api/auth/refresh' ? json(200, nueva) : undefined))
  }

  // Primer intento con el token viejo: 401; el reintento con el token nuevo responde.
  const llamar = async (token: string) => {
    if (token === 'jwt.admin') throw NO_AUTENTICADO
    return token
  }

  it('el refresh trae a B, contador: se vacían los activos con precio de A y la sesión es la de B', async () => {
    refrescaCon(sesionDe('contador'))
    const { cliente, result } = montar(sesionDe('admin'))
    await expect(act(() => result.current.conToken(llamar))).resolves.toBe('jwt.contador')
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
    expect(cliente.getQueryData(CLAVE_SESION)).toMatchObject({ rol: 'contador', usuario: { id: sesionDe('contador').usuario.id } })
  })

  it('el refresh trae el mismo rol de otra clínica: se vacía la caché de negocio', async () => {
    refrescaCon({ ...sesionDe('admin', 'jwt.otra'), tenant: OTRO_TENANT })
    const { cliente, result } = montar(sesionDe('admin'))
    await expect(act(() => result.current.conToken(llamar))).resolves.toBe('jwt.otra')
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
    expect(cliente.getQueryData(CLAVE_SESION)).toMatchObject({ tenant: { id: OTRO_TENANT.id } })
  })

  it('el refresh trae el mismo usuario y la misma clínica: la caché se conserva', async () => {
    refrescaCon(sesionDe('admin', 'jwt.nuevo'))
    const { cliente, result } = montar(sesionDe('admin'))
    await expect(act(() => result.current.conToken(llamar))).resolves.toBe('jwt.nuevo')
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toEqual(ACTIVOS_DE_A)
    expect(cliente.getQueryData(CLAVE_SESION)).toMatchObject({ access_token: 'jwt.nuevo' })
  })

  it('la consulta de la sesión (reintentar) que trae a otra persona también vacía la caché', async () => {
    refrescaCon(sesionDe('contador'))
    const { cliente, result } = montar(sesionDe('admin'))
    await act(() => cliente.refetchQueries({ queryKey: CLAVE_SESION }))
    await waitFor(() => expect(result.current.sesion.sesion?.rol).toBe('contador'))
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
  })

  it('vaciar la caché de negocio no toca la consola de la plataforma', async () => {
    simularSesion(null)
    const { cliente, result } = montar(sesionDe('admin'))
    cliente.setQueryData(CLAVE_PLATAFORMA, { desarrollador: 'dev' })
    cliente.setQueryData(CLAVE_EMPRESAS, [{ id: 'e1' }])
    await expect(result.current.conToken(async () => Promise.reject(NO_AUTENTICADO))).rejects.toBe(NO_AUTENTICADO)
    await waitFor(() => expect(cliente.getQueryData(CLAVE_SESION)).toBeNull())
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
    expect(cliente.getQueryData(CLAVE_PLATAFORMA)).toEqual({ desarrollador: 'dev' })
    expect(cliente.getQueryData(CLAVE_EMPRESAS)).toEqual([{ id: 'e1' }])
  })
})

// Una pantalla con la lista de activos de A abierta (consulta activa y observada) que no
// depende de la sesión: tras el cambio de persona no debe seguir mostrando los datos de A.
describe('consulta de negocio activa al cambiar de persona', () => {
  type Lista = typeof ACTIVOS_DE_A

  function ListaActivos({ cargar }: { cargar: () => Promise<Lista> }) {
    const { data } = useQuery({ queryKey: CLAVE_ACTIVOS_A, queryFn: cargar, staleTime: Infinity })
    return <p>{data ? data.activos.map((a) => a.nombre).join(', ') : 'sin datos'}</p>
  }

  function montar(cargar: () => Promise<Lista>, conDatos: boolean) {
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    cliente.setQueryData(CLAVE_SESION, sesionDe('admin'))
    if (conDatos) cliente.setQueryData(CLAVE_ACTIVOS_A, ACTIVOS_DE_A)
    const envoltura = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={cliente}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
    render(<ListaActivos cargar={cargar} />, { wrapper: envoltura })
    const { result } = renderHook(() => useSesion(), { wrapper: envoltura })
    return { cliente, result }
  }

  const nunca = () => new Promise<Lista>(() => {})

  it('la lista mostrada de A desaparece cuando entra B', async () => {
    simularSesion('admin')
    const { result } = montar(nunca, true)
    expect(screen.getByText('Silla ergonómica')).toBeTruthy()
    act(() => result.current.iniciar(sesionDe('contador')))
    await waitFor(() => expect(screen.queryByText('Silla ergonómica')).toBeNull())
  })

  it('una carga de A en vuelo que termina tras el cambio no se muestra ni queda en caché', async () => {
    simularSesion('admin')
    let resolverA: (lista: Lista) => void = () => {}
    const cargar = vi
      .fn<() => Promise<Lista>>()
      .mockImplementationOnce(() => new Promise<Lista>((resolver) => (resolverA = resolver)))
      .mockImplementation(nunca)
    const { cliente, result } = montar(cargar, false)
    await waitFor(() => expect(cargar).toHaveBeenCalledTimes(1))
    act(() => result.current.iniciar(sesionDe('contador')))
    await act(async () => resolverA(ACTIVOS_DE_A))
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByText('Silla ergonómica')).toBeNull()
    expect(cliente.getQueryData(CLAVE_ACTIVOS_A)).toBeUndefined()
  })
})

describe('arranque sin sesión previa', () => {
  it('el refresh 401 del arranque no quita las consultas públicas (p. ej. validar la invitación)', async () => {
    simularSesion(null)
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const CLAVE_INVITACION = ['invitacion', 'validar', 'tok'] as const
    cliente.setQueryData(CLAVE_INVITACION, { vigente: true })
    const { result } = renderHook(() => useSesion(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={cliente}>
          <MemoryRouter>{children}</MemoryRouter>
        </QueryClientProvider>
      ),
    })
    await waitFor(() => expect(result.current.estado).toBe('anonima'))
    expect(cliente.getQueryData(CLAVE_INVITACION)).toEqual({ vigente: true })
  })
})
