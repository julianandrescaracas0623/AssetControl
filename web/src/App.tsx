import { useCallback, useEffect, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { fetchHealth, type HealthResult } from '@/lib/health'

// Pantalla base de la fundación (spec 001, T8): solo muestra el estado de la
// API. No es el diseño final; el app shell llega en su propia spec.

type HealthState = { kind: 'loading' } | HealthResult

function useHealth() {
  const [state, setState] = useState<HealthState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(setState)
      .catch(() => {
        // Petición abortada al desmontar o reintentar: no hay nada que mostrar.
      })
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState({ kind: 'loading' })
    setAttempt((value) => value + 1)
  }, [])

  return { state, retry }
}

function StatusBadge({ state }: { state: HealthState }) {
  switch (state.kind) {
    case 'loading':
      return <Badge variant="secondary">Consultando…</Badge>
    case 'ok':
      return <Badge>En línea</Badge>
    case 'degraded':
      return <Badge variant="destructive">Base de datos sin respuesta</Badge>
    case 'unreachable':
      return <Badge variant="destructive">Sin conexión</Badge>
  }
}

function StatusMessage({ state }: { state: HealthState }) {
  switch (state.kind) {
    case 'loading':
      return <p>Consultando el estado del servidor…</p>
    case 'ok':
      return <p>El servidor y la base de datos responden con normalidad.</p>
    case 'degraded':
      return (
        <p>
          El servidor responde, pero la base de datos no. Intenta de nuevo en
          unos minutos.
        </p>
      )
    case 'unreachable':
      return (
        <p>
          No pudimos comunicarnos con el servidor. Revisa tu conexión e intenta
          de nuevo.
        </p>
      )
  }
}

export default function App() {
  const { state, retry } = useHealth()
  const version = state.kind === 'ok' || state.kind === 'degraded' ? state.payload.version : null

  return (
    <main className="flex min-h-svh items-center justify-center bg-muted/40 p-4 sm:p-8">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-lg">AssetControl</CardTitle>
          <CardDescription>Estado del servidor</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3" aria-live="polite" aria-busy={state.kind === 'loading'}>
          <StatusBadge state={state} />
          <StatusMessage state={state} />
          {version !== null && <p className="text-muted-foreground">Versión de la API: {version}</p>}
        </CardContent>
        {state.kind !== 'ok' && (
          <CardFooter>
            <Button
              className="h-11 w-full"
              onClick={retry}
              disabled={state.kind === 'loading'}
            >
              Reintentar
            </Button>
          </CardFooter>
        )}
      </Card>
    </main>
  )
}
