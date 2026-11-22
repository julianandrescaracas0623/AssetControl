import * as React from "react"

const MOBILE_BREAKPOINT = 768
const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

// Ajuste de spec 001b, T2: la versión de la CLI llamaba a setState dentro de
// un efecto (regla react-hooks/set-state-in-effect). useSyncExternalStore lee
// la media query sin renders en cascada y sin desajuste en el primer render.
function subscribe(onChange: () => void) {
  const mql = window.matchMedia(QUERY)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false
  )
}
