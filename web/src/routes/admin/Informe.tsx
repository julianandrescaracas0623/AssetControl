import { Download, Lock, Wrench } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { ConEstado, EncabezadoPagina } from '@/components/app/ConEstado'
import { EmptyState } from '@/components/app/EmptyState'
import { ThreeFiguresCard } from '@/components/app/FigureCards'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCOP, formatEntero } from '@/lib/format'
import { useSimulacion } from '@/lib/simulacion'
import { ULTIMO_INFORME, type FilaDesglose } from '@/mocks/datos-ficticios'

// Informe de sesión (docs/08 §7.5, CU-INF-01): tres cifras, desglose y lista
// de no encontrados congelados al cierre (R4, R9, R9a). La pantalla lee; no
// recalcula: también los totales de cada tabla vienen del servidor.

const I = ULTIMO_INFORME

function Desglose({ filas, rotulo }: { filas: FilaDesglose[]; rotulo: string }) {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table className="min-w-[680px]">
        <TableHeader>
          <TableRow>
            <TableHead className="sticky left-0 bg-background pl-4">{rotulo}</TableHead>
            <TableHead className="text-right">Encontrado</TableHead>
            <TableHead className="text-right">u.</TableHead>
            <TableHead className="text-right">No encontrado</TableHead>
            <TableHead className="text-right">u.</TableHead>
            <TableHead className="text-right">Total registrado</TableHead>
            <TableHead className="pr-4 text-right">u.</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filas.map((f) => (
            <TableRow key={f.nombre}>
              <TableCell className="sticky left-0 bg-background pl-4 font-medium">{f.nombre}</TableCell>
              <TableCell className="text-right tabular-nums">{formatCOP(f.encontrado)}</TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">{f.encontradoU}</TableCell>
              <TableCell className="text-right tabular-nums">{formatCOP(f.noEncontrado)}</TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">{f.noEncontradoU}</TableCell>
              <TableCell className="text-right font-semibold tabular-nums">{formatCOP(f.total)}</TableCell>
              <TableCell className="pr-4 text-right text-muted-foreground tabular-nums">{f.totalU}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell className="sticky left-0 bg-muted pl-4">Total</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(I.encontrado.valor)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatEntero(I.encontrado.unidades)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(I.noEncontrado.valor)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatEntero(I.noEncontrado.unidades)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatCOP(I.total.valor)}</TableCell>
            <TableCell className="pr-4 text-right tabular-nums">{formatEntero(I.total.unidades)}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  )
}

function NoEncontrados() {
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table className="min-w-[680px]">
        <TableHeader>
          <TableRow>
            <TableHead className="pl-4">Código</TableHead>
            <TableHead>Activo</TableHead>
            <TableHead>Categoría</TableHead>
            <TableHead>Ubicación esperada</TableHead>
            <TableHead>Nota al cierre</TableHead>
            <TableHead className="pr-4 text-right">Precio</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {I.noEncontrados.map((a) => (
            <TableRow key={a.codigo}>
              <TableCell className="pl-4 font-mono">{a.codigo}</TableCell>
              <TableCell className="min-w-44 font-medium whitespace-normal">{a.nombre}</TableCell>
              <TableCell>{a.categoria}</TableCell>
              <TableCell className="text-muted-foreground">{a.ubicacion}</TableCell>
              <TableCell>
                {a.enReparacion && (
                  <Badge variant="warning">
                    <Wrench aria-hidden="true" />
                    En reparación
                  </Badge>
                )}
              </TableCell>
              <TableCell className="pr-4 text-right tabular-nums">{formatCOP(a.precio)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell colSpan={5} className="pl-4">
              {I.noEncontrados.length} activos no encontrados · lista congelada al cierre
            </TableCell>
            <TableCell className="pr-4 text-right tabular-nums">{formatCOP(I.noEncontrado.valor)}</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  )
}

export default function Informe() {
  const { estado } = useSimulacion()
  const exportar = (formato: string) => () => toast(`Exportar a ${formato} llega con la spec 009, con las mismas cifras de esta pantalla`)
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        titulo={`Informe · ${I.sesion}`}
        insignia={
          <Badge variant="dark">
            <Lock aria-hidden="true" />
            Informe congelado
          </Badge>
        }
        descripcion={
          <span className="flex flex-wrap gap-x-4 gap-y-1">
            <span>Fecha de corte <b className="font-medium text-foreground tabular-nums">{I.corte}</b></span>
            <span>Cerrada <b className="font-medium text-foreground tabular-nums">{I.cerradaEn}</b></span>
            <span>Por <b className="font-medium text-foreground">{I.cerradaPor}</b></span>
            <span>Valores en COP · precio de compra al contar</span>
          </span>
        }
        acciones={
          <>
            <Button asChild variant="ghost">
              <Link to="/admin/valor">Ver valor actual</Link>
            </Button>
            <Button variant="outline" onClick={exportar('Excel')}>
              <Download />
              Exportar Excel
            </Button>
            <Button onClick={exportar('PDF')}>
              <Download />
              Exportar PDF
            </Button>
          </>
        }
      />
      <ConEstado
        estado={estado}
        etiquetaCargando="Cargando el informe"
        cargando={
          <>
            <Skeleton className="h-36 rounded-xl" />
            <Skeleton className="h-72 rounded-xl" />
          </>
        }
        vacio={
          <EmptyState
            titulo="Esta sesión sigue abierta"
            descripcion="El informe se genera al cerrar la sesión."
            accion={
              <Button asChild>
                <Link to="/admin/sesiones">Ir a la sesión</Link>
              </Button>
            }
          />
        }
      >
        <ThreeFiguresCard
          titulo="Cifras del informe"
          informe={{ fuente: 'informe_congelado', sesion: I.sesion, corte: I.corte, encontrado: I.encontrado, noEncontrado: I.noEncontrado, total: I.total }}
        />
        <p className="-mt-2 text-xs text-muted-foreground">{I.porcentajeEncontrado} % de las unidades encontradas.</p>
        <Tabs defaultValue="categoria" className="gap-4">
          <TabsList className="max-w-full overflow-x-auto">
            <TabsTrigger value="categoria">Por categoría</TabsTrigger>
            <TabsTrigger value="ubicacion">Por ubicación</TabsTrigger>
            <TabsTrigger value="no-encontrados">
              No encontrados <span className="text-xs text-muted-foreground tabular-nums">{I.noEncontrados.length}</span>
            </TabsTrigger>
          </TabsList>
          <TabsContent value="categoria">
            <Desglose filas={I.porCategoria} rotulo="Categoría" />
          </TabsContent>
          <TabsContent value="ubicacion">
            <Desglose filas={I.porUbicacion} rotulo="Ubicación (al cierre)" />
          </TabsContent>
          <TabsContent value="no-encontrados">
            <NoEncontrados />
          </TabsContent>
        </Tabs>
        <p className="max-w-3xl text-xs text-muted-foreground">
          Cifras calculadas por el servidor una sola vez al cerrar la sesión. Los cambios posteriores de precio, categoría o ubicación no
          alteran este informe. El PDF y el Excel muestran exactamente las mismas cifras.
        </p>
      </ConEstado>
    </div>
  )
}
