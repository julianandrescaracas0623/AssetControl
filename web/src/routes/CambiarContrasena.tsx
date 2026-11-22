import { Eye, EyeOff, KeyRound, LogOut } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { CampoContrasena, POLITICA_CONTRASENA } from '@/components/app/CampoContrasena'
import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton, Campo } from '@/components/kit'
import { api, ErrorApi } from '@/lib/api/cliente'
import { textoEspera } from '@/lib/espera'
import { destinoTrasLogin, useApiAutenticada, useCerrarSesion, useSesion } from '@/lib/sesion'

// /cambiar-contrasena (spec 017, T4; R26–R27, R38–R39; CU-10, A16).
// - Mientras la sesión tenga `debe_cambiar_password` es la única pantalla (la guarda de
//   RequiereSesion lleva aquí, recordando adónde iba la persona en `desde`). Sin la marca
//   sirve para un cambio voluntario.
// - Contraseña actual, nueva y confirmación. Los valores se leen del formulario al enviar y
//   no se guardan en estado, caché ni almacenamiento (sin TanStack Query: `useMutation`
//   guardaría `variables`); el formulario se vacía al terminar. Los atributos
//   `autocomplete` (current-password / new-password, con el correo como usuario) dejan que
//   el gestor de contraseñas complete la actual y guarde la nueva: cero digitación de más.
// - El servidor decide (política, distinta de la actual, confirmación); aquí solo se
//   adelanta el aviso de confirmación distinta o nueva igual a la actual.
// - Al guardar, el servidor responde una sesión nueva (las demás quedan cerradas): se toma
//   y se sigue a donde iba.

const RUTA = '/cambiar-contrasena'
const NO_COINCIDEN = 'Las contraseñas no coinciden. Escribe la misma en los dos campos.'
const REPETIDA = 'La contraseña nueva debe ser distinta de la actual.'
const ACTUAL_ERRONEA = 'La contraseña actual no es correcta.'
const ERROR_SERVICIO = 'El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.'
const ERROR_GENERICO = 'No pudimos guardar la contraseña. Intenta de nuevo.'

type ErrorPantalla = { campo: 'actual' | 'nueva' | 'confirmar' | 'general'; mensaje: string }

function errorDe(error: unknown): ErrorPantalla {
  if (!(error instanceof ErrorApi)) return { campo: 'general', mensaje: ERROR_GENERICO }
  if (error.code === 'credenciales_invalidas') return { campo: 'actual', mensaje: ACTUAL_ERRONEA }
  if (error.code === 'contrasenas_distintas') return { campo: 'confirmar', mensaje: NO_COINCIDEN }
  if (error.code === 'contrasena_repetida' || error.code.startsWith('contrasena_')) {
    return { campo: 'nueva', mensaje: error.message }
  }
  if (error.status === 429) {
    const espera = textoEspera(error.reintentarEn)
    return {
      campo: 'general',
      mensaje: `Hiciste varios intentos seguidos. Espera ${espera ?? 'unos minutos'} e intenta de nuevo.`,
    }
  }
  if (error.code === 'sin_conexion') return { campo: 'general', mensaje: error.message }
  if (error.status === 503) return { campo: 'general', mensaje: ERROR_SERVICIO }
  return { campo: 'general', mensaje: ERROR_GENERICO }
}

export default function CambiarContrasena() {
  const { sesion, iniciar } = useSesion()
  const conToken = useApiAutenticada()
  const cerrarSesion = useCerrarSesion()
  const navigate = useNavigate()
  const location = useLocation()
  const desde = (location.state as { desde?: unknown } | null)?.desde
  const obligatorio = sesion?.debe_cambiar_password === true
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<ErrorPantalla | null>(null)
  const [actualVisible, setActualVisible] = useState(false)
  const enCurso = useRef(false)
  const formRef = useRef<HTMLFormElement>(null)
  const actualRef = useRef<HTMLInputElement>(null)
  const nuevaRef = useRef<HTMLInputElement>(null)
  const confirmarRef = useRef<HTMLInputElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)

  // Foco al error: el lector lo anuncia y el teclado sigue desde el campo que falla. Lo
  // escrito queda seleccionado para reescribirlo sin borrarlo a mano.
  useEffect(() => {
    if (!error) return
    const destino = { actual: actualRef, nueva: nuevaRef, confirmar: confirmarRef, general: avisoRef }[error.campo]
    destino.current?.focus()
    if (destino.current instanceof HTMLInputElement) destino.current.select()
  }, [error])

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (enCurso.current) return
    const datos = new FormData(evento.currentTarget)
    const actual = String(datos.get('actual') ?? '')
    const nueva = String(datos.get('nueva') ?? '')
    const confirmacion = String(datos.get('confirmacion') ?? '')
    if (nueva !== confirmacion) {
      setError({ campo: 'confirmar', mensaje: NO_COINCIDEN })
      return
    }
    if (nueva === actual) {
      setError({ campo: 'nueva', mensaje: REPETIDA })
      return
    }
    enCurso.current = true
    setEnviando(true)
    setError(null)
    try {
      const nuevaSesion = await conToken((token) => api.cambiarContrasena(token, { actual, nueva, confirmacion }))
      formRef.current?.reset()
      iniciar(nuevaSesion)
      const destino = destinoTrasLogin(nuevaSesion.rol, desde === RUTA ? undefined : desde)
      navigate(destino, { replace: true })
    } catch (e) {
      enCurso.current = false
      setEnviando(false)
      setError(errorDe(e))
    }
  }

  return (
    <MarcoAcceso
      titulo="Cambia tu contraseña"
      icono={obligatorio ? <KeyRound /> : undefined}
      descripcion={
        obligatorio
          ? 'Antes de seguir, cambia la contraseña que te entregaron por una que solo tú conozcas.'
          : 'Escribe la actual y la nueva. Al guardarla se cierran tus otras sesiones abiertas.'
      }
    >
      <form ref={formRef} className="flex flex-col gap-4" onSubmit={alEnviar}>
        {error?.campo === 'general' && (
          <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={error.mensaje} className="outline-none" />
        )}
        {/* Para el gestor de contraseñas: a qué cuenta pertenece la contraseña nueva. Oculto
            solo a la vista (sr-only, no `hidden`: muchos gestores ignoran display:none). */}
        <input
          type="email"
          name="username"
          autoComplete="username"
          value={sesion?.usuario.email ?? ''}
          readOnly
          tabIndex={-1}
          aria-hidden="true"
          className="sr-only"
        />
        <Campo
          ref={actualRef}
          id="cambiar-actual"
          etiqueta="Contraseña actual"
          name="actual"
          type={actualVisible ? 'text' : 'password'}
          autoComplete="current-password"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={128}
          error={error?.campo === 'actual' ? error.mensaje : undefined}
          autoFocus
          // La actual suele ser la que te entregaron y se copia a mano: verla evita un 401
          // (y gastar intentos) por un carácter mal leído. Mismo control que la nueva.
          sufijo={
            <Boton
              variante="fantasma"
              soloIcono
              icono={actualVisible ? <EyeOff /> : <Eye />}
              aria-label={`${actualVisible ? 'Ocultar' : 'Mostrar'} la contraseña actual`}
              aria-pressed={actualVisible}
              className="text-muted-foreground hover:bg-transparent hover:text-foreground"
              onClick={() => setActualVisible((v) => !v)}
            />
          }
        />
        <CampoContrasena
          ref={nuevaRef}
          id="cambiar-nueva"
          etiqueta="Contraseña nueva"
          name="nueva"
          queMostrar="la contraseña nueva"
          ayuda={POLITICA_CONTRASENA}
          error={error?.campo === 'nueva' ? error.mensaje : undefined}
        />
        <CampoContrasena
          ref={confirmarRef}
          id="cambiar-confirmar"
          etiqueta="Confirma la contraseña nueva"
          name="confirmacion"
          queMostrar="la confirmación"
          error={error?.campo === 'confirmar' ? error.mensaje : undefined}
        />
        <Boton type="submit" anchoCompleto className="mt-2" cargando={enviando} textoCargando="Guardando…">
          Guardar contraseña
        </Boton>
      </form>
      <div className="border-t pt-5 text-center">
        <button
          type="button"
          onClick={cerrarSesion}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-sm px-1 text-etiqueta text-muted-foreground hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <LogOut className="size-4" aria-hidden="true" />
          Cerrar sesión
        </button>
      </div>
    </MarcoAcceso>
  )
}
