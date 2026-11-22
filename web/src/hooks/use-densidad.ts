import { useLayoutEffect } from 'react'

// Spec 016, T1 (D6): densidad por modo. El shell la marca en su raíz y también en
// <html>, para que los diálogos, menús y sheets (que Radix monta en un portal fuera
// del shell) tomen las mismas alturas de control. Al desmontar se restaura la anterior.

export type Densidad = 'conteo' | 'admin'

export function useDensidad(densidad: Densidad): void {
  useLayoutEffect(() => {
    const html = document.documentElement
    const anterior = html.getAttribute('data-densidad')
    html.setAttribute('data-densidad', densidad)
    return () => {
      if (anterior === null) html.removeAttribute('data-densidad')
      else html.setAttribute('data-densidad', anterior)
    }
  }, [densidad])
}
