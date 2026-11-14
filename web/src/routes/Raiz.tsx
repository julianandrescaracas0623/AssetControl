import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { Outlet } from 'react-router'

import { ErrorApi } from '@/lib/api/cliente'

// Raíz de todas las rutas (spec 002b, T3): un cliente de TanStack Query por montaje
// (las pruebas que montan `routes` usan el mismo código que el navegador).

/** Reintenta solo lo que puede mejorar solo: sin red o 5xx, hasta 2 veces. */
function reintentar(fallos: number, error: unknown): boolean {
  if (fallos >= 2) return false
  if (!(error instanceof ErrorApi)) return false
  return error.status === 0 || error.status >= 500
}

function crearClienteDeConsultas(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: reintentar, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  })
}

export default function Raiz() {
  const [cliente] = useState(crearClienteDeConsultas)
  return (
    <QueryClientProvider client={cliente}>
      <Outlet />
    </QueryClientProvider>
  )
}
