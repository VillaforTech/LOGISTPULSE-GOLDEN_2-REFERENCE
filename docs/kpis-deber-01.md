# Contrato de fulfillment y KPIs

Un pedido aceptado en `t0=createdAt` debe alcanzar `READY` con `readyAt <= t0+15s`. WAITING, PREPARING y READY son estados persistentes. La preparación simulada dura cuatro segundos; el worker único procesa secuencialmente. El contrato detecta sobrecarga real: no inventa READY ni extiende el plazo para ocultarla.

| KPI | Fórmula en el instante `t` | Unidad / muestra |
| --- | --- | --- |
| L-K1 | `100 × incumplidos/cohorte`; cohorte: `t−900 < createdAt <= t−15`. Incumplido: sin readyAt o readyAt > createdAt+15 | porcentaje; muestra = tamaño de cohorte; denominador cero ⇒ `value:null,status:NO_SAMPLE` |
| L-K2 | suma exacta de total para WAITING/PREPARING con createdAt+15 <= t | DEMO; muestra = pedidos vencidos abiertos |
| L-K3 | suma de `max(t−createdAt−15,0)` para esos mismos pedidos | pedido·segundos; muestra = pedidos vencidos abiertos |

Cada snapshot recomputa la deuda desde timestamps persistidos. Repetir un tick no duplica segundos. Un timer de 200 ms actualiza vencimientos y expiración de ventana aunque no lleguen eventos nuevos. El valor de deuda empieza en cero exactamente al límite; un microsegundo tarde ya incumple. Un pedido que termina tarde sale del backlog L-K2/L-K3, pero conserva el incumplimiento histórico L-K1 hasta salir de la cohorte. La llegada tardía de un hecho READY que ocurrió a tiempo corrige la proyección.

Las tres alertas se activan cuando su valor válido es mayor que cero y persisten cambios de estado y timestamps. Un hueco, conflicto o desconexión suspende la interpretación; no resuelve alertas como si el problema de negocio hubiera desaparecido.

## Calidad y visualización

- `FRESH`: bootstrap completo; consumer/source heartbeats recientes; sin lag, gaps ni cuarentena; ninguna publicación pendiente; cantidad y digest de todas las identidades/versiones iguales a la fuente.
- `INCOMPLETE`: hay cambios pendientes, versión faltante, evento inválido/conflictivo o cobertura distinta. Se mantiene `observedValue` para diagnóstico, pero `value:null`.
- `STALE`: no hay heartbeat vigente del consumidor/fuente o el último cálculo persistido supera tres segundos. No se devuelve un verde histórico como actual.

Grafana Live recibe los snapshots por `/api/live/push/logistpulse` y los expone en `stream/logistpulse/business`. El datasource nativo usa `queryType:measurements`. Sus paneles traducen −1 a DATOS NO CONFIABLES y −2 a SIN MUESTRA; los números normales nunca usan esos valores. Identidad, versión, revisión, timestamp, calidad y muestra están visibles en la tabla.

Una interrupción total del adapter puede dejar el último frame en un panel nativo. Por ello el dashboard muestra dos monitores independientes (edad del cálculo y transporte) consultados por Prometheus cada cinco segundos; sus fallos invalidan la lectura de los números. La consola aplica además un watchdog local de tres segundos que oculta valores y muestra STALE si deja de recibir revisiones. **El auto-refresh de esos monitores no cuenta como evidencia de streaming.**

La demo asume reloj UTC del mismo host para servicios y DB. La latencia de render se mide enteramente con `performance.now()` del navegador, sin restar relojes de servidores. No se afirma una SLA de producción ni alta disponibilidad: broker de una réplica, una partición y worker único son elecciones del laboratorio.
