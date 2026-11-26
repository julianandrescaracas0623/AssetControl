import { useMutation } from '@tanstack/react-query'
import { Copy, MailPlus, Power, PowerOff, ShieldCheck, TriangleAlert, UserPlus, Users } from 'lucide-react'
import { useId, type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, Confirmar, Dialogo, EncabezadoPagina, Insignia, ListaDatos, Panel, TablaDatos, type ColumnaTabla } from '@/components/kit'
import { useIsMobile } from '@/hooks/use-mobile'
import { api, ErrorApi, type InvitacionCreada, mensajeDeError, type Rol } from '@/lib/api/cliente'
import { type UsuarioEmpresa, useCambiarUsuario, useUsuarios } from '@/lib/usuarios'
import { etiquetaRol, useApiAutenticada, useSesion } from '@/lib/sesion'
import { cn } from '@/lib/utils'

// /admin/usuarios (spec 002b, T5; plan §7): invitar con correo y rol. El enlace sale
// una sola vez (el servidor no lo vuelve a dar) y se copia para enviarlo por un canal
// privado. Las personas con acceso salen de GET /usuarios, en tabla; el doble clic abre
// la ficha (solo lo que ya trajo la lista). El admin cambia el rol y activa o desactiva
// con PUT /usuarios/{usuario_id} (0033). El servidor decide y avisa: no deja cambiar el
// propio rol ni desactivarse, ni quitar al último admin activo.
// Spec 016, T9 (R2, R5): presentación con el kit. El rol lo decide el servidor; el enlace
// no se guarda ni se escribe en ningún registro.

const ROLES: { valor: Rol; descripcion: string; icono: typeof Users }[] = [
  { valor: 'contador', descripcion: 'Cuenta y verifica activos. No ve precios.', icono: Users },
  { valor: 'admin', descripcion: 'Gestiona activos, precios, conteos, informes y usuarios.', icono: ShieldCheck },
]

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function SelectorRol({ valor, onCambio }: { valor: Rol; onCambio: (rol: Rol) => void }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-1.5">
      <legend className="mb-1.5 text-etiqueta text-foreground">Rol</legend>
      <div className="grid gap-separacion sm:grid-cols-2">
        {ROLES.map(({ valor: rol, descripcion, icono: Icono }) => (
          <label
            key={rol}
            className={cn(
              'flex min-h-control cursor-pointer items-start gap-3 rounded-lg border bg-card p-3 shadow-xs transition-colors has-[:focus-visible]:border-foreground motion-reduce:transition-none',
              valor === rol ? 'border-brand-border bg-brand-soft' : 'hover:bg-muted',
            )}
          >
            <input
              type="radio"
              name="rol"
              value={rol}
              checked={valor === rol}
              onChange={() => onCambio(rol)}
              className="mt-0.5 size-4 shrink-0 accent-brand"
            />
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="flex items-center gap-1.5 text-cuerpo font-medium">
                <Icono className="size-4 text-muted-foreground" aria-hidden="true" />
                {etiquetaRol(rol)}
              </span>
              <span className="text-etiqueta font-normal text-muted-foreground">{descripcion}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function Resultado({ creada, onOtra }: { creada: InvitacionCreada; onOtra: () => void }) {
  const enlace = `${window.location.origin}${creada.enlace}`
  const { email, rol, expira_en } = creada.invitacion

  async function copiar() {
    try {
      await navigator.clipboard.writeText(enlace)
      toast.success('Enlace copiado')
    } catch {
      const campo = document.getElementById('enlace-invitacion') as HTMLInputElement | null
      campo?.select()
      toast.info('Selecciona el enlace y cópialo')
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <Aviso tono="exito" icono={<MailPlus aria-hidden="true" />} titulo="Invitación creada">
        <div className="flex flex-col gap-0.5">
          <span>
            Para <strong className="font-medium break-all">{email}</strong> como {etiquetaRol(rol)}.
          </span>
          <span>Vence: {fechaHora.format(new Date(expira_en))}</span>
        </div>
      </Aviso>
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-separacion sm:flex-row sm:items-end">
          <Campo
            id="enlace-invitacion"
            tipo="codigo"
            etiqueta="Enlace de invitación"
            readOnly
            value={enlace}
            onFocus={(evento) => evento.currentTarget.select()}
            className="flex-1"
          />
          <Boton icono={<Copy />} className="shrink-0" onClick={() => void copiar()}>
            Copiar enlace
          </Boton>
        </div>
        <p className="flex items-start gap-1.5 text-etiqueta font-normal text-muted-foreground">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
          El enlace se muestra una sola vez. Envíalo solo a esa persona por un canal privado; quien lo abra puede crear la
          cuenta.
        </p>
      </div>
      <Boton variante="secundario" icono={<UserPlus />} className="self-start max-sm:w-full" onClick={onOtra}>
        Invitar a otra persona
      </Boton>
    </div>
  )
}

/** Lo que pasó, en una frase, tras un cambio que el servidor aceptó. */
function mensajeDeCambio(persona: UsuarioEmpresa, despues: { rol: Rol; activa: boolean }): string {
  if (!despues.activa) return `${persona.nombre} quedó desactivada`
  if (!persona.activa) return `${persona.nombre} vuelve a tener acceso`
  return `${persona.nombre} ahora es ${etiquetaRol(despues.rol)}`
}

function RolPersona({ persona }: { persona: UsuarioEmpresa }) {
  return <Insignia tono={persona.rol === 'admin' ? 'fuerte' : 'neutro'}>{etiquetaRol(persona.rol)}</Insignia>
}

function EstadoPersona({ persona }: { persona: UsuarioEmpresa }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {persona.activa ? <span className="text-etiqueta text-muted-foreground">Activa</span> : <Insignia tono="error">Desactivada</Insignia>}
      {persona.debe_cambiar_password && <Insignia tono="aviso">Debe cambiar su contraseña</Insignia>}
    </span>
  )
}

function columnas(miId: string | undefined): ColumnaTabla<UsuarioEmpresa>[] {
  return [
    {
      id: 'persona',
      encabezado: 'Persona',
      principal: true,
      celda: (persona) => (
        <span className="inline-flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="break-words">{persona.nombre}</span>
          {persona.id === miId && <Insignia tono="info">Tú</Insignia>}
        </span>
      ),
    },
    {
      id: 'correo',
      encabezado: 'Correo',
      clase: '[overflow-wrap:anywhere]',
      celda: (persona) => <span className="text-muted-foreground">{persona.email}</span>,
    },
    { id: 'rol', encabezado: 'Rol', celda: (persona) => <RolPersona persona={persona} /> },
    { id: 'estado', encabezado: 'Estado', celda: (persona) => <EstadoPersona persona={persona} /> },
  ]
}

function FichaPersona({ persona, esYo, onCerrar }: { persona: UsuarioEmpresa; esYo: boolean; onCerrar: () => void }) {
  return (
    <Dialogo
      abierto
      onAbiertoChange={(abierto) => {
        if (!abierto) onCerrar()
      }}
      titulo={<span className="break-words">{persona.nombre}</span>}
      descripcion={<span className="break-all">{persona.email}</span>}
      pie={
        <Boton variante="secundario" onClick={onCerrar}>
          Cerrar
        </Boton>
      }
    >
      <ListaDatos
        datos={[
          { rotulo: 'Rol', valor: <RolPersona persona={persona} /> },
          { rotulo: 'Estado', valor: persona.activa ? 'Activa' : <Insignia tono="error">Desactivada</Insignia> },
          { rotulo: 'Contraseña', valor: persona.debe_cambiar_password ? <Insignia tono="aviso">Debe cambiar su contraseña</Insignia> : false },
          { rotulo: 'Cuenta', valor: esYo ? <Insignia tono="info">Tú</Insignia> : false },
        ]}
      />
    </Dialogo>
  )
}

function ListaPersonas() {
  const usuarios = useUsuarios()
  const cambiar = useCambiarUsuario()
  const { sesion } = useSesion()
  const esMovil = useIsMobile()
  const [aDesactivar, setADesactivar] = useState<UsuarioEmpresa | null>(null)
  const [fichaId, setFichaId] = useState<string | null>(null)

  const miId = sesion?.usuario.id
  const lista = usuarios.data
  const ficha = lista?.find((persona) => persona.id === fichaId) ?? null

  function cambio(persona: UsuarioEmpresa, valores: { rol?: Rol; activa?: boolean }) {
    const despues = { rol: valores.rol ?? persona.rol, activa: valores.activa ?? persona.activa }
    cambiar.mutate(
      { id: persona.id, ...despues },
      {
        onSuccess: () => toast.success(mensajeDeCambio(persona, despues)),
        // El texto llega del servidor en español (p. ej. «no puedes cambiar tu propio rol»).
        onError: (error) => toast.error(mensajeDeError(error)),
      },
    )
  }

  function acciones(persona: UsuarioEmpresa) {
    if (persona.id === miId) return null
    const otroRol: Rol = persona.rol === 'admin' ? 'contador' : 'admin'
    return (
      <div className="flex flex-wrap justify-end gap-2">
        <Boton
          variante="secundario"
          icono={persona.rol === 'admin' ? <Users /> : <ShieldCheck />}
          disabled={cambiar.isPending}
          onClick={() => cambio(persona, { rol: otroRol })}
        >
          {persona.rol === 'admin' ? 'Pasar a contador' : 'Hacer administrador'}
        </Boton>
        {persona.activa ? (
          <Boton variante="secundario" icono={<PowerOff />} disabled={cambiar.isPending} onClick={() => setADesactivar(persona)}>
            Desactivar
          </Boton>
        ) : (
          <Boton variante="secundario" icono={<Power />} disabled={cambiar.isPending} onClick={() => cambio(persona, { activa: true })}>
            Reactivar
          </Boton>
        )}
      </div>
    )
  }

  function tarjeta(persona: UsuarioEmpresa) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="inline-flex flex-wrap items-center gap-1.5 text-cuerpo font-medium">
            {persona.nombre}
            {persona.id === miId && <Insignia tono="info">Tú</Insignia>}
          </span>
          <span className="text-etiqueta text-muted-foreground [overflow-wrap:anywhere]">{persona.email}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <RolPersona persona={persona} />
          <EstadoPersona persona={persona} />
        </div>
        <Boton variante="secundario" className="self-start" aria-label={`Ver a ${persona.nombre}`} onClick={() => setFichaId(persona.id)}>
          Ver
        </Boton>
        {acciones(persona)}
      </div>
    )
  }

  return (
    <>
      <TablaDatos
        etiqueta="Personas con acceso"
        columnas={columnas(miId)}
        filas={lista}
        claveFila={(persona) => persona.id}
        nombrarFilas
        cargando={usuarios.isPending}
        etiquetaCargando="Cargando personas con acceso"
        error={
          usuarios.isError
            ? { titulo: 'No se pudo cargar la lista', onReintentar: () => void usuarios.refetch(), reintentando: usuarios.isRefetching }
            : null
        }
        vacio={{ titulo: 'Todavía no hay personas con acceso', descripcion: 'Invita a la primera con el formulario.' }}
        onAbrirFila={(persona) => setFichaId(persona.id)}
        ayudaAbrirFila="Doble clic para ver"
        accionesFila={esMovil ? undefined : acciones}
        tarjeta={esMovil ? tarjeta : undefined}
      />
      {ficha && <FichaPersona persona={ficha} esYo={ficha.id === miId} onCerrar={() => setFichaId(null)} />}
      <Confirmar
        abierto={aDesactivar !== null}
        onAbiertoChange={(abierto) => {
          if (!abierto) setADesactivar(null)
        }}
        titulo={`¿Desactivar a ${aDesactivar?.nombre ?? 'esta persona'}?`}
        descripcion="Deja de tener acceso a la empresa desde su siguiente petición y no puede renovar su sesión. Puedes reactivarla después."
        textoConfirmar="Sí, desactivar"
        peligro
        onConfirmar={() => {
          if (aDesactivar) cambio(aDesactivar, { activa: false })
          setADesactivar(null)
        }}
      />
    </>
  )
}

export default function Usuarios() {
  const conToken = useApiAutenticada()
  const [rol, setRol] = useState<Rol>('contador')
  const [formulario, setFormulario] = useState(0) // cambiarlo vacía el formulario

  const crear = useMutation({
    mutationFn: (cuerpo: { email: string; rol: Rol }) => conToken((token) => api.crearInvitacion(token, cuerpo)),
  })

  const error = crear.error instanceof ErrorApi ? crear.error : null
  const errorCorreo = error?.code === 'solicitud_invalida' ? 'Revisa el correo: no parece válido.' : null
  const errorGeneral = crear.isError && !errorCorreo ? mensajeDeError(crear.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const email = String(new FormData(evento.currentTarget).get('email') ?? '').trim()
    crear.mutate({ email, rol })
  }

  function otra() {
    crear.reset()
    setRol('contador')
    setFormulario((n) => n + 1)
  }

  const tituloLista = useId()

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Usuarios"
        descripcion="Invita a las personas de tu empresa. Cada invitación es para un correo y un rol, y vence en 72 horas."
      />
      <Panel
        titulo="Invitar a una persona"
        descripcion="La persona crea su cuenta con el enlace: solo escribe su nombre y una contraseña."
        className="max-w-xl"
      >
        {crear.isSuccess ? (
          <Resultado creada={crear.data} onOtra={otra} />
        ) : (
          <form key={formulario} className="flex flex-col gap-5" onSubmit={alEnviar}>
            {errorGeneral && <Aviso tono="error" titulo={errorGeneral} />}
            <Campo
              id="invitar-email"
              etiqueta="Correo de la persona"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              required
              placeholder="nombre@clinica.com"
              error={errorCorreo ?? undefined}
            />
            <SelectorRol valor={rol} onCambio={setRol} />
            <Boton type="submit" icono={<MailPlus />} cargando={crear.isPending} className="self-start max-sm:w-full">
              Crear invitación
            </Boton>
          </form>
        )}
      </Panel>
      <section aria-labelledby={tituloLista} className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 id={tituloLista} className="inline-flex items-center gap-2 text-titulo-seccion">
            <Users className="size-4 text-muted-foreground" aria-hidden="true" />
            Personas con acceso
          </h2>
          <p className="text-etiqueta text-muted-foreground">
            Quién tiene acceso a la empresa, con su rol y su estado. Puedes cambiar el rol o activar y desactivar a cada persona. Doble clic para ver
            su ficha.
          </p>
        </div>
        <ListaPersonas />
      </section>
    </div>
  )
}
