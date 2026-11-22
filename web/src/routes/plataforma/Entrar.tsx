import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton, Campo } from '@/components/kit'
import { ErrorApi } from '@/lib/api/cliente'
import { apiPlataforma } from '@/lib/api/plataforma'
import { textoEspera } from '@/lib/espera'

import { PantallaCarga } from '../PantallaCarga'
import { SinConexion } from '../SinConexion'
import { MarcaPlataforma } from './MarcaPlataforma'
import { ConsolaNoDisponible } from './NoDisponible'
import { destinoTrasEntrar, esConsolaApagada, useSesionPlataforma } from './sesion'

// /plataforma/entrar (spec 017, T8; CU-01, R2–R3, R14). Solo correo y contraseña del
// desarrollador. Los valores se leen del formulario al enviar y no se guardan en estado,
// caché ni almacenamiento (sin `useMutation`, que guardaría `variables`); tras un error
// se borra la contraseña y se conserva el correo. Errores siempre genéricos (401: mismo
// texto para correo inexistente, contraseña errónea o cuenta inactiva). Con la consola
// apagada (404), «No disponible» en lugar del formulario.

const CREDENCIALES = 'Correo o contraseña incorrectos.'
const SERVICIO = 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.'
const GENERICO = 'No pudimos iniciar la sesión. Intenta de nuevo.'

function mensajeDe(error: unknown): string {
  if (!(error instanceof ErrorApi)) return GENERICO
  if (error.status === 401) return CREDENCIALES
  if (error.status === 429) return `Demasiados intentos, espera ${textoEspera(error.reintentarEn) ?? 'unos minutos'} e intenta de nuevo.`
  if (error.code === 'sin_conexion') return error.message
  if (error.status === 503) return SERVICIO
  return GENERICO
}

export default function Entrar() {
  const { estado, sesion, iniciar, reintentar } = useSesionPlataforma()
  const location = useLocation()
  const navigate = useNavigate()
  const desde = (location.state as { desde?: unknown } | null)?.desde
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apagada, setApagada] = useState(false)
  const enCurso = useRef(false)
  const claveRef = useRef<HTMLInputElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)

  // El error recibe el foco: el lector lo anuncia y el teclado sigue a la contraseña.
  useEffect(() => {
    if (error) avisoRef.current?.focus()
  }, [error])

  if (apagada || estado === 'no_disponible') {
    return (
      <ConsolaNoDisponible
        onReintentar={() => {
          setApagada(false)
          reintentar()
        }}
      />
    )
  }
  if (estado === 'cargando') return <PantallaCarga etiqueta="Comprobando la sesión" />
  if (estado === 'error') return <SinConexion onReintentar={reintentar} />
  if (sesion && !enviando) return <Navigate to={destinoTrasEntrar(desde)} replace />

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (enCurso.current) return
    const datos = new FormData(evento.currentTarget)
    const email = String(datos.get('email') ?? '')
    const password = String(datos.get('password') ?? '')
    enCurso.current = true
    setEnviando(true)
    setError(null)
    try {
      const nueva = await apiPlataforma.login({ email, password })
      iniciar(nueva)
      navigate(destinoTrasEntrar(desde), { replace: true })
    } catch (e) {
      enCurso.current = false
      setEnviando(false)
      if (claveRef.current) claveRef.current.value = ''
      if (esConsolaApagada(e)) setApagada(true)
      else setError(mensajeDe(e))
    }
  }

  return (
    <MarcoAcceso
      marca={<MarcaPlataforma />}
      titulo="Iniciar sesión"
    >
      {/* method="post": defensa en profundidad; un envío nativo nunca pone la contraseña en la URL (D20). */}
      <form method="post" className="flex flex-col gap-4" onSubmit={alEnviar}>
        {error && <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={error} className="outline-none" />}
        <Campo
          id="plataforma-email"
          etiqueta="Correo"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={254}
          autoFocus
        />
        <Campo
          ref={claveRef}
          id="plataforma-password"
          etiqueta="Contraseña"
          name="password"
          type="password"
          autoComplete="current-password"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={128}
        />
        <Boton type="submit" anchoCompleto className="mt-2" cargando={enviando} textoCargando="Entrando…">
          Entrar
        </Boton>
      </form>
    </MarcoAcceso>
  )
}
