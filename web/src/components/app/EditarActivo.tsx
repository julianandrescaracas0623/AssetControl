import { RefreshCw } from 'lucide-react'
import { type RefObject, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { InputSugerido } from '@/components/app/InputSugerido'
import { Aviso, Boton, Campo, Dialogo, MarcoCampo } from '@/components/kit'
import type { Activo } from '@/lib/activos'
import { type CampoEdicion, camposDe, ETIQUETAS, useEdicionActivo } from '@/lib/cambiosActivo'
import { useCategorias } from '@/lib/catalogo'
import { formatCOP } from '@/lib/format'

// Editar un activo desde su ficha (spec 005, T5; CU-CAT-05). Los mismos campos del
// alta, sin el código (inmutable). Si otra persona lo cambió mientras tanto (412), se
// conserva lo escrito, se marcan los campos que cambió y se elige: guardar lo mío sobre
// la versión nueva o descartarlo. Spec 015 (T2): diálogo centrado de dos columnas (una en
// teléfono) con el cuerpo desplazable y el pie fijo, en vez del panel lateral.
// Spec 016, T8: Dialogo, Campo y Aviso del kit. El pie del diálogo envía el formulario con
// `form=`; el estado de la edición vive en un componente que se monta de nuevo cada vez que
// se abre (empieza del activo que muestra la ficha, como antes).

const FORMULARIO = 'editar-activo'

/** Clases de los controles propios (sugerencias) con la altura y el fondo del kit. */
const CONTROL = 'h-control bg-card px-3 text-base shadow-xs md:text-sm'

export function EditarActivo({
  activo,
  abierto,
  onAbierto,
  devolverFocoA,
  onCloseAutoFocus,
}: {
  activo: Activo
  abierto: boolean
  onAbierto: (v: boolean) => void
  /** A dónde vuelve el foco al cerrar (el botón que lo abrió). */
  devolverFocoA?: RefObject<HTMLElement | null>
  onCloseAutoFocus?: (evento: Event) => void
}) {
  // Cada apertura empieza de cero (antes el formulario se desmontaba al cerrar).
  const [ronda, setRonda] = useState(0)
  const [antes, setAntes] = useState(abierto)
  if (abierto !== antes) {
    setAntes(abierto)
    if (abierto) setRonda((r) => r + 1)
  }
  return (
    <Edicion
      key={ronda}
      activo={activo}
      abierto={abierto}
      onAbierto={onAbierto}
      devolverFocoA={devolverFocoA}
      onCloseAutoFocus={onCloseAutoFocus}
    />
  )
}

function valorVisible(activo: Activo, campo: CampoEdicion): string {
  if (campo === 'precio') return activo.precio_compra ? formatCOP(activo.precio_compra) : '—'
  if (campo === 'categoria') return activo.categoria.nombre
  return camposDe(activo)[campo] || 'vacío'
}

function Edicion({
  activo,
  abierto,
  onAbierto,
  devolverFocoA,
  onCloseAutoFocus,
}: {
  activo: Activo
  abierto: boolean
  onAbierto: (v: boolean) => void
  devolverFocoA?: RefObject<HTMLElement | null>
  onCloseAutoFocus?: (evento: Event) => void
}) {
  const cerrar = () => onAbierto(false)
  // Spec 016, T10 (Deuda T8 a): la respuesta de un guardado solo cierra este diálogo si
  // sigue abierto. Si se cerró con el guardado en vuelo y se abrió otra acción (Mover,
  // Dar de baja), cerrar() la cerraría a ella. El aviso «Cambios guardados» sí se muestra.
  const sigueAbierto = useRef(abierto)
  useEffect(() => {
    sigueAbierto.current = abierto
  }, [abierto])
  const edicion = useEdicionActivo(activo, (_guardado, sinCambios) => {
    toast.success(sinCambios ? 'Sin cambios que guardar' : 'Cambios guardados')
    if (sigueAbierto.current) cerrar()
  })
  return (
    <Dialogo
      abierto={abierto}
      onAbiertoChange={onAbierto}
      forma="auto"
      ancho="ancho"
      className="sm:max-w-2xl"
      devolverFocoA={devolverFocoA}
      onCloseAutoFocus={onCloseAutoFocus}
      titulo="Editar activo"
      descripcion={
        <>
          <span className="font-mono">{activo.codigo}</span> · el código del sticker no se cambia.
        </>
      }
      pie={
        <>
          <Boton variante="fantasma" onClick={cerrar}>
            Cancelar
          </Boton>
          <Boton type="submit" form={FORMULARIO} cargando={edicion.guardando} textoCargando="Guardando…">
            Guardar cambios
          </Boton>
        </>
      }
    >
      {/* Las categorías se piden al abrir, como antes (no al cargar la ficha). */}
      {abierto && <Formulario edicion={edicion} />}
    </Dialogo>
  )
}

function Formulario({ edicion }: { edicion: ReturnType<typeof useEdicionActivo> }) {
  const categorias = useCategorias()
  const { campos, errores, conflicto } = edicion
  const otro = (campo: CampoEdicion) =>
    conflicto?.cambiados.includes(campo) ? `Otra persona lo cambió a «${valorVisible(conflicto.vigente, campo)}»` : undefined
  const ayuda = (campo: CampoEdicion, normal?: string) => otro(campo) ?? normal
  const describir = (campo: CampoEdicion) => (errores[campo] ? `${campo}-error` : otro(campo) ? `${campo}-ayuda` : undefined)

  return (
    <form
      id={FORMULARIO}
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(evento) => {
        evento.preventDefault()
        edicion.guardar()
      }}
    >
      {conflicto && (
        <Aviso
          tono="aviso"
          titulo="Alguien cambió este activo mientras editabas"
          accion={
            <>
              <Boton type="submit" variante="secundario" disabled={edicion.guardando}>
                Guardar mis cambios
              </Boton>
              <Boton variante="secundario" onClick={edicion.descartar}>
                Descartar los míos
              </Boton>
            </>
          }
        >
          {conflicto.cambiados.length > 0
            ? `Cambió: ${conflicto.cambiados.map((c) => ETIQUETAS[c].toLowerCase()).join(', ')}. Tus datos siguen aquí.`
            : 'Cambió su estado o su ubicación. Tus datos siguen aquí.'}
        </Aviso>
      )}
      {edicion.errorGeneral && (
        <Aviso
          tono="error"
          titulo="No se guardó"
          accion={
            edicion.errorGeneral.reintentable && (
              <Boton type="submit" variante="secundario" icono={<RefreshCw />}>
                Reintentar
              </Boton>
            )
          }
        >
          {edicion.errorGeneral.mensaje}
        </Aviso>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <MarcoCampo id="nombre" etiqueta="Nombre" obligatorio error={errores.nombre} ayuda={ayuda('nombre')}>
          <InputSugerido
            campo="nombre"
            id="nombre"
            value={campos.nombre}
            onChange={(e) => edicion.cambiar('nombre', e.target.value)}
            maxLength={120}
            autoComplete="off"
            aria-required
            aria-invalid={errores.nombre ? true : undefined}
            aria-describedby={describir('nombre')}
            className={CONTROL}
          />
        </MarcoCampo>
        <Campo
          id="precio"
          tipo="dinero"
          etiqueta="Precio de compra (COP)"
          obligatorio
          error={errores.precio}
          ayuda={ayuda('precio', 'Cambiarlo deja el antes y el después en el historial.')}
          value={campos.precio}
          onChange={(e) => edicion.cambiar('precio', e.target.value)}
          autoComplete="off"
        />
        <Campo
          id="categoria"
          tipo="seleccion"
          etiqueta="Categoría"
          obligatorio
          ayuda={ayuda('categoria')}
          opciones={(categorias.data ?? []).map((c) => ({ valor: c.id, etiqueta: c.nombre }))}
          valor={campos.categoria}
          onValorChange={(v) => edicion.cambiar('categoria', v)}
          cargando={categorias.isPending}
          placeholder="Elige una categoría"
        />
        <Campo
          id="serial"
          tipo="codigo"
          etiqueta="Serial"
          ayuda={ayuda('serial')}
          value={campos.serial}
          onChange={(e) => edicion.cambiar('serial', e.target.value)}
          maxLength={120}
          autoComplete="off"
        />
        {(['marca', 'modelo', 'subtipo'] as const).map((campo) => (
          <MarcoCampo key={campo} id={campo} etiqueta={ETIQUETAS[campo]} ayuda={ayuda(campo)}>
            <InputSugerido
              campo={campo}
              id={campo}
              value={campos[campo]}
              onChange={(e) => edicion.cambiar(campo, e.target.value)}
              maxLength={120}
              autoComplete="off"
              aria-describedby={describir(campo)}
              className={CONTROL}
            />
          </MarcoCampo>
        ))}
        <Campo
          id="fecha"
          type="date"
          etiqueta="Fecha de compra"
          error={errores.fecha}
          ayuda={ayuda('fecha')}
          value={campos.fecha}
          onChange={(e) => edicion.cambiar('fecha', e.target.value)}
        />
      </div>
    </form>
  )
}
