import { useMutation, useQuery } from '@tanstack/react-query'
import { CircleAlert, Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { MarcoAcceso } from '@/components/app/MarcoAcceso'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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

function Encabezado({ titulo, descripcion }: { titulo: string; descripcion: string }) {
  return (
    <CardHeader>
      <CardTitle>
        <h1 className="text-xl font-semibold tracking-tight">{titulo}</h1>
      </CardTitle>
      <CardDescription>{descripcion}</CardDescription>
    </CardHeader>
  )
}

function EnlaceNoValido() {
  return (
    <MarcoAcceso>
      <Encabezado
        titulo="Este enlace no es válido"
        descripcion="Puede que haya vencido o que ya se haya usado. Si recargaste la página, abre otra vez el enlace que te enviaron; si sigue sin funcionar, pide al administrador de tu clínica una invitación nueva."
      />
      <CardContent>
        <Button asChild variant="outline" className="h-11 w-full md:h-9">
          <Link to="/login">Ir a iniciar sesión</Link>
        </Button>
      </CardContent>
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
    <MarcoAcceso>
      <Encabezado
        titulo="Crea tu cuenta"
        descripcion="Te invitaron a AssetControl. Escribe tu nombre y una contraseña; tu correo ya quedó en la invitación."
      />
      <CardContent>
        <form className="flex flex-col gap-4" onSubmit={alEnviar}>
          {errorGeneral && (
            <Alert variant="destructive">
              <CircleAlert />
              <AlertDescription>{errorGeneral}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor="invitacion-nombre">Nombre</Label>
            <Input
              id="invitacion-nombre"
              name="nombre"
              autoComplete="name"
              required
              maxLength={NOMBRE_MAX}
              autoFocus
              aria-invalid={errorNombre ? true : undefined}
              aria-describedby={errorNombre ? 'invitacion-nombre-error' : undefined}
              className="h-11 md:h-9"
            />
            {errorNombre && (
              <p id="invitacion-nombre-error" className="text-sm text-destructive">
                {errorNombre}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="invitacion-password">Contraseña</Label>
            <div className="relative">
              <Input
                id="invitacion-password"
                name="password"
                type={visible ? 'text' : 'password'}
                autoComplete="new-password"
                required
                minLength={10}
                maxLength={128}
                aria-invalid={errorClave ? true : undefined}
                aria-describedby={errorClave ? 'invitacion-password-error invitacion-password-ayuda' : 'invitacion-password-ayuda'}
                className="h-11 pr-12 md:h-9 md:pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute top-0 right-0 size-11 text-muted-foreground md:size-9"
                aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                aria-pressed={visible}
                onClick={() => setVisible((v) => !v)}
              >
                {visible ? <EyeOff /> : <Eye />}
              </Button>
            </div>
            {errorClave && (
              <p id="invitacion-password-error" className="text-sm text-destructive">
                {errorClave}
              </p>
            )}
            <p id="invitacion-password-ayuda" className="text-xs text-muted-foreground">
              {POLITICA}
            </p>
          </div>
          <Button type="submit" className="h-11 w-full md:h-9" disabled={enviando}>
            {enviando && <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            Crear cuenta y entrar
          </Button>
        </form>
      </CardContent>
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
      <MarcoAcceso>
        <Encabezado titulo="No pudimos revisar el enlace" descripcion={mensajeDeError(validacion.error)} />
        <CardContent>
          <Button className="h-11 w-full md:h-9" onClick={() => void validacion.refetch()}>
            Reintentar
          </Button>
        </CardContent>
      </MarcoAcceso>
    )
  }
  if (!validacion.data.vigente) return <EnlaceNoValido />
  return <Formulario token={token} />
}
