import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { simularAncho } from '@/test/matchMedia'

import { Boton } from './Boton'
import { TablaDatos, type ColumnaTabla, type OrdenTabla } from './TablaDatos'

// Spec 016, T3 (docs/08 §4.3, §4.4): tabla de datos sin @tanstack/react-table. El orden,
// el filtro y la paginación los decide quien la usa (cliente o servidor); la tabla los
// presenta y avisa. Datos ficticios.

afterEach(cleanup)

type Fila = { id: string; codigo: string; nombre: string; ubicacion: string; precio?: string }

const FILAS: Fila[] = [
  { id: 'a', codigo: '000457', nombre: 'Silla ergonómica', ubicacion: 'Sala 2', precio: '$ 389.900,00' },
  { id: 'b', codigo: '000215', nombre: 'Impresora multifuncional', ubicacion: 'Recepción', precio: '$ 1.250.000,00' },
]

const COLUMNAS: ColumnaTabla<Fila>[] = [
  { id: 'codigo', encabezado: 'Código', celda: (f) => f.codigo, tipo: 'codigo', ordenable: true },
  { id: 'nombre', encabezado: 'Nombre', celda: (f) => f.nombre, principal: true, ordenable: true },
  { id: 'ubicacion', encabezado: 'Ubicación', celda: (f) => f.ubicacion },
  { id: 'precio', encabezado: 'Precio de compra', celda: (f) => f.precio ?? '—', tipo: 'cifra' },
]

function tabla(props: Partial<Parameters<typeof TablaDatos<Fila>>[0]> = {}) {
  return render(
    <TablaDatos<Fila>
      etiqueta="Activos"
      columnas={COLUMNAS}
      filas={FILAS}
      claveFila={(f) => f.id}
      vacio={{ titulo: 'Aún no hay activos', descripcion: 'Escanea un sticker para crear el primero.' }}
      {...props}
    />,
  )
}

describe('TablaDatos: tabla', () => {
  it('tabla nombrada con encabezados, celdas, códigos en mono y cifras a la derecha', () => {
    tabla()
    const t = screen.getByRole('table', { name: 'Activos' })
    expect(within(t).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Código', 'Nombre', 'Ubicación', 'Precio de compra'])
    expect(within(t).getAllByRole('row')).toHaveLength(3)
    expect(within(t).getByText('000457').closest('td')?.className).toContain('font-mono')
    const precio = within(t).getByText('$ 389.900,00').closest('td') as HTMLElement
    expect(precio.className).toContain('text-right')
    expect(precio.className).toContain('tabular-nums')
    expect(within(t).getAllByRole('columnheader')[3].className).toContain('text-right')
  })

  it('las filas miden la altura de la densidad (h-fila)', () => {
    tabla()
    expect(screen.getAllByRole('row')[1].className).toContain('h-fila')
  })

  it('orden accesible: aria-sort en el encabezado y el botón avisa la nueva dirección', () => {
    const cambio = vi.fn<(o: OrdenTabla) => void>()
    const { rerender } = tabla({ orden: { columna: 'codigo', direccion: 'asc' }, onOrdenChange: cambio })
    const [codigo, nombre, ubicacion] = screen.getAllByRole('columnheader')
    expect(codigo.getAttribute('aria-sort')).toBe('ascending')
    expect(nombre.getAttribute('aria-sort')).toBe('none')
    expect(ubicacion.getAttribute('aria-sort')).toBeNull()
    expect(within(ubicacion).queryByRole('button')).toBeNull()

    fireEvent.click(within(codigo).getByRole('button', { name: /Código/ }))
    expect(cambio).toHaveBeenLastCalledWith({ columna: 'codigo', direccion: 'desc' })
    fireEvent.click(within(nombre).getByRole('button', { name: /Nombre/ }))
    expect(cambio).toHaveBeenLastCalledWith({ columna: 'nombre', direccion: 'asc' })

    rerender(
      <TablaDatos<Fila>
        etiqueta="Activos"
        columnas={COLUMNAS}
        filas={FILAS}
        claveFila={(f) => f.id}
        vacio={{ titulo: 'x' }}
        orden={{ columna: 'codigo', direccion: 'desc' }}
        onOrdenChange={cambio}
      />,
    )
    expect(screen.getAllByRole('columnheader')[0].getAttribute('aria-sort')).toBe('descending')
  })

  it('fila: doble clic o Enter la abren; un doble clic en un control de la fila no', () => {
    const abrir = vi.fn()
    const menu = vi.fn()
    tabla({
      onAbrirFila: abrir,
      accionesFila: (f) => <Boton variante="fantasma" soloIcono aria-label={`Acciones de ${f.nombre}`} icono={<span>⋯</span>} onClick={menu} />,
    })
    const fila = screen.getAllByRole('row')[1]
    expect(fila.getAttribute('tabindex')).toBe('0')
    fireEvent.doubleClick(within(fila).getByText('Silla ergonómica'))
    expect(abrir).toHaveBeenLastCalledWith(FILAS[0])
    fila.focus()
    fireEvent.keyDown(fila, { key: 'Enter' })
    expect(abrir).toHaveBeenCalledTimes(2)
    fireEvent.doubleClick(screen.getByRole('button', { name: 'Acciones de Silla ergonómica' }))
    expect(abrir).toHaveBeenCalledTimes(2)
    expect(screen.getAllByRole('columnheader').at(-1)?.textContent).toBe('Acciones')
  })

  it('sin onAbrirFila la fila no es enfocable', () => {
    tabla()
    expect(screen.getAllByRole('row')[1].getAttribute('tabindex')).toBeNull()
  })
})

describe('TablaDatos: estados (R3)', () => {
  it('cargando: esqueleto anunciado con la etiqueta', () => {
    tabla({ filas: undefined, cargando: true })
    expect(screen.getByRole('status', { name: 'Cargando activos' }).getAttribute('aria-busy')).toBe('true')
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('error: aviso con «Reintentar» que llama al callback', () => {
    const reintentar = vi.fn()
    tabla({ filas: undefined, error: { titulo: 'No se pudieron cargar los activos', descripcion: 'Sin conexión.', onReintentar: reintentar } })
    const aviso = screen.getByRole('alert')
    expect(aviso.textContent).toContain('No se pudieron cargar los activos')
    fireEvent.click(within(aviso).getByRole('button', { name: 'Reintentar' }))
    expect(reintentar).toHaveBeenCalledOnce()
  })

  it('vacío: título, descripción y la acción que lo resuelve', () => {
    const limpiar = vi.fn()
    tabla({ filas: [], vacio: { titulo: 'Nada coincide', descripcion: 'Prueba con otro código.', accion: <Boton onClick={limpiar}>Limpiar filtros</Boton> } })
    expect(screen.getByText('Nada coincide')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(limpiar).toHaveBeenCalledOnce()
    expect(screen.queryByRole('table')).toBeNull()
  })
})

describe('TablaDatos: barra de herramientas y paginación', () => {
  it('búsqueda con nombre, filtros, «Limpiar filtros» y acción principal; la barra sigue al cargar', () => {
    const buscar = vi.fn()
    const limpiar = vi.fn()
    tabla({
      cargando: true,
      filas: undefined,
      barra: {
        busqueda: { valor: 'sil', onCambio: buscar, etiqueta: 'Buscar activos', placeholder: 'Código, nombre o serial' },
        filtros: <Boton variante="secundario">Categoría</Boton>,
        hayFiltros: true,
        onLimpiar: limpiar,
        accion: <Boton>Registrar activo</Boton>,
      },
    })
    const busqueda = screen.getByRole('searchbox', { name: 'Buscar activos' }) as HTMLInputElement
    expect(busqueda.value).toBe('sil')
    fireEvent.change(busqueda, { target: { value: 'silla' } })
    expect(buscar).toHaveBeenCalledWith('silla')
    expect(screen.getByRole('button', { name: 'Categoría' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(limpiar).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Registrar activo' })).toBeTruthy()
    expect(screen.getByRole('status', { name: 'Cargando activos' })).toBeTruthy()
  })

  it('sin filtros activos no ofrece «Limpiar filtros»', () => {
    tabla({ barra: { hayFiltros: false, onLimpiar: vi.fn() } })
    expect(screen.queryByRole('button', { name: 'Limpiar filtros' })).toBeNull()
  })

  it('paginación «1–25 de 200» con anterior y siguiente', () => {
    const anterior = vi.fn()
    const siguiente = vi.fn()
    tabla({ paginacion: { desde: 1, hasta: 25, total: 1250, onAnterior: anterior, onSiguiente: siguiente, hayAnterior: false, haySiguiente: true } })
    const nav = screen.getByRole('navigation', { name: 'Paginación de activos' })
    expect(nav.textContent).toContain('1–25 de 1.250')
    expect((within(nav).getByRole('button', { name: /Anterior/ }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(within(nav).getByRole('button', { name: /Siguiente/ }))
    expect(siguiente).toHaveBeenCalledOnce()
    expect(anterior).not.toHaveBeenCalled()
  })

  it('paginación ocupada: no deja pedir otra página mientras llega', () => {
    tabla({ paginacion: { desde: 26, hasta: 50, total: 60, onAnterior: vi.fn(), onSiguiente: vi.fn(), hayAnterior: true, haySiguiente: true, ocupado: true } })
    const nav = screen.getByRole('navigation', { name: 'Paginación de activos' })
    for (const b of within(nav).getAllByRole('button')) expect((b as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('TablaDatos: por debajo de md (docs/08 §4.4)', () => {
  it('tarjetas: una por fila, la columna principal como título y el resto rótulo/valor', () => {
    simularAncho({ movil: true })
    tabla({ accionesFila: (f) => <Boton variante="fantasma" soloIcono aria-label={`Acciones de ${f.nombre}`} icono={<span>⋯</span>} /> })
    expect(screen.queryByRole('table')).toBeNull()
    const lista = screen.getByRole('list', { name: 'Activos' })
    const items = within(lista).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(within(items[0]).getByText('Silla ergonómica').closest('[data-tarjeta=titulo]')).toBeTruthy()
    const rotulos = Array.from(items[0].querySelectorAll('dt')).map((dt) => dt.textContent)
    expect(rotulos).toEqual(['Código', 'Ubicación', 'Precio de compra'])
    expect(within(items[0]).getByRole('button', { name: 'Acciones de Silla ergonómica' })).toBeTruthy()
  })

  it('tarjeta propia si la pantalla la necesita', () => {
    simularAncho({ movil: true })
    tabla({ tarjeta: (f) => <p>Tarjeta {f.codigo}</p> })
    expect(screen.getByText('Tarjeta 000457')).toBeTruthy()
  })

  it('desplazar: conserva la tabla con desplazamiento y la primera columna fija', () => {
    simularAncho({ movil: true })
    tabla({ movil: 'desplazar' })
    const t = screen.getByRole('table', { name: 'Activos' })
    expect(within(t).getAllByRole('columnheader')[0].className).toContain('sticky')
    expect(within(t).getByText('000457').closest('td')?.className).toContain('sticky')
  })
})

// Spec 016, T7: fila de total del servidor (valor actual, desglose del informe, no
// encontrados). La tabla no suma: cada celda del pie llega ya formateada.
describe('TablaDatos: pie (fila de total)', () => {
  const PIE = [
    { contenido: 'Total', columnas: 3 },
    { contenido: '$ 1.639.900,00', tipo: 'cifra' as const },
  ]

  it('en la tabla: una fila de pie con las celdas dadas, cifras a la derecha y el ancho pedido', () => {
    tabla({ pie: PIE })
    const t = screen.getByRole('table', { name: 'Activos' })
    const filas = within(t).getAllByRole('row')
    expect(filas).toHaveLength(4)
    const pie = filas.at(-1) as HTMLElement
    expect(pie.closest('tfoot')).toBeTruthy()
    const celdas = within(pie).getAllByRole('cell')
    expect(celdas.map((c) => c.textContent)).toEqual(['Total', '$ 1.639.900,00'])
    expect(celdas[0].getAttribute('colspan')).toBe('3')
    expect(celdas[1].className).toContain('text-right')
    expect(celdas[1].className).toContain('tabular-nums')
  })

  it('con acciones por fila, el pie completa la columna de acciones', () => {
    tabla({ pie: PIE, accionesFila: () => <span>⋯</span> })
    const pie = within(screen.getByRole('table')).getAllByRole('row').at(-1) as HTMLElement
    expect(within(pie).getAllByRole('cell')).toHaveLength(3)
  })

  it('desplazar en el teléfono: una primera celda del pie de una sola columna queda fija y es opaca', () => {
    simularAncho({ movil: true })
    tabla({
      pie: [{ contenido: 'Total' }, { contenido: '—' }, { contenido: '—' }, { contenido: '$ 1.639.900,00', tipo: 'cifra' }],
      movil: 'desplazar',
    })
    const pie = within(screen.getByRole('table')).getAllByRole('row').at(-1) as HTMLElement
    const primera = within(pie).getAllByRole('cell')[0]
    expect(primera.className).toContain('sticky')
    expect(primera.className).toContain('bg-muted')
  })

  // Revisión de la T7: una celda fija que abarca varias columnas mide más que la pantalla
  // y, al desplazar, tapa el total del final (el precio congelado de los no encontrados).
  it.each([2, 3, 5])('desplazar en el teléfono: una celda del pie que abarca %i columnas no queda fija ni tapa el total', (columnas) => {
    simularAncho({ movil: true })
    tabla({ pie: [{ contenido: '2 activos no encontrados · lista congelada al cierre', columnas }, { contenido: '$ 1.639.900,00', tipo: 'cifra' }], movil: 'desplazar' })
    const pie = within(screen.getByRole('table')).getAllByRole('row').at(-1) as HTMLElement
    const [rotulo, total] = within(pie).getAllByRole('cell')
    expect(rotulo.getAttribute('colspan')).toBe(String(columnas))
    expect(rotulo.className).not.toMatch(/\bsticky\b/)
    expect(rotulo.className).not.toMatch(/\bz-10\b/)
    expect(total.className).not.toMatch(/\bsticky\b/)
    expect(total.textContent).toBe('$ 1.639.900,00')
  })

  it('tarjetas en el teléfono: el pie va al final como resumen', () => {
    simularAncho({ movil: true })
    tabla({ pie: PIE })
    const resumen = document.querySelector('[data-tabla=pie]') as HTMLElement
    expect(resumen.textContent).toBe('Total$ 1.639.900,00')
  })

  it('sin filas no hay pie', () => {
    tabla({ pie: PIE, filas: [] })
    expect(document.querySelector('tfoot')).toBeNull()
    expect(document.querySelector('[data-tabla=pie]')).toBeNull()
  })
})
