import { CameraOff, RefreshCw, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { CountShell } from '@/components/app/CountShell'
import { Aviso, Boton, Campo, EncabezadoPagina } from '@/components/kit'
import { useSimulacion } from '@/lib/simulacion'
import { normalizarCodigo } from '@/lib/activos'
import { useCabeceraConteo } from '@/lib/conteo'

// Entrada manual del código (docs/08 §7.1, CU-VER-05). Con ?estado=error se
// ve como cámara denegada. Mismo camino que un escaneo: existe → verificar;
// no existe → alta.
// Spec 016, T5: el código es el campo protagonista del kit (56 px, mono, centrado) y
// «Buscar» la acción principal de la barra.

export default function Escribir() {
  const { estado } = useSimulacion()
  const navigate = useNavigate()
  const cabecera = useCabeceraConteo()
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
      titulo={cabecera.titulo}
      subtitulo={cabecera.subtitulo}
      volver="/contar/escanear"
      estadoRed="en_linea"
      principal={
        <Boton type="submit" form="buscar-codigo" tamano="accion">
          Buscar
        </Boton>
      }
    >
      <EncabezadoPagina titulo="Escribir código" />
      {estado === 'error' && (
        <Aviso
          tono="aviso"
          icono={<CameraOff aria-hidden="true" />}
          titulo="Sin acceso a la cámara"
          accion={
            <Boton asChild variante="secundario">
              <Link to="/contar/escanear">
                <RefreshCw />
                Reintentar cámara
              </Link>
            </Boton>
          }
        >
          Actívala en los permisos del navegador, o escribe el código del sticker.
        </Aviso>
      )}
      <form id="buscar-codigo" onSubmit={buscar} noValidate>
        <Campo
          id="codigo"
          tipo="codigo"
          grande
          etiqueta="Código del sticker"
          ayuda="Está impreso debajo de las barras del sticker."
          error={error || undefined}
          value={codigo}
          onChange={(e) => {
            setCodigo(e.target.value)
            setError('')
          }}
          autoComplete="off"
          enterKeyHint="search"
        />
      </form>
      <Boton
        variante="fantasma"
        icono={<Search />}
        className="self-center text-brand-strong"
        onClick={() => toast('Buscar por nombre o serial llega con la spec 004')}
      >
        Buscar por nombre o serial
      </Boton>
    </CountShell>
  )
}
