import { useParams } from 'react-router'

import { DetalleSesion } from '@/routes/admin/Sesiones'

// /admin/sesiones/:id (spec 006, T5; CU-SES-02).
export default function RutaDetalleSesion() {
  const { id = '' } = useParams()
  return <DetalleSesion id={id} />
}
