import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { AltaActivo } from '@/lib/altaActivo'
import { Resumen } from './FormularioAlta'

// Spec 020, T7: el resumen del alta sin código mostraba el «—» en la fuente monoespaciada
// del código (más corto que los demás guiones de la columna).

afterEach(cleanup)

const alta = (codigo: string) =>
  ({
    campos: { codigo, nombre: '', categoria: '', ubicacion: '', precio: '' },
    copiado: null,
    duplicando: false,
  }) as unknown as AltaActivo

function valorDe(rotulo: string) {
  return screen.getByText(rotulo, { selector: 'dt' }).nextElementSibling as HTMLElement
}

describe('Resumen del alta', () => {
  it('sin código, el guion va en la fuente normal, como los demás', () => {
    render(<Resumen alta={alta('')} rol="contador" categorias={[]} ubicaciones={[]} />)
    const codigo = valorDe('Código')
    expect(codigo.textContent).toBe('—')
    expect(codigo.className).not.toContain('font-mono')
  })

  it('con código, el código va en la fuente monoespaciada', () => {
    render(<Resumen alta={alta('e2e-0009')} rol="contador" categorias={[]} ubicaciones={[]} />)
    const codigo = valorDe('Código')
    expect(codigo.textContent).toBe('E2E-0009')
    expect(codigo.className).toContain('font-mono')
  })

  it('el contador no ve la fila de precio', () => {
    render(<Resumen alta={alta('e2e-0009')} rol="contador" categorias={[]} ubicaciones={[]} />)
    expect(screen.queryByText('Precio')).toBeNull()
  })
})
