import { Check, ChevronDown, CircleAlert, Info, RefreshCw, X } from 'lucide-react'
import { type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'

import { CopiarDeParecido } from '@/components/app/CopiarDeParecido'
import { CountShell } from '@/components/app/CountShell'
import { LocationPicker } from '@/components/app/LocationPicker'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { type ErroresAlta, useAltaActivo } from '@/lib/altaActivo'
import { useCategorias, useUbicaciones } from '@/lib/catalogo'
import { useRol } from '@/lib/sesion'

// Alta por escaneo (docs/08 §7.3, CU-CAT-02/03) a 375 px, en una columna (spec 004,
// T6). El código llega del sticker y es fijo. Obligatorios: nombre, precio, categoría
// y ubicación. El contador escribe el precio y después no lo ve; si copia de un
// parecido, el servidor copia el precio sin mostrarlo (P13, Q3).

function Campo({ id, etiqueta, error, ayuda, children }: { id: string; etiqueta: ReactNode; error?: string; ayuda?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className="text-[15px]">{etiqueta}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-center gap-1.5 text-sm text-destructive">
          <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        ayuda && <p id={`${id}-ayuda`} className="text-sm text-muted-foreground">{ayuda}</p>
      )}
    </div>
  )
}

const Obligatorio = () => <span className="text-destructive" aria-hidden="true">*</span>
const aria = (errores: ErroresAlta, campo: keyof ErroresAlta, ayuda = false) => ({
  'aria-invalid': errores[campo] ? true : undefined,
  'aria-describedby': errores[campo] ? `${campo}-error` : ayuda ? `${campo}-ayuda` : undefined,
})

export default function Alta() {
  const [params] = useSearchParams()
  const rol = useRol()
  const codigo = (params.get('codigo') ?? '').trim().toUpperCase()
  const alta = useAltaActivo({ rol, codigoInicial: codigo, ubicacionInicial: params.get('ubicacion') ?? '' })
  const categorias = useCategorias()
  const ubicaciones = useUbicaciones()
  const { campos, errores, copiado, duplicando } = alta

  if (alta.creado) {
    return (
      <CountShell titulo="Registrar activo" volver="/contar" estadoRed="guardado"
        acciones={
          <Button asChild className="min-h-14 font-semibold">
            <Link to="/contar/escanear">Escanear otro</Link>
          </Button>
        }
      >
        <h1 className="sr-only">Registrar activo</h1>
        <Alert variant="success">
          <Check />
          <AlertTitle>Activo creado</AlertTitle>
          <AlertDescription>
            {alta.creado.nombre} · <span className="font-mono">{alta.creado.codigo}</span> quedó registrado en{' '}
            {alta.creado.ubicacion.ruta}.
          </AlertDescription>
        </Alert>
      </CountShell>
    )
  }

  return (
    <CountShell
      titulo="Registrar activo"
      volver="/contar/escribir"
      estadoRed="en_linea"
      acciones={
        <Button type="submit" form="alta" className="min-h-14 font-semibold" disabled={alta.guardando}>
          {alta.guardando ? 'Guardando…' : 'Guardar activo'}
        </Button>
      }
    >
      <h1 className="sr-only">Registrar activo</h1>
      <form
        id="alta"
        noValidate
        onSubmit={(evento) => {
          evento.preventDefault()
          alta.enviar()
        }}
        className="flex flex-col gap-4"
      >
        {alta.errorGeneral && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertTitle>No se guardó</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-3">
              {alta.errorGeneral.mensaje}
              {alta.errorGeneral.reintentable && (
                <Button type="submit" variant="outline" className="min-h-11">
                  <RefreshCw />
                  Reintentar
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}
        {alta.existente && (
          <Alert variant="warning">
            <Info />
            <AlertTitle>Ese código ya está registrado</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-3">
              Es {alta.existente.nombre}. Ábrelo en vez de crear otro.
              <Button asChild variant="outline" className="min-h-11">
                <Link to={`/contar/activo/${encodeURIComponent(alta.existente.codigo)}`}>Abrir activo</Link>
              </Button>
            </AlertDescription>
          </Alert>
        )}
        <div className="flex items-center gap-3 rounded-xl border bg-muted/50 px-3 py-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs text-muted-foreground">Código del sticker · nuevo</p>
            <p className="font-mono text-lg tracking-wider break-all">{codigo || '—'}</p>
          </div>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <Checkbox checked={alta.confirmado} onCheckedChange={(v) => alta.setConfirmado(v === true)} {...aria(errores, 'confirmado')} />
            Coincide
          </label>
        </div>
        {(errores.confirmado || errores.codigo) && (
          <p id={errores.confirmado ? 'confirmado-error' : 'codigo-error'} className="-mt-2 flex items-center gap-1.5 text-sm text-destructive">
            <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
            {errores.confirmado ?? errores.codigo}
          </p>
        )}
        <CopiarDeParecido onCopiar={alta.copiar} copiado={copiado} className="h-12 text-base md:h-12" />
        {duplicando ? (
          <Alert variant="info">
            <Info />
            <AlertTitle>Se copia de {copiado!.nombre}</AlertTitle>
            <AlertDescription className="flex flex-col items-start gap-2 text-foreground">
              Nombre, categoría ({copiado!.categoria.nombre}), marca, modelo y precio se copian del original. El precio solo lo
              ven los administradores.
              <Button type="button" variant="ghost" className="min-h-11 px-1 text-brand-strong" onClick={alta.quitarCopia}>
                <X />
                Quitar la copia
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <Campo id="nombre" etiqueta={<>Nombre <Obligatorio /></>} error={errores.nombre}>
              <Input id="nombre" value={campos.nombre} onChange={(e) => alta.cambiar('nombre', e.target.value)} maxLength={120} autoComplete="off" enterKeyHint="next" {...aria(errores, 'nombre')} className="h-12 text-base" />
            </Campo>
            <Campo id="precio" etiqueta={<>Precio de compra (COP) <Obligatorio /></>} error={errores.precio} ayuda="Después de guardar, solo lo verán los administradores.">
              <div className="relative">
                <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" aria-hidden="true">$</span>
                <Input id="precio" value={campos.precio} onChange={(e) => alta.cambiar('precio', e.target.value)} inputMode="decimal" autoComplete="off" {...aria(errores, 'precio', true)} className="h-12 pl-7 text-base tabular-nums" />
              </div>
            </Campo>
            <Campo id="categoria" etiqueta={<>Categoría <Obligatorio /></>} error={errores.categoria}>
              <Select value={campos.categoria} onValueChange={(v) => alta.cambiar('categoria', v)} disabled={categorias.isPending}>
                <SelectTrigger id="categoria" className="h-12! w-full text-base" {...aria(errores, 'categoria')}>
                  <SelectValue placeholder={categorias.isPending ? 'Cargando…' : 'Elige una categoría'} />
                </SelectTrigger>
                <SelectContent>
                  {(categorias.data ?? []).map((c) => (
                    <SelectItem key={c.id} value={c.id} className="min-h-11">{c.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Campo>
          </>
        )}
        <Campo id="ubicacion" etiqueta={<>Ubicación <Obligatorio /></>} error={errores.ubicacion} ayuda="Sala o box donde está el activo.">
          <LocationPicker
            id="ubicacion"
            ubicaciones={ubicaciones.data ?? []}
            cargando={ubicaciones.isPending}
            valor={campos.ubicacion || undefined}
            onChange={(v) => alta.cambiar('ubicacion', v)}
            className="h-12 text-base md:h-12"
          />
        </Campo>
        <Collapsible className="rounded-lg border">
          <CollapsibleTrigger className="group flex min-h-12 w-full items-center gap-2 px-3 text-left text-[15px] font-medium">
            <ChevronDown className="size-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" />
            <span className="truncate">Más datos (opcional)</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex flex-col gap-4 border-t p-3">
            <Campo id="serial" etiqueta="Serial" ayuda="No tiene que ser único.">
              <Input id="serial" value={campos.serial} onChange={(e) => alta.cambiar('serial', e.target.value)} maxLength={120} autoComplete="off" className="h-12 font-mono text-base" />
            </Campo>
            {!duplicando && (
              <>
                <Campo id="marca" etiqueta="Marca"><Input id="marca" value={campos.marca} onChange={(e) => alta.cambiar('marca', e.target.value)} maxLength={120} autoComplete="off" className="h-12 text-base" /></Campo>
                <Campo id="modelo" etiqueta="Modelo"><Input id="modelo" value={campos.modelo} onChange={(e) => alta.cambiar('modelo', e.target.value)} maxLength={120} autoComplete="off" className="h-12 text-base" /></Campo>
                <Campo id="subtipo" etiqueta="Subtipo" ayuda="Por ejemplo: computador, fuente, video."><Input id="subtipo" value={campos.subtipo} onChange={(e) => alta.cambiar('subtipo', e.target.value)} maxLength={120} autoComplete="off" className="h-12 text-base" /></Campo>
                <Campo id="fecha" etiqueta="Fecha de compra" error={errores.fecha}><Input id="fecha" type="date" value={campos.fecha} onChange={(e) => alta.cambiar('fecha', e.target.value)} {...aria(errores, 'fecha')} className="h-12 text-base" /></Campo>
              </>
            )}
          </CollapsibleContent>
        </Collapsible>
      </form>
    </CountShell>
  )
}
