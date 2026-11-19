import { useMutation } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton, Campo } from '@/components/kit'
import { api, ErrorApi } from '@/lib/api/cliente'

// /recuperar (spec 014, T6; R1, R12, R17; A16). Pide solo el correo. Todo 202 muestra
// el mismo texto, sin repetir el correo ni usar el del servidor: la pantalla no dice si
// la cuenta existe (con el correo desactivado el servidor también responde 202). El
// correo puede llegar del login en el estado del router (cero digitación).

const MENSAJE_ENVIADO = 'Si existe una cuenta con ese correo, te enviamos un enlace que vale 30 minutos.'
const ERROR_CORREO = 'Revisa el correo: escribe la dirección completa, por ejemplo nombre@clinica.com.'
const ERROR_SERVICIO = 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.'
const ERROR_GENERICO = 'No pudimos enviar la solicitud. Intenta de nuevo.'

/** «15 minutos», «1 minuto», «45 segundos»; `null` si no hay un número útil. */
function textoEspera(segundos: number | undefined): string | null {
  if (segundos === undefined || !Number.isFinite(segundos) || segundos <= 0) return null
  if (segundos < 60) return segundos === 1 ? '1 segundo' : `${segundos} segundos`
  const minutos = Math.ceil(segundos / 60)
  return minutos === 1 ? '1 minuto' : `${minutos} minutos`
}

function mensajeGeneral(error: unknown): string {
  if (!(error instanceof ErrorApi)) return ERROR_GENERICO
  if (error.status === 429) {
    const espera = textoEspera(error.reintentarEn)
    return `Hiciste varias solicitudes seguidas. Espera ${espera ?? 'unos minutos'} e intenta de nuevo.`
  }
  if (error.code === 'sin_conexion') return error.message
  if (error.status === 503) return ERROR_SERVICIO
  return ERROR_GENERICO
}

/** 400 (cuerpo no válido) y 413 (demasiado largo) solo pueden venir del correo. */
function esErrorDeCorreo(error: unknown): boolean {
  return error instanceof ErrorApi && (error.status === 400 || error.status === 413)
}

function correoInicial(estado: unknown): string {
  const email = (estado as { email?: unknown } | null)?.email
  return typeof email === 'string' ? email : ''
}

export default function RecuperarContrasena() {
  const location = useLocation()
  const [correo, setCorreo] = useState(() => correoInicial(location.state))
  const enviando = useRef(false)
  const campoRef = useRef<HTMLInputElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)
  const exitoRef = useRef<HTMLDivElement>(null)

  const solicitar = useMutation({
    mutationFn: api.solicitarRecuperacion,
    onSettled: () => {
      enviando.current = false
    },
  })

  const errorCorreo = solicitar.isError && esErrorDeCorreo(solicitar.error) ? ERROR_CORREO : null
  const errorGeneral = solicitar.isError && !errorCorreo ? mensajeGeneral(solicitar.error) : null

  // Foco al resultado: el lector lo lee y quien usa teclado sigue desde ahí.
  useEffect(() => {
    if (solicitar.isSuccess) exitoRef.current?.focus()
    else if (errorCorreo) campoRef.current?.focus()
    else if (errorGeneral) avisoRef.current?.focus()
  }, [solicitar.isSuccess, solicitar.error, errorCorreo, errorGeneral])

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (enviando.current) return
    enviando.current = true
    solicitar.mutate({ email: correo.trim() })
  }

  if (solicitar.isSuccess) {
    return (
      <MarcoAcceso titulo="Revisa tu correo">
        <Aviso ref={exitoRef} tabIndex={-1} tono="exito" titulo={MENSAJE_ENVIADO} className="outline-none">
          Si no lo ves en unos minutos, busca en la carpeta de correo no deseado.
        </Aviso>
        <div className="flex flex-col gap-3">
          <Boton asChild anchoCompleto>
            <Link to="/login">Volver a iniciar sesión</Link>
          </Boton>
          <Boton variante="secundario" anchoCompleto onClick={() => solicitar.reset()}>
            Pedir otro enlace
          </Boton>
        </div>
      </MarcoAcceso>
    )
  }

  return (
    <MarcoAcceso
      titulo="Recuperar contraseña"
      descripcion="Escribe el correo con el que entras. Si tiene una cuenta, te enviaremos un enlace para crear una contraseña nueva."
    >
      <form className="flex flex-col gap-4" onSubmit={alEnviar}>
        {errorGeneral && (
          <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={errorGeneral} className="outline-none" />
        )}
        <Campo
          ref={campoRef}
          id="recuperar-email"
          etiqueta="Correo"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          autoFocus
          value={correo}
          onChange={(e) => setCorreo(e.target.value)}
          error={errorCorreo ?? undefined}
        />
        <Boton type="submit" anchoCompleto className="mt-2" cargando={solicitar.isPending} textoCargando="Enviando…">
          Enviar enlace
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
