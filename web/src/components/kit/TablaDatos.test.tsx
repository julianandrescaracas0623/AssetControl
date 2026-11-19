import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { createPortal } from 'react-dom'
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

  // Spec 016, T8 (015-T4 R2): React propaga los eventos de un portal (el menú de la fila)
  // hasta la fila; lo que nace fuera de su DOM no la abre.
  it('un doble clic que viene de un portal (menú de la fila) no abre la fila', () => {
    const abrir = vi.fn()
    const portal = document.createElement('div')
    document.body.appendChild(portal)
    tabla({
      onAbrirFila: abrir,
      accionesFila: (f) => createPortal(<div role="menu"><a href="#ficha" role="menuitem">Ver ficha de {f.nombre}</a></div>, portal),
    })
    fireEvent.doubleClick(screen.getByRole('menuitem', { name: 'Ver ficha de Silla ergonómica' }))
    expect(abrir).not.toHaveBeenCalled()
    portal.remove()
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

  // Spec 016, T8: los nombres de la paginación son los que ya usaban Activos y Categorías.
  it('los botones se llaman «‹ Anterior» y «Siguiente ›»', () => {
    tabla({ paginacion: { desde: 26, hasta: 50, total: 60, onAnterior: vi.fn(), onSiguiente: vi.fn(), hayAnterior: true, haySiguiente: true } })
    const nav = screen.getByRole('navigation', { name: 'Paginación de activos' })
    expect(within(nav).getAllByRole('button').map((b) => b.textContent)).toEqual(['‹ Anterior', 'Siguiente ›'])
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

  // Spec 016, T10 (Deuda T7 a): la celda del pie que ocupa una columna lleva las clases de
  // esa columna (ancho, ajuste de línea, relleno), así el total no ensancha la tabla en el
  // teléfono; y admite clases propias.
  it('una celda del pie de una columna hereda la clase de su columna y admite la propia', () => {
    const columnas: ColumnaTabla<Fila>[] = [
      { ...COLUMNAS[0], clase: 'min-w-20' },
      { ...COLUMNAS[1], clase: 'whitespace-normal' },
      COLUMNAS[2],
      { ...COLUMNAS[3], clase: 'pr-4' },
    ]
    tabla({
      columnas,
      pie: [{ contenido: 'Total', columnas: 2 }, { contenido: '—', clase: 'italic' }, { contenido: '$ 1.639.900,00', tipo: 'cifra' }],
    })
    const pie = within(screen.getByRole('table')).getAllByRole('row').at(-1) as HTMLElement
    const [rotulo, medio, total] = within(pie).getAllByRole('cell')
    // Abarca dos columnas: no hereda la de ninguna.
    expect(rotulo.className).not.toContain('min-w-20')
    expect(rotulo.className).not.toContain('whitespace-normal')
    expect(medio.className).toContain('italic')
    expect(total.className).toContain('pr-4')
    expect(total.className).toContain('text-right')
  })

  it('desplazar en el teléfono: el rótulo de una celda ancha se queda a la vista al desplazar (sin tapar el total)', () => {
    simularAncho({ movil: true })
    tabla({ pie: [{ contenido: '2 activos no encontrados', columnas: 3 }, { contenido: '$ 1.639.900,00', tipo: 'cifra' }], movil: 'desplazar' })
    const pie = within(screen.getByRole('table')).getAllByRole('row').at(-1) as HTMLElement
    const [rotulo] = within(pie).getAllByRole('cell')
    expect(rotulo.className).not.toMatch(/\bsticky\b/)
    const texto = within(rotulo).getByText('2 activos no encontrados')
    expect(texto.className).toMatch(/\bsticky\b/)
    expect(texto.className).toContain('left-4')
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

// Spec 016, T9 (Categorías, Discrepancias): filas nombradas, encabezado solo para el
// lector y foco que no se pierde al llegar a la primera o la última página.
describe('TablaDatos: gestión (T9)', () => {
  it('nombrarFilas: cada fila (y cada tarjeta) se llama como su columna principal', () => {
    tabla({ nombrarFilas: true, accionesFila: (f) => <Boton variante="fantasma" soloIcono aria-label={`Renombrar ${f.nombre}`} icono={<span>✎</span>} /> })
    const fila = screen.getByRole('row', { name: 'Silla ergonómica' })
    expect(within(fila).getByRole('button', { name: 'Renombrar Silla ergonómica' })).toBeTruthy()
    // El encabezado no se nombra: solo las filas de datos.
    expect(screen.getAllByRole('row').filter((r) => r.getAttribute('aria-labelledby'))).toHaveLength(2)
    cleanup()
    simularAncho({ movil: true })
    tabla({ nombrarFilas: true })
    expect(screen.getByRole('listitem', { name: 'Impresora multifuncional' })).toBeTruthy()
  })

  it('sin nombrarFilas las filas no llevan aria-labelledby', () => {
    tabla()
    expect(screen.getAllByRole('row').some((r) => r.getAttribute('aria-labelledby'))).toBe(false)
  })

  it('encabezadoOculto: el texto queda solo para el lector (columna de casillas)', () => {
    const columnas: ColumnaTabla<Fila>[] = [{ id: 'sel', encabezado: 'Seleccionar', encabezadoOculto: true, celda: () => '·' }, ...COLUMNAS]
    tabla({ columnas })
    const th = screen.getAllByRole('columnheader')[0]
    expect(th.textContent).toBe('Seleccionar')
    expect(th.querySelector('.sr-only')?.textContent).toBe('Seleccionar')
  })

  it('al llegar a la última página el foco pasa a «‹ Anterior», y a la primera, a «Siguiente ›»', () => {
    const props = (desde: number, hasta: number) => ({
      desde,
      hasta,
      total: 50,
      hayAnterior: desde > 1,
      haySiguiente: hasta < 50,
      onAnterior: vi.fn(),
      onSiguiente: vi.fn(),
    })
    const { rerender } = tabla({ paginacion: props(1, 25) })
    const siguiente = screen.getByRole('button', { name: 'Siguiente ›' })
    siguiente.focus()
    fireEvent.click(siguiente)
    const comun = { etiqueta: 'Activos', columnas: COLUMNAS, filas: FILAS, claveFila: (f: Fila) => f.id, vacio: { titulo: 'Vacío' } }
    rerender(<TablaDatos<Fila> {...comun} paginacion={props(26, 50)} />)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '‹ Anterior' }))
    fireEvent.click(screen.getByRole('button', { name: '‹ Anterior' }))
    rerender(<TablaDatos<Fila> {...comun} paginacion={props(1, 25)} />)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Siguiente ›' }))
  })

  // Spec 016, T10 (Deuda T9 b): con paginación del servidor (cursor), un clic que no cambia
  // de página (la petición falla) no deja el «pulsado» armado: un cambio posterior (otro
  // filtro que deja una sola página) no le roba el foco a quien lo tenga.
  it('un clic cuya petición termina sin cambiar de página no mueve el foco después', () => {
    const props = (haySiguiente: boolean, ocupado: boolean) => ({
      desde: 26,
      hasta: 50,
      total: 60,
      hayAnterior: true,
      haySiguiente,
      ocupado,
      onAnterior: vi.fn(),
      onSiguiente: vi.fn(),
    })
    const comun = { etiqueta: 'Activos', columnas: COLUMNAS, filas: FILAS, claveFila: (f: Fila) => f.id, vacio: { titulo: 'Vacío' } }
    const { rerender } = tabla({ paginacion: props(true, false) })
    const siguiente = screen.getByRole('button', { name: 'Siguiente ›' })
    siguiente.focus()
    fireEvent.click(siguiente)
    rerender(<TablaDatos<Fila> {...comun} paginacion={props(true, true)} />)
    rerender(<TablaDatos<Fila> {...comun} paginacion={props(true, false)} />)
    const otro = document.createElement('input')
    document.body.append(otro)
    otro.focus()
    rerender(<TablaDatos<Fila> {...comun} paginacion={props(false, false)} />)
    expect(document.activeElement).toBe(otro)
    otro.remove()
  })

  it('la búsqueda no se autocompleta con lo que guardó el navegador', () => {
    tabla({ barra: { busqueda: { valor: '', onCambio: vi.fn(), etiqueta: 'Buscar activos' } } })
    expect(screen.getByRole('searchbox', { name: 'Buscar activos' }).getAttribute('autocomplete')).toBe('off')
  })
})

// Spec 016, T10 (Deuda T7 a): a 375 px Valor desplazaba 12 px dentro de la tabla. Por
// debajo de md las celdas usan 8 px de relleno lateral (12 px desde md).
describe('TablaDatos: relleno compacto en el teléfono', () => {
  it('encabezados, celdas y pie con px-2 y md:px-3', () => {
    simularAncho({ movil: true })
    tabla({ movil: 'desplazar', pie: [{ contenido: 'Total', columnas: 3 }, { contenido: '$ 1,00', tipo: 'cifra' }] })
    const t = screen.getByRole('table')
    const celdas = [within(t).getAllByRole('columnheader')[1], within(t).getAllByRole('cell')[1], within(t).getAllByRole('row').at(-1)!.querySelectorAll('td')[1]]
    for (const c of celdas) {
      expect(c.className.split(/\s+/)).toContain('px-2')
      expect(c.className.split(/\s+/)).toContain('md:px-3')
    }
  })
})
