import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'

import { Campo, Obligatorio } from './CampoFormulario'
import { ConEstado, EncabezadoPagina, ErrorCarga } from './ConEstado'
import { EmptyState } from './EmptyState'
import { EstadoActivoBadge } from './EstadoActivoBadge'
import { LiveValueCard, ThreeFiguresCard } from './FigureCards'
import { StatCard } from './StatCard'
import { Input } from '@/components/ui/input'

// Spec 016, T2: los componentes de app conservan su API y delegan en el kit.

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

describe('EmptyState delega en Estado.Vacio', () => {
  it('misma API: título, descripción y acción', () => {
    render(<EmptyState titulo="Aún no hay activos" descripcion="Escanea un sticker." accion={<button>Ir a escanear</button>} />)
    expect(document.querySelector('[data-kit=estado-vacio]')?.textContent).toContain('Aún no hay activos')
    expect(screen.getByRole('button', { name: 'Ir a escanear' })).toBeTruthy()
  })
})

describe('ConEstado delega en Estado', () => {
  function renderCon(estado: 'cargando' | 'vacio' | 'error' | 'exito', ruta = '/admin/activos?estado=error&vista=tabla') {
    return render(
      <MemoryRouter initialEntries={[ruta]}>
        <ConEstado estado={estado} etiquetaCargando="Cargando activos" cargando={<p>esqueleto</p>} vacio={<p>sin datos</p>}>
          <p>contenido</p>
        </ConEstado>
      </MemoryRouter>,
    )
  }

  it('cargando: role=status con la etiqueta y el esqueleto propio', () => {
    renderCon('cargando')
    const estado = screen.getByRole('status', { name: 'Cargando activos' })
    expect(estado.getAttribute('aria-busy')).toBe('true')
    expect(estado.getAttribute('data-kit')).toBe('estado-cargando')
    expect(screen.getByText('esqueleto')).toBeTruthy()
  })

  it('vacío y éxito muestran lo que se les pasa', () => {
    renderCon('vacio')
    expect(screen.getByText('sin datos')).toBeTruthy()
    cleanup()
    renderCon('exito')
    expect(screen.getByText('contenido')).toBeTruthy()
  })

  it('error: aviso con «Reintentar» que vuelve a la ruta sin ?estado=', () => {
    renderCon('error')
    const aviso = screen.getByRole('alert')
    expect(aviso.getAttribute('data-kit')).toBe('aviso')
    expect(aviso.textContent).toContain('No se pudo cargar')
    expect(screen.getByRole('link', { name: 'Reintentar' }).getAttribute('href')).toBe('/admin/activos?vista=tabla')
  })

  it('ErrorCarga admite otro título', () => {
    render(
      <MemoryRouter>
        <ErrorCarga titulo="No se pudo cargar el informe" />
      </MemoryRouter>,
    )
    expect(screen.getByRole('alert').textContent).toContain('No se pudo cargar el informe')
  })
})

describe('Campo (CampoFormulario) delega en MarcoCampo', () => {
  it('misma API e ids: etiqueta, error en ${id}-error y ayuda en ${id}-ayuda', () => {
    render(
      <>
        <Campo id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error="Escribe el nombre">
          <Input id="nombre" aria-describedby="nombre-error" />
        </Campo>
        <Campo id="serial" etiqueta="Serial" ayuda="No tiene que ser único.">
          <Input id="serial" aria-describedby="serial-ayuda" />
        </Campo>
      </>,
    )
    expect(screen.getByRole('textbox', { name: /Nombre/ }).getAttribute('aria-describedby')).toBe('nombre-error')
    expect(document.getElementById('nombre-error')?.textContent).toBe('Escribe el nombre')
    expect(document.getElementById('serial-ayuda')?.textContent).toBe('No tiene que ser único.')
    expect(document.querySelectorAll('[data-kit=campo]')).toHaveLength(2)
    expect(document.querySelector('[data-obligatorio]')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('los controles de shadcn que recibe quedan sobre blanco (Deuda T1 d)', () => {
    render(
      <Campo id="x" etiqueta="X">
        <Input id="x" />
      </Campo>,
    )
    expect(document.querySelector('[data-kit=campo]')?.getAttribute('data-controles-sobre-blanco')).toBe('true')
  })
})

// Spec 016, T3: StatCard, ThreeFiguresCard, LiveValueCard y EncabezadoPagina conservan su
// API y delegan en Cifra, CifrasCongeladas y EncabezadoPagina del kit.

describe('cifras delegan en Cifra del kit (R7 de docs/03-07)', () => {
  it('StatCard es una Cifra indicador', () => {
    render(
      <MemoryRouter>
        <StatCard titulo="Activos hoy" valor="219" contexto="Incluye 2 en reparación" href="/admin/activos" />
      </MemoryRouter>,
    )
    const enlace = screen.getByRole('link', { name: /Activos hoy/ })
    expect(enlace.getAttribute('data-kit')).toBe('cifra')
    expect(enlace.getAttribute('data-fuente')).toBe('indicador')
  })

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

describe('EncabezadoPagina (ConEstado) delega en el kit', () => {
  it('misma API: título, descripción, insignia y acciones', () => {
    render(<EncabezadoPagina titulo="Activos" descripcion="219 activos" insignia={<span>nueva</span>} acciones={<button>Exportar</button>} claseAcciones="extra" />)
    const h1 = screen.getByRole('heading', { level: 1, name: 'Activos' })
    expect(h1.closest('[data-kit=encabezado-pagina]')).toBeTruthy()
    expect(screen.getByText('nueva')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Exportar' }).parentElement?.className).toContain('extra')
  })
})
