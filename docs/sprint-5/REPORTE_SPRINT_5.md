# UrbanCheck · Sprint 5 · Reporte final

Generado el 15/10/2026 a partir de `Sprint5_Instrucciones_Claude_Code.md`. Los
números son de corridas reales en el entorno Docker de desarrollo de ese día.
Donde falta un dato se dice "sin dato" y por qué. El detalle cronológico está
en `BITACORA.md` y la trazabilidad completa en `TRAZABILIDAD.md`, los dos en
esta misma carpeta.

---

## 1. Resumen ejecutivo

1. Las siete historias ya estaban implementadas en `feature/sprint-5`. Este trabajo cerró los huecos (la foto de la apelación no se podía denunciar, faltaba el comando retroactivo de US-042, la visibilidad única tenía tres excepciones) y marcó cada escenario con su caso `CP-…`.
2. La deuda de seguridad quedó saldada: límites de intentos y de tasa, proxies confiables, log de seguridad, metadatos, Argon2id con test, CI con cinco etapas en los tres repos, Dependabot, configuración de producción y `check --deploy` sin advertencias.
3. Se corrigieron 99 vulnerabilidades conocidas en 11 paquetes de Python y las de npm que tenían versión corregida. Quedan 3 advertencias altas de npm sin versión corregida publicada, documentadas como excepciones revisadas.
4. Tests: backend 1409 → 1509, panel 328 → 335, app 371 → 383, todos en verde. Cobertura: backend 97 %, panel 89,9 % de líneas, app 76,1 %.
5. Benchmark de US-041 sobre el set provisorio de 37 fotos: 92,6 % de rostros y 93,3 % de patentes. Tiempos de 1,1 s promedio y 1,3 s p95 en una foto de 12 MP.
6. Parcial: QA-05, porque la validación colectiva usa el me gusta y no una entidad de confirmación (decisión del equipo).
7. Quedó afuera: correr los dos comandos retroactivos sobre datos (necesitan autorización), el set de benchmark propio y las pruebas manuales en dispositivo.
8. **El equipo tiene que decidir:** (a) si se reescribe el historial para sacar las fotos del benchmark que quedaron en el commit `068c0c5` de un repo público; (b) si autoriza `anonymize_existing_photos --apply` y `strip_image_metadata --apply`; (c) corregir el documento de Seguridad (bloqueo "5 en 5 min con 15 de bloqueo") y el punto 2.4 de las instrucciones (confirmación ciudadana).

---

## 2. Línea base

Estado al empezar (15/10/2026, 09:10). Docker Desktop estaba apagado y se levantó.

| Repo | Rama | Último commit | Tests | Resultado |
| --- | --- | --- | --- | --- |
| Backend (`urbancheck_backend`) | `feature/sprint-5` (= `origin`) | `068c0c5` feat(reports): add sprint 5 privacy, duplicate and complaint flows (13/10) | 1409 + 1 xfail | Todo en verde (36,7 s) |
| Panel (`urbanchech_frontend`) | `feature/sprint-5` (= `origin`) | `1cbe810` feat(panel): add sprint 5 privacy inbox and closure comparison (13/10) | 328 (37 archivos, Vitest) | Todo en verde; `tsc -b` y ESLint limpios |
| App (`urbancheck_mobile`) | `feature/sprint-5` (= `origin`) | `38e3f11` feat(mobile): add sprint 5 reporting, privacy and duplicate screens (13/10) | 371 (36 suites, Jest) | Primera corrida en frío: 8 fallas por timeout en 5 suites; la segunda, 371/371. `tsc` limpio. Sin ESLint configurado |

Diferencias de stack con el documento: la app corre **Expo SDK 57 / React Native 0.86.3** (no SDK 54 / RN 0.81); el panel prueba con **Vitest** (no Jest).

---

## 3. Inventario

| ID | Ítem | Estado inicial | Estado final | Evidencia |
| --- | --- | --- | --- | --- |
| SEC-01 | Cache sobre Redis | Falta (memoria local en dev; `django-redis` con `IGNORE_EXCEPTIONS` en prod) | Hecho | `config/settings/base.py` (`CACHES`); CP-SEC01-01 |
| SEC-02 | Limitación de allauth | Parcial (defaults de allauth activos, sin variables ni tests; el bloqueo respondía 400) | Hecho | `ACCOUNT_RATE_LIMITS`, `common/security.py::HeadlessLockoutMiddleware`; CP-SEC02-01..07 |
| SEC-03 | Throttling de DRF | Falta | Hecho | `common/throttling.py`, `ReportViewSet.get_throttles`; CP-SEC03-01..08 |
| SEC-04 | Proxies confiables | Falta | Hecho | `DJANGO_NUM_PROXIES` → `NUM_PROXIES`, `ALLAUTH_TRUSTED_PROXY_COUNT`; CP-SEC04-01..03 |
| SEC-05 | 429 en app y panel | Falta | Hecho | `urbancheck_mobile/src/api/errors.ts`, `urbanchech_frontend/src/api/client.ts`; CP-SEC05-M01..M09, P01..P05 |
| SEC-06 | Metadatos: foto de reporte | Parcial (el servicio los descartaba; no había test sobre el archivo guardado) | Hecho | `test_upload.py`: CP-041-13, CP-041-14 (`assert_no_metadata`) |
| SEC-07 | Metadatos: evidencia del operario | Parcial | Hecho | CP-041-15 / CP-046-07 |
| SEC-08 | Metadatos: foto de apelación | Parcial | Hecho | CP-041-16, CP-042-37 |
| SEC-09 | Metadatos: foto de perfil | Falta | Hecho | `anonymization/fields.py::MetadataFreeImageField`; CP-SEC09-01..04 |
| SEC-10 | Saneamiento retroactivo de metadatos | Falta | Hecho (no ejecutado) | `strip_image_metadata`; CP-SEC10-01..03 |
| SEC-11 | CI del backend | Parcial (CI de cookiecutter solo en PR a `main`, sin Bandit, pip-audit ni gitleaks) | Hecho | `.github/workflows/ci.yml`; corrido localmente herramienta por herramienta |
| SEC-12 | CI del panel | Falta | Hecho | `urbanchech_frontend/.github/workflows/ci.yml` |
| SEC-13 | CI de la app | Falta | Hecho | `urbancheck_mobile/.github/workflows/ci.yml` |
| SEC-14 | Argon2id | Parcial (primer hasher, sin test) | Hecho | CP-SEC14-01, CP-SEC14-02 |
| SEC-15 | Dependabot | Parcial (solo backend, diario) | Hecho | `.github/dependabot.yml` en los tres repos |
| SEC-16 | Configuración de producción | Parcial (HSTS de 60 s, sin CORS, el log de seguridad no existía) | Hecho | `config/settings/production.py`; CP-SEC16-01..06 |
| SEC-17 | `check --deploy` | Falta (nunca corrido; 11 advertencias de drf-spectacular) | Hecho | `docs/sprint-5/check-deploy.txt`; CP-SEC17-01 |
| SEC-18 | Log de seguridad | Falta | Hecho | `common/security.py`, `common/security_receivers.py`; CP-SEC18-01..14 |
| SEC-19 | `.env.example` | Parcial (solo el panel, incompleto) | Hecho | `.env.example` en los tres repos; CP-SEC19-01, 02 |
| HU-041 | US-041 E1–E10 | Parcial (E9 leía fotos versionadas, sin informe; pesos sin verificación) | Hecho | CP-041-01..41 |
| HU-042 | US-042 E1–E9 + apelación | Parcial (E9 no implementado por decisión previa) | Hecho | CP-042-01..43, M01..M04, P01 |
| HU-046-E7 | US-046 E7 | Parcial (comportamiento y test, sin caso propio) | Hecho | CP-046-07 |
| HU-VIS | Visibilidad única 6.1 | Parcial (validación repetía filtros; inactivos abribles por id; denuncias sobre retenidos; el panel mostraba la imagen en revisión) | Hecho (con la excepción declarada del panel) | `reports/models.py::publicly_visible_condition`; CP-VIS-00..06 |
| HU-021 | US-021 E1–E10 | Hecho | Hecho | CP-021-01..48, M01..M11 |
| HU-043 | US-043 E1–E11 + antiabuso | Parcial (la foto de la apelación no se podía denunciar; sin throttling ni log) | Hecho (E5 con desvío decidido) | CP-043-01..75, M01..M12, P01..P13; CP-SEC03-03/04; CP-SEC18-09 |
| HU-026 | US-026 E1–E9 | Parcial (E9 medido con 800 filas, sin volumen) | Hecho | CP-026-01..15; `benchmark-us026.md` |
| HU-032 | US-032 E1–E9 | Hecho | Hecho | CP-032-01..18, M01..M10 |
| HU-015 | US-015 E1–E10 | Parcial (sin selector de proveedor ni proveedor nulo) | Hecho | CP-015-01..41, P01..P08 |
| QA-01 | Suites en verde | Hecho (app con timeouts en frío) | Hecho | §10 |
| QA-02 | Linters y tipado | Parcial (341 hallazgos de ruff; la app sin ESLint) | Hecho (1 aviso de ESLint en la app) | §14 |
| QA-03 | Sin migraciones pendientes | Hecho | Hecho | `makemigrations --check --dry-run`: "No changes detected" |
| QA-04 | Pruebas de componente | Parcial (pantallas de cuenta de la app y login del panel sin tests) | Hecho | `RateLimitedAuthScreens.test.tsx`, `LoginPage.test.tsx` |
| QA-05 | Invariantes 2.4 | Parcial | Parcial | Ver §5 (confirmación ciudadana) |

---

## 4. Trabajo realizado por ítem

Commits en `feature/sprint-5`, sin push (ver §19).

### Backend

| Commit | Mensaje | Ítems | Archivos principales | Tests agregados |
| --- | --- | --- | --- | --- |
| `af2e35e` | feat(security): add rate limits, trusted proxies and a security event log | SEC-01..04, 14, 18 | `config/settings/{base,local,production,test}.py`, `common/security.py`, `common/security_receivers.py`, `common/throttling.py`, `reports/{complaints,privacy}.py`, `reports/api/views.py`, `users/apps.py` | `common/tests/test_rate_limits.py` (18), `test_security_log.py` (16) |
| `a89d42b` | fix(deps): bump Django, DRF, Pillow and transitive packages with known CVEs | SEC-11 (hallazgos) | `pyproject.toml`, `uv.lock` | — |
| `d79cec0` | style: clear the ruff and bandit findings the CI gate will enforce | QA-02, SEC-11 | 59 archivos (182 códigos HTTP a `HTTPStatus`, `__str__` de `Comment` y `Like`, `usedforsecurity=False`) | — |
| `7686b40` | ci: gate every PR on ruff, bandit, pip-audit, gitleaks, pytest and migrations | SEC-11, SEC-15 | `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.gitleaksignore` | — |
| `6d5b6ec` | chore(anonymization): move the benchmark photos out of the repository | HU-041 E9, SEC-06..08 | `.gitignore`, `.dockerignore`, `benchmark_anonymization.py`, `detectors.py`, `tests/images.py`, `compose/production/django/Dockerfile` | `test_benchmark.py` (6); `test_upload.py` y `test_service.py` adaptados |
| `43f84ac` | feat(anonymization): strip profile photo metadata and reprocess legacy photos | SEC-09, SEC-10, HU-042 E9 | `anonymization/{fields,service,pipeline}.py`, `anonymize_existing_photos.py`, `strip_image_metadata.py`, `users/models.py`, migración `users/0009` | `test_retroactive.py` (12) |
| `e2d19b4` | feat(reports): let anyone report the photo of an appeal as personal data | HU-043 E1, HU-VIS | `reports/{models,privacy,admin}.py`, `api/{views,serializers,panel_serializers,privacy_serializers}.py`, `notifications/services.py`, migración `reports/0014` | `test_privacy_appeal_and_admin.py` (13) |
| `a3d5c47` | fix(reports): apply the single visibility rule to every point of section 6.1 | HU-VIS, DEF-20, DEF-22 | `reports/models.py`, `api/validation_views.py`, `complaints.py` | `test_visibility_sweep.py` (19) |
| `7a7e20a` | feat(settings): harden production and pass check --deploy with no warnings | SEC-16, 17, 19 | `production.py`, `.env.example`, 6 vistas (esquema OpenAPI) | `test_production_settings.py` (7), `test_env_example.py` (2) |
| `b947f49` | feat(reports): pick the vision provider by name, with a null provider by default | HU-015 | `reports/vision.py`, `retry_resolution_comparisons.py`, settings, `.envs/.local/.django` (con la clave vacía) | `test_vision_provider.py` (5) |
| `e301d40` | test(reports): measure duplicate detection and blurring at realistic volume | HU-026 E9 | `benchmark_duplicate_detection.py`, `docs/sprint-5/benchmark-us026.md`, `rendimiento-us041.md` | 1 en `test_duplicates.py` |
| `a8fd8b5` | test(anonymization): turn the scenario 8 measurement into a command | HU-041 E8 | `measure_anonymization.py` | 1 en `test_benchmark.py` |
| `7b37095` | test: tag every Sprint 5 scenario test with its CP case id | trazabilidad | 13 archivos de test (276 tests marcados) | — |
| `28e4c9e` | docs(readme): document the Sprint 5 security controls and the new commands | documentación | `README.md` | 1 (CP-SEC18-14) |
| `265bccb` | docs(sprint-5): add the scenario to case to test traceability table | trazabilidad | `docs/sprint-5/TRAZABILIDAD.md` | — |

Además, `BITACORA.md` y este reporte van en un último commit de documentación.

### Panel

| Commit | Mensaje | Ítems | Tests |
| --- | --- | --- | --- |
| `4b20600` | fix(deps): apply npm audit fix to clear known advisories | SEC-12 | — |
| `a5deb8e` | ci(panel): run ESLint, tsc, npm audit, gitleaks and Vitest on every PR | SEC-12, 15 | — (`scripts/audit-gate.mjs`, `audit-allowlist.json`) |
| `61e86bf` | feat(panel): name and show the appeal photo in the privacy inbox (US-043) | HU-043 E1/E11 | 2 |
| `2b8287c` | feat(panel): explain a 429 instead of showing allauth's English message | SEC-05 | 5 (`client.test.ts` 3, `LoginPage.test.tsx` 2) |
| `99e5c8f` | docs(env): document API_UPSTREAM and BACKEND_NETWORK in .env.example | SEC-19 | — |
| `939f371`, `0e4c449` | test(panel): CP ids | trazabilidad | — |

### App

| Commit | Mensaje | Ítems | Tests |
| --- | --- | --- | --- |
| `033abd7` | chore(mobile): add ESLint and align the Expo SDK 57 patch versions | SEC-13, QA-02 | tests existentes ajustados al lint |
| `fef6f01` | ci(mobile): run ESLint, tsc, npm audit, gitleaks and Jest on every PR | SEC-13, 15 | — |
| `8d75291` | feat(mobile): let anyone report the photo of an appeal (US-043) | HU-043 E1/E11 | 3 |
| `c27729b` | feat(mobile): explain a 429 instead of blaming the credentials | SEC-05, QA-04 | 9 |
| `8ad9726` | docs(env): add .env.example | SEC-19 | — |
| `58a6bf0`, `85dbc8d` | test(mobile): CP ids | trazabilidad | — |

**Tests existentes modificados (regla 1):**
- `src/api/__tests__/reports.test.ts`: `requestPrivacyReview(7, 3)` pasó a `requestPrivacyReview(7, { evidence: 3 })` porque la firma cambió para admitir la foto de la apelación.
- Dos fixtures de `ReportDetailThread.test.tsx` y uno de `ResolutionThread.test.tsx` suman el campo nuevo `photo_removed_at`.
- `test_comparison.py::test_the_images_directory_exists` se eliminó: verificaba que las fotos del benchmark estuvieran en el repo, que es justo lo que ya no corresponde.
- Los tests de US-041 que usaban fotos reales sin necesitarlas pasaron a fotos sintéticas.
- `test_vision_provider.py::test_it_is_the_default` lee la configuración en un proceso limpio, porque el entorno local ahora activa Gemini.

Ninguno se debilitó.

---

## 5. Decisiones tomadas

Las cuatro primeras se consultaron con el usuario durante la sesión. ⚠️ indica que contradicen el texto de una historia, del documento de instrucciones o del de Seguridad, y que esa documentación hay que corregirla.

| # | Decisión | Alternativa descartada | Motivo |
| --- | --- | --- | --- |
| 1 ⚠️ | La validación colectiva sigue contando **me gusta**; no hay entidad "confirmación ciudadana" | Crear `Confirmation` (unicidad reporte + usuario) y un botón nuevo | Es lo que dicen US-040 y US-032 ("si el me gusta es lo que valida un reporte en US-040…"). Decisión del equipo. **Corregir el punto 2.4 de las instrucciones.** El "sumarse" de US-032 registra el me gusta, que ya computa para el umbral, así que el default del punto 4 se cumple sin cambios |
| 2 ⚠️ | El panel **sigue listando** reportes con la imagen en procesamiento, fallida, retenidos por dato personal, cancelados y archivados | Que el panel aplique `publicly_visible` | El agente gestiona esos reportes; decisión previa del equipo para US-042. Lo que el panel **nunca** devuelve es una imagen sin procesar ni la que está en revisión (CP-VIS-02..06). **Contradice la lista del 6.1** |
| 3 ⚠️ | Eliminar la foto **del reporte** por US-043 retira el reporte entero, para siempre | Republicarlo sin imagen (escenario 5) | Decisión previa del equipo: "no se debe publicar ningún reporte sin foto". **Corregir el escenario 5 de US-043.** La foto de un cierre o de una apelación se retira sola, como pide el escenario 11 |
| 4 | El historial de git **no** se reescribe por ahora | Reescribir `068c0c5` y hacer force-push | Operación destructiva; el equipo decide (§19) |
| 5 | Detección de duplicados con Haversine + caja delimitadora + índice parcial B-tree `(municipality, category, latitude, longitude)` | PostGIS | Default del punto 4, ya implementado en US-026. Medido con 100.000 reportes (§16) |
| 6 | "Sumarse" = me gusta (ver decisión 1) | Confirmación + me gusta | Ver decisión 1 |
| 7 | Candidatos a duplicado: reportes en estado activo y no retirados, **incluidos** los que tienen la imagen en procesamiento o una revisión por dato personal en curso | Solo los visibles públicamente más los del propio usuario (default del punto 4) | Excluirlos permitía publicar dos veces el mismo bache. Lo que viaja en el `409` es la tarjeta del existente, que oculta la foto si no está procesada. **Difiere del default del punto 4**; ya estaba documentado en el README (US-042, "Límites conocidos") |
| 8 | Resolución de solicitudes por dato personal **en el admin de Django y en el panel**, con los mismos servicios (`privacy.remove_image` / `dismiss`) | Solo uno de los dos canales | El panel ya tenía la bandeja; el punto 4 pide el admin de Django. Las dos llaman a la misma capa de servicio |
| 9 | Detectores YuNet 2023mar (MIT) y YOLOv9-s 608 de patentes (MIT), **versionados en el repo** y verificados por SHA-256 al cargar y al construir la imagen de producción | Bajarlos en el build de Docker | En desarrollo `/app` es un bind mount que taparía lo bajado en el build; versionarlos evita además depender de la red al construir. La verificación de checksum que pide el punto 4 está en los dos lugares |
| 10 | Rendimiento medido en el Docker de desarrollo (Mac M, 10 CPU) | — | Default del punto 4. **El equipo decide si es representativo** |
| 11 | `DJANGO_VISION_PROVIDER` vacío = proveedor nulo; `openai_compatible` = Gemini (elegido por el equipo en US-015), activado solo en `.envs/.local/.django` | Que el adaptador quedara activo por default | Default del punto 4. Producción arranca sin enviar fotos a nadie |
| 12 | `anonymize_existing_photos` y `strip_image_metadata` implementados y **no ejecutados**; sin `--apply` solo cuentan | Correrlos | Regla 5 de las instrucciones |
| 13 ⚠️ | Login fallido: **5 por cuenta en 15 minutos con ventana deslizante** + 10 por minuto por IP | "5 en 5 minutos con bloqueo de 15" (documento de Seguridad) | Default del punto 4. allauth no tiene "bloqueo de N minutos": cuenta los intentos de la ventana. **Corregir el documento de Seguridad** |
| 14 | Reenvío de confirmación: `1/3m/key,3/h/key` | Solo `3/h/key` | Se conservó la espera de 3 minutos entre envíos que trae allauth |
| 15 | allauth headless responde el bloqueo de login con **400** y el reenvío limitado con **403**; un middleware los convierte en **429** | Dejar los códigos de allauth | El punto 5.1 pide 429 |
| 16 | Una denuncia con motivo dato personal consume el cupo de denuncias **y** el de dato personal, por los dos endpoints | Cupos separados por endpoint | Si no, una cuenta ocultaría el doble de reportes |
| 17 | `NUM_PROXIES` por defecto **0** | `None` (default de DRF) | Con `None` el ident del throttle es el `X-Forwarded-For` entero, que controla el cliente |
| 18 | Redis del cache sin `IGNORE_EXCEPTIONS`: si Redis cae, el login falla | Ignorar errores del cache (como hacía producción) | Ignorarlos dejaba los límites sin contar |
| 19 | El log guarda una **huella SHA-256 truncada** de la cuenta en un login fallido, no el correo | Guardar el correo escrito | Si alguien escribió la contraseña en el campo del correo, quedaría en el archivo |
| 20 | El panel retiene **solo** la imagen denunciada (`photo: null`) mientras la solicitud está pendiente | Ocultar el reporte entero al agente | Ver decisión 2 |
| 21 | Un tercero ya **no** abre por id un reporte Cancelado o Archivado | Mantenerlo abierto "porque ahí lleva el aviso" | El aviso de cambio de estado solo le llega al autor, que lo sigue viendo. Es lo que pide el 6.1 |
| 22 | HEIC: el backend no lo acepta (Pillow sin `pillow-heif` responde 400); la app reencodea a JPEG en alta, edición, cierre y apelación | Agregar `pillow-heif` | Ningún HEIC llega a guardarse con metadatos. El avatar no se reencodea en la app (con recorte, iOS entrega JPEG) |
| 23 | pip-audit falla ante **cualquier** vulnerabilidad | Filtrar por "alta o crítica" | pip-audit no informa la severidad; fallar ante todas es más estricto. Una excepción se agrega con `--ignore-vuln` y su motivo |
| 24 | `npm audit --audit-level=high` con excepciones revisadas (`audit-allowlist.json` + `scripts/audit-gate.mjs`) | `npm audit` a secas | `braces` y `node-forge` no tienen versión corregida publicada y solo llegan a herramientas de desarrollo. La lista falla si una excepción deja de hacer falta |
| 25 | Ruff en CI corre `check`, no `format --check` | Exigir formato | El repo nunca se formateó entero (47 archivos) y `ruff format` reescribe `except (A, B)` con la sintaxis de 3.14. Queda como observación |
| 26 | ESLint en la app con `eslint-config-expo` (ESLint 9) y 10 excepciones por línea justificadas de las reglas del React Compiler | Desactivar las reglas | Regla 2. Cada `setState` en efecto que quedó es una sincronización con algo externo |
| 27 | Identificadores `CP-<historia>-nn` para el backend, `-Mnn` para la app y `-Pnn` para el panel | Numeración única | US-043 tiene 75 casos de backend; un solo rango numérico chocaba |
| 28 | Las fotos del benchmark (Commons) se usan como set provisorio | No medir | El equipo todavía no dejó el set propio. Se bajaron en una sesión anterior, contra la indicación de no bajar fotos de personas (OBS-S5-02) |

---

## 6. Cambios al modelo de datos

| Entidad | Situación | Campos agregados o cambiados | Relaciones | Restricciones |
| --- | --- | --- | --- | --- |
| `ReportComplaint` | Modificada (`reports/0014`) | `resolution_appeal` (FK nula) | → `ResolutionAppeal` (CASCADE, `related_name="complaints"`) | `unique_pending_complaint_per_image` ahora sobre `(reporter, report, resolution_evidence, resolution_appeal, reason)` cuando `status='pendiente'`, `nulls_distinct=False`. **Nueva** `complaint_targets_one_image`: evidencia o apelación, nunca las dos |
| `ResolutionAppeal` | Modificada (`reports/0014`) | `photo_removed_at` (fecha, nula) | — | — |
| `User` | Modificada (`users/0009`) | `avatar` pasa a `MetadataFreeImageField` (misma columna; sin cambio de esquema) | — | — |
| `Comment`, `Like` | Modificadas (sin migración) | `__str__` | — | — |

Propiedades nuevas, sin columna: `ReportComplaint.target` y `ReportComplaint.image_kind` (`report` | `resolution_evidence` | `resolution_appeal`).

Entidades heredadas del sprint que el diagrama tiene que incluir si todavía no las tiene: `PendingPhotoMixin` (abstracta: `photo_pending`, `photo_status`, `photo_attempts`, `photo_failed_at`, `photo_queued_at`) heredada por `Report`, `ResolutionEvidence` y `ResolutionAppeal`; `ResolutionComparison`; `ReportComplaint`.

---

## 7. Estados

### Procesamiento de imagen (`PhotoStatus`), por foto

```
            alta / reemplazo / cierre / apelación
                        │
                        ▼
                  ┌───────────┐  tarea anonymize_photo OK   ┌───────────┐
   reencolado ──► │ pendiente │ ──────────────────────────► │ procesada │
  (beat 15 min)   └───────────┘                             └───────────┘
                        │ reintentos agotados o archivo ilegible   ▲
                        ▼                                          │
                  ┌───────────┐  el autor sube otra foto           │
                  │  fallida  │ ──► pendiente ─────────────────────┘
                  └───────────┘

 procesada (photo_attempts = 0, anterior a US-041)
        ── anonymize_existing_photos --apply ──► procesada (attempts = 1)
                                             └─► fallida (si no se puede procesar)
```

| Transición | Disparador |
| --- | --- |
| (nueva) → pendiente | El ciudadano crea el reporte o reemplaza la foto, el operario cierra, el autor apela (API) |
| pendiente → procesada | Tarea de Celery `anonymize_photo` |
| pendiente → pendiente (reintento) | La misma tarea, con espera exponencial (`DJANGO_ANONYMIZATION_RETRY_BASE_SECONDS`) |
| pendiente → fallida | La tarea agota `DJANGO_ANONYMIZATION_MAX_RETRIES`, o el archivo es ilegible (sin reintentos) |
| pendiente → reencolada | Tarea periódica `requeue_stale_pending_photos` (cada 15 min, pasado `DJANGO_ANONYMIZATION_STALE_MINUTES`) |
| fallida → pendiente | El autor vuelve a cargar la foto |
| procesada (legado) → procesada / fallida | `manage.py anonymize_existing_photos --apply` (lo ejecuta una persona; nunca se corrió) |

### Solicitud por dato personal (`ReportComplaint.Status`)

`pendiente` → `imagen_eliminada` (administrador: "Eliminar la imagen", panel o admin de Django) · `pendiente` → `desestimada` (administrador: "Desestimar"). Las de contenido de US-021 quedan en `pendiente` hasta US-049.

### Máquina de estados del reporte

**No cambió.** `reports/state_machine.py` solo recibió un cambio de import de tipado (`Callable` bajo `TYPE_CHECKING`); `services.apply_transition` solo un comentario `noqa: C901` justificado. Los tests de la máquina de estados pasan sin modificaciones de comportamiento.

---

## 8. API

| Método y ruta | Cambio | Permisos | Respuestas | Ejemplo de error |
| --- | --- | --- | --- | --- |
| `POST /api/reports/` | Modificado: límite de 20 por hora | Ciudadano autenticado | 201, 400, 409 `report_already_exists`, **429** | `{"code": "throttled", "detail": "Hiciste demasiadas solicitudes seguidas. Probá de nuevo en 37 minutos.", "retry_after": 2210}` |
| `POST /api/reports/{id}/comments/` | Modificado: 60 por hora | Ciudadano | 201, 404, **429** | ídem |
| `POST /api/reports/{id}/complaints/` | Modificado: 10 por día (+ 5 por día si el motivo es `dato_personal`); un reporte retenido por dato personal rechaza denuncias de contenido | Ciudadano, no el autor | 201, 400, 403, 404, 409 (`complaint_already_filed`, `report_not_public`, `image_already_removed`), **429** | `{"code": "report_not_public", "detail": "Este reporte no está publicado en este momento."}` |
| `POST /api/reports/{id}/privacy-request/` | **Modificado**: acepta `appeal` (id de la apelación) además de `evidence`; el acuse trae `appeal`; 5 por día y 10 por día | Cualquier ciudadano autenticado | 201, 400 (imagen ajena o dos imágenes), 404, 409, **429** | `{"appeal": ["La imagen no pertenece a este reporte."]}` |
| `GET /api/reports/{id}/` | **Modificado (incompatible para terceros)**: un Cancelado o Archivado responde 404 a quien no es el autor. `resolution_appeals[].photo_removed_at` nuevo | Autenticado | 200, 404 | — |
| `GET /api/panel/reports/{id}/` | Modificado: `photo: null` para la imagen en revisión por dato personal (reporte, cierre o apelación); `resolution_appeals[].photo_removed_at` | Agente (su jurisdicción) | 200, 403, 404 | — |
| `GET /api/platform/privacy-requests/` | Modificado: `image.kind` admite `resolution_appeal`; nuevo `image.appeal_id` | Administrador de la plataforma | 200, 403 | — |
| `POST /_allauth/app/v1/auth/login` | Modificado: 6.º intento fallido por cuenta en 15 min → **429** (antes 400) | Público | 200, 400, 401, **429** | `{"status": 429, "errors": [{"code": "too_many_login_attempts", "message": "Too many failed login attempts. Try again later."}]}` |
| `POST /_allauth/app/v1/auth/password/request` | 4.º pedido por cuenta en una hora → 429 | Público | 200, 400, **429** | página 429 de allauth (sin JSON) |
| `PUT /_allauth/app/v1/account/email` | Reenvío limitado → **429** (antes 403) | Autenticado | 200, **429** | — |
| `POST /_allauth/app/v1/auth/signup` | 20 por hora por IP → 429 | Público | 200, 400, **429** | — |

**Cambios incompatibles:**
- Un tercero ya no abre por id un reporte Cancelado o Archivado.
- El bloqueo de login y el reenvío limitado de la confirmación cambian su código de estado (400 y 403 pasan a 429).
- En la app, `requestPrivacyReview` recibe un objeto (`{ evidence }` o `{ appeal }`). Es interno al cliente.

**Comandos de gestión nuevos:** `benchmark_anonymization [CARPETA] --report`, `measure_anonymization`, `anonymize_existing_photos [--apply]`, `strip_image_metadata [--apply]`, `benchmark_duplicate_detection --reports N`.

---

## 9. Interfaces

| Canal | Pantalla | Cambio | Componente |
| --- | --- | --- | --- |
| App | Detalle del reporte | La foto de una objeción muestra "Denunciar foto" (para cualquier ciudadano que no sea cuenta de trabajo), "Imagen retirada" si se retiró y el estado de procesamiento | `urbancheck_mobile/app/(app)/(tabs)/report/[id].tsx` |
| App | Login | El bloqueo por intentos dice "Demasiados intentos · Esperá unos minutos…", no "Email o contraseña incorrectos" | `app/(auth)/login.tsx` |
| App | Registro | El tope por IP se explica | `app/(auth)/register.tsx` |
| App | Recuperar contraseña | El tope por cuenta se explica | `app/(auth)/forgot-password.tsx` |
| App | Restablecer contraseña | El tope se explica | `app/reset-password.tsx` |
| App | Cambiar contraseña | El tope se explica | `app/change-password.tsx` |
| App | Cualquier formulario (reporte, comentario, denuncia) | Ante un 429, alerta "Demasiados intentos" con el tiempo de espera del servidor | `src/api/errors.ts` (`describeApiError`) |
| Panel | Login | El bloqueo muestra el aviso en castellano | `urbanchech_frontend/src/routes/pages/LoginPage.tsx` |
| Panel | Bandeja de protección de datos | Nombra "Foto de la objeción del vecino" y confirma "La foto de la objeción se eliminó; el reporte sigue publicado." | `src/features/privacy/PrivacyRequestsPage.tsx`, `components/PrivacyRequestsTable.tsx` |
| Panel | Detalle del reporte | La foto en revisión no se muestra; la de una objeción retirada se muestra como retirada | `src/features/reports/ReportDetailPage.tsx`, `components/ResolutionThread.tsx` |
| Admin de Django | Denuncias (`/<DJANGO_ADMIN_URL>/reports/reportcomplaint/`) | Columnas "imagen", "vence" y "fuera de plazo"; filtro "plazo"; acciones "Eliminar la imagen denunciada" y "Desestimar" (solo administrador de la plataforma) | `urbancheck_backend/urbancheck/reports/admin.py::ReportComplaintAdmin` |
| Admin de Django | Usuarios | La foto de perfil se guarda sin metadatos | `users/admin.py` (sin cambios de pantalla) |

---

## 10. Testing

### Por historia

Todos los casos se ejecutaron el 15/10/2026. "Aprobado con observación" = pasa en local, pero depende del set de referencia no versionado y en CI se saltea.

| Historia | Casos | Aprobados | Aprobados con observación | Fallidos | No verificables |
| --- | --- | --- | --- | --- | --- |
| US-041 | 41 | 34 | 7 (CP-041-01..07, detección sobre fotos reales) | 0 | 0 |
| US-042 | 48 (43 back + 4 app + 1 panel) | 48 | 0 | 0 | 0 |
| US-046 E7 | 1 | 1 | 0 | 0 | 0 |
| Visibilidad 6.1 | 7 (19 ejecuciones parametrizadas) | 7 | 0 | 0 | 0 |
| US-021 | 58 (48 + 10 app) | 58 | 0 | 0 | 0 |
| US-043 | 99 (75 + 11 app + 13 panel) | 99 | 0 | 0 | 0 |
| US-026 | 15 | 15 | 0 | 0 | 0 |
| US-032 | 28 (18 + 10 app) | 28 | 0 | 0 | 0 |
| US-015 | 47 (41 + 6 panel) | 47 | 0 | 0 | 0 |

Las pruebas manuales en dispositivo que exige la DoD están en §18 y no entran en esta tabla.

### Trazabilidad escenario → caso → archivo (resumen)

La tabla fila por fila, con el nombre de cada test, está en `TRAZABILIDAD.md`.

| Historia | Escenario | Casos | Archivos |
| --- | --- | --- | --- |
| US-041 | E1 | CP-041-01..03 | `anonymization/tests/test_service.py` |
| | E2 | CP-041-04 | `test_service.py` |
| | E3 | CP-041-05..07 | `test_service.py` |
| | E4 | CP-041-08 | `test_service.py` |
| | E5 | CP-041-09..12 | `test_service.py` |
| | E6 | CP-041-13..20 | `test_upload.py`, `test_deferred_publication.py`, `test_service.py` |
| | E7 | CP-041-21..25 | `test_upload.py`, `test_deferred_publication.py` |
| | E8 | CP-041-26, 27 | `test_service.py`, `test_benchmark.py` |
| | E9 | CP-041-28..31 | `test_benchmark.py` |
| | E10 | CP-041-32..36 | `test_service.py` |
| | Metadatos, modelos, fallos | CP-041-37..41 | `test_service.py`, `test_benchmark.py` |
| US-042 | E1 | CP-042-01..03 | `test_deferred_publication.py`, `test_photo_processing_visibility.py` |
| | E2 | CP-042-04..08 | `test_photo_processing_visibility.py` |
| | E3 | CP-042-09..11, M01, M03 | ídem, `CreateReportScreen.test.tsx`, `ProfileScreen.test.tsx` |
| | E4 | CP-042-12..14 | `test_deferred_publication.py` |
| | E5 | CP-042-15..19, M04 | ídem, `ProfileScreen.test.tsx` |
| | E6 | CP-042-20..24, P01 | `test_photo_processing_visibility.py`, `ReportDetailPage.test.tsx` |
| | E7 | CP-042-25..28, M02 | ídem, `CreateReportScreen.test.tsx` |
| | E8 | CP-042-29..31 | `test_deferred_publication.py` |
| | E9 | CP-042-32..36 | `test_retroactive.py` |
| | Apelación (ampliación) | CP-042-37 | `test_upload.py` |
| US-046 | E7 | CP-046-07 | `test_upload.py` |
| US-021 | E1 | CP-021-01..10, M04, M05 | `test_complaints.py`, `ComplaintModal.test.tsx` |
| | E2 | CP-021-11..14, M01 | ídem |
| | E3 | CP-021-15..18, M06, M07 | ídem |
| | E4 | CP-021-19, 20, M02, M03 | ídem |
| | E5 | CP-021-21..26, M11 | `test_complaints.py`, `PrivacyReview.test.tsx` |
| | E6 | CP-021-27..33, M08 | `test_complaints.py`, `ComplaintModal.test.tsx` |
| | E7 | CP-021-34, M09 | `test_complaints.py`, `PrivacyReview.test.tsx` |
| | E8 | CP-021-35..37, M10 | ídem |
| | E9 | CP-021-38..47 | `test_complaints.py` |
| | E10 | CP-021-48 | `test_complaints.py` |
| US-043 | E1 | CP-043-01..12, M04, M07, P07 | `test_privacy_requests.py`, `test_privacy_appeal_and_admin.py`, `PrivacyReview.test.tsx`, `PrivacyRequestsPage.test.tsx` |
| | E2 | CP-043-13..22, M02, M09, M11 | `test_privacy_requests.py`, `PrivacyReview.test.tsx` |
| | E3 | CP-043-23, 24, M03 | ídem |
| | E4 | CP-043-25..29, P06, P08, P13 | `test_privacy_requests.py`, `PrivacyRequestsPage.test.tsx` |
| | E5 | CP-043-30..43, M10, P04, P05, P09, P11 | `test_privacy_requests.py`, `test_privacy_appeal_and_admin.py`, `PrivacyReview.test.tsx`, `ReportDetailPage.test.tsx`, `PrivacyRequestsPage.test.tsx` |
| | E6 | CP-043-44..48, M12, P10 | ídem |
| | E7 | CP-043-49..52, P08 | `test_privacy_requests.py`, `test_privacy_appeal_and_admin.py`, `PrivacyRequestsPage.test.tsx` |
| | E8 | CP-043-53..55, P12 | `test_privacy_requests.py`, `PrivacyRequestsPage.test.tsx` |
| | E9 | CP-043-56..58, M05 | `test_privacy_requests.py`, `PrivacyReview.test.tsx` |
| | E10 | CP-043-59..65, P03 | `test_privacy_requests.py`, `test_privacy_appeal_and_admin.py`, `ReportDetailPage.test.tsx` |
| | E11 | CP-043-66..70, M06, M08, P01, P02 | `test_privacy_requests.py`, `test_privacy_appeal_and_admin.py`, `PrivacyReview.test.tsx`, `ResolutionThread.test.tsx` |
| | Antiabuso | CP-SEC03-03, CP-SEC03-04, CP-SEC18-09 | `common/tests/test_rate_limits.py`, `test_security_log.py` |
| US-026 | E1–E7 | CP-026-01..10 | `test_duplicates.py` |
| | E8 | CP-026-11, 12 | `test_duplicate_reports.py` |
| | E9 | CP-026-13..15 | `test_duplicates.py` |
| US-032 | E1 | CP-032-01..05, M01, M02, M07 | `test_duplicate_reports.py`, `ExistingReportModal.test.tsx`, `CreateReportScreen.test.tsx` |
| | E2 | CP-032-06, M03, M08 | ídem |
| | E3 | CP-032-M04, M09 | `ExistingReportModal.test.tsx`, `CreateReportScreen.test.tsx` |
| | E4 | CP-032-07, M05 | ídem |
| | E5 | CP-032-08, M06, M10 | ídem |
| | E6 | CP-032-09..14 | `test_duplicate_reports.py` |
| | E7 | CP-032-15, 16 | `test_duplicate_reports.py` |
| | E8 | CP-032-17 | `test_duplicate_reports.py` |
| | E9 | CP-032-18 | `test_duplicate_reports.py` |
| US-015 | E1 | CP-015-01..03 | `test_comparison.py` |
| | E2 | CP-015-04, P01, P02 | `test_comparison.py`, `ResolutionComparisonCard.test.tsx` |
| | E3 | CP-015-05..08, P04, P06, P07 | `test_comparison.py`, `ResolutionComparisonCard.test.tsx`, `ReportsTable.test.tsx`, `ReportFilters.test.tsx` |
| | E4 | CP-015-09, 10, P03 | ídem |
| | E5 | CP-015-11..16, P05 | `test_comparison.py`, `ResolutionComparisonCard.test.tsx` |
| | E6 | CP-015-17, 18, P05 | ídem |
| | E7 | CP-015-19, P08 | `test_comparison.py`, `ResolutionThread.test.tsx` |
| | E8 | CP-015-20, 21 | `test_comparison.py` |
| | E9 | CP-015-22, P01 | ídem |
| | E10 | CP-015-23 | `test_comparison.py` |
| | Proveedor, cliente, reintento | CP-015-24..41 | `test_vision_provider.py`, `test_comparison.py` |
| 6.1 | Barrido | CP-VIS-00..06 | `reports/tests/test_visibility_sweep.py`, `test_privacy_appeal_and_admin.py` |

### Tests agregados y totales

| Repo | Línea base | Final | Agregados |
| --- | --- | --- | --- |
| Backend | 1409 + 1 xfail | 1509 + 1 xfail | +100 (y 1 eliminado, ver §4) |
| Panel | 328 | 335 | +7 |
| App | 371 | 383 | +12 |

### Cobertura

| Repo | Herramienta | Líneas | Sentencias | Ramas | Funciones |
| --- | --- | --- | --- | --- | --- |
| Backend | `coverage run -m pytest` | **97 %** (4993 sentencias, 148 sin cubrir) | — | sin dato (no se mide por rama) | — |
| Panel | `vitest --coverage` | 89,87 % | 88,43 % | 83,53 % | 82,87 % |
| App | `jest --coverage` | 76,07 % | 74,29 % | 70,35 % | 66,66 % |

Módulos nuevos o tocados del backend: `vision.py`, `detectors.py`, `fields.py`, `complaints.py` y `duplicates.py` al 100 %; `models.py` 97 %; `service.py` 96 %; `security.py` 96 %; `privacy.py` 95 %; `throttling.py` 93 %; `pipeline.py` 92 %; `comparison.py` 85 %.

### Pruebas de seguridad (no funcionales)

| Control | Casos | Archivo |
| --- | --- | --- |
| 5.1 Cache compartido | CP-SEC01-01 | `common/tests/test_security_log.py` |
| 5.1 Límites de allauth (6.º intento → 429, contraseña correcta bloqueada, por cuenta, mensaje genérico, recuperación, reenvío, registro) | CP-SEC02-01..07 | `common/tests/test_rate_limits.py` |
| 5.1 Throttling de DRF (11.ª denuncia, por usuario, 6.ª solicitud que no oculta, cupo por los dos endpoints, comentarios, lectura libre, 21.º reporte, tasa por configuración) | CP-SEC03-01..08 | `test_rate_limits.py` |
| 5.1 Proxies (dos XFF, dos contadores; conteo desde la derecha; XFF ignorado sin proxies) | CP-SEC04-01..03 | `test_rate_limits.py` |
| 5.1 429 en clientes | CP-SEC05-M01..M09, P01..P05 | `RateLimitedAuthScreens.test.tsx`, `errors.test.ts`, `client.test.ts`, `LoginPage.test.tsx` |
| 5.2 Metadatos por punto de carga (GPSInfo 34853, EXIF, XMP, IPTC) | CP-041-13..16, CP-SEC09-01..04, CP-SEC10-01..03 | `test_upload.py`, `test_retroactive.py` |
| 5.4 Argon2id | CP-SEC14-01, 02 | `test_security_log.py` |
| 5.4 Producción | CP-SEC16-01..06 | `common/tests/test_production_settings.py` |
| 5.4 `check --deploy` | CP-SEC17-01 | ídem |
| 5.5 Log de seguridad | CP-SEC18-01..14 | `test_security_log.py` |
| Regla 7 `.env.example` | CP-SEC19-01, 02 | `common/tests/test_env_example.py` |
| 5.3 Pipeline | Cada herramienta corrida localmente (§14) | `.github/workflows/ci.yml` (×3) |

---

## 11. Defectos encontrados

| ID | Historia | Descripción | Severidad | Causa | Corrección | Test que lo fija |
| --- | --- | --- | --- | --- | --- | --- |
| DEF-20 | US-021 / 6.1 | Un reporte oculto por una solicitud de dato personal aceptaba denuncias de contenido de terceros | Media | `complaints/` deja pasar los reportes retenidos para que el denunciante reciba "ya lo denunciaste"; la excepción alcanzaba también a los motivos de contenido | `complaints.file_complaint` rechaza con `report_not_public` (`a3d5c47`) | CP-VIS-01 [revision_dato_personal] |
| DEF-21 | US-043 | La foto de una apelación no se podía denunciar (el escenario 1 nombra tres imágenes) | Alta | `ReportComplaint` solo apuntaba al reporte o a una evidencia | FK `resolution_appeal`, servicio, vista, panel y app (`e2d19b4`, `61e86bf`, `8d75291`) | CP-043-10..12, 67, 68, M07, M08, P02, P07 |
| DEF-22 | 6.1 | Un tercero podía abrir por id un reporte Cancelado o Archivado | Baja | `visible_to` los habilitaba "para el aviso del cambio de estado", que solo recibe el autor | `visible_to` usa la condición única (`a3d5c47`) | CP-VIS-01 [cancelado, archivado], CP-VIS-05 |
| DEF-23 | 6.1 / US-043 | El panel mostraba al agente la imagen que estaba en revisión por dato personal | Media | El detalle del panel no filtraba por solicitudes pendientes | `PanelReportDetailSerializer.to_representation` (`e2d19b4`) | CP-VIS-02..04, CP-VIS-06 |
| DEF-24 | 6.1 | La bandeja de validación repetía a mano tres condiciones de visibilidad | Baja (riesgo de divergencia) | Filtros copiados en lugar de la función única | `Report.objects.publishable()` (`a3d5c47`) | CP-VIS-01 [bandeja_validacion] |
| DEF-25 | Seguridad 5.1 | En la app, el bloqueo de login se mostraba como "Email o contraseña incorrectos"; en el panel, con el texto en inglés de allauth | Media | Las pantallas leían `errors` sin mirar el estado; el bloqueo de allauth no trae `param` | `isRateLimited` / `normalizeError` (`c27729b`, `2b8287c`) | CP-SEC05-M01, P04 |
| DEF-26 | Seguridad 5.1 | allauth headless respondía el bloqueo de login con 400 y el reenvío limitado con 403 | Baja | Comportamiento de allauth 65.16.1 | `HeadlessLockoutMiddleware` (`af2e35e`) | CP-SEC02-01, 06; CP-SEC18-03 |
| DEF-27 | US-041 / regla 4 | 37 fotos de personas, patentes y vía pública versionadas y subidas a un repo público | Alta | Set de benchmark guardado dentro del árbol en una sesión anterior | Fuera del árbol, ignoradas por git y Docker (`6d5b6ec`). **Siguen en el historial** (§19) | CP-041-31 |
| DEF-28 | Seguridad 5.3 | 99 vulnerabilidades conocidas en 11 paquetes de Python (Django 6.0.5, Pillow 12.2.0, cryptography 48, DRF…) y 24 / 64 en npm | Alta | Dependencias sin actualizar | Parches de la misma línea (`a89d42b`, `4b20600`, `033abd7`) | Etapa pip-audit / npm audit del CI (sin test unitario) |
| DEF-29 | Seguridad 5.4 | El esquema OpenAPI fallaba al generar `ValidatorViewSet` sin usuario (`'AnonymousUser' object has no attribute 'is_platform_admin'`) | Baja | `get_serializer_class` asumía un usuario real | `getattr` defensivo (`7a7e20a`) | CP-SEC17-01 |
| DEF-30 | Seguridad 5.5 | El `LOGGING` de `production.py` reemplaza al de `base.py`: el logger `security` no habría existido en producción | Media | Dos diccionarios de configuración independientes | `security_logging()` compartida (`7a7e20a`) | CP-SEC16-06 |

---

## 12. Huecos de cobertura

| ID | Comportamiento existente sin test | Test que lo cierra |
| --- | --- | --- |
| GAP-S5-01 | Argon2id como hasher principal y migración desde PBKDF2 | CP-SEC14-01, 02 |
| GAP-S5-02 | Qué podía abrir por id un tercero de un reporte inactivo (no había test en ningún sentido) | CP-VIS-01, CP-VIS-05 |
| GAP-S5-03 | El SHA-256 de los pesos estaba documentado pero nada lo verificaba | CP-041-38, 39 |
| GAP-S5-04 | La ausencia de metadatos solo se probaba sobre la salida del servicio, no sobre el archivo guardado en cada punto de carga | CP-041-13..16 |
| GAP-S5-05 | El barrido de todos los puntos del 6.1 con un reporte no visible | CP-VIS-00, 01 |
| GAP-S5-06 | Las pantallas de login, registro, recuperación, restablecimiento y cambio de contraseña de la app no tenían pruebas de componente | CP-SEC05-M01..M05 |
| GAP-S5-07 | El login del panel no tenía prueba de componente | CP-SEC05-P04, P05 |
| GAP-S5-08 | La tarjeta de comparación del panel ante un veredicto ausente estaba probada pero sin trazar a E5/E6 | CP-015-P05 |

---

## 13. Observaciones abiertas

| ID | Observación |
| --- | --- |
| OBS-S5-01 | Los 7 tests de detección de US-041 (CP-041-01..07) necesitan el set de referencia no versionado: en CI se saltean con el motivo a la vista. Para que corran en CI hace falta un set privado (por ejemplo, un artefacto cifrado) |
| OBS-S5-02 | El set del benchmark es provisorio: 37 fotos de Wikimedia Commons, bajadas en una sesión anterior aunque las instrucciones piden no bajar fotos de personas. Hasta que el equipo cargue fotos propias de Villa María, la tasa medida es de ese set |
| OBS-S5-03 | `/media/` es público. La URL de la foto de un reporte oculto (retenido, en procesamiento fallido, cancelado) sigue sirviendo el archivo a quien ya la conozca, hasta que se elimina. Es un límite conocido desde US-043 |
| OBS-S5-04 | La validación colectiva cuenta me gusta (decisión 1). El punto 2.4 de las instrucciones describe otra cosa |
| OBS-S5-05 | npm audit: `braces` (GHSA-vfj7-8cjw-p6xm, panel y app) y `node-forge` (GHSA-86w9-cpqp-85rv, app) no tienen versión corregida publicada; quedan como excepciones revisadas el 15/10/2026 |
| OBS-S5-06 | ESLint de la app: 1 aviso preexistente (`react-hooks/exhaustive-deps` en `map.tsx`) y 10 excepciones por línea de las reglas del React Compiler, cada una con su motivo |
| OBS-S5-07 | `ruff format` no se exige en CI: 47 archivos del backend no están formateados |
| OBS-S5-08 | La primera corrida de Jest en frío dio 8 timeouts en 5 suites; las siguientes, todo en verde. Si se repite en CI, subir `testTimeout` |
| OBS-S5-09 | Push: sigue simulado. `notifications/push.py::deliver_push` es el único punto de envío; respeta las preferencias del usuario y llama a `send_push`, que hoy solo escribe un log y devuelve `False`. La notificación queda en la bandeja in-app. No hay token de dispositivo en el modelo |
| OBS-S5-10 | Los límites de allauth no son atómicos (lo dice su documentación): con muchos pedidos paralelos se puede pasar uno o dos intentos de más |
| OBS-S5-11 | Rendimiento medido en una Mac con 10 núcleos; en un servidor con menos núcleos el tiempo crece en proporción (estimación, no medición) |
| OBS-S5-12 | Las altas registradas fuera de un request (seed de demo, shell, el comando de benchmark de US-026) quedan en el log de seguridad sin usuario ni IP |
| OBS-S5-13 | `measure_anonymization` importa el generador de fotos sintéticas de `anonymization/tests/images.py` |
| OBS-S5-14 | El CI de GitHub no se ejecutó (no hubo push). Las herramientas se corrieron localmente con las mismas versiones; la primera corrida real en Actions puede necesitar ajustes de entorno |
| OBS-S5-15 | El comando de benchmark de US-026 usa SQL armado a mano (`ANALYZE` y `EXPLAIN ANALYZE`) sobre el nombre de la tabla y el SQL que genera el ORM, sin datos de usuario. Es la única excepción a "solo ORM", y es diagnóstica |

---

## 14. Seguridad

### Estado de cada control (apartado 12 del documento de Seguridad v1.1)

| Control | Estado | Detalle |
| --- | --- | --- |
| Registro con verificación de correo | Implementado | allauth, `ACCOUNT_EMAIL_VERIFICATION = "optional"`. Reenvío limitado a 1 cada 3 min y 3 por hora por cuenta |
| Token de sesión e invalidación | Implementado | allauth headless, `X-Session-Token`; logout invalida la sesión |
| Recuperación de contraseña | Implementado | 3 pedidos por cuenta por hora y 20 por minuto por IP; enlace con vencimiento de 24 h |
| Control por rol y jurisdicción | Implementado | Queryset por municipalidad (404 a lo ajeno), 403 por rol, `IsAuthenticated` global |
| Auditoría de transiciones | Implementado | `ReportStatusHistory` con origen y responsable (sin cambios en este sprint) |
| Secretos fuera del repositorio | Implementado | `.env.example` en los tres repos; gitleaks en CI; la clave de Gemini del entorno local nunca se commiteó. Las credenciales del compose local quedan versionadas por diseño (`.gitleaksignore`) |
| Limitación de intentos y de tasa | Implementado | Login fallido 5/15 min por cuenta (ventana deslizante) + 10/min por IP; recuperación 3/h; confirmación 1/3 min y 3/h; registro 20/h por IP; reportes 20/h; comentarios 60/h; denuncias 10/día; dato personal 5/día. Proxies: `DJANGO_NUM_PROXIES` |
| Eliminación de metadatos | Implementado | Reporte, reemplazo, cierre y apelación (circuito de US-041) y perfil (campo de modelo). Comando retroactivo para perfiles, sin ejecutar |
| Difuminado de rostros y patentes | Implementado | Gaussiano irreversible; benchmark 92,6 % rostros y 93,3 % patentes (set provisorio de 37 fotos); fotos anteriores a US-041 pendientes del comando retroactivo |
| Argon2id | Implementado | Hasher principal; PBKDF2 para migración transparente; probado |
| CI de seguridad | Implementado (sin corrida en GitHub) | Backend: ruff, Bandit (≥ media), pip-audit, gitleaks, pytest, migraciones. Clientes: ESLint, tsc, npm audit (≥ alta, con excepciones), gitleaks, tests |
| Dependabot | Implementado | Semanal en los tres repos |
| `check --deploy` | Implementado | Sin advertencias (`check-deploy.txt`) |
| Registro de eventos | Implementado | Logger `security` con rotación (10 MB × 10 archivos) |
| HTTPS | Planificado | Configurado en Django (HSTS 1 año, redirección, cookies seguras, proxy SSL). El despliegue con certificado está fuera del alcance |
| Copias de seguridad | Fuera del alcance | Punto 9 de las instrucciones |
| Control antiabuso de US-043 | Implementado | 5 solicitudes por día por usuario por los dos endpoints, y cada solicitud y resolución en el log con usuario e IP |
| Validación de proximidad | Implementado | Radio de 50 m en el servidor (US-036, sin cambios) |

### Hallazgos de la primera corrida y su resolución

| Herramienta | Repo | Hallazgos | Resolución |
| --- | --- | --- | --- |
| Bandit 1.9.4 (1.8.6 no corre en Python 3.14) | Backend | 2 altos: B324 SHA1 en `geocoding.py` | Son claves de cache, no seguridad: `usedforsecurity=False` |
| | | 1 medio: B104 `0.0.0.0` en `local.py` | Es el `ALLOWED_HOSTS` de desarrollo, no un bind: `# nosec B104` con justificación |
| | | 4 bajos (B105 en `seed_demo.py`, B101 en `users/views.py`) | No bloquean (umbral medio); se dejan como están |
| pip-audit 2.10.1 | Backend | 99 vulnerabilidades en 11 paquetes | Django 6.0.9, DRF 3.17.2, Pillow 12.3.0, Werkzeug 3.1.9, cryptography 50.0.2, sqlparse 0.6.0, starlette 1.8.0, tornado 6.5.10, urllib3 2.8.0, virtualenv 21.14.5, anyio 4.14.2 → 0 |
| npm audit | Panel | 24 (1 baja, 5 moderadas, 17 altas, 1 crítica) | `npm audit fix` → 1 alta sin corrección (`braces`), excepción revisada |
| | App | 64 (12 moderadas, 51 altas, 1 crítica) | `npm audit fix` + `expo install --fix` → 2 altas sin corrección (`braces`, `node-forge`), excepciones revisadas |
| gitleaks 8.28.0 | Backend | 2 (`generic-api-key` en `.envs/.local/.postgres` y `.django`, commit `ab6580e`) | Credenciales del compose local, generadas por cookiecutter, sin datos reales: `.gitleaksignore`. En el árbol local además detecta la clave de Gemini de `.envs/.local/.django`, que nunca se commiteó |
| | Panel, App | 0 | — |
| Ruff 0.15.13 | Backend | 341 | 0. Se corrigieron todos; las cuentas en asserts y las contraseñas de prueba llevan `noqa` por línea, como ya hacía la suite |
| ESLint | App | No existía; al agregarlo, 28 errores y 22 avisos | 0 errores, 1 aviso (OBS-S5-06) |
| `check --deploy` | Backend | 0 de seguridad, 11 de drf-spectacular | 0 |

### Diferencias con el documento de Seguridad v1.0

**Sin dato apartado por apartado:** el documento de Seguridad v1.0 no está en los repositorios ni en `docxs/`. Las diferencias que se conocen, por lo que cita el documento de instrucciones:

| Tema | Promete v1.0 | Implementado | Acción |
| --- | --- | --- | --- |
| Bloqueo de login | 5 intentos en 5 minutos, bloqueo de 15 | 5 intentos por cuenta en una ventana deslizante de 15 minutos, más 10 por minuto por IP; no hay "bloqueo" fijo, vence el intento más viejo | Corregir v1.1 |
| Limitación, metadatos y CI | Comprometidos para el Sprint 4 | Entregados en el Sprint 5 | Actualizar el cronograma |
| Severidad de pip-audit | Falla con altas o críticas | Falla con cualquiera (pip-audit no informa severidad) | Documentar |

---

## 15. Implementación y despliegue

### Migraciones nuevas

| Migración | Qué hace |
| --- | --- |
| `users/0009_avatar_without_metadata` | `AlterField` de `avatar` a `MetadataFreeImageField`. Sin cambio de esquema |
| `reports/0014_privacy_request_on_appeal_photo` | Agrega `ReportComplaint.resolution_appeal` y `ResolutionAppeal.photo_removed_at`; rehace `unique_pending_complaint_per_image` incluyendo la apelación; agrega `complaint_targets_one_image` |

### Variables de entorno nuevas (todas en `.env.example`)

| Variable | Default |
| --- | --- |
| `DJANGO_CACHE_URL` | `REDIS_URL` |
| `DJANGO_NUM_PROXIES` | `0` |
| `DJANGO_RATELIMIT_LOGIN_FAILED` | `10/m/ip,5/15m/key` |
| `DJANGO_RATELIMIT_RESET_PASSWORD` | `20/m/ip,3/h/key` |
| `DJANGO_RATELIMIT_CONFIRM_EMAIL` | `1/3m/key,3/h/key` |
| `DJANGO_RATELIMIT_SIGNUP` | `20/h/ip` |
| `DJANGO_THROTTLE_REPORTS` | `20/hour` |
| `DJANGO_THROTTLE_COMMENTS` | `60/hour` |
| `DJANGO_THROTTLE_COMPLAINTS` | `10/day` |
| `DJANGO_THROTTLE_PRIVACY_REQUESTS` | `5/day` |
| `DJANGO_SECURITY_LOG_FILE` | `<repo>/logs/security.log` (vacío = solo consola) |
| `DJANGO_SECURITY_LOG_MAX_MB` | `10` |
| `DJANGO_SECURITY_LOG_BACKUP_COUNT` | `10` |
| `DJANGO_SECURE_HSTS_SECONDS` | `31536000` |
| `DJANGO_CORS_ALLOWED_ORIGINS` | vacío |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | vacío |
| `DJANGO_ANONYMIZATION_REFERENCE_SET` | `<repo>/benchmark_data/anonymization` |
| `DJANGO_VISION_PROVIDER` | vacío (proveedor nulo); `openai_compatible` en `.envs/.local/.django` |
| Panel: `BACKEND_NETWORK`, `API_UPSTREAM` | `urbancheck_backend_default`, `http://django:8000` (ya existían; ahora documentadas) |
| App: `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_USE_RN_FETCH` | ya existían; primer `.env.example` |

### Dependencias nuevas o actualizadas

| Paquete | Versión | Licencia |
| --- | --- | --- |
| Django | 6.0.5 → 6.0.9 | BSD-3-Clause |
| djangorestframework | 3.17.1 → 3.17.2 | BSD-3-Clause |
| Pillow | 12.2.0 → 12.3.0 | MIT-CMU |
| Werkzeug | 3.1.8 → 3.1.9 | BSD-3-Clause |
| cryptography (vía fido2 2.2.1) | 48.0.0 → 50.0.2 | Apache-2.0 / BSD-3-Clause |
| sqlparse, starlette, tornado, urllib3, virtualenv, anyio | 0.6.0, 1.8.0, 6.5.10, 2.8.0, 21.14.5, 4.14.2 | BSD-3, BSD-3, Apache-2.0, MIT, MIT, MIT |
| App: eslint, eslint-config-expo (nuevas, desarrollo) | 9.39.5, 57.0.2 | MIT |
| App: expo y módulos `expo-*` | 57.0.19 → 57.0.29 (parches del mismo SDK) | MIT |
| Panel: actualizaciones de `npm audit fix` (vite 8.3.4, axios 1.20.0, undici 7.30.0, qs 6.16.1…) | parches y menores | MIT |
| CI: bandit 1.9.4, pip-audit 2.10.1, gitleaks 8.28.0 (binario, SHA-256 fijo), ruff 0.15.13 | — | Apache-2.0, Apache-2.0, MIT, MIT |

### Modelos de detección

| Modelo | Versión | Licencia | Tamaño | Origen | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| YuNet (rostros) | `face_detection_yunet_2023mar.onnx` | MIT | 232.589 bytes | OpenCV Zoo | `8f2383e4…52fa4` |
| YOLOv9-s 608 (patentes, end-to-end) | `yolo-v9-s-608-license-plates-end2end.onnx` | MIT | 28.612.350 bytes | open-image-models, release `assets` | `2b878b38…0be9a` |

### Docker y Compose

- `compose/production/django/Dockerfile`: nuevo paso `sha256sum -c` de los dos modelos antes de instalar el proyecto. La imagen se construyó para verificarlo: 1,15 GB.
- `.dockerignore`: excluye `benchmark_data/` y `logs/`.
- Compose sin cambios.

### Levantar el entorno desde cero

1. `cd urbancheck_backend && docker compose -f docker-compose.local.yml up -d --build`. El arranque aplica las migraciones.
2. (Opcional) Copiar el set de referencia a `benchmark_data/anonymization/` (`manifest.json` + `images/`).
3. Para la comparación con IA: completar `DJANGO_RESOLUTION_COMPARISON_API_KEY` en `.envs/.local/.django` **sin commitearla** y correr `docker compose up -d django celeryworker`.
4. Panel: `cd urbanchech_frontend && cp .env.example .env && npm ci && npm run dev` (o `docker compose up`).
5. App: `cd urbancheck_mobile && cp .env.example .env && npm ci && npm run go`.
6. Verificar: `docker compose -f docker-compose.local.yml run --rm django pytest`, `npm test` en cada cliente.
7. Producción: además de lo habitual, definir `DJANGO_NUM_PROXIES` (1 detrás del nginx del panel; 2 si además hay Traefik) y `DJANGO_ADMIN_URL`.

### Plan de reversa

- Los commits están solo en `feature/sprint-5` local. Si la integración a `develop` falla, se revierte el merge (`git revert -m 1 <merge>`) o se deja de integrar la rama. Nada tocó `develop` ni `main`.
- Las migraciones `users/0009` y `reports/0014` son reversibles con `migrate users 0008` y `migrate reports 0013`. Bajar la 0014 **borra** el vínculo de las solicitudes hechas sobre fotos de apelaciones, si ya existieran.
- Las dependencias se revierten con el `uv.lock` y los `package-lock.json` del commit anterior.
- Si los límites de tasa molestaran en producción, se relajan por variable de entorno, sin redeploy de código.

---

## 16. Rendimiento

**Máquina:** Mac con Apple Silicon (aarch64), Docker Desktop 28.4.0; contenedor con 10 CPU y 7,7 GB de RAM; Python 3.14.2; onnxruntime sobre CPU. Detalle en `rendimiento-us041.md` y `benchmark-us026.md`.

### US-041

| Medición | Imágenes | Promedio | p95 | CPU por imagen |
| --- | --- | --- | --- | --- |
| Foto de 12 MP (4000 × 3000) | 10 | 1085 ms | 1305 ms | 9,8 s |
| Set de referencia (1600 px) | 37 | 962 ms | 1240 ms | 9,0 s |
| Benchmark del escenario 9 (otra corrida) | 37 | 786 ms | 961 ms | — |

- Memoria (RSS del proceso): 141 MB al arrancar, 264 MB con los modelos, 847 MB de pico con una foto de 12 MP.
- Imagen de Docker de producción: 1,15 GB; de desarrollo: 2,48 GB.
- Límite del escenario 8 (10 s): cumplido con amplio margen en esta máquina.
- Tasa de detección: rostros 175/189 (92,6 %), patentes 28/30 (93,3 %), total 203/219 (92,7 %). Falsos negativos por archivo y tipo en `benchmark-us041.md`; los más grandes son `people_06.jpg` (16 de 18 rostros), `people_07.jpg` (15/17), `people_09.jpg` (22/24 rostros y 0/1 patente), `street_cars_14.jpg` (2/3 patentes) y `street_cars_05.jpg` (0/1 rostro).

### US-026

100.000 reportes en una municipalidad (70 % cerrados, 6 categorías, recuadro de unos 10 km), 300 búsquedas al azar. Por búsqueda: **promedio 1,34 ms**, mediana 1,20 ms, **p95 2,06 ms**, máximo 5,19 ms. El plan usa `Index Scan using report_duplicate_lookup`, con ejecución en Postgres de 0,021 ms. Todo lo cargado se revirtió: la base quedó con 0 reportes de prueba.

---

## 17. Ayuda para el usuario

**Ciudadano**
- Si una foto de la objeción a un cierre muestra la cara de alguien o una patente, se puede tocar "Denunciar foto" debajo de ella. El reporte se oculta mientras se revisa, en un máximo de 24 horas.
- Si se equivoca varias veces la contraseña, la app avisa "Demasiados intentos" y hay que esperar unos minutos. Lo mismo pasa si se piden muchos correos de recuperación seguidos.
- Hay un tope de 20 reportes por hora, 60 comentarios por hora y 10 denuncias por día. Al llegar, la app dice cuánto falta para poder seguir.
- La foto de perfil se guarda sin la ubicación ni los datos del teléfono que vienen dentro del archivo.
- Un reporte cancelado o archivado de otra persona ya no se puede abrir.

**Operario**
- Sin cambios en su uso. La foto de cierre se guarda difuminada y sin la ubicación del teléfono; la ubicación del cierre se sigue registrando aparte, como hasta ahora.

**Agente municipal**
- Si un vecino denunció una imagen de un reporte por dato personal, el panel muestra el reporte con el aviso "en revisión" pero sin esa imagen hasta que el administrador decida.
- Si se equivoca varias veces la contraseña, el panel dice que hay que esperar unos minutos.

**Administrador de la plataforma**
- Las solicitudes por dato personal se pueden resolver desde la bandeja del panel o desde la administración de Django (sección Denuncias): filtrar "Fuera de plazo", seleccionar y elegir "Eliminar la imagen denunciada" o "Desestimar".
- Las solicitudes pueden ser sobre la foto del reporte, la de un cierre o la de una objeción; la bandeja indica cuál.
- La administración de Django ya no está en la dirección `/admin/`, sino en la que se configure al instalar.

---

## 18. Pruebas manuales pendientes para el equipo

La DoD exige prueba en dispositivo para toda historia con impacto en la app. Ninguna de estas se pudo hacer en esta sesión.

- [ ] **Denunciar la foto de una objeción (iOS y Android).** Con un ciudadano A, crear un reporte; con un operario, cerrarlo con foto; con A, objetar con foto. Con un ciudadano B, abrir el reporte y tocar "Denunciar foto" bajo la objeción. Verificar la confirmación con el plazo y que B sale del reporte. Con A, ver el aviso "en revisión". En el panel (administrador), ver "Foto de la objeción del vecino" y eliminarla. En la app, ver "Imagen retirada" y el motivo de la objeción intacto.
- [ ] **Bloqueo de login en la app.** Ingresar 6 veces una contraseña errónea para la misma cuenta y verificar que aparece "Demasiados intentos" y no "Email o contraseña incorrectos". Esperar 15 minutos (o vaciar Redis en dev) y entrar.
- [ ] **Bloqueo de login en el panel.** Igual que el anterior.
- [ ] **Recuperación de contraseña.** Pedir 4 correos seguidos para la misma cuenta: el 4.º muestra el aviso de espera. Verificar en Mailpit que llegaron 3.
- [ ] **Tope de reportes.** Bajar `DJANGO_THROTTLE_REPORTS` a `2/hour`, reiniciar y crear 3 reportes: el 3.º muestra el aviso con el tiempo de espera y el formulario conserva lo cargado.
- [ ] **Foto de perfil desde el teléfono.** Subir una foto con ubicación activada. Descargar el avatar desde `/media/avatars/` y verificar con `exiftool` que no tiene GPS ni modelo.
- [ ] **HEIC desde la galería de iOS:** crear un reporte, editarlo, cerrar como operario y objetar con una foto HEIC; las cuatro tienen que subir (la app las reencodea a JPEG). Probar también la foto de perfil HEIC y anotar el resultado (OBS: no se reencodea).
- [ ] **Detrás de un proxy real.** Con el nginx del panel delante y `DJANGO_NUM_PROXIES=1`, verificar en `logs/security.log` que la IP registrada es la del cliente.
- [ ] **Benchmark con fotos propias.** Cargar el set de Villa María en `benchmark_data/anonymization/` y correr `python manage.py benchmark_anonymization --report informe.md`.
- [ ] **Primera corrida del CI en GitHub** al abrir los PR (OBS-S5-14).

---

## 19. Pendientes y bloqueos

| Pendiente | Por qué | Qué hace falta del equipo |
| --- | --- | --- |
| Push de `feature/sprint-5` (16 commits en el backend, 7 en cada cliente) y PR a `develop` | Las instrucciones piden commits en la rama, sin integrar; no se pidió push | Autorizar el push y abrir los tres PR |
| Fotos del benchmark en el historial (commit `068c0c5`, repo público) | Reescribir el historial es destructivo (regla 5); el usuario eligió no hacerlo por ahora | Decidir si se reescribe `feature/sprint-5` antes de integrar a `develop`. Si se integra tal cual, las fotos quedan también en `develop` |
| `anonymize_existing_photos --apply` | Toca archivos publicados (regla 5) | Autorizarlo y elegir el entorno. Correrlo antes sin `--apply` para ver cuántas fotos son |
| `strip_image_metadata --apply` | Ídem | Ídem |
| Set de benchmark propio | No se descargan fotos de personas | Fotos urbanas de Villa María con su `manifest.json` etiquetado |
| Proveedor de visión en producción | El default es el nulo | Confirmar Gemini en plan pago (el gratuito puede usar el contenido) u otro, y cargar la clave en `.envs/.production/` |
| Corrección de documentos | Decisiones 1, 2, 3, 7 y 13 | Actualizar US-032 (sumarse = me gusta), US-043 E5, el punto 2.4 y el 6.1 de las instrucciones, y el documento de Seguridad v1.1 (bloqueo) |
| Pruebas manuales | Requieren dispositivo | §18 |

---

## 20. Uso de IA en la construcción

**Producido por el asistente (Claude Code) en esta sesión:**
- Código del backend: límites de tasa e intentos, middleware de 429, log de seguridad, campo de modelo sin metadatos, comandos retroactivos y de medición, denuncia de la foto de apelación, acciones del admin, proveedor de visión con interfaz, endurecimiento de producción y correcciones de visibilidad.
- Código de los clientes: manejo del 429, botón y estados de la foto de objeción, etiquetas de la bandeja, ESLint de la app.
- Tests: 100 en el backend, 7 en el panel y 12 en la app, más los identificadores de trazabilidad de 409 casos.
- Configuración: tres workflows de CI, Dependabot, `.gitleaksignore`, el control de npm audit con excepciones, `.env.example` y actualización de dependencias.
- Revisión: corridas de ruff, Bandit, pip-audit, npm audit, gitleaks, actionlint y `check --deploy`; inventario contra el código.
- Documentación: README del backend, `AGENTS.md` de la app, `BITACORA.md`, `TRAZABILIDAD.md`, `check-deploy.txt`, informes de rendimiento y este reporte.

**Sujeto a revisión humana antes de integrar:**
- Los tres PR a `develop` (revisión de código de cada commit).
- Las decisiones del §5 marcadas con ⚠️.
- Las excepciones de seguridad (`.gitleaksignore`, `audit-allowlist.json`, el `nosec` de B104 y las 10 excepciones de ESLint de la app).
- Los valores de los límites de tasa para el uso real.
- La representatividad de las mediciones de rendimiento.
- La autorización de los comandos retroactivos y de la reescritura del historial.
- Las pruebas manuales del §18.

Las historias del sprint ya se habían implementado con el asistente en sesiones anteriores (13/09 a 13/10/2026); este reporte cubre el trabajo del 15/10/2026.
