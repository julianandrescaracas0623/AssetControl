import { useSyncExternalStore } from 'react'

// Spec 015, T8 (R8, Q7 = B): el conteo usa el diseño de escritorio solo con pantalla
// ancha y puntero fino (mouse o trackpad). Una tableta táctil o un teléfono siguen con
// el diseño de 375 px y la cámara primero. Mismo patrón que use-mobile (sin setState en
// efectos ni desajuste en el primer render).

export const CONSULTA_ESCRITORIO = '(min-width: 1024px) and (pointer: fine)'

function suscribir(onChange: () => void) {
  const mql = window.matchMedia(CONSULTA_ESCRITORIO)
  mql.addEventListener('change', onChange)
  return () => mql.removeEventListener('change', onChange)
}

export function useEsEscritorio(): boolean {
  return useSyncExternalStore(
    suscribir,
    () => window.matchMedia(CONSULTA_ESCRITORIO).matches,
    () => false,
  )
}
