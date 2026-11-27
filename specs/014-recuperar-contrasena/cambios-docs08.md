# Cambios a docs/08 por la spec 014 (recuperar contraseña por correo)

Lista para que el humano actualice `docs/08-diseno-visual.md` (cambio 5 de «Cambios en docs» de `spec.md`, con los textos definitivos de T6 y T7). Archivo local, no se versiona; el agente no edita `docs/08`. Los textos salen del código en `develop` (`web/src/routes/RecuperarContrasena.tsx`, `NuevaContrasena.tsx`, `Login.tsx`, `web/src/components/app/CampoContrasena.tsx`). Nota: el cambio 5 de la spec proponía «Si el correo está registrado, te enviamos un enlace…» y «Enlace vencido o ya usado. Pide uno nuevo.»; los textos definitivos son los de abajo.

## §3.2 Componentes propios

1. Nueva fila `CampoContrasena` (`web/src/components/app/CampoContrasena.tsx`): `Campo` de contraseña nueva con botón mostrar/ocultar (ícono ojo, `aria-label` «Mostrar …»/«Ocultar …», `aria-pressed`), `autoComplete="new-password"`, 10–128 caracteres y política fija con `ayudaFija` («Entre 10 y 128 caracteres. Evita contraseñas comunes.»). Lo comparten `/invitacion` y `/restablecer`.
2. Patrón «enlace secundario» de las pantallas de acceso (`MarcoAcceso`): al pie, bajo un separador (`border-t`), centrado, texto apagado (`text-muted-foreground`, tamaño `etiqueta`) con flecha a la izquierda, alto mínimo 44 px y foco visible; p. ej. «← Volver a iniciar sesión» en `/recuperar` y `/restablecer`.

## §6.1 Inventario de pantallas (fila de `/login`)

3. Ampliar la fila `/login`, `/invitacion/:token` (o añadir una fila junto a ella), CU ACC-06, sin precios:
   - `/recuperar`: pide el correo para recibir el enlace.
   - `/restablecer` (token en el fragmento `#`, que la pantalla quita de la barra al abrir): fija la contraseña nueva.
4. En `/login`: enlace «¿Olvidaste tu contraseña?» bajo el campo de contraseña, alineado a la derecha, en color primario, alto mínimo 44 px. Lleva a `/recuperar` con el correo ya escrito (cero digitación; viaja en el estado del router, no en la URL).

## §8 Estados y mensajes (nuevas filas)

5. **Recuperar contraseña** (`/recuperar`, título «Recuperar contraseña», descripción «Escribe el correo con el que entras. Si tiene una cuenta, te enviaremos un enlace para crear una contraseña nueva.», botón «Enviar enlace»):
   - Cargando: «Enviando…».
   - Error del correo (junto al campo, con foco): «Revisa el correo: escribe la dirección completa, por ejemplo nombre@clinica.com.»
   - Error general (`Aviso` de error con foco): `429` «Hiciste varias solicitudes seguidas. Espera <tiempo> e intenta de nuevo.» · `503` «El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.» · sin conexión: el mensaje de red del cliente · otro: «No pudimos enviar la solicitud. Intenta de nuevo.»
   - Éxito (igual para todo `202`, exista o no la cuenta; nunca repite el correo): título «Revisa tu correo»; `Aviso` de éxito con foco «Si existe una cuenta con ese correo, te enviamos un enlace que vale 30 minutos.» y «Si no lo ves en unos minutos, busca en la carpeta de correo no deseado.»; botones «Volver a iniciar sesión» (principal) y «Pedir otro enlace» (secundario).
6. **Nueva contraseña** (`/restablecer`, título «Crea una contraseña nueva», descripción «Escríbela dos veces. Al guardarla se cierran tus sesiones abiertas y entras de nuevo con ella.», campos «Nueva contraseña» y «Confirma la contraseña» con `CampoContrasena`, botón «Guardar contraseña»):
   - Cargando: «Guardando…».
   - Errores junto al campo: los `contrasena_*` del servidor en «Nueva contraseña»; «Las contraseñas no coinciden. Escribe la misma en los dos campos.» en la confirmación.
   - Error general: `429` «Hiciste varios intentos seguidos. Espera <tiempo> e intenta de nuevo.» · `503` como arriba · otro: «No pudimos guardar la contraseña. Intenta de nuevo.»
   - Enlace sin token o rechazado (`enlace_invalido`): título «Enlace vencido o ya usado» (ícono de enlace roto, tono aviso); `Aviso` de error con foco «Este enlace no es válido o ya venció. Pide uno nuevo.» y «El enlace vale 30 minutos y sirve una sola vez. Si pediste varios, solo funciona el último.»; botón «Pedir un enlace nuevo» (a `/recuperar`) y enlace secundario «Volver a iniciar sesión».
   - Éxito: sin sesión, lleva a `/login`.
7. **Login**, columna Éxito: tras restablecer, `Aviso` de éxito con foco al llegar «Tu contraseña se actualizó. Inicia sesión con la nueva.» (llega por el estado del router y se borra del historial; desaparece al intentar entrar).
8. **Login / invitación**, columna Error: «Enlace vencido o ya usado. Pide uno nuevo.» sigue siendo el de la invitación; el de recuperación es el del punto 6.
