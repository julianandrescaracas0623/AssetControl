import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import Componentes from './Componentes'

// Spec 001b, T2: galería del sistema (equivale a la página "Sistema visual"
// del lienzo aprobado).

afterEach(cleanup)

describe('galería de componentes', () => {
  it('muestra cada sección del sistema', () => {
    render(<Componentes />)
    for (const name of ['Paleta', 'Tipografía', 'Densidad', 'Botones', 'Campos', 'Insignias', 'Avisos', 'Datos', 'Superficies']) {
      expect(screen.getByRole('heading', { name })).toBeTruthy()
    }
  })

  it('todo botón tiene nombre accesible', () => {
    render(<Componentes />)
    // Sin jest-dom: un botón sin nombre no aparece al filtrar por nombre.
    const all = screen.getAllByRole('button')
    expect(screen.getAllByRole('button', { name: /\S/ })).toHaveLength(all.length)
  })

  it('todo campo tiene etiqueta', () => {
    render(<Componentes />)
    const all = screen.getAllByRole('textbox')
    expect(all.length).toBeGreaterThan(0)
    expect(screen.getAllByRole('textbox', { name: /\S/ })).toHaveLength(all.length)
  })

  // Spec 016, T1 (A7): paleta, escala tipográfica y las dos densidades.
  it('muestra cada token de color por nombre, sin valores literales', () => {
    render(<Componentes />)
    const paleta = screen.getByRole('region', { name: 'Paleta' })
    for (const token of ['--page', '--card', '--ink', '--primary', '--primary-hover', '--brand-soft', '--success', '--warning', '--destructive', '--border', '--input', '--ring']) {
      expect(within(paleta).getByText(token)).toBeTruthy()
    }
  })

  it('muestra la escala tipográfica nombrada', () => {
    render(<Componentes />)
    const escala = screen.getByRole('region', { name: 'Tipografía' })
    for (const nombre of ['titulo-pagina', 'titulo-seccion', 'cuerpo', 'etiqueta', 'cifra', 'codigo']) {
      expect(within(escala).getByText(`text-${nombre}`)).toBeTruthy()
    }
  })

  it('muestra las densidades de conteo y de administración', () => {
    render(<Componentes />)
    const densidad = screen.getByRole('region', { name: 'Densidad' })
    const modos = Array.from(densidad.querySelectorAll('[data-densidad]')).map((el) => el.getAttribute('data-densidad'))
    expect(modos).toEqual(['conteo', 'admin'])
  })

  // Spec 016, T2 (A7): los primitivos del kit en sus variantes y estados.
  it('muestra los primitivos del kit con sus variantes y estados', () => {
    render(<Componentes />)
    const botones = screen.getByRole('region', { name: 'Botones' })
    const variantes = Array.from(botones.querySelectorAll('[data-kit=boton]')).map((b) => b.getAttribute('data-variante'))
    for (const v of ['principal', 'secundario', 'fuerte', 'fantasma', 'peligro']) expect(variantes, v).toContain(v)
    expect(within(botones).getByRole('button', { name: 'Guardando…' }).getAttribute('aria-busy')).toBe('true')

    const campos = screen.getByRole('region', { name: 'Campos' })
    expect(campos.querySelectorAll('[data-kit=campo]').length).toBeGreaterThanOrEqual(8)
    expect(within(campos).getByRole('combobox', { name: /Categoría/ })).toBeTruthy()

    const insignias = screen.getByRole('region', { name: 'Insignias' })
    const tonos = new Set(Array.from(insignias.querySelectorAll('[data-kit=insignia]')).map((i) => i.getAttribute('data-tono')))
    for (const t of ['exito', 'aviso', 'error', 'info', 'neutro', 'fuerte']) expect(tonos.has(t), t).toBe(true)

    const avisos = screen.getByRole('region', { name: 'Avisos' })
    expect(avisos.querySelectorAll('[data-kit=aviso]')).toHaveLength(4)

    const estados = screen.getByRole('region', { name: 'Estados' })
    expect(within(estados).getByRole('status', { name: 'Cargando activos' })).toBeTruthy()
    expect(within(estados).getByText('Aún no hay activos')).toBeTruthy()
    expect(within(estados).getByRole('button', { name: 'Reintentar' })).toBeTruthy()
  })

  // Spec 016, T3 (A7): el resto del kit, con datos ficticios.
  it('muestra los primitivos B del kit', () => {
    render(<Componentes />)
    const superficies = screen.getByRole('region', { name: 'Superficies' })
    expect(superficies.querySelectorAll('[data-kit=panel]').length).toBeGreaterThanOrEqual(2)
    expect(within(superficies).getByRole('button', { name: 'Más datos', expanded: false })).toBeTruthy()
    expect(superficies.querySelector('[data-kit=encabezado-pagina]')).toBeTruthy()
    expect(superficies.querySelectorAll('dl[data-kit=lista-datos]').length).toBeGreaterThanOrEqual(2)

    const cifras = screen.getByRole('region', { name: 'Cifras' })
    const fuentes = new Set(Array.from(cifras.querySelectorAll('[data-kit=cifra]')).map((c) => c.getAttribute('data-fuente')))
    for (const f of ['indicador', 'en_vivo', 'congelada']) expect(fuentes.has(f), f).toBe(true)
    expect(within(cifras).getByRole('status', { name: /Cargando/ })).toBeTruthy()

    const dialogos = screen.getByRole('region', { name: 'Diálogos' })
    for (const nombre of ['Editar ubicación', 'Editar activo', 'Dar de baja']) {
      expect(within(dialogos).getByRole('button', { name: nombre })).toBeTruthy()
    }
    expect(dialogos.querySelector('[data-kit=barra-accion]')).toBeTruthy()

    const tablas = screen.getByRole('region', { name: 'Tablas' })
    expect(within(tablas).getByRole('tablist', { name: 'Vista de la tabla' })).toBeTruthy()
    expect(within(tablas).getByRole('table', { name: 'Activos de ejemplo' })).toBeTruthy()
    expect(within(tablas).getByRole('searchbox', { name: 'Buscar activos' })).toBeTruthy()
    expect(within(tablas).getByRole('button', { name: /Categoría/ }).getAttribute('data-kit')).toBe('filtro')
    expect(within(tablas).getByRole('navigation', { name: /Paginación/ })).toBeTruthy()
  })
})
