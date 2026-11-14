import { vi } from 'vitest'

// jsdom no implementa matchMedia; la barra lateral la usa para saber si está
// en celular (hooks/use-mobile.ts). `movil` simula un ancho menor que md.
export function simularAncho({ movil }: { movil: boolean }) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: movil,
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
