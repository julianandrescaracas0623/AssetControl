import { useMutation } from '@tanstack/react-query'
import { CircleAlert, Copy, LoaderCircle, MailPlus, ShieldCheck, TriangleAlert, UserPlus, Users } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { toast } from 'sonner'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ErrorApi, type InvitacionCreada, mensajeDeError, type Rol } from '@/lib/api/cliente'
import { etiquetaRol, useApiAutenticada } from '@/lib/sesion'
import { cn } from '@/lib/utils'

// /admin/usuarios (spec 002b, T5; plan §7): invitar con correo y rol. El enlace sale
// una sola vez (el servidor no lo vuelve a dar) y se copia para enviarlo por un canal
// privado. La lista de usuarios llega con una spec posterior: aquí no se inventa.

const ROLES: { valor: Rol; descripcion: string; icono: typeof Users }[] = [
  { valor: 'contador', descripcion: 'Cuenta y verifica activos. No ve precios.', icono: Users },
  { valor: 'admin', descripcion: 'Gestiona activos, precios, conteos, informes y usuarios.', icono: ShieldCheck },
]

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function SelectorRol({ valor, onCambio }: { valor: Rol; onCambio: (rol: Rol) => void }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="mb-2 text-sm leading-none font-medium">Rol</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {ROLES.map(({ valor: rol, descripcion, icono: Icono }) => (
          <label
            key={rol}
            className={cn(
              'flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background',
              valor === rol ? 'border-brand-border bg-brand-soft' : 'hover:bg-muted/60',
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
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <Icono className="size-4 text-muted-foreground" aria-hidden="true" />
                {etiquetaRol(rol)}
              </span>
              <span className="text-xs text-muted-foreground">{descripcion}</span>
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
    <div className="flex flex-col gap-4">
      <Alert variant="success">
        <MailPlus />
        <AlertTitle>Invitación creada</AlertTitle>
        <AlertDescription>
          <span className="break-all">
            Para <strong className="font-medium">{email}</strong> como {etiquetaRol(rol)}. Vence el{' '}
            {fechaHora.format(new Date(expira_en))}.
          </span>
        </AlertDescription>
      </Alert>
      <div className="flex flex-col gap-2">
        <Label htmlFor="enlace-invitacion">Enlace de invitación</Label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id="enlace-invitacion"
            readOnly
            value={enlace}
            onFocus={(evento) => evento.currentTarget.select()}
            className="h-11 min-w-0 flex-1 font-mono text-xs md:h-9"
          />
          <Button type="button" className="h-11 shrink-0 md:h-9" onClick={() => void copiar()}>
            <Copy />
            Copiar enlace
          </Button>
        </div>
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <TriangleAlert className="mt-px size-3.5 shrink-0 text-warning" aria-hidden="true" />
          El enlace se muestra una sola vez. Envíalo solo a esa persona por un canal privado; quien lo abra puede crear la
          cuenta.
        </p>
      </div>
      <Button type="button" variant="outline" className="h-11 self-start md:h-9" onClick={onOtra}>
        <UserPlus />
        Invitar a otra persona
      </Button>
    </div>
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
        descripcion="Invita a las personas de tu clínica. Cada invitación es para un correo y un rol, y vence en 72 horas."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,40rem)_minmax(0,1fr)] lg:items-start">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="text-base font-semibold">Invitar a una persona</h2>
            </CardTitle>
            <CardDescription>La persona crea su cuenta con el enlace: solo escribe su nombre y una contraseña.</CardDescription>
          </CardHeader>
          <CardContent>
            {crear.isSuccess ? (
              <Resultado creada={crear.data} onOtra={otra} />
            ) : (
              <form key={formulario} className="flex flex-col gap-5" onSubmit={alEnviar}>
                {errorGeneral && (
                  <Alert variant="destructive">
                    <CircleAlert />
                    <AlertDescription>{errorGeneral}</AlertDescription>
                  </Alert>
                )}
                <div className="flex flex-col gap-2">
                  <Label htmlFor="invitar-email">Correo de la persona</Label>
                  <Input
                    id="invitar-email"
                    name="email"
                    type="email"
                    inputMode="email"
                    autoComplete="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    placeholder="nombre@clinica.com"
                    aria-invalid={errorCorreo ? true : undefined}
                    aria-describedby={errorCorreo ? 'invitar-email-error' : undefined}
                    className="h-11 md:h-9"
                  />
                  {errorCorreo && (
                    <p id="invitar-email-error" className="flex items-center gap-1.5 text-xs text-destructive">
                      <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
                      {errorCorreo}
                    </p>
                  )}
                </div>
                <SelectorRol valor={rol} onCambio={setRol} />
                <Button type="submit" className="h-11 self-start md:h-9" disabled={crear.isPending}>
                  {crear.isPending ? (
                    <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  ) : (
                    <MailPlus />
                  )}
                  Crear invitación
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
        <section aria-labelledby="personas-titulo" className="flex flex-col gap-2 rounded-xl border border-dashed p-5">
          <h2 id="personas-titulo" className="flex items-center gap-2 text-sm font-medium">
            <Users className="size-4 text-muted-foreground" aria-hidden="true" />
            Personas con acceso
          </h2>
          <p className="text-sm text-muted-foreground">
            La lista de personas con acceso llega con una spec posterior, junto con cambiar el rol y dar de baja.
          </p>
        </section>
      </div>
    </div>
  )
}
