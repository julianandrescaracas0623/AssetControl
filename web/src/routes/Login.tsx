import { useMutation } from '@tanstack/react-query'
import { type FormEvent, type MouseEvent, useRef } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton, Campo } from '@/components/kit'
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
  const correoRef = useRef<HTMLInputElement>(null)

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

  // Spec 014, T6: el correo ya escrito pasa a /recuperar en el estado del router (no
  // en la URL), para no teclearlo dos veces.
  function alOlvidar(evento: MouseEvent<HTMLAnchorElement>) {
    if (evento.defaultPrevented || evento.button !== 0 || evento.metaKey || evento.ctrlKey || evento.shiftKey || evento.altKey) return
    evento.preventDefault()
    const email = correoRef.current?.value.trim() ?? ''
    navigate('/recuperar', { state: email ? { email } : null })
  }

  const enviando = entrar.isPending || entrar.isSuccess
  return (
    <MarcoAcceso titulo="Iniciar sesión" descripcion="Entra con el correo con el que te invitó tu clínica.">
      <form className="flex flex-col gap-4" onSubmit={alEnviar}>
        {entrar.isError && <Aviso tono="error" titulo={mensajeDeError(entrar.error)} />}
        <Campo
          ref={correoRef}
          id="login-email"
          etiqueta="Correo"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          autoFocus
        />
        <Campo
          id="login-password"
          etiqueta="Contraseña"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        <Link
          to="/recuperar"
          onClick={alOlvidar}
          className="-my-2 inline-flex min-h-11 items-center self-end rounded-sm px-1 text-etiqueta font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          ¿Olvidaste tu contraseña?
        </Link>
        <Boton type="submit" anchoCompleto className="mt-2" cargando={enviando} textoCargando="Entrando…">
          Entrar
        </Boton>
      </form>
      <p className="border-t pt-5 text-center text-etiqueta font-normal text-muted-foreground">
        ¿No tienes cuenta? Pide una invitación al administrador de tu clínica.
      </p>
    </MarcoAcceso>
  )
}
