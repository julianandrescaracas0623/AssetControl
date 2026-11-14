import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AssetCard } from './AssetCard'
import { EmptyState } from './EmptyState'
import { LiveValueCard, ThreeFiguresCard } from './FigureCards'
import { LocationPicker } from './LocationPicker'
import { PendingList } from './PendingList'
import { StatCard } from './StatCard'
import type { InformeCongelado, ValorActual } from '@/lib/cifras'

// Spec 001b, T7: componentes propios de datos (R10, R11, R12; A7).

afterEach(cleanup)

const informe: InformeCongelado = {
  fuente: 'informe_congelado',
  sesion: 'Conteo may 2026',
  corte: '15/05/2026',
  encontrado: { valor: '262118400.00', unidades: 198 },
  noEncontrado: { valor: '14731900.00', unidades: 9 },
  total: { valor: '276850300.00', unidades: 207 },
}
const valorActual: ValorActual = { fuente: 'valor_actual', valor: '286450300.00', activos: 219, consultadoA: '10:42' }

const activo = {
  codigo: '000123',
  nombre: 'Autoclave clase B 18 L',
  categoria: 'Biomédicos',
  ubicacion: 'Esterilización',
  estado: 'activo' as const,
  precio: '14200000.00',
}

describe('cifras: informe congelado y valor actual (R10)', () => {
  it('ThreeFiguresCard rotula «Informe congelado» y muestra las tres cifras', () => {
    render(<ThreeFiguresCard informe={informe} />)
    const tarjeta = screen.getByRole('region', { name: /Informe congelado/ })
    expect(tarjeta.textContent).toContain('$ 262.118.400,00')
    expect(tarjeta.textContent).toContain('$ 14.731.900,00')
    expect(tarjeta.textContent).toContain('$ 276.850.300,00')
    expect(tarjeta.textContent).toContain('corte 15/05/2026')
    expect(tarjeta.textContent).not.toContain('Valor actual')
  })

  it('LiveValueCard rotula «Valor actual · no es el informe»', () => {
    render(<LiveValueCard valor={valorActual} />)
    const tarjeta = screen.getByRole('region', { name: /Valor actual/ })
    expect(tarjeta.textContent).toContain('No es el informe')
    expect(tarjeta.textContent).toContain('$ 286.450.300,00')
    expect(tarjeta.textContent).not.toContain('Informe congelado')
  })

  it('los tipos no se mezclan (lo comprueba npm run typecheck)', () => {
    // @ts-expect-error: un valor actual no es un informe congelado.
    const malo1 = <ThreeFiguresCard informe={valorActual} />
    // @ts-expect-error: un informe congelado no es un valor actual.
    const malo2 = <LiveValueCard valor={informe} />
    expect([malo1, malo2]).toHaveLength(2)
  })
})

describe('AssetCard (R11)', () => {
  it('el admin ve el precio de referencia', () => {
    render(<AssetCard activo={activo} rol="admin" />)
    expect(screen.getByText('$ 14.200.000,00')).toBeTruthy()
  })

  it('el contador no ve precio, ni hueco, ni marcador', () => {
    const { container } = render(<AssetCard activo={activo} rol="contador" />)
    expect(container.textContent).not.toContain('$')
    expect(container.textContent).not.toContain('•••')
    expect(container.textContent).not.toMatch(/precio/i)
  })

  it('muestra código, categoría, ubicación y estado', () => {
    const { container } = render(<AssetCard activo={activo} rol="contador" />)
    for (const texto of ['000123', 'Biomédicos', 'Esterilización', 'Activo']) {
      expect(container.textContent).toContain(texto)
    }
  })

  it('un nombre largo baja de línea y la ubicación se corta sin desbordar (R12)', () => {
    render(
      <AssetCard
        activo={{ ...activo, nombre: 'Nombre larguísimo '.repeat(10), ubicacion: 'Sede › Sala › Box '.repeat(6) }}
        rol="contador"
      />,
    )
    expect(screen.getByRole('heading').classList.contains('break-words')).toBe(true)
    expect(screen.getByText(/Sede › Sala › Box/).classList.contains('truncate')).toBe(true)
  })
})

describe('StatCard', () => {
  it('muestra rótulo, cifra y contexto, y enlaza al detalle', () => {
    render(
      <MemoryRouter>
        <StatCard titulo="Activos hoy" valor="219" contexto="Incluye 2 en reparación" href="/admin/activos" />
      </MemoryRouter>,
    )
    const enlace = screen.getByRole('link', { name: /Activos hoy/ })
    expect(enlace.getAttribute('href')).toBe('/admin/activos')
    expect(enlace.textContent).toContain('219')
    expect(enlace.textContent).toContain('Incluye 2 en reparación')
  })
})

describe('PendingList', () => {
  it('lista pendientes por ubicación', () => {
    render(
      <PendingList
        items={[
          { ubicacion: 'Bodega', pendientes: 58, verificados: 0, total: 58 },
          { ubicacion: 'Administración', pendientes: 16, verificados: 13, total: 29 },
        ]}
      />,
    )
    const filas = screen.getAllByRole('listitem')
    expect(filas).toHaveLength(2)
    expect(within(filas[1]).getByText('13 de 29')).toBeTruthy()
    expect(within(filas[1]).getByText('16')).toBeTruthy()
  })
})

describe('EmptyState', () => {
  it('muestra título, ayuda y una acción', () => {
    render(<EmptyState titulo="Aún no hay activos" descripcion="Escanea un sticker." accion={<button>Ir a escanear</button>} />)
    expect(screen.getByText('Aún no hay activos')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Ir a escanear' })).toBeTruthy()
  })
})

describe('LocationPicker', () => {
  it('pone la última usada arriba y se elige con el teclado', async () => {
    const alCambiar = vi.fn()
    render(<LocationPicker id="ubi" valor="administracion" ultimaUsada="c1b2" onChange={alCambiar} />)
    const disparador = screen.getByRole('combobox')
    expect(disparador.textContent).toContain('Administración')
    fireEvent.click(disparador)
    const lista = await screen.findByRole('listbox')
    const opciones = within(lista).getAllByRole('option')
    expect(opciones[0].textContent).toContain('Consultorio 1 › Box 2')
    expect(within(lista).getByText('Última usada')).toBeTruthy()
    const campo = screen.getByRole('combobox', { name: 'Buscar ubicación' })
    fireEvent.change(campo, { target: { value: 'bodega' } })
    fireEvent.keyDown(campo, { key: 'Enter' })
    expect(alCambiar).toHaveBeenCalledWith('bodega')
  })
})
