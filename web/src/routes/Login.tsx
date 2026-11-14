import { useMutation } from '@tanstack/react-query'
import { CircleAlert, LoaderCircle } from 'lucide-react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, mensajeDeError } from '@/lib/api/cliente'
import { destinoTrasLogin, useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'

// /login (spec 002b, T3; R2, R3): solo correo y contraseña. El destino lo decide el
// rol que devuelve el servidor; `desde` llega en el estado del router.

export default function Login() {
  const { estado, sesion, iniciar } = useSesion()
  const location = useLocation()
  const navigate = useNavigate()
  const desde = (location.state as { desde?: unknown } | null)?.desde

  const entrar = useMutation({
    mutationFn: api.login,
    onSuccess: (nueva) => {
      iniciar(nueva)
      navigate(destinoTrasLogin(nueva.rol, desde), { replace: true })
    },
  })

  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (sesion && !entrar.isPending && !entrar.isSuccess) {
    return <Navigate to={destinoTrasLogin(sesion.rol, desde)} replace />
  }

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const datos = new FormData(evento.currentTarget)
    entrar.mutate({ email: String(datos.get('email') ?? ''), password: String(datos.get('password') ?? '') })
  }

  const enviando = entrar.isPending || entrar.isSuccess
  return (
    <MarcoAcceso>
      <CardHeader>
        <CardTitle>
          <h1 className="text-xl font-semibold tracking-tight">Iniciar sesión</h1>
        </CardTitle>
        <CardDescription>Entra con el correo con el que te invitó tu clínica.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={alEnviar}>
          {entrar.isError && (
            <Alert variant="destructive">
              <CircleAlert />
              <AlertDescription>{mensajeDeError(entrar.error)}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor="login-email">Correo</Label>
            <Input
              id="login-email"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              autoFocus
              className="h-11 md:h-9"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="login-password">Contraseña</Label>
            <Input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              className="h-11 md:h-9"
            />
          </div>
          <Button type="submit" className="h-11 w-full md:h-9" disabled={enviando}>
            {enviando && <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            Entrar
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          ¿No tienes cuenta? Pide una invitación al administrador de tu clínica.
        </p>
      </CardContent>
    </MarcoAcceso>
  )
}
