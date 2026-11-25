import { useMutation } from '@tanstack/react-query'
import { type FormEvent, type MouseEvent, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton, Campo } from '@/components/kit'
import { api, mensajeDeError } from '@/lib/api/cliente'
import { AVISO_CONTRASENA_ACTUALIZADA } from '@/lib/avisos'
import { destinoTrasLogin, useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'

// /login (spec 002b, T3; R2, R3): solo correo y contraseña. El destino lo decide el
// rol que devuelve el servidor; `desde` llega en el estado del router.
// Spec 014, T7 (R10): tras restablecer la contraseña llega `aviso` en el estado; se
// muestra una vez (el estado se limpia al leerlo, no reaparece al recargar).

const TEXTO_CONTRASENA_ACTUALIZADA = 'Tu contraseña se actualizó. Inicia sesión con la nueva.'

export default function Login() {
  const { estado, sesion, iniciar } = useSesion()
  const location = useLocation()
  const navigate = useNavigate()
  const desde = (location.state as { desde?: unknown } | null)?.desde
  const correoRef = useRef<HTMLInputElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)
  const [aviso] = useState(
    () => (location.state as { aviso?: unknown } | null)?.aviso === AVISO_CONTRASENA_ACTUALIZADA,
  )
  const avisoEnEstado = (location.state as { aviso?: unknown } | null)?.aviso !== undefined

  useEffect(() => {
    if (!avisoEnEstado) return
    navigate(
      { pathname: location.pathname, search: location.search },
      { replace: true, state: desde === undefined ? null : { desde } },
    )
  }, [avisoEnEstado, desde, location.pathname, location.search, navigate])

  // El aviso recibe el foco: el lector lo anuncia y el teclado sigue al correo.
  useEffect(() => {
    if (aviso) avisoRef.current?.focus()
  }, [aviso, estado])

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
    <MarcoAcceso titulo="Iniciar sesión" descripcion="Entra con el correo con el que te invitó tu empresa.">
      <form className="flex flex-col gap-4" onSubmit={alEnviar}>
        {aviso && entrar.isIdle && (
          <Aviso ref={avisoRef} tabIndex={-1} tono="exito" titulo={TEXTO_CONTRASENA_ACTUALIZADA} className="outline-none" />
        )}
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
          autoFocus={!aviso}
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
          className="-my-2 inline-flex min-h-11 items-center self-center rounded-sm px-1 text-etiqueta font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
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
