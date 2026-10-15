# Sprint 5 · Bitácora de trabajo

Registro de la sesión que sigue `Sprint5_Instrucciones_Claude_Code.md`. Si la
sesión se corta, retomar desde la última entrada.

## 2026-10-15 · Fase 1, reconocimiento

- Docker Desktop estaba apagado; se levantó (`open -a Docker`). 10 CPU, 8 GB.
- Los tres repos ya están en `feature/sprint-5`, sincronizados con `origin`:
  backend `068c0c5`, panel `1cbe810`, móvil `38e3f11` (13/10/2026). Las siete
  historias del sprint se implementaron en sesiones anteriores y se subieron en
  un único commit por repo.
- `develop` existe en `origin` en los tres repos; en el panel no hay rama
  local `develop`.
- Convención de commits: Conventional Commits en inglés (`feat(reports): …`).
- Diferencias de stack con el documento de instrucciones:
  - móvil en **Expo SDK 57 / RN 0.86.3 / React 19.2.3**, no SDK 54 / RN 0.81;
  - el panel prueba con **Vitest**, no Jest;
  - el móvil **no tiene ESLint** configurado.
- Línea base:

  | Repo | Tests | Resultado |
  | --- | --- | --- |
  | backend | 1409 + 1 xfail | todo en verde (36,7 s) |
  | panel | 328 (37 archivos) | todo en verde; `tsc -b` y ESLint limpios |
  | móvil | 371 (36 suites) | primera corrida en frío: 8 fallas por timeout en 5 suites; la segunda, 371/371. `tsc` limpio |

- **Hallazgo de privacidad:** las 37 fotos del benchmark de US-041 (personas,
  patentes y calle, bajadas de Wikimedia Commons) están **versionadas** en
  `urbancheck/anonymization/benchmark/images/` y subidas a
  `origin/feature/sprint-5`, en un repo público. Contradice la regla 4 y el
  punto 6.2 de las instrucciones. Sacarlas del árbol no es destructivo (se
  conservan en una carpeta no versionada); sacarlas del **historial** es
  reescribirlo y requiere confirmación del equipo.
- `urbancheck_backend/.envs/.local/.django` está versionado y contiene en el
  disco una clave real de Gemini, commiteada vacía. Nunca `git add -A`.

## 2026-10-15 · Decisiones consultadas al equipo

Respondidas por el usuario antes de implementar:

1. **Validación colectiva:** se mantiene el me gusta como confirmación (como
   dicen US-040 y US-032). El punto 2.4 de las instrucciones, que habla de una
   entidad de confirmación separada, queda como diferencia a corregir en el
   documento.
2. **Panel municipal:** sigue viendo los reportes con la imagen en
   procesamiento (sin foto y sin acciones), decisión previa del usuario.
3. **US-043 E5:** se mantiene el retiro total del reporte cuando se elimina su
   foto, decisión previa del usuario.
4. **Fotos del benchmark en el historial:** no se reescribe el historial por
   ahora; se sacan del árbol con un commit nuevo.

## 2026-10-15 · Fase 3, paso 1: base de seguridad (`af2e35e`)

- Cache `RedisCache` de Django en `base.py`; los tests usan memoria local.
- Límites de allauth: `login_failed` 10/m/ip + 5/15m/key, `reset_password`
  3/h/key, `confirm_email` 1/3m/key + 3/h/key, `signup` 20/h/ip.
- **Hallazgo:** allauth headless responde el bloqueo de login con **400**
  (`too_many_login_attempts`) y el reenvío limitado de la confirmación con
  **403** sin cuerpo. `HeadlessLockoutMiddleware` los pasa a 429.
- Throttles de DRF por acción (`ScopedThrottle`): reportes 20/h, comentarios
  60/h, denuncias 10/d, dato personal 5/d. Una denuncia con motivo
  `dato_personal` por `complaints/` consume los dos cupos.
- `DJANGO_NUM_PROXIES` (default 0) alimenta `NUM_PROXIES` de DRF,
  `ALLAUTH_TRUSTED_PROXY_COUNT` y el log. **Hallazgo:** con el default de DRF
  (`None`) el ident del throttle era el `X-Forwarded-For` entero, que el
  cliente controla.
- Logger `security` con `RotatingFileHandler` y receptores de señales.
- Argon2id ya era el hasher principal; faltaba el test.

## 2026-10-15 · Paso 2: CI y Dependabot

- pip-audit: 99 vulnerabilidades en 11 paquetes → parches (Django 6.0.9, DRF
  3.17.2, Pillow 12.3.0, Werkzeug 3.1.9, cryptography 50.0.2, etc.)
  (`a89d42b`).
- Bandit 1.8.6 no corre en Python 3.14 (`ast.Num`); se usa 1.9.4. Hallazgos:
  2 altos (SHA1 en claves de cache → `usedforsecurity=False`), 1 medio
  (`0.0.0.0` en `ALLOWED_HOSTS` de dev, justificado con `nosec`).
- Ruff: 341 hallazgos previos → 0 (`d79cec0`). 182 códigos HTTP literales
  pasaron a `HTTPStatus`; cuentas en asserts y contraseñas de prueba con
  `noqa` por línea, como el resto de la suite.
- gitleaks: 2 hallazgos en el backend (credenciales del compose local) en
  `.gitleaksignore`; panel y móvil limpios.
- npm audit: panel 24 → 1 alta sin corrección publicada (`braces`); móvil
  64 → 2 altas sin corrección (`braces`, `node-forge`). Excepciones revisadas
  en `audit-allowlist.json` con `scripts/audit-gate.mjs`.
- Móvil: ESLint 9 + `eslint-config-expo` agregados (no existía); 28 errores
  → 0. `expo install --fix` dejó expo-doctor 21/21 (expo 57.0.29).
- Commits: backend `7686b40`; panel `4b20600`, `a5deb8e`; móvil `033abd7`,
  `fef6f01`.

## 2026-10-15 · Pasos 3 a 9

- **US-041** (`6d5b6ec`): fotos del benchmark fuera del árbol, a
  `benchmark_data/` (ignorada por git y Docker); `benchmark_anonymization
  [CARPETA] --report` con tasa por tipo, falsos negativos, promedio y p95. Los
  tests de detección leen el set y se saltean si falta; el resto usa fotos
  sintéticas con GPS/XMP. Checksum de los pesos al cargarlos y en el build de
  producción. Benchmark en Docker: 92,6 % rostros, 93,3 % patentes, 786 ms
  promedio, 961 ms p95 (`docs/sprint-5/benchmark-us041.md`).
- **SEC-09/10 y US-042 E9** (`43f84ac`): avatar sin metadatos por campo de
  modelo; `strip_image_metadata` y `anonymize_existing_photos`, simulacro por
  defecto. **No se ejecutaron sobre datos.**
- **Hueco de US-043 E1** (`e2d19b4`): la foto de la apelación no se podía
  denunciar. `ReportComplaint.resolution_appeal` + migración `reports/0014`.
  Bandeja también en el admin de Django. El panel retiene la imagen en revisión.
- **HU-VIS** (`a3d5c47`): condiciones únicas `publicly_visible_condition`;
  la bandeja de validación las reutiliza. Un tercero ya no abre por id un
  reporte cancelado o archivado. **DEF-20**: un reporte retenido por dato
  personal aceptaba denuncias de contenido.
- **Clientes** (US-043): botón "Denunciar foto" en la objeción (móvil
  `8d75291`), tipo `resolution_appeal` en la bandeja (panel `61e86bf`).
- **SEC-05**: 429 con mensaje propio en móvil (`c27729b`) y panel (`2b8287c`).
  **Hallazgo:** el login de la app mostraba "Email o contraseña incorrectos"
  ante el bloqueo.
- **SEC-16/17/19** (`7a7e20a`): HSTS 1 año, CORS cerrado, admin fuera de
  `admin/`; el `LOGGING` de producción perdía el logger `security`.
  `check --deploy`: 0 advertencias de seguridad desde el principio; 11 de
  drf-spectacular corregidas. `.env.example` en los tres repos.

## 2026-10-15 · Pasos 10 y 11, y reporte

- **US-015** (`b947f49`): `DJANGO_VISION_PROVIDER` con proveedor nulo por
  default; `openai_compatible` (Gemini) activado en `.envs/.local/.django`,
  commiteado con la clave vacía (blob armado a mano).
- **US-026 E9** (`e301d40`): 100.000 reportes, 1,34 ms promedio, 2,06 ms p95,
  con índice. **US-041 E8** (`a8fd8b5`): `measure_anonymization`.
- **Trazabilidad**: 276 tests del backend marcados `CP-<historia>-nn`; clientes
  `-Mnn` (app) y `-Pnn` (panel). `TRAZABILIDAD.md`: 409 casos, sin repetidos.
- **QA final**: backend 1509 + 1 xfail, ruff 0, Bandit 0 (≥ media), pip-audit
  0, gitleaks 0, sin migraciones pendientes, cobertura 97 %. Panel 335, tsc y
  ESLint limpios, 89,9 %. App 383, tsc limpio, ESLint 0 errores (1 aviso),
  76,1 %. npm audit solo con excepciones revisadas.
- Reporte final: `REPORTE_SPRINT_5.md`. **Nada se subió a `origin`.**
