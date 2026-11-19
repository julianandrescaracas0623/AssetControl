// Spec 016 (D11): biblioteca propia de componentes, sobre components/ui (shadcn,
// intacto) y los tokens de index.css. Las pantallas importan de aquí, no de ui (R7).

import { EstadoCargando, EstadoError, EstadoVacio } from './Estado'

export { Aviso, type AvisoProps, type TonoAviso } from './Aviso'
export { BarraAccion, type BarraAccionProps } from './BarraAccion'
export { Boton, type BotonProps, type TamanoBoton, type VarianteBoton } from './Boton'
export { Casilla, type CasillaProps } from './Casilla'
export { Campo, MarcaObligatorio, MarcoCampo, type CampoProps, type OpcionCampo } from './Campo'
export { Cifra, CifrasCongeladas, type CifraCongelada, type CifraProps, type CifrasCongeladasProps } from './Cifra'
export { Confirmar, type ConfirmarProps } from './Confirmar'
export { Dialogo, type DialogoProps, type FormaDialogo } from './Dialogo'
export { EncabezadoPagina, type EncabezadoPaginaProps, type Miga } from './EncabezadoPagina'
export {
  Esqueleto,
  EstadoCargando,
  EstadoError,
  EstadoVacio,
  type EstadoCargandoProps,
  type EstadoErrorProps,
  type EstadoVacioProps,
} from './Estado'
export { Filtro, type FiltroProps, type OpcionFiltro } from './Filtro'
export { Interruptor, type InterruptorProps } from './Interruptor'
export { Insignia, type InsigniaProps, type TonoInsignia } from './Insignia'
export { ListaDatos, type Dato, type ListaDatosProps, type TipoDato } from './ListaDatos'
export { MarcoImagen, type MarcoImagenProps } from './MarcoImagen'
export { MEDIDAS_IMAGEN, type VarianteImagen } from './medidasImagen'
export { Menu, type MenuProps, type OpcionMenu } from './Menu'
export { Notificaciones, type NotificacionesProps } from './Notificaciones'
export { Panel, type PanelProps } from './Panel'
export { Pestanas, type Pestana, type PestanasProps } from './Pestanas'
export { Progreso, type ProgresoProps } from './Progreso'
export { ID_CONTENIDO, SaltarContenido } from './SaltarContenido'
export { Tecla, type TeclaProps } from './Tecla'
export {
  TablaDatos,
  type BarraTabla,
  type CeldaPie,
  type ColumnaTabla,
  type OrdenTabla,
  type PaginacionTabla,
  type TablaDatosProps,
  type TipoColumna,
} from './TablaDatos'

/** `Estado.Cargando`, `Estado.Vacio` y `Estado.Error` (R3). */
export const Estado = {
  Cargando: EstadoCargando,
  Vacio: EstadoVacio,
  Error: EstadoError,
} as const
