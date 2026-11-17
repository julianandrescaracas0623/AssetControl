import { describe, expect, it } from 'vitest'

import { digitoVerificacion, MENSAJES, normalizarNit, validarEmpresa } from '@/lib/empresa'

// Spec 013, T6 (R1): las mismas reglas que el servidor, para avisar antes de enviar.

const BASE = { nombre: 'Clínica Ejemplo', direccion: 'Calle 10 # 5-20', nit: '', telefono: '', correo: '' }

describe('NIT', () => {
  it('calcula el dígito de verificación de la DIAN', () => {
    expect(digitoVerificacion('890903938')).toBe(8)
    expect(digitoVerificacion('800197268')).toBe(4)
    expect(digitoVerificacion('900123456')).toBe(8)
  })

  it.each([
    ['890903938-8', '890.903.938-8'],
    ['890.903.938-8', '890.903.938-8'],
    ['890 903 938 - 8', '890.903.938-8'],
    ['890903938', '890.903.938'],
    ['1094123456', '1.094.123.456'],
  ])('normaliza %s', (entrada, salida) => {
    expect(normalizarNit(entrada)).toBe(salida)
  })

  it.each(['890903938-7', '12-3', 'ABC', '890903938-88', '1234'])('rechaza %s', (nit) => {
    expect(normalizarNit(nit)).toBeNull()
  })
})

describe('validarEmpresa', () => {
  it('limpia espacios y deja los opcionales vacíos en null', () => {
    expect(validarEmpresa({ ...BASE, direccion: '  Calle  10 #  5-20 ', nit: '890903938-8' })).toEqual({
      errores: {},
      cuerpo: { nombre: 'Clínica Ejemplo', direccion: 'Calle 10 # 5-20', nit: '890.903.938-8', telefono: null, correo: null },
    })
  })

  it('nombra cada campo que no es válido', () => {
    const { errores, cuerpo } = validarEmpresa({
      nombre: ' ',
      direccion: '',
      nit: '890903938-1',
      telefono: '123',
      correo: 'a@b',
    })
    expect(cuerpo).toBeUndefined()
    expect(errores).toEqual(MENSAJES)
  })

  it('acepta teléfono y correo con formato', () => {
    const { cuerpo } = validarEmpresa({ ...BASE, telefono: '(602) 210 0000', correo: 'contacto@clinica.co' })
    expect(cuerpo?.telefono).toBe('(602) 210 0000')
    expect(cuerpo?.correo).toBe('contacto@clinica.co')
  })
})
