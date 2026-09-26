import { FormEvent, useEffect, useState } from 'react'
import { LegalFooter } from './LegalPages'
import type { SessionUser } from './AuthPages'
import csvTemplate from '../templates/service-history.csv?raw'

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
}

type Plan = {
  date: string
  covers: number
  cover_source: 'forecast' | 'manual'
  cover_history_days: number
  forecast_covers: number | null
  dishes: Dish[]
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
type ImportPreview = { dishes: number; services: number; rows: number; prepared_rows: number; dish_names: string[]; dish_costs: { id: string; name: string; ingredient_cost: number | null; price: number | null }[]; first_day: string; last_day: string }

const money = (value: number) => '$' + value.toLocaleString('en-NZ', { maximumFractionDigits: 0 })
const unitMoney = (value: number) => '$' + value.toFixed(2)
const localDate = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
const longDate = (value: string) => new Date(value + 'T12:00:00').toLocaleDateString('en-NZ', { weekday: 'long', day: 'numeric', month: 'long' })
export default function ProductDashboard({ user, onSignOut, onAuthLost, onAdmin }: { user: SessionUser; onSignOut: () => void; onAuthLost: () => void; onAdmin: () => void }) {
  const [view, setView] = useState<View>(user.data_mode === 'empty' ? 'import' : 'plan')
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
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [importText, setImportText] = useState('')
  const [importFileName, setImportFileName] = useState('')
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [importCosts, setImportCosts] = useState<Record<string, CostDraft>>({})
  const [importBusy, setImportBusy] = useState(false)

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
      if (!response.ok) {
        const body = await response.json()
        throw new Error(body.detail || 'Could not save the service actuals.')
      }
      setActualDish(null)
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

  async function previewCsv(file: File) {
    setImportPreview(null)
    setError('')
    setNotice('')
    setImportFileName(file.name)
    if (file.size > 2_000_000) { setError('CSV must be smaller than 2 MB.'); return }
    setImportBusy(true)
    try {
      const csv_text = await file.text()
      const response = await fetch('/api/import/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ csv_text }) })
      if (response.status === 401) { onAuthLost(); return }
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not read this CSV.')
      setImportText(csv_text)
      const preview = body as ImportPreview
      setImportCosts(Object.fromEntries(preview.dish_costs.map(dish => [dish.id, { ingredient_cost: dish.ingredient_cost?.toFixed(2) ?? '', price: dish.price?.toFixed(2) ?? '' }])))
      setImportPreview(preview)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not read this CSV.')
    } finally {
      setImportBusy(false)
    }
  }

  async function importCsv() {
    if (!importPreview) return
    const menu_costs: Record<string, { ingredient_cost: number; price: number }> = {}
    for (const dish of importPreview.dish_costs) {
      const ingredient_cost = Number(importCosts[dish.id]?.ingredient_cost)
      const price = Number(importCosts[dish.id]?.price)
      if (!Number.isFinite(ingredient_cost) || ingredient_cost <= 0 || !Number.isFinite(price) || price <= ingredient_cost) {
        setError(`Enter a positive ingredient cost and higher sale price for ${dish.name}.`)
        return
      }
      menu_costs[dish.id] = { ingredient_cost, price }
    }
    if (hasData && !window.confirm(`Replace all current dishes and service history for ${user.workspace_name} with ${importFileName}? This cannot be undone.`)) return
    setImportBusy(true)
    setError('')
    try {
      const response = await fetch('/api/import/commit', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token }, body: JSON.stringify({ csv_text: importText, menu_costs }) })
      if (response.status === 401) { onAuthLost(); return }
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not import this CSV.')
      setHasData(true)
      setView('plan')
      await loadPlan()
      setNotice(body.services < 14
        ? `${body.rows} ${body.rows === 1 ? 'row' : 'rows'} imported. Enter expected covers to build tomorrow’s plan.`
        : `${body.rows} ${body.rows === 1 ? 'row' : 'rows'} across ${body.services} services imported. Tomorrow’s plan now uses your data.`)
      setImportPreview(null)
      setImportText('')
      setImportCosts({})
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not import this CSV.')
    } finally {
      setImportBusy(false)
    }
  }

  return <div className="product-shell">
    <header className="product-header">
      <button className="product-brand" onClick={() => setView('plan')} aria-label="YLD plan">YLD<span>.</span></button>
      <nav className="product-nav" aria-label="Planner navigation">
        {(hasData ? ['plan', 'history', 'costs', 'import'] as const : ['import'] as const).map(item => <button key={item} className={view === item ? 'active' : ''} aria-current={view === item ? 'page' : undefined} onClick={() => { setView(item); setError(''); setNotice('') }}>{item === 'costs' ? 'MENU COSTS' : item === 'import' ? 'IMPORT CSV' : item.toUpperCase()}</button>)}
        {user.is_admin && <button onClick={onAdmin}>ADMIN</button>}
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
        <section className="product-section" aria-labelledby="dish-plan-title">
          <div className="product-section-head"><div><span className="product-kicker">THE RECOMMENDATION</span><h2 id="dish-plan-title">Dish by dish</h2></div><span>{plan?.dishes.length ?? '—'} {plan?.dishes.length === 1 ? 'DISH' : 'DISHES'}</span></div>
          <div className="product-dish-list">
            {plan?.dishes.map(dish => <article className="product-dish" key={dish.id}>
              <div className="product-dish-name"><h3>{dish.name}</h3><span>{dish.category} · {unitMoney(dish.ingredient_cost)} INGREDIENT COST</span></div>
              <div className="product-dish-quantity"><span>PREP</span><strong>{dish.prep}</strong><small>{dish.delta === null ? 'PREP NOT RECORDED' : `${dish.delta > 0 ? '+' : ''}${dish.delta} VS LAST RECORDED PREP`}</small></div>
              <div className="product-dish-detail"><span>DEMAND FORECAST</span><strong>{dish.forecast}</strong><small>{dish.confidence_low}–{dish.confidence_high} likely range</small></div>
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
          <p className="product-footnote">{plan?.backtest.available === false ? 'Add prepared quantities or log actuals to compare waste. Sales alone cannot prove historical savings.' : 'Only dishes with at least 14 earlier sales records and known prep are tested. Historical stockouts may hide demand; missed plates count only observed sales.'}</p>
        </section>
        <section className="product-section" aria-labelledby="recent-title"><div className="product-section-head"><div><span className="product-kicker">RECENT ACTUALS</span><h2 id="recent-title">Services</h2></div></div><div className="product-history-list">{plan?.trend.slice().reverse().map(day => <div key={day.day}><strong>{longDate(day.day)}</strong><span>{day.prepared == null ? 'Prep not recorded' : `${day.prepared} portions prepared`}</span><span>{day.waste == null ? 'Waste not recorded' : `${money(day.waste)} ingredient waste`}</span></div>)}</div></section>
      </>}

      {view === 'costs' && <>
        <div className="product-page-head"><div><span className="product-kicker">SET UP YOUR MENU</span><h1>Menu costs</h1><p>Enter the ingredient cost and sale price per portion. These numbers shape every prep recommendation.</p></div></div>
        <section className="product-section" aria-labelledby="costs-title"><div className="product-section-head"><div><span className="product-kicker">{plan?.dishes.length ?? '—'} {plan?.dishes.length === 1 ? 'DISH' : 'DISHES'}</span><h2 id="costs-title">Cost per portion</h2></div></div><div className="product-cost-list">{plan?.dishes.map(dish => <article key={dish.id} className="product-cost-row"><div><h3>{dish.name}</h3><span>{dish.category}</span></div><label>INGREDIENT COST ($)<input type="number" min="0.01" step="0.01" value={costs[dish.id]?.ingredient_cost ?? ''} onChange={event => setCosts(current => ({ ...current, [dish.id]: { ...current[dish.id], ingredient_cost: event.target.value } }))} /></label><label>SALE PRICE ($)<input type="number" min="0.01" step="0.01" value={costs[dish.id]?.price ?? ''} onChange={event => setCosts(current => ({ ...current, [dish.id]: { ...current[dish.id], price: event.target.value } }))} /></label><button className="product-secondary" disabled={savingId === dish.id} onClick={() => void saveCosts(dish)}>{savingId === dish.id ? 'SAVING…' : 'SAVE'}</button></article>)}</div><p className="product-footnote">Use your per-portion costs and sale prices. Saving a change recalculates the plan.</p></section>
      </>}

      {view === 'import' && <>
        <div className="product-page-head"><div><span className="product-kicker">BRING YOUR OWN HISTORY</span><h1>Import sales</h1><p>Upload one CSV row per dish and service. YLD will learn from your sales and produce tomorrow’s prep list.</p></div></div>
        <section className="product-section" aria-labelledby="import-title"><div className="product-section-head"><div><span className="product-kicker">STEP 01 / CHECK THE FILE</span><h2 id="import-title">Your service CSV</h2></div></div>
          <div className="product-import-body">
            <p>Required columns: <code>date,dish,sold,covers</code>. Optional: <code>prepared,ingredient_cost,price,category</code>. Dates use YYYY-MM-DD. Add per-portion costs below if they are not in your sales file.</p>
            <div className="product-import-actions"><a className="product-secondary" href={`data:text/csv;charset=utf-8,${encodeURIComponent(csvTemplate)}`} download="yld-service-history-template.csv">DOWNLOAD BLANK TEMPLATE ↓</a>{hasData && <a className="product-secondary" href="/api/export/history" download="yld-service-history.csv">DOWNLOAD CURRENT DATA ↓</a>}<label className="product-file-label">CHOOSE CSV FILE<input type="file" accept=".csv,text/csv" onChange={event => { const file = event.target.files?.[0]; if (file) void previewCsv(file) }} /></label></div>
            {importBusy && <p role="status">Checking your file…</p>}
            {importPreview && <div className="product-import-preview">
              <span className="product-kicker">READY TO IMPORT · {importFileName}</span>
              <strong>{importPreview.services} {importPreview.services === 1 ? 'service' : 'services'} · {importPreview.dishes} {importPreview.dishes === 1 ? 'dish' : 'dishes'}</strong>
              <p>{importPreview.first_day} to {importPreview.last_day}. {importPreview.prepared_rows === 0 ? 'No prepared quantities: YLD can forecast demand, but cannot compare actual waste yet.' : `${importPreview.prepared_rows} of ${importPreview.rows} rows include prepared quantities for waste comparisons.`}</p>
              {importPreview.services < 14 && <p role="note">With fewer than 14 services, enter your expected covers for tomorrow after import. Covers become automatic as more services are recorded.</p>}
              <div className="product-import-costs"><h3>Cost per dish</h3><p>These figures let YLD balance leftover ingredients against missed sales. You can change them later.</p>
                {importPreview.dish_costs.map(dish => <div className="product-import-cost-row" key={dish.id}>
                  <strong>{dish.name}</strong>
                  <label>INGREDIENT COST ($)<input type="number" min="0.01" step="0.01" value={importCosts[dish.id]?.ingredient_cost ?? ''} onChange={event => setImportCosts(current => ({ ...current, [dish.id]: { ...current[dish.id], ingredient_cost: event.target.value } }))} /></label>
                  <label>SALE PRICE ($)<input type="number" min="0.01" step="0.01" value={importCosts[dish.id]?.price ?? ''} onChange={event => setImportCosts(current => ({ ...current, [dish.id]: { ...current[dish.id], price: event.target.value } }))} /></label>
                </div>)}
              </div>
              {user.role === 'owner' ? <button className="product-primary" type="button" disabled={importBusy} onClick={() => void importCsv()}>{hasData ? 'REPLACE CURRENT DATA' : 'IMPORT DATA & BUILD PLAN'} <span>→</span></button> : <p>Only the workspace owner can finish an import.</p>}
            </div>}
          </div><p className="product-footnote">{hasData ? 'Import replaces this workspace’s existing dishes and history. Download current data before replacing it.' : 'Upload your service history to create the first plan for this kitchen.'} Keep your original CSV as a backup.</p>
        </section>
      </>}
    </main>

    <LegalFooter />
    {actualDish && <div className="product-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setActualDish(null) }}><form className="product-dialog" role="dialog" aria-modal="true" aria-labelledby="actual-title" onSubmit={event => void saveActual(event)}><button type="button" className="product-close" aria-label="Close" onClick={() => setActualDish(null)}>×</button><span className="product-kicker">AFTER SERVICE</span><h2 id="actual-title">Log {actualDish.name}</h2><p>Record what happened. Leftovers feed tomorrow's forecast.</p><label>SERVICE DATE<input required type="date" max={localDate()} value={actualDay} onChange={event => setActualDay(event.target.value)} /></label><label>ACTUAL COVERS<input required type="number" min="1" max="1000" value={actualCovers} onChange={event => setActualCovers(event.target.value)} /></label><div className="product-dialog-pair"><label>PREPARED<input required type="number" min="0" step="1" value={prepared} onChange={event => setPrepared(event.target.value)} /></label><label>SOLD<input required type="number" min="0" step="1" max={prepared || undefined} value={sold} onChange={event => setSold(event.target.value)} /></label></div><div className="product-leftover"><span>LEFTOVER</span><strong>{prepared !== '' && sold !== '' ? Math.max(0, Number(prepared) - Number(sold)) : '—'}</strong></div>{error && <div className="product-message product-error" role="alert">{error}</div>}<button className="product-primary" disabled={savingId === actualDish.id}>{savingId === actualDish.id ? 'SAVING…' : 'SAVE ACTUALS'} <span>→</span></button></form></div>}
  </div>
}
