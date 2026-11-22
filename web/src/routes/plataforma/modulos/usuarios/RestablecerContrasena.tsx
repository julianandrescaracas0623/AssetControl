import { useQueryClient } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { toast } from 'sonner'

import { CampoContrasena, POLITICA_CONTRASENA } from '@/components/app/CampoContrasena'
import { Aviso, Boton, Confirmar, Dialogo } from '@/components/kit'
import { ErrorApi } from '@/lib/api/cliente'
import { apiPlataforma } from '@/lib/api/plataforma'

import { useApiPlataforma } from '../../sesion'
import { CLAVE_EMPRESAS } from '../empresas/api'
import {
  type CampoClave,
  CLAVE_MAX,
  CLAVE_MIN,
  CLAVE_USUARIOS,
  type ErrorContrasena,
  errorDeContrasena,
  MENSAJE_CLAVE_CORTA,
  MENSAJE_CLAVES_DISTINTAS,
  type UsuarioPlataforma,
} from './api'

// Restablecer contraseña (spec 017, C1b/T16; R53–R60, R39; CU-14; A29 en la web). Cuadro
// centrado, como Editar usuario (decisión del humano, T15b), desde «Restablecer contraseña»
// en la fila de Usuarios. El desarrollador define una contraseña temporal; la persona la
// cambia al entrar y pierde todas sus sesiones (en todas sus empresas).
//
// La contraseña nunca pasa por React (R58, security-reviewer):
// - Los dos campos no son controlados: se leen del formulario solo al validar y al enviar.
// - Sin `useMutation`: la llamada es directa, así no queda en `variables` de la MutationCache.
// - Los campos se vacían tras responder el servidor (éxito o error), tras un error de la web,
//   al cancelar o cerrar y al desmontar; se vuelven a montar (`generacion`), así «Mostrar»
//   vuelve a oculto. Sin «Copiar» ni generador (R39); el valor no va a toast, aviso ni registro.
// - No es idempotente: ningún reintento automático ante 503/429; el botón espera `Retry-After`
//   y la persona vuelve a escribirla. Mientras se envía, todo queda deshabilitado.
// Esconder o deshabilitar no es seguridad: el servidor responde 409/404 igual.

type Props = {
  empresa: { id: string; nombre: string }
  usuario: UsuarioPlataforma
  onCerrar: () => void
}

type Fallo = Extract<ErrorContrasena, { tipo: 'general' }>

/** 401 que no se recuperó: el servidor no procesó el cambio. Repetir no sirve sin entrar. */
const SESION_EXPIRADA: Fallo = {
  tipo: 'general',
  titulo: 'Tu sesión expiró; entra de nuevo',
  descripcion: 'No se cambió la contraseña. Al volver, escríbela de nuevo.',
  bloquea: true,
}

/** Borra del DOM los dos valores (sin tocar el estado: sirve también al desmontar). */
function borrarValores(form: HTMLFormElement | null) {
  for (const nombre of ['password', 'password_confirmacion']) {
    const campo = form?.elements.namedItem(nombre)
    if (campo instanceof HTMLInputElement) campo.value = ''
  }
}

export function RestablecerContrasena({ empresa, usuario, onCerrar }: Props) {
  const conToken = useApiPlataforma()
  const cliente = useQueryClient()
  const formId = useId()
  const idClave = `${formId}-clave`
  const idConfirmar = `${formId}-confirmar`
  const formRef = useRef<HTMLFormElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)
  const enCurso = useRef(false)
  const montado = useRef(true)
  const [enviando, setEnviando] = useState(false)
  const [generacion, setGeneracion] = useState(0)
  const [errores, setErrores] = useState<Partial<Record<CampoClave, string>>>({})
  const [fallo, setFallo] = useState<Fallo | null>(null)
  const [vaciados, setVaciados] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const [espera, setEspera] = useState(0)
  const [foco, setFoco] = useState<{ a: CampoClave | 'aviso'; n: number } | null>(null)

  const bloqueado = fallo?.bloquea === true

  /** Los dos valores, leídos del formulario en el momento (nunca guardados). */
  function leer() {
    const form = formRef.current
    const valor = (nombre: CampoClave) => {
      const campo = form?.elements.namedItem(nombre)
      return campo instanceof HTMLInputElement ? campo.value : ''
    }
    return { password: valor('password'), password_confirmacion: valor('password_confirmacion') }
  }

  /** Borra los valores y vuelve a montar los campos (así «Mostrar» vuelve a oculto). */
  function vaciarCampos(form: HTMLFormElement | null, remontar = true) {
    borrarValores(form)
    if (remontar) setGeneracion((g) => g + 1)
  }

  useEffect(() => {
    const form = formRef.current
    montado.current = true
    return () => {
      montado.current = false
      borrarValores(form)
    }
  }, [])

  useEffect(() => {
    if (!foco) return
    if (foco.a === 'aviso') avisoRef.current?.focus()
    else document.getElementById(foco.a === 'password' ? idClave : idConfirmar)?.focus()
  }, [foco, idClave, idConfirmar])

  // Espera de `Retry-After` (503/429): cuenta atrás en el botón; no se reintenta sola.
  useEffect(() => {
    if (espera <= 0) return
    const reloj = setTimeout(() => setEspera((s) => s - 1), 1000)
    return () => clearTimeout(reloj)
  }, [espera])

  function cerrar() {
    if (enCurso.current) return
    vaciarCampos(formRef.current)
    onCerrar()
  }

  function errorDeLaWeb(campo: CampoClave, mensaje: string) {
    vaciarCampos(formRef.current)
    setVaciados(true)
    setErrores({ [campo]: mensaje })
    setFoco({ a: campo, n: Date.now() })
  }

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (enCurso.current || bloqueado || espera > 0) return
    const { password, password_confirmacion } = leer()
    setFallo(null)
    if (password === '') return errorDeLaWeb('password', `Escribe la contraseña temporal (entre ${CLAVE_MIN} y ${CLAVE_MAX} caracteres).`)
    if (password.length < CLAVE_MIN) return errorDeLaWeb('password', MENSAJE_CLAVE_CORTA)
    if (password.length > CLAVE_MAX) return errorDeLaWeb('password', `Usa como máximo ${CLAVE_MAX} caracteres.`)
    if (password !== password_confirmacion) return errorDeLaWeb('password_confirmacion', MENSAJE_CLAVES_DISTINTAS)
    setErrores({})
    setConfirmando(true)
  }

  async function enviar() {
    if (enCurso.current) return
    const cuerpo = leer()
    if (cuerpo.password === '') return
    enCurso.current = true
    setEnviando(true)
    try {
      await conToken((t) => apiPlataforma.restablecerContrasenaUsuario(t, empresa.id, usuario.id, cuerpo))
      vaciarCampos(formRef.current)
      // La fila pasa a «Cambio de contraseña pendiente» con lo que diga el servidor.
      void cliente.invalidateQueries({ queryKey: [...CLAVE_USUARIOS, empresa.id] })
      toast.success('Contraseña temporal definida', {
        description: `Entrégasela a ${usuario.nombre} por tu propio medio. Deberá cambiarla al entrar.`,
      })
      enCurso.current = false
      onCerrar()
    } catch (e) {
      vaciarCampos(formRef.current, montado.current)
      enCurso.current = false
      if (!montado.current) return
      setEnviando(false)
      setVaciados(true)
      // 401 sin sesión renovable: el guard lleva a /plataforma/entrar. Si el diálogo sigue
      // abierto, no queda mudo: lo dice (sin repetir el envío ni conservar la contraseña).
      if (e instanceof ErrorApi && e.status === 401) {
        setErrores({})
        setFallo(SESION_EXPIRADA)
        setFoco({ a: 'aviso', n: Date.now() })
        return
      }
      if (e instanceof ErrorApi && e.code === 'empresa_inactiva') void cliente.invalidateQueries({ queryKey: CLAVE_EMPRESAS })
      if (e instanceof ErrorApi && e.status === 404) void cliente.invalidateQueries({ queryKey: [...CLAVE_USUARIOS, empresa.id] })
      const error = errorDeContrasena(e, empresa.nombre)
      if (error.tipo === 'campo') {
        setErrores({ [error.campo]: error.mensaje })
        setFoco({ a: error.campo, n: Date.now() })
      } else {
        setErrores({})
        setFallo(error)
        if (error.esperar) setEspera(Math.ceil(error.esperar))
        setFoco({ a: 'aviso', n: Date.now() })
      }
    }
  }

  function quitarError(nombre: string) {
    if (nombre === 'password' && errores.password) setErrores((a) => ({ ...a, password: undefined }))
    if ((nombre === 'password' || nombre === 'password_confirmacion') && errores.password_confirmacion) {
      setErrores((a) => ({ ...a, password_confirmacion: undefined }))
    }
  }

  return (
    <Dialogo
      abierto
      onAbiertoChange={(abierto) => {
        if (!abierto) cerrar()
      }}
      forma="centrado"
      centradoEnTelefono
      titulo="Restablecer contraseña"
      descripcion={`${usuario.nombre} · ${empresa.nombre}`}
      pie={
        <>
          <Boton variante="secundario" onClick={cerrar} disabled={enviando}>
            Cancelar
          </Boton>
          <Boton
            type="submit"
            form={formId}
            icono={<KeyRound />}
            disabled={bloqueado || espera > 0}
            cargando={enviando}
            textoCargando="Definiendo…"
          >
            {espera > 0 ? `Espera ${espera} s` : 'Definir contraseña'}
          </Boton>
        </>
      }
    >
      <form
        ref={formRef}
        id={formId}
        // Defensa en profundidad (D20): un envío nativo nunca pone la contraseña en la URL.
        method="post"
        noValidate
        onSubmit={alEnviar}
        // Al escribir solo se quita el error, sin leer el valor.
        onInput={(e) => quitarError((e.target as HTMLInputElement).name)}
        className="flex flex-col gap-4"
        aria-label="Definir contraseña temporal"
      >
        {fallo && (
          <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={fallo.titulo} className="outline-none">
            {fallo.descripcion}
          </Aviso>
        )}
        {!usuario.activa && (
          <Aviso tono="info" titulo="Acceso desactivado">
            El acceso de {usuario.nombre} a {empresa.nombre} está desactivado. Puedes definir la contraseña; no podrá entrar a {empresa.nombre} hasta
            que lo reactives.
          </Aviso>
        )}
        {/* El efecto, antes de escribir (CU-14). */}
        <Aviso tono="info" icono={<KeyRound aria-hidden="true" />} titulo="Entrégala por tu propio medio">
          {usuario.nombre} deberá cambiarla al entrar y perderá su sesión abierta. No se vuelve a mostrar.
        </Aviso>
        <div key={generacion} className="flex flex-col gap-4">
          <CampoContrasena
            id={idClave}
            etiqueta="Contraseña temporal"
            name="password"
            queMostrar="la contraseña temporal"
            ayuda={POLITICA_CONTRASENA}
            error={errores.password}
            obligatorio
            disabled={enviando || bloqueado}
            sinGestor
          />
          <CampoContrasena
            id={idConfirmar}
            etiqueta="Confirmar contraseña"
            name="password_confirmacion"
            queMostrar="la confirmación"
            error={errores.password_confirmacion}
            obligatorio
            disabled={enviando || bloqueado}
            sinGestor
          />
        </div>
        {vaciados && !bloqueado && <p className="text-etiqueta text-muted-foreground">Por seguridad, los dos campos se vaciaron. Escribe la contraseña de nuevo en los dos.</p>}
      </form>
      {confirmando && (
        <Confirmar
          abierto
          onAbiertoChange={(abierto) => {
            if (!abierto) setConfirmando(false)
          }}
          titulo={`¿Definir una contraseña temporal para ${usuario.nombre}?`}
          descripcion={
            <>
              Vas a definir una contraseña temporal para <strong>{usuario.nombre}</strong> en <strong>{empresa.nombre}</strong>. Se cerrarán todas sus
              sesiones abiertas, también en otras empresas donde tenga acceso, y deberá cambiar esta contraseña al entrar. No se vuelve a mostrar.
              Le enviaremos un aviso a su correo.
            </>
          }
          textoConfirmar="Sí, definir la contraseña"
          textoConfirmando="Definiendo…"
          onConfirmar={() => void enviar()}
        />
      )}
    </Dialogo>
  )
}
