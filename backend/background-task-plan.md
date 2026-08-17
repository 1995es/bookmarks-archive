# Plan: enriquecimiento asíncrono de bookmarks

Feature: tras crear un bookmark, una `BackgroundTask` de FastAPI ejecuta el caso de uso
`EnrichBookmark`, que enriquece el bookmark con una descripción y unos tags generados a partir de
su contenido.

## Decisiones tomadas

| Punto | Decisión |
|---|---|
| Persistencia | El caso de uso recibe un `BookmarkRepository` y persiste con `repo.save()` |
| Entrada del caso de uso | Recibe el `bookmark_id` (`UUID`), no la instancia; lee el bookmark del repo |
| Fetch (paso 1) | Nuevo puerto `ContentFetcher` con implementación HTTP en `adapters/outbound` |
| Merge de `description` | Append a la que escribió el usuario (si la había) |
| Merge de `tags` | Append a los existentes, deduplicando y preservando orden |
| Errores | Se capturan en el borde de la tarea, se loguean; el bookmark queda sin enriquecer |
| Concurrencia | Una sola lectura del repo. Un `PUT` concurrente puede pisar el enriquecimiento; asumido a propósito (app local, un solo usuario) |

**Asunción declarada**: en el append de tags se deduplica — si el LLM devuelve `python` y el usuario
ya lo puso, no se duplica. El límite de 50 tags de `schemas.py` se replica como corte en el dominio.

**Desviación de nomenclatura, deliberada**: el caso de uso se llama `EnrichBookmark`
conceptualmente, pero la capa `application` de este proyecto usa funciones a nivel de módulo
(`create_bookmark`, `update_bookmark`…), no clases. Se implementa como `enrich_bookmark()` en
`app/application/enrich_bookmark.py` para no romper la consistencia.

---

## 1. Capa de dominio

### `app/domain/models.py`

Nuevo value object, inmutable, sin frameworks:

```python
@dataclass(frozen=True)
class ExtractedData:
    description: str
    tags: list[str]
```

Nuevo método en `Bookmark` — **la única vía sancionada** para enriquecer, igual que `update()` y
`delete()`:

```python
def enrich(self, data: ExtractedData) -> None:
    # description: append (separador "\n\n") si ya había una; si era None/vacía, se asigna
    # tags: extend con los nuevos que no estén ya presentes, preservando orden
    # truncar a _MAX_TAGS
    # self.validate()
```

Las constantes `_MAX_TAGS = 50` / `_MAX_TAG_LENGTH = 50` se mueven a `domain/models.py` y
`schemas.py` las importa, para que el límite tenga una sola fuente. Hoy viven solo en `schemas.py`;
el LLM no pasa por Pydantic, así que el dominio necesita conocerlas.

### `app/domain/ports.py`

Dos puertos nuevos, ambos `Protocol` y `async`:

```python
class ContentFetcher(Protocol):
    async def fetch(self, url: str) -> str:
        ...
        # devuelve el contenido textual de la URL
        # lanza ContentFetchError ante fallo de red / status no-2xx


class BookmarkEnricherService(Protocol):
    async def extract_data(self, *, url: str, content: str) -> ExtractedData:
        ...
        # lanza EnrichmentError si el proveedor falla o la respuesta no es parseable
```

`extract_data` recibe `url` además de `content` porque el LLM se beneficia de la URL como señal de
contexto (dominio, path). Recibir el `Bookmark` completo acoplaría el puerto a la entidad sin
ganancia real.

### `app/domain/exceptions.py`

```python
class ContentFetchError(Exception): ...


class EnrichmentError(Exception): ...
```

Ambas se quedan en el dominio y **no** se mapean a HTTP en `main.py` — nunca cruzan la frontera de
una request, ocurren después de la respuesta.

---

## 2. Capa de aplicación

### `app/application/enrich_bookmark.py`

```python
async def enrich_bookmark(
    bookmark_id: uuid.UUID,
    *,
    repo: BookmarkRepository,
    fetcher: ContentFetcher,
    enricher: BookmarkEnricherService,
) -> Bookmark | None:
    bookmark = await repo.get(bookmark_id)
    if bookmark is None:
        return None  # inexistente o borrado

    content = await fetcher.fetch(bookmark.url)  # paso 1
    data = await enricher.extract_data(url=bookmark.url, content=content)  # paso 2
    bookmark.enrich(data)  # paso 3
    return await repo.save(bookmark)
```

- **Devuelve `None` en lugar de lanzar** cuando el bookmark no existe, igual que `get_bookmark` y
  `update_bookmark`. El "no encontrado" cotidiano no es excepcional.
- **No captura excepciones**: dejarlas propagar es lo correcto — quien decide qué hacer con un fallo
  es el borde (la tarea), no el caso de uso. Esto lo mantiene testeable sin mocks de logging.
- `bookmark_id` es posicional; las tres dependencias son keyword-only para que no se confundan entre
  sí en el call site.
- Recibir el `UUID` en lugar de la instancia evita capturar un objeto de dominio potencialmente
  obsoleto en el closure de la tarea: lo único que cruza la frontera de la request es un `UUID`, que
  no puede quedar stale.

---

## 3. Adaptadores outbound

### `app/adapters/outbound/http_content_fetcher.py`

`HttpContentFetcher` implementa `ContentFetcher` sobre `httpx.AsyncClient`:

- timeout explícito (10s), `follow_redirects=True`, User-Agent propio
- límite de tamaño de respuesta (~1 MB) para no cargar un PDF de 300 MB en memoria
- extrae texto plano del HTML (strip de tags; un regex conservador basta y evita una dependencia)
- traduce `httpx.HTTPError` y status ≥ 400 a `ContentFetchError`

El cliente `httpx` se crea **por tarea** y se cierra con `async with`; no hay pool compartido en esta
iteración (una tarea, una petición).

### `app/adapters/outbound/llm_bookmark_enricher.py`

`LLMBookmarkEnricherService` implementa `BookmarkEnricherService`. **Vacía por ahora**; la
estructura queda montada:

```python
class LLMBookmarkEnricherService:
    def __init__(self, *, model: str = ..., max_content_chars: int = ...) -> None: ...

    async def extract_data(self, *, url: str, content: str) -> ExtractedData:
        raise NotImplementedError("pending litellm integration")
```

Notas para cuando se implemente, para que el hueco no se rellene con decisiones arbitrarias:

- `litellm.acompletion` (variante async, no la síncrona — todo el stack es async)
- modelo por defecto `anthropic/claude-opus-5` (prefijo de proveedor `anthropic/` + ID del modelo)
- salida estructurada vía `response_format` con un JSON schema `{description: str, tags: list[str]}`,
  no parseo de texto libre
- truncar `content` antes de enviarlo
- envolver cualquier excepción de litellm en `EnrichmentError`

### `pyproject.toml`

- `httpx` pasa del grupo `dev` a `dependencies` (ahora es dependencia de producción)
- se añade `litellm` a `dependencies`

---

## 4. Adaptador inbound: BackgroundTasks

### El problema de la sesión

`get_db` cierra la `AsyncSession` cuando termina la request. Una `BackgroundTask` corre **después**,
así que no puede reutilizar ni el `repo` ni la sesión inyectados en la ruta. La tarea abre su propia
sesión con `SessionLocal`.

### `app/adapters/inbound/background.py` (nuevo)

```python
logger = logging.getLogger(__name__)

EnrichmentRunner = Callable[[uuid.UUID], Awaitable[None]]


async def run_enrichment(bookmark_id: uuid.UUID) -> None:
    """Borde de la tarea: compone dependencias, abre sesión propia, traga errores."""
    try:
        async with SessionLocal() as db:
            repo = SqlAlchemyBookmarkRepository(db)
            async with HttpContentFetcher() as fetcher:
                enricher = LLMBookmarkEnricherService()
                await enrich_bookmark(bookmark_id, repo=repo, fetcher=fetcher, enricher=enricher)
    except (ContentFetchError, EnrichmentError, BookmarkNotFoundError, BookmarkInvalidError) as exc:
        logger.warning("enrichment failed for %s: %s", bookmark_id, exc)
    except Exception:
        logger.exception("unexpected error enriching %s", bookmark_id)


def get_enrichment_runner() -> EnrichmentRunner:
    """Provider FastAPI. Permite override en tests."""
    return run_enrichment
```

`BookmarkNotFoundError` se captura explícitamente: si el bookmark se borra entre el `get` y el
`save`, `repo.save()` lo lanza. No es un bug, es la carrera esperada.

### `app/adapters/inbound/api.py`

Solo cambia `create_bookmark`:

```python
@router.post("/bookmarks", response_model=BookmarkRead, status_code=201)
async def create_bookmark(
    bookmark: BookmarkCreate,
    background_tasks: BackgroundTasks,
    repo: BookmarkRepository = Depends(get_repository),
    enrich: EnrichmentRunner = Depends(get_enrichment_runner),
) -> BookmarkRead:
    created = await bookmark_service.create_bookmark(repo, **bookmark.model_dump())
    background_tasks.add_task(enrich, created.id)
    return created
```

Sigue sin haber lógica de negocio en la ruta: registra una tarea y devuelve. La composición de
dependencias vive en `background.py`, que es adapter.

### `app/main.py`

Sin cambios funcionales. Solo configuración de `logging` básica si aún no la hay.

---

## 5. Tests

### `tests/domain/test_models.py` (añadir)

| Test | Comprueba |
|---|---|
| `test_enrich_sets_description_when_empty` | `description=None` → queda la generada |
| `test_enrich_appends_to_existing_description` | usuario puso "un artículo" → el resultado contiene ambas |
| `test_enrich_appends_tags_preserving_user_tags` | `["python"]` + `["web"]` → `["python", "web"]` en ese orden |
| `test_enrich_does_not_duplicate_tags` | `["python"]` + `["python", "web"]` → `["python", "web"]` |
| `test_enrich_truncates_at_max_tags` | corte en 50 |
| `test_enrich_revalidates_invariants` | enriquecer no puede dejar el bookmark inválido |
| `test_enrich_does_not_touch_name_url_type` | los campos que no son suyos quedan intactos |

### `tests/application/test_enrich_bookmark.py` (nuevo)

Fakes en el propio módulo, mismo patrón que `FakeBookmarkRepository`:

```python
class FakeContentFetcher:      # devuelve contenido fijo, registra las URLs pedidas
class FailingContentFetcher:   # lanza ContentFetchError
class FakeEnricherService:     # devuelve ExtractedData fijo; `on_call` opcional para efectos laterales
class FailingEnricherService:  # lanza EnrichmentError
```

`FakeBookmarkRepository` se extrae de `test_bookmark_service.py` a `tests/fakes.py` para no
duplicarlo. Los tests del contrato siguen importándose donde ya lo hacen.

| Test | Comprueba |
|---|---|
| `test_fetches_the_bookmark_url` | el fetcher recibe exactamente `bookmark.url` |
| `test_passes_fetched_content_to_enricher` | paso 1 → paso 2 encadenados; el enricher no recibe contenido vacío |
| `test_applies_extracted_data_to_bookmark` | la instancia devuelta trae description y tags |
| `test_persists_the_enriched_bookmark` | `repo.get(id)` tras el caso de uso devuelve la versión enriquecida |
| `test_returns_none_when_bookmark_does_not_exist` | repo vacío → `None`; el fetcher **no** se invoca |
| `test_returns_none_when_soft_deleted` | `repo.get` oculta borrados → no se enriquece |
| `test_fetch_failure_propagates` | `ContentFetchError` sube; el enricher no se invoca; nada se persiste |
| `test_enricher_failure_propagates` | `EnrichmentError` sube; nada se persiste |
| `test_raises_not_found_when_deleted_during_enrichment` | el fake enricher borra la fila al ser invocado (`on_call`) → `repo.save()` lanza `BookmarkNotFoundError`. Documenta la única carrera que queda |

### `tests/adapters/outbound/test_http_content_fetcher.py` (nuevo)

Con `httpx.MockTransport` — sin red real:

| Test | Comprueba |
|---|---|
| `test_returns_text_content` | 200 con HTML → texto extraído, sin tags |
| `test_raises_on_http_error_status` | 404 → `ContentFetchError` |
| `test_raises_on_connection_error` | excepción de transporte → `ContentFetchError` |
| `test_truncates_oversized_response` | body > límite → cortado, no explota |
| `test_follows_redirects` | 302 → sigue al destino |

### `tests/adapters/outbound/test_llm_bookmark_enricher.py` (nuevo)

Mientras la implementación esté vacía, un único test que **documenta** el estado:

| Test | Comprueba |
|---|---|
| `test_extract_data_not_implemented_yet` | `pytest.raises(NotImplementedError)` |

Es intencionalmente frágil: cuando se implemente litellm, falla y obliga a escribir los tests reales
(respuesta bien formada → `ExtractedData`; JSON inválido → `EnrichmentError`; error del proveedor →
`EnrichmentError`; contenido truncado antes de enviarse).

### `tests/adapters/inbound/test_api.py` (añadir)

Fixture nueva que hace override de `get_enrichment_runner` con un spy async que registra las
llamadas:

| Test | Comprueba |
|---|---|
| `test_create_schedules_enrichment_task` | tras el POST 201, el runner fue llamado exactamente una vez |
| `test_enrichment_receives_the_created_bookmark_id` | el runner recibe un `uuid.UUID` igual al `id` del cuerpo de la respuesta |
| `test_create_returns_201_before_enrichment_completes` | la respuesta no contiene la description enriquecida |
| `test_failing_enrichment_does_not_affect_response` | runner que lanza → el POST sigue devolviendo 201 |
| `test_other_endpoints_do_not_schedule_enrichment` | PUT y DELETE no registran tarea |

`ASGITransport` **sí** ejecuta las `BackgroundTasks`, así que el spy se invoca de verdad dentro del
`await client.post(...)`. No hace falta sincronización manual.

### Test de integración end-to-end (opcional, 1 test)

En `test_api.py`, con override de `get_enrichment_runner` por un runner que usa fakes de
fetcher/enricher pero el **repo real** sobre la BD temporal: POST → `GET /bookmarks/{id}` devuelve la
description y los tags enriquecidos. Es el único que prueba que la sesión nueva de la tarea escribe
donde la request lee.

**Total estimado**: ~29 tests nuevos sobre los 50 actuales.

---

## 6. Documentación a actualizar

- `backend/CLAUDE.md`: los dos puertos nuevos en la sección de arquitectura; la regla de que las
  tareas de background abren su propia sesión; el árbol de `app/` con `enrich_bookmark.py`,
  `background.py`, `http_content_fetcher.py`, `llm_bookmark_enricher.py`; nota de que `_MAX_TAGS`
  vive ahora en el dominio
- `CLAUDE.md` raíz: mención de que el POST dispara enriquecimiento asíncrono, y que la API key del
  LLM es necesaria en prod
- `README.md`: comportamiento visible para el usuario (los tags aparecen unos segundos después de
  crear el bookmark)
- `docker-compose.yml` / `docker-compose.prod.yml`: pasar `ANTHROPIC_API_KEY` al servicio backend

**Sin cambios en**: `frontend/src/types.ts` (no cambia ningún esquema Pydantic), `orm.py`, esquema de
BD. Nada de migraciones.

---

## 7. Orden de implementación

1. Dominio (`ExtractedData`, `Bookmark.enrich`, excepciones, puertos) + sus tests → verde
2. Caso de uso + fakes + tests → verde
3. `HttpContentFetcher` + tests → verde
4. `LLMBookmarkEnricherService` stub + test → verde
5. `background.py` + cambio en `api.py` + tests de API → verde
6. Docs y compose

Cada paso deja la suite en verde, así que es interrumpible en cualquier punto.
