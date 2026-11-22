import { Building2, KeyRound, Pencil, Power, PowerOff, Users as IconoUsuarios } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, type ColumnaTabla, Confirmar, EncabezadoPagina, Estado, Insignia, TablaDatos } from '@/components/kit'
import { useIsMobile } from '@/hooks/use-mobile'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import { formatEntero } from '@/lib/format'
import { etiquetaRol } from '@/lib/sesion'

import { RUTA_PLATAFORMA } from '../../sesion'
import { useEmpresas } from '../empresas/api'
import { EditarUsuario } from './EditarUsuario'
import { RestablecerContrasena } from './RestablecerContrasena'
import { type CambioUsuario, empresaDeConsulta, type ErrorCambio, errorDeCambio, useCambiarEstadoUsuario, useUsuarios, type UsuarioPlataforma } from './api'

// Módulo Usuarios de la consola (spec 017, T10; R29–R31, R38, R40; CU-07; A17).
// - La empresa se elige en un selector y queda en la URL (`?empresa=<id>`), que es también
//   el enlace «Ver usuarios» de Empresas (CU-05). Un `?empresa=` que no es un UUID canónico
//   se ignora: sin redirigir ni pedir nada.
// - Por usuario: nombre, correo, rol, estado y «Cambio de contraseña pendiente» (R29; sin
//   fecha de alta: el contrato no la tiene). Tabla a 1440 px, tarjetas a 375 px.
// - Desactivar y reactivar con Confirmar que nombra a la persona, la empresa y el efecto
//   (R40), incluido que pierde la sesión abierta. Los rechazos del servidor (`ultimo_admin`,
//   `empresa_inactiva`, 404, 429, 503) se explican en un aviso con su acción.
// - «Editar» (C1/T15; R47–R52; CU-13) abre EditarUsuario: nombre y rol, correo solo de lectura.
//   También con doble clic o Enter sobre la fila (ajuste T15b), con las mismas condiciones
//   que el botón: con la empresa desactivada o desconocida la fila no se abre.
// - «Restablecer contraseña» (C1b/T16; R53–R60; CU-14) abre RestablecerContrasena: una
//   contraseña temporal que la persona cambia al entrar. Con éxito, la lista se vuelve a pedir
//   y la fila muestra «Cambio de contraseña pendiente» (lo que diga el servidor).
// - Empresa desactivada: acciones deshabilitadas con la explicación (D9; el servidor
//   responde `409 empresa_inactiva` igual). Esconder o deshabilitar no es seguridad.
// Nombres y correos se pintan como texto (React escapa): nunca HTML.

function EstadoUsuario({ usuario }: { usuario: UsuarioPlataforma }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {usuario.activa ? (
        <Insignia tono="exito">Activo</Insignia>
      ) : (
        <Insignia tono="neutro" icono={<PowerOff aria-hidden="true" />}>
          Desactivado
        </Insignia>
      )}
      {usuario.debe_cambiar_password && (
        <Insignia tono="aviso" icono={<KeyRound aria-hidden="true" />}>
          Cambio de contraseña pendiente
        </Insignia>
      )}
    </span>
  )
}

const COLUMNAS: ColumnaTabla<UsuarioPlataforma>[] = [
  { id: 'nombre', encabezado: 'Nombre', principal: true, celda: (u) => <span className="break-words">{u.nombre}</span>, clase: 'min-w-48' },
  { id: 'correo', encabezado: 'Correo', celda: (u) => <span className="break-all">{u.email}</span> },
  { id: 'rol', encabezado: 'Rol', celda: (u) => etiquetaRol(u.rol) },
  { id: 'estado', encabezado: 'Estado', celda: (u) => <EstadoUsuario usuario={u} />, clase: 'min-w-44' },
]

const ID_AVISO_INACTIVA = 'usuarios-empresa-inactiva'
const ID_ESTADO_EMPRESA = 'usuarios-estado-empresa'

type Fallo = { cambio: CambioUsuario; error: ErrorCambio }

export default function Usuarios() {
  const [parametros, setParametros] = useSearchParams()
  const empresaId = empresaDeConsulta(parametros.get('empresa'))
  const empresas = useEmpresas()
  const usuarios = useUsuarios(empresaId)
  const cambiar = useCambiarEstadoUsuario()
  const [pendiente, setPendiente] = useState<UsuarioPlataforma | null>(null)
  const [fallo, setFallo] = useState<Fallo | null>(null)
  const [editando, setEditando] = useState<UsuarioPlataforma | null>(null)
  const [restableciendo, setRestableciendo] = useState<UsuarioPlataforma | null>(null)
  const esMovil = useIsMobile()

  const empresa = empresaId ? empresas.data?.find((e) => e.id === empresaId) : undefined
  const nombreEmpresa = empresa?.nombre ?? 'esta empresa'
  const inactiva = empresa?.activa === false
  // D23: hasta conocer la empresa (lista cargando, con error o sin ella) no se sabe si está
  // activa ni cómo se llama: las acciones esperan, con su estado explicado.
  const desconocida = Boolean(empresaId) && !empresa
  const bloqueada = inactiva || desconocida
  const idExplicacion = inactiva ? ID_AVISO_INACTIVA : desconocida ? ID_ESTADO_EMPRESA : undefined

  function elegirEmpresa(id: string) {
    setFallo(null)
    setParametros({ empresa: id }, { replace: true })
  }

  function enviar(cambio: CambioUsuario) {
    setFallo(null)
    cambiar.mutate(cambio, {
      onSuccess: ({ activa }) => {
        const nombre = cambio.usuario.nombre
        toast.success(activa ? `${nombre} reactivado en ${nombreEmpresa}` : `${nombre} desactivado en ${nombreEmpresa}`)
      },
      onError: (error) => {
        // 401 sin sesión renovable: el guard lleva a /plataforma/entrar; no hay nada que decir aquí.
        if (error instanceof ErrorApi && error.status === 401) return
        setFallo({ cambio, error: errorDeCambio(error, cambio.usuario, nombreEmpresa) })
      },
    })
  }

  const opciones = [...(empresas.data ?? [])]
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es-CO'))
    .map((e) => ({ valor: e.id, etiqueta: e.activa ? e.nombre : `${e.nombre} (desactivada)` }))

  // A 375 px: tarjeta propia (nombre, correo a lo ancho, rol y estado, y la acción abajo),
  // para que el correo no se parta en una columna estrecha junto al botón.
  function tarjeta(usuario: UsuarioPlataforma) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-cuerpo font-medium break-words">{usuario.nombre}</p>
        <p className="text-etiqueta text-muted-foreground [overflow-wrap:anywhere]">{usuario.email}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="text-etiqueta">{etiquetaRol(usuario.rol)}</span>
          <EstadoUsuario usuario={usuario} />
        </div>
        <div className="mt-2">{acciones(usuario)}</div>
      </div>
    )
  }

  // Doble clic o Enter en la fila: igual que el botón «Editar» (deshabilitado si está ocupado).
  function abrirEdicion(usuario: UsuarioPlataforma) {
    if (cambiar.isPending && cambiar.variables?.usuario.id === usuario.id) return
    setEditando(usuario)
  }

  function acciones(usuario: UsuarioPlataforma) {
    const activa = !usuario.activa
    const ocupado = cambiar.isPending && cambiar.variables?.usuario.id === usuario.id
    return (
      <div className="flex gap-2 max-sm:grid max-sm:grid-cols-2 sm:justify-end">
        <Boton
          variante="secundario"
          icono={<Pencil />}
          disabled={bloqueada || ocupado}
          aria-label={`Editar a ${usuario.nombre}`}
          aria-describedby={idExplicacion}
          onClick={() => setEditando(usuario)}
        >
          Editar
        </Boton>
        <Boton
          variante="secundario"
          icono={<KeyRound />}
          disabled={bloqueada || ocupado}
          aria-label={`Restablecer la contraseña de ${usuario.nombre}`}
          aria-describedby={idExplicacion}
          // A 375 px va abajo, a lo ancho: su texto es el más largo.
          className="max-sm:order-last max-sm:col-span-2"
          onClick={() => setRestableciendo(usuario)}
        >
          Restablecer contraseña
        </Boton>
        <Boton
          variante="secundario"
          icono={usuario.activa ? <PowerOff /> : <Power />}
          disabled={bloqueada || (cambiar.isPending && !ocupado)}
          cargando={ocupado}
          textoCargando={activa ? 'Reactivando…' : 'Desactivando…'}
          aria-label={`${usuario.activa ? 'Desactivar' : 'Reactivar'} a ${usuario.nombre}`}
          aria-describedby={idExplicacion}
          onClick={() => setPendiente(usuario)}
        >
          {usuario.activa ? 'Desactivar' : 'Reactivar'}
        </Boton>
      </div>
    )
  }

  let contenido
  if (!empresaId) {
    contenido =
      empresas.data && empresas.data.length === 0 ? (
        <Estado.Vacio
          icono={<Building2 />}
          titulo="Aún no hay empresas"
          descripcion="Los usuarios pertenecen a una empresa. Crea la primera en Empresas."
          accion={
            <Boton variante="secundario" asChild>
              <Link to={`${RUTA_PLATAFORMA}/empresas`}>Ir a Empresas</Link>
            </Boton>
          }
        />
      ) : (
        <Estado.Vacio
          icono={<IconoUsuarios />}
          titulo="Elige una empresa"
          descripcion="Verás quién tiene acceso a ella, con su rol y su estado."
        />
      )
  } else {
    const lista = usuarios.data
    const activos = lista?.filter((u) => u.activa).length ?? 0
    contenido = (
      <div className="flex flex-col gap-4">
        {lista && (
          <p className="text-cuerpo text-muted-foreground" aria-live="polite">
            {empresa && (
              <>
                <span className="font-medium text-foreground">{empresa.nombre}</span> ·{' '}
              </>
            )}
            {formatEntero(lista.length)} {lista.length === 1 ? 'usuario' : 'usuarios'} · {formatEntero(activos)}{' '}
            {activos === 1 ? 'activo' : 'activos'}
          </p>
        )}
        {desconocida && !empresas.isError && (
          <p id={ID_ESTADO_EMPRESA} role="status" className="text-etiqueta text-muted-foreground">
            {empresas.isPending
              ? 'Comprobando el estado de la empresa… Las acciones se habilitan en cuanto se sepa si está activa.'
              : 'No encontramos esta empresa en la lista de empresas. Elígela en el selector.'}
          </p>
        )}
        {desconocida && empresas.isError && (
          <Aviso
            id={ID_ESTADO_EMPRESA}
            tono="error"
            titulo="No se pudo cargar la lista de empresas"
            rol="status"
            accion={
              <Boton variante="secundario" cargando={empresas.isFetching} textoCargando="Reintentando…" onClick={() => void empresas.refetch()}>
                Reintentar
              </Boton>
            }
          >
            Sin ella no sabemos si la empresa está activa, así que editar, restablecer la contraseña, desactivar y reactivar esperan. {mensajeDeError(empresas.error)}
          </Aviso>
        )}
        {inactiva && (
          <Aviso
            id={ID_AVISO_INACTIVA}
            tono="aviso"
            titulo="Esta empresa está desactivada"
            rol="status"
            accion={
              <Boton variante="secundario" asChild>
                <Link to={`${RUTA_PLATAFORMA}/empresas`}>Ir a Empresas</Link>
              </Boton>
            }
          >
            Sus usuarios no pueden entrar. Para editar, restablecer la contraseña, desactivar o reactivar a alguien, primero reactiva la empresa en Empresas.
          </Aviso>
        )}
        {fallo && (
          <Aviso
            tono="error"
            titulo={fallo.error.titulo}
            accion={
              fallo.error.reintentar ? (
                <Boton variante="secundario" cargando={cambiar.isPending} textoCargando="Reintentando…" onClick={() => enviar(fallo.cambio)}>
                  Reintentar
                </Boton>
              ) : undefined
            }
          >
            {fallo.error.descripcion}
          </Aviso>
        )}
        <TablaDatos
          etiqueta={`Usuarios de ${nombreEmpresa}`}
          columnas={COLUMNAS}
          filas={lista}
          claveFila={(u) => u.id}
          // La tarjeta propia no lleva el id del nombre: solo las filas de la tabla se nombran así.
          nombrarFilas={!esMovil}
          tarjeta={tarjeta}
          cargando={usuarios.isPending}
          etiquetaCargando="Cargando usuarios"
          error={
            usuarios.isError
              ? usuarios.error instanceof ErrorApi && usuarios.error.status === 404
                ? { titulo: 'No encontramos esa empresa', descripcion: 'Puede que el enlace esté incompleto. Elige la empresa en el selector.' }
                : {
                    titulo: 'No se pudieron cargar los usuarios',
                    descripcion: mensajeDeError(usuarios.error),
                    onReintentar: () => void usuarios.refetch(),
                    reintentando: usuarios.isFetching,
                  }
              : null
          }
          vacio={{
            icono: <IconoUsuarios />,
            titulo: 'Esta empresa aún no tiene usuarios',
            descripcion: 'Su admin invita a las personas desde la aplicación de la clínica.',
          }}
          accionesFila={esMovil ? undefined : acciones}
          onAbrirFila={bloqueada ? undefined : abrirEdicion}
          ayudaAbrirFila="Doble clic para editar"
        />
      </div>
    )
  }

  const cambio: CambioUsuario | null = pendiente && empresaId ? { empresaId, usuario: pendiente, activa: !pendiente.activa } : null

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Usuarios"
        descripcion="Quién tiene acceso a cada empresa. Puedes corregir el nombre o el rol de alguien, definirle una contraseña temporal o desactivarlo sin borrar nada; los nuevos usuarios los invita el admin de la clínica."
      />
      <Campo
        id="usuarios-empresa"
        tipo="seleccion"
        etiqueta="Empresa"
        className="max-w-md"
        placeholder={empresas.isError ? 'No se pudieron cargar las empresas' : 'Elige una empresa'}
        cargando={empresas.isPending}
        disabled={empresas.isError || opciones.length === 0}
        opciones={opciones}
        // Siempre controlado: '' muestra el texto de ayuda (sin empresa elegida o desconocida).
        valor={empresa ? empresa.id : ''}
        onValorChange={elegirEmpresa}
        error={empresas.isError ? 'No se pudo cargar la lista de empresas. Revisa la conexión y recarga la página.' : undefined}
      />
      {contenido}
      {editando && empresaId && empresa && (
        <EditarUsuario empresa={{ id: empresaId, nombre: empresa.nombre }} usuario={editando} onCerrar={() => setEditando(null)} />
      )}
      {restableciendo && empresaId && empresa && (
        <RestablecerContrasena
          empresa={{ id: empresaId, nombre: empresa.nombre }}
          usuario={restableciendo}
          onCerrar={() => setRestableciendo(null)}
        />
      )}
      {cambio && (
        <Confirmar
          abierto
          onAbiertoChange={(abierto) => {
            if (!abierto) setPendiente(null)
          }}
          titulo={cambio.activa ? `¿Reactivar a ${cambio.usuario.nombre}?` : `¿Desactivar a ${cambio.usuario.nombre}?`}
          descripcion={
            cambio.activa ? (
              <>
                <strong>{cambio.usuario.nombre}</strong> podrá volver a entrar a <strong>{nombreEmpresa}</strong> con su correo y
                contraseña, como {etiquetaRol(cambio.usuario.rol).toLocaleLowerCase('es-CO')}.
              </>
            ) : (
              <>
                <strong>{cambio.usuario.nombre}</strong> no podrá entrar a <strong>{nombreEmpresa}</strong>. Si tiene una sesión
                abierta, se cierra en su siguiente acción. No se borra nada; puedes reactivarlo cuando quieras.
              </>
            )
          }
          textoConfirmar={cambio.activa ? 'Sí, reactivar' : 'Sí, desactivar'}
          textoConfirmando={cambio.activa ? 'Reactivando…' : 'Desactivando…'}
          peligro={!cambio.activa}
          onConfirmar={() => enviar(cambio)}
        />
      )}
    </div>
  )
}
