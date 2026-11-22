import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { Outlet } from 'react-router'

import { ErrorApi } from '@/lib/api/cliente'

// Raíz de /plataforma/** (spec 017, T8; plan §2.2): fuera de la Raiz de la clínica, con su
// propio cliente de TanStack Query. Así ni la caché ni el token de la consola se mezclan
// con los de la clínica: cada árbol solo ve su cliente. Las páginas de la consola piden no
// indexarse (plan §2.7; React lleva la etiqueta a <head>).

/** Reintenta solo lo que puede mejorar solo: sin red o 5xx, hasta 2 veces (como Raiz). */
function reintentar(fallos: number, error: unknown): boolean {
  if (fallos >= 2) return false
  if (!(error instanceof ErrorApi)) return false
  return error.status === 0 || error.status >= 500
}

function crearClientePlataforma(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: reintentar, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
}

export default function RaizPlataforma() {
  const [cliente] = useState(crearClientePlataforma)
  return (
    <QueryClientProvider client={cliente}>
      <meta name="robots" content="noindex, nofollow" />
      <Outlet />
    </QueryClientProvider>
  )
}
