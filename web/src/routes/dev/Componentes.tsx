import {
  AlertTriangle,
  Check,
  CircleAlert,
  Download,
  Info,
  Lock,
  MoreHorizontal,
  Plus,
  RefreshCw,
  ScanBarcode,
  Wrench,
  X,
} from 'lucide-react'
import type { ReactNode } from 'react'

import { useState } from 'react'

import { AssetCard } from '@/components/app/AssetCard'
import { EmptyState } from '@/components/app/EmptyState'
import { LiveValueCard, ThreeFiguresCard } from '@/components/app/FigureCards'
import { LocationPicker } from '@/components/app/LocationPicker'
import { NetworkStatus } from '@/components/app/NetworkStatus'
import { PendingList } from '@/components/app/PendingList'
import { StatCard } from '@/components/app/StatCard'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ACTIVOS, RESUMEN, ULTIMO_INFORME, UBICACIONES_API } from '@/mocks/datos-ficticios'

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
        <Button className="h-control px-4">Confirmar</Button>
        <Button variant="outline" className="h-control px-4">Escribir código</Button>
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

export default function Componentes() {
  const [ubicacion, setUbicacion] = useState('administracion')
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
        <div className="flex flex-wrap items-center gap-2">
          <Button>Abrir sesión</Button>
          <Button variant="outline">
            <Download />
            Exportar Excel
          </Button>
          <Button variant="secondary">Secundario</Button>
          <Button variant="ghost">Cancelar</Button>
          <Button variant="destructive">Dar de baja</Button>
          <Button variant="link">Ver informe</Button>
          <Button variant="outline" size="icon" aria-label="Más acciones">
            <MoreHorizontal />
          </Button>
          <Button disabled>Deshabilitado</Button>
        </div>
        <div className="flex max-w-md flex-col gap-2">
          <Button variant="outline" className="h-12 text-base">
            <Plus />
            Registrar activo nuevo
          </Button>
          <Button className="h-14 text-base font-semibold">
            <ScanBarcode />
            Escanear
          </Button>
          <p className="text-xs text-muted-foreground">
            Conteo: acción principal de 56 px, a ancho completo y fija abajo.
          </p>
        </div>
      </Section>

      <Section title="Campos">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="g-nombre">Nombre</Label>
            <Input id="g-nombre" defaultValue="Silla ergonómica" />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="g-precio">Precio de compra (COP)</Label>
            <Input id="g-precio" inputMode="decimal" className="tabular-nums" defaultValue="389.900" />
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="g-codigo">Código del sticker</Label>
            <Input id="g-codigo" className="font-mono" defaultValue="000457" readOnly />
            <p className="text-xs text-muted-foreground">Fijo: viene del sticker y no cambia.</p>
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="g-error">Precio de compra (COP)</Label>
            <Input id="g-error" aria-invalid="true" aria-describedby="g-error-msg" placeholder="$ 0" />
            <p id="g-error-msg" className="flex items-center gap-1.5 text-xs text-destructive">
              <CircleAlert className="size-3.5" aria-hidden="true" />
              Escribe el precio
            </p>
          </div>
          <div className="flex min-w-0 flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="g-nota">Nota</Label>
            <Textarea id="g-nota" placeholder="Opcional" />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="g-coincide" defaultChecked />
            <Label htmlFor="g-coincide">Revisé que coincide con el sticker</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="g-varias" defaultChecked />
            <Label htmlFor="g-varias">Registrar varias unidades iguales</Label>
          </div>
        </div>
      </Section>

      <Section title="Insignias">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="success">
            <Check />
            Encontrado
          </Badge>
          <Badge variant="destructive">
            <X />
            No encontrado
          </Badge>
          <Badge variant="warning">
            <Wrench />
            En reparación
          </Badge>
          <Badge variant="warning">
            <AlertTriangle />
            Dañado
          </Badge>
          <Badge variant="brand">Abierta</Badge>
          <Badge variant="neutral">Dado de baja</Badge>
          <Badge variant="dark">
            <Lock />
            Informe congelado
          </Badge>
          <Badge variant="outline">Contador</Badge>
        </div>
      </Section>

      <Section title="Avisos">
        <div className="grid gap-3 md:grid-cols-2">
          <Alert variant="info">
            <Info />
            <AlertTitle>Sin sticker no hay registro</AlertTitle>
            <AlertDescription>El código lo trae el sticker pegado al activo.</AlertDescription>
          </Alert>
          <Alert variant="success">
            <Check />
            <AlertTitle>Verificado</AlertTitle>
            <AlertDescription>Impresora multifuncional · 000215.</AlertDescription>
          </Alert>
          <Alert variant="warning">
            <AlertTriangle />
            <AlertTitle>No se pudo confirmar</AlertTitle>
            <AlertDescription>No sabemos si quedó guardado. Reintentar no lo duplica.</AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <Lock />
            <AlertTitle>La sesión se cerró</AlertTitle>
            <AlertDescription>Esta verificación no se guardó.</AlertDescription>
          </Alert>
        </div>
      </Section>

      <Section title="Datos">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard titulo="Activos hoy" valor="219" contexto="Incluye 2 en reparación" />
          <StatCard titulo="Discrepancias" valor="3" contexto="Sin resolver" tono="aviso" />
          <StatCard titulo={RESUMEN.conteoAbierto.nombre} valor="60,3 %" contexto="132 de 219 verificados">
            <Progress value={60.3} aria-label="Avance del conteo" />
          </StatCard>
          <LiveValueCard valor={{ fuente: 'valor_actual', valor: RESUMEN.valorActual, activos: 219, consultadoA: '10:42' }} />
        </div>
        <ThreeFiguresCard
          informe={{
            fuente: 'informe_congelado',
            sesion: ULTIMO_INFORME.sesion,
            corte: ULTIMO_INFORME.corte,
            encontrado: ULTIMO_INFORME.encontrado,
            noEncontrado: ULTIMO_INFORME.noEncontrado,
            total: ULTIMO_INFORME.total,
          }}
        />
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
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="g-ubicacion">Ubicación</Label>
            <LocationPicker id="g-ubicacion" ubicaciones={UBICACIONES_API} valor={ubicacion} ultimaUsada="c1b2" onChange={setUbicacion} />
          </div>
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
          <EmptyState
            titulo="Aún no hay activos"
            descripcion="Escanea un sticker para crear el primero."
            accion={<Button>Registrar activo</Button>}
          />
        </div>
      </Section>

      <Section title="Superficies">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardDescription>Conteo nov 2026</CardDescription>
              <CardTitle className="text-3xl tabular-nums">60,3 %</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Progress value={60.3} aria-label="Avance del conteo" />
              <p className="text-xs text-muted-foreground tabular-nums">132 de 219 verificados</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardDescription>Cargando</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Skeleton className="h-8 w-40" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </CardContent>
          </Card>
        </div>
        <Tabs defaultValue="categoria">
          <TabsList>
            <TabsTrigger value="categoria">Por categoría</TabsTrigger>
            <TabsTrigger value="ubicacion">Por ubicación</TabsTrigger>
          </TabsList>
          <TabsContent value="categoria">
            <div className="overflow-x-auto rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Categoría</TableHead>
                    <TableHead className="text-right">Activos</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell className="font-medium">Biomédicos</TableCell>
                    <TableCell className="text-right tabular-nums">41</TableCell>
                    <TableCell className="text-right tabular-nums">$ 168.240.000</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell className="font-medium">Mobiliario</TableCell>
                    <TableCell className="text-right tabular-nums">96</TableCell>
                    <TableCell className="text-right tabular-nums">$ 38.912.800</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </TabsContent>
          <TabsContent value="ubicacion">
            <p className="text-sm text-muted-foreground">Mismo formato por ubicación.</p>
          </TabsContent>
        </Tabs>
        <Button variant="outline" className="self-start">
          <RefreshCw />
          Reintentar
        </Button>
      </Section>
    </main>
  )
}
