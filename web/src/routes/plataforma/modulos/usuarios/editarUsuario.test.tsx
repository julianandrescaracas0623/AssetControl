import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ErrorApi, type Esquemas } from '@/lib/api/cliente'
import { routes } from '@/router'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, json } from '@/test/sesion'

import { errorDeEdicion, nombreNormalizado } from './api'

// Spec 017, C1/T15 (R47–R52; CU-13; A24, A25 en la web): «Editar» por fila en Usuarios abre
// un diálogo con el correo (solo lectura), el nombre y el rol. Rutas reales, API simulada.

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

type Manejador = (url: string, init: RequestInit) => Response | Promise<Response | undefined> | undefined

function abrir(path: string, { usuarios = USUARIOS, extra }: { usuarios?: Usuario[]; extra?: Manejador } = {}) {
  const f = vi.fn(async (entrada: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(entrada)
    const propia = await extra?.(url, init)
    if (propia) return propia
    if (url === '/api/plataforma/auth/refresh') return json(200, SESION)
    if (url === '/api/plataforma/modulos') return json(200, { modulos: MODULOS })
    if (url === '/api/plataforma/empresas?estado=todas') return json(200, { empresas: EMPRESAS })
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
const ruta = (usuario: string) => `/api/plataforma/empresas/${ACTIVA}/usuarios/${usuario}`
const listaUrl = `/api/plataforma/empresas/${ACTIVA}/usuarios`

async function abrirEdicion(nombre: string) {
  const boton = (await screen.findByRole('button', { name: `Editar a ${nombre}` })) as HTMLButtonElement
  await waitFor(() => expect(boton.disabled).toBe(false))
  fireEvent.click(boton)
  return screen.findByRole('dialog')
}

const guardar = (dialogo: HTMLElement) => within(dialogo).getByRole('button', { name: 'Guardar cambios' }) as HTMLButtonElement
const campoNombre = (dialogo: HTMLElement) => within(dialogo).getByRole('textbox', { name: /Nombre/ }) as HTMLInputElement

async function elegirRol(dialogo: HTMLElement, rol: 'Admin' | 'Contador') {
  fireEvent.click(within(dialogo).getByRole('combobox', { name: /Rol/ }))
  fireEvent.click(within(await screen.findByRole('listbox')).getByRole('option', { name: rol }))
}

const pidePut = (manejar: (init: RequestInit, n: number) => Response, usuario = LUIS.id): Manejador => {
  let n = 0
  return (url, init) => {
    if (url !== ruta(usuario) || init.method !== 'PUT') return undefined
    n += 1
    return manejar(init, n)
  }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('abrir Editar usuario (CU-13; R52)', () => {
  it('cada fila tiene «Editar» junto a Desactivar/Reactivar', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const tabla = await screen.findByRole('table', { name: 'Usuarios de Biotecnología Dental' })
    for (const u of USUARIOS) {
      const fila = within(tabla).getByText(u.nombre).closest('tr')!
      expect(within(fila).getByRole('button', { name: `Editar a ${u.nombre}` })).toBeTruthy()
      expect(within(fila).getByRole('button', { name: `${u.activa ? 'Desactivar' : 'Reactivar'} a ${u.nombre}` })).toBeTruthy()
    }
  })

  it('muestra el correo solo de lectura, el nombre y el rol; «Guardar» empieza deshabilitado', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirEdicion('Luis Pérez')
    expect(within(dialogo).getByRole('heading', { name: 'Editar usuario' })).toBeTruthy()
    expect(dialogo.textContent).toContain('Biotecnología Dental')
    const correo = within(dialogo).getByRole('textbox', { name: /Correo/ }) as HTMLInputElement
    expect(correo.value).toBe('luis@clinica.test')
    expect(correo.disabled).toBe(true)
    expect(dialogo.textContent).toContain('El correo no se cambia desde la consola')
    expect(campoNombre(dialogo).value).toBe('Luis Pérez')
    expect(within(dialogo).getByRole('combobox', { name: /Rol/ }).textContent).toContain('Contador')
    expect(guardar(dialogo).disabled).toBe(true)
  })

  it('avisa que el nombre es de la persona en todas sus empresas y que cambiar el rol cierra su sesión (R49, R51)', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirEdicion('Luis Pérez')
    const nombre = campoNombre(dialogo)
    const ayudaNombre = document.getElementById(nombre.getAttribute('aria-describedby')!.split(' ')[0])!
    expect(ayudaNombre.textContent).toMatch(/si tiene acceso a otra empresa, allí también cambia/i)
    expect(dialogo.textContent).toMatch(/Cambiar el rol cierra su sesión abierta/)
  })

  it('una membresía desactivada se puede editar y lo dice (R51)', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirEdicion('Eva Gil')
    expect(dialogo.textContent).toContain('El acceso de Eva Gil a Biotecnología Dental está desactivado. Puedes editar su nombre y su rol')
    expect(campoNombre(dialogo).disabled).toBe(false)
  })

  it('a 375 px la tarjeta también tiene «Editar»', async () => {
    simularAncho({ movil: true })
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const lista = await screen.findByRole('list', { name: 'Usuarios de Biotecnología Dental' })
    expect(within(lista).getByRole('button', { name: 'Editar a Luis Pérez' })).toBeTruthy()
    expect(within(lista).getByRole('button', { name: 'Desactivar a Luis Pérez' })).toBeTruthy()
  })

  // Ajuste T15b (C1): cuadro centrado y doble clic sobre la fila.
  it('«Editar» abre un cuadro de diálogo centrado, también a 375 px', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    expect((await abrirEdicion('Luis Pérez')).getAttribute('data-forma')).toBe('centrado')
    cleanup()
    simularAncho({ movil: true })
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    expect((await abrirEdicion('Luis Pérez')).getAttribute('data-forma')).toBe('centrado')
  })

  it('doble clic sobre la fila abre Editar usuario de esa persona, con la pista en la fila', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const tabla = await screen.findByRole('table', { name: 'Usuarios de Biotecnología Dental' })
    await waitFor(() => expect((screen.getByRole('button', { name: 'Editar a Luis Pérez' }) as HTMLButtonElement).disabled).toBe(false))
    const fila = within(tabla).getByText('Luis Pérez').closest('tr')!
    expect(fila.getAttribute('title')).toBe('Doble clic para editar')
    fireEvent.doubleClick(within(fila).getByText('luis@clinica.test'))
    const dialogo = await screen.findByRole('dialog', { name: 'Editar usuario' })
    expect(campoNombre(dialogo).value).toBe('Luis Pérez')
  })

  it('doble clic en el botón «Editar» abre un solo diálogo; en «Desactivar» no abre Editar', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const editar = (await screen.findByRole('button', { name: 'Editar a Luis Pérez' })) as HTMLButtonElement
    await waitFor(() => expect(editar.disabled).toBe(false))
    fireEvent.click(editar)
    fireEvent.click(editar)
    fireEvent.doubleClick(editar)
    expect(await screen.findAllByRole('dialog')).toHaveLength(1)
    cleanup()
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const desactivar = (await screen.findByRole('button', { name: 'Desactivar a Luis Pérez' })) as HTMLButtonElement
    await waitFor(() => expect(desactivar.disabled).toBe(false))
    fireEvent.doubleClick(desactivar)
    expect(screen.queryByRole('dialog', { name: 'Editar usuario' })).toBeNull()
  })

  it('empresa desactivada: el doble clic sobre la fila tampoco abre Editar', async () => {
    abrir(`/plataforma/usuarios?empresa=${INACTIVA}`)
    const tabla = await screen.findByRole('table', { name: 'Usuarios de Sonrisas del Valle' })
    await waitFor(() => expect(screen.getByText('Esta empresa está desactivada')).toBeTruthy())
    const fila = within(tabla).getByText('Luis Pérez').closest('tr')!
    expect(fila.getAttribute('title')).toBeNull()
    expect(fila.getAttribute('tabindex')).toBeNull()
    fireEvent.doubleClick(within(fila).getByText('luis@clinica.test'))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('empresa desactivada: «Editar» queda deshabilitado con la explicación', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${INACTIVA}`)
    await screen.findByRole('table', { name: 'Usuarios de Sonrisas del Valle' })
    const boton = screen.getByRole('button', { name: 'Editar a Luis Pérez' }) as HTMLButtonElement
    await waitFor(() => expect(screen.getByText('Esta empresa está desactivada')).toBeTruthy())
    expect(boton.disabled).toBe(true)
    expect(document.getElementById(boton.getAttribute('aria-describedby')!)!.textContent).toContain('primero reactiva la empresa')
    fireEvent.click(boton)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(llamadas(f, /\/usuarios\//, 'PUT')).toHaveLength(0)
  })
})

describe('guardar (R47, R49, R50)', () => {
  it('solo el nombre: PUT con exactamente {nombre, rol}, sin confirmar; cierra y refresca la lista', async () => {
    let hecho = false
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: (url, init) => {
        if (url === ruta(LUIS.id) && init.method === 'PUT') {
          hecho = true
          return json(200, { id: LUIS.id, nombre: 'Luis A. Pérez', rol: 'contador' })
        }
        if (url === listaUrl && hecho) return json(200, { usuarios: USUARIOS.map((u) => (u.id === LUIS.id ? { ...u, nombre: 'Luis A. Pérez' } : u)) })
        return undefined
      },
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: '  Luis A. Pérez  ' } })
    expect(guardar(dialogo).disabled).toBe(false)
    fireEvent.click(guardar(dialogo))
    await waitFor(() => expect(llamadas(f, ruta(LUIS.id), 'PUT')).toHaveLength(1))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    const [, init] = llamadas(f, ruta(LUIS.id), 'PUT')[0]
    expect(cuerpo(init)).toEqual({ nombre: 'Luis A. Pérez', rol: 'contador' })
    expect(Object.keys(cuerpo(init)).sort()).toEqual(['nombre', 'rol'])
    expect(new Headers((init as RequestInit).headers).get('Authorization')).toBe('Bearer jwt.plataforma')
    // El PATCH (estado) no se usa para editar.
    expect(llamadas(f, /\/usuarios\//, 'PATCH')).toHaveLength(0)
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('Luis A. Pérez')).toBeTruthy()
    await waitFor(() => expect(llamadas(f, listaUrl, 'GET').length).toBeGreaterThan(1))
    await waitFor(() => expect(llamadas(f, '/api/plataforma/empresas?estado=todas').length).toBeGreaterThan(1))
  })

  it('volver al valor original (o solo espacios alrededor) deja «Guardar» deshabilitado', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: 'Luis' } })
    expect(guardar(dialogo).disabled).toBe(false)
    fireEvent.change(campoNombre(dialogo), { target: { value: ' Luis Pérez ' } })
    expect(guardar(dialogo).disabled).toBe(true)
  })

  it('nombre vacío: error en el campo y no se envía nada', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: '   ' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('Escribe el nombre de la persona (máximo 120 caracteres).')).toBeTruthy()
    expect(campoNombre(dialogo).getAttribute('aria-invalid')).toBe('true')
    expect(llamadas(f, /\/usuarios\//, 'PUT')).toHaveLength(0)
  })

  it('cambiar el rol pide Confirmar con persona, empresa y efecto; cancelar no envía', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`)
    const dialogo = await abrirEdicion('Luis Pérez')
    await elegirRol(dialogo, 'Admin')
    fireEvent.click(guardar(dialogo))
    const confirmar = await screen.findByRole('alertdialog')
    expect(within(confirmar).getByRole('heading', { name: '¿Hacer admin a Luis Pérez?' })).toBeTruthy()
    expect(confirmar.textContent).toContain('Luis Pérez pasará a ser admin en Biotecnología Dental.')
    expect(confirmar.textContent).toContain('Su sesión abierta se cerrará y tendrá los permisos de admin.')
    fireEvent.click(within(confirmar).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(llamadas(f, /\/usuarios\//, 'PUT')).toHaveLength(0)
    // El diálogo de edición sigue abierto con lo escrito.
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('al confirmar el cambio de rol envía {nombre, rol: "contador"}', async () => {
    const otraAdmin = { ...LUIS, rol: 'admin' as const }
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      usuarios: [ANA, otraAdmin, EVA],
      extra: pidePut(() => json(200, { id: LUIS.id, nombre: 'Luis Pérez', rol: 'contador' })),
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    await elegirRol(dialogo, 'Contador')
    fireEvent.click(guardar(dialogo))
    const confirmar = await screen.findByRole('alertdialog')
    expect(within(confirmar).getByRole('heading', { name: '¿Cambiar a Luis Pérez a contador?' })).toBeTruthy()
    expect(confirmar.textContent).toContain('tendrá los permisos de contador')
    fireEvent.click(within(confirmar).getByRole('button', { name: 'Sí, cambiar el rol' }))
    await waitFor(() => expect(llamadas(f, ruta(LUIS.id), 'PUT')).toHaveLength(1))
    expect(cuerpo(llamadas(f, ruta(LUIS.id), 'PUT')[0][1])).toEqual({ nombre: 'Luis Pérez', rol: 'contador' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})

describe('rechazos del servidor (R48; A24)', () => {
  it('409 ultimo_admin: lo dice claro, sin «Reintentar», y refresca la lista', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePut(() => errorApi(409, 'ultimo_admin', 'No se puede quitar el rol admin al último admin activo.'), ANA.id),
    })
    const dialogo = await abrirEdicion('Ana Torres')
    await elegirRol(dialogo, 'Contador')
    fireEvent.click(guardar(dialogo))
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Sí, cambiar el rol' }))
    const titulo = await within(dialogo).findByText('No se puede quitar el rol admin al último admin activo de la empresa')
    const aviso = titulo.closest('[data-kit=aviso]') as HTMLElement
    expect(aviso.textContent).toContain('Biotecnología Dental necesita al menos un admin activo')
    expect(aviso.textContent).toContain('No se cambió nada')
    expect(within(aviso).queryByRole('button', { name: 'Reintentar' })).toBeNull()
    await waitFor(() => expect(llamadas(f, listaUrl, 'GET').length).toBe(2))
  })

  it('409 empresa_inactiva: lo explica y vuelve a pedir las empresas', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePut(() => errorApi(409, 'empresa_inactiva', 'La empresa está desactivada.')),
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: 'Luis Pérez Gómez' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('Esta empresa está desactivada')).toBeTruthy()
    expect(dialogo.textContent).toContain('Reactiva Biotecnología Dental en Empresas')
    await waitFor(() => expect(llamadas(f, '/api/plataforma/empresas?estado=todas').length).toBeGreaterThan(1))
  })

  it('404: el usuario ya no es de la empresa; refresca la lista', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePut(() => errorApi(404, 'no_encontrado', 'Ese usuario no pertenece a esta empresa.')),
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: 'Luis Pérez Gómez' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('Ese usuario ya no aparece en esta empresa')).toBeTruthy()
    await waitFor(() => expect(llamadas(f, listaUrl, 'GET').length).toBe(2))
  })

  it('422 con campo: el error va en su campo', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePut(() =>
        json(422, { error: { code: 'campo_invalido', message: 'El nombre no es válido.', request_id: 'r', campo: 'nombre' } }),
      ),
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: 'Luis 🙂' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('El nombre no es válido.')).toBeTruthy()
    await waitFor(() => expect(campoNombre(dialogo).getAttribute('aria-invalid')).toBe('true'))
  })

  it('503: «Reintentar» repite el mismo PUT', async () => {
    const { f } = abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePut((_, n) =>
        n === 1 ? errorApi(503, 'servicio_no_disponible', 'No disponible.') : json(200, { id: LUIS.id, nombre: 'Luis Pérez Gómez', rol: 'contador' }),
      ),
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: 'Luis Pérez Gómez' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('El servicio no está disponible en este momento')).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(llamadas(f, ruta(LUIS.id), 'PUT')).toHaveLength(2))
    for (const [, init] of llamadas(f, ruta(LUIS.id), 'PUT')) expect(cuerpo(init)).toEqual({ nombre: 'Luis Pérez Gómez', rol: 'contador' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('429: dice cuánto esperar y permite reintentar', async () => {
    abrir(`/plataforma/usuarios?empresa=${ACTIVA}`, {
      extra: pidePut(() => json(429, { error: { code: 'demasiadas_solicitudes', message: 'x', request_id: 'r' } }, { 'Retry-After': '120' })),
    })
    const dialogo = await abrirEdicion('Luis Pérez')
    fireEvent.change(campoNombre(dialogo), { target: { value: 'Luis Pérez Gómez' } })
    fireEvent.click(guardar(dialogo))
    expect(await within(dialogo).findByText('Hiciste varias acciones seguidas')).toBeTruthy()
    expect(within(dialogo).getByText('Espera 2 minutos e intenta de nuevo.')).toBeTruthy()
    expect(within(dialogo).getByRole('button', { name: 'Reintentar' })).toBeTruthy()
  })
})

describe('reglas de edición (api.ts)', () => {
  it('nombreNormalizado: NFC y sin espacios alrededor; vacío o sin letras ni números es null', () => {
    expect(nombreNormalizado('  Ana  Torres ')).toBe('Ana  Torres')
    expect(nombreNormalizado('José')).toBe('José')
    expect(nombreNormalizado('   ')).toBeNull()
    expect(nombreNormalizado('---')).toBeNull()
    expect(nombreNormalizado('a'.repeat(121))).toBeNull()
    expect(nombreNormalizado('a'.repeat(120))).toBe('a'.repeat(120))
  })

  it('errorDeEdicion traduce los códigos del contrato', () => {
    const e = (status: number, code: string) => new ErrorApi(status, code as never, 'mensaje')
    expect(errorDeEdicion(e(409, 'ultimo_admin'), 'X')).toMatchObject({ tipo: 'general', reintentar: false })
    expect(errorDeEdicion(e(409, 'empresa_inactiva'), 'X')).toMatchObject({ titulo: 'Esta empresa está desactivada', reintentar: false })
    expect(errorDeEdicion(e(404, 'no_encontrado'), 'X')).toMatchObject({ reintentar: false })
    expect(errorDeEdicion(e(503, 'servicio_no_disponible'), 'X')).toMatchObject({ reintentar: true })
    expect(errorDeEdicion(e(0, 'sin_conexion'), 'X')).toMatchObject({ titulo: 'Sin conexión con el servidor', reintentar: true })
    expect(errorDeEdicion(e(400, 'solicitud_invalida'), 'X')).toMatchObject({ reintentar: false })
    expect(errorDeEdicion(new Error('x'), 'X')).toMatchObject({ reintentar: true })
  })
})
