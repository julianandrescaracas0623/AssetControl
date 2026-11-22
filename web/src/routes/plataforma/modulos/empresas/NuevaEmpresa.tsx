import { ArrowLeft, Building2, CircleCheck, Image, KeyRound, Pencil, Plus, UserRound } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { CampoContrasena, POLITICA_CONTRASENA } from '@/components/app/CampoContrasena'
import { Aviso, Boton, Campo, EncabezadoPagina, Panel } from '@/components/kit'
import { ErrorApi } from '@/lib/api/cliente'
import { apiPlataforma } from '@/lib/api/plataforma'

import { useApiPlataforma } from '../../sesion'
import {
  type CampoAlta,
  type DatosAdmin,
  type DatosFicha,
  errorDeAlta,
  errorDeLogo,
  type ErroresAlta,
  FICHA_VACIA,
  idCampo,
  idElegirLogo,
  type LogoElegido,
  MENSAJE_LOGO_PESADO,
  nombreRepetido,
  prepararLogo,
  useEmpresas,
  useLogoElegido,
  validarAlta,
} from './api'
import { BloqueLogo } from './BloqueLogo'
import { CamposFicha } from './CamposFicha'
import { EditarEmpresa } from './EditarEmpresa'

// /plataforma/empresas/nueva (spec 017, T9 y C1c/T14; R16–R20, R23, R24, R39, R46; CU-03, CU-04).
// Un solo formulario: ficha de la empresa, logo opcional y primer admin; un solo «Crear empresa»
// y un solo estado de envío. Sin pasos ni barra de progreso (C1c, decisión del humano).
// - La contraseña no vive en estado de React, caché de consultas, URL ni almacenamiento: los dos
//   campos son no controlados, se leen del formulario al enviar y se vacían en cuanto responde
//   el servidor (con éxito o con error; R39). Sin useMutation (guardaría el cuerpo en
//   `variables`). El `id` de la empresa (UUID) nace al abrir el formulario y se repite en cada
//   reintento: un doble envío no crea dos empresas (409 empresa_existente, R20).
// - Al crearse la empresa (201, o 409 empresa_existente: ya la creó un envío anterior), si se
//   eligió un logo se sube en una segunda llamada `multipart` (solo `logo_id` y el archivo; la
//   contraseña nunca va ahí), con el `logo_id` nacido al elegir el archivo.
// - Si el logo falla, la empresa ya existe y no se deshace: el formulario se cambia por el aviso
//   «Empresa creada; el logo no se pudo subir» con el motivo; el reintento es desde «Editar
//   empresa». El formulario ya no existe, así que el POST de creación no se vuelve a llamar.

const RUTA_LISTA = '/plataforma/empresas'
const AVISO_CAMBIO = 'El admin deberá cambiar esta contraseña al entrar.'
const AVISO_PRIMER_ENVIO =
  'La empresa se creó con un envío anterior: el nombre y el correo son los de ese primer envío, aunque los hayas cambiado después. La contraseña válida es la de ese primer envío; si no la tienes, el admin puede usar «¿Olvidaste tu contraseña?» en el inicio de sesión.'

type EmpresaNueva = { id: string; nombre: string; adminEmail: string }
type Resultado = {
  empresa: EmpresaNueva
  /** 409 empresa_existente: la creó un envío anterior (D18). */
  existente: boolean
  logo: 'sin_logo' | 'subido' | { fallo: string; elegido: LogoElegido }
}

/** Recibe el foco al aparecer (el lector anuncia el resultado). */
function useFocoAlMontar<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => ref.current?.focus(), [])
  return ref
}

// --- Formulario -------------------------------------------------------------------------------

function Formulario({ empresaId, onTerminado }: { empresaId: string; onTerminado: (resultado: Resultado) => void }) {
  const conToken = useApiPlataforma()
  const empresas = useEmpresas()
  const logo = useLogoElegido()
  const [ficha, setFicha] = useState<DatosFicha>(FICHA_VACIA)
  const [admin, setAdmin] = useState<DatosAdmin>({ nombre: '', email: '' })
  const [errores, setErrores] = useState<ErroresAlta>({})
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [clavesBorradas, setClavesBorradas] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const enCurso = useRef(false)
  // D18: nombre y correo del primer envío que pudo crear la empresa (nunca la contraseña).
  // Si luego llega `409 empresa_existente`, la empresa es la de ese envío, no la del formulario
  // actual. Un envío que el servidor rechazó (4xx) no creó nada y deja de contar.
  const primerEnvio = useRef<EmpresaNueva | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const avisoRef = useRef<HTMLDivElement>(null)
  const [foco, setFoco] = useState<{ campo: CampoAlta | 'aviso' | 'logo'; n: number } | null>(null)

  // Foco al primer error (o al aviso general): el lector lo anuncia y se corrige sin buscarlo.
  useEffect(() => {
    if (!foco) return
    if (foco.campo === 'aviso') avisoRef.current?.focus()
    else if (foco.campo === 'logo') document.getElementById(idElegirLogo('alta'))?.focus()
    else document.getElementById(idCampo(foco.campo))?.focus()
  }, [foco])

  function quitarError(campo: CampoAlta) {
    if (!errores[campo]) return
    setErrores((anteriores) => {
      const resto = { ...anteriores }
      delete resto[campo]
      return resto
    })
  }

  /** R39: las contraseñas se borran del formulario en cuanto el servidor responde. */
  function borrarClaves() {
    const form = formRef.current
    if (!form) return
    for (const nombre of ['password', 'password_confirmacion']) {
      const campo = form.elements.namedItem(nombre)
      if (campo instanceof HTMLInputElement) campo.value = ''
    }
  }

  /** Segunda llamada (multipart): solo el logo, con la empresa ya creada. */
  async function subirLogo(empresa: EmpresaNueva, existente: boolean, elegido: LogoElegido | null, listo: Blob | null) {
    if (!elegido || !listo) return onTerminado({ empresa, existente, logo: 'sin_logo' })
    try {
      await conToken((t) => apiPlataforma.subirLogoEmpresa(t, empresa.id, { id: elegido.id, archivo: listo }))
      onTerminado({ empresa, existente, logo: 'subido' })
    } catch (e) {
      const fallo = errorDeLogo(e)
      const siguiente = fallo.idNuevo ? { ...elegido, id: crypto.randomUUID() } : elegido
      onTerminado({ empresa, existente, logo: { fallo: fallo.mensaje, elegido: siguiente } })
    }
  }

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    if (enCurso.current) return
    const datos = new FormData(evento.currentTarget)
    const validado = validarAlta(ficha, admin, String(datos.get('password') ?? ''), String(datos.get('password_confirmacion') ?? ''))
    setErrorGeneral(null)
    setErrores(validado.errores)
    if (!validado.ficha || !validado.admin) {
      const primero = (Object.keys(validado.errores) as CampoAlta[])[0]
      setFoco({ campo: primero, n: Date.now() })
      return
    }
    enCurso.current = true
    setEnviando(true)
    // El logo se prepara antes de crear: un archivo que no cabe se dice aquí, sin crear nada.
    const elegido = logo.elegido
    const listo = elegido ? await prepararLogo(elegido.archivo) : null
    if (elegido && !listo) {
      enCurso.current = false
      setEnviando(false)
      logo.setErrorArchivo(MENSAJE_LOGO_PESADO)
      setFoco({ campo: 'logo', n: Date.now() })
      return
    }
    const { ficha: datosFicha, admin: datosAdmin } = validado
    const envio: EmpresaNueva = { id: empresaId, nombre: datosFicha.nombre, adminEmail: datosAdmin.email }
    primerEnvio.current ??= envio
    try {
      // El cuerpo (con la contraseña) existe solo durante esta llamada.
      await conToken((t) =>
        apiPlataforma.crearEmpresa(t, {
          id: empresaId,
          ...datosFicha,
          admin: {
            nombre: datosAdmin.nombre,
            email: datosAdmin.email,
            password: String(datos.get('password') ?? ''),
            password_confirmacion: String(datos.get('password_confirmacion') ?? ''),
          },
        }),
      )
    } catch (e) {
      borrarClaves()
      datos.delete('password')
      datos.delete('password_confirmacion')
      if (e instanceof ErrorApi && e.code === 'empresa_existente') {
        // Ya la creó un envío anterior con este mismo id: no se recrea; se sigue con el logo.
        void empresas.refetch()
        await subirLogo(primerEnvio.current ?? envio, true, elegido, listo)
        return
      }
      setClavesBorradas(true)
      enCurso.current = false
      setEnviando(false)
      // Una respuesta 4xx de la API = el servidor rechazó ese envío y no creó nada.
      const rechazado = e instanceof ErrorApi && e.status >= 400 && e.status < 500 && e.code !== 'sin_conexion'
      if (rechazado && primerEnvio.current === envio) primerEnvio.current = null
      const error = errorDeAlta(e)
      if (error.tipo === 'campo') {
        setErrores({ [error.campo]: error.mensaje })
        setFoco({ campo: error.campo, n: Date.now() })
      } else {
        setErrorGeneral(error.mensaje)
        setFoco({ campo: 'aviso', n: Date.now() })
      }
      return
    }
    // 201: la empresa existe. Las contraseñas salen del formulario antes de subir el logo.
    borrarClaves()
    datos.delete('password')
    datos.delete('password_confirmacion')
    void empresas.refetch()
    await subirLogo(envio, false, elegido, listo)
  }

  const repetido = nombreRepetido(empresas.data, ficha.nombre)

  return (
    <form
      ref={formRef}
      // Defensa en profundidad (D20): un envío nativo nunca pone la contraseña en la URL.
      method="post"
      className="flex flex-col gap-6"
      onSubmit={alEnviar}
      // Las contraseñas no son controladas (no pasan por el estado): al escribir en ellas solo
      // se quita su error, sin leer el valor.
      onInput={(e) => {
        const nombre = (e.target as HTMLInputElement).name
        if (nombre === 'password') quitarError('admin.password')
        if (nombre === 'password' || nombre === 'password_confirmacion') quitarError('admin.password_confirmacion')
      }}
      noValidate
      aria-label="Nueva empresa"
    >
      {errorGeneral && <Aviso ref={avisoRef} tabIndex={-1} tono="error" titulo={errorGeneral} className="outline-none" />}
      <Panel
        titulo={
          <span className="inline-flex items-center gap-2">
            <Building2 className="size-4 text-muted-foreground" aria-hidden="true" />
            Datos de la empresa
          </span>
        }
        descripcion="Salen en los informes de la clínica. Su admin podrá cambiarlos después."
      >
        <CamposFicha
          prefijo="alta"
          valores={ficha}
          errores={errores}
          focoInicial
          ayudaNombre={repetido ? 'Ya existe una empresa con ese nombre. Puedes crearla igual si es otra.' : undefined}
          onCambio={(campo, valor) => {
            setFicha((anteriores) => ({ ...anteriores, [campo]: valor }))
            quitarError(campo)
          }}
        />
      </Panel>
      <Panel
        titulo={
          <span className="inline-flex items-center gap-2">
            <Image className="size-4 text-muted-foreground" aria-hidden="true" />
            Logo (opcional)
          </span>
        }
        descripcion="Sale arriba a la izquierda en los informes. Si no lo tienes ahora, se sube después desde Editar empresa o lo sube su admin."
      >
        <BloqueLogo
          prefijo="alta"
          archivo={logo.elegido?.archivo ?? null}
          onElegir={logo.elegir}
          onQuitar={logo.quitar}
          errorArchivo={logo.errorArchivo}
          deshabilitado={enviando}
        />
      </Panel>
      <Panel
        titulo={
          <span className="inline-flex items-center gap-2">
            <UserRound className="size-4 text-muted-foreground" aria-hidden="true" />
            Primer admin
          </span>
        }
        descripcion="Se crea con la empresa, sin invitación. Entrégale su correo y la contraseña por tu propio medio."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo
            id={idCampo('admin.nombre')}
            etiqueta="Nombre"
            obligatorio
            error={errores['admin.nombre']}
            name="admin_nombre"
            value={admin.nombre}
            maxLength={120}
            required
            autoComplete="off"
            onChange={(e) => {
              const valor = e.target.value
              setAdmin((a) => ({ ...a, nombre: valor }))
              quitarError('admin.nombre')
            }}
          />
          <Campo
            id={idCampo('admin.email')}
            etiqueta="Correo"
            obligatorio
            error={errores['admin.email']}
            ayuda="Con él entrará. Debe ser un correo que nadie use en AssetControl."
            name="admin_email"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            spellCheck={false}
            value={admin.email}
            maxLength={254}
            required
            autoComplete="off"
            onChange={(e) => {
              const valor = e.target.value
              setAdmin((a) => ({ ...a, email: valor }))
              quitarError('admin.email')
            }}
          />
          <CampoContrasena
            id={idCampo('admin.password')}
            etiqueta="Contraseña"
            name="password"
            queMostrar="la contraseña"
            ayuda={POLITICA_CONTRASENA}
            error={errores['admin.password']}
          />
          <CampoContrasena
            id={idCampo('admin.password_confirmacion')}
            etiqueta="Confirmar contraseña"
            name="password_confirmacion"
            queMostrar="la confirmación"
            error={errores['admin.password_confirmacion']}
          />
        </div>
        <div className="mt-4 flex flex-col gap-3">
          {clavesBorradas && (
            <Aviso tono="info" titulo="Por seguridad, la contraseña se borró al enviar. Escríbela de nuevo en los dos campos." />
          )}
          <Aviso tono="info" icono={<KeyRound aria-hidden="true" />} titulo={AVISO_CAMBIO}>
            No se vuelve a mostrar. Si se pierde, define otra desde Usuarios.
          </Aviso>
        </div>
      </Panel>
      <div className="flex flex-col-reverse gap-separacion sm:flex-row sm:justify-end">
        <Boton variante="secundario" asChild className="max-sm:w-full">
          <Link to={RUTA_LISTA}>Cancelar</Link>
        </Boton>
        <Boton type="submit" icono={<Plus />} cargando={enviando} textoCargando="Creando empresa…" className="max-sm:w-full">
          Crear empresa
        </Boton>
      </div>
    </form>
  )
}

// --- Resultado --------------------------------------------------------------------------------

function DatosParaElAdmin({ empresa, conLogo }: { empresa: EmpresaNueva; conLogo: boolean }) {
  return (
    <>
      <p className="text-cuerpo text-muted-foreground">
        {empresa.nombre} ya está activa{conLogo ? ' y con su logo' : ', sin logo por ahora'}. Entrega al admin su correo (
        <span className="font-medium text-foreground">{empresa.adminEmail}</span>) y la contraseña por tu propio medio.
      </p>
      <p className="text-cuerpo font-medium">{AVISO_CAMBIO}</p>
    </>
  )
}

function EmpresaLista({ resultado, onOtra }: { resultado: Resultado; onOtra: () => void }) {
  const titulo = useFocoAlMontar<HTMLHeadingElement>()
  const { empresa, existente } = resultado
  return (
    <Panel>
      <div className="flex flex-col items-center gap-4 py-6 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-success-soft text-success" aria-hidden="true">
          <CircleCheck className="size-6" />
        </span>
        <div className="flex max-w-md flex-col gap-1">
          <h2 ref={titulo} tabIndex={-1} className="text-titulo-seccion outline-none">
            Empresa lista
          </h2>
          <DatosParaElAdmin empresa={empresa} conLogo={resultado.logo === 'subido'} />
          {existente && <p className="text-etiqueta text-muted-foreground">(el correo es el del primer envío)</p>}
        </div>
        {existente && (
          <Aviso tono="aviso" titulo="Esta empresa ya se había creado" className="max-w-xl text-left">
            {AVISO_PRIMER_ENVIO}
          </Aviso>
        )}
        <div className="flex w-full flex-col-reverse gap-separacion sm:w-auto sm:flex-row">
          <Boton variante="secundario" icono={<Plus />} onClick={onOtra} className="max-sm:w-full">
            Crear otra empresa
          </Boton>
          <Boton icono={<ArrowLeft />} asChild className="max-sm:w-full">
            <Link to={RUTA_LISTA}>Volver a empresas</Link>
          </Boton>
        </div>
      </div>
    </Panel>
  )
}

function LogoFallido({ resultado, motivo, onEditar }: { resultado: Resultado; motivo: string; onEditar: () => void }) {
  const aviso = useFocoAlMontar<HTMLDivElement>()
  const navigate = useNavigate()
  const { empresa, existente } = resultado
  return (
    <div className="flex flex-col gap-4">
      <Aviso
        ref={aviso}
        tabIndex={-1}
        tono="aviso"
        titulo="Empresa creada; el logo no se pudo subir"
        className="outline-none"
        accion={
          <>
            <Boton variante="secundario" icono={<Pencil />} onClick={onEditar} className="max-sm:w-full">
              Editar empresa
            </Boton>
            {/* Botón y no enlace: dentro de un Aviso los enlaces van subrayados (ui/alert). */}
            <Boton icono={<ArrowLeft />} onClick={() => navigate(RUTA_LISTA)} className="max-sm:w-full">
              Volver a empresas
            </Boton>
          </>
        }
      >
        {motivo} La empresa y su admin ya existen y no hay que volver a crearlos. Puedes subirlo desde «Editar empresa»; también lo
        puede subir su admin desde su pantalla Empresa.
      </Aviso>
      <Panel titulo="Datos para el admin">
        <div className="flex flex-col gap-1">
          <DatosParaElAdmin empresa={empresa} conLogo={false} />
          {existente && <p className="text-etiqueta text-muted-foreground">{AVISO_PRIMER_ENVIO}</p>}
        </div>
      </Panel>
    </div>
  )
}

export default function NuevaEmpresa() {
  // Un `id` por formulario: «Crear otra empresa» monta uno nuevo (con su propio id).
  const [intento, setIntento] = useState(0)
  return <Alta key={intento} onOtra={() => setIntento((n) => n + 1)} />
}

function Alta({ onOtra }: { onOtra: () => void }) {
  const [empresaId] = useState(() => crypto.randomUUID())
  const [resultado, setResultado] = useState<Resultado | null>(null)
  const [editando, setEditando] = useState(false)
  const subidoAlEditar = useRef(false)
  const fallo = resultado && typeof resultado.logo === 'object' ? resultado.logo : null

  let contenido
  if (!resultado) contenido = <Formulario empresaId={empresaId} onTerminado={setResultado} />
  else if (fallo) contenido = <LogoFallido resultado={resultado} motivo={fallo.fallo} onEditar={() => setEditando(true)} />
  else contenido = <EmpresaLista resultado={resultado} onOtra={onOtra} />

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <EncabezadoPagina
        titulo="Nueva empresa"
        migas={[{ etiqueta: 'Empresas', href: RUTA_LISTA }, { etiqueta: 'Nueva empresa' }]}
        descripcion={resultado ? undefined : 'La clínica, su logo si lo tienes y su primer admin, en un solo paso.'}
      />
      {contenido}
      {editando && resultado && (
        <EditarEmpresa
          empresa={{ id: resultado.empresa.id, nombre: resultado.empresa.nombre }}
          logoInicial={fallo?.elegido ?? null}
          onLogoSubido={() => {
            subidoAlEditar.current = true
          }}
          onCerrar={() => {
            setEditando(false)
            // Al cerrar (no antes: el diálogo tiene el foco), el resultado pasa a «Empresa lista».
            if (subidoAlEditar.current) setResultado((actual) => actual && { ...actual, logo: 'subido' })
          }}
        />
      )}
    </div>
  )
}
