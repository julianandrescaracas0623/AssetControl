import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { routes } from '@/router'
import { simularSesion } from '@/test/sesion'

// Spec 001b, T8: maquetas de administración con datos ficticios y sus cuatro
// estados (R13, A9). Sin gráficas (spec 010).

afterEach(cleanup)

async function abrir(path: string) {
  simularSesion('admin')
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  await screen.findByRole('heading', { level: 1 })
  return router
}

function pestaña(nombre: RegExp | string) {
  const tab = screen.getByRole('tab', { name: nombre })
  fireEvent.mouseDown(tab, { button: 0 })
  return tab
}

describe('Inicio', () => {
  it('muestra indicadores, informe congelado y valor actual separados, y actividad', async () => {
    await abrir('/admin')
    expect(screen.getByRole('heading', { level: 1, name: 'Resumen' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Activos hoy/ }).textContent).toContain('219')
    const informe = screen.getByRole('region', { name: /Informe congelado/ })
    const valor = screen.getByRole('region', { name: /Valor actual/ })
    expect(informe).not.toBe(valor)
    expect(informe.contains(valor) || valor.contains(informe)).toBe(false)
    expect(screen.getByRole('link', { name: /Discrepancias\s*3/ }).textContent).toContain('3')
    expect(screen.getByRole('region', { name: 'Actividad reciente' }).textContent).toContain('Autoclave clase B 18 L')
  })

  it.each([
    ['cargando', 'Cargando el resumen'],
    ['vacio', 'Aún no hay activos ni sesiones'],
    ['error', 'No se pudo cargar'],
  ])('estado %s', async (estado, texto) => {
    await abrir(`/admin?estado=${estado}`)
    expect(screen.getAllByText(texto).length).toBeGreaterThan(0)
  })

  it('el error ofrece reintentar', async () => {
    await abrir('/admin?estado=error')
    expect(screen.getByRole('link', { name: 'Reintentar' })).toBeTruthy()
  })
})

describe('Activos', () => {
  it('lista los activos con precio para el admin y filtra por código', async () => {
    await abrir('/admin/activos')
    const tabla = screen.getByRole('table')
    expect(within(tabla).getAllByRole('row')).toHaveLength(13)
    expect(within(tabla).getByText('$ 14.200.000,00')).toBeTruthy()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: '000123' } })
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2)
  })

  it('filtra por estado con las pestañas', async () => {
    await abrir('/admin/activos')
    pestaña(/En reparación/)
    const filas = within(screen.getByRole('table')).getAllByRole('row')
    expect(filas).toHaveLength(2)
    expect(filas[1].textContent).toContain('Compresor libre de aceite')
  })

  it('sin coincidencias ofrece limpiar los filtros', async () => {
    await abrir('/admin/activos')
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar activos' }), { target: { value: 'zzzz' } })
    expect(screen.getByText('Nada coincide')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(13)
  })

  it('dar de baja pide confirmación con su efecto', async () => {
    await abrir('/admin/activos')
    fireEvent.keyDown(screen.getByRole('button', { name: 'Acciones de Monitor 24″ (000210)' }), { key: 'Enter' })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Dar de baja' }))
    const dialogo = await screen.findByRole('alertdialog')
    expect(within(dialogo).getByRole('heading', { name: '¿Dar de baja «Monitor 24″»?' })).toBeTruthy()
    expect(dialogo.textContent).toMatch(/no se borra/i)
    expect(within(dialogo).getByRole('button', { name: 'Cancelar' })).toBeTruthy()
  })

  it('estado vacío invita a registrar', async () => {
    await abrir('/admin/activos?estado=vacio')
    expect(screen.getByText('Aún no hay activos')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: 'Registrar activo' }).length).toBeGreaterThan(0)
  })
})

describe('Registrar activo', () => {
  it('no guarda sin código, nombre, precio, categoría ni ubicación', async () => {
    await abrir('/admin/activos/nuevo')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    for (const mensaje of [
      'Escanea o escribe el código del sticker',
      'Escribe el nombre',
      'Escribe el precio',
      'Elige la categoría',
      'Elige la ubicación',
    ]) {
      expect(screen.getByText(mensaje)).toBeTruthy()
    }
    expect(screen.queryByText('Activo creado')).toBeNull()
  })

  it('rechaza un código que ya existe', async () => {
    await abrir('/admin/activos/nuevo')
    fireEvent.change(screen.getByRole('textbox', { name: /Código del sticker/ }), { target: { value: '000123' } })
    expect(screen.getByText('Ese código ya existe')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Abrir activo' }).getAttribute('href')).toBe('/admin/activos/000123')
  })

  it('copiar de un parecido llena los datos y guarda', async () => {
    await abrir('/admin/activos/nuevo')
    fireEvent.change(screen.getByRole('textbox', { name: /Código del sticker/ }), { target: { value: '000458' } })
    expect(screen.getByText('Código libre')).toBeTruthy()
    fireEvent.click(screen.getByRole('checkbox', { name: /Revisé que coincide/ }))
    fireEvent.click(screen.getByRole('combobox', { name: /Copiar de un parecido/ }))
    const campo = await screen.findByRole('combobox', { name: 'Buscar activo parecido' })
    fireEvent.change(campo, { target: { value: 'silla' } })
    fireEvent.keyDown(campo, { key: 'Enter' })
    expect((screen.getByRole('textbox', { name: /Nombre/ }) as HTMLInputElement).value).toBe('Silla ergonómica')
    expect((screen.getByRole('textbox', { name: /Precio de compra/ }) as HTMLInputElement).value).toBe('389.900')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar activo' }))
    expect(await screen.findByText('Activo creado')).toBeTruthy()
    expect(screen.getByText(/000458/)).toBeTruthy()
  })

  it('el error de guardado ofrece reintentar', async () => {
    await abrir('/admin/activos/nuevo?estado=error')
    expect(screen.getByText('No se pudo guardar. Revisa la conexión.')).toBeTruthy()
  })
})

describe('Informe de sesión', () => {
  it('muestra tres cifras congeladas y el desglose por pestañas', async () => {
    await abrir('/admin/sesiones/conteo-may-2026/informe')
    expect(screen.getByRole('heading', { level: 1, name: 'Informe · Conteo may 2026' })).toBeTruthy()
    expect(screen.getByRole('region', { name: /Informe congelado/ }).textContent).toContain('$ 276.850.300,00')
    expect(within(screen.getByRole('table')).getByText('Biomédicos')).toBeTruthy()
    pestaña('Por ubicación')
    expect(within(screen.getByRole('table')).getByText('Bodega')).toBeTruthy()
    pestaña(/No encontrados/)
    const tabla = screen.getByRole('table')
    expect(within(tabla).getAllByText('En reparación')).toHaveLength(1)
    expect(tabla.textContent).toContain('$ 14.731.900,00')
  })

  it('con la sesión abierta no hay informe', async () => {
    await abrir('/admin/sesiones/conteo-may-2026/informe?estado=vacio')
    expect(screen.getByText('El informe se genera al cerrar la sesión.')).toBeTruthy()
  })
})
