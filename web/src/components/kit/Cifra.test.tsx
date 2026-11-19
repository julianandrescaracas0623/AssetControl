import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Cifra, CifrasCongeladas } from './Cifra'

// Spec 016, T3 (R7 de docs/03-07, R9): la cifra llega del servidor ya como texto y el
// kit solo la presenta. «Informe congelado» y «Valor actual (no es el informe)» nunca
// comparten tarjeta ni rótulo: cada variante pone el suyo y no se puede quitar.

afterEach(cleanup)

describe('Cifra (indicador)', () => {
  it('rótulo, cifra con tabular-nums y contexto; con enlace es un vínculo al detalle', () => {
    render(
      <MemoryRouter>
        <Cifra rotulo="Activos hoy" valor="219" contexto="Incluye 2 en reparación" href="/admin/activos" />
      </MemoryRouter>,
    )
    const enlace = screen.getByRole('link', { name: /Activos hoy/ })
    expect(enlace.getAttribute('href')).toBe('/admin/activos')
    expect(enlace.getAttribute('data-kit')).toBe('cifra')
    expect(enlace.textContent).toContain('Incluye 2 en reparación')
    const cifra = within(enlace).getByText('219')
    expect(cifra.className).toContain('tabular-nums')
    expect(cifra.className).toContain('text-cifra')
  })

  it('tono aviso pinta la cifra en el color de aviso y acepta insignia e hijos', () => {
    render(
      <Cifra rotulo="Discrepancias" valor="3" tono="aviso" insignia={<span>nueva</span>}>
        <progress aria-label="Avance" />
      </Cifra>,
    )
    expect(screen.getByText('3').className).toContain('text-warning')
    expect(screen.getByText('nueva')).toBeTruthy()
    expect(screen.getByRole('progressbar', { name: 'Avance' })).toBeTruthy()
  })

  it('como región: el rótulo es su encabezado', () => {
    render(<Cifra rotulo="Valor por categoría" valor="$ 1,00" region />)
    expect(screen.getByRole('region', { name: 'Valor por categoría' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Valor por categoría' })).toBeTruthy()
  })

  it('cargando: anuncia la carga sin mostrar una cifra falsa', () => {
    render(<Cifra rotulo="Activos hoy" valor="219" estado="cargando" />)
    const estado = screen.getByRole('status', { name: 'Cargando activos hoy' })
    expect(estado.getAttribute('aria-busy')).toBe('true')
    expect(screen.queryByText('219')).toBeNull()
  })

  it('error: dice que no se pudo cargar y «Reintentar» llama al callback', () => {
    const reintentar = vi.fn()
    render(<Cifra rotulo="Activos hoy" valor="219" estado="error" onReintentar={reintentar} />)
    expect(screen.queryByText('219')).toBeNull()
    expect(screen.getByText('No se pudo cargar')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(reintentar).toHaveBeenCalledOnce()
  })
})

describe('Cifra en vivo', () => {
  it('siempre rotula «Tiempo real» y «No es el informe», nunca «Informe congelado»', () => {
    render(<Cifra fuente="en_vivo" rotulo="Valor actual" valor="$ 286.450.300,00" contexto="COP · 219 activos · 10:42" region />)
    const tarjeta = screen.getByRole('region', { name: /Valor actual/ })
    expect(tarjeta.getAttribute('data-fuente')).toBe('en_vivo')
    expect(tarjeta.textContent).toContain('Tiempo real')
    expect(tarjeta.textContent).toContain('No es el informe')
    expect(tarjeta.textContent).toContain('COP · 219 activos · 10:42')
    expect(tarjeta.textContent).not.toContain('Informe congelado')
  })
})

describe('CifrasCongeladas', () => {
  const cifras = [
    { rotulo: 'Encontrado', valor: '$ 262.118.400,00', detalle: '198 unidades', tono: 'exito' as const },
    { rotulo: 'No encontrado', valor: '$ 14.731.900,00', detalle: '9 unidades', tono: 'error' as const },
    { rotulo: 'Total registrado', valor: '$ 276.850.300,00', detalle: '207 unidades' },
  ]

  it('rotula «Informe congelado» en la insignia y en el nombre de la región', () => {
    render(<CifrasCongeladas titulo="Último informe cerrado" meta="Conteo may 2026 · corte 15/05/2026" cifras={cifras} />)
    const region = screen.getByRole('region', { name: /Informe congelado/ })
    expect(region.getAttribute('data-fuente')).toBe('congelada')
    expect(within(region).getByRole('heading', { name: /Último informe cerrado/ })).toBeTruthy()
    expect(region.textContent).toContain('corte 15/05/2026')
    expect(region.textContent).not.toContain('Valor actual')
    expect(region.textContent).not.toContain('Tiempo real')
  })

  it('cada cifra con su rótulo, ícono decorativo y unidades; las cifras no se suman aquí', () => {
    render(<CifrasCongeladas titulo="Informe" cifras={cifras} accion={<button>Ver informe</button>} />)
    for (const c of cifras) {
      expect(screen.getByText(c.valor).className).toContain('tabular-nums')
      expect(screen.getByText(c.detalle)).toBeTruthy()
    }
    expect(screen.getByText('Encontrado').querySelector('svg[aria-hidden=true]')).toBeTruthy()
    expect(screen.getByText('No encontrado').querySelector('svg[aria-hidden=true]')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Ver informe' })).toBeTruthy()
  })
})
