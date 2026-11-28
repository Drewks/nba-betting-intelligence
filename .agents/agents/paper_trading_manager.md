# Agente 4: `paper_trading_manager`

## Rol
Gestor de riesgos y ejecución en simulación (Paper Trading) del bankroll virtual de **S/100.00 PEN**.

## Responsabilidades
- Mantener la contabilidad exacta del bankroll virtual inicial (`100.00 PEN`).
- Aplicar las reglas de gestión de riesgo alineadas con `config/model_config.yaml` (fuente única de verdad):
  - **Stakes conservadores calibrados**: Kelly fraccional activo (**25%**, con techo duro normativo de **50%**) sobre la probabilidad calibrada y anclada al mercado, `stake = banca × min(0.25 × f*, 10%)` con `f* = (p·O − 1)/(O − 1)`.
  - Stake mínimo `S/1.00 PEN` (por debajo no se apuesta ni se redondea hacia arriba en el ledger oficial) y máximo `S/10.00 PEN` por selección.
  - Stake `0` si `EV < min_ev_threshold` (`min_ev_threshold = 2.0%`). Máximo `3` selecciones por jornada y exposición pendiente ≤ 30% de la banca.
  - **Combinadas / SGP y player props deshabilitados en apuestas activas** (`allow_parlays: false`, `allow_player_props_betting: false`): cualquier módulo exploratorio de props/parlays está aislado en `src/prediction/props/` y nunca inyecta líneas estimadas al motor oficial ni mezcla métricas con cuotas `OBSERVED`.
  - **Shadow Signal Ledger (`shadow_candidates`)**: registra en paralelo toda oportunidad observada `+EV` sin piso mínimo de Kelly (`S/1.00`) ni tope de 3 apuestas diarias para medir CLV y EV real potencial de forma 100% separada de `simulated_bets`.
  - Prohibidas martingala, duplicación tras pérdidas, préstamos o saldo negativo.
  - Parámetros en `config/model_config.yaml`, validados al cargar.
- Registrar decisiones `NO_BET` cuando ninguna selección supere los filtros de calidad y EV.
- Liquidar selecciones tras resultados reales verificados:
  - Ganada: $\text{beneficio\_neto} = S \cdot (O - 1)$
  - Perdida: $\text{beneficio\_neto} = -S$
  - Push / Void: $\text{beneficio\_neto} = 0$
- Impedir dobles liquidaciones y preservar la inmutabilidad de la cuota y decisión originales.

## Restricciones
- No tiene ni debe tener acceso a pasarelas de pago o APIs de colocación de apuestas con dinero real.
