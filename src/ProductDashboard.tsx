import { FormEvent, useEffect, useRef, useState } from 'react'
import { LegalFooter } from './LegalPages'
import type { SessionUser } from './AuthPages'

type Dish = {
  id: string
  name: string
  category: string
  ingredient_cost: number
  price: number
  forecast: number
  confidence_low: number
  confidence_high: number
  prep: number
  previous_prep: number | null
  delta: number | null
  expected_leftover: number
  expected_missed: number
  forecast_source: 'trained' | 'standard'
}

type Plan = {
  date: string
  covers: number
  cover_source: 'forecast' | 'manual'
  cover_history_days: number
  forecast_covers: number | null
  model_version: string | null
  dishes: Dish[]
  insights: { title: string; detail: string }[]
  summary: {
    prep_units: number
    expected_waste: number
    usual_waste: number | null
    at_risk: number
  }
  backtest: {
    days: number
    available: boolean
    usual_waste: number | null
    model_waste: number | null
    difference: number | null
    observed_missed: number | null
  }
  trend: { day: string; prepared: number | null; waste: number | null }[]
}

type View = 'plan' | 'history' | 'costs' | 'import'
type CostDraft = { ingredient_cost: string; price: string }
type DishServices = { name: string; services: number }
type ImportPreview = { dishes: number; services: number; rows: number; prepared_rows: number; dish_names: string[]; dish_costs: { id: string; name: string; ingredient_cost: number | null; price: number | null }[]; dish_services: DishServices[]; eligible_dishes: number; first_day: string; last_day: string }
type ImportField = 'date' | 'dish' | 'sold' | 'covers' | 'prepared' | 'ingredient_cost' | 'price' | 'category'
type ImportMapping = { sheet: string; header_row: number; layout: 'long' | 'wide'; date_format: 'auto' | 'dmy' | 'mdy'; aggregation: 'none' | 'sum'; columns: Record<ImportField, string>; dish_columns: string[] }
type ImportHeaderOption = { header_row: number; headers: string[]; sample: Record<string, string>[] }
type ImportSource = { filename: string; content_base64: string; signature: string; mapping_source: 'saved' | 'agent' | 'rules'; sheets: (ImportHeaderOption & { name: string; rows: number; header_options: ImportHeaderOption[] })[] }
type ModelMetrics = { promoted_dishes: number; tested_dishes: number; results?: { dish_id: string; services_tested: number; baseline_mae: number; candidate_mae: number; passed: boolean }[] }
type ModelStage = 'queued' | 'analyzing' | 'training' | 'validating' | 'promoting' | 'complete'
type ModelStatus = { enabled: boolean; eligible_dishes: number; max_services: number; required_services: number; dish_services: DishServices[]; job: { id: string; status: string; stage: ModelStage; reason: string | null; metrics: ModelMetrics | null } | null; active: { id: string; created_at: number; metrics: ModelMetrics } | null }
type ServiceSummary = { day: string; covers: number | null; total_dishes: number; logged_dishes: number; complete: boolean; prepared: number; sold: number; leftovers: number; ingredient_waste: number; dishes: { id: string; name: string; prepared: number; sold: number; leftover: number }[] }

const money = (value: number) => '$' + value.toLocaleString('en-NZ', { maximumFractionDigits: 0 })
const unitMoney = (value: number) => '$' + value.toFixed(2)
const localDate = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
const longDate = (value: string) => new Date(value + 'T12:00:00').toLocaleDateString('en-NZ', { weekday: 'long', day: 'numeric', month: 'long' })
export default function ProductDashboard({ user, onSignOut, onAuthLost }: { user: SessionUser; onSignOut: () => void; onAuthLost: () => void }) {
  const [view, setView] = useState<View>('import')
  const [hasData, setHasData] = useState(user.data_mode === 'imported')
  const [plan, setPlan] = useState<Plan | null>(null)
  const [covers, setCovers] = useState('82')
  const [needsCovers, setNeedsCovers] = useState(false)
  const [showCoverOverride, setShowCoverOverride] = useState(false)
  const [coverHistoryDays, setCoverHistoryDays] = useState(0)
  const [costs, setCosts] = useState<Record<string, CostDraft>>({})
  const [actualDish, setActualDish] = useState<Dish | null>(null)
  const [actualDay, setActualDay] = useState(localDate())
  const [actualCovers, setActualCovers] = useState('82')
  const [prepared, setPrepared] = useState('')
  const [sold, setSold] = useState('')
  const [serviceSummary, setServiceSummary] = useState<ServiceSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [importText, setImportText] = useState('')
  const [importFileName, setImportFileName] = useState('')
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [importSource, setImportSource] = useState<ImportSource | null>(null)
  const [importMapping, setImportMapping] = useState<ImportMapping | null>(null)
  const [importSample, setImportSample] = useState<Record<string, string>[]>([])
  const [importBusy, setImportBusy] = useState(false)
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null)
  const seenModelId = useRef<string | null | undefined>(undefined)

  async function loadModelStatus() {
    const response = await fetch('/api/models/status')
    if (response.status === 401) { onAuthLost(); return }
    if (!response.ok) return
    const status: ModelStatus = await response.json()
    setModelStatus(status)
    const activeId = status.active?.id ?? null
    if (hasData && seenModelId.current !== undefined && seenModelId.current !== activeId) void loadPlan()
    seenModelId.current = activeId
  }

  async function loadPlan(nextCovers?: number, fallbackCovers?: number) {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextCovers === undefined ? {} : { covers: nextCovers }),
      })
      if (response.status === 401) { onAuthLost(); return }
      if (response.status === 409) {
        const body = await response.json()
        if (body.detail?.code === 'import_needed') {
          setHasData(false)
          setView('import')
          setPlan(null)
          return
        }
        if (body.detail?.code === 'covers_needed') {
          if (fallbackCovers !== undefined) {
            await loadPlan(fallbackCovers)
            return
          }
          setNeedsCovers(true)
          setCovers('')
          setCoverHistoryDays(body.detail.service_days)
          setPlan(null)
          return
        }
      }
      if (!response.ok) throw new Error('Could not load the prep plan.')
      const nextPlan: Plan = await response.json()
      setPlan(nextPlan)
      setCovers(String(nextPlan.covers))
      setNeedsCovers(false)
      setShowCoverOverride(false)
      setCoverHistoryDays(nextPlan.cover_history_days)
      setCosts(Object.fromEntries(nextPlan.dishes.map(dish => [dish.id, {
        ingredient_cost: dish.ingredient_cost.toFixed(2),
        price: dish.price.toFixed(2),
      }])))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load the prep plan.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (user.data_mode === 'imported') void loadPlan(); else setLoading(false) }, [])
  useEffect(() => {
    void loadModelStatus()
    const timer = window.setInterval(() => { void loadModelStatus() }, 5000)
    return () => window.clearInterval(timer)
  }, [hasData])

  function openActual(dish: Dish) {
    setActualDish(dish)
    setActualDay(localDate())
    setActualCovers(String(plan?.covers ?? covers))
    setPrepared('')
    setSold('')
    setError('')
    setNotice('')
  }

  async function saveActual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!actualDish) return
    const made = Number(prepared)
    const soldCount = Number(sold)
    if (!Number.isInteger(made) || !Number.isInteger(soldCount) || soldCount > made) {
      setError('Sold must be a whole number no greater than prepared.')
      return
    }
    setSavingId(actualDish.id)
    setError('')
    try {
      const response = await fetch('/api/actuals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token },
        body: JSON.stringify({ day: actualDay, covers: Number(actualCovers), dish_id: actualDish.id, prepared: made, sold: soldCount }),
      })
      if (response.status === 401) { onAuthLost(); return }
      const body = await response.json()
      if (!response.ok) {
        throw new Error(body.detail || 'Could not save the service actuals.')
      }
      setActualDish(null)
      setServiceSummary(body.summary as ServiceSummary)
      setNotice(`${actualDish.name}: ${made - soldCount} leftover portions recorded.`)
      await loadPlan(plan?.cover_source === 'manual' && plan.cover_history_days >= 14 ? plan.covers : undefined, plan?.covers)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the service actuals.')
    } finally {
      setSavingId(null)
    }
  }

  async function saveCosts(dish: Dish) {
    const draft = costs[dish.id]
    const ingredientCost = Number(draft?.ingredient_cost)
    const price = Number(draft?.price)
    if (!Number.isFinite(ingredientCost) || ingredientCost <= 0 || !Number.isFinite(price) || price <= ingredientCost) {
      setError('Enter a positive ingredient cost and a sale price above that cost.')
      return
    }
    setSavingId(dish.id)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/dishes/${dish.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token },
        body: JSON.stringify({ ingredient_cost: ingredientCost, price }),
      })
      if (response.status === 401) { onAuthLost(); return }
      if (!response.ok) {
        const body = await response.json()
        throw new Error(body.detail || 'Could not save the dish costs.')
      }
      await loadPlan(plan?.cover_source === 'manual' ? plan.covers : undefined)
      setNotice(`${dish.name} costs saved. The plan has been recalculated.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the dish costs.')
    } finally {
      setSavingId(null)
    }
  }

  const change = plan && plan.summary.usual_waste !== null && plan.summary.usual_waste > 0
    ? Math.round((plan.summary.usual_waste - plan.summary.expected_waste) / plan.summary.usual_waste * 100)
    : 0

  async function inspectFile(file: File) {
    setImportPreview(null)
    setImportSource(null)
    setImportMapping(null)
    setImportSample([])
    setError('')
    setNotice('')
    setImportFileName(file.name)
    if (file.size > 4_000_000) { setError('File must be smaller than 4 MB.'); return }
    setImportBusy(true)
    try {
      const bytes = new Uint8Array(await file.arrayBuffer())
      let binary = ''
      for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768))
      const content_base64 = btoa(binary)
      const response = await fetch('/api/import/inspect', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token }, body: JSON.stringify({ filename: file.name, content_base64 }) })
      if (response.status === 401) { onAuthLost(); return }
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not read this file.')
      const source = { filename: file.name, content_base64, signature: body.signature, mapping_source: body.mapping_source, sheets: body.sheets } as ImportSource
      const mapping = body.mapping as ImportMapping
      setImportSource(source)
      setImportMapping(mapping)
      await previewMapped(source, mapping)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not read this file.')
    } finally {
      setImportBusy(false)
    }
  }

  async function previewMapped(source = importSource, mapping = importMapping) {
    if (!source || !mapping) return
    setImportBusy(true)
    setImportPreview(null)
    setError('')
    try {
      const response = await fetch('/api/import/normalize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename: source.filename, content_base64: source.content_base64, mapping }) })
      if (response.status === 401) { onAuthLost(); return }
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not convert this spreadsheet.')
      const preview = body.preview as ImportPreview
      setImportText(body.csv_text)
      setImportSample(body.sample as Record<string, string>[])
      setImportPreview(preview)
      await importCsv(preview, body.csv_text, source, mapping)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not convert this spreadsheet.')
    } finally {
      setImportBusy(false)
    }
  }

  async function importCsv(preview = importPreview, csvText = importText, source = importSource, mapping = importMapping) {
    if (!preview) return
    const menu_costs: Record<string, { ingredient_cost: number; price: number }> = {}
    for (const dish of preview.dish_costs) {
      if (dish.ingredient_cost && dish.price) menu_costs[dish.id] = { ingredient_cost: dish.ingredient_cost, price: dish.price }
    }
    setImportBusy(true)
    setError('')
    try {
      const response = await fetch('/api/import/commit', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token }, body: JSON.stringify({ csv_text: csvText, menu_costs, source_mapping: mapping, source_signature: source?.signature }) })
      if (response.status === 401) { onAuthLost(); return }
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not import this CSV.')
      setHasData(true)
      await loadPlan()
      await loadModelStatus()
      setNotice(body.services < 14
        ? `${body.rows} ${body.rows === 1 ? 'row' : 'rows'} imported. Enter expected covers to build tomorrow’s plan.`
        : `${body.rows} ${body.rows === 1 ? 'row' : 'rows'} across ${body.services} services imported. Tomorrow’s plan now uses your data.${body.default_cost_dishes ? ` Default cost assumptions were applied to ${body.default_cost_dishes} ${body.default_cost_dishes === 1 ? 'dish' : 'dishes'}; adjust them in Menu costs.` : ''}`)
      setImportPreview(null)
      setImportSource(null)
      setImportMapping(null)
      setImportSample([])
      setImportText('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not import this CSV.')
    } finally {
      setImportBusy(false)
    }
  }

  const importFlowStep = importBusy ? 2 : hasData ? 4 : importPreview ? 3 : 1

  return <div className="product-shell">
    <header className="product-header">
      <button className="product-brand" onClick={() => setView('import')} aria-label="YLD Agent">YLD<span>.</span></button>
      <nav className="product-nav" aria-label="Planner navigation">
        <button className={view === 'import' ? 'active' : ''} aria-current={view === 'import' ? 'page' : undefined} onClick={() => { setView('import'); setError(''); setNotice('') }}>YLD AGENT</button>
      </nav>
      <button className="product-signout" onClick={onSignOut}>SIGN OUT ↗</button>
    </header>

    <main className="product-main">
      {error && !actualDish && <div className="product-message product-error" role="alert">{error}</div>}
      {notice && <div className="product-message" role="status">{notice}</div>}

      {view === 'plan' && <>
        <div className="product-page-head">
          <div><span className="product-kicker">{plan ? longDate(plan.date) : 'Tomorrow'}</span><h1>Tomorrow's prep</h1><p>One clear prep quantity for every dish, based on past sales and the cost of waste.</p></div>
          <div className="product-total"><strong>{plan?.summary.prep_units ?? '—'}</strong><span>TOTAL PORTIONS</span></div>
        </div>
        <button className="product-agent-entry" type="button" onClick={() => setView('import')}>
          <span><small>YLD PREP PLANNER</small><strong>See your sales become a forecast.</strong><em>Upload data and inspect your prep plan.</em></span>
          <b>OPEN DATA <span aria-hidden="true">↗</span></b>
        </button>
        {plan && !showCoverOverride && <div className="product-cover-bar">
          <div><span className="product-kicker">{plan.cover_source === 'forecast' ? `AUTOMATIC FORECAST · ${plan.cover_history_days} SERVICES` : 'MANUAL ESTIMATE'}</span><strong>{plan.covers} covers</strong><p>{plan.cover_source === 'forecast' ? 'Estimated from your service history. It updates as actuals are logged.' : plan.forecast_covers === null ? `${plan.cover_history_days} of 14 services recorded. We’ll estimate covers automatically once there’s enough history.` : `Adjusted from the ${plan.forecast_covers}-cover forecast.`}</p></div>
          <div className="product-cover-actions"><button className="product-secondary" onClick={() => { setCovers(String(plan.covers)); setShowCoverOverride(true) }}>ADJUST COVERS</button>{plan.cover_source === 'manual' && plan.forecast_covers !== null && <button className="product-secondary" disabled={loading} onClick={() => void loadPlan()}>USE FORECAST</button>}</div>
        </div>}
        {!plan && loading && <div className="product-cover-bar"><span className="product-kicker">CALCULATING TOMORROW’S PLAN…</span></div>}
        {(needsCovers || showCoverOverride || (!plan && !loading && !error)) && <form className="product-controls" onSubmit={event => { event.preventDefault(); setNotice(''); void loadPlan(Number(covers)) }}>
          {needsCovers && <p className="product-cover-help">Add an estimate for tomorrow. After 14 recorded services, YLD will forecast covers automatically. ({coverHistoryDays}/14 recorded)</p>}
          <label>EXPECTED COVERS<input type="number" min="1" max="1000" required value={covers} onChange={event => setCovers(event.target.value)} /></label>
          <button className="product-primary" disabled={loading || !covers || Number(covers) < 1 || Number(covers) > 1000}>{loading ? 'CALCULATING…' : 'UPDATE PLAN'} <span>→</span></button>
          {showCoverOverride && <button type="button" className="product-secondary" onClick={() => setShowCoverOverride(false)}>CANCEL</button>}
        </form>}
        <div className="product-stats">
          <div><span>EXPECTED INGREDIENT WASTE</span><strong>{plan ? money(plan.summary.expected_waste) : '—'}</strong></div>
          <div><span>USUAL DAILY WASTE</span><strong>{plan?.summary.usual_waste == null ? '—' : money(plan.summary.usual_waste)}</strong></div>
          <div><span>EXPECTED MISSED PLATES</span><strong>{plan?.summary.at_risk ?? '—'}</strong></div>
          <div className="product-stat-accent"><span>WASTE VS USUAL</span><strong>{plan?.summary.usual_waste == null ? '—' : `${change > 0 ? '−' : change < 0 ? '+' : ''}${Math.abs(change)}%`}</strong></div>
        </div>
        {!!plan?.insights.length && <section className="product-section" aria-labelledby="insights-title">
          <div className="product-section-head"><div><span className="product-kicker">FROM YOUR SERVICE DATA</span><h2 id="insights-title">Prep insights</h2></div></div>
          <div className="product-insights">{plan.insights.map(insight => <article key={insight.title}><h3>{insight.title}</h3><p>{insight.detail}</p></article>)}</div>
        </section>}
        <section className="product-section" aria-labelledby="dish-plan-title">
          <div className="product-section-head"><div><span className="product-kicker">THE RECOMMENDATION</span><h2 id="dish-plan-title">Dish by dish</h2></div><span>{plan?.dishes.length ?? '—'} {plan?.dishes.length === 1 ? 'DISH' : 'DISHES'}</span></div>
          <div className="product-dish-list">
            {plan?.dishes.map(dish => <article className="product-dish" key={dish.id}>
              <div className="product-dish-name"><h3>{dish.name}</h3><span>{dish.category} · {unitMoney(dish.ingredient_cost)} INGREDIENT COST</span></div>
              <div className="product-dish-quantity"><span>PREP</span><strong>{dish.prep}</strong><small>{dish.delta === null ? 'PREP NOT RECORDED' : `${dish.delta > 0 ? '+' : ''}${dish.delta} VS LAST RECORDED PREP`}</small></div>
              <div className="product-dish-detail"><span>{dish.forecast_source === 'trained' ? 'YLD AGENT FORECAST' : 'STANDARD FORECAST'}</span><strong>{dish.forecast}</strong><small>{dish.confidence_low}–{dish.confidence_high} likely range</small></div>
              <div className="product-dish-detail"><span>EXPECTED LEFTOVER</span><strong>{dish.expected_leftover}</strong><small>{unitMoney(dish.expected_leftover * dish.ingredient_cost)} of ingredients</small></div>
              <button className="product-row-action" onClick={() => openActual(dish)}>LOG ACTUAL <span>→</span></button>
            </article>)}
          </div>
          <p className="product-footnote">Why these numbers? The demand model learns from earlier services. The planner weighs the ingredient cost of leftovers against the margin lost when a dish sells out.</p>
        </section>
      </>}

      {view === 'history' && <>
        <div className="product-page-head"><div><span className="product-kicker">LEARN FROM EVERY SERVICE</span><h1>History</h1><p>We replayed past services using only the sales available before each one.</p></div></div>
        <section className="product-section" aria-labelledby="backtest-title">
          <div className="product-section-head"><div><span className="product-kicker">{plan?.backtest.days ? `${plan.backtest.days} SERVICE ${plan.backtest.days === 1 ? 'DATE' : 'DATES'} TESTED` : 'NO COMPARISON YET'}</span><h2 id="backtest-title">How the plan compares</h2></div></div>
          <div className="product-comparison"><div><span>USUAL APPROACH</span><strong>{plan?.backtest.usual_waste == null ? '—' : money(plan.backtest.usual_waste)}</strong><small>ingredient waste</small></div><div><span>YLD RECOMMENDATIONS</span><strong>{plan?.backtest.model_waste == null ? '—' : money(plan.backtest.model_waste)}</strong><small>estimated ingredient waste</small></div><div className="product-comparison-result"><span>DIFFERENCE</span><strong>{plan?.backtest.difference == null ? '—' : money(plan.backtest.difference)}</strong><small>{plan?.backtest.observed_missed ?? '—'} observed sales would be at risk</small></div></div>
          <p className="product-footnote">{plan?.backtest.available === false ? 'Add prepared quantities or log actuals to compare waste. Sales alone cannot prove historical savings.' : `Only dishes with at least 14 earlier sales records and known prep are tested. Historical stockouts may hide demand; missed plates count only observed sales.${plan?.model_version ? ' This historic waste simulation uses the standard forecast; trained models are assessed separately on held-out sales.' : ''}`}</p>
        </section>
        <section className="product-section" aria-labelledby="recent-title"><div className="product-section-head"><div><span className="product-kicker">RECENT ACTUALS</span><h2 id="recent-title">Services</h2></div></div><div className="product-history-list">{plan?.trend.slice().reverse().map(day => <div key={day.day}><strong>{longDate(day.day)}</strong><span>{day.prepared == null ? 'Prep not recorded' : `${day.prepared} portions prepared`}</span><span>{day.waste == null ? 'Waste not recorded' : `${money(day.waste)} ingredient waste`}</span></div>)}</div></section>
      </>}

      {view === 'costs' && <>
        <div className="product-page-head"><div><span className="product-kicker">SET UP YOUR MENU</span><h1>Menu costs</h1><p>Enter the ingredient cost and sale price per portion. These numbers shape every prep recommendation.</p></div></div>
        <section className="product-section" aria-labelledby="costs-title"><div className="product-section-head"><div><span className="product-kicker">{plan?.dishes.length ?? '—'} {plan?.dishes.length === 1 ? 'DISH' : 'DISHES'}</span><h2 id="costs-title">Cost per portion</h2></div></div><div className="product-cost-list">{plan?.dishes.map(dish => <article key={dish.id} className="product-cost-row"><div><h3>{dish.name}</h3><span>{dish.category}</span></div><label>INGREDIENT COST ($)<input type="number" min="0.01" step="0.01" value={costs[dish.id]?.ingredient_cost ?? ''} onChange={event => setCosts(current => ({ ...current, [dish.id]: { ...current[dish.id], ingredient_cost: event.target.value } }))} /></label><label>SALE PRICE ($)<input type="number" min="0.01" step="0.01" value={costs[dish.id]?.price ?? ''} onChange={event => setCosts(current => ({ ...current, [dish.id]: { ...current[dish.id], price: event.target.value } }))} /></label><button className="product-secondary" disabled={savingId === dish.id} onClick={() => void saveCosts(dish)}>{savingId === dish.id ? 'SAVING…' : 'SAVE'}</button></article>)}</div><p className="product-footnote">Use your per-portion costs and sale prices. Saving a change recalculates the plan.</p></section>
      </>}

      {view === 'import' && <>
        <div className="product-page-head"><div><span className="product-kicker">YOUR DATA · YOUR MODEL</span><h1>YLD Agent.</h1><p>Upload sales, watch the agent test model options, and see exactly which forecasts earn a place in your prep plan.</p></div></div>
        <section className="product-agent-workspace" aria-labelledby="import-title">
          <div className="product-agent-upload"><div className="product-section-head"><div><span className="product-kicker">START OR UPDATE YOUR PLAN</span><h2 id="import-title">Upload sales data</h2></div></div>
          <div className="product-import-body">
            <ol className="product-import-flow" aria-label="Sales import progress">{['UPLOAD FILE', 'YLD AGENT', 'PLAN READY'].map((label, index) => <li key={label} className={index + 1 < importFlowStep ? 'is-done' : index + 1 === importFlowStep ? 'is-active' : 'is-waiting'} aria-current={index + 1 === importFlowStep ? 'step' : undefined}><span>{String(index + 1).padStart(2, '0')}</span><strong>{label}</strong><b aria-hidden="true">{index + 1 < importFlowStep ? '✓' : index + 1 === importFlowStep ? '●' : '·'}</b></li>)}</ol>
            <details className="product-import-guide" open>
              <summary><span>WHAT YLD NEEDS FROM YOUR FILE</span><b aria-hidden="true">+</b></summary>
              <p>YLD needs a service date, dish, portions sold, and covers. Prepared quantities and per-portion costs help evaluate waste and build a prep plan. A missing covers figure needs another source; it cannot be inferred from orders.</p>
            </details>
            <div className="product-import-actions">{hasData && <a className="product-secondary" href="/api/export/history" download="yld-service-history.csv">DOWNLOAD CURRENT DATA ↓</a>}<label className="product-file-label">CHOOSE CSV OR XLSX<input type="file" accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event => setPendingImportFile(event.target.files?.[0] ?? null)} /></label></div>
            {pendingImportFile && <div className="product-import-agent-gate"><span className="product-kicker">AGENT CONTEXT GATE</span><strong>Let YLD map this file?</strong><p>YLD will send the sheet names, column headers, and up to three sample rows to the mapping service. The agent will map the file automatically, then show the converted-data preview.</p><div><button className="product-secondary" type="button" onClick={() => setPendingImportFile(null)}>CANCEL</button><button className="product-primary" type="button" disabled={importBusy} onClick={() => { const file = pendingImportFile; setPendingImportFile(null); if (file) void inspectFile(file) }}>MAP WITH YLD AGENT <span>→</span></button></div></div>}
            {importBusy && <p role="status">YLD is mapping, checking, and building your plan…</p>}
            {importPreview && <div className="product-import-preview">
              <span className="product-kicker">READY TO IMPORT · {importFileName}</span>
              <strong>{importPreview.services} {importPreview.services === 1 ? 'service' : 'services'} · {importPreview.dishes} {importPreview.dishes === 1 ? 'dish' : 'dishes'}</strong>
              <p>{importPreview.first_day} to {importPreview.last_day}. {importPreview.prepared_rows === 0 ? 'No prepared quantities: YLD can forecast demand, but cannot compare actual waste yet.' : `${importPreview.prepared_rows} of ${importPreview.rows} rows include prepared quantities for waste comparisons.`}</p>
              <p><strong>{importPreview.rows}</strong> sales records have been added to your prep plan.</p>
              {importSample.length > 0 && <div className="product-import-converted-sample"><span>CONVERTED ROWS</span>{importSample.map((row, index) => <small key={index}>{row.date} · {row.dish} · {row.sold} sold · {row.covers} covers{row.prepared ? ` · ${row.prepared} prepared` : ''}</small>)}</div>}
              {importPreview.services < 14 && <p role="note">With fewer than 14 services, enter your expected covers for tomorrow after import. Covers become automatic as more services are recorded.</p>}
              <p>Your file has been processed automatically. Update any cost assumptions later in Menu costs.</p>
            </div>}
          </div>
        </div>
        <section className="product-analytics" aria-labelledby="analytics-title">
          <div className="product-analytics-head"><div><span className="product-kicker">YOUR KITCHEN AT A GLANCE</span><h2 id="analytics-title">Analytics</h2></div><span>{importPreview ? 'FILE PREVIEW' : 'CURRENT PLAN'}</span></div>
          <div className="product-analytics-grid">
            <article><span>SERVICES</span><strong>{importPreview?.services ?? modelStatus?.max_services ?? plan?.trend.length ?? '—'}</strong><small>{importPreview ? 'in this file' : 'recorded services'}</small></article>
            <article><span>DISHES</span><strong>{importPreview?.dishes ?? plan?.dishes.length ?? '—'}</strong><small>{importPreview ? 'ready to import' : 'in your plan'}</small></article>
            <article><span>TOMORROW'S COVERS</span><strong>{plan?.covers ?? '—'}</strong><small>{plan ? plan.cover_source === 'forecast' ? 'forecast' : 'manual estimate' : 'available after import'}</small></article>
            <article><span>PORTIONS TO PREP</span><strong>{plan?.summary.prep_units ?? '—'}</strong><small>across your menu</small></article>
          </div>
        </section>
        </section>
      </>}
    </main>

    <LegalFooter />
    {actualDish && <div className="product-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setActualDish(null) }}><form className="product-dialog" role="dialog" aria-modal="true" aria-labelledby="actual-title" onSubmit={event => void saveActual(event)}><button type="button" className="product-close" aria-label="Close" onClick={() => setActualDish(null)}>×</button><span className="product-kicker">AFTER SERVICE</span><h2 id="actual-title">Log {actualDish.name}</h2><p>Record what happened. Leftovers feed tomorrow's forecast.</p><label>SERVICE DATE<input required type="date" max={localDate()} value={actualDay} onChange={event => setActualDay(event.target.value)} /></label><label>ACTUAL COVERS<input required type="number" min="1" max="1000" value={actualCovers} onChange={event => setActualCovers(event.target.value)} /></label><div className="product-dialog-pair"><label>PREPARED<input required type="number" min="0" step="1" value={prepared} onChange={event => setPrepared(event.target.value)} /></label><label>SOLD<input required type="number" min="0" step="1" max={prepared || undefined} value={sold} onChange={event => setSold(event.target.value)} /></label></div><div className="product-leftover"><span>LEFTOVER</span><strong>{prepared !== '' && sold !== '' ? Math.max(0, Number(prepared) - Number(sold)) : '—'}</strong></div>{error && <div className="product-message product-error" role="alert">{error}</div>}<button className="product-primary" disabled={savingId === actualDish.id}>{savingId === actualDish.id ? 'SAVING…' : 'SAVE ACTUALS'} <span>→</span></button></form></div>}
    {serviceSummary && <div className="product-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setServiceSummary(null) }}><section className="product-dialog product-service-summary" role="dialog" aria-modal="true" aria-labelledby="service-summary-title"><button type="button" className="product-close" aria-label="Close summary" onClick={() => setServiceSummary(null)}>×</button><span className="product-kicker">{serviceSummary.complete ? 'SERVICE SUMMARY' : 'SERVICE IN PROGRESS'}</span><h2 id="service-summary-title">{serviceSummary.complete ? <>Service<br/>logged.</> : <>Actuals<br/>saved.</>}</h2><p>{serviceSummary.complete ? `All ${serviceSummary.total_dishes} dishes are recorded for ${longDate(serviceSummary.day)}. Tomorrow’s forecast will use these actuals.` : `${serviceSummary.logged_dishes} of ${serviceSummary.total_dishes} dishes logged. Keep recording actuals to complete this service.`}</p><div className="product-service-summary-metrics"><div><span>PREPARED</span><strong>{serviceSummary.prepared}</strong></div><div><span>SOLD</span><strong>{serviceSummary.sold}</strong></div><div><span>LEFT OVER</span><strong>{serviceSummary.leftovers}</strong></div><div><span>INGREDIENT VALUE</span><strong>{money(serviceSummary.ingredient_waste)}</strong></div></div><div className="product-service-summary-dishes">{serviceSummary.dishes.map(dish => <div key={dish.id}><span>{dish.name}</span><span>{dish.prepared} prepared · {dish.sold} sold · {dish.leftover} left</span></div>)}</div><button className="product-primary" type="button" onClick={() => setServiceSummary(null)}>{serviceSummary.complete ? 'CLOSE SUMMARY' : 'CONTINUE LOGGING'} <span>→</span></button></section></div>}
  </div>
}
