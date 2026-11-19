import { Flashlight, FlashlightOff, LoaderCircle, VideoOff } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { type CrearLector, clasificarFallo, crearLectorZxing, type FalloCamara, type Lector } from '@/lib/lector'

// Visor del escáner (docs/08 §7.1; spec 004, T8; R9). Lee solo, sin tocar nada; una
// lectura repetida del mismo código en menos de 1 s se ignora. Si la cámara falla, lo
// explica y deja la entrada manual a la mano (la pone quien usa el componente).

const ANTIRREBOTE_MS = 1000

const MENSAJES: Record<FalloCamara, { titulo: string; texto: string }> = {
  denegada: {
    titulo: 'Sin acceso a la cámara',
    texto: 'Actívala en los permisos del navegador para esta página, o escribe el código del sticker.',
  },
  sin_camara: { titulo: 'No encontramos una cámara', texto: 'Escribe el código del sticker.' },
  inseguro: {
    titulo: 'La cámara necesita una conexión segura',
    texto: 'Abre la web con https:// para escanear, o escribe el código del sticker.',
  },
  error: { titulo: 'La cámara no respondió', texto: 'Vuelve a intentarlo o escribe el código del sticker.' },
}

export function Escaner({
  onLectura,
  crearLector = crearLectorZxing,
  className = 'min-h-[380px]',
}: {
  onLectura: (texto: string) => void
  crearLector?: CrearLector
  className?: string
}) {
  const video = useRef<HTMLVideoElement>(null)
  const ultima = useRef<{ texto: string; en: number } | null>(null)
  const alLeer = useRef(onLectura)
  const [estado, setEstado] = useState<'iniciando' | 'leyendo' | FalloCamara>('iniciando')
  const [lector, setLector] = useState<Lector | null>(null)
  const [linterna, setLinterna] = useState(false)
  const [intento, setIntento] = useState(0)

  useEffect(() => {
    alLeer.current = onLectura
  }, [onLectura])

  useEffect(() => {
    let cancelado = false
    let activo: Lector | null = null
    const corte = new AbortController()
    crearLector(video.current!, (texto) => {
      const ahora = Date.now()
      if (ultima.current && ultima.current.texto === texto && ahora - ultima.current.en < ANTIRREBOTE_MS) return
      ultima.current = { texto, en: ahora }
      navigator.vibrate?.(40)
      alLeer.current(texto)
    }, corte.signal)
      .then((creado) => {
        if (cancelado) {
          creado.detener()
          return
        }
        activo = creado
        setLector(creado)
        setEstado('leyendo')
      })
      .catch((error: unknown) => {
        if (cancelado) return
        setEstado(error instanceof Error && error.name === 'Inseguro' ? 'inseguro' : clasificarFallo(error))
      })
    return () => {
      cancelado = true
      corte.abort()
      activo?.detener()
    }
  }, [crearLector, intento])

  async function cambiarLinterna() {
    if (!lector?.linterna) return
    try {
      await lector.linterna(!linterna)
      setLinterna(!linterna)
    } catch {
      setLinterna(false)
    }
  }

  const fallo = estado !== 'iniciando' && estado !== 'leyendo' ? MENSAJES[estado] : null

  return (
    <div className="flex flex-col gap-3">
      <div className={`relative flex flex-1 items-center justify-center overflow-hidden rounded-2xl bg-ink text-ink-foreground ${className}`}>
        <video ref={video} className="absolute inset-0 size-full object-cover" muted playsInline aria-hidden="true" />
        {fallo ? (
          <div role="alert" className="relative flex max-w-xs flex-col items-center gap-3 px-6 text-center">
            <VideoOff className="size-8" aria-hidden="true" />
            <p className="font-semibold">{fallo.titulo}</p>
            <p className="text-sm text-ink-foreground/80">{fallo.texto}</p>
            {estado !== 'inseguro' && (
              <Button variant="secondary" className="min-h-11" onClick={() => { setEstado('iniciando'); setIntento((n) => n + 1) }}>
                Reintentar la cámara
              </Button>
            )}
          </div>
        ) : (
          <>
            <span className="absolute top-3 left-3 inline-flex h-7 items-center gap-1.5 rounded-full border border-ink-foreground/30 bg-ink/60 px-2.5 text-xs">
              {estado === 'iniciando' ? (
                <LoaderCircle className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              ) : (
                <span className="size-2 rounded-full bg-success-border" aria-hidden="true" />
              )}
              {estado === 'iniciando' ? 'Abriendo la cámara…' : 'Cámara activa'}
            </span>
            <div className="relative h-36 w-64" aria-hidden="true">
              <span className="absolute top-0 left-0 size-8 rounded-tl-xl border-t-4 border-l-4 border-ink-foreground" />
              <span className="absolute top-0 right-0 size-8 rounded-tr-xl border-t-4 border-r-4 border-ink-foreground" />
              <span className="absolute bottom-0 left-0 size-8 rounded-bl-xl border-b-4 border-l-4 border-ink-foreground" />
              <span className="absolute right-0 bottom-0 size-8 rounded-br-xl border-r-4 border-b-4 border-ink-foreground" />
              <span className="absolute inset-x-4 top-1/2 h-0.5 bg-brand-border" />
            </div>
            <div className="absolute inset-x-0 bottom-5 flex flex-col items-center gap-1 px-4 text-center">
              <span className="font-semibold">Apunta al sticker</span>
              <span className="text-sm text-ink-foreground/80">Se lee solo, sin tocar nada</span>
            </div>
          </>
        )}
        <p className="sr-only" role="status">
          {estado === 'leyendo' ? 'Cámara activa: apunta al código de barras del sticker.' : estado === 'iniciando' ? 'Abriendo la cámara.' : ''}
        </p>
      </div>
      {lector?.linterna && (
        <Button variant="outline" className="min-h-11 self-end" aria-pressed={linterna} onClick={() => void cambiarLinterna()}>
          {linterna ? <FlashlightOff /> : <Flashlight />}
          {linterna ? 'Apagar linterna' : 'Linterna'}
        </Button>
      )}
    </div>
  )
}
