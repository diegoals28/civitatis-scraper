# Civitatis Scraper - Notas de Desarrollo

## Estado Actual (23/01/2026)

### Arquitectura
- **Frontend**: `index.html` (servido por Vercel)
- **Backend**: Flask en Railway (`app.py`)
- **Base de datos**: PostgreSQL en Railway
- **Scraper**: Playwright (`scraper.py`)

### URLs
- Frontend: https://civitatis-scraper.vercel.app/
- Backend API: https://web-production-d27c8.up.railway.app

---

## Funcionalidades Implementadas

### Calendario
- Muestra fechas con datos en verde
- Tooltip al pasar el mouse (posicionamiento dinámico para no cortarse en bordes)
- Selección múltiple de fechas

### Scraping
- Scrape automático diario **DESHABILITADO** (usuario prefiere manual)
- Scrape manual con "Scrapear Selección" para fechas seleccionadas
- Guarda datos en base de datos después de cada scrape
- Recarga datos del servidor después de scrapear

### Tabla de Datos
- Muestra datos de fechas seleccionadas en parte inferior
- Columnas: Horario, Operador, Precio, Plazas
- Se actualiza automáticamente al seleccionar fechas o scrapear

### Exportar
- Exporta a CSV las fechas seleccionadas

---

## Problemas Conocidos / Pendientes

### Precios
- **Problema**: Algunos precios no coinciden con el sitio real de Civitatis
- **Causa probable**: El precio puede no actualizarse lo suficientemente rápido después de cambiar horario
- **Solución implementada**:
  - Priorizar selector `#tPrecioSpan0` (span visible) sobre `#tPrecio0` (input hidden)
  - Tiempo de espera aumentado a 1000ms
- **Estado**: Pendiente de verificar si funciona correctamente

### Selectores de Precio (en orden de prioridad)
```javascript
const selectors = [
    '#tPrecioSpan0',       // Visible price span (más preciso)
    '.pax-price',          // Price class
    '#tPrecio0',           // Hidden input (puede tener valores viejos)
    '.a-text--price--big', // Big price display
    '.m-counter--price input[type="hidden"]'
];
```

---

## Archivos Principales

### `index.html`
- Interfaz completa del frontend
- Calendario interactivo con tooltips
- Tabla de datos de fechas seleccionadas
- Estilos CSS embebidos

### `app.py`
- API Flask
- Endpoints:
  - `POST /api/scrape` - Scrapea una fecha y guarda en BD
  - `GET /api/calendar/<tour_id>` - Obtiene datos del calendario
  - `GET /api/tours` - Lista de tours
  - `GET /api/schedules/<tour_id>` - Horarios de un tour

### `scraper.py`
- Scraper con Playwright
- `compare_all_schedules()` - Función principal
- `extract_price()` - Extrae precio del DOM
- Mapeo de provider_id a nombres de operadores

### `scheduler.py`
- Scheduler con APScheduler (actualmente deshabilitado)
- `run_daily_scrape()` - Scrape completo de todos los tours

### `models.py`
- Modelos SQLAlchemy: Tour, Schedule, ScrapeLog

---

## Tours Configurados

1. Coliseo, Foro y Palatino
2. Museos Vaticanos y Capilla Sixtina
3. Coliseo + Arena de Gladiadores

---

## Configuración

### Variables de Entorno (Railway)
- `DATABASE_URL` - PostgreSQL connection string
- `PORT` - 8080

### Vercel
- Archivo `vercel.json` para configuración
- Despliega `index.html` como estático

---

## Comandos Útiles

```bash
# Ver logs de Railway
railway logs

# Ejecutar localmente
python app.py

# Instalar dependencias
pip install -r requirements.txt
playwright install chromium
```

---

## Historial de Cambios Recientes

1. Tooltip con posicionamiento dinámico (evita cortarse en bordes)
2. Badge de plazas debajo del precio (no al lado)
3. Scrape automático deshabilitado
4. Tabla de datos de fechas seleccionadas
5. Panel de estado del scrape eliminado
6. Mejora en extracción de precios (priorizar span visible)
7. Tiempo de espera aumentado a 1s para actualización de precios
