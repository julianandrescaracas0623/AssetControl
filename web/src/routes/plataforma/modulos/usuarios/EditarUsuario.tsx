import { RefreshCw, Save } from 'lucide-react'
import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, Confirmar, Dialogo } from '@/components/kit'
import { ErrorApi, type Rol } from '@/lib/api/cliente'
import { etiquetaRol } from '@/lib/sesion'

import { type EdicionUsuario, type ErrorEdicion, errorDeEdicion, MENSAJE_NOMBRE, NOMBRE_MAX, nombreNormalizado, useEditarUsuario, type UsuarioPlataforma } from './api'

// Editar usuario (spec 017, C1/T15; R47–R52; CU-13; A24, A25 en la web). Cuadro de diálogo
// centrado, como Editar empresa (ajuste T15b: también en el teléfono), desde «Editar» o con
// doble clic sobre la fila:
// - El correo se ve pero no se edita (ni viaja: el PUT lleva exactamente {nombre, rol}).
// - «Guardar cambios» queda deshabilitado sin cambios. Un cambio de rol pide Confirmar con la
//   persona, la empresa y el efecto: su sesión abierta se cierra (R49, R52).
// - Avisa que el nombre es de la persona, también en otras empresas (R51).
// - Rechazos del servidor (`ultimo_admin`, `empresa_inactiva`, 404, 422 con campo, 429, 503)
//   dentro del diálogo, con «Reintentar» solo cuando repetir el mismo PUT puede servir.
// El servidor decide los roles; aquí solo se propone.

const ROLES: { valor: Rol; etiqueta: string }[] = [
  { valor: 'admin', etiqueta: etiquetaRol('admin') },
  { valor: 'contador', etiqueta: etiquetaRol('contador') },
]

const rolEnTexto = (rol: Rol) => etiquetaRol(rol).toLocaleLowerCase('es-CO')

type Props = {
  empresa: { id: string; nombre: string }
  usuario: UsuarioPlataforma
  onCerrar: () => void
}

export function EditarUsuario({ empresa, usuario, onCerrar }: Props) {
  const editar = useEditarUsuario()
  const formId = useId()
  const idNombre = `${formId}-nombre`
  const idRol = `${formId}-rol`
  const [nombre, setNombre] = useState(usuario.nombre)
  const [rol, setRol] = useState<Rol>(usuario.rol)
  const [errores, setErrores] = useState<{ nombre?: string; rol?: string }>({})
  // El fallo guarda el cuerpo enviado: «Reintentar» repite exactamente ese PUT.
  const [fallo, setFallo] = useState<{ error: Extract<ErrorEdicion, { tipo: 'general' }>; edicion: EdicionUsuario } | null>(null)
  const [confirmarRol, setConfirmarRol] = useState(false)
  const [foco, setFoco] = useState<{ a: 'nombre' | 'rol' | 'aviso'; n: number } | null>(null)
  const avisoRef = useRef<HTMLDivElement>(null)

  const guardando = editar.isPending
  const sinCambios = nombre.normalize('NFC').trim() === usuario.nombre && rol === usuario.rol

  useEffect(() => {
    if (!foco) return
    if (foco.a === 'aviso') avisoRef.current?.focus()
    else document.getElementById(foco.a === 'nombre' ? idNombre : idRol)?.focus()
  }, [foco, idNombre, idRol])

  function enviar(edicion: EdicionUsuario) {
    setFallo(null)
    editar.mutate(edicion, {
      onSuccess: (editado) => {
        toast.success(editado.rol !== usuario.rol ? `${editado.nombre} ahora es ${rolEnTexto(editado.rol)} en ${empresa.nombre}` : `Cambios guardados para ${editado.nombre}`)
        onCerrar()
      },
      onError: (e) => {
        // 401 sin sesión renovable: el guard lleva a /plataforma/entrar.
        if (e instanceof ErrorApi && e.status === 401) return
        const error = errorDeEdicion(e, empresa.nombre)
        if (error.tipo === 'campo') {
          setErrores({ [error.campo]: error.mensaje })
          setFoco({ a: error.campo, n: Date.now() })
        } else {
          setFallo({ error, edicion })
          setFoco({ a: 'aviso', n: Date.now() })
        }
      },
    })
  }

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (sinCambios || guardando) return
    const limpio = nombreNormalizado(nombre)
    if (!limpio) {
      setErrores({ nombre: MENSAJE_NOMBRE })
      setFoco({ a: 'nombre', n: Date.now() })
      return
    }
    setErrores({})
    if (rol !== usuario.rol) setConfirmarRol(true)
    else enviar({ empresaId: empresa.id, usuarioId: usuario.id, nombre: limpio, rol })
  }

  const nombreFinal = nombreNormalizado(nombre) ?? usuario.nombre

  return (
    <Dialogo
      abierto
      onAbiertoChange={(abierto) => {
        if (!abierto && !guardando) onCerrar()
      }}
      forma="centrado"
      centradoEnTelefono
      titulo="Editar usuario"
      descripcion={`${usuario.nombre} · ${empresa.nombre}`}
      pie={
        <>
          <Boton variante="secundario" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Boton>
          <Boton type="submit" form={formId} icono={<Save />} disabled={sinCambios} cargando={guardando} textoCargando="Guardando…">
            Guardar cambios
          </Boton>
        </>
      }
    >
      <form id={formId} method="post" noValidate onSubmit={alEnviar} className="flex flex-col gap-4" aria-label="Datos del usuario">
        {fallo && (
          <Aviso
            ref={avisoRef}
            tabIndex={-1}
            tono="error"
            titulo={fallo.error.titulo}
            className="outline-none"
            accion={
              fallo.error.reintentar ? (
                <Boton
                  variante="secundario"
                  icono={<RefreshCw />}
                  cargando={guardando}
                  textoCargando="Reintentando…"
                  onClick={() => enviar(fallo.edicion)}
                >
                  Reintentar
                </Boton>
              ) : undefined
            }
          >
            {fallo.error.descripcion}
          </Aviso>
        )}
        {!usuario.activa && (
          <Aviso tono="info" titulo="Acceso desactivado">
            El acceso de {usuario.nombre} a {empresa.nombre} está desactivado. Puedes editar su nombre y su rol; seguirá sin poder entrar hasta que lo
            reactives.
          </Aviso>
        )}
        <Campo
          id={`${formId}-correo`}
          etiqueta="Correo"
          type="email"
          value={usuario.email}
          disabled
          readOnly
          ayuda="El correo no se cambia desde la consola: es con el que la persona entra."
        />
        <Campo
          id={idNombre}
          etiqueta="Nombre"
          obligatorio
          error={errores.nombre}
          ayuda="Es el nombre de la persona: si tiene acceso a otra empresa, allí también cambia."
          name="nombre"
          value={nombre}
          maxLength={NOMBRE_MAX}
          required
          autoComplete="off"
          disabled={guardando}
          onChange={(e) => {
            setNombre(e.target.value)
            if (errores.nombre) setErrores((a) => ({ ...a, nombre: undefined }))
          }}
        />
        <Campo
          id={idRol}
          tipo="seleccion"
          etiqueta="Rol"
          obligatorio
          opciones={ROLES}
          valor={rol}
          disabled={guardando}
          error={errores.rol}
          ayudaFija
          ayuda="Admin administra la empresa; contador cuenta los activos y no ve precios. Cambiar el rol cierra su sesión abierta: vuelve a entrar con los permisos nuevos."
          onValorChange={(valor) => {
            setRol(valor as Rol)
            if (errores.rol) setErrores((a) => ({ ...a, rol: undefined }))
          }}
        />
      </form>
      {confirmarRol && (
        <Confirmar
          abierto
          onAbiertoChange={(abierto) => {
            if (!abierto) setConfirmarRol(false)
          }}
          titulo={rol === 'admin' ? `¿Hacer admin a ${usuario.nombre}?` : `¿Cambiar a ${usuario.nombre} a ${rolEnTexto(rol)}?`}
          descripcion={
            <>
              <strong>{usuario.nombre}</strong> pasará a ser {rolEnTexto(rol)} en <strong>{empresa.nombre}</strong>. Su sesión abierta se cerrará y
              tendrá los permisos de {rolEnTexto(rol)}.
            </>
          }
          textoConfirmar="Sí, cambiar el rol"
          textoConfirmando="Guardando…"
          onConfirmar={() => enviar({ empresaId: empresa.id, usuarioId: usuario.id, nombre: nombreFinal, rol })}
        />
      )}
    </Dialogo>
  )
}
