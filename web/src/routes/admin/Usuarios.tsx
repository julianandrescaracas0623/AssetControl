import { useMutation } from '@tanstack/react-query'
import { Copy, MailPlus, ShieldCheck, TriangleAlert, UserPlus, Users } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { Aviso, Boton, Campo, EncabezadoPagina, Estado, Insignia, Panel } from '@/components/kit'
import { api, ErrorApi, type InvitacionCreada, mensajeDeError, type Rol } from '@/lib/api/cliente'
import { type UsuarioEmpresa, useUsuarios } from '@/lib/usuarios'
import { etiquetaRol, useApiAutenticada } from '@/lib/sesion'
import { cn } from '@/lib/utils'

// /admin/usuarios (spec 002b, T5; plan §7): invitar con correo y rol. El enlace sale
// una sola vez (el servidor no lo vuelve a dar) y se copia para enviarlo por un canal
// privado. La lista de personas con acceso sale de GET /usuarios (solo lectura: cambiar
// el rol y dar de baja llegan en una spec posterior).
// Spec 016, T9 (R2, R5): presentación con el kit (Panel, Campo, Aviso, Boton). El rol lo
// decide el servidor; el enlace no se guarda ni se escribe en ningún registro.

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

function ListaPersonas() {
  const usuarios = useUsuarios()
  if (usuarios.isPending) return <Estado.Cargando etiqueta="Cargando personas con acceso" />
  if (usuarios.isError)
    return (
      <Estado.Error titulo="No se pudo cargar la lista" onReintentar={() => void usuarios.refetch()} reintentando={usuarios.isRefetching} />
    )
  const lista: UsuarioEmpresa[] = usuarios.data
  if (lista.length === 0)
    return <Estado.Vacio titulo="Todavía no hay personas con acceso" descripcion="Invita a la primera con el formulario." />
  return (
    <ul aria-label="Personas con acceso" className="flex flex-col divide-y">
      {lista.map((persona) => (
        <li key={persona.id} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
          <span className="text-cuerpo font-medium break-all">{persona.nombre}</span>
          <span className="text-etiqueta font-normal break-all text-muted-foreground">{persona.email}</span>
          <div className="flex flex-wrap gap-1.5">
            <Insignia tono={persona.rol === 'admin' ? 'fuerte' : 'neutro'}>{etiquetaRol(persona.rol)}</Insignia>
            {!persona.activa && <Insignia tono="error">Desactivada</Insignia>}
            {persona.debe_cambiar_password && <Insignia tono="aviso">Debe cambiar su contraseña</Insignia>}
          </div>
        </li>
      ))}
    </ul>
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

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Usuarios"
        descripcion="Invita a las personas de tu empresa. Cada invitación es para un correo y un rol, y vence en 72 horas."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,40rem)_minmax(0,1fr)] lg:items-start">
        <Panel titulo="Invitar a una persona" descripcion="La persona crea su cuenta con el enlace: solo escribe su nombre y una contraseña.">
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
        <Panel
          titulo={
            <span className="inline-flex items-center gap-2">
              <Users className="size-4 text-muted-foreground" aria-hidden="true" />
              Personas con acceso
            </span>
          }
          descripcion="Quién tiene acceso a la empresa, con su rol y su estado."
        >
          <ListaPersonas />
        </Panel>
      </div>
    </div>
  )
}
