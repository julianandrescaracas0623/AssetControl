import { vi } from 'vitest'

// jsdom no implementa matchMedia; la barra lateral la usa para saber si está
// en celular (hooks/use-mobile.ts). `movil` simula un ancho menor que md.
// `escritorio` (spec 015, T8) simula ≥ 1024 px con puntero fino (hooks/use-escritorio.ts);
// por defecto es falso: las pruebas existentes siguen viendo el conteo del teléfono.
export function simularAncho({ movil, escritorio = false }: { movil: boolean; escritorio?: boolean }) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: query.includes('pointer: fine') ? escritorio && !movil : movil,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
  vi.stubGlobal('innerWidth', movil ? 375 : 1440)
}

/** Computador con mouse: ≥ 1024 px y puntero fino. */
export const simularEscritorio = () => simularAncho({ movil: false, escritorio: true })
