import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { simularSesion } from '@/test/sesion'

// Spec 005: acciones de la ficha del activo (T5 editar con If-Match y 412).

afterEach(cleanup)

const SILLA = '00000000-0000-4000-8000-0000000000d2'

function abrir(path = '/admin/activos/000123', catalogo = catalogoDemo('admin')) {
  simularAncho({ movil: false })
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const cambios = (f: ReturnType<typeof simularSesion>) =>
  f.mock.calls.filter(([url, init]) => String(url).startsWith(`/api/activos/${SILLA}`) && (init?.method ?? 'GET') !== 'GET')

async function abrirEdicion() {
  fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
  return screen.findByRole('dialog', { name: 'Editar activo' })
}

describe('editar (T5)', () => {
  it('envía solo lo cambiado con If-Match y muestra lo guardado', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    expect((within(panel).getByLabelText(/Precio de compra/) as HTMLInputElement).value).toBe('389.900')
    fireEvent.change(within(panel).getByLabelText(/Precio de compra/), { target: { value: '420.000' } })
    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: '' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('$ 420.000,00')).toBeTruthy()
    const [[, init]] = cambios(f)
    expect(init?.method).toBe('PATCH')
    expect(new Headers(init?.headers).get('If-Match')).toBe('"1"')
    expect(JSON.parse(String(init?.body))).toEqual({ precio_compra: '420000.00', marca: null })
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Editar' })))
  })

  it('sin cambios no llama a la API', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(cambios(f)).toHaveLength(0)
  })

  it('valida nombre y precio antes de enviar', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: '  ' } })
    fireEvent.change(within(panel).getByLabelText(/Precio de compra/), { target: { value: 'mucho' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    expect(await within(panel).findByText('Escribe el nombre')).toBeTruthy()
    expect(within(panel).getByText(/Escribe el precio en pesos/)).toBeTruthy()
    expect(cambios(f)).toHaveLength(0)
  })

  it('ante un 412 conserva lo escrito, marca lo que cambió otra persona y reaplica', async () => {
    const { f, catalogo } = abrir()
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla ergonómica gris' } })
    catalogo.cambiarPorOtro(SILLA, { precio_compra: '400000.00' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))

    const aviso = await within(panel).findByRole('alert')
    expect(aviso.textContent).toContain('Cambió: precio de compra')
    expect((within(panel).getByLabelText(/Nombre/) as HTMLInputElement).value).toBe('Silla ergonómica gris')
    expect(within(panel).getByText('Otra persona lo cambió a «$ 400.000,00»')).toBeTruthy()
    // Spec 016, T10 (Deuda T8 b): una sola acción principal en el diálogo (la del pie); la
    // del aviso es secundaria.
    expect(within(aviso).getByRole('button', { name: 'Guardar mis cambios' }).getAttribute('data-variante')).toBe('secundario')
    expect(panel.querySelectorAll('[data-kit=boton][data-variante=principal]')).toHaveLength(1)

    fireEvent.click(within(aviso).getByRole('button', { name: 'Guardar mis cambios' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica gris' })).toBeTruthy()
    expect(screen.getByText('$ 400.000,00')).toBeTruthy()
    const envios = cambios(f)
    expect(envios).toHaveLength(2)
    expect(new Headers(envios[1][1]?.headers).get('If-Match')).toBe('"2"')
    expect(JSON.parse(String(envios[1][1]?.body))).toEqual({ nombre: 'Silla ergonómica gris' })
  })

  it('descartar lo mío carga el activo vigente', async () => {
    const { catalogo } = abrir()
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: 'Otra' } })
    catalogo.cambiarPorOtro(SILLA, { marca: 'Rimax Pro' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    const aviso = await within(panel).findByRole('alert')
    fireEvent.click(within(aviso).getByRole('button', { name: 'Descartar los míos' }))
    expect((within(panel).getByLabelText('Marca') as HTMLInputElement).value).toBe('Rimax Pro')
    expect(within(panel).queryByRole('alert')).toBeNull()
  })

  it('?accion=editar abre el formulario', async () => {
    abrir('/admin/activos/000123?accion=editar')
    expect(await screen.findByRole('dialog', { name: 'Editar activo' })).toBeTruthy()
  })

  it('se abre como diálogo centrado, no como panel lateral (015-T2)', async () => {
    abrir()
    const panel = await abrirEdicion()
    expect(panel.getAttribute('data-slot')).toBe('dialog-content')
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull()
  })

  // Spec 016, T10 (Deuda T8 a): reabrir la edición empieza del activo, no de lo escrito.
  it('cancelar y reabrir empieza de cero', async () => {
    abrir()
    let panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText('Marca'), { target: { value: 'Otra marca' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    panel = await abrirEdicion()
    expect((within(panel).getByLabelText('Marca') as HTMLInputElement).value).toBe('Rimax')
  })

  // Spec 016, T10 (Deuda T8 a): si se cierra el diálogo con el guardado en vuelo y se abre
  // otra acción, la respuesta no cierra esa otra acción (solo cierra su propio diálogo).
  it('un guardado que termina con el diálogo ya cerrado no cierra «Mover»', async () => {
    const catalogo = catalogoDemo('admin')
    let soltar = () => {}
    const enVuelo = new Promise<void>((r) => (soltar = r))
    simularAncho({ movil: false })
    const f = simularSesion('admin', (url, init) => {
      // El PATCH espera a `soltar()`: el guardado queda en vuelo.
      if (init?.method === 'PATCH' && String(url) === `/api/activos/${SILLA}`) {
        return enVuelo.then(() => catalogo.manejador(url, init)) as Promise<Response>
      }
      return catalogo.manejador(url, init)
    })
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/admin/activos/000123'] })} />)
    const panel = await abrirEdicion()
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla en vuelo' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(cambios(f)).toHaveLength(1))
    fireEvent.keyDown(panel, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Editar activo' })).toBeNull())
    fireEvent.click(screen.getByRole('button', { name: 'Mover' }))
    expect(await screen.findByRole('dialog', { name: 'Mover activo' })).toBeTruthy()
    soltar()
    // El diálogo «Mover» es modal: la ficha queda oculta al lector mientras tanto (hidden).
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla en vuelo', hidden: true })).toBeTruthy()
    expect(screen.getByRole('dialog', { name: 'Mover activo' })).toBeTruthy()
  })

  it('Escape cierra el diálogo sin guardar (015-T2)', async () => {
    const { f } = abrir()
    const panel = await abrirEdicion()
    fireEvent.keyDown(panel, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(cambios(f)).toHaveLength(0)
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Editar' })))
  })
})

describe('confirmar «Enviar a reparación» (015-T2, Q5 A; en «Más» desde 015-T7)', () => {
  it('«No» cierra la confirmación sin llamar al servidor', async () => {
    const { f } = abrir()
    await elegirEnMas('Enviar a reparación…')
    const confirmar = await screen.findByRole('alertdialog', { name: '¿Enviar a reparación?' })
    expect(confirmar.textContent).toContain('Sigue contando en el inventario')
    fireEvent.click(within(confirmar).getByRole('button', { name: 'No' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(cambios(f)).toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'Volver a activo' })).toBeNull()
    expect(within(await abrirMas()).getByRole('menuitem', { name: 'Enviar a reparación…' })).toBeTruthy()
  })

  it('Escape también cancela sin llamar al servidor y el foco vuelve a «Más»', async () => {
    const { f } = abrir()
    await elegirEnMas('Enviar a reparación…')
    const confirmar = await screen.findByRole('alertdialog', { name: '¿Enviar a reparación?' })
    fireEvent.keyDown(confirmar, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    expect(cambios(f)).toHaveLength(0)
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Más acciones' })))
  })

  it('el foco inicial está en «No»', async () => {
    abrir()
    await elegirEnMas('Enviar a reparación…')
    const confirmar = await screen.findByRole('alertdialog', { name: '¿Enviar a reparación?' })
    await waitFor(() => expect(document.activeElement).toBe(within(confirmar).getByRole('button', { name: 'No' })))
  })

  it('tras «Sí» el foco espera en «Más» y pasa a «Volver a activo» cuando termina de guardar', async () => {
    // El servidor tarda: el diálogo se cierra mientras guarda.
    const catalogo = catalogoDemo('admin')
    let soltar = () => {}
    const espera = new Promise<void>((r) => (soltar = r))
    const manejador: typeof catalogo.manejador = (url, init) =>
      url === `/api/activos/${SILLA}/estado`
        ? espera.then(async () => (await catalogo.manejador(url, init)) ?? new Response(null, { status: 500 }))
        : catalogo.manejador(url, init)
    abrir('/admin/activos/000123', { ...catalogo, manejador })
    await confirmarReparacion()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Más acciones' })))
    expect(screen.queryByRole('button', { name: 'Volver a activo' })).toBeNull()
    soltar()
    const volver = await screen.findByRole('button', { name: 'Volver a activo' })
    await waitFor(() => expect(document.activeElement).toBe(volver))
  })

  it('«Sí, enviar a reparación» llama al servidor; «Volver a activo» no pide confirmación', async () => {
    const { f } = abrir()
    await confirmarReparacion()
    expect(await screen.findByRole('button', { name: 'Volver a activo' })).toBeTruthy()
    expect(cambios(f)).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Volver a activo' }))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Volver a activo' })).toBeNull())
    expect(cambios(f)).toHaveLength(2)
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Más acciones' })))
    expect(within(await abrirMas()).getByRole('menuitem', { name: 'Enviar a reparación…' })).toBeTruthy()
  })
})

async function abrirMas() {
  fireEvent.keyDown(await screen.findByRole('button', { name: 'Más acciones' }), { key: 'Enter' })
  return screen.findByRole('menu')
}

async function elegirEnMas(nombre: string) {
  fireEvent.click(within(await abrirMas()).getByRole('menuitem', { name: nombre }))
}

async function confirmarReparacion() {
  await elegirEnMas('Enviar a reparación…')
  const confirmar = await screen.findByRole('alertdialog', { name: '¿Enviar a reparación?' })
  fireEvent.click(within(confirmar).getByRole('button', { name: 'Sí, enviar a reparación' }))
}

async function elegirEnSelect(nombre: RegExp | string, opcion: string) {
  const disparador = screen.getByRole('combobox', { name: nombre })
  fireEvent.keyDown(disparador, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: opcion }))
}

describe('ciclo de vida (T6)', () => {
  it('mueve a otra sala o box con If-Match', async () => {
    const { f } = abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Mover' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Mover activo' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Mover' }))
    expect(await within(dialogo).findByText('Elige la sala o el box de destino')).toBeTruthy()
    fireEvent.click(within(dialogo).getByRole('combobox'))
    fireEvent.click(await screen.findByRole('option', { name: /Administración/ }))
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Mover' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(await screen.findByText('Administración', { selector: 'dd' })).toBeTruthy()
    const [[url, init]] = cambios(f)
    expect(String(url)).toBe(`/api/activos/${SILLA}/mover`)
    expect(JSON.parse(String(init?.body))).toEqual({ ubicacion_id: '00000000-0000-4000-8000-0000000000a2' })
  })

  it('envía a reparación (con confirmación) y vuelve a activo en un toque', async () => {
    const { f } = abrir()
    await confirmarReparacion()
    expect(await screen.findByRole('button', { name: 'Volver a activo' })).toBeTruthy()
    expect(screen.getByText('En reparación')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Volver a activo' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Volver a activo' })).toBeNull())
    expect(screen.getByText('Activo', { selector: '[data-slot=badge]' })).toBeTruthy()
    const envios = cambios(f)
    expect(envios.map(([, init]) => new Headers(init?.headers).get('If-Match'))).toEqual(['"1"', '"2"'])
  })

  it('dar de baja exige motivo (y nota con «otro»), deja la ficha en solo lectura y se reactiva', async () => {
    const { f } = abrir()
    await elegirEnMas('Dar de baja…')
    const dialogo = await screen.findByRole('dialog', { name: 'Dar de baja' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Dar de baja' }))
    expect(await within(dialogo).findByText('Elige un motivo', { selector: 'p' })).toBeTruthy()
    await elegirEnSelect(/Motivo/, 'Otro')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Dar de baja' }))
    expect(await within(dialogo).findByText('Con «Otro», escribe una nota')).toBeTruthy()
    await elegirEnSelect(/Motivo/, 'Perdido')
    fireEvent.change(within(dialogo).getByLabelText(/Nota/), { target: { value: 'No apareció en el conteo' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Dar de baja' }))

    const aviso = await screen.findByText('Dado de baja: perdido')
    expect(aviso).toBeTruthy()
    expect(await screen.findByText('«No apareció en el conteo»')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Editar' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Mover' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Más acciones' })).toBeNull()
    expect(JSON.parse(String(cambios(f)[0][1]?.body))).toEqual({ motivo: 'perdido', nota: 'No apareció en el conteo' })

    fireEvent.click(screen.getByRole('button', { name: 'Reactivar' }))
    const reactivar = await screen.findByRole('dialog', { name: 'Reactivar activo' })
    await elegirEnSelect(/Motivo/, 'Apareció')
    fireEvent.click(within(reactivar).getByRole('button', { name: 'Reactivar' }))
    expect(await screen.findByRole('button', { name: 'Editar' })).toBeTruthy()
    expect(JSON.parse(String(cambios(f)[1][1]?.body))).toEqual({ estado: 'activo', motivo: 'encontrado', nota: null })
  })

  it('si otra persona lo cambió, avisa y muestra el vigente', async () => {
    const { catalogo } = abrir()
    await screen.findByRole('button', { name: 'Más acciones' })
    catalogo.cambiarPorOtro(SILLA, { nombre: 'Silla renombrada' })
    await confirmarReparacion()
    expect(await screen.findByText(/Alguien cambió este activo/)).toBeTruthy()
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla renombrada' })).toBeTruthy()
  })
})

describe('disposición de la ficha (015-T7, R13)', () => {
  it('encabezado con nombre, código, categoría, estado y acciones: «Editar» principal, «Mover» y «Más»', async () => {
    abrir()
    const titulo = await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })
    const encabezado = titulo.closest('header')!
    expect(encabezado).toBeTruthy()
    expect(within(encabezado).getByText('000123')).toBeTruthy()
    expect(within(encabezado).getByText('Activo')).toBeTruthy()
    const editar = within(encabezado).getByRole('button', { name: 'Editar' })
    expect(editar.getAttribute('data-variant')).toBe('default')
    expect(within(encabezado).getByRole('button', { name: 'Mover' }).getAttribute('data-variant')).toBe('outline')
    expect(within(encabezado).getByRole('button', { name: 'Más acciones' })).toBeTruthy()
    // Reparación y baja ya no son botones sueltos: viven en «Más».
    expect(screen.queryByRole('button', { name: /Enviar a reparación/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Dar de baja/ })).toBeNull()
    const menu = await abrirMas()
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Enviar a reparación…', 'Dar de baja…'])
    expect(within(menu).getByRole('menuitem', { name: 'Dar de baja…' }).getAttribute('data-variant')).toBe('destructive')
  })

  it('datos de Identificación y Compra; foto, identificación, compra, historial y ubicación, en ese orden', async () => {
    abrir()
    const identificacion = await screen.findByRole('region', { name: 'Identificación' })
    const dato = (region: HTMLElement, etiqueta: string) =>
      within(region).getByText(etiqueta, { selector: 'dt' }).nextElementSibling?.textContent
    expect(dato(identificacion, 'Código')).toBe('000123')
    expect(dato(identificacion, 'Marca')).toBe('Rimax')
    for (const etiqueta of ['Serial', 'Categoría', 'Subtipo', 'Modelo']) {
      expect(within(identificacion).getByText(etiqueta, { selector: 'dt' })).toBeTruthy()
    }
    const ubicacion = screen.getByRole('region', { name: 'Ubicación' })
    expect(within(ubicacion).getByText('Sala o box', { selector: 'dt' })).toBeTruthy()
    const compra = screen.getByRole('region', { name: 'Compra' })
    expect(dato(compra, 'Precio de compra')).toBe('$ 389.900,00')
    expect(within(compra).getByText('Fecha de compra', { selector: 'dt' })).toBeTruthy()
    expect(within(compra).getByText('Registrado', { selector: 'dt' })).toBeTruthy()
    const historial = screen.getByRole('region', { name: 'Historial' })
    const foto = screen.getByRole('region', { name: 'Foto del activo' })
    const antes = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
    expect(antes(foto, identificacion)).toBe(true)
    expect(antes(identificacion, compra)).toBe(true)
    expect(antes(compra, historial)).toBe(true)
    expect(antes(historial, ubicacion)).toBe(true)
    // Un expediente, no cinco tarjetas sueltas: las secciones viven en un solo Panel.
    const expediente = identificacion.closest('[data-kit=panel]')
    expect(expediente).toBeTruthy()
    expect(foto.closest('[data-kit=panel]')).toBe(expediente)
    expect(compra.closest('[data-kit=panel]')).toBe(expediente)
    expect(historial.closest('[data-kit=panel]')).toBe(expediente)
    expect(ubicacion.closest('[data-kit=panel]')).toBe(expediente)
    expect(screen.queryByText('Una foto principal por activo.')).toBeNull()
  })

  it('en reparación, «Volver a activo» queda a la vista y «Más» solo ofrece la baja', async () => {
    abrir()
    await confirmarReparacion()
    const volver = await screen.findByRole('button', { name: 'Volver a activo' })
    expect(volver.closest('header')).toBeTruthy()
    const menu = await abrirMas()
    expect(within(menu).getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Dar de baja…'])
  })

  it('cancelar la baja devuelve el foco a «Más» sin llamar al servidor', async () => {
    const { f } = abrir()
    await elegirEnMas('Dar de baja…')
    const dialogo = await screen.findByRole('dialog', { name: 'Dar de baja' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(cambios(f)).toHaveLength(0)
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Más acciones' })))
  })

  it('Escape en el menú «Más» lo cierra sin elegir nada y devuelve el foco a «Más»', async () => {
    const { f } = abrir()
    const menu = await abrirMas()
    // Con el menú abierto el foco está dentro del menú, no en «Más».
    await waitFor(() => expect(menu.contains(document.activeElement)).toBe(true))
    fireEvent.keyDown(menu, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(cambios(f)).toHaveLength(0)
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Más acciones' })))
  })
})
