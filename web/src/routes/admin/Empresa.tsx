import { Building2, CircleAlert, ImageOff, ImageUp, LoaderCircle, Save, Trash2 } from 'lucide-react'
import { type FormEvent, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Campo, Obligatorio } from '@/components/app/CampoFormulario'
import { EncabezadoPagina } from '@/components/app/ConEstado'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorApi, mensajeDeError } from '@/lib/api/cliente'
import {
  type CampoEmpresa,
  type Empresa,
  type ErroresEmpresa,
  LOGO_MAX_BYTES,
  MENSAJES,
  useEmpresa,
  useGuardarEmpresa,
  useImagenLogo,
  useQuitarLogo,
  useSubirLogo,
  validarEmpresa,
} from '@/lib/empresa'

// /admin/empresa (spec 013, T6; R1, R2, R10): datos y logo de la empresa para los
// informes. Lo que se guarde sale en los informes que se cierren desde ahora; los ya
// cerrados conservan los datos que tenían al cerrarse (R3).

const CAMPOS: { campo: CampoEmpresa; etiqueta: string; obligatorio?: boolean; ayuda?: string; tipo?: string; modo?: 'tel' | 'email' | 'numeric' | 'text' }[] = [
  { campo: 'nombre', etiqueta: 'Nombre o razón social', obligatorio: true },
  { campo: 'direccion', etiqueta: 'Dirección', obligatorio: true, ayuda: 'Calle, número y ciudad.' },
  { campo: 'nit', etiqueta: 'NIT', ayuda: 'Opcional. Con el dígito de verificación: 900123456-8.', modo: 'numeric' },
  { campo: 'telefono', etiqueta: 'Teléfono', ayuda: 'Opcional.', tipo: 'tel', modo: 'tel' },
  { campo: 'correo', etiqueta: 'Correo', ayuda: 'Opcional.', tipo: 'email', modo: 'email' },
]

function valores(empresa: Empresa): Record<CampoEmpresa, string> {
  return {
    nombre: empresa.nombre ?? '',
    direccion: empresa.direccion ?? '',
    nit: empresa.nit ?? '',
    telefono: empresa.telefono ?? '',
    correo: empresa.correo ?? '',
  }
}

function Formulario({ empresa }: { empresa: Empresa }) {
  const guardar = useGuardarEmpresa()
  const [datos, setDatos] = useState(() => valores(empresa))
  const [errores, setErrores] = useState<ErroresEmpresa>({})
  const errorServidor = guardar.error instanceof ErrorApi ? guardar.error : null
  const campoServidor = (errorServidor?.cuerpo as { error?: { campo?: CampoEmpresa } } | undefined)?.error?.campo
  const errorGeneral = guardar.isError && !campoServidor ? mensajeDeError(guardar.error) : null

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    const { errores: nuevos, cuerpo } = validarEmpresa(datos)
    setErrores(nuevos)
    if (!cuerpo) {
      document.getElementById(`empresa-${Object.keys(nuevos)[0]}`)?.focus()
      return
    }
    guardar.mutate(cuerpo, {
      onSuccess: ({ empresa: guardada }) => {
        setDatos(valores(guardada))
        toast.success('Datos de la empresa guardados')
      },
    })
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={alEnviar} noValidate>
      {errorGeneral && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription>{errorGeneral}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {CAMPOS.map(({ campo, etiqueta, obligatorio, ayuda, tipo, modo }) => {
          const id = `empresa-${campo}`
          const error = errores[campo] ?? (campoServidor === campo ? MENSAJES[campo] : undefined)
          return (
            <Campo
              key={campo}
              id={id}
              etiqueta={
                <>
                  {etiqueta} {obligatorio && <Obligatorio />}
                </>
              }
              error={error}
              ayuda={ayuda}
              className={campo === 'nombre' || campo === 'direccion' ? 'sm:col-span-2' : undefined}
            >
              <Input
                id={id}
                name={campo}
                type={tipo ?? 'text'}
                inputMode={modo}
                value={datos[campo]}
                required={obligatorio}
                autoComplete={campo === 'correo' ? 'email' : campo === 'telefono' ? 'tel' : 'off'}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${id}-error` : ayuda ? `${id}-ayuda` : undefined}
                className="h-11 md:h-9"
                onChange={(evento) => {
                  const valor = evento.target.value
                  setDatos((anteriores) => ({ ...anteriores, [campo]: valor }))
                  if (errores[campo]) {
                    setErrores((anteriores) => {
                      const resto = { ...anteriores }
                      delete resto[campo]
                      return resto
                    })
                  }
                }}
              />
            </Campo>
          )
        })}
      </div>
      <Button type="submit" className="h-11 self-start md:h-9" disabled={guardar.isPending}>
        {guardar.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Save />}
        Guardar datos
      </Button>
    </form>
  )
}

function Logo({ empresa }: { empresa: Empresa }) {
  const entrada = useRef<HTMLInputElement>(null)
  const subir = useSubirLogo()
  const quitar = useQuitarLogo()
  const [confirmando, setConfirmando] = useState(false)
  const logoId = empresa.logo?.id ?? null
  const imagen = useImagenLogo(logoId)
  const ocupado = subir.isPending || quitar.isPending

  function elegir(archivo: File | null) {
    if (!archivo) return
    subir.mutate(archivo, {
      onSuccess: () => toast.success('Logo guardado'),
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex min-h-28 items-center justify-center rounded-lg border border-dashed bg-muted/30 p-4">
        {logoId && imagen.url ? (
          <img src={imagen.url} alt={`Logo de ${empresa.nombre}`} className="max-h-24 max-w-full object-contain" />
        ) : logoId && imagen.cargando ? (
          <Skeleton className="h-20 w-40" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
            <ImageOff className="size-5" aria-hidden="true" />
            Sin logo
          </span>
        )}
      </div>
      {!empresa.completa && (
        <p className="text-xs text-muted-foreground">Guarda primero el nombre y la dirección para poder subir el logo.</p>
      )}
      <input
        ref={entrada}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="entrada-logo"
        onChange={(evento) => {
          const archivo = evento.target.files?.[0] ?? null
          evento.target.value = ''
          elegir(archivo)
        }}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          className="h-11 md:h-9"
          disabled={!empresa.completa || ocupado}
          onClick={() => entrada.current?.click()}
        >
          {subir.isPending ? <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <ImageUp />}
          {logoId ? 'Cambiar logo' : 'Subir logo'}
        </Button>
        {logoId && (
          <Button type="button" variant="ghost" className="h-11 md:h-9" disabled={ocupado} onClick={() => setConfirmando(true)}>
            <Trash2 aria-hidden="true" /> Quitar logo
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        PNG, JPG o WebP de hasta {LOGO_MAX_BYTES / 1024 / 1024} MB. Se guarda sin datos ocultos y con fondo transparente si lo
        tiene.
      </p>
      {subir.isError && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription className="flex flex-wrap items-center gap-2">
            {mensajeDeError(subir.error)}
            {subir.variables && (
              <Button size="sm" variant="outline" onClick={() => subir.mutate(subir.variables!)}>
                Reintentar
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}
      <AlertDialog open={confirmando} onOpenChange={setConfirmando}>
        <AlertDialogContent>
          <AlertDialogTitle>¿Quitar el logo?</AlertDialogTitle>
          <AlertDialogDescription>
            Los próximos informes saldrán sin logo. Los informes ya cerrados conservan el logo que tenían.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                quitar.mutate(undefined, {
                  onSuccess: () => toast.success('Logo quitado'),
                  onError: (error) => toast.error(mensajeDeError(error)),
                })
              }
            >
              Quitar logo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default function EmpresaPagina() {
  const empresa = useEmpresa()

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo="Empresa"
        descripcion="Los datos y el logo salen en el encabezado del Excel y del PDF de los informes que cierres desde ahora. Los informes ya cerrados conservan los datos que tenían."
      />
      {empresa.isError ? (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertDescription className="flex flex-wrap items-center gap-2">
            {mensajeDeError(empresa.error)}
            <Button size="sm" variant="outline" onClick={() => void empresa.refetch()}>
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,40rem)_minmax(0,22rem)] lg:items-start">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="flex items-center gap-2 text-base font-semibold">
                  <Building2 className="size-4 text-muted-foreground" aria-hidden="true" />
                  Datos de la empresa
                </h2>
              </CardTitle>
              <CardDescription>Nombre y dirección son obligatorios; lo demás, si lo tienes.</CardDescription>
            </CardHeader>
            <CardContent>
              {empresa.data ? (
                <Formulario empresa={empresa.data} />
              ) : (
                <div className="flex flex-col gap-4" aria-busy="true" aria-label="Cargando datos de la empresa">
                  <Skeleton className="h-9 w-full" />
                  <Skeleton className="h-9 w-full" />
                  <Skeleton className="h-9 w-2/3" />
                </div>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="text-base font-semibold">Logo</h2>
              </CardTitle>
              <CardDescription>Opcional. Sale arriba a la izquierda en el Excel y en el PDF.</CardDescription>
            </CardHeader>
            <CardContent>{empresa.data ? <Logo empresa={empresa.data} /> : <Skeleton className="h-28 w-full" />}</CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
