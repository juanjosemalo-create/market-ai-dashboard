"""Manual de la herramienta, embebido en la app.
Se muestra con un boton en el sidebar. Tambien permite descargar el .docx si esta presente.
"""
import os
import streamlit as st

MANUAL_MD = r"""
# Manual del Tablero de Sentimiento de Mercado
### IA / Semiconductores - AI / Semis Market Sentiment Dashboard (v5)
*Que muestra · En que se fundamenta · Que evidencia lo respalda*

---

## 1. Que es esta herramienta

Es un tablero que mide, en un solo lugar, que tan tensionado o tranquilo esta el mercado,
con foco en el Nasdaq y los semiconductores (NVDA, TSM, AVGO, QCOM y compania).

**No predice el futuro:** traduce senales de volatilidad, credito, precio relativo y opciones
en un punado de puntajes faciles de leer, con semaforos de colores. La idea central es no decir
"el mercado va a caer", sino **"las condiciones que historicamente precedieron a las caidas estan dadas"**.
Es una herramienta de probabilidad condicional y de gestion de exposicion, no una bola de cristal
ni una senal de compra/venta.

Tres usos concretos: graduar el ritmo de DCA y la exposicion, distinguir un mal dia puntual de las
tecnologicas de un problema sistemico, y comunicar postura a los clientes con un fundamento objetivo.

---

## 2. Que podes ver en pantalla

Se lee de arriba hacia abajo, de lo mas resumido a lo mas detallado:

| Bloque | Que muestra | Para que sirve |
|---|---|---|
| **Semaforo de entrada** | Una sola luz (verde/amarillo/rojo/azul) con accion sugerida. | El resumen accionable. Si miras una sola cosa, es esta. |
| **5 scores principales** | General, AI/Semis, Market, Options, Capitulation (0-100 + semaforo). | El estado del mercado en cinco dimensiones. |
| **Term structure** | El ratio VIX/VIX3M con semaforo de 4 estados. | El indicador mas confiable del tablero. |
| **Tabla de indicadores** | Cada senal con su valor, su semaforo y que significa. | El detalle, para entender que empuja los scores. |
| **Opciones** | Movimiento esperado y cobertura por ticker. | Para vos: mira sobre todo "movimiento esperado %". |
| **Graficos y glosario** | Evolucion intradia + diccionario en criollo. | Contexto visual y consulta de terminos. |

---

## 3. El fundamento: puntaje por percentil

**El problema de los umbrales fijos.** Decir "VIX arriba de 28 = peligro" falla porque el mercado
cambia de regimen: un VIX de 20 viniendo de 12-14 es alarma; el mismo 20 viniendo de 35 es alivio.
Un umbral fijo los lee igual y se equivoca.

**La solucion: percentil sobre 2 anios.** Cada indicador se mide contra su propia historia de los
ultimos ~2 anios (504 ruedas). El puntaje 0-100 es el **percentil** del valor de hoy: 90 = mas alto
que el 90% de los dias, o sea extremo *para su propio regimen*. 50 = un dia normal.

**Por que es mejor:** el tablero se autocalibra al contexto. No hay que reajustar umbrales cuando
cambia la volatilidad de fondo, y funciona desde el primer arranque con la historia de Yahoo.

---

## 4. Los cinco scores en detalle

Semaforo: verde 0-40 (tranquilo), amarillo 40-65 (presion), rojo 65-100 (alerta).
La Capitulacion es la excepcion: el azul (sobreventa extrema) no es malo, suele marcar pisos.

**4.1 General Risk.** El resumen de todo: 30% Market + 35% AI/Semis + 20% Options + 15% Capitulation.

**4.2 AI/Semis Risk** - el mas relevante para la cartera. Alto = tech/semis liderando la baja.

| Componente | Peso | Que mide |
|---|---|---|
| VXN | 25% | Miedo del Nasdaq (VIX para tech). |
| QQQ-SPY 20d | 25% | Si el Nasdaq cae mas que el mercado (validado). |
| SMH-QQQ 20d | 15% | Si semis cae mas que el Nasdaq. |
| VXN cambio 1d | 15% | El salto del miedo tech en el dia. |
| SMH-QQQ 5d | 10% | Lo mismo a una semana (mas ruidoso). |
| NVDA-SMH 20d | 10% | Si el lider (NVDA) ya no aguanta. |

**4.3 Market Stress** - estres sistemico. Aca vive la mejor senal anticipatoria.

| Componente | Peso | Que mide |
|---|---|---|
| Term structure (VIX/VIX3M) | 35% | Curva de volatilidad. El mejor predictor. |
| Credito HYG/IEF | 25% | Bonos riesgosos vs seguros. Estres de fondo. |
| VIX | 20% | Miedo del S&P 500. |
| SKEW | 10% | Proteccion contra caidas extremas. |
| VVIX | 5% | Volatilidad de la volatilidad. |
| Tasas 10Y (cambio) | 5% | Suba de tasas presiona a las tech. |

**4.4 Options Sentiment.** Demanda de cobertura (put/call CBOE). **Atencion:** fuente fragil, suele
venir incompleta. El tablero avisa cuando falta. No es critico para el uso principal.

**4.5 Capitulation** - el contrapeso. RSI, drawdown, breadth, VIX extremo y put/call. Semaforo azul
porque un valor alto suele marcar PISOS, no techos: te frena de vender en panico. Arriba de 75, el
riesgo se vuelve asimetrico al alza.

---

## 5. El semaforo unico de entrada

La sintesis accionable. Toma solo las senales validadas y las combina en una luz. El term structure
define el nivel base (0 a 3); los confirmadores lo suben cuando acompanan.

| Luz | Cuando aparece | Postura sugerida |
|---|---|---|
| 🟢 **VERDE** | Term en contango, sin confirmadores. | DCA y exposicion segun plan. |
| 🟡 **AMARILLO** | Term tensandose o 1 confirmador. | Fraccionar entradas, no agregar agresivo. |
| 🔴 **ROJO** | Term comprimido/invertido o varios confirmadores. | Pausar entradas agresivas. NO vender en panico. |
| 🔵 **AZUL** | Estres extremo + capitulacion (>75). | Zona de acumular con cabeza. Para DCA: acelerar. |

Los tres confirmadores validados: **credito en estres**, **VIX elevado** y **Nasdaq debil vs S&P**.

---

## 6. El term structure: el indicador estrella

Si hay que entender un solo numero, es el ratio **VIX/VIX3M**: compara el miedo a 1 mes contra el de 3 meses.

- **Contango (ratio < 1):** estado normal. Miedo a largo > miedo a corto. Mercado tranquilo.
- **Backwardation (ratio > 1):** la curva se invierte. Miedo de corto supera al de largo. Panico inmediato.

| Semaforo | Ratio | Estado | Lectura |
|---|---|---|---|
| 🟢 VERDE | < 0,90 | Contango pleno | Calma con colchon. Bajas comprables. |
| 🟡 AMARILLO | 0,90 - 0,95 | Aplanandose | El colchon se consume. Prestar atencion. |
| 🟠 NARANJA | 0,95 - 1,00 | Comprimido | Alerta: aca ya empezaban las bajas. |
| 🔴 ROJO | > 1,00 | Backwardation | Estres agudo. No meter la mano todavia. |

El umbral 0,95 surgio de observar que las bajas aparecian antes de la inversion total. El backtest lo confirmo.

### 6.1 Pagina de probabilidades VIX/VIX3M

El tablero principal muestra **intensidad y postura**. La pagina adicional transforma el estado actual en
frecuencias historicas condicionadas y responde preguntas distintas:

| Pregunta | Metrica adecuada |
|---|---|
| ¿Puede aparecer un precio inferior? | Nuevo minimo y excursion adversa en 3, 5 o 10 ruedas. |
| ¿Puede caer una magnitud concreta? | Probabilidad de -0,5%, -1%, -2%, -3%, -5% o -10%. |
| ¿Como termina el horizonte? | Probabilidad de cierre negativo/positivo y retorno mediano. |
| ¿La senal mejora realmente? | Probabilidad base, probabilidad condicionada y lift. |
| ¿Que tan firme es la estimacion? | Cantidad de casos e intervalo de confianza del 95%. |

Una probabilidad alta de nuevo minimo **no equivale** a igual probabilidad de cierre negativo: el SPX puede
hacer un minimo inferior durante la semana y luego recuperar. Por eso el motor separa recorrido, resultado final
y recuperacion.

---

## 7. La evidencia: el backtest

Cada senal se testeo contra la historia real (2008-2026, ~4.500 ruedas).

**Que significan los numeros:**

| Metrica | Que significa en criollo |
|---|---|
| Base rate | Cada cuanto ocurre la caida sin condicionar. La linea de partida. |
| Precision | De las veces que la senal se prendio, cuantas precedieron una caida. |
| Lift | Cuanto mejora contra el azar. Lift 3 = caida 3 veces mas probable. Lift 1 = inutil. |
| Recall | De todas las caidas, cuantas aviso la senal. |
| Edge | Cuanto peor le fue al mercado con la senal prendida. Positivo y grande = buena. |

**Ranking de senales (lift sobre SPY).** Base rate: 8,5% para -5%, 1,7% para -10%.

| Senal | Lift -5% | Lift -10% | Veredicto |
|---|---|---|---|
| Term backwardation (>1,0) | 2,68 | 7,02 | ★ La reina. La mejor de todas. |
| Term percentil > 90 | 2,61 | 6,32 | ★ Excelente, mas precisa. |
| Term percentil > 80 | 2,21 | 4,39 | ★ Muy buena, buena cobertura. |
| Combo 3+ senales | 2,21 | 4,61 | ★ Solido confirmador. |
| Term cruce 0,95 | 2,00 | 3,63 | ★ Alerta temprana y amplia. |
| VIX percentil > 80 | 1,97 | 2,77 | ★ La de mayor cobertura. |
| Credito en estres | 1,84 | 3,95 | ★ Brilla en caidas grandes. |
| QQQ-SPY debil | 1,67 | 1,72 | ✓ El relativo bueno (parejo). |
| SMH-QQQ debil | 1,52 | 1,55 | ~ Flojo, peso reducido. |
| NVDA-SMH debil | 1,42 | 1,03 | ~ El mas flojo. |
| VXN/VIX alto | 0,64 | 0,53 | ✗ No anticipa. Descartado. |

**Datos clave:** las senales funcionan mejor cuanto mas grande la caida (lift 2,7 para -5% vs 7,0 para
-10% en el term structure). Y se confirmo que **SMH no anticipa al mercado**: SMH y SPY giran a la par.

---

## 8. Como se determinaron los pesos y los rangos

Ningun peso esta puesto a ojo: cada uno se justifica con el backtest.

- El **term structure subio a 35%** porque fue, lejos, el mejor predictor (lift 2,7 a 7,0).
- El **credito subio a 25%** porque brilla en las caidas grandes (lift ~4), las que mas importa anticipar.
- El **VXN/VIX se saco** del puntaje: lift menor a 1 y edge negativo. Describe donde esta el nervio, pero no anticipa.
- De los relativos, solo **QQQ-SPY se gano peso alto** (25%): el unico parejo. SMH-QQQ y NVDA-SMH se degradaron.
- La **velocidad de compresion quedo secundaria** (lift ~1,5): pesa poco.

Los rangos de los semaforos (0,90 / 0,95 / 1,00) se fijaron combinando la logica del indicador con lo
que el backtest mostro que efectivamente precedia caidas, no con numeros redondos arbitrarios.

---

## 9. Glosario en criollo

| Termino | En criollo |
|---|---|
| Percentil | En que puesto esta el valor de hoy vs los ultimos 2 anios. |
| VIX / VXN | Medidor de miedo del S&P (VIX) y del Nasdaq (VXN). |
| Term structure | Compara el miedo a 1 mes contra el de 3 meses. |
| Contango | Estado normal: miedo a largo > miedo a corto. Tranquilo. |
| Backwardation | Estado de alarma: se invirtio. Miedo a corto > largo. Panico. |
| Breadth | Cuantas acciones aguantan vs cuantas caen. |
| RSI | Si algo esta sobrecomprado o sobrevendido (posible rebote). |
| Drawdown | Cuanto cayo desde su maximo del ultimo anio. |
| Credito HYG/IEF | Bonos riesgosos vs seguros. Si caen los riesgosos, hay estres. |
| Capitulacion | El miedo ya toco el extremo. Suele marcar pisos. |
| Lift | Cuanto mejora una senal contra tirar la moneda. |
| Lead | Cuantos dias de aviso te dio la senal antes de la caida. |

---

## 10. Limitaciones y advertencias

- **No es una bola de cristal.** Es probabilidad condicional: el term en backwardation acerto caidas de -10% el 46% de las veces (enorme contra el 1,7% de base, pero no es certeza).
- **La evidencia es in-sample.** Dice que funciono en 2008-2026; no garantiza que siga identico.
- **Las caidas grandes se apoyan en pocos episodios** (~10-15 en 17 anios). No afinar al decimal.
- **El "lead" mide ruedas hasta el fondo**, no dias de aviso. La metrica solida es el lift.
- **Datos gratuitos y demorados** (Yahoo + CBOE). Validar antes de operar.
- **No es asesoramiento ni recomendacion.** Es una guia de postura para uso profesional propio.

---

## 11. Ficha tecnica

| Aspecto | Detalle |
|---|---|
| Plataforma | Streamlit (navegador, local o Streamlit Cloud). |
| Fuentes | Yahoo Finance + CBOE. |
| Ventana de percentil | 504 ruedas (~2 anios). |
| Periodo del backtest | 2008-2026. |
| Archivos | app.py, scoring.py, data_sources.py, config.py, backtest.py. |
| Costo | Cero. Sin API keys. |

---

*Finsur - Documento de referencia interna. No constituye asesoramiento de inversion.*
"""


def render_manual():
    """Muestra el manual a pantalla completa con un boton para volver."""
    st.button("\u2190 Volver al tablero", on_click=_close_manual, type="primary")
    # Boton de descarga del .docx si esta presente junto a la app
    docx_path = os.path.join(os.path.dirname(__file__), "Manual_Tablero_Sentimiento.docx")
    if os.path.exists(docx_path):
        with open(docx_path, "rb") as f:
            st.download_button("\U0001F4E5 Descargar manual en Word (.docx)", f.read(),
                               file_name="Manual_Tablero_Sentimiento.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    st.markdown(MANUAL_MD)
    st.button("\u2190 Volver al tablero", key="back_bottom", on_click=_close_manual)


def _close_manual():
    st.session_state["show_manual"] = False


def open_manual():
    st.session_state["show_manual"] = True
