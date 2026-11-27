import { describe, expect, it } from 'vitest'

import { APP_NAV, entradaDeRuta, migasDeRuta, navDeRol, rutaInforme } from '@/components/app/app-nav'
import { desdeAliasAdmin, rutaActivo, rutaApp, rutaSesion } from '@/lib/rutas'

// Spec 020, T3 (R1, R2, R4): menú por rol desde una sola fuente y rutas sin /admin fijo.

const titulos = (rol: 'admin' | 'contador') => navDeRol(rol).flatMap((g) => g.items.map((i) => i.titulo))

describe('APP_NAV por rol', () => {
  it('el contador ve exactamente Inicio, Contar, Activos, Registrar activo, Sesiones y Discrepancias (R4)', () => {
    expect(titulos('contador').sort()).toEqual(['Activos', 'Contar', 'Discrepancias', 'Inicio', 'Registrar activo', 'Sesiones'].sort())
    const contar = navDeRol('contador').flatMap((g) => g.items).find((i) => i.titulo === 'Contar')
    expect(contar?.ruta).toBe('/contar/escanear')
  })

  it('el contador no tiene grupos vacíos ni entradas del admin', () => {
    const grupos = navDeRol('contador').map((g) => g.titulo)
    expect(grupos).toEqual(['General', 'Inventario', 'Conteo'])
    for (const ajena of ['Ubicaciones', 'Categorías', 'Valor actual', 'Usuarios', 'Empresa']) {
      expect(titulos('contador')).not.toContain(ajena)
    }
  })

  it('el admin conserva su menú de siempre, sin «Contar» suelto', () => {
    expect(navDeRol('admin').map((g) => g.titulo)).toEqual(['General', 'Inventario', 'Conteo', 'Finanzas', 'Ajustes'])
    expect(titulos('admin')).toEqual([
      'Inicio', 'Activos', 'Registrar activo', 'Ubicaciones', 'Categorías', 'Sesiones', 'Discrepancias', 'Valor actual', 'Usuarios', 'Empresa',
    ])
  })

  it('cada entrada declara al menos un rol y ninguna ruta del marco usa /admin', () => {
    for (const item of APP_NAV.flatMap((g) => g.items)) {
      expect(item.roles.length, item.titulo).toBeGreaterThan(0)
      expect(item.ruta.startsWith('/admin'), item.titulo).toBe(false)
    }
  })
})

describe('rutas del marco', () => {
  it('rutaApp y sus ayudantes construyen rutas bajo /app', () => {
    expect(rutaApp()).toBe('/app')
    expect(rutaApp('activos')).toBe('/app/activos')
    expect(rutaApp('/valor')).toBe('/app/valor')
    expect(rutaActivo('A/1 b')).toBe('/app/activos/A%2F1%20b')
    expect(rutaSesion('s1')).toBe('/app/sesiones/s1')
    expect(rutaInforme('s1')).toBe('/app/sesiones/s1/informe')
  })

  it('el alias /admin pasa a /app conservando la subruta; lo demás no cambia', () => {
    expect(desdeAliasAdmin('/admin')).toBe('/app')
    expect(desdeAliasAdmin('/admin/activos/000123')).toBe('/app/activos/000123')
    expect(desdeAliasAdmin('/administrar')).toBe('/administrar')
    expect(desdeAliasAdmin('/contar')).toBe('/contar')
  })

  it('las migas y la entrada activa salen de /app', () => {
    expect(entradaDeRuta('/app/activos/000123')?.item.titulo).toBe('Activos')
    expect(entradaDeRuta('/app')?.item.titulo).toBe('Inicio')
    expect(migasDeRuta('/app/sesiones/x/informe')).toEqual([
      { texto: 'Conteo' },
      { texto: 'Sesiones', ruta: '/app/sesiones' },
      { texto: 'Sesión', ruta: '/app/sesiones/x' },
      { texto: 'Informe' },
    ])
  })
})

describe('migas con una URL mal codificada (spec 020, T3)', () => {
  it('no rompe el marco: muestra el segmento tal cual llega', () => {
    expect(() => migasDeRuta('/app/activos/%E0%A4%A')).not.toThrow()
    expect(migasDeRuta('/app/activos/%E0%A4%A')).toEqual([
      { texto: 'Inventario' },
      { texto: 'Activos', ruta: '/app/activos' },
      { texto: '%E0%A4%A' },
    ])
  })

  it('un código bien codificado se sigue mostrando decodificado', () => {
    expect(migasDeRuta('/app/activos/A%2FB').at(-1)).toEqual({ texto: 'A/B' })
  })
})
