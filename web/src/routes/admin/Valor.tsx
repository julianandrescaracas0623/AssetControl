import { CircleAlert, Package, RefreshCw, Wrench } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'

import { EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { mensajeDeError } from '@/lib/api/cliente'
import { formatCOP, formatEntero, formatUnidades } from '@/lib/format'
import { type FilaValor, type ValorEnVivo, useValorActual } from '@/lib/informe'

// Valor actual del inventario (spec 008, T6; R8 de la spec, R7 de docs/03; CU-INF-02):
// suma en vivo de los activos vigentes (activos y en reparación; los dados de baja no).
// No es un informe: sigue cada cambio y nunca se mezcla con las cifras congeladas de un
// cierre (R10). Todo llega calculado del servidor.

const hora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })

function Cifras({ valor }: { valor: ValorEnVivo }) {
  const tituloId = useId()
  return (
    <section aria-labelledby={tituloId} className="rounded-xl border">
      <div className="flex flex-wrap items-center gap-2 border-b px-5 py-4">
        <h2 id={tituloId} className="font-semibold">
          Valor actual <span className="sr-only">· tiempo real, no es un informe</span>
        </h2>
        <Badge variant="brand">Tiempo real</Badge>
        <span className="text-xs text-muted-foreground">No es un informe</span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        <div className="flex min-w-0 flex-col gap-1 px-5 py-4">
          <span className="text-xs font-medium text-muted-foreground">Total vigente</span>
          <span className="truncate text-2xl font-semibold tracking-tight tabular-nums">{formatCOP(valor.total)}</span>
          <span className="text-xs text-muted-foreground tabular-nums">{formatUnidades(valor.unidades)}</span>
        </div>
        <div className="flex min-w-0 flex-col gap-1 border-t px-5 py-4 sm:border-t-0 sm:border-l">
          <span className="flex items-center gap-1.5 text-xs font-medium text-warning">
            <Wrench className="size-3.5" aria-hidden="true" />
            En reparación (incluido)
          </span>
          <span className="truncate text-2xl font-semibold tracking-tight tabular-nums">{formatCOP(valor.en_reparacion.valor)}</span>
          <span className="text-xs text-muted-foreground tabular-nums">{formatUnidades(valor.en_reparacion.unidades)}</span>
        </div>
      </div>
    </section>
  )
}

function Tabla({ filas, rotulo, valor }: { filas: FilaValor[]; rotulo: string; valor: ValorEnVivo }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">{rotulo}</TableHead>
            <TableHead className="text-right">Valor</TableHead>
            <TableHead className="pr-4 text-right">Unidades</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filas.map((f) => (
            <TableRow key={f.id}>
              <TableCell className="pl-4 font-medium whitespace-normal">{f.etiqueta}</TableCell>
              <TableCell className="text-right tabular-nums">{formatCOP(f.valor)}</TableCell>
              <TableCell className="pr-4 text-right tabular-nums">{formatEntero(f.unidades)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell className="pl-4">Total</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(valor.total)}</TableCell>
            <TableCell className="pr-4 text-right tabular-nums">{formatEntero(valor.unidades)}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  )
}

export default function Valor() {
  const consulta = useValorActual()
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <EncabezadoPagina
        titulo="Valor actual"
        descripcion={
          consulta.isSuccess
            ? `Suma en vivo del precio de compra de los activos vigentes · calculado ${hora.format(new Date(consulta.data.calculado_en))}`
            : 'Suma en vivo del precio de compra de los activos vigentes.'
        }
        acciones={
          <Button variant="outline" disabled={consulta.isFetching} onClick={() => void consulta.refetch()}>
            <RefreshCw className={consulta.isFetching ? 'animate-spin' : undefined} />
            Actualizar
          </Button>
        }
      />
      {consulta.isPending ? (
        <div role="status" aria-label="Calculando el valor actual" className="flex flex-col gap-4">
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : consulta.isError ? (
        <Alert variant="destructive" className="items-start">
          <CircleAlert />
          <AlertTitle>No se pudo calcular el valor actual</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {mensajeDeError(consulta.error)}
            <Button variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void consulta.refetch()}>
              <RefreshCw />
              Reintentar
            </Button>
          </AlertDescription>
        </Alert>
      ) : consulta.data.unidades === 0 ? (
        <EmptyState
          icono={<Package className="size-5" />}
          titulo="Aún no hay activos vigentes"
          descripcion="Cuando registres activos, aquí verás cuánto vale el inventario hoy."
          accion={
            <Button asChild>
              <Link to="/admin/activos/nuevo">Registrar activo</Link>
            </Button>
          }
        />
      ) : (
        <>
          <Cifras valor={consulta.data} />
          <Tabs defaultValue="categoria" className="gap-4">
            <TabsList className="max-w-full overflow-x-auto">
              <TabsTrigger value="categoria">Por categoría</TabsTrigger>
              <TabsTrigger value="ubicacion">Por ubicación</TabsTrigger>
            </TabsList>
            <TabsContent value="categoria">
              <Tabla filas={consulta.data.por_categoria} rotulo="Categoría" valor={consulta.data} />
            </TabsContent>
            <TabsContent value="ubicacion">
              <Tabla filas={consulta.data.por_ubicacion} rotulo="Ubicación" valor={consulta.data} />
            </TabsContent>
          </Tabs>
        </>
      )}
      <p className="max-w-3xl text-xs text-muted-foreground">
        Cuentan los activos «activo» y «en reparación»; los dados de baja no. Cambia en cuanto se corrige un precio, se mueve o se da de baja un activo.
        Las cifras de un conteo están en el informe de su sesión, congeladas al cierre.{' '}
        <Link to="/admin/sesiones" className="font-medium text-foreground underline-offset-4 hover:underline">
          Ver sesiones
        </Link>
      </p>
    </div>
  )
}
