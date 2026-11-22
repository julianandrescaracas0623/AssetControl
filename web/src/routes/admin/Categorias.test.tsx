import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { normalizarBusqueda } from '@/lib/catalogo'
import { routes } from '@/router'
import { crearCatalogo } from '@/test/catalogo'
import { simularAncho } from '@/test/matchMedia'
import { errorApi, llamadas, simularSesion } from '@/test/sesion'

// Spec 003, T6 (R3, R6; plan §5): lista cerrada de categorías del tenant.
// Spec 015, T6 (R12, Q10 = A): búsqueda y paginación en el cliente, estado en la URL.

afterEach(cleanup)

function abrir(catalogo = crearCatalogo(), ruta = '/admin/categorias') {
  const f = simularSesion('admin', catalogo.manejador)
  const router = createMemoryRouter(routes, { initialEntries: [ruta] })
  render(<RouterProvider router={router} />)
  return { catalogo, f, router }
}

const titulo = () => screen.findByRole('heading', { level: 1, name: 'Categorías' })
// En computador cada categoría es una fila de tabla; en teléfono, un elemento de lista.
const fila = (nombre: string) => screen.findByRole('row', { name: nombre })
const filasDeDatos = () => screen.getAllByRole('row').filter((r) => r.getAttribute('aria-labelledby'))

const muchas = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `c${i + 1}`, nombre: `Categoría ${String(i + 1).padStart(3, '0')}` }))

describe('/admin/categorias', () => {
  it('vacía: carga las 6 sugeridas con un botón', async () => {
    const { f } = abrir()
    await titulo()
    expect(await screen.findByText('Aún no hay categorías')).toBeTruthy()
    expect(screen.queryByRole('searchbox')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Cargar las 6 sugeridas' }))
    for (const nombre of ['Mobiliario', 'Electrónica', 'CPU', 'Periféricos', 'Electrodomésticos', 'Biomédicos']) {
      expect(await fila(nombre)).toBeTruthy()
    }
    expect(await screen.findByText('Se agregaron 6 categorías')).toBeTruthy()
    expect(llamadas(f, '/api/categorias/sugeridas')).toHaveLength(1)
  })

  it('crea y renombra', async () => {
    const { catalogo } = abrir(crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }))
    await titulo()
    await fila('CPU')

    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }))
    let dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Equipo de laboratorio' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear' }))
    expect(await fila('Equipo de laboratorio')).toBeTruthy()

    fireEvent.click(within(await fila('CPU')).getByRole('button', { name: 'Renombrar CPU' }))
    dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Computadores' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
    expect(await fila('Computadores')).toBeTruthy()
    expect(catalogo.categorias.map((c) => c.nombre)).toEqual(['Computadores', 'Equipo de laboratorio'])
  })

  it('un nombre repetido se marca en el campo', async () => {
    const { catalogo } = abrir(crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }))
    catalogo.fallar('POST /api/categorias', () =>
      errorApi(409, 'nombre_duplicado', 'Ya existe uno con ese nombre en el mismo lugar.'),
    )
    await titulo()
    await fila('CPU')
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'cpu' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear' }))
    expect(await within(dialogo).findByText('Ya existe una categoría con ese nombre.')).toBeTruthy()
    expect(within(dialogo).getByLabelText('Nombre').getAttribute('aria-invalid')).toBe('true')
  })

  it('con categorías, "Cargar sugeridas" agrega solo las que faltan', async () => {
    abrir(crearCatalogo({ categorias: [{ id: 'c1', nombre: 'CPU' }] }))
    await titulo()
    await fila('CPU')
    fireEvent.click(screen.getByRole('button', { name: 'Cargar sugeridas' }))
    expect(await screen.findByText('Se agregaron 5 categorías')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cargar sugeridas' }))
    expect(await screen.findByText('Ya estaban todas las sugeridas')).toBeTruthy()
  })
})

describe('/admin/categorias con muchas categorías (spec 015, T6)', () => {
  it('normaliza sin tildes, mayúsculas ni espacios de más', () => {
    expect(normalizarBusqueda('  ELECTRÓNICA   Médica ')).toBe('electronica medica')
    expect(normalizarBusqueda('Ñandú')).toBe('nandu')
  })

  it('con 200 categorías pagina de a 25 y guarda la página en la URL', async () => {
    const { router } = abrir(crearCatalogo({ categorias: muchas(200) }))
    await fila('Categoría 001')
    expect(filasDeDatos()).toHaveLength(25)
    expect(screen.getByText('200 categorías')).toBeTruthy()
    expect(screen.getByText('1–25 de 200')).toBeTruthy()
    expect(screen.queryByRole('row', { name: 'Categoría 026' })).toBeNull()
    expect((screen.getByRole('button', { name: '‹ Anterior' }) as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'Siguiente ›' }))
    expect(await fila('Categoría 026')).toBeTruthy()
    expect(screen.queryByRole('row', { name: 'Categoría 001' })).toBeNull()
    expect(screen.getByText('26–50 de 200')).toBeTruthy()
    expect(new URLSearchParams(router.state.location.search).get('pagina')).toBe('2')

    for (let i = 0; i < 6; i++) fireEvent.click(screen.getByRole('button', { name: 'Siguiente ›' }))
    expect(await fila('Categoría 200')).toBeTruthy()
    expect(screen.getByText('176–200 de 200')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Siguiente ›' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('busca sin tildes ni mayúsculas, vuelve a la página 1 y muestra «n de N»', async () => {
    const categorias = [...muchas(119), { id: 'e1', nombre: 'Electrónica médica' }]
    const { router } = abrir(crearCatalogo({ categorias }), '/admin/categorias?pagina=3')
    await fila('Categoría 051')

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar categorías' }), { target: { value: 'ELECTRONICA' } })
    expect(await fila('Electrónica médica')).toBeTruthy()
    expect(filasDeDatos()).toHaveLength(1)
    expect(screen.getByText('1 de 120 categorías')).toBeTruthy()
    const busqueda = new URLSearchParams(router.state.location.search)
    expect(busqueda.get('q')).toBe('ELECTRONICA')
    expect(busqueda.get('pagina')).toBeNull()
    // Una sola página: no hace falta paginar.
    expect(screen.queryByRole('button', { name: 'Siguiente ›' })).toBeNull()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar categorías' }), { target: { value: 'categoria 11' } })
    expect(await fila('Categoría 110')).toBeTruthy()
    expect(screen.getByText('10 de 120 categorías')).toBeTruthy()
  })

  it('sin resultados ofrece limpiar la búsqueda', async () => {
    const { router } = abrir(crearCatalogo({ categorias: muchas(120) }))
    await fila('Categoría 001')
    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar categorías' }), { target: { value: 'zzz' } })
    expect(await screen.findByText('Ninguna categoría coincide')).toBeTruthy()
    expect(screen.getByText('0 de 120 categorías')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar búsqueda' }))
    expect(await fila('Categoría 001')).toBeTruthy()
    expect((screen.getByRole('searchbox', { name: 'Buscar categorías' }) as HTMLInputElement).value).toBe('')
    expect(router.state.location.search).toBe('')
  })

  it('restaura búsqueda y página desde la URL y corrige una página fuera de rango', async () => {
    abrir(crearCatalogo({ categorias: muchas(120) }), '/admin/categorias?q=categor%C3%ADa%200&pagina=2')
    expect(await fila('Categoría 026')).toBeTruthy()
    expect((screen.getByRole('searchbox', { name: 'Buscar categorías' }) as HTMLInputElement).value).toBe('categoría 0')
    expect(screen.getByText('99 de 120 categorías')).toBeTruthy()
    cleanup()

    abrir(crearCatalogo({ categorias: muchas(120) }), '/admin/categorias?pagina=99')
    expect(await fila('Categoría 120')).toBeTruthy()
    expect(screen.getByText('101–120 de 120')).toBeTruthy()
  })

  it('una página no numérica o negativa abre la primera', async () => {
    for (const ruta of ['/admin/categorias?pagina=abc', '/admin/categorias?pagina=-3']) {
      abrir(crearCatalogo({ categorias: muchas(120) }), ruta)
      expect(await fila('Categoría 001')).toBeTruthy()
      expect(screen.getByText('1–25 de 120')).toBeTruthy()
      cleanup()
    }
  })

  it('si una recarga reduce el total, la página se corrige a la última', async () => {
    const { catalogo } = abrir(crearCatalogo({ categorias: muchas(120) }), '/admin/categorias?pagina=5')
    fireEvent.click(within(await fila('Categoría 101')).getByRole('button', { name: 'Renombrar Categoría 101' }))
    const dialogo = await screen.findByRole('dialog')
    // Otra persona borró del catálogo mientras tanto: la recarga trae 50.
    catalogo.categorias.splice(30, 70)
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Sillas' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('26–50 de 50')).toBeTruthy()
    expect(await fila('Sillas')).toBeTruthy()
  })

  it('al cambiar de página lo anuncia y no pierde el foco en el botón que se deshabilita', async () => {
    abrir(crearCatalogo({ categorias: muchas(50) }))
    await fila('Categoría 001')
    const estado = screen.getByRole('status')
    expect(estado.textContent).toContain('Página 1 de 2')

    const siguiente = screen.getByRole('button', { name: 'Siguiente ›' })
    siguiente.focus()
    fireEvent.click(siguiente)
    expect(await fila('Categoría 026')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('Página 2 de 2')
    expect((siguiente as HTMLButtonElement).disabled).toBe(true)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '‹ Anterior' }))

    fireEvent.click(screen.getByRole('button', { name: '‹ Anterior' }))
    expect(await fila('Categoría 001')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('Página 1 de 2')
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Siguiente ›' }))
  })

  it('guarda la búsqueda recortada en la URL sin tocar lo que se escribe', async () => {
    const { router } = abrir(crearCatalogo({ categorias: muchas(30) }))
    await fila('Categoría 001')
    const campo = screen.getByRole('searchbox', { name: 'Buscar categorías' }) as HTMLInputElement
    fireEvent.change(campo, { target: { value: '  categoría 01 ' } })
    expect(await fila('Categoría 010')).toBeTruthy()
    expect(campo.value).toBe('  categoría 01 ')
    expect(new URLSearchParams(router.state.location.search).get('q')).toBe('categoría 01')
  })

  it('al crear con un filtro y en otra página avisa con el nombre, limpia el filtro y va a su página', async () => {
    const { router } = abrir(crearCatalogo({ categorias: muchas(60) }), '/admin/categorias?q=categoria%200&pagina=2')
    await fila('Categoría 026')
    fireEvent.click(screen.getByRole('button', { name: 'Nueva categoría' }))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Zeta' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Crear' }))
    expect(await screen.findByText('Categoría «Zeta» creada')).toBeTruthy()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect((screen.getByRole('searchbox', { name: 'Buscar categorías' }) as HTMLInputElement).value).toBe('')
    // El servidor la devuelve al final (61 de 61): queda en la página 3.
    expect(await fila('Zeta')).toBeTruthy()
    const busqueda = new URLSearchParams(router.state.location.search)
    expect(busqueda.get('q')).toBeNull()
    expect(busqueda.get('pagina')).toBe('3')
    expect(screen.getByText('51–61 de 61')).toBeTruthy()
  })

  it('en teléfono es una lista tocable y renombrar sigue igual', async () => {
    simularAncho({ movil: true })
    const { catalogo } = abrir(crearCatalogo({ categorias: muchas(120) }))
    const item = await screen.findByRole('listitem', { name: 'Categoría 001' })
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getAllByRole('listitem').length).toBeGreaterThanOrEqual(25)
    const boton = within(item).getByRole('button', { name: 'Renombrar Categoría 001' })
    // Spec 016, T9: selector de clase visual size-11 → size-control (48 px en el teléfono, D6).
    expect(boton.className).toContain('size-control')
    fireEvent.click(boton)
    const dialogo = await screen.findByRole('dialog')
    fireEvent.change(within(dialogo).getByLabelText('Nombre'), { target: { value: 'Sillas' } })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('listitem', { name: 'Sillas' })).toBeTruthy()
    expect(catalogo.categorias[0].nombre).toBe('Sillas')
  })
})
