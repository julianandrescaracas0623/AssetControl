import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import type { Rol } from '@/lib/api/cliente'
import { routes } from '@/router'
import { catalogoDemo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, simularSesion } from '@/test/sesion'

// Spec 016, T8 (R2, R3, R5, R8, R9, R11; D13; A9): Activos, ficha, edición y «Registrar
// activo» del admin con el kit.
// 1) Caracterización: lo que el rediseño no puede cambiar (textos, estados, precio solo
//    admin, roles). Pasa antes y después de migrar.
// 2) Diseño: las piezas son del kit (TablaDatos, Pestanas, Menu, Panel, ListaDatos,
//    Dialogo, Confirmar, Aviso, Boton, MarcoImagen) y la foto de la ficha tiene el tamaño
//    de D13. Los cuadros de diálogo devuelven el foco (Deuda: «Mover», «Dar de baja» y
//    «Reactivar» no lo devolvían).

afterEach(cleanup)

const SILLA = '00000000-0000-4000-8000-0000000000d2'
const clases = (el: Element | null | undefined) => (el?.getAttribute('class') ?? '').split(/\s+/)

function abrir(path: string, catalogo = catalogoDemo('admin'), { movil = false, rol = 'admin' as Rol } = {}) {
  simularAncho({ movil })
  const f = simularSesion(rol, catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return { f, router, catalogo }
}

const foto = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], 'IMG_0001.jpg', { type: 'image/jpeg' })

async function subirFoto(nombre = 'Silla ergonómica') {
  fireEvent.change(await screen.findByTestId('entrada-foto-activo'), { target: { files: [foto()] } })
  fireEvent.click(await screen.findByRole('button', { name: 'Guardar foto' }))
  return screen.findByRole('button', { name: `Ver la foto de ${nombre}` })
}

async function abrirMas() {
  fireEvent.keyDown(await screen.findByRole('button', { name: 'Más acciones' }), { key: 'Enter' })
  return screen.findByRole('menu')
}

const filas = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)

describe('caracterización de Activos (T8): lo que no cambia', () => {
  it('mientras carga se anuncia «Cargando activos»', async () => {
    abrir('/admin/activos')
    expect(await screen.findByRole('status', { name: 'Cargando activos' })).toBeTruthy()
  })

  it('un error dice qué pasó y «Reintentar» vuelve a pedir la lista', async () => {
    const catalogo = catalogoDemo('admin')
    let fallas = 1
    const manejador: typeof catalogo.manejador = (url, init) => {
      if (url.startsWith('/api/activos?') && fallas > 0) {
        fallas -= 1
        return errorApi(503, 'no_disponible', 'El servidor no responde.')
      }
      return catalogo.manejador(url, init)
    }
    abrir('/admin/activos', { ...catalogo, manejador })
    expect(await screen.findByText('No se pudieron cargar los activos')).toBeTruthy()
    expect(screen.getByText('El servidor no responde.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(filas()).toHaveLength(2))
  })

  it('vacío sin activos: «Registrar activo» e «Ir a escanear»', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.activos.splice(0)
    abrir('/admin/activos', catalogo)
    expect(await screen.findByText('Aún no hay activos')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ir a escanear' }).getAttribute('href')).toBe('/contar/escanear')
    expect(screen.getAllByRole('link', { name: /Registrar activo/ }).every((a) => a.getAttribute('href') === '/admin/activos/nuevo')).toBe(true)
  })

  it('en el teléfono, una tarjeta por activo con enlace a la ficha, estado y precio (admin)', async () => {
    abrir('/admin/activos', catalogoDemo('admin'), { movil: true })
    const enlace = await screen.findByRole('link', { name: /Silla ergonómica/ })
    expect(enlace.getAttribute('href')).toBe('/admin/activos/000123')
    expect(screen.queryByRole('table')).toBeNull()
    const tarjeta = enlace.closest('li')!
    expect(tarjeta.textContent).toContain('000123')
    expect(tarjeta.textContent).toContain('$ 389.900,00')
    expect(within(tarjeta).getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' })).toBeTruthy()
  })
})

describe('diseño de Activos (T8): kit', () => {
  it('la lista es una TablaDatos con pestañas del kit; Exportar es secundario y Registrar es la principal', async () => {
    abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    expect(screen.getByRole('table').closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('tablist').getAttribute('data-kit')).toBe('pestanas')
    expect(screen.getByRole('button', { name: 'Exportar' }).getAttribute('data-variante')).toBe('secundario')
    const registrar = screen.getAllByRole('link', { name: /Registrar activo/ }).find((a) => a.closest('[data-kit=encabezado-pagina]'))
    expect(registrar?.getAttribute('data-variante')).toBe('principal')
    expect(screen.getByRole('searchbox', { name: 'Buscar activos' }).closest('[data-kit=tabla-datos]')).toBeTruthy()
    expect(screen.getByRole('navigation', { name: 'Paginación de activos' })).toBeTruthy()
  })

  it('el menú de la fila es el Menu del kit y su botón un Boton', async () => {
    abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    const boton = screen.getByRole('button', { name: 'Acciones de Silla ergonómica (000123)' })
    expect(boton.getAttribute('data-kit')).toBe('boton')
    fireEvent.keyDown(boton, { key: 'Enter' })
    expect((await screen.findByRole('menu')).getAttribute('data-kit')).toBe('menu')
  })

  it('el filtro de ubicación conserva su buscador (LocationPicker) para listas largas', async () => {
    abrir('/admin/activos')
    await waitFor(() => expect(filas()).toHaveLength(2))
    fireEvent.click(screen.getByRole('combobox', { name: 'Filtrar por ubicación' }))
    expect(await screen.findByPlaceholderText('Buscar sala o box…')).toBeTruthy()
  })

  it('con resultados y filtros activos ofrece «Limpiar filtros» en la barra (una sola vez)', async () => {
    abrir('/admin/activos?ubicacion=00000000-0000-4000-8000-0000000000a4')
    await waitFor(() => expect(filas()).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    await waitFor(() => expect(filas()).toHaveLength(2))
  })
})

describe('caracterización de la ficha (T8): lo que no cambia', () => {
  it('cargando y no encontrado', async () => {
    abrir('/admin/activos/000123')
    expect(await screen.findByRole('status', { name: 'Cargando el activo' })).toBeTruthy()
    cleanup()
    abrir('/admin/activos/NOEXISTE')
    expect(await screen.findByRole('heading', { level: 1, name: 'No encontramos ese código' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ver activos' }).getAttribute('href')).toBe('/admin/activos')
  })

  it('un error ofrece «Reintentar»', async () => {
    const catalogo = catalogoDemo('admin')
    let fallas = 1
    const manejador: typeof catalogo.manejador = (url, init) => {
      if (url.startsWith('/api/activos/por-codigo') && fallas > 0) {
        fallas -= 1
        return errorApi(503, 'no_disponible', 'El servidor no responde.')
      }
      return catalogo.manejador(url, init)
    }
    abrir('/admin/activos/000123', { ...catalogo, manejador })
    expect(await screen.findByText('No se pudo cargar el activo')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Silla ergonómica' })).toBeTruthy()
  })

  it('el precio se rotula como solo de administradores', async () => {
    abrir('/admin/activos/000123')
    const compra = await screen.findByRole('region', { name: 'Compra' })
    expect(compra.textContent).toContain('El precio solo lo ven los administradores.')
  })

  it('sin foto: «Sin foto», «Agregar foto» y la nota de una foto principal', async () => {
    abrir('/admin/activos/000123')
    expect(await screen.findByText('Sin foto')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Agregar foto' })).toBeTruthy()
    expect(screen.getByText('Una foto principal por activo.')).toBeTruthy()
  })
})

describe('diseño de la ficha (T8): kit y foto de tamaño prudente (D13)', () => {
  it('datos en Panel + ListaDatos del kit; historial en un Panel', async () => {
    abrir('/admin/activos/000123')
    for (const nombre of ['Identificación', 'Ubicación', 'Compra', 'Historial']) {
      const region = await screen.findByRole('region', { name: nombre })
      expect(region.getAttribute('data-kit')).toBe('panel')
    }
    expect(within(screen.getByRole('region', { name: 'Compra' })).getByText('$ 389.900,00').closest('dd')?.className).toContain('tabular-nums')
    expect(screen.getByRole('region', { name: 'Identificación' }).querySelector('[data-kit=lista-datos]')).toBeTruthy()
  })

  it('sin foto: la caja tiene el tamaño de D13 y «Agregar foto» es un Boton del kit (48 px en teléfono)', async () => {
    abrir('/admin/activos/000123')
    const vacio = await screen.findByText('Sin foto')
    const caja = vacio.closest('[data-kit=marco-imagen]')
    expect(caja?.getAttribute('data-variante')).toBe('foto')
    expect(clases(caja)).toEqual(expect.arrayContaining(['w-full', 'h-50', 'md:w-80', 'md:h-60']))
    expect(screen.getByRole('button', { name: 'Agregar foto' }).getAttribute('data-kit')).toBe('boton')
    expect(clases(screen.getByRole('button', { name: 'Agregar foto' }))).toContain('h-control')
  })

  it('con foto: caja de 320 × 240 (200 px de alto en teléfono), object-cover, y al tocarla se amplía en un Dialogo', async () => {
    abrir('/admin/activos/000123')
    const ver = await subirFoto()
    expect(ver.getAttribute('data-kit')).toBe('marco-imagen')
    expect(clases(ver)).toEqual(expect.arrayContaining(['w-full', 'h-50', 'md:w-80', 'md:h-60', 'max-w-full']))
    const miniatura = ver.querySelector('img')!
    expect(clases(miniatura)).toEqual(expect.arrayContaining(['size-full', 'object-cover']))
    // La foto ya no ocupa todo el ancho de la columna (antes aspect-[4/3] w-full).
    expect(document.querySelector('.aspect-\\[4\\/3\\]')).toBeNull()
    ver.focus()
    fireEvent.click(ver)
    const dialogo = await screen.findByRole('dialog', { name: 'Foto de Silla ergonómica' })
    expect(dialogo.getAttribute('data-kit')).toBe('dialogo')
    const ampliada = within(dialogo).getByRole('img', { name: 'Foto de Silla ergonómica' })
    expect(clases(ampliada)).toContain('object-contain')
    fireEvent.keyDown(dialogo, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Ver la foto de Silla ergonómica' })))
  })

  it('quitar la foto pide confirmación con el Confirmar del kit (efecto explícito)', async () => {
    abrir('/admin/activos/000123')
    await subirFoto()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar foto' }))
    const confirmar = await screen.findByRole('alertdialog', { name: '¿Quitar la foto de Silla ergonómica?' })
    expect(confirmar.getAttribute('data-kit')).toBe('confirmar')
    expect(confirmar.textContent).toContain('La imagen se borra y no se puede recuperar')
    expect(within(confirmar).getByRole('button', { name: 'Quitar foto' }).getAttribute('data-variante')).toBe('peligro')
  })

  it('Editar abre el Dialogo del kit; el 412 se muestra con un Aviso del kit', async () => {
    const { catalogo } = abrir('/admin/activos/000123')
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    const panel = await screen.findByRole('dialog', { name: 'Editar activo' })
    expect(panel.getAttribute('data-kit')).toBe('dialogo')
    expect(within(panel).getByRole('button', { name: 'Guardar cambios' }).getAttribute('data-variante')).toBe('principal')
    fireEvent.change(within(panel).getByLabelText(/Nombre/), { target: { value: 'Silla gris' } })
    catalogo.cambiarPorOtro(SILLA, { precio_compra: '400000.00' })
    fireEvent.click(within(panel).getByRole('button', { name: 'Guardar cambios' }))
    const aviso = await within(panel).findByRole('alert')
    expect(aviso.getAttribute('data-kit')).toBe('aviso')
    expect(aviso.getAttribute('data-tono')).toBe('aviso')
    // El código sigue sin poder cambiarse: no hay campo de código.
    expect(within(panel).queryByLabelText(/Código/)).toBeNull()
  })

  it('«Enviar a reparación» se confirma con el Confirmar del kit («No» / «Sí, enviar a reparación»)', async () => {
    abrir('/admin/activos/000123')
    const menu = await abrirMas()
    expect(menu.getAttribute('data-kit')).toBe('menu')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Enviar a reparación…' }))
    const confirmar = await screen.findByRole('alertdialog', { name: '¿Enviar a reparación?' })
    expect(confirmar.getAttribute('data-kit')).toBe('confirmar')
    expect(within(confirmar).getByRole('button', { name: 'No' })).toBeTruthy()
  })

  it('cancelar «Mover» devuelve el foco a «Mover»', async () => {
    abrir('/admin/activos/000123')
    const mover = await screen.findByRole('button', { name: 'Mover' })
    mover.focus()
    fireEvent.click(mover)
    const dialogo = await screen.findByRole('dialog', { name: 'Mover activo' })
    expect(dialogo.getAttribute('data-kit')).toBe('dialogo')
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Mover' })))
  })

  it('tras dar de baja el foco va a «Reactivar»; tras reactivar, a «Editar»', async () => {
    abrir('/admin/activos/000123')
    fireEvent.click(within(await abrirMas()).getByRole('menuitem', { name: 'Dar de baja…' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Dar de baja' })
    expect(within(dialogo).getByRole('button', { name: 'Dar de baja' }).getAttribute('data-variante')).toBe('peligro')
    fireEvent.keyDown(within(dialogo).getByRole('combobox', { name: /Motivo/ }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('option', { name: 'Perdido' }))
    await act(() => new Promise((listo) => setTimeout(listo, 0)))
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Dar de baja' }))
    expect(await screen.findByText('Dado de baja: perdido')).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Reactivar' })))

    fireEvent.click(screen.getByRole('button', { name: 'Reactivar' }))
    const reactivar = await screen.findByRole('dialog', { name: 'Reactivar activo' })
    fireEvent.keyDown(within(reactivar).getByRole('combobox', { name: /Motivo/ }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('option', { name: 'Apareció' }))
    await act(() => new Promise((listo) => setTimeout(listo, 0)))
    fireEvent.click(within(reactivar).getByRole('button', { name: 'Reactivar' }))
    expect(await screen.findByRole('button', { name: 'Editar' })).toBeTruthy()
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Editar' })))
  })

  it('cancelar «Reactivar» devuelve el foco a «Reactivar»', async () => {
    const catalogo = catalogoDemo('admin')
    catalogo.activos.find((a) => a.id === SILLA)!.estado = 'dado_de_baja'
    abrir('/admin/activos/000123', catalogo)
    const boton = await screen.findByRole('button', { name: 'Reactivar' })
    boton.focus()
    fireEvent.click(boton)
    const dialogo = await screen.findByRole('dialog', { name: 'Reactivar activo' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Reactivar' })))
  })
})

describe('foto en /contar (D13 d)', () => {
  it('la miniatura del contador mide 96 px (≤ 200 px de alto a 375 px) y «Agregar foto» es un Boton', async () => {
    abrir('/contar/activo/000123', catalogoDemo('contador'), { movil: true, rol: 'contador' })
    const agregar = await screen.findByRole('button', { name: 'Agregar foto' })
    expect(agregar.getAttribute('data-kit')).toBe('boton')
    const ver = await subirFoto()
    expect(clases(ver.querySelector('img'))).toEqual(expect.arrayContaining(['size-24', 'object-cover']))
    // El contador no ve precio en la vista del activo (P13).
    expect(document.body.textContent).not.toMatch(/389\.900|Precio de compra/)
  })
})

describe('Registrar activo (T8): kit', () => {
  it('el formulario va en un Panel del kit con «Guardar activo» como principal y el pie fijo en teléfono', async () => {
    abrir('/admin/activos/nuevo')
    await screen.findByRole('textbox', { name: /Código del sticker/ })
    const guardar = screen.getByRole('button', { name: 'Guardar activo' })
    expect(guardar.getAttribute('data-variante')).toBe('principal')
    expect(screen.getByRole('button', { name: 'Guardar y registrar otro' }).getAttribute('data-variante')).toBe('secundario')
    const panel = guardar.closest('[data-kit=panel]')
    expect(panel).toBeTruthy()
    const pie = guardar.closest('[data-panel=pie]')
    expect(clases(pie)).toEqual(expect.arrayContaining(['max-md:sticky', 'max-md:bottom-0']))
    // Sin el fondo de la barra lateral (Deuda T1 e).
    expect(clases(pie)).not.toContain('bg-sidebar')
    expect(screen.getByRole('region', { name: 'Resumen' }).getAttribute('data-kit')).toBe('panel')
  })

  it('el precio es un Campo de dinero del kit, solo para el admin', async () => {
    abrir('/admin/activos/nuevo')
    const precio = await screen.findByRole('textbox', { name: /Precio de compra/ })
    expect(precio.closest('[data-kit=campo]')?.querySelector('[data-prefijo]')?.textContent).toBe('$')
    expect(screen.getByText('Solo lo ven los administradores.')).toBeTruthy()
  })
})
