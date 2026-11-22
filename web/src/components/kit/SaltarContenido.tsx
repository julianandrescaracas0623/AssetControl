import type { MouseEvent } from 'react'

// Spec 016, T10 (Deuda T4 e; R6): primer elemento con foco de cada shell. Oculto hasta
// recibir el foco con el teclado; lleva el foco al contenido principal sin pasar por el
// menú ni el encabezado. No cambia la URL (el foco se mueve a mano, sin #ancla).

export const ID_CONTENIDO = 'contenido'

export function SaltarContenido() {
  function saltar(evento: MouseEvent<HTMLAnchorElement>) {
    evento.preventDefault()
    document.getElementById(ID_CONTENIDO)?.focus()
  }
  return (
    <a
      href={`#${ID_CONTENIDO}`}
      data-kit="saltar-contenido"
      onClick={saltar}
      className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:inline-flex focus:h-control focus:items-center focus:rounded-lg focus:bg-card focus:px-4 focus:text-cuerpo focus:font-medium focus:text-foreground focus:shadow-lg focus:outline-2 focus:outline-offset-2 focus:outline-ring"
    >
      Saltar al contenido
    </a>
  )
}
