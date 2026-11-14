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

// Galería del sistema de diseño (spec 001b, T2). Ruta de desarrollo
// /dev/componentes: equivale a la página "Sistema visual" del lienzo aprobado
// (docs/08). Solo datos de ejemplo; no llama a la API.

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  )
}

export default function Componentes() {
  return (
    <main className="mx-auto flex w-full max-w-[1320px] flex-col gap-10 p-4 md:p-8">
      <header className="flex flex-col gap-1 border-b pb-6">
        <p className="text-xs font-medium text-muted-foreground">AssetControl · desarrollo</p>
        <h1 className="text-2xl font-semibold tracking-tight">Sistema de diseño · Grafito y Cobalto</h1>
        <p className="text-sm text-muted-foreground">
          Componentes de shadcn/ui con el tema aprobado. Cifras con{' '}
          <span className="font-mono">tabular-nums</span>, códigos en{' '}
          <span className="font-mono">Geist Mono</span>.
        </p>
      </header>

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
