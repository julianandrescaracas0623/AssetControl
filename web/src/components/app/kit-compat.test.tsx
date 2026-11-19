import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { EstadoActivoBadge } from './EstadoActivoBadge'
import { LiveValueCard, ThreeFiguresCard } from './FigureCards'

// Spec 016, T2: los componentes de app conservan su API y delegan en el kit.
// Spec 016, T10: EmptyState, ConEstado (con ErrorCarga y EncabezadoPagina), CampoFormulario
// y StatCard se retiraron al quedar sin pantallas (kit.node.test.ts impide que vuelvan).
// Lo que probaban aquí lo prueban los componentes del kit en los que delegaban:
// Estado.test (vacío con acción; cargando con role=status y aria-busy; error con alerta),
// EncabezadoPagina.test (h1, insignia, acciones y claseAcciones), Campo.test (MarcoCampo:
// ids `${id}-error` y `${id}-ayuda`, marca de obligatorio oculta al lector) y Cifra.test
// (indicador con enlace al detalle y data-fuente).

afterEach(cleanup)

describe('EstadoActivoBadge delega en Insignia', () => {
  it.each([
    ['activo', 'Activo', 'exito'],
    ['en_reparacion', 'En reparación', 'aviso'],
    ['dado_de_baja', 'Dado de baja', 'neutro'],
  ] as const)('%s → «%s» (tono %s)', (estado, texto, tono) => {
    render(<EstadoActivoBadge estado={estado} />)
    const insignia = screen.getByText(texto, { selector: '[data-slot=badge]' })
    expect(insignia.getAttribute('data-kit')).toBe('insignia')
    expect(insignia.getAttribute('data-tono')).toBe(tono)
    expect(insignia.querySelector('[aria-hidden=true]')).toBeTruthy()
  })
})

// Spec 016, T3: ThreeFiguresCard y LiveValueCard conservan su API y delegan en
// CifrasCongeladas y Cifra del kit.

describe('cifras delegan en Cifra del kit (R7 de docs/03-07)', () => {
  it('ThreeFiguresCard es CifrasCongeladas y LiveValueCard una Cifra en vivo', () => {
    render(
      <>
        <ThreeFiguresCard
          informe={{
            fuente: 'informe_congelado',
            sesion: 'Conteo may 2026',
            corte: '15/05/2026',
            encontrado: { valor: '262118400.00', unidades: 198 },
            noEncontrado: { valor: '14731900.00', unidades: 9 },
            total: { valor: '276850300.00', unidades: 207 },
          }}
        />
        <LiveValueCard valor={{ fuente: 'valor_actual', valor: '286450300.00', activos: 219, consultadoA: '10:42' }} />
      </>,
    )
    expect(screen.getByRole('region', { name: /Informe congelado/ }).getAttribute('data-fuente')).toBe('congelada')
    const vivo = screen.getByRole('region', { name: /Valor actual/ })
    expect(vivo.getAttribute('data-fuente')).toBe('en_vivo')
    expect(vivo.textContent).toContain('No es el informe')
  })
})
