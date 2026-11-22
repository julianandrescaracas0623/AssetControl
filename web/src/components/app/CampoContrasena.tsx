import { Eye, EyeOff } from 'lucide-react'
import { type ComponentProps, type ReactNode, useState } from 'react'

import { Boton, Campo } from '@/components/kit'

// Contraseña nueva con «mostrar/ocultar» (spec 002b, T4; spec 014, T7): el mismo campo
// en aceptar invitación y en restablecer. La política es la de 002 (R12/Q9) y la decide
// el servidor; aquí solo se muestra fija (`ayudaFija`) y se acota el largo (10–128).

export const POLITICA_CONTRASENA = 'Entre 10 y 128 caracteres. Evita contraseñas comunes.'

type CampoContrasenaProps = {
  id: string
  etiqueta: ReactNode
  name: string
  /** Lo que se muestra/oculta, para el nombre del botón: «la nueva contraseña». */
  queMostrar?: string
  ayuda?: ReactNode
  error?: string
  ref?: ComponentProps<'input'>['ref']
  autoFocus?: boolean
  disabled?: boolean
  /** Marca «*» del kit (spec 017, T16). */
  obligatorio?: boolean
  /**
   * Pide a los gestores de contraseñas (1Password, Bitwarden, LastPass, Dashlane) no
   * guardarla ni autocompletarla (spec 017, C1b/T16). Opt-in: solo la contraseña temporal
   * que define el desarrollador; en login, invitación y cambio propio el gestor sí ayuda.
   */
  sinGestor?: boolean
}

export function CampoContrasena({ queMostrar = 'contraseña', ayuda, sinGestor = false, ...props }: CampoContrasenaProps) {
  const [visible, setVisible] = useState(false)
  const gestor = sinGestor ? 'true' : undefined
  return (
    <Campo
      {...props}
      data-1p-ignore={gestor}
      data-bwignore={gestor}
      data-lpignore={gestor}
      data-form-type={sinGestor ? 'other' : undefined}
      type={visible ? 'text' : 'password'}
      autoComplete="new-password"
      autoCapitalize="none"
      spellCheck={false}
      required
      minLength={10}
      maxLength={128}
      ayuda={ayuda}
      ayudaFija={ayuda !== undefined}
      sufijo={
        <Boton
          variante="fantasma"
          soloIcono
          icono={visible ? <EyeOff /> : <Eye />}
          aria-label={`${visible ? 'Ocultar' : 'Mostrar'} ${queMostrar}`}
          aria-pressed={visible}
          className="text-muted-foreground hover:bg-transparent hover:text-foreground"
          onClick={() => setVisible((v) => !v)}
        />
      }
    />
  )
}
