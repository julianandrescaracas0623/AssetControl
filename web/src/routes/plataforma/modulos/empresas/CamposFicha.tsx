import { Campo } from '@/components/kit'
import type { CampoEmpresa } from '@/lib/empresa'

import { CAMPOS_FICHA, type DatosFicha, idCampo } from './api'

// Los cinco campos de la ficha de la empresa (spec 017, T9 y C1/T14): los mismos en el alta y en
// Editar empresa, con las ayudas y topes de /admin/empresa. Grilla de dos columnas desde sm:
// nombre y dirección a lo ancho.

export type CamposFichaProps = {
  prefijo: 'alta' | 'editar'
  valores: DatosFicha
  errores: Partial<Record<CampoEmpresa, string>>
  onCambio: (campo: CampoEmpresa, valor: string) => void
  /** Ayuda del nombre cuando hay otra empresa que se llama igual (P34; solo en el alta). */
  ayudaNombre?: string
  deshabilitado?: boolean
  focoInicial?: boolean
}

export function CamposFicha({ prefijo, valores, errores, onCambio, ayudaNombre, deshabilitado, focoInicial }: CamposFichaProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {CAMPOS_FICHA.map(({ campo, etiqueta, obligatorio, ayuda, tipo, modo, max }) => (
        <Campo
          key={campo}
          id={idCampo(campo, prefijo)}
          etiqueta={etiqueta}
          obligatorio={obligatorio}
          error={errores[campo]}
          ayuda={campo === 'nombre' && ayudaNombre ? ayudaNombre : ayuda}
          className={campo === 'nombre' || campo === 'direccion' ? 'sm:col-span-2' : undefined}
          name={campo}
          type={tipo ?? 'text'}
          inputMode={modo}
          value={valores[campo]}
          maxLength={max}
          required={obligatorio}
          autoComplete="off"
          autoFocus={focoInicial && campo === 'nombre'}
          disabled={deshabilitado}
          onChange={(e) => onCambio(campo, e.target.value)}
        />
      ))}
    </div>
  )
}
