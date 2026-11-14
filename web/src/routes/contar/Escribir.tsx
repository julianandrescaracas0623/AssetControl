import { CameraOff, RefreshCw, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { CountShell } from '@/components/app/CountShell'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useSimulacion } from '@/lib/simulacion'
import { normalizarCodigo } from '@/lib/activos'
import { RESUMEN } from '@/mocks/datos-ficticios'

// Entrada manual del código (docs/08 §7.1, CU-VER-05). Con ?estado=error se
// ve como cámara denegada. Mismo camino que un escaneo: existe → verificar;
// no existe → alta.

export default function Escribir() {
  const { estado } = useSimulacion()
  const navigate = useNavigate()
  const [codigo, setCodigo] = useState('')
  const [error, setError] = useState('')

  function buscar(evento: React.FormEvent) {
    evento.preventDefault()
    if (!codigo.trim()) {
      setError('Escribe el código del sticker')
      return
    }
    // Spec 004: el código se normaliza como en el servidor y la ficha lo resuelve.
    const c = normalizarCodigo(codigo)
    if (!c) {
      setError('Ese texto no es un código: usa letras sin tilde, números o - . / _, sin espacios')
      return
    }
    navigate(`/contar/activo/${encodeURIComponent(c)}`)
  }

  return (
    <CountShell
      titulo={RESUMEN.conteoAbierto.nombre}
      subtitulo="Administración"
      volver="/contar/escanear"
      estadoRed="en_linea"
      acciones={
        <Button type="submit" form="buscar-codigo" className="min-h-14 font-semibold">
          Buscar
        </Button>
      }
    >
      <h1 className="text-xl font-semibold tracking-tight">Escribir código</h1>
      {estado === 'error' && (
        <Alert variant="warning">
          <CameraOff />
          <AlertTitle>Sin acceso a la cámara</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            Actívala en los permisos del navegador, o escribe el código del sticker.
            <Button asChild variant="outline" className="min-h-11">
              <Link to="/contar/escanear">
                <RefreshCw />
                Reintentar cámara
              </Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <form id="buscar-codigo" onSubmit={buscar} noValidate className="flex flex-col gap-2">
        <Label htmlFor="codigo" className="text-base">Código del sticker</Label>
        <Input
          id="codigo"
          value={codigo}
          onChange={(e) => {
            setCodigo(e.target.value)
            setError('')
          }}
          autoComplete="off"
          enterKeyHint="search"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? 'codigo-error' : 'codigo-ayuda'}
          className="h-14 text-center font-mono text-2xl tracking-widest md:text-2xl"
        />
        {error ? (
          <p id="codigo-error" className="text-sm text-destructive">{error}</p>
        ) : (
          <p id="codigo-ayuda" className="text-sm text-muted-foreground">Está impreso debajo de las barras del sticker.</p>
        )}
      </form>
      <Button variant="ghost" className="min-h-11 self-center text-brand-strong" onClick={() => toast('Buscar por nombre o serial llega con la spec 004')}>
        <Search />
        Buscar por nombre o serial
      </Button>
    </CountShell>
  )
}
