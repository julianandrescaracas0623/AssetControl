import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { guardarSala } from '@/lib/conteo'
import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { lectorFalso } from '@/test/lector'
import { simularAncho, simularEscritorio } from '@/test/matchMedia'
import { errorApi, llamadas, simularSesion } from '@/test/sesion'

// Spec 004, T6 (R3, R4, R6, Q3; A5): altas reales sin cámara, en conteo y en
// administración. El `id` se reutiliza en cada reintento; el contador no ve precios.

afterEach(cleanup)

const lector = vi.hoisted(() => ({ actual: null as ReturnType<typeof import('@/test/lector').lectorFalso> | null }))
vi.mock('@/lib/lector', async (original) => ({
  ...(await original<typeof import('@/lib/lector')>()),
  crearLectorZxing: (...args: Parameters<import('@/lib/lector').CrearLector>) => lector.actual!.crear(...args),
}))

function abrir(path: string, rol: Rol = 'admin', catalogo = catalogoDemo(rol)) {
  simularAncho({ movil: rol === 'contador' })
  const f = simularSesion(rol, catalogo.manejador)
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
  return { f, catalogo }
}

const posts = (f: ReturnType<typeof simularSesion>) =>
  llamadas(f, '/api/activos')
    .filter(([, init]) => init?.method === 'POST')
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>)

async function elegir(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.click(disparador)
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

async function elegirSelect(etiqueta: RegExp, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: etiqueta })
  await waitFor(() => expect(disparador.hasAttribute('disabled')).toBe(false))
  fireEvent.keyDown(disparador, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

describe('alta en administración', () => {
  it('no guarda sin código, nombre, precio, categoría ni ubicación', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await screen.findByRole('heading', { level: 1, name: 'Registrar activo' })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    for (const mensaje of ['Escanea o escribe el código del sticker', 'Escribe el nombre', 'Escribe el precio', 'Elige la categoría', 'Elige la ubicación']) {
      expect(screen.getByText(mensaje)).toBeTruthy()
    }
    expect(posts(f)).toHaveLength(0)
  })

  it('avisa que un código ya existe y enlaza al activo', async () => {
    abrir('/admin/activos/nuevo')
    fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: '000123' } })
    expect(await screen.findByText(/Ese código ya existe: Silla ergonómica/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Abrir activo' }).getAttribute('href')).toBe('/app/activos/000123')
  })

  it('copia de un parecido (con precio para el admin) y guarda con el precio canónico', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: 'ac-0458' } })
    expect(await screen.findByText('Código libre')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    expect((screen.getByRole('combobox', { name: /Nombre/ }) as HTMLInputElement).value).toBe('Silla ergonómica')
    expect((screen.getByRole('textbox', { name: /Precio de compra/ }) as HTMLInputElement).value).toBe('389.900')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [cuerpo] = posts(f)
    expect(cuerpo).toMatchObject({
      codigo: 'AC-0458',
      nombre: 'Silla ergonómica',
      precio_compra: '389900.00',
      categoria_id: '00000000-0000-4000-8000-0000000000c2',
      ubicacion_id: '00000000-0000-4000-8000-0000000000a4',
      marca: 'Rimax',
    })
    expect(cuerpo).not.toHaveProperty('copiar_de')
    expect(String(cuerpo.id)).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('un error de red ofrece reintentar con el mismo id', async () => {
    const { f, catalogo } = abrir('/admin/activos/nuevo')
    catalogo.fallar('POST /api/activos', () => new Response('<html></html>', { status: 502 }))
    fireEvent.change(await screen.findByRole('textbox', { name: /Código del sticker/ }), { target: { value: 'NUEVO-1' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Lámpara' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '120.000' } })
    await elegirSelect(/Categoría/, 'Mobiliario')
    await elegir(/Ubicación/, 'Administración')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [primero, segundo] = posts(f)
    expect(segundo.id).toBe(primero.id)
    expect(primero.precio_compra).toBe('120000.00')
  })
})

describe('alta en el modo conteo', () => {
  it('el contador duplica sin ver ni enviar precio y elige la ubicación', async () => {
    const { f, catalogo } = abrir('/contar/nuevo?codigo=ac-0500', 'contador')
    expect(await screen.findByText('AC-0500')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Coincide' }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    expect(screen.queryByRole('textbox', { name: /Precio/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    const [cuerpo] = posts(f)
    expect(Object.keys(cuerpo).sort()).toEqual(['codigo', 'copiar_de', 'id', 'serial', 'ubicacion_id'])
    expect(cuerpo).toMatchObject({ codigo: 'AC-0500', copiar_de: '00000000-0000-4000-8000-0000000000d2' })
    expect(document.body.textContent).not.toContain('389')
    expect(catalogo.activos[0].precio_compra).toBe('389900.00')
  })

  it('un código que ya existe ofrece abrir el activo', async () => {
    const { catalogo } = abrir('/contar/nuevo?codigo=NUEVO-2', 'contador')
    catalogo.activos.push({ ...catalogo.activos[0], id: '00000000-0000-4000-8000-0000000000d9', codigo: 'NUEVO-2' })
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Coincide' }))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Silla' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio/ }), { target: { value: '10' } })
    await elegirSelect(/Categoría/, 'Mobiliario')
    await elegir(/Ubicación/, 'Administración')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    const aviso = await screen.findByText('Ese código ya está registrado')
    expect(within(aviso.closest('[data-slot=alert]')!).getByRole('link', { name: 'Abrir activo' }).getAttribute('href')).toBe('/contar/activo/NUEVO-2')
  })

  it('un precio en formato colombiano se envía canónico; uno mal escrito se marca', async () => {
    const { f, catalogo } = abrir('/contar/nuevo?codigo=NUEVO-3', 'contador')
    catalogo.fallar('POST /api/activos', () => errorApi(400, 'ubicacion_invalida', 'Elige una sala o un box activos.'))
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Coincide' }))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Monitor' } })
    const precio = screen.getByRole('textbox', { name: /Precio/ })
    fireEvent.change(precio, { target: { value: '1.2.3' } })
    await elegirSelect(/Categoría/, 'Electrónica')
    await elegir(/Ubicación/, 'Consultorio 1 › Box 2')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(screen.getByText('Escribe el precio en pesos, por ejemplo 389.900')).toBeTruthy()
    fireEvent.change(precio, { target: { value: '1.250.000,50' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Elige una sala o un box activos.')).toBeTruthy()
    expect(posts(f)[0].precio_compra).toBe('1250000.50')
  })
})

describe('sugerencias (T7)', () => {
  it('al enfocar nombre y marca sugiere lo ya registrado, sin precio', async () => {
    const { f } = abrir('/contar/nuevo?codigo=NUEVO-4', 'contador')
    const nombre = await screen.findByRole('combobox', { name: /Nombre/ })
    fireEvent.focus(nombre)
    fireEvent.change(nombre, { target: { value: 'sil' } })
    const lista = document.getElementById(nombre.getAttribute('list')!)!
    await waitFor(() => expect([...lista.querySelectorAll('option')].map((o) => o.value)).toEqual(['Silla ergonómica']))
    const pedidas = f.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith('/api/activos/sugerencias'))
    expect(pedidas.at(-1)).toBe('/api/activos/sugerencias?campo=nombre&q=sil')
    expect(lista.textContent).not.toContain('389')
  })
})

describe('escanear en administración (T8)', () => {
  it('la cámara llena el código normalizado y cierra el visor', async () => {
    lector.actual = lectorFalso()
    abrir('/admin/activos/nuevo')
    fireEvent.click(await screen.findByRole('button', { name: 'Usar la cámara' }))
    await screen.findByText('Cámara activa')
    act(() => lector.actual!.leer('ac-0777'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect((screen.getByRole('textbox', { name: /Código del sticker/ }) as HTMLInputElement).value).toBe('AC-0777')
    expect(lector.actual.detenido).toBe(1)
  })
})

// Spec 015, T10 (R11; Q9 = A; maquetas t10-registrar-A, t10-registrar-otro, t10-contar-nuevo):
// dos columnas en escritorio, foco inicial, Enter del lector en el código pasa a Nombre,
// Enter guarda en los demás campos y Ctrl+Enter es «Guardar y registrar otro», que conserva
// categoría, ubicación, marca, modelo y subtipo y borra código, nombre, precio, serial y foto.

const valor = (nombre: RegExp, rol: 'textbox' | 'combobox' = 'textbox') => (screen.getByRole(rol, { name: nombre }) as HTMLInputElement).value

async function llenarAdmin(codigo: string) {
  const campoCodigo = await screen.findByRole('textbox', { name: /Código del sticker/ })
  fireEvent.change(campoCodigo, { target: { value: codigo } })
  fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
  fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Silla auxiliar' } })
  fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '1.250.000' } })
  await elegirSelect(/Categoría/, 'Mobiliario')
  await elegir(/Ubicación/, 'Consultorio 1 › Box 2')
  fireEvent.change(screen.getByRole('combobox', { name: /Marca/ }), { target: { value: 'Ergodent' } })
  fireEvent.change(screen.getByRole('combobox', { name: /Modelo/ }), { target: { value: 'SA-40' } })
  fireEvent.change(screen.getByRole('combobox', { name: /Subtipo/ }), { target: { value: 'Silla' } })
  fireEvent.change(screen.getByRole('textbox', { name: /Serial/ }), { target: { value: 'EG-1' } })
  await focoDevuelto()
}

/** Radix devuelve el foco al selector en un `setTimeout(0)` al cerrarse: esperarlo. */
const focoDevuelto = () => act(() => new Promise((listo) => setTimeout(listo, 0)))

describe('Registrar activo mejorado en administración (015-T10)', () => {
  it('el foco empieza en el código y su Enter pasa a Nombre sin guardar', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    const codigo = await screen.findByRole('textbox', { name: /Código del sticker/ })
    await waitFor(() => expect(document.activeElement).toBe(codigo))
    fireEvent.change(codigo, { target: { value: 'NUEVO-10' } })
    fireEvent.keyDown(codigo, { key: 'Enter' })
    expect(document.activeElement).toBe(screen.getByRole('combobox', { name: /Nombre/ }))
    expect(posts(f)).toHaveLength(0)
  })

  it('«Más datos» está a la vista sin desplegar y el resumen muestra lo que conserva «registrar otro»', async () => {
    abrir('/admin/activos/nuevo')
    await screen.findByRole('textbox', { name: /Código del sticker/ })
    expect(screen.getByRole('textbox', { name: /Serial/ })).toBeTruthy()
    expect(screen.getByRole('combobox', { name: /Subtipo/ })).toBeTruthy()
    const resumen = screen.getByRole('region', { name: 'Resumen' })
    expect(resumen.textContent).toContain('Conserva categoría, ubicación, marca, modelo y subtipo. Borra código, nombre, serial, precio y foto.')
    expect(within(resumen).getByRole('switch', { name: /Varias unidades iguales/ }).getAttribute('aria-checked')).toBe('false')
  })

  it('el resumen refleja lo escrito, con el precio en COP', async () => {
    abrir('/admin/activos/nuevo')
    await llenarAdmin('nuevo-11')
    const resumen = screen.getByRole('region', { name: 'Resumen' })
    await waitFor(() => expect(resumen.textContent).toContain('NUEVO-11'))
    expect(resumen.textContent).toContain('Silla auxiliar')
    expect(resumen.textContent).toContain('Mobiliario')
    expect(resumen.textContent).toContain('Consultorio 1 › Box 2')
    expect(resumen.textContent).toContain('$ 1.250.000,00')
  })

  it('Enter en un campo de datos guarda', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await llenarAdmin('NUEVO-12')
    fireEvent.keyDown(screen.getByRole('textbox', { name: /Precio de compra/ }), { key: 'Enter' })
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect(posts(f)).toHaveLength(1)
  })

  it('Ctrl+Enter guarda y deja el formulario listo para otro (Q9 A), con el foco en el código', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await llenarAdmin('NUEVO-13')
    expect(await screen.findByText('Código libre')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('textbox', { name: /Serial/ }), { key: 'Enter', ctrlKey: true })
    const aviso = (await screen.findByText(/Ahora escanea el siguiente sticker/)).closest('[role=status]') as HTMLElement
    expect(aviso.textContent).toContain('Silla auxiliar · NUEVO-13')
    expect(within(aviso).getByRole('link', { name: 'Ver el activo' }).getAttribute('href')).toBe('/app/activos/NUEVO-13')
    const codigo = screen.getByRole('textbox', { name: /Código del sticker/ })
    await waitFor(() => expect(document.activeElement).toBe(codigo))
    expect((codigo as HTMLInputElement).value).toBe('')
    // El aviso de «ya existe» del código anterior no se queda pegado al campo vacío.
    await act(() => new Promise((listo) => setTimeout(listo, 100)))
    expect(screen.queryByText(/Ese código ya existe/)).toBeNull()
    expect(codigo.getAttribute('aria-invalid')).toBe('false')
    expect(valor(/Nombre/, 'combobox')).toBe('')
    expect(valor(/Precio de compra/)).toBe('')
    expect(valor(/Serial/)).toBe('')
    expect(valor(/Marca/, 'combobox')).toBe('Ergodent')
    expect(valor(/Modelo/, 'combobox')).toBe('SA-40')
    expect(valor(/Subtipo/, 'combobox')).toBe('Silla')
    expect(screen.getByRole('combobox', { name: /Categoría/ }).textContent).toContain('Mobiliario')
    expect(screen.getByRole('combobox', { name: /Ubicación/ }).textContent).toContain('Box 2')
    expect(screen.getByRole('checkbox', { name: /Revisé que coincide/ }).getAttribute('aria-checked')).toBe('false')
    // El precio no se arrastra: sin escribirlo no se guarda.
    fireEvent.change(codigo, { target: { value: 'NUEVO-14' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Silla auxiliar' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    expect(screen.getByText('Escribe el precio')).toBeTruthy()
    fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '900.000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    await waitFor(() => expect(document.body.textContent).toContain('Silla auxiliar · NUEVO-14 en'))
    const [primero, segundo] = posts(f)
    expect(segundo.id).not.toBe(primero.id)
    expect(segundo).toMatchObject({
      codigo: 'NUEVO-14',
      precio_compra: '900000.00',
      marca: 'Ergodent',
      modelo: 'SA-40',
      subtipo: 'Silla',
      serial: null,
      categoria_id: primero.categoria_id,
      ubicacion_id: primero.ubicacion_id,
    })
  })

  it('«Varias unidades iguales» (apagado por defecto) conserva también nombre y precio', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await llenarAdmin('NUEVO-15')
    fireEvent.click(screen.getByRole('switch', { name: /Varias unidades iguales/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    await screen.findByText(/Ahora escanea el siguiente sticker/)
    expect(valor(/Código del sticker/)).toBe('')
    expect(valor(/Serial/)).toBe('')
    expect(valor(/Nombre/, 'combobox')).toBe('Silla auxiliar')
    expect(valor(/Precio de compra/)).toBe('1.250.000')
    expect(posts(f)).toHaveLength(1)
  })

  // Revisión de T10: lo que se escribe mientras se guarda no se pierde (Q9: lo conservado
  // sale del estado actual, no del que había al hacer clic).
  function abrirConEspera() {
    const catalogo = catalogoDemo('admin')
    let soltar = () => {}
    let retener = false
    simularAncho({ movil: false })
    const f = simularSesion('admin', (url, init) => {
      if (!retener || url !== '/api/activos' || init.method !== 'POST') return catalogo.manejador(url, init)
      retener = false
      return new Promise<void>((listo) => (soltar = listo)).then(() => catalogo.manejador(url, init)!)
    })
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/activos/nuevo'] })} />)
    return { f, retener: () => (retener = true), soltar: () => act(async () => soltar()) }
  }

  it('«Guardar y registrar otro» conserva lo editado mientras se guardaba', async () => {
    const { f, retener, soltar } = abrirConEspera()
    await llenarAdmin('NUEVO-30')
    retener()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    await waitFor(() => expect(posts(f)).toHaveLength(1))
    fireEvent.change(screen.getByRole('combobox', { name: /Marca/ }), { target: { value: 'Otra marca' } })
    fireEvent.change(screen.getByRole('combobox', { name: /Modelo/ }), { target: { value: '' } })
    await soltar()
    await screen.findByText(/Ahora escanea el siguiente sticker/)
    expect(valor(/Marca/, 'combobox')).toBe('Otra marca')
    expect(valor(/Modelo/, 'combobox')).toBe('')
    expect(valor(/Subtipo/, 'combobox')).toBe('Silla')
    expect(valor(/Código del sticker/)).toBe('')
    expect(valor(/Nombre/, 'combobox')).toBe('')
    expect(valor(/Precio de compra/)).toBe('')
    // Lo vaciado no se marca como conservado; lo editado sí se conserva y resalta.
    expect(screen.getByRole('combobox', { name: /Modelo/ }).className).not.toContain('bg-brand-soft')
    expect(screen.getByRole('combobox', { name: /Marca/ }).className).toContain('bg-brand-soft')
  })

  it('«Varias unidades iguales» conserva lo editado mientras se guardaba', async () => {
    const { f, retener, soltar } = abrirConEspera()
    await llenarAdmin('NUEVO-31')
    fireEvent.click(screen.getByRole('switch', { name: /Varias unidades iguales/ }))
    retener()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    await waitFor(() => expect(posts(f)).toHaveLength(1))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Silla auxiliar gris' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '1.300.000' } })
    await soltar()
    await screen.findByText(/Ahora escanea el siguiente sticker/)
    expect(valor(/Nombre/, 'combobox')).toBe('Silla auxiliar gris')
    expect(valor(/Precio de compra/)).toBe('1.300.000')
    expect(valor(/Código del sticker/)).toBe('')
    expect(valor(/Serial/)).toBe('')
  })

  it.each([
    ['un 502', () => new Response('<html></html>', { status: 502 })],
    ['un error de red', () => Promise.reject(new TypeError('Failed to fetch')) as unknown as Response],
  ])('«Guardar y registrar otro» tras %s reintenta con el mismo id y lo cambia solo al guardar', async (_, falla) => {
    const { f, catalogo } = abrir('/admin/activos/nuevo')
    await llenarAdmin('NUEVO-32')
    catalogo.fallar('POST /api/activos', falla)
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    expect(await screen.findByText('No se guardó')).toBeTruthy()
    expect(valor(/Código del sticker/)).toBe('NUEVO-32')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    await screen.findByText(/Ahora escanea el siguiente sticker/)
    fireEvent.change(screen.getByRole('textbox', { name: /Código del sticker/ }), { target: { value: 'NUEVO-33' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Silla auxiliar' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio de compra/ }), { target: { value: '900.000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    await waitFor(() => expect(document.body.textContent).toContain('Silla auxiliar · NUEVO-33 en'))
    const ids = posts(f).map((c) => c.id)
    expect(ids).toHaveLength(3)
    expect(ids[1]).toBe(ids[0])
    expect(ids[2]).not.toBe(ids[0])
  })

  it.each([
    ['en composición (IME)', { isComposing: true }],
    ['repetido (tecla sostenida)', { repeat: true }],
  ])('Enter %s no guarda', async (_, extra) => {
    const { f } = abrir('/admin/activos/nuevo')
    await llenarAdmin('NUEVO-34')
    const precio = screen.getByRole('textbox', { name: /Precio de compra/ })
    fireEvent.keyDown(precio, { key: 'Enter', ...extra })
    fireEvent.keyDown(precio, { key: 'Enter', ctrlKey: true, ...extra })
    await act(() => new Promise((listo) => setTimeout(listo, 50)))
    expect(posts(f)).toHaveLength(0)
    expect(screen.queryByText('Activo creado')).toBeNull()
    expect(screen.queryByText(/Ahora escanea el siguiente sticker/)).toBeNull()
  })

  // Cierre de T10 (security M1): mantener Enter no envía el formulario de forma implícita
  // ni lanza un segundo POST mientras el primero está en vuelo.
  it('Enter o Ctrl+Enter sostenidos no lanzan un segundo POST mientras se guarda', async () => {
    const { f, retener, soltar } = abrirConEspera()
    await llenarAdmin('NUEVO-36')
    retener()
    const precio = screen.getByRole('textbox', { name: /Precio de compra/ })
    fireEvent.keyDown(precio, { key: 'Enter' })
    await waitFor(() => expect(posts(f)).toHaveLength(1))
    expect(fireEvent.keyDown(precio, { key: 'Enter', repeat: true })).toBe(false)
    expect(fireEvent.keyDown(precio, { key: 'Enter', ctrlKey: true, repeat: true })).toBe(false)
    // El envío implícito del navegador (submit del formulario) tampoco duplica.
    fireEvent.submit(precio.closest('form')!)
    await act(() => new Promise((listo) => setTimeout(listo, 50)))
    expect(posts(f)).toHaveLength(1)
    await soltar()
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect(posts(f)).toHaveLength(1)
  })

  it('con «Varias unidades iguales» no dice que se borran nombre y precio', async () => {
    abrir('/admin/activos/nuevo')
    await screen.findByRole('textbox', { name: /Código del sticker/ })
    const resumen = screen.getByRole('region', { name: 'Resumen' })
    fireEvent.click(within(resumen).getByRole('switch', { name: /Varias unidades iguales/ }))
    expect(resumen.textContent).not.toContain('Borra código, nombre, serial, precio y foto.')
    expect(resumen.textContent).toContain('también nombre y precio')
  })

  it('Enter dentro de una lista emergente (portal) no guarda', async () => {
    const { f } = abrir('/admin/activos/nuevo')
    await llenarAdmin('NUEVO-35')
    fireEvent.click(screen.getByRole('combobox', { name: /Ubicación/ }))
    const buscar = await screen.findByPlaceholderText('Buscar sala o box…')
    expect(buscar.closest('form')).toBeNull()
    fireEvent.change(buscar, { target: { value: 'zzz' } })
    fireEvent.keyDown(buscar, { key: 'Enter' })
    fireEvent.keyDown(buscar, { key: 'Enter', ctrlKey: true })
    await act(() => new Promise((listo) => setTimeout(listo, 50)))
    expect(posts(f)).toHaveLength(0)
    expect(screen.queryByText('Activo creado')).toBeNull()
  })

  it('la foto se puede arrastrar al recuadro', async () => {
    abrir('/admin/activos/nuevo')
    await screen.findByRole('textbox', { name: /Código del sticker/ })
    const zona = screen.getByText(/Arrastra una foto aquí/).closest('[data-zona-foto]') as HTMLElement
    const archivo = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], 'IMG_0002.jpg', { type: 'image/jpeg' })
    fireEvent.drop(zona, { dataTransfer: { files: [archivo], types: ['Files'] } })
    expect(await screen.findByRole('img', { name: 'Vista previa de la foto' })).toBeTruthy()
  })

  it.each([
    ['un archivo que no es imagen', new File(['hola'], 'notas.txt', { type: 'text/plain' })],
    ['un SVG', new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' })],
  ])('al recuadro de la foto se ignora %s', async (_, archivo) => {
    abrir('/admin/activos/nuevo')
    await screen.findByRole('textbox', { name: /Código del sticker/ })
    const zona = screen.getByText(/Arrastra una foto aquí/).closest('[data-zona-foto]') as HTMLElement
    fireEvent.drop(zona, { dataTransfer: { files: [archivo], types: ['Files'] } })
    await act(() => new Promise((listo) => setTimeout(listo, 20)))
    expect(screen.queryByRole('img', { name: 'Vista previa de la foto' })).toBeNull()
    expect(screen.getByText(/Arrastra una foto aquí/)).toBeTruthy()
  })
})

describe('Registrar activo mejorado en el conteo (015-T10)', () => {
  function abrirEscritorio(path: string, rol: Rol = 'contador') {
    const catalogo = catalogoDemo(rol)
    simularEscritorio()
    const f = simularSesion(rol, catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
    return { f, catalogo }
  }

  it('en escritorio: foco en Nombre, ubicación de la sala y resumen sin precio para el contador', async () => {
    guardarSala('00000000-0000-4000-8000-0000000000a4')
    abrirEscritorio('/contar/nuevo?codigo=nuevo-20')
    const nombre = await screen.findByRole('combobox', { name: /Nombre/ })
    await waitFor(() => expect(document.activeElement).toBe(nombre))
    expect(screen.getAllByText('NUEVO-20')).toHaveLength(2)
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Ubicación/ }).textContent).toContain('Box 2'))
    expect(screen.getByText('Viene de la sala donde estás contando.')).toBeTruthy()
    expect(screen.getByRole('textbox', { name: /Serial/ })).toBeTruthy()
    const resumen = screen.getByRole('region', { name: 'Resumen' })
    expect(within(resumen).queryByText('Precio')).toBeNull()
    expect(screen.getByRole('link', { name: 'Volver al conteo' }).getAttribute('href')).toBe('/contar/escanear')
  })

  it('en escritorio, Ctrl+Enter guarda y pide el siguiente sticker en un campo editable', async () => {
    const { f } = abrirEscritorio('/contar/nuevo?codigo=NUEVO-21')
    fireEvent.click(await screen.findByRole('checkbox', { name: /Coincide con el sticker/ }))
    fireEvent.change(screen.getByRole('combobox', { name: /Nombre/ }), { target: { value: 'Monitor' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Precio/ }), { target: { value: '500.000' } })
    await elegirSelect(/Categoría/, 'Electrónica')
    await elegir(/Ubicación/, 'Administración')
    fireEvent.change(screen.getByRole('combobox', { name: /Marca/ }), { target: { value: 'LG' } })
    await focoDevuelto()
    fireEvent.keyDown(screen.getByRole('combobox', { name: /Nombre/ }), { key: 'Enter', ctrlKey: true })
    await screen.findByText(/Ahora escanea el siguiente sticker/)
    const codigo = screen.getByRole('textbox', { name: /Código del sticker/ })
    await waitFor(() => expect(document.activeElement).toBe(codigo))
    expect(valor(/Nombre/, 'combobox')).toBe('')
    expect(valor(/Precio/)).toBe('')
    expect(valor(/Marca/, 'combobox')).toBe('LG')
    expect(screen.getByRole('combobox', { name: /Categoría/ }).textContent).toContain('Electrónica')
    fireEvent.change(codigo, { target: { value: 'nuevo-22' } })
    fireEvent.keyDown(codigo, { key: 'Enter' })
    expect(document.activeElement).toBe(screen.getByRole('combobox', { name: /Nombre/ }))
    expect(posts(f)).toHaveLength(1)
    expect(document.body.textContent).not.toContain('500.000')
  })

  it('en el teléfono, el pie trae «Guardar y registrar otro» y sin código en la URL se escribe', async () => {
    abrir('/contar/nuevo', 'contador')
    expect(await screen.findByRole('button', { name: 'Guardar y registrar otro' })).toBeTruthy()
    expect(screen.getByRole('textbox', { name: /Código del sticker/ })).toBeTruthy()
  })

  it('en escritorio, el contador duplica sin ver el precio y «registrar otro» no arrastra la copia', async () => {
    guardarSala('00000000-0000-4000-8000-0000000000a4')
    const { f } = abrirEscritorio('/contar/nuevo?codigo=NUEVO-23')
    fireEvent.click(await screen.findByRole('checkbox', { name: /Coincide con el sticker/ }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    await focoDevuelto()
    const resumen = screen.getByRole('region', { name: 'Resumen' })
    expect(resumen.textContent).toContain('Silla ergonómica')
    expect(document.body.textContent).not.toContain('389')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y registrar otro' }))
    await screen.findByText(/Ahora escanea el siguiente sticker/)
    const [cuerpo] = posts(f)
    expect(Object.keys(cuerpo).sort()).toEqual(['codigo', 'copiar_de', 'id', 'serial', 'ubicacion_id'])
    expect(valor(/Nombre/, 'combobox')).toBe('')
    expect(valor(/Precio/)).toBe('')
    expect(screen.getByRole('combobox', { name: /Categoría/ }).textContent).toContain('Mobiliario')
    expect(screen.getByRole('combobox', { name: /Categoría/ }).className).toContain('bg-brand-soft')
    expect(screen.getByRole('combobox', { name: /Ubicación/ }).className).toContain('bg-brand-soft')
    expect(document.body.textContent).not.toContain('389')
  })

  // Cierre de T10 (security M2): defensa en dos capas; aunque el servidor enviara el precio
  // del activo copiado, el formulario del contador no lo carga.
  it('el contador que copia no carga el precio aunque el activo lo traiga', async () => {
    const catalogo = catalogoDemo('admin')
    simularEscritorio()
    simularSesion('contador', catalogo.manejador)
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/contar/nuevo?codigo=NUEVO-25'] })} />)
    fireEvent.click(await screen.findByRole('combobox', { name: /Copiar de un parecido/ }))
    fireEvent.change(await screen.findByRole('combobox', { name: 'Buscar activo parecido' }), { target: { value: 'silla' } })
    fireEvent.click(await screen.findByRole('option', { name: /Silla ergonómica/ }))
    await focoDevuelto()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar la copia' }))
    expect(valor(/Precio/)).toBe('')
    expect(document.body.textContent).not.toContain('389.900')
    expect(screen.getByText('El precio no se muestra aquí; después de guardar, solo lo ven los administradores.')).toBeTruthy()
  })

  it('el admin en el conteo de escritorio ve el precio en el resumen', async () => {
    abrirEscritorio('/contar/nuevo?codigo=NUEVO-24', 'admin')
    fireEvent.change(await screen.findByRole('textbox', { name: /Precio/ }), { target: { value: '389.900' } })
    expect(within(screen.getByRole('region', { name: 'Resumen' })).getByText('$ 389.900,00')).toBeTruthy()
  })
})
