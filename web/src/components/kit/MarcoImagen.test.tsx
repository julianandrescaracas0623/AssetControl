import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MarcoImagen } from './MarcoImagen'
import { MEDIDAS_IMAGEN } from './medidasImagen'

// Spec 016, D13 (R11, A9): tamaños fijos de imagen. La caja manda: una imagen muy grande
// o muy pequeña ocupa siempre la misma caja, sin deformarse (object-cover en la foto,
// object-contain en el logo) y sin pasar del ancho disponible (sin scroll horizontal).

afterEach(cleanup)

const clases = (el: Element | null) => (el?.getAttribute('class') ?? '').split(/\s+/)

describe('MarcoImagen', () => {
  it('foto de la ficha: 320 × 240 px desde md; en teléfono ancho completo y 200 px de alto; object-cover', () => {
    render(<MarcoImagen variante="foto" src="blob:foto" alt="Silla" />)
    const caja = document.querySelector('[data-kit=marco-imagen]')
    expect(caja?.getAttribute('data-variante')).toBe('foto')
    // h-50 = 200 px y w-full en teléfono; md:h-60 = 240 px y md:w-80 = 320 px.
    expect(clases(caja)).toEqual(expect.arrayContaining(['w-full', 'h-50', 'md:w-80', 'md:h-60', 'max-w-full', 'overflow-hidden']))
    const img = screen.getByRole('img', { name: 'Silla' })
    // Llena la caja y recorta: nunca se estira ni se sale.
    expect(clases(img)).toEqual(expect.arrayContaining(['size-full', 'object-cover']))
    expect(clases(img)).not.toContain('object-contain')
  })

  it('logo de la empresa: caja fija de 160 × 64 px con object-contain y fondo neutro', () => {
    render(<MarcoImagen variante="logo" src="blob:logo" alt="Logo de la clínica" />)
    const caja = document.querySelector('[data-kit=marco-imagen]')
    expect(clases(caja)).toEqual(expect.arrayContaining(['w-40', 'h-16', 'bg-muted', 'overflow-hidden']))
    const img = screen.getByRole('img', { name: 'Logo de la clínica' })
    expect(clases(img)).toEqual(expect.arrayContaining(['size-full', 'object-contain']))
  })

  it('logo en cabecera: 32 px de alto, ancho automático hasta 120 px, object-contain', () => {
    render(<MarcoImagen variante="logoCabecera" src="blob:logo" alt="Logo" />)
    const caja = document.querySelector('[data-kit=marco-imagen]')
    expect(clases(caja)).toEqual(expect.arrayContaining(['h-8', 'max-w-30']))
    const img = screen.getByRole('img', { name: 'Logo' })
    expect(clases(img)).toEqual(expect.arrayContaining(['h-full', 'w-auto', 'max-w-full', 'object-contain']))
  })

  it('las medidas viven en un solo lugar (MEDIDAS_IMAGEN) para reutilizarlas', () => {
    expect(MEDIDAS_IMAGEN.foto.caja).toContain('md:w-80')
    expect(MEDIDAS_IMAGEN.logo.ajuste).toBe('object-contain')
    expect(MEDIDAS_IMAGEN.foto.ajuste).toBe('object-cover')
  })

  it('una imagen enorme o diminuta ocupa la misma caja (las medidas no dependen de la imagen)', () => {
    const { rerender } = render(<MarcoImagen variante="foto" src="blob:enorme" alt="Enorme" />)
    const enorme = screen.getByRole('img', { name: 'Enorme' })
    // Sin width/height propios: la caja decide; tampoco hay estilos en línea.
    expect(enorme.getAttribute('width')).toBeNull()
    expect(enorme.getAttribute('style')).toBeNull()
    const cajaEnorme = document.querySelector('[data-kit=marco-imagen]')?.getAttribute('class')
    rerender(<MarcoImagen variante="foto" src="blob:diminuta" alt="Diminuta" />)
    expect(document.querySelector('[data-kit=marco-imagen]')?.getAttribute('class')).toBe(cajaEnorme)
  })

  it('sin imagen muestra el contenido vacío dentro de la misma caja', () => {
    render(<MarcoImagen variante="foto" alt="Silla" vacio="Sin foto" />)
    expect(screen.queryByRole('img')).toBeNull()
    const vacio = screen.getByText('Sin foto')
    expect(vacio.closest('[data-kit=marco-imagen]')).toBeTruthy()
  })

  it('cargando: esqueleto con nombre para el lector, en la misma caja', () => {
    render(<MarcoImagen variante="foto" alt="Silla" cargando />)
    const estado = screen.getByRole('status', { name: 'Cargando foto' })
    expect(estado.closest('[data-kit=marco-imagen]')).toBeTruthy()
  })

  it('error: lo dice con texto, sin romper la caja', () => {
    render(<MarcoImagen variante="foto" alt="Silla" error />)
    expect(screen.getByText('No se pudo cargar la foto')).toBeTruthy()
  })

  it('ampliable: toda la caja es un botón con nombre, foco visible y objetivo táctil', () => {
    const ampliar = vi.fn()
    render(<MarcoImagen variante="foto" src="blob:foto" alt="" onAmpliar={ampliar} etiquetaAmpliar="Ver la foto de Silla" />)
    const boton = screen.getByRole('button', { name: 'Ver la foto de Silla' })
    expect(boton.getAttribute('data-kit')).toBe('marco-imagen')
    expect(clases(boton)).toEqual(expect.arrayContaining(['h-50', 'md:h-60', 'focus-visible:ring-2']))
    fireEvent.click(boton)
    expect(ampliar).toHaveBeenCalledOnce()
  })
})
