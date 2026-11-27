import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Esquemas } from '@/lib/api/cliente'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json } from '@/test/sesion'

import { errorDeAlta, errorDeFicha, errorDeLogo, filtrarEmpresas, nombreRepetido, validarAlta } from './api'

// Spec 017, T9 y T14 (R16–R24, R38–R46; A7, A14, A19, A26; CU-03 a CU-06, CU-12): módulo Empresas de la
// consola, montando las rutas reales con la API simulada.

type Empresa = Esquemas['EmpresaPlataforma']
type Modulo = Esquemas['ModuloPlataforma']

const DEV = { id: '00000000-0000-4000-8000-0000000000f1', email: 'dev@ejemplo.test', nombre: 'Daniela Ríos' }
const SESION = { access_token: 'jwt.plataforma', token_type: 'Bearer', expires_in: 600, desarrollador: DEV }
const EMPRESAS_MOD: Modulo = { id: 'empresas', titulo: 'Empresas', orden: 10 }
const USUARIOS_MOD: Modulo = { id: 'usuarios', titulo: 'Usuarios', orden: 20 }

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const CLAVE = 'Clave-Inicial-2026'

function empresa(n: number, extra: Partial<Empresa> = {}): Empresa {
  return {
    id: `00000000-0000-4000-8000-00000000010${n}`,
    nombre: `Clínica ${n}`,
    activa: true,
    creado_en: '2026-11-10T15:00:00+00:00',
    tiene_logo: false,
    n_membresias_activas: 3,
    n_admins_activos: 1,
    ...extra,
  }
}

const LISTA = [
  empresa(1, { nombre: 'Odontología Sonrisa', tiene_logo: true }),
  empresa(2, { nombre: 'Sonrisas del Valle', activa: false }),
  empresa(3, { nombre: 'Odonto Norte', n_admins_activos: 0, n_membresias_activas: 1 }),
]

type Manejador = (url: string, init: RequestInit) => Response | Promise<Response | undefined> | undefined

function abrir(path: string, { empresas = LISTA, modulos = [EMPRESAS_MOD], extra }: { empresas?: Empresa[] | Response; modulos?: Modulo[]; extra?: Manejador } = {}) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/plataforma/auth/refresh') return json(200, SESION)
    if (url === '/api/plataforma/modulos') return json(200, { modulos })
    if (url === '/api/plataforma/empresas?estado=todas') return empresas instanceof Response ? empresas.clone() : json(200, { empresas })
    return new Promise<Response>(() => {})
  })
  vi.stubGlobal('fetch', f)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router }
}

const llamadas = (f: ReturnType<typeof vi.fn>, url: string, metodo?: string) =>
  f.mock.calls.filter(([e, init]) => String(e) === url && (!metodo || (init as RequestInit | undefined)?.method === metodo))
const cuerpo = (init: unknown) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>
const h1 = (name: string | RegExp) => screen.findByRole('heading', { level: 1, name })
const campo = (nombre: RegExp) => screen.getByRole('textbox', { name: nombre }) as HTMLInputElement
const clave = (id: string) => document.getElementById(id) as HTMLInputElement

function llenarPaso1({ password = CLAVE, confirmacion = CLAVE } = {}) {
  fireEvent.change(campo(/^Nombre o razón social/), { target: { value: 'Clínica Nueva' } })
  fireEvent.change(campo(/^Dirección/), { target: { value: 'Calle 5 # 10-20, Cartago' } })
  fireEvent.change(campo(/^NIT/), { target: { value: '900123456-8' } })
  fireEvent.change(campo(/^Nombre\*?$/), { target: { value: 'Ana Torres' } })
  fireEvent.change(campo(/^Correo\*?$/), { target: { value: 'Ana@Clinica.test ' } })
  fireEvent.change(clave('alta-admin-password'), { target: { value: password } })
  fireEvent.change(clave('alta-admin-password_confirmacion'), { target: { value: confirmacion } })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('lista de empresas (CU-05; R21)', () => {
  it('aparece en el menú y /plataforma abre Empresas', async () => {
    const { router } = abrir('/plataforma')
    await h1('Empresas')
    expect(router.state.location.pathname).toBe('/plataforma/empresas')
    expect(screen.getByRole('link', { name: 'Empresas' }).getAttribute('aria-current')).toBe('page')
  })

  it('muestra nombre, estado, fecha, conteos y logo; marca «Sin admin activo»', async () => {
    abrir('/plataforma/empresas')
    const tabla = await screen.findByRole('table', { name: 'Empresas' })
    const filas = within(tabla).getAllByRole('row').slice(1)
    expect(filas).toHaveLength(3)
    expect(within(filas[0]).getByText('Odontología Sonrisa')).toBeTruthy()
    expect(within(filas[0]).getByText('Activa')).toBeTruthy()
    expect(within(filas[0]).getByText('Sí')).toBeTruthy()
    expect(within(filas[1]).getByText('Desactivada')).toBeTruthy()
    expect(within(filas[2]).getByText('Sin admin activo')).toBeTruthy()
    expect(within(filas[2]).getByText('Sin logo')).toBeTruthy()
    expect(within(filas[0]).getByText(/^10\D{1,6}(11|nov)\D{0,2}2026$/)).toBeTruthy()
    // Solo los conteos de R21: nada de datos de negocio.
    expect(screen.queryByText(/\$/)).toBeNull()
  })

  it('a 375 px la lista son tarjetas (A14)', async () => {
    simularAncho({ movil: true })
    abrir('/plataforma/empresas')
    const lista = await screen.findByRole('list', { name: 'Empresas' })
    expect(within(lista).getAllByRole('listitem')).toHaveLength(3)
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('filtra por nombre al escribir, sin pedir al servidor', async () => {
    const { f } = abrir('/plataforma/empresas')
    await screen.findByRole('table', { name: 'Empresas' })
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar empresa por nombre' }), { target: { value: 'valle' } })
    const filas = within(screen.getByRole('table', { name: 'Empresas' })).getAllByRole('row').slice(1)
    expect(filas).toHaveLength(1)
    expect(within(filas[0]).getByText('Sonrisas del Valle')).toBeTruthy()
    expect(llamadas(f, '/api/plataforma/empresas?estado=todas')).toHaveLength(1)
  })

  it('sin resultados: «No hay empresas con ese nombre» y limpiar', async () => {
    abrir('/plataforma/empresas')
    await screen.findByRole('table', { name: 'Empresas' })
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar empresa por nombre' }), { target: { value: 'zzz' } })
    expect(screen.getByText('No hay empresas con ese nombre')).toBeTruthy()
    fireEvent.click(screen.getAllByRole('button', { name: 'Limpiar filtros' })[0])
    expect(within(screen.getByRole('table', { name: 'Empresas' })).getAllByRole('row')).toHaveLength(4)
  })

  it('filtra por estado (Activas, Desactivadas, Todas)', async () => {
    abrir('/plataforma/empresas')
    await screen.findByRole('table', { name: 'Empresas' })
    fireEvent.click(screen.getByRole('button', { name: 'Estado' }))
    fireEvent.click(await screen.findByRole('radio', { name: /Desactivadas/ }))
    const filas = within(screen.getByRole('table', { name: 'Empresas' })).getAllByRole('row').slice(1)
    expect(filas).toHaveLength(1)
    expect(within(filas[0]).getByText('Sonrisas del Valle')).toBeTruthy()
  })

  it('vacía: «Aún no hay empresas. Crea la primera.» con «Nueva empresa»', async () => {
    abrir('/plataforma/empresas', { empresas: [] })
    expect(await screen.findByText('Aún no hay empresas. Crea la primera.')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: 'Nueva empresa' }).length).toBeGreaterThan(0)
  })

  it('mientras carga lo dice y con error ofrece reintentar', async () => {
    let intentos = 0
    abrir('/plataforma/empresas', {
      extra: (url) => {
        if (url !== '/api/plataforma/empresas?estado=todas') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(400, 'solicitud_invalida', 'La solicitud no es válida.') : json(200, { empresas: LISTA })
      },
    })
    expect(await screen.findByRole('status', { name: 'Cargando empresas' })).toBeTruthy()
    expect(await screen.findByText('No se pudieron cargar las empresas')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('table', { name: 'Empresas' })).toBeTruthy()
  })

  it('«Ver usuarios» solo si el módulo Usuarios está habilitado, con la empresa en la ruta', async () => {
    abrir('/plataforma/empresas', { modulos: [EMPRESAS_MOD] })
    await screen.findByRole('table', { name: 'Empresas' })
    // Sin el módulo Usuarios en el servidor no hay enlace muerto.
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Acciones de Odontología Sonrisa' }), { button: 0, ctrlKey: false })
    const menu = await screen.findByRole('menu')
    expect(within(menu).queryByRole('menuitem', { name: 'Ver usuarios' })).toBeNull()
    expect(within(menu).getByRole('menuitem', { name: 'Desactivar' })).toBeTruthy()
  })

  it('con Usuarios habilitado (T10), «Ver usuarios» abre Usuarios con esa empresa elegida (CU-05)', async () => {
    const id = LISTA[0].id
    const { f, router } = abrir('/plataforma/empresas', {
      modulos: [EMPRESAS_MOD, USUARIOS_MOD],
      extra: (url) => (url === `/api/plataforma/empresas/${id}/usuarios` ? json(200, { usuarios: [] }) : undefined),
    })
    await screen.findByRole('table', { name: 'Empresas' })
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Acciones de Odontología Sonrisa' }), { button: 0, ctrlKey: false })
    const enlace = within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Ver usuarios' })
    expect(enlace.getAttribute('href')).toBe(`/plataforma/usuarios?empresa=${id}`)
    fireEvent.click(enlace)
    await h1('Usuarios')
    expect(router.state.location.pathname).toBe('/plataforma/usuarios')
    expect(router.state.location.search).toBe(`?empresa=${id}`)
    await waitFor(() => expect(llamadas(f, `/api/plataforma/empresas/${id}/usuarios`)).toHaveLength(1))
    expect(await screen.findByText('Esta empresa aún no tiene usuarios')).toBeTruthy()
  })
})

describe('desactivar y reactivar (CU-06; R22, R40)', () => {
  async function elegir(nombre: string, opcion: string) {
    fireEvent.pointerDown(await screen.findByRole('button', { name: `Acciones de ${nombre}` }), { button: 0, ctrlKey: false })
    fireEvent.click(await screen.findByRole('menuitem', { name: opcion }))
    return screen.findByRole('alertdialog')
  }

  it('desactivar pide confirmación con el nombre y el efecto, y no envía si se cancela', async () => {
    const { f } = abrir('/plataforma/empresas')
    const dialogo = await elegir('Odontología Sonrisa', 'Desactivar')
    expect(within(dialogo).getByRole('heading', { name: '¿Desactivar Odontología Sonrisa?' })).toBeTruthy()
    expect(dialogo.textContent).toContain('Los usuarios de Odontología Sonrisa no podrán entrar. No se borra nada.')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(f.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'PATCH')).toBe(false)
  })

  it('al confirmar envía {activa: false} y la fila queda «Desactivada»', async () => {
    const id = LISTA[0].id
    let desactivada = false
    const { f } = abrir('/plataforma/empresas', {
      extra: (url, init) => {
        if (url === `/api/plataforma/empresas/${id}` && init.method === 'PATCH') {
          desactivada = true
          return json(200, { id, activa: false })
        }
        // La lista que se vuelve a pedir ya trae el estado nuevo (como el servidor).
        if (url === '/api/plataforma/empresas?estado=todas' && desactivada) {
          return json(200, { empresas: LISTA.map((e) => (e.id === id ? { ...e, activa: false } : e)) })
        }
        return undefined
      },
    })
    const dialogo = await elegir('Odontología Sonrisa', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    await waitFor(() => expect(llamadas(f, `/api/plataforma/empresas/${id}`, 'PATCH')).toHaveLength(1))
    const [, init] = llamadas(f, `/api/plataforma/empresas/${id}`, 'PATCH')[0]
    expect(cuerpo(init)).toEqual({ activa: false })
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer jwt.plataforma')
    const fila = (await screen.findByText('Odontología Sonrisa')).closest('tr')!
    await waitFor(() => expect(within(fila).getByText('Desactivada')).toBeTruthy())
  })

  it('reactivar también confirma y envía {activa: true}', async () => {
    const id = LISTA[1].id
    const { f } = abrir('/plataforma/empresas', {
      extra: (url, init) => (url === `/api/plataforma/empresas/${id}` && init.method === 'PATCH' ? json(200, { id, activa: true }) : undefined),
    })
    const dialogo = await elegir('Sonrisas del Valle', 'Reactivar')
    expect(within(dialogo).getByRole('heading', { name: '¿Reactivar Sonrisas del Valle?' })).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, reactivar' }))
    await waitFor(() => expect(llamadas(f, `/api/plataforma/empresas/${id}`, 'PATCH')).toHaveLength(1))
    expect(cuerpo(llamadas(f, `/api/plataforma/empresas/${id}`, 'PATCH')[0][1])).toEqual({ activa: true })
  })

  it('si el servidor falla, lo dice y la fila no cambia', async () => {
    const id = LISTA[0].id
    abrir('/plataforma/empresas', {
      extra: (url, init) =>
        url === `/api/plataforma/empresas/${id}` && init.method === 'PATCH' ? errorApi(404, 'no_encontrado', 'La empresa no existe.') : undefined,
    })
    const dialogo = await elegir('Odontología Sonrisa', 'Desactivar')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sí, desactivar' }))
    expect(await screen.findByText('La empresa no existe.')).toBeTruthy()
    const fila = screen.getByText('Odontología Sonrisa').closest('tr')!
    expect(within(fila).getByText('Activa')).toBeTruthy()
  })
})

// --- Alta: formulario único (C1c; T14) ----------------------------------------------------

const png = (nombre = 'logo.png', tipo = 'image/png') => new File([new Uint8Array([137, 80, 78, 71])], nombre, { type: tipo })
const elegirLogoAlta = (archivo: File) => fireEvent.change(screen.getByTestId('entrada-logo-alta'), { target: { files: [archivo] } })
const formLogo = (init: unknown) => (init as RequestInit).body as FormData
const ADMIN_ID = '00000000-0000-4000-8000-0000000000a9'

/** POST de creación que responde 201 con el id enviado; el resto lo atiende `logo` (con `__ID__` en la URL). */
function conAlta(logo?: Manejador): Manejador {
  let empresaId = ''
  return (url, init) => {
    if (url === '/api/plataforma/empresas' && init.method === 'POST') {
      empresaId = String(cuerpo(init).id)
      return json(201, { empresa_id: empresaId, admin_id: ADMIN_ID })
    }
    return empresaId ? logo?.(url.replace(empresaId, '__ID__'), init) : undefined
  }
}
const LOGO = '/api/plataforma/empresas/__ID__/logo'
const FICHA = '/api/plataforma/empresas/__ID__/ficha'

function sinSecretos(...secretos: string[]) {
  for (const secreto of secretos) {
    expect(document.body.innerHTML).not.toContain(secreto)
    expect(JSON.stringify({ ...localStorage })).not.toContain(secreto)
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(secreto)
    expect(window.location.href).not.toContain(secreto)
    expect(JSON.stringify(window.history.state ?? null)).not.toContain(secreto)
  }
}

describe('nueva empresa: un solo formulario (CU-03, CU-04; R16–R20, R39, R46)', () => {
  it('abre desde la lista: un formulario con la ficha, el logo opcional y el primer admin; sin pasos ni barra', async () => {
    const { router } = abrir('/plataforma/empresas')
    await screen.findByRole('table', { name: 'Empresas' })
    fireEvent.click(screen.getByRole('link', { name: 'Nueva empresa' }))
    await h1('Nueva empresa')
    expect(router.state.location.pathname).toBe('/plataforma/empresas/nueva')
    // C1c: no hay asistente.
    expect(screen.queryByText(/Paso \d de 2/)).toBeNull()
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(document.querySelectorAll('form')).toHaveLength(1)
    for (const nombre of [/^Nombre o razón social/, /^Dirección/, /^NIT/, /^Teléfono/, /^Correo de la empresa/, /^Nombre\*?$/, /^Correo\*?$/]) {
      expect(campo(nombre)).toBeTruthy()
    }
    // El logo va junto a los datos de la empresa, antes del primer admin.
    const datos = screen.getByText('Datos de la empresa')
    const logo = screen.getByText('Logo (opcional)')
    const admin = screen.getByText('Primer admin')
    expect(datos.compareDocumentPosition(logo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(logo.compareDocumentPosition(admin) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText(/160 × 64 px/)).toBeTruthy()
    expect(screen.getByText('Sin logo')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Elegir imagen' })).toBeTruthy()
    expect(screen.getByText('El admin deberá cambiar esta contraseña al entrar.')).toBeTruthy()
    // C1b (T16): si se pierde, se define otra temporal desde Usuarios (ya no «no se puede recuperar»).
    expect(screen.getByText('No se vuelve a mostrar. Si se pierde, define otra desde Usuarios.')).toBeTruthy()
    expect(screen.queryByText(/no se puede recuperar/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /Copiar/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Saltar/ })).toBeNull()
    // Un solo botón de envío.
    expect(screen.getAllByRole('button', { name: 'Crear empresa' })).toHaveLength(1)
  })

  it('las contraseñas son ocultas, sin autocompletar y no controladas por React', async () => {
    abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    for (const id of ['alta-admin-password', 'alta-admin-password_confirmacion']) {
      const input = clave(id)
      expect(input.type).toBe('password')
      expect(input.autocomplete).toBe('new-password')
    }
    expect(screen.getByLabelText('Contraseña', { selector: 'input' })).toBeTruthy()
    expect(screen.getByLabelText('Confirmar contraseña', { selector: 'input' })).toBeTruthy()
    expect(campo(/^Correo\*?$/).autocomplete).toBe('off')
    // El selector de archivo no tiene nombre: el FormData del alta nunca lleva el archivo.
    expect(screen.getByTestId('entrada-logo-alta').getAttribute('name')).toBeNull()
  })

  it('el formulario es POST y el envío no navega (D20: la contraseña nunca va en la URL)', async () => {
    abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    const form = screen.getByRole('button', { name: 'Crear empresa' }).closest('form')!
    expect(form.getAttribute('method')).toBe('post')
    expect(fireEvent.submit(form)).toBe(false)
  })

  it('valida antes de enviar y lleva el foco al primer error', async () => {
    const { f } = abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('Escribe el nombre de la empresa (máximo 120 caracteres).')).toBeTruthy()
    expect(screen.getByText('Escribe el nombre del primer admin (máximo 120 caracteres).')).toBeTruthy()
    expect(screen.getByText('La contraseña debe tener entre 10 y 128 caracteres.')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(campo(/^Nombre o razón social/)))
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(0)
    fireEvent.input(clave('alta-admin-password'), { target: { value: 'x' } })
    expect(screen.queryByText('La contraseña debe tener entre 10 y 128 caracteres.')).toBeNull()
  })

  it('confirmación distinta: lo dice sin enviar y conserva lo escrito', async () => {
    const { f } = abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    llenarPaso1({ confirmacion: 'Otra-Clave-2026' })
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('Las contraseñas no coinciden. Escribe la misma en los dos campos.')).toBeTruthy()
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(0)
    expect(clave('alta-admin-password').value).toBe(CLAVE)
  })

  it('avisa si ya hay una empresa con ese nombre, pero deja crearla (P34)', async () => {
    abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    await waitFor(() => expect(screen.queryByText(/Ya existe una empresa con ese nombre/)).toBeNull())
    fireEvent.change(campo(/^Nombre o razón social/), { target: { value: '  odontología sonrisa ' } })
    expect(await screen.findByText(/Ya existe una empresa con ese nombre/)).toBeTruthy()
  })

  it('sin logo: crea con id de cliente, borra las contraseñas y muestra «Empresa lista» sin subir nada (A7)', async () => {
    const { f } = abrir('/plataforma/empresas/nueva', { extra: conAlta() })
    await h1('Nueva empresa')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByRole('heading', { name: 'Empresa lista' })).toBeTruthy()
    expect(screen.getByText(/sin logo por ahora/)).toBeTruthy()
    const [, init] = llamadas(f, '/api/plataforma/empresas', 'POST')[0]
    const enviado = cuerpo(init)
    expect(enviado.id).toMatch(UUID)
    expect(enviado).toMatchObject({
      nombre: 'Clínica Nueva',
      direccion: 'Calle 5 # 10-20, Cartago',
      nit: '900.123.456-8',
      telefono: null,
      correo: null,
      admin: { nombre: 'Ana Torres', email: 'ana@clinica.test', password: CLAVE, password_confirmacion: CLAVE },
    })
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer jwt.plataforma')
    expect(f.mock.calls.some(([u]) => String(u).endsWith('/logo'))).toBe(false)
    expect(screen.getByText(/ana@clinica\.test/)).toBeTruthy()
    expect(screen.getByText('El admin deberá cambiar esta contraseña al entrar.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Volver a empresas' }).getAttribute('href')).toBe('/plataforma/empresas')
    sinSecretos(CLAVE)
  })

  it('con logo: crea la empresa y luego sube el logo en otra llamada multipart, sin la contraseña', async () => {
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: conAlta((url, init) => (url === LOGO && init.method === 'POST' ? json(201, { logo: { id: 'x' } }) : undefined)),
    })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    expect(screen.getByRole('img', { name: 'Vista previa del logo' })).toBeTruthy()
    expect(screen.getByText('logo.png')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Elegir otra imagen' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByRole('heading', { name: 'Empresa lista' })).toBeTruthy()
    expect(screen.getByText(/y con su logo/)).toBeTruthy()
    const altas = llamadas(f, '/api/plataforma/empresas', 'POST')
    expect(altas).toHaveLength(1)
    const empresaId = String(cuerpo(altas[0][1]).id)
    const logos = llamadas(f, `/api/plataforma/empresas/${empresaId}/logo`, 'POST')
    expect(logos).toHaveLength(1)
    // Primero la empresa, luego el logo.
    const orden = f.mock.calls as unknown[]
    expect(orden.indexOf(altas[0])).toBeLessThan(orden.indexOf(logos[0]))
    const form = formLogo(logos[0][1])
    expect([...form.keys()].sort()).toEqual(['archivo', 'logo_id'])
    expect(String(form.get('logo_id'))).toMatch(UUID)
    expect(form.get('archivo')).toBeInstanceOf(Blob)
    for (const [, valor] of form.entries()) expect(typeof valor === 'string' ? valor : '').not.toContain(CLAVE)
    // La creación no lleva el archivo.
    expect(String((altas[0][1] as RequestInit).body)).not.toContain('logo')
    sinSecretos(CLAVE)
  })

  it.each([
    [413, 'foto_demasiado_grande', 'La imagen pesa más de 2 MB. Elige una más liviana.'],
    [415, 'tipo_no_admitido', 'El archivo no es PNG, JPEG ni WebP.'],
    [503, 'logos_no_disponibles', 'El almacenamiento de imágenes no está disponible en este servidor.'],
  ])('fallo parcial (%i): la empresa queda creada, avisa y no la vuelve a crear (A26)', async (status, code, motivo) => {
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: conAlta((url, init) => (url === LOGO && init.method === 'POST' ? errorApi(status, code, 'El archivo no es PNG, JPEG ni WebP.') : undefined)),
    })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    const aviso = (await screen.findByText('Empresa creada; el logo no se pudo subir')).closest<HTMLElement>('[role="alert"]')!
    expect(aviso.textContent).toContain(motivo)
    expect(aviso.textContent).toContain('Puedes subirlo desde «Editar empresa»')
    expect(within(aviso).getByRole('button', { name: 'Editar empresa' })).toBeTruthy()
    expect(within(aviso).getByRole('button', { name: 'Volver a empresas' })).toBeTruthy()
    // La empresa no se recrea: un solo POST de creación y el formulario ya no está.
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Crear empresa' })).toBeNull()
    expect(document.querySelector('form')).toBeNull()
    expect(screen.queryByText(/Paso \d de 2/)).toBeNull()
    expect(screen.queryByRole('progressbar')).toBeNull()
    // Sigue diciendo cómo entra el admin.
    expect(screen.getByText(/ana@clinica\.test/)).toBeTruthy()
    sinSecretos(CLAVE)
    fireEvent.click(within(aviso).getByRole('button', { name: 'Volver a empresas' }))
    await h1('Empresas')
  })

  it('tras el fallo parcial, «Editar empresa» reintenta el logo con el mismo archivo y nunca recrea la empresa', async () => {
    let intentos = 0
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: conAlta((url, init) => {
        if (url === FICHA && (init.method ?? 'GET') === 'GET') {
          return json(200, { nombre: 'Clínica Nueva', direccion: 'Calle 5 # 10-20, Cartago', nit: '900.123.456-8', telefono: null, correo: null, tiene_logo: false })
        }
        if (url !== LOGO || init.method !== 'POST') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(201, { logo: { id: 'x' } })
      }),
    })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Editar empresa' }))
    const dialogo = await screen.findByRole('dialog')
    expect(await within(dialogo).findByDisplayValue('Clínica Nueva')).toBeTruthy()
    // El archivo elegido en el alta ya está en el bloque del logo.
    expect(within(dialogo).getByRole('img', { name: 'Vista previa del logo' })).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Subir logo' }))
    await waitFor(() => expect(intentos).toBe(2))
    expect(await within(dialogo).findByText('Tiene logo')).toBeTruthy()
    const empresaId = String(cuerpo(llamadas(f, '/api/plataforma/empresas', 'POST')[0][1]).id)
    const ids = llamadas(f, `/api/plataforma/empresas/${empresaId}/logo`, 'POST').map(([, i]) => formLogo(i).get('logo_id'))
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBe(ids[1])
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(1)
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar' }))
    // Al cerrar, el resultado ya dice que tiene logo.
    expect(await screen.findByRole('heading', { name: 'Empresa lista' })).toBeTruthy()
    expect(screen.getByText(/y con su logo/)).toBeTruthy()
  })

  it('un archivo que no es imagen se rechaza en el navegador y no se elige', async () => {
    abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    elegirLogoAlta(png('notas.txt', 'text/plain'))
    expect(screen.getByText('Ese archivo no es una imagen PNG, JPG o WebP. Elige otro.')).toBeTruthy()
    expect(screen.getByText('Sin logo')).toBeTruthy()
  })

  it('«Quitar imagen» deja el alta sin logo', async () => {
    const { f } = abrir('/plataforma/empresas/nueva', { extra: conAlta() })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    fireEvent.click(screen.getByRole('button', { name: 'Quitar imagen' }))
    expect(screen.queryByRole('img', { name: 'Vista previa del logo' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/sin logo por ahora/)).toBeTruthy()
    expect(f.mock.calls.some(([u]) => String(u).endsWith('/logo'))).toBe(false)
  })

  it('el botón queda ocupado mientras envía: un doble clic no manda dos altas', async () => {
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: (url, init) => (url === '/api/plataforma/empresas' && init.method === 'POST' ? new Promise<Response>(() => {}) : undefined),
    })
    await h1('Nueva empresa')
    llenarPaso1()
    const boton = screen.getByRole('button', { name: 'Crear empresa' })
    fireEvent.click(boton)
    fireEvent.submit(boton.closest('form')!)
    await screen.findByRole('button', { name: 'Creando empresa…' })
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(1)
  })

  it('mientras sube el logo sigue «Creando empresa…» (un solo estado de envío)', async () => {
    abrir('/plataforma/empresas/nueva', {
      extra: conAlta((url, init) => (url === LOGO && init.method === 'POST' ? new Promise<Response>(() => {}) : undefined)),
    })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByRole('button', { name: 'Creando empresa…' })).toBeTruthy()
    // Las contraseñas ya se borraron aunque el logo siga subiendo.
    await waitFor(() => expect(clave('alta-admin-password').value).toBe(''))
  })

  it('409 email_en_uso: lo dice en el correo del admin y borra las contraseñas; el logo no se sube', async () => {
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: (url, init) =>
        url === '/api/plataforma/empresas' && init.method === 'POST'
          ? errorApi(409, 'email_en_uso', 'Ese correo ya está en uso. Usa otro correo para el primer admin.')
          : undefined,
    })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('Ese correo ya está en uso. Usa otro correo para el primer admin.')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(campo(/^Correo\*?$/)))
    expect(clave('alta-admin-password').value).toBe('')
    expect(clave('alta-admin-password_confirmacion').value).toBe('')
    expect(screen.getByText(/la contraseña se borró al enviar/)).toBeTruthy()
    expect(campo(/^Nombre o razón social/).value).toBe('Clínica Nueva')
    // El logo elegido se conserva para el reenvío.
    expect(screen.getByRole('img', { name: 'Vista previa del logo' })).toBeTruthy()
    expect(f.mock.calls.some(([u]) => String(u).endsWith('/logo'))).toBe(false)
  })

  it('422 con campo: el error queda en ese campo (NIT)', async () => {
    abrir('/plataforma/empresas/nueva', {
      extra: (url, init) =>
        url === '/api/plataforma/empresas' && init.method === 'POST'
          ? json(422, { error: { code: 'campo_invalido', message: 'El NIT del servidor no es válido.', request_id: 'x', campo: 'nit' } })
          : undefined,
    })
    await h1('Nueva empresa')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('El NIT del servidor no es válido.')).toBeTruthy()
    expect(campo(/^NIT/).getAttribute('aria-invalid')).toBe('true')
  })

  it('el reintento tras un fallo de la creación usa el mismo id (idempotente, R20)', async () => {
    let intentos = 0
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: (url, init) => {
        if (url !== '/api/plataforma/empresas' || init.method !== 'POST') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(201, { empresa_id: cuerpo(init).id, admin_id: 'a' })
      },
    })
    await h1('Nueva empresa')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/El servicio no está disponible/)).toBeTruthy()
    fireEvent.change(clave('alta-admin-password'), { target: { value: CLAVE } })
    fireEvent.change(clave('alta-admin-password_confirmacion'), { target: { value: CLAVE } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    await screen.findByRole('heading', { name: 'Empresa lista' })
    const ids = llamadas(f, '/api/plataforma/empresas', 'POST').map(([, init]) => cuerpo(init).id)
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBe(ids[1])
  })

  it('409 empresa_existente: la empresa ya estaba creada; termina sin recrearla y sube el logo elegido', async () => {
    let empresaId = ''
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: (url, init) => {
        if (url === '/api/plataforma/empresas' && init.method === 'POST') {
          empresaId = String(cuerpo(init).id)
          return errorApi(409, 'empresa_existente', 'Esta empresa ya se creó. La contraseña del admin no se puede recuperar.')
        }
        if (empresaId && url === `/api/plataforma/empresas/${empresaId}/logo`) return json(201, { logo: { id: 'x' } })
        return undefined
      },
    })
    await h1('Nueva empresa')
    llenarPaso1()
    elegirLogoAlta(png())
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByRole('heading', { name: 'Empresa lista' })).toBeTruthy()
    expect(screen.getByText('Esta empresa ya se había creado')).toBeTruthy()
    expect(screen.getByText(/y con su logo/)).toBeTruthy()
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(1)
    expect(llamadas(f, `/api/plataforma/empresas/${empresaId}/logo`, 'POST')).toHaveLength(1)
  })

  it('409 empresa_existente tras editar: el resultado muestra el nombre y el correo del primer envío (D18)', async () => {
    let intentos = 0
    abrir('/plataforma/empresas/nueva', {
      extra: (url, init) => {
        if (url !== '/api/plataforma/empresas' || init.method !== 'POST') return undefined
        intentos += 1
        // 1.º: el servidor la crea pero la respuesta se pierde. 2.º: mismo id → 409.
        if (intentos === 1) return Promise.reject(new TypeError('Failed to fetch'))
        return errorApi(409, 'empresa_existente', 'Esta empresa ya se creó. La contraseña del admin no se puede recuperar.')
      },
    })
    await h1('Nueva empresa')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/la contraseña se borró al enviar/)).toBeTruthy()
    fireEvent.change(campo(/^Nombre o razón social/), { target: { value: 'Clínica Editada' } })
    fireEvent.change(campo(/^Correo\*?$/), { target: { value: 'otro@clinica.test' } })
    fireEvent.change(clave('alta-admin-password'), { target: { value: 'Otra-Clave-2026' } })
    fireEvent.change(clave('alta-admin-password_confirmacion'), { target: { value: 'Otra-Clave-2026' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('Esta empresa ya se había creado')).toBeTruthy()
    expect(screen.getByText(/Clínica Nueva ya está activa/)).toBeTruthy()
    expect(screen.getByText(/ana@clinica\.test/)).toBeTruthy()
    expect(screen.getByText(/el correo es el del primer envío/)).toBeTruthy()
    expect(screen.queryByText(/otro@clinica\.test/)).toBeNull()
    expect(screen.queryByText(/Clínica Editada/)).toBeNull()
    sinSecretos(CLAVE, 'Otra-Clave-2026')
  })

  it('409 empresa_existente tras un 503 que sí creó la empresa: el 5xx cuenta como primer envío (D18)', async () => {
    let intentos = 0
    const { f } = abrir('/plataforma/empresas/nueva', {
      extra: (url, init) => {
        if (url !== '/api/plataforma/empresas' || init.method !== 'POST') return undefined
        intentos += 1
        if (intentos === 1) return errorApi(503, 'servicio_no_disponible')
        return errorApi(409, 'empresa_existente', 'Esta empresa ya se creó. La contraseña del admin no se puede recuperar.')
      },
    })
    await h1('Nueva empresa')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/El servicio no está disponible/)).toBeTruthy()
    expect(llamadas(f, '/api/plataforma/empresas', 'POST')).toHaveLength(1)
    fireEvent.change(campo(/^Nombre o razón social/), { target: { value: 'Clínica Editada' } })
    fireEvent.change(campo(/^Correo\*?$/), { target: { value: 'otro@clinica.test' } })
    fireEvent.change(clave('alta-admin-password'), { target: { value: 'Otra-Clave-2026' } })
    fireEvent.change(clave('alta-admin-password_confirmacion'), { target: { value: 'Otra-Clave-2026' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('Esta empresa ya se había creado')).toBeTruthy()
    const ids = llamadas(f, '/api/plataforma/empresas', 'POST').map(([, init]) => cuerpo(init).id)
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBe(ids[1])
    expect(screen.getByText(/Clínica Nueva ya está activa/)).toBeTruthy()
    expect(screen.queryByText(/otro@clinica\.test/)).toBeNull()
    sinSecretos(CLAVE, 'Otra-Clave-2026')
  })

  it('409 empresa_existente: un envío rechazado (422) no cuenta como primer envío (D18)', async () => {
    let intentos = 0
    abrir('/plataforma/empresas/nueva', {
      extra: (url, init) => {
        if (url !== '/api/plataforma/empresas' || init.method !== 'POST') return undefined
        intentos += 1
        if (intentos === 1) return json(422, { error: { code: 'campo_invalido', message: 'El NIT del servidor no es válido.', request_id: 'x', campo: 'nit' } })
        if (intentos === 2) return Promise.reject(new TypeError('Failed to fetch'))
        return errorApi(409, 'empresa_existente', 'Esta empresa ya se creó. La contraseña del admin no se puede recuperar.')
      },
    })
    await h1('Nueva empresa')
    llenarPaso1()
    const reescribirClaves = () => {
      fireEvent.change(clave('alta-admin-password'), { target: { value: CLAVE } })
      fireEvent.change(clave('alta-admin-password_confirmacion'), { target: { value: CLAVE } })
    }
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText('El NIT del servidor no es válido.')).toBeTruthy()
    fireEvent.change(campo(/^Correo\*?$/), { target: { value: 'segundo@clinica.test' } })
    reescribirClaves()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    await waitFor(() => expect(intentos).toBe(2))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Crear empresa' })).toBeTruthy())
    fireEvent.change(campo(/^Correo\*?$/), { target: { value: 'tercero@clinica.test' } })
    reescribirClaves()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    expect(await screen.findByText(/segundo@clinica\.test/)).toBeTruthy()
  })

  it('«Crear otra empresa» abre un formulario nuevo con otro id', async () => {
    const { f } = abrir('/plataforma/empresas/nueva', { extra: conAlta() })
    await h1('Nueva empresa')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Crear otra empresa' }))
    expect(await screen.findByRole('button', { name: 'Crear empresa' })).toBeTruthy()
    expect(campo(/^Nombre o razón social/).value).toBe('')
    llenarPaso1()
    fireEvent.click(screen.getByRole('button', { name: 'Crear empresa' }))
    await screen.findByRole('heading', { name: 'Empresa lista' })
    const ids = llamadas(f, '/api/plataforma/empresas', 'POST').map(([, init]) => cuerpo(init).id)
    expect(ids).toHaveLength(2)
    expect(ids[0]).not.toBe(ids[1])
  })

  it('«Cancelar» vuelve a la lista', async () => {
    const { router } = abrir('/plataforma/empresas/nueva')
    await h1('Nueva empresa')
    fireEvent.click(screen.getByRole('link', { name: 'Cancelar' }))
    await h1('Empresas')
    expect(router.state.location.pathname).toBe('/plataforma/empresas')
  })
})

// --- Editar empresa (C1; R41–R44; CU-12; A21, A22, A26) ------------------------------------

describe('editar empresa (CU-12; R41–R44)', () => {
  const EMPRESA = LISTA[0]
  const URL_FICHA = `/api/plataforma/empresas/${EMPRESA.id}/ficha`
  const URL_LOGO = `/api/plataforma/empresas/${EMPRESA.id}/logo`
  const VIGENTE = { nombre: 'Odontología Sonrisa', direccion: 'Cra 4 # 12-30, Cartago', nit: '900.123.456-8', telefono: '606 211 0000', correo: 'hola@bio.test', tiene_logo: true }

  async function abrirEditar({ ficha = VIGENTE as unknown, extra }: { ficha?: unknown; extra?: Manejador } = {}) {
    const ctx = abrir('/plataforma/empresas', {
      extra: async (url, init) => {
        const propia = await extra?.(url, init)
        if (propia) return propia
        if (url === URL_FICHA && (init.method ?? 'GET') === 'GET') return ficha instanceof Response ? ficha.clone() : json(200, ficha)
        return undefined
      },
    })
    fireEvent.pointerDown(await screen.findByRole('button', { name: `Acciones de ${EMPRESA.nombre}` }), { button: 0, ctrlKey: false })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Editar' }))
    const dialogo = await screen.findByRole('dialog')
    return { ...ctx, dialogo }
  }

  const guardar = (dialogo: HTMLElement) => within(dialogo).getByRole('button', { name: 'Guardar cambios' }) as HTMLButtonElement
  const enDialogo = (dialogo: HTMLElement, nombre: RegExp) => within(dialogo).getByRole('textbox', { name: nombre }) as HTMLInputElement
  const elegirLogoEditar = (archivo: File) => fireEvent.change(screen.getByTestId('entrada-logo-editar'), { target: { files: [archivo] } })

  it('«Editar» está en el menú de cada fila, antes de desactivar', async () => {
    abrir('/plataforma/empresas')
    fireEvent.pointerDown(await screen.findByRole('button', { name: 'Acciones de Sonrisas del Valle' }), { button: 0, ctrlKey: false })
    const opciones = within(await screen.findByRole('menu')).getAllByRole('menuitem').map((o) => o.textContent)
    expect(opciones).toEqual(['Editar', 'Reactivar'])
  })

  // Ajuste T15b (C1): cuadro centrado y doble clic sobre la fila.
  it('«Editar» abre un cuadro de diálogo centrado (no una hoja lateral)', async () => {
    const { dialogo } = await abrirEditar()
    expect(dialogo.getAttribute('data-forma')).toBe('centrado')
    expect(within(dialogo).getByRole('heading', { name: 'Editar empresa' })).toBeTruthy()
  })

  it('a 375 px también es un cuadro centrado', async () => {
    simularAncho({ movil: true })
    abrir('/plataforma/empresas', {
      extra: (url) => (url === URL_FICHA ? json(200, VIGENTE) : undefined),
    })
    fireEvent.pointerDown(await screen.findByRole('button', { name: `Acciones de ${EMPRESA.nombre}` }), { button: 0, ctrlKey: false })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Editar' }))
    expect((await screen.findByRole('dialog', { name: 'Editar empresa' })).getAttribute('data-forma')).toBe('centrado')
  })

  it('doble clic sobre la fila abre Editar empresa de esa empresa, con la pista en la fila', async () => {
    abrir('/plataforma/empresas', { extra: (url) => (url === URL_FICHA ? json(200, VIGENTE) : undefined) })
    const tabla = await screen.findByRole('table', { name: 'Empresas' })
    const fila = within(tabla).getByText(EMPRESA.nombre).closest('tr')!
    expect(fila.getAttribute('title')).toBe('Doble clic para editar')
    fireEvent.doubleClick(within(fila).getByText('Sí'))
    const dialogo = await screen.findByRole('dialog', { name: 'Editar empresa' })
    expect(dialogo.textContent).toContain(EMPRESA.nombre)
    expect(dialogo.getAttribute('data-forma')).toBe('centrado')
  })

  it('doble clic en el menú ⋯ de la fila no abre Editar empresa', async () => {
    abrir('/plataforma/empresas')
    fireEvent.doubleClick(await screen.findByRole('button', { name: `Acciones de ${EMPRESA.nombre}` }))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('doble clic también abre Editar con la empresa desactivada (como el menú)', async () => {
    abrir('/plataforma/empresas')
    const fila = within(await screen.findByRole('table', { name: 'Empresas' })).getByText('Sonrisas del Valle').closest('tr')!
    fireEvent.doubleClick(fila)
    expect((await screen.findByRole('dialog', { name: 'Editar empresa' })).textContent).toContain('Sonrisas del Valle')
  })

  it('carga la ficha vigente con el token y deja «Guardar cambios» deshabilitado sin cambios (R41)', async () => {
    const { f, dialogo } = await abrirEditar()
    expect(within(dialogo).getByRole('heading', { name: 'Editar empresa' })).toBeTruthy()
    expect(await within(dialogo).findByDisplayValue('Odontología Sonrisa')).toBeTruthy()
    expect(enDialogo(dialogo, /^Dirección/).value).toBe(VIGENTE.direccion)
    expect(enDialogo(dialogo, /^NIT/).value).toBe(VIGENTE.nit)
    expect(enDialogo(dialogo, /^Teléfono/).value).toBe(VIGENTE.telefono)
    expect(enDialogo(dialogo, /^Correo de la empresa/).value).toBe(VIGENTE.correo)
    expect(guardar(dialogo).disabled).toBe(true)
    const [, init] = llamadas(f, URL_FICHA)[0]
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer jwt.plataforma')
    // Bloque del logo: tiene logo, se reemplaza.
    expect(within(dialogo).getByText('Tiene logo')).toBeTruthy()
    expect(within(dialogo).getByText(/160 × 64 px/)).toBeTruthy()
    expect((within(dialogo).getByRole('button', { name: 'Reemplazar logo' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('sin logo: «Sin logo» y «Subir logo»', async () => {
    const { dialogo } = await abrirEditar({ ficha: { ...VIGENTE, tiene_logo: false } })
    expect(await within(dialogo).findByText('Sin logo')).toBeTruthy()
    expect(within(dialogo).getByRole('button', { name: 'Subir logo' })).toBeTruthy()
  })

  it('mientras carga lo dice; si falla, ofrece reintentar', async () => {
    let intentos = 0
    const { dialogo } = await abrirEditar({
      extra: (url) => {
        if (url !== URL_FICHA) return undefined
        intentos += 1
        return intentos === 1 ? new Promise<Response>((listo) => setTimeout(() => listo(errorApi(503, 'servicio_no_disponible')), 30)) : json(200, VIGENTE)
      },
    })
    expect(within(dialogo).getByRole('status', { name: 'Cargando los datos de la empresa' })).toBeTruthy()
    expect(await within(dialogo).findByText('No se pudieron cargar los datos de la empresa')).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reintentar' }))
    expect(await within(dialogo).findByDisplayValue('Odontología Sonrisa')).toBeTruthy()
  })

  it('409 empresa_sin_datos: explica que los completa su admin y no muestra el formulario', async () => {
    const { dialogo } = await abrirEditar({ ficha: errorApi(409, 'empresa_sin_datos', 'La empresa no tiene sus datos.') })
    expect(await within(dialogo).findByText(/Esta empresa aún no tiene sus datos/)).toBeTruthy()
    expect(within(dialogo).queryByRole('button', { name: 'Guardar cambios' })).toBeNull()
  })

  it('guarda con PUT de las cinco claves (vacío quita el opcional) y refresca la lista (R42, Q-E1)', async () => {
    const nueva = { ...VIGENTE, nombre: 'Odontología Sonrisa S.A.S.', telefono: null }
    const { f, dialogo } = await abrirEditar({
      extra: (url, init) => (url === URL_FICHA && init.method === 'PUT' ? json(200, nueva) : undefined),
    })
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    const listasAntes = llamadas(f, '/api/plataforma/empresas?estado=todas').length
    fireEvent.change(enDialogo(dialogo, /^Nombre o razón social/), { target: { value: 'Odontología Sonrisa S.A.S.' } })
    fireEvent.change(enDialogo(dialogo, /^Teléfono/), { target: { value: '' } })
    expect(guardar(dialogo).disabled).toBe(false)
    fireEvent.click(guardar(dialogo))
    await waitFor(() => expect(llamadas(f, URL_FICHA, 'PUT')).toHaveLength(1))
    const [, init] = llamadas(f, URL_FICHA, 'PUT')[0]
    expect(cuerpo(init)).toEqual({
      nombre: 'Odontología Sonrisa S.A.S.',
      direccion: VIGENTE.direccion,
      nit: VIGENTE.nit,
      telefono: null,
      correo: VIGENTE.correo,
    })
    expect(await screen.findByText('Cambios guardados en Odontología Sonrisa S.A.S.')).toBeTruthy()
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(llamadas(f, '/api/plataforma/empresas?estado=todas').length).toBeGreaterThan(listasAntes))
  })

  it('valida en el campo antes de enviar y lleva el foco al que falla', async () => {
    const { f, dialogo } = await abrirEditar()
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    fireEvent.change(enDialogo(dialogo, /^NIT/), { target: { value: '900123456-1' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('El NIT no es válido: revisa los números y el dígito de verificación.')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(enDialogo(dialogo, /^NIT/)))
    expect(llamadas(f, URL_FICHA, 'PUT')).toHaveLength(0)
  })

  it('422 del servidor con campo: el error queda en ese campo', async () => {
    const { dialogo } = await abrirEditar({
      extra: (url, init) =>
        url === URL_FICHA && init.method === 'PUT'
          ? json(422, { error: { code: 'campo_invalido', message: 'El correo del servidor no es válido.', request_id: 'x', campo: 'correo' } })
          : undefined,
    })
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    fireEvent.change(enDialogo(dialogo, /^Correo de la empresa/), { target: { value: 'otro@bio.test' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('El correo del servidor no es válido.')).toBeTruthy()
    expect(enDialogo(dialogo, /^Correo de la empresa/).getAttribute('aria-invalid')).toBe('true')
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('503 al guardar: lo dice en el diálogo, que sigue abierto con lo escrito', async () => {
    const { dialogo } = await abrirEditar({
      extra: (url, init) => (url === URL_FICHA && init.method === 'PUT' ? errorApi(503, 'servicio_no_disponible') : undefined),
    })
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    fireEvent.change(enDialogo(dialogo, /^Dirección/), { target: { value: 'Calle 1, Cartago' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText(/El servicio no está disponible/)).toBeTruthy()
    expect(enDialogo(dialogo, /^Dirección/).value).toBe('Calle 1, Cartago')
  })

  it('reemplaza el logo: vista previa del archivo y multipart con logo_id y archivo (R44)', async () => {
    const { f, dialogo } = await abrirEditar({
      extra: (url, init) => (url === URL_LOGO && init.method === 'POST' ? json(201, { logo: { id: 'x' } }) : undefined),
    })
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    elegirLogoEditar(png('nuevo.png'))
    expect(within(dialogo).getByRole('img', { name: 'Vista previa del logo' })).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reemplazar logo' }))
    expect(await screen.findByText('Logo de Odontología Sonrisa reemplazado')).toBeTruthy()
    const [, init] = llamadas(f, URL_LOGO, 'POST')[0]
    const form = formLogo(init)
    expect([...form.keys()].sort()).toEqual(['archivo', 'logo_id'])
    expect(String(form.get('logo_id'))).toMatch(UUID)
    // El PUT de la ficha no se envía por subir el logo.
    expect(llamadas(f, URL_FICHA, 'PUT')).toHaveLength(0)
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it.each([
    [413, 'foto_demasiado_grande', 'La imagen pesa más de 2 MB. Elige una más liviana.', 'Elegir otra imagen'],
    [415, 'tipo_no_admitido', 'Mensaje del servidor.', 'Elegir otra imagen'],
    [503, 'logos_no_disponibles', 'El almacenamiento de imágenes no está disponible en este servidor.', 'Reintentar'],
  ])('error %i al subir el logo: lo dice con su acción y el logo vigente sigue', async (status, code, mensaje, accion) => {
    const { dialogo } = await abrirEditar({
      extra: (url, init) => (url === URL_LOGO && init.method === 'POST' ? errorApi(status, code) : undefined),
    })
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    elegirLogoEditar(png())
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reemplazar logo' }))
    const aviso = await within(dialogo).findByRole('alert')
    expect(aviso.textContent).toContain(mensaje)
    expect(within(aviso).getByRole('button', { name: accion })).toBeTruthy()
    expect(within(dialogo).getByText('Tiene logo')).toBeTruthy()
  })

  it('503 al subir el logo: «Reintentar» repite el mismo logo_id', async () => {
    let intentos = 0
    const { f, dialogo } = await abrirEditar({
      extra: (url, init) => {
        if (url !== URL_LOGO || init.method !== 'POST') return undefined
        intentos += 1
        return intentos === 1 ? errorApi(503, 'servicio_no_disponible') : json(201, { logo: { id: 'x' } })
      },
    })
    await within(dialogo).findByDisplayValue('Odontología Sonrisa')
    elegirLogoEditar(png())
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reemplazar logo' }))
    fireEvent.click(await within(dialogo).findByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Logo de Odontología Sonrisa reemplazado')).toBeTruthy()
    const ids = llamadas(f, URL_LOGO, 'POST').map(([, i]) => formLogo(i).get('logo_id'))
    expect(ids).toHaveLength(2)
    expect(ids[0]).toBe(ids[1])
  })
})

describe('reglas del módulo (api.ts)', () => {
  it('filtrarEmpresas y nombreRepetido ignoran mayúsculas y espacios', () => {
    expect(filtrarEmpresas(LISTA, '  NORTE ', 'todas').map((e) => e.nombre)).toEqual(['Odonto Norte'])
    expect(filtrarEmpresas(LISTA, '', 'activas')).toHaveLength(2)
    expect(nombreRepetido(LISTA, 'sonrisas del valle')).toBe(true)
    expect(nombreRepetido(LISTA, 'Sonrisas')).toBe(false)
    expect(nombreRepetido(undefined, 'x')).toBe(false)
  })

  it('validarAlta normaliza el correo y no devuelve la contraseña', () => {
    const r = validarAlta(
      { nombre: 'Clínica', direccion: 'Calle 1', nit: '', telefono: '', correo: '' },
      { nombre: '  Ana   Torres ', email: ' ANA@X.TEST ' },
      CLAVE,
      CLAVE,
    )
    expect(r.admin).toEqual({ nombre: 'Ana Torres', email: 'ana@x.test' })
    expect(JSON.stringify(r)).not.toContain(CLAVE)
  })

  it('errorDeAlta, errorDeLogo y errorDeFicha traducen los códigos del contrato', async () => {
    const { ErrorApi } = await import('@/lib/api/cliente')
    expect(errorDeAlta(new ErrorApi(429, 'demasiadas_solicitudes', 'x', undefined, undefined, 120)).mensaje).toContain('2 minutos')
    expect(errorDeLogo(new ErrorApi(415, 'tipo_no_admitido' as never, 'Tipo no admitido.')).otroArchivo).toBe(true)
    expect(errorDeLogo(new ErrorApi(413, 'foto_demasiado_grande' as never, 'Muy grande.')).otroArchivo).toBe(true)
    expect(errorDeLogo(new ErrorApi(409, 'logo_id_en_uso', 'x')).idNuevo).toBe(true)
    expect(errorDeLogo(new ErrorApi(0, 'sin_conexion', 'Sin conexión.')).reintentar).toBe(true)
    // C1: ya no hay «la empresa ya tiene logo»; el logo se reemplaza.
    expect(Object.keys(errorDeLogo(new ErrorApi(503, 'logos_no_disponibles', 'x')))).not.toContain('yaTieneLogo')
    expect(errorDeFicha(new ErrorApi(409, 'empresa_sin_datos', 'x')).mensaje).toContain('Los completa su admin')
    expect(errorDeFicha(new ErrorApi(422, 'campo_invalido', 'NIT malo.', undefined, { error: { campo: 'nit' } }))).toEqual({
      tipo: 'campo',
      campo: 'nit',
      mensaje: 'NIT malo.',
    })
    // Un campo que no es de la ficha (p. ej. del admin) no se pinta en un campo inexistente.
    expect(errorDeFicha(new ErrorApi(422, 'campo_invalido', 'x', undefined, { error: { campo: 'admin.email' } })).tipo).toBe('general')
  })
})
