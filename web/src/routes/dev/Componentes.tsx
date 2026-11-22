import {
  Download,
  Lock,
  MoreHorizontal,
  Plus,
  RefreshCw,
  ScanBarcode,
  Wrench,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { useState } from 'react'

import { AssetCard } from '@/components/app/AssetCard'
import { EstadoActivoBadge } from '@/components/app/EstadoActivoBadge'
import { LocationPicker } from '@/components/app/LocationPicker'
import { NetworkStatus } from '@/components/app/NetworkStatus'
import { PendingList } from '@/components/app/PendingList'
import { Aviso, Boton, Campo, Casilla, Estado, Insignia, Interruptor, MarcoCampo, Progreso, type OpcionCampo } from '@/components/kit'
import { ACTIVOS, RESUMEN, UBICACIONES_API } from '@/mocks/datos-ficticios'

import { CampoClave, CifrasKit, DialogosKit, ImagenesKit, SeleccionKit, SuperficiesKit, TablasKit } from './GaleriaKit'

// Galería del sistema de diseño (spec 001b, T2). Ruta de desarrollo
// /dev/componentes: equivale a la página "Sistema visual" del lienzo aprobado
// (docs/08). Solo datos de ejemplo; no llama a la API.

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = `seccion-${title.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '')}`
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <h2 id={id} className="text-titulo-seccion">{title}</h2>
      {children}
    </section>
  )
}

// Spec 016, T1 (A7): la galería muestra los tokens por nombre; el valor se lee del
// CSS en tiempo de ejecución (index.css es el único archivo con literales, R1).
const PALETA: Array<{ token: string; muestra: string; uso: string }> = [
  { token: '--page', muestra: 'bg-page', uso: 'Fondo de página' },
  { token: '--card', muestra: 'bg-card', uso: 'Tarjetas, tablas, campos y diálogos' },
  { token: '--muted', muestra: 'bg-muted', uso: 'Relleno neutro, pistas' },
  { token: '--border', muestra: 'bg-border', uso: 'Bordes decorativos' },
  { token: '--input', muestra: 'bg-input', uso: 'Contorno de controles (3 : 1)' },
  { token: '--muted-foreground', muestra: 'bg-muted-foreground', uso: 'Texto secundario' },
  { token: '--foreground', muestra: 'bg-foreground', uso: 'Texto' },
  { token: '--ink', muestra: 'bg-ink', uso: 'Botón fuerte, informe congelado' },
  { token: '--primary', muestra: 'bg-primary', uso: 'Acción principal' },
  { token: '--primary-hover', muestra: 'bg-primary-hover', uso: 'Acción principal al pasar o pulsar' },
  { token: '--brand-soft', muestra: 'bg-brand-soft', uso: 'Información, selección, ítem activo' },
  { token: '--ring', muestra: 'bg-ring', uso: 'Foco: anillo de 2 px con 2 px de separación' },
  { token: '--success', muestra: 'bg-success', uso: 'Encontrado, guardado' },
  { token: '--warning', muestra: 'bg-warning', uso: 'Aviso, no confirmado' },
  { token: '--destructive', muestra: 'bg-destructive', uso: 'Error, no encontrado' },
]

function valorToken(token: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim()
}

function Muestra({ token, muestra, uso }: { token: string; muestra: string; uso: string }) {
  const [valor] = useState(() => valorToken(token))
  return (
    <li className="flex min-w-0 items-center gap-3 rounded-xl border bg-card p-3 shadow-xs">
      <span className={`size-10 shrink-0 rounded-lg border ${muestra}`} aria-hidden="true" />
      <span className="flex min-w-0 flex-col">
        <span className="truncate font-mono text-sm font-medium">{token}</span>
        <span className="truncate text-xs text-muted-foreground">{uso}</span>
        {valor && <span className="font-mono text-xs text-muted-foreground">{valor}</span>}
      </span>
    </li>
  )
}

const ESCALA: Array<{ clase: string; ejemplo: string; nota: string }> = [
  { clase: 'text-titulo-pagina', ejemplo: 'Activos', nota: '20 px / 24 px desde md · 600' },
  { clase: 'text-titulo-seccion', ejemplo: 'Por ubicación', nota: '16 px · 600' },
  { clase: 'text-cuerpo', ejemplo: 'Escanea el sticker del activo para verificarlo.', nota: '16 px / 14 px desde md · 400' },
  { clase: 'text-etiqueta', ejemplo: 'Ubicación', nota: '14 px / 13 px desde md · 500' },
  { clase: 'text-cifra', ejemplo: '$ 207.152.800', nota: '28 px / 30 px desde md · 600 · tabular-nums' },
  { clase: 'text-codigo', ejemplo: '000457', nota: '18 px / 13 px desde md · Geist Mono 500' },
]

function DemoDensidad({ densidad, titulo, nota }: { densidad: 'conteo' | 'admin'; titulo: string; nota: string }) {
  return (
    <div data-densidad={densidad} className="flex min-w-0 flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs">
      <div className="flex flex-col">
        <p className="text-titulo-seccion">{titulo}</p>
        <p className="text-etiqueta text-muted-foreground">{nota}</p>
      </div>
      <div className="flex flex-wrap gap-separacion">
        <Boton>Confirmar</Boton>
        <Boton variante="secundario">Escribir código</Boton>
      </div>
      <ul className="divide-y rounded-lg border">
        <li className="flex h-fila items-center justify-between gap-3 px-3">
          <span className="min-w-0 truncate">Silla ergonómica</span>
          <span className="font-mono text-sm text-muted-foreground">000457</span>
        </li>
        <li className="flex h-fila items-center justify-between gap-3 px-3">
          <span className="min-w-0 truncate">Impresora multifuncional</span>
          <span className="font-mono text-sm text-muted-foreground">000215</span>
        </li>
      </ul>
    </div>
  )
}

const CATEGORIAS: OpcionCampo[] = [
  { valor: 'biomedicos', etiqueta: 'Biomédicos' },
  { valor: 'mobiliario', etiqueta: 'Mobiliario' },
  { valor: 'computo', etiqueta: 'Cómputo' },
]

export default function Componentes() {
  const [ubicacion, setUbicacion] = useState('administracion')
  const [categoria, setCategoria] = useState('biomedicos')
  const [reintentando, setReintentando] = useState(false)
  const [coincide, setCoincide] = useState(true)
  const [varias, setVarias] = useState(true)
  const [fecha, setFecha] = useState('2026-11-19')
  // Demostración: «Reintentar» queda ocupado un momento, como mientras llega la respuesta.
  function reintentar() {
    setReintentando(true)
    window.setTimeout(() => setReintentando(false), 1500)
  }
  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-10 p-4 md:p-8">
      <header className="flex flex-col gap-1 border-b pb-6">
        <p className="text-xs font-medium text-muted-foreground">AssetControl · desarrollo</p>
        <h1 className="text-titulo-pagina">Sistema de diseño · Grafito y Cobalto</h1>
        <p className="text-sm text-muted-foreground">
          Componentes de shadcn/ui con el tema aprobado. Cifras con{' '}
          <span className="font-mono">tabular-nums</span>, códigos en{' '}
          <span className="font-mono">Geist Mono</span>.
        </p>
      </header>

      <Section title="Paleta">
        <p className="text-sm text-muted-foreground">
          Página en gris muy claro y todo lo que se toca en blanco. Una sola señal de acción: el cobalto.
        </p>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PALETA.map((m) => (
            <Muestra key={m.token} {...m} />
          ))}
        </ul>
      </Section>

      <Section title="Tipografía">
        <ul className="flex flex-col divide-y rounded-xl border bg-card shadow-xs">
          {ESCALA.map(({ clase, ejemplo, nota }) => (
            <li key={clase} className="flex flex-col gap-1 p-4 md:flex-row md:items-baseline md:gap-6">
              <span className="w-44 shrink-0 font-mono text-xs text-muted-foreground">{clase}</span>
              <span
                className={`min-w-0 flex-1 ${clase} ${clase === 'text-cifra' ? 'tabular-nums' : ''} ${clase === 'text-codigo' ? 'font-mono' : ''} ${clase === 'text-etiqueta' ? 'text-muted-foreground' : ''}`}
              >
                {ejemplo}
              </span>
              <span className="text-xs text-muted-foreground">{nota}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Densidad">
        <p className="text-sm text-muted-foreground">
          Un mismo componente, dos densidades: <span className="font-mono">h-control</span> y{' '}
          <span className="font-mono">h-fila</span> cambian con <span className="font-mono">data-densidad</span>.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <DemoDensidad densidad="conteo" titulo="Conteo" nota="Siempre: control 48 px, fila 56 px, separación 8 px." />
          <DemoDensidad densidad="admin" titulo="Administración" nota="Desde 768 px: control 36 px, fila 44 px. Por debajo, como el conteo." />
        </div>
      </Section>

      <Section title="Botones">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">Boton</span> del kit. Una sola acción principal por pantalla; la altura sale de la densidad.
        </p>
        <div className="flex flex-wrap items-center gap-separacion">
          <Boton>Abrir sesión</Boton>
          <Boton variante="secundario" icono={<Download />}>
            Exportar Excel
          </Boton>
          <Boton variante="fuerte">Fuerte</Boton>
          <Boton variante="fantasma">Cancelar</Boton>
          <Boton variante="peligro">Dar de baja</Boton>
          <Boton variante="secundario" soloIcono aria-label="Más acciones" icono={<MoreHorizontal />} />
          <Boton disabled>Deshabilitado</Boton>
          <Boton cargando textoCargando="Guardando…">
            Guardar
          </Boton>
        </div>
        <div data-densidad="conteo" className="flex max-w-md flex-col gap-separacion">
          <Boton variante="secundario" anchoCompleto icono={<Plus />}>
            Registrar activo nuevo
          </Boton>
          <Boton tamano="accion" anchoCompleto icono={<ScanBarcode />}>
            Escanear
          </Boton>
          <p className="text-xs text-muted-foreground">
            Conteo: acción principal de 56 px, a ancho completo y fija abajo.
          </p>
        </div>
      </Section>

      <Section title="Campos">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">Campo</span> del kit: etiqueta visible, control sobre blanco, ayuda y error enlazados.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id="g-nombre" etiqueta="Nombre" obligatorio defaultValue="Silla ergonómica" autoComplete="off" />
          <Campo id="g-precio" etiqueta="Precio de compra (COP)" tipo="dinero" obligatorio defaultValue="389.900" ayuda="Solo lo ven los administradores." />
          <Campo id="g-codigo" etiqueta="Código del sticker" tipo="codigo" defaultValue="000457" readOnly ayuda="Fijo: viene del sticker y no cambia." />
          <Campo id="g-error" etiqueta="Precio de compra (COP)" tipo="dinero" obligatorio placeholder="0" error="Escribe el precio" />
          <Campo id="g-unidades" etiqueta="Unidades iguales" tipo="numero" defaultValue="3" />
          <Campo
            id="g-categoria"
            etiqueta="Categoría"
            tipo="seleccion"
            obligatorio
            opciones={CATEGORIAS}
            valor={categoria}
            onValorChange={setCategoria}
            ayuda="Lista cerrada de la clínica."
          />
          <Campo id="g-cargando" etiqueta="Ubicación" tipo="seleccion" cargando opciones={[]} placeholder="Elige una ubicación" />
          <Campo id="g-deshabilitado" etiqueta="Serial" tipo="codigo" disabled defaultValue="SN-4471" />
          <CampoClave />
          <Campo
            id="g-fecha"
            etiqueta="Fecha de compra"
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
            ayuda="Calendario del sistema."
          />
          <Campo id="g-nota" etiqueta="Nota" tipo="area" placeholder="Opcional" className="sm:col-span-2" ayuda="Hasta 120 caracteres." />
          <Casilla etiqueta="Revisé que coincide con el sticker" etiquetaVisible marcada={coincide} onMarcadaChange={setCoincide} />
          <Interruptor etiqueta="Registrar varias unidades iguales" activo={varias} onActivoChange={setVarias} />
        </div>
      </Section>

      <Section title="Insignias">
        <div className="flex flex-wrap items-center gap-2">
          <Insignia tono="exito">Encontrado</Insignia>
          <Insignia tono="error">No encontrado</Insignia>
          <Insignia tono="aviso" icono={<Wrench aria-hidden="true" />}>
            En reparación
          </Insignia>
          <Insignia tono="aviso">Dañado</Insignia>
          <Insignia tono="info">Abierta</Insignia>
          <Insignia tono="neutro">Contador</Insignia>
          <Insignia tono="fuerte" icono={<Lock aria-hidden="true" />}>
            Informe congelado
          </Insignia>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <EstadoActivoBadge estado="activo" />
          <EstadoActivoBadge estado="en_reparacion" />
          <EstadoActivoBadge estado="dado_de_baja" />
          <Insignia tono="exito" tamano="grande">
            Verificado
          </Insignia>
          <Insignia tono="aviso" tamano="grande">
            No se pudo confirmar
          </Insignia>
        </div>
      </Section>

      <Section title="Avisos">
        <div className="grid gap-3 md:grid-cols-2">
          <Aviso tono="info" titulo="Sin sticker no hay registro">
            El código lo trae el sticker pegado al activo.
          </Aviso>
          <Aviso tono="exito" titulo="Verificado">
            Impresora multifuncional · 000215.
          </Aviso>
          <Aviso
            tono="aviso"
            titulo="No se pudo confirmar"
            accion={
              <Boton variante="secundario" icono={<RefreshCw />}>
                Reintentar
              </Boton>
            }
          >
            No sabemos si quedó guardado. Reintentar no lo duplica.
          </Aviso>
          <Aviso tono="error" titulo="La sesión se cerró" icono={<Lock aria-hidden="true" />}>
            Esta verificación no se guardó.
          </Aviso>
        </div>
      </Section>

      <Section title="Estados">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">Estado.Cargando</span>, <span className="font-mono">Estado.Vacio</span> y{' '}
          <span className="font-mono">Estado.Error</span>: el mismo aspecto en todas las pantallas.
        </p>
        <div className="grid gap-4 lg:grid-cols-3">
          <Estado.Cargando etiqueta="Cargando activos" filas={4} />
          <Estado.Vacio
            titulo="Aún no hay activos"
            descripcion="Escanea un sticker para crear el primero."
            accion={<Boton icono={<ScanBarcode />}>Ir a escanear</Boton>}
          />
          <Estado.Error onReintentar={reintentar} reintentando={reintentando} />
        </div>
      </Section>

      <CifrasKit Seccion={Section} />

      <Section title="Datos">
        <div className="flex max-w-md flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground">Progreso del conteo</p>
          <Progreso valor={60.3} etiqueta="Avance del conteo" />
          <p className="text-xs text-muted-foreground tabular-nums">
            {RESUMEN.conteoAbierto.nombre} · 132 de 219 verificados
          </p>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-muted-foreground">AssetCard · admin</p>
            <AssetCard activo={ACTIVOS[2]} rol="admin" />
          </div>
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-muted-foreground">AssetCard · contador (sin precio)</p>
            <AssetCard activo={ACTIVOS[2]} rol="contador" />
          </div>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <MarcoCampo id="g-ubicacion" etiqueta="Ubicación">
            <LocationPicker id="g-ubicacion" ubicaciones={UBICACIONES_API} valor={ubicacion} ultimaUsada="c1b2" onChange={setUbicacion} />
          </MarcoCampo>
          <div className="flex flex-wrap items-center gap-2">
            <NetworkStatus estado="en_linea" />
            <NetworkStatus estado="enviando" />
            <NetworkStatus estado="guardado" />
            <NetworkStatus estado="no_confirmado" />
            <NetworkStatus estado="sin_conexion" />
          </div>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <PendingList items={RESUMEN.conteoAbierto.pendientesPorUbicacion} />
          <Estado.Vacio
            titulo="Aún no hay activos"
            descripcion="Escanea un sticker para crear el primero."
            accion={<Boton>Registrar activo</Boton>}
          />
        </div>
      </Section>

      <Section title="Superficies">
        <p className="text-sm text-muted-foreground">
          <span className="font-mono">Panel</span>, <span className="font-mono">EncabezadoPagina</span> y{' '}
          <span className="font-mono">ListaDatos</span>: superficie blanca sobre la página, rótulo y valor; el contador no recibe hueco de precio.
        </p>
        <SuperficiesKit />
      </Section>

      <DialogosKit Seccion={Section} />

      <ImagenesKit Seccion={Section} />
      <SeleccionKit Seccion={Section} />

      <TablasKit Seccion={Section} />
    </main>
  )
}
