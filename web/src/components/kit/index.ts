// Spec 016 (D11): biblioteca propia de componentes, sobre components/ui (shadcn,
// intacto) y los tokens de index.css. Las pantallas importan de aquí, no de ui (R7).

import { EstadoCargando, EstadoError, EstadoVacio } from './Estado'

export { Aviso, type AvisoProps, type TonoAviso } from './Aviso'
export { Boton, type BotonProps, type TamanoBoton, type VarianteBoton } from './Boton'
export { Campo, MarcaObligatorio, MarcoCampo, type CampoProps, type OpcionCampo } from './Campo'
export {
  EstadoCargando,
  EstadoError,
  EstadoVacio,
  type EstadoCargandoProps,
  type EstadoErrorProps,
  type EstadoVacioProps,
} from './Estado'
export { Insignia, type InsigniaProps, type TonoInsignia } from './Insignia'

/** `Estado.Cargando`, `Estado.Vacio` y `Estado.Error` (R3). */
export const Estado = {
  Cargando: EstadoCargando,
  Vacio: EstadoVacio,
  Error: EstadoError,
} as const
