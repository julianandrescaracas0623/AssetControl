import { useQueryClient } from '@tanstack/react-query'
import { Image, ImageOff, ImageUp, RefreshCw, Save } from 'lucide-react'
import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Aviso, Boton, Dialogo, Estado, Insignia } from '@/components/kit'
import { ErrorApi } from '@/lib/api/cliente'
import { type CampoEmpresa, validarEmpresa } from '@/lib/empresa'

import {
  claveFicha,
  CAMPOS_FICHA,
  type DatosFicha,
  datosDeFicha,
  type ErrorLogo,
  errorDeFicha,
  errorDeLogo,
  type FichaEmpresa,
  idCampo,
  idElegirLogo,
  type LogoElegido,
  MENSAJE_LOGO_PESADO,
  MENSAJE_SIN_DATOS,
  prepararLogo,
  useFichaEmpresa,
  useGuardarFicha,
  useLogoElegido,
  useSubirLogoEmpresa,
} from './api'
import { BloqueLogo } from './BloqueLogo'
import { CamposFicha } from './CamposFicha'

// Editar empresa (spec 017, C1/T14; R41–R44; CU-12; A21, A22, A26). Cuadro de diálogo centrado
// (ajuste T15b: también en el teléfono, con margen y desplazamiento interno), desde «Editar» en
// el menú de la fila o con doble clic sobre la fila:
// - Carga la ficha vigente (`GET …/ficha`, clave propia que se vacía al cerrar) y la muestra en
//   los mismos campos y con los mismos mensajes del alta. «Guardar cambios» queda deshabilitado
//   sin cambios y envía las cinco claves (vacío = null: quita el opcional, R42).
// - Bloque «Logo» aparte: «Tiene logo / Sin logo»; elegir un archivo muestra su vista previa y
//   «Reemplazar logo» o «Subir logo» lo envía (R44). El logo anterior se conserva en el servidor.
//   Es la vía para reintentar un logo que falló en el alta (`logoInicial`, mismo `logo_id`).

type Props = {
  empresa: { id: string; nombre: string }
  onCerrar: () => void
  /** Archivo que no se pudo subir en el alta: llega elegido para reintentarlo con un clic. */
  logoInicial?: LogoElegido | null
  onLogoSubido?: () => void
}

export function EditarEmpresa({ empresa, onCerrar, logoInicial, onLogoSubido }: Props) {
  const cliente = useQueryClient()
  const ficha = useFichaEmpresa(empresa.id)
  const formId = useId()
  const [pie, setPie] = useState<{ sinCambios: boolean; guardando: boolean }>({ sinCambios: true, guardando: false })
  // Con un logo elegido y sin subir, guardar la ficha no cierra: el archivo no se pierde.
  const logoPendiente = useRef(false)

  // La ficha no se queda en caché al cerrar (plan §10.3).
  useEffect(() => () => cliente.removeQueries({ queryKey: claveFicha(empresa.id) }), [cliente, empresa.id])

  const sinDatos = ficha.error instanceof ErrorApi && ficha.error.code === 'empresa_sin_datos'

  let contenido
  if (ficha.data) {
    contenido = (
      <>
        <FormularioFicha
          formId={formId}
          empresaId={empresa.id}
          ficha={ficha.data}
          onEstado={setPie}
          onGuardado={() => {
            if (!logoPendiente.current) onCerrar()
          }}
        />
        <SeccionLogo
          empresa={empresa}
          tieneLogo={ficha.data.tiene_logo}
          logoInicial={logoInicial}
          onLogoSubido={onLogoSubido}
          onPendiente={(valor) => {
            logoPendiente.current = valor
          }}
        />
      </>
    )
  } else if (sinDatos) {
    contenido = <Aviso tono="info" titulo={MENSAJE_SIN_DATOS} />
  } else if (ficha.isError) {
    contenido = (
      <Aviso
        tono="error"
        titulo="No se pudieron cargar los datos de la empresa"
        accion={
          <Boton variante="secundario" icono={<RefreshCw />} cargando={ficha.isFetching} textoCargando="Reintentando…" onClick={() => void ficha.refetch()}>
            Reintentar
          </Boton>
        }
      >
        {errorDeFicha(ficha.error).mensaje}
      </Aviso>
    )
  } else {
    contenido = <Estado.Cargando etiqueta="Cargando los datos de la empresa" filas={5} />
  }

  return (
    <Dialogo
      abierto
      onAbiertoChange={(abierto) => {
        if (!abierto) onCerrar()
      }}
      forma="centrado"
      centradoEnTelefono
      ancho="ancho"
      titulo="Editar empresa"
      descripcion={empresa.nombre}
      pie={
        ficha.data ? (
          <>
            <Boton variante="secundario" onClick={onCerrar} disabled={pie.guardando}>
              Cancelar
            </Boton>
            <Boton type="submit" form={formId} icono={<Save />} disabled={pie.sinCambios} cargando={pie.guardando} textoCargando="Guardando…">
              Guardar cambios
            </Boton>
          </>
        ) : undefined
      }
    >
      {contenido}
    </Dialogo>
  )
}

// --- Ficha ------------------------------------------------------------------------------------

function FormularioFicha({
  formId,
  empresaId,
  ficha,
  onEstado,
  onGuardado,
}: {
  formId: string
  empresaId: string
  ficha: FichaEmpresa
  onEstado: (estado: { sinCambios: boolean; guardando: boolean }) => void
  onGuardado: () => void
}) {
  const guardar = useGuardarFicha(empresaId)
  const [base, setBase] = useState<DatosFicha>(() => datosDeFicha(ficha))
  const [valores, setValores] = useState<DatosFicha>(base)
  const [errores, setErrores] = useState<Partial<Record<CampoEmpresa, string>>>({})
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [foco, setFoco] = useState<{ campo: CampoEmpresa | 'aviso'; n: number } | null>(null)
  const avisoRef = useRef<HTMLDivElement>(null)

  const sinCambios = CAMPOS_FICHA.every(({ campo }) => valores[campo] === base[campo])
  const guardando = guardar.isPending
  useEffect(() => onEstado({ sinCambios, guardando }), [onEstado, sinCambios, guardando])

  useEffect(() => {
    if (!foco) return
    if (foco.campo === 'aviso') avisoRef.current?.focus()
    else document.getElementById(idCampo(foco.campo, 'editar'))?.focus()
  }, [foco])

  function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (sinCambios || guardando) return
    const { errores: nuevos, cuerpo } = validarEmpresa(valores)
    setErrores(nuevos)
    setErrorGeneral(null)
    if (!cuerpo) {
      setFoco({ campo: (Object.keys(nuevos) as CampoEmpresa[])[0], n: Date.now() })
      return
    }
    // Las cinco claves siempre (R42): un opcional vacío viaja como null y lo quita.
    const completo = { nombre: cuerpo.nombre, direccion: cuerpo.direccion, nit: cuerpo.nit ?? null, telefono: cuerpo.telefono ?? null, correo: cuerpo.correo ?? null }
    guardar.mutate(completo, {
      onSuccess: (guardada) => {
        toast.success(`Cambios guardados en ${guardada.nombre}`)
        const nuevos = datosDeFicha(guardada)
        setBase(nuevos)
        setValores(nuevos)
        onGuardado()
      },
      onError: (e) => {
        const error = errorDeFicha(e)
        if (error.tipo === 'campo') {
          setErrores({ [error.campo]: error.mensaje })
          setFoco({ campo: error.campo, n: Date.now() })
        } else {
          setErrorGeneral(error.mensaje)
          setFoco({ campo: 'aviso', n: Date.now() })
        }
      },
    })
  }

  return (
    <form id={formId} method="post" noValidate onSubmit={alEnviar} className="flex flex-col gap-4" aria-label="Datos de la empresa">
      {errorGeneral && <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={errorGeneral} className="outline-none" />}
      <CamposFicha
        prefijo="editar"
        valores={valores}
        errores={errores}
        deshabilitado={guardando}
        onCambio={(campo, valor) => {
          setValores((anteriores) => ({ ...anteriores, [campo]: valor }))
          if (errores[campo]) {
            setErrores((anteriores) => {
              const resto = { ...anteriores }
              delete resto[campo]
              return resto
            })
          }
        }}
      />
      <p className="text-etiqueta font-normal text-muted-foreground">
        Salen en los próximos informes de la clínica. Los informes ya cerrados conservan los datos que tenían.
      </p>
    </form>
  )
}

// --- Logo -------------------------------------------------------------------------------------

function SeccionLogo({
  empresa,
  tieneLogo,
  logoInicial,
  onLogoSubido,
  onPendiente,
}: {
  empresa: { id: string; nombre: string }
  tieneLogo: boolean
  logoInicial?: LogoElegido | null
  onLogoSubido?: () => void
  onPendiente: (pendiente: boolean) => void
}) {
  const subir = useSubirLogoEmpresa(empresa.id)
  const logo = useLogoElegido(logoInicial ?? null)
  const [subido, setSubido] = useState<LogoElegido | null>(null)
  const [error, setError] = useState<ErrorLogo | null>(null)
  const pendiente = logo.elegido !== null && logo.elegido !== subido
  const accion = tieneLogo ? 'Reemplazar logo' : 'Subir logo'
  useEffect(() => onPendiente(pendiente), [onPendiente, pendiente])

  async function enviar() {
    const elegido = logo.elegido
    if (!elegido || subir.isPending) return
    setError(null)
    const listo = await prepararLogo(elegido.archivo)
    if (!listo) {
      logo.setErrorArchivo(MENSAJE_LOGO_PESADO)
      return
    }
    const reemplazo = tieneLogo
    subir.mutate(
      { id: elegido.id, archivo: listo },
      {
        onSuccess: () => {
          setSubido(elegido)
          toast.success(reemplazo ? `Logo de ${empresa.nombre} reemplazado` : `Logo de ${empresa.nombre} subido`)
          onLogoSubido?.()
        },
        onError: (e) => {
          const fallo = errorDeLogo(e)
          if (fallo.idNuevo) logo.renovarId()
          setError(fallo)
        },
      },
    )
  }

  let accionError = null
  if (error?.reintentar) {
    accionError = (
      <Boton variante="secundario" icono={<RefreshCw />} onClick={() => void enviar()} cargando={subir.isPending} textoCargando="Reintentando…">
        Reintentar
      </Boton>
    )
  } else if (error?.otroArchivo) {
    accionError = (
      <Boton variante="secundario" icono={<ImageUp />} onClick={() => document.getElementById(idElegirLogo('editar'))?.click()}>
        Elegir otra imagen
      </Boton>
    )
  }

  return (
    <section aria-labelledby="editar-logo-titulo" className="flex flex-col gap-3 border-t pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="editar-logo-titulo" className="text-cuerpo font-semibold">
          Logo
        </h3>
        {tieneLogo ? <Insignia tono="exito">Tiene logo</Insignia> : <Insignia tono="neutro">Sin logo</Insignia>}
      </div>
      <p className="text-etiqueta font-normal text-muted-foreground">
        {tieneLogo
          ? 'Aquí no se ve el logo vigente. Si subes otro, lo reemplaza en los próximos informes; los ya cerrados conservan el anterior.'
          : 'Sale arriba a la izquierda en los informes de la clínica.'}
      </p>
      <BloqueLogo
        prefijo="editar"
        archivo={logo.elegido?.archivo ?? null}
        onElegir={(archivo) => {
          setError(null)
          logo.elegir(archivo)
        }}
        onQuitar={pendiente ? logo.quitar : undefined}
        errorArchivo={logo.errorArchivo}
        deshabilitado={subir.isPending}
        vacio={
          <span className="flex items-center gap-1.5 px-2 text-center text-etiqueta font-normal text-muted-foreground">
            {tieneLogo ? <Image className="size-4 shrink-0" aria-hidden="true" /> : <ImageOff className="size-4 shrink-0" aria-hidden="true" />}
            {tieneLogo ? 'Logo vigente' : 'Sin imagen'}
          </span>
        }
        acciones={
          <Boton
            variante="fuerte"
            icono={<ImageUp />}
            disabled={!pendiente}
            cargando={subir.isPending}
            textoCargando="Subiendo logo…"
            onClick={() => void enviar()}
            className="max-sm:w-full"
          >
            {accion}
          </Boton>
        }
        aviso={error && <Aviso tono="error" titulo={error.mensaje} accion={accionError} />}
      />
    </section>
  )
}
