import { type ComponentProps, useEffect, useId, useState } from 'react'

import { Input } from '@/components/ui/input'
import { type CampoSugerido, useSugerencias } from '@/lib/activos'

// Campo de texto con sugerencias de lo ya registrado (spec 004, T7; CU-CAT-04). Usa
// <datalist>: el teclado del teléfono y el navegador muestran las opciones sin otra
// dependencia. Pide a la API después de una pausa de 250 ms y solo con el campo enfocado.
export function InputSugerido({
  campo,
  value,
  ...props
}: Omit<ComponentProps<typeof Input>, 'list'> & { campo: CampoSugerido; value: string }) {
  const lista = useId()
  const [activo, setActivo] = useState(false)
  const [consulta, setConsulta] = useState(value)
  useEffect(() => {
    const reloj = setTimeout(() => setConsulta(value.trim()), 250)
    return () => clearTimeout(reloj)
  }, [value])
  const sugerencias = useSugerencias(campo, consulta, activo)
  const opciones = (sugerencias.data ?? []).filter((v) => v !== value)

  return (
    <>
      <Input
        {...props}
        value={value}
        list={lista}
        onFocus={(evento) => {
          setActivo(true)
          props.onFocus?.(evento)
        }}
      />
      <datalist id={lista}>
        {opciones.map((v) => (
          <option key={v} value={v} />
        ))}
      </datalist>
    </>
  )
}
