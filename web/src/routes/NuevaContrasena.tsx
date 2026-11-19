import { ArrowLeft, Link2Off } from 'lucide-react'
import { type FormEvent, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { CampoContrasena, POLITICA_CONTRASENA } from '@/components/app/CampoContrasena'
import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton } from '@/components/kit'
import { api, ErrorApi } from '@/lib/api/cliente'
import { AVISO_CONTRASENA_ACTUALIZADA } from '@/lib/avisos'
import { textoEspera } from '@/lib/espera'
import { useOlvidarSesionLocal } from '@/lib/sesion'

// /restablecer#<token> (spec 014, T7; R5, R9, R10, R11, R17; A16).
// - El token se lee UNA vez de `window.location.hash` en el primer render, queda solo en
//   memoria de este componente (nunca en almacenamiento, historial ni query) y la URL se
//   reemplaza enseguida sin él; también se limpia la ubicación del router.
// - Sin endpoint de validación (plan §10): la validez se conoce al enviar.
// - Sin TanStack Query a propósito: `useMutation` guardaría token y contraseña en
//   `variables` de la caché de mutaciones; aquí viven solo en esta llamada.
// - 204 no inicia sesión (R10): lleva a /login con el aviso en el estado del router. Si
//   esta pestaña tenía una sesión en memoria, se olvida solo en el cliente (el servidor
//   ya revocó todas): así /login no redirige a la app y el aviso no se pierde.

const RUTA = '/restablecer'
const ENLACE_INVALIDO = 'Este enlace no es válido o ya venció. Pide uno nuevo.'
const NO_COINCIDEN = 'Las contraseñas no coinciden. Escribe la misma en los dos campos.'
const ERROR_SERVICIO = 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.'
const ERROR_GENERICO = 'No pudimos guardar la contraseña. Intenta de nuevo.'

/** El token del fragmento de la barra (`#<token>`), o '' si no hay. */
function leerFragmento(): string {
  return window.location.hash.slice(1)
}

/**
 * Referrer-Policy: no-referrer mientras esta pantalla está abierta (meta, porque la web
 * estática aún no tiene cabeceras propias; ver la spec de despliegue). Al salir nunca se
 * rebaja: si había un meta se restaura su valor; si no, queda no-referrer (quitar el
 * meta no devuelve la política por defecto y fijar otra sería más permisiva).
 */
function useSinReferente() {
  useLayoutEffect(() => {
    let meta = document.head.querySelector<HTMLMetaElement>('meta[name="referrer"]')
    const previo = meta?.getAttribute('content') ?? null
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'referrer'
      document.head.appendChild(meta)
    }
    meta.content = 'no-referrer'
    const propio = meta
    return () => {
      if (previo !== null) propio.content = previo
    }
  }, [])
}

type ErrorPantalla =
  | { campo: 'password'; mensaje: string }
  | { campo: 'confirmar'; mensaje: string }
  | { campo: 'general'; mensaje: string }

function mensajeGeneral(error: unknown): string {
  if (!(error instanceof ErrorApi)) return ERROR_GENERICO
  if (error.status === 429) {
    const espera = textoEspera(error.reintentarEn)
    return `Hiciste varios intentos seguidos. Espera ${espera ?? 'unos minutos'} e intenta de nuevo.`
  }
  if (error.code === 'sin_conexion') return error.message
  if (error.status === 503) return ERROR_SERVICIO
  return ERROR_GENERICO
}

function EnlaceNoValido() {
  const avisoRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    avisoRef.current?.focus()
  }, [])
  return (
    <MarcoAcceso titulo="Enlace vencido o ya usado" icono={<Link2Off />} tonoIcono="aviso">
      <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={ENLACE_INVALIDO} className="outline-none">
        El enlace vale 30 minutos y sirve una sola vez. Si pediste varios, solo funciona el último.
      </Aviso>
      <Boton asChild anchoCompleto>
        <Link to="/recuperar">Pedir un enlace nuevo</Link>
      </Boton>
      <div className="border-t pt-5 text-center">
        <Link
          to="/login"
          className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-1 text-etiqueta text-muted-foreground hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Volver a iniciar sesión
        </Link>
      </div>
    </MarcoAcceso>
  )
}

export default function NuevaContrasena() {
  const navigate = useNavigate()
  const location = useLocation()
  const olvidarSesionLocal = useOlvidarSesionLocal()
  const [token, setToken] = useState(leerFragmento)
  const [guardada, setGuardada] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<ErrorPantalla | null>(null)
  const enCurso = useRef(false)
  const formRef = useRef<HTMLFormElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)
  const confirmarRef = useRef<HTMLInputElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)

  useSinReferente()

  // Antes de pintar: fuera de la barra y del historial (mismo registro, sin fragmento)
  // y fuera de la ubicación en memoria del router.
  useLayoutEffect(() => {
    if (window.location.hash || window.location.search) {
      window.history.replaceState(window.history.state, '', RUTA)
    }
  }, [])
  const routerConFragmento = location.hash !== '' || location.search !== ''
  useLayoutEffect(() => {
    if (routerConFragmento) navigate(RUTA, { replace: true })
  }, [routerConFragmento, navigate])

  // Foco al resultado: el lector lo anuncia y el teclado sigue desde ahí.
  useEffect(() => {
    if (!error) return
    if (error.campo === 'password') passwordRef.current?.focus()
    else if (error.campo === 'confirmar') confirmarRef.current?.focus()
    else avisoRef.current?.focus()
  }, [error])

  /** Al terminar (éxito o enlace rechazado) no queda nada canjeable en memoria. */
  function olvidar() {
    formRef.current?.reset()
    setToken('')
  }

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (enCurso.current || !token) return
    const datos = new FormData(evento.currentTarget)
    const password = String(datos.get('password') ?? '')
    const confirmar = String(datos.get('confirmar') ?? '')
    if (password !== confirmar) {
      setError({ campo: 'confirmar', mensaje: NO_COINCIDEN })
      return
    }
    enCurso.current = true
    setEnviando(true)
    setError(null)
    try {
      await api.restablecerContrasena({ token, password })
      setGuardada(true)
      olvidar()
      olvidarSesionLocal()
      navigate('/login', { replace: true, state: { aviso: AVISO_CONTRASENA_ACTUALIZADA } })
    } catch (e) {
      enCurso.current = false
      setEnviando(false)
      if (e instanceof ErrorApi && e.code === 'enlace_invalido') {
        olvidar()
      } else if (e instanceof ErrorApi && e.code.startsWith('contrasena_')) {
        setError({ campo: 'password', mensaje: e.message })
      } else {
        setError({ campo: 'general', mensaje: mensajeGeneral(e) })
      }
    }
  }

  // Tras el 204 el token ya se olvidó: el formulario queda «Guardando…» hasta salir.
  if (!token && !guardada) return <EnlaceNoValido />

  return (
    <MarcoAcceso
      titulo="Crea una contraseña nueva"
      descripcion="Escríbela dos veces. Al guardarla se cierran tus sesiones abiertas y entras de nuevo con ella."
    >
      <form ref={formRef} className="flex flex-col gap-4" onSubmit={alEnviar}>
        {error?.campo === 'general' && (
          <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={error.mensaje} className="outline-none" />
        )}
        <CampoContrasena
          ref={passwordRef}
          id="restablecer-password"
          etiqueta="Nueva contraseña"
          name="password"
          queMostrar="la nueva contraseña"
          ayuda={POLITICA_CONTRASENA}
          error={error?.campo === 'password' ? error.mensaje : undefined}
          autoFocus
        />
        <CampoContrasena
          ref={confirmarRef}
          id="restablecer-confirmar"
          etiqueta="Confirma la contraseña"
          name="confirmar"
          queMostrar="la confirmación"
          error={error?.campo === 'confirmar' ? error.mensaje : undefined}
        />
        <Boton type="submit" anchoCompleto className="mt-2" cargando={enviando || guardada} textoCargando="Guardando…">
          Guardar contraseña
        </Boton>
      </form>
      <div className="border-t pt-5 text-center">
        <Link
          to="/login"
          className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-1 text-etiqueta text-muted-foreground hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Volver a iniciar sesión
        </Link>
      </div>
    </MarcoAcceso>
  )
}
