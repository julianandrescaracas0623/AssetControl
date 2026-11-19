import { useMutation, useQuery } from '@tanstack/react-query'
import { Eye, EyeOff, RefreshCw } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Aviso, Boton, Campo } from '@/components/kit'
import { api, ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { inicioDeRol, useSesion } from '@/lib/sesion'
import { PantallaCarga } from './PantallaCarga'

// /invitacion#<token> (spec 002b, T4; R2, R3, R4; Q13). El token se lee una vez del
// fragmento, queda solo en memoria y la URL se reemplaza sin él (no queda en el
// historial). Viaja únicamente en el cuerpo de validar y aceptar. Solo se pide
// nombre y contraseña: el correo lo fijó quien invitó.

const POLITICA = 'Entre 10 y 128 caracteres. Evita contraseñas comunes.'
// Cambio H-3 de la spec 002: el servidor exige letras o números visibles y 120 como máximo.
const NOMBRE_MAX = 120
const ERROR_NOMBRE = `Revisa el nombre: usa letras o números, hasta ${NOMBRE_MAX} caracteres y sin símbolos invisibles.`

function EnlaceNoValido() {
  return (
    <MarcoAcceso
      titulo="Este enlace no es válido"
      descripcion="Puede que haya vencido o que ya se haya usado. Si recargaste la página, abre otra vez el enlace que te enviaron; si sigue sin funcionar, pide al administrador de tu clínica una invitación nueva."
    >
      <Boton asChild variante="secundario" anchoCompleto>
        <Link to="/login">Ir a iniciar sesión</Link>
      </Boton>
    </MarcoAcceso>
  )
}

function Formulario({ token }: { token: string }) {
  const { iniciar } = useSesion()
  const navigate = useNavigate()
  const [visible, setVisible] = useState(false)

  const aceptar = useMutation({
    mutationFn: api.aceptarInvitacion,
    onSuccess: (sesion) => {
      iniciar(sesion)
      navigate(inicioDeRol(sesion.rol), { replace: true })
    },
  })

  const error = aceptar.error instanceof ErrorApi ? aceptar.error : null
  if (error?.code === 'invitacion_invalida') return <EnlaceNoValido />
  const errorClave = error?.code.startsWith('contrasena_') ? error.message : null
  // Token y contraseña siempre son texto desde esta pantalla: el 400 genérico es el nombre.
  const errorNombre = error?.code === 'solicitud_invalida' ? ERROR_NOMBRE : null
  const errorGeneral = aceptar.isError && !errorClave && !errorNombre ? mensajeDeError(aceptar.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const datos = new FormData(evento.currentTarget)
    aceptar.mutate({ token, nombre: String(datos.get('nombre') ?? ''), password: String(datos.get('password') ?? '') })
  }

  const enviando = aceptar.isPending || aceptar.isSuccess
  return (
    <MarcoAcceso
      titulo="Crea tu cuenta"
      descripcion="Te invitaron a AssetControl. Escribe tu nombre y una contraseña; tu correo ya quedó en la invitación."
    >
      <form className="flex flex-col gap-4" onSubmit={alEnviar}>
        {errorGeneral && <Aviso tono="error" titulo={errorGeneral} />}
        <Campo
          id="invitacion-nombre"
          etiqueta="Nombre"
          name="nombre"
          autoComplete="name"
          required
          maxLength={NOMBRE_MAX}
          autoFocus
          error={errorNombre ?? undefined}
        />
        <Campo
          id="invitacion-password"
          etiqueta="Contraseña"
          name="password"
          type={visible ? 'text' : 'password'}
          autoComplete="new-password"
          required
          minLength={10}
          maxLength={128}
          ayuda={POLITICA}
          error={errorClave ?? undefined}
          sufijo={
            <Boton
              variante="fantasma"
              soloIcono
              icono={visible ? <EyeOff /> : <Eye />}
              aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              aria-pressed={visible}
              className="text-muted-foreground hover:bg-transparent hover:text-foreground"
              onClick={() => setVisible((v) => !v)}
            />
          }
        />
        <Boton type="submit" anchoCompleto className="mt-2" cargando={enviando} textoCargando="Creando tu cuenta…">
          Crear cuenta y entrar
        </Boton>
      </form>
    </MarcoAcceso>
  )
}

export default function Invitacion() {
  const location = useLocation()
  const navigate = useNavigate()
  // El fragmento se lee al llegar (también si cambia sin recargar, p. ej. al pegar
  // otro enlace en la misma pestaña); después vive solo en el estado del componente.
  const fragmento = location.hash.slice(1)
  const [token, setToken] = useState(fragmento)
  if (fragmento && fragmento !== token) setToken(fragmento)

  useEffect(() => {
    if (location.hash) navigate({ pathname: location.pathname, search: '', hash: '' }, { replace: true })
  }, [location.hash, location.pathname, navigate])

  const validacion = useQuery({
    queryKey: ['invitacion', 'validar', token],
    queryFn: () => api.validarInvitacion(token),
    enabled: token !== '',
    retry: false, // validar cuenta para el límite por IP: sin reintentos automáticos
    staleTime: Infinity,
    gcTime: 0,
  })

  if (!token) return <EnlaceNoValido />
  if (validacion.isPending) return <PantallaCarga etiqueta="Comprobando la invitación" />
  if (validacion.isError) {
    return (
      <MarcoAcceso titulo="No pudimos revisar el enlace" descripcion={mensajeDeError(validacion.error)}>
        <Boton
          anchoCompleto
          icono={<RefreshCw />}
          cargando={validacion.isFetching}
          textoCargando="Reintentando…"
          onClick={() => void validacion.refetch()}
        >
          Reintentar
        </Boton>
      </MarcoAcceso>
    )
  }
  if (!validacion.data.vigente) return <EnlaceNoValido />
  return <Formulario token={token} />
}
