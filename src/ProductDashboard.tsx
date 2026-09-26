import { DragEvent, FormEvent, useEffect, useRef, useState } from 'react'
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

type View = 'dashboard' | 'history' | 'costs'
type CostDraft = { ingredient_cost: string; price: string }
type DishServices = { name: string; services: number }
type ImportPreview = { dishes: number; services: number; rows: number; prepared_rows: number; dish_names: string[]; dish_costs: { id: string; name: string; ingredient_cost: number | null; price: number | null }[]; dish_services: DishServices[]; eligible_dishes: number; first_day: string; last_day: string }
type ImportField = 'date' | 'dish' | 'sold' | 'covers' | 'prepared' | 'ingredient_cost' | 'price' | 'category'
type ImportMapping = { sheet: string; header_row: number; layout: 'long' | 'wide'; date_format: 'auto' | 'dmy' | 'mdy'; aggregation: 'none' | 'sum'; columns: Record<ImportField, string>; dish_columns: string[] }
type ImportHeaderOption = { header_row: number; headers: string[]; sample: Record<string, string>[] }
type ImportSource = { filename: string; content_base64: string; signature: string; mapping_source: 'saved' | 'agent' | 'rules'; sheets: (ImportHeaderOption & { name: string; rows: number; header_options: ImportHeaderOption[] })[] }
type MenuItem = { name: string; ingredient_cost: string; price: string; category: string }
type ModelMetrics = { promoted_dishes: number; tested_dishes: number; selection?: { algorithm: 'ridge_weekday_v1' | 'ridge_decay_v1'; window: number; penalty: number; reason: string }; results?: { dish_id: string; services_tested: number; baseline_mae: number; candidate_mae: number; passed: boolean }[] }
type ModelStage = 'queued' | 'analyzing' | 'training' | 'validating' | 'promoting' | 'complete'
type ModelJob = { id: string; status: string; stage: ModelStage; created_at: number; reason: string | null; metrics: ModelMetrics | null }
type ModelStatus = { enabled: boolean; eligible_dishes: number; max_services: number; required_services: number; dish_services: DishServices[]; job: ModelJob | null; active: { id: string; created_at: number; metrics: ModelMetrics } | null }
type ServiceSummary = { day: string; covers: number | null; total_dishes: number; logged_dishes: number; complete: boolean; prepared: number; sold: number; leftovers: number; ingredient_waste: number; dishes: { id: string; name: string; prepared: number; sold: number; leftover: number }[] }
type UploadPhase = 'reading' | 'sales' | 'menu' | 'checking' | 'saving' | null
type ImportResult = { rows: number; dishes: number; services: number; training: { status: string; job_id?: string; required_services?: number } }

const modelSteps: { stage: ModelStage; label: string }[] = [
  { stage: 'queued', label: 'Queued' }, { stage: 'analyzing', label: 'Agent analysis' },
  { stage: 'training', label: 'Training' }, { stage: 'validating', label: 'Validation' },
  { stage: 'promoting', label: 'Activating' },
]
const uploadSteps: { phase: Exclude<UploadPhase, null>; label: string }[] = [
  { phase: 'reading', label: 'Reading files' }, { phase: 'sales', label: 'Mapping sales' },
  { phase: 'menu', label: 'Mapping menu' }, { phase: 'checking', label: 'Checking matches' },
  { phase: 'saving', label: 'Saving data' },
]

function PipelineProgress({ title, steps, active, complete = false, paused = false, detail }: { title: string; steps: string[]; active: number; complete?: boolean; paused?: boolean; detail: string }) {
  const completed = complete ? steps.length : Math.max(0, active)
  return <div className={`product-pipeline${paused ? ' is-paused' : ''}`} role="status" aria-live="polite">
    <div className="product-pipeline-head"><span className="product-kicker">{title}</span><strong>{complete ? 'COMPLETE' : `${Math.min(active + 1, steps.length)} / ${steps.length}`}</strong></div>
    <div className="product-pipeline-track" role="progressbar" aria-label={title} aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={completed} aria-valuetext={complete ? 'Complete' : steps[active] ?? 'Waiting'}><span style={{ width: `${completed / steps.length * 100}%` }} /></div>
    <p>{detail}</p>
    <ol>{steps.map((step, index) => <li key={step} className={complete || index < active ? 'is-done' : index === active ? 'is-active' : ''}><span>{complete || index < active ? '✓' : String(index + 1).padStart(2, '0')}</span>{step}</li>)}</ol>
  </div>
}

function ModelTrainingProgress({ job, statusUnavailable = false }: { job: ModelJob; statusUnavailable?: boolean }) {
  if (job.status === 'failed' || job.status === 'rejected') {
    return <div className="product-pipeline product-pipeline-outcome" role="status"><span className="product-kicker">MODEL RUN {job.status.toUpperCase()} · {modelSteps.find(step => step.stage === job.stage)?.label ?? 'Queued'}</span><h3>{job.status === 'rejected' ? 'The standard forecast stays active.' : 'Training could not finish.'}</h3><p>{job.reason || 'Check the model worker before trying again.'}</p></div>
  }
  const complete = job.status === 'promoted'
  const active = complete ? modelSteps.length - 1 : Math.max(0, modelSteps.findIndex(step => step.stage === job.stage))
  const detail = statusUnavailable && !complete
    ? 'Live status is temporarily unavailable. Reconnecting to the model worker status…'
    : complete
    ? 'The selected dish forecasts are now active.'
    : job.stage === 'queued' && Date.now() / 1000 - job.created_at > 600
      ? 'Still queued after ten minutes. The model worker may need attention.'
      : ({ queued: 'Waiting for the model worker to start.', analyzing: 'The agent is comparing forecast methods.', training: 'Fitting models to the service history.', validating: 'Testing models against held-out services.', promoting: 'Activating models that beat the standard forecast.', complete: 'Complete.' } as Record<ModelStage, string>)[job.stage]
  const progress = <PipelineProgress title="MODEL TRAINING" steps={modelSteps.map(step => step.label)} active={active} complete={complete} paused={statusUnavailable} detail={detail} />
  if (!complete) return progress
  const metrics = job.metrics
  const method = metrics?.selection?.algorithm === 'ridge_decay_v1' ? 'Recency-weighted weekday ridge regression' : metrics?.selection?.algorithm === 'ridge_weekday_v1' ? 'Weekday ridge regression' : 'Method details unavailable'
  return <div className="product-model-run">{progress}<div className="product-model-summary">
    <span className="product-kicker">RUN SUMMARY</span>
    <p>The agent selected a supported forecasting setup. The trainer fitted dish models, then tested each against 14 held-out services.</p>
    <div className="product-model-summary-grid"><div><span>MODEL USED</span><strong>{method}</strong></div><div><span>MODEL SETTINGS</span><strong>{metrics?.selection ? `${metrics.selection.window} services · penalty ${metrics.selection.penalty}` : '—'}</strong></div><div><span>ACTIVATED</span><strong>{metrics ? `${metrics.promoted_dishes} of ${metrics.tested_dishes} dishes` : '—'}</strong></div></div>
    {metrics?.selection?.reason && <p className="product-model-reason">Selection note: {metrics.selection.reason}</p>}
    <small>Only dish forecasts that beat the standard forecast on held-out sales were activated. This test does not establish waste savings.</small>
  </div></div>
}

function UploadDropZone({ title, hint, file, disabled, inputVersion, onFile, onError }: { title: string; hint: string; file: File | null; disabled: boolean; inputVersion: number; onFile: (file: File) => void; onError: (message: string) => void }) {
  const [dragging, setDragging] = useState(false)

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    const files = event.dataTransfer.files
    if (files.length === 1) onFile(files[0])
    else onError('Drop one spreadsheet into each area.')
  }

  return <label className={`product-file-dropzone${dragging ? ' is-dragging' : ''}${disabled ? ' is-disabled' : ''}`}
    onDragEnter={event => { event.preventDefault(); if (!disabled) setDragging(true) }}
    onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? 'none' : 'copy' }}
    onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false) }}
    onDrop={handleDrop}>
    <strong>{title}</strong>
    <span>{file ? file.name : 'Drop a CSV or XLSX here, or click to browse'}</span>
    <small>{file ? 'Ready to map · click or drop to replace' : hint}</small>
    <input key={inputVersion} type="file" accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={disabled} onChange={event => { const selected = event.target.files?.[0]; if (selected) onFile(selected) }} />
  </label>
}

const money = (value: number) => '$' + value.toLocaleString('en-NZ', { maximumFractionDigits: 0 })
const unitMoney = (value: number) => '$' + value.toFixed(2)
function PrepPlanOverview({ plan, loading, detailsOpen, onOpenPlan }: { plan: Plan | null; loading: boolean; detailsOpen: boolean; onOpenPlan: () => void }) {
  const dishes = [...(plan?.dishes ?? [])].sort((a, b) => b.prep - a.prep)
  const scale = Math.max(1, ...dishes.map(dish => dish.prep))
  const wasteChange = plan && plan.summary.usual_waste !== null && plan.summary.usual_waste > 0
    ? Math.round((plan.summary.usual_waste - plan.summary.expected_waste) / plan.summary.usual_waste * 100)
    : null

  return <div className="product-prep-overview">
    {!plan && <div className="product-prep-summary"><h1>{loading ? 'Building your prep list…' : 'Set expected covers to build your plan.'}</h1><p>Your sales and menu costs will become a dish-by-dish prep list.</p></div>}
    {plan && <>
      <div className="product-prep-chart-head"><h1>What to make</h1><span><i aria-hidden="true" /> PORTIONS</span></div>
      <div className="product-prep-chart" role="img" aria-label={`Recommended portions to prepare: ${dishes.map(dish => `${dish.name}, ${dish.prep}`).join('; ')}`}>
        {dishes.map(dish => <div className="product-prep-chart-row" key={dish.id} aria-hidden="true"><span>{dish.name}</span><div className="product-prep-chart-track"><div style={{ width: `${dish.prep / scale * 100}%` }} /></div><strong>{dish.prep}</strong></div>)}
      </div>
      <section className={`product-impact product-prep-impact${wasteChange !== null && wasteChange < 0 ? ' is-higher' : ''}`} aria-labelledby="prep-impact-title">
        <div className="product-impact-main">
          <h2 id="prep-impact-title">Projected prep impact</h2>
          <div className="product-impact-headline"><strong>{money(plan.summary.expected_waste)}</strong><span>expected ingredient waste</span></div>
          <p>{plan.summary.usual_waste === null ? 'Record prepared quantities to establish your usual daily waste.' : `vs ${money(plan.summary.usual_waste)} usual daily waste`}</p>
        </div>
        <div className="product-impact-change"><strong>{wasteChange === null ? '—' : `${wasteChange > 0 ? '−' : wasteChange < 0 ? '+' : ''}${Math.abs(wasteChange)}%`}</strong><span>WASTE VS USUAL</span></div>
      </section>
      <div className="product-prep-action"><button className="product-primary" type="button" onClick={onOpenPlan}>{detailsOpen ? 'HIDE FULL PLAN' : 'VIEW FULL PLAN'} <span>{detailsOpen ? '↑' : '→'}</span></button></div>
    </>}
    {!plan && !loading && <div className="product-prep-action"><button className="product-primary" type="button" onClick={onOpenPlan}>SET EXPECTED COVERS <span>→</span></button></div>}
  </div>
}
const localDate = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
const longDate = (value: string) => new Date(value + 'T12:00:00').toLocaleDateString('en-NZ', { weekday: 'long', day: 'numeric', month: 'long' })
export default function ProductDashboard({ user, onSignOut, onAuthLost }: { user: SessionUser; onSignOut: () => void; onAuthLost: () => void }) {
  const [view, setView] = useState<View>('dashboard')
  const [showPlanDetails, setShowPlanDetails] = useState(false)
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
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [importSource, setImportSource] = useState<ImportSource | null>(null)
  const [importMapping, setImportMapping] = useState<ImportMapping | null>(null)
  const [importBusy, setImportBusy] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [salesFile, setSalesFile] = useState<File | null>(null)
  const [menuFile, setMenuFile] = useState<File | null>(null)
  const [fileInputVersion, setFileInputVersion] = useState(0)
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])
  const [useAgentMapping, setUseAgentMapping] = useState(false)
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null)
  const [modelStatusUnavailable, setModelStatusUnavailable] = useState(false)
  const seenModelId = useRef<string | null | undefined>(undefined)

  async function loadModelStatus() {
    try {
      const response = await fetch('/api/models/status')
      if (response.status === 401) { onAuthLost(); return }
      if (!response.ok) { setModelStatusUnavailable(true); return }
      const status: ModelStatus = await response.json()
      setModelStatusUnavailable(false)
      setModelStatus(status)
      const activeId = status.active?.id ?? null
      if (hasData && seenModelId.current !== undefined && seenModelId.current !== activeId) void loadPlan()
      seenModelId.current = activeId
    } catch {
      setModelStatusUnavailable(true)
    }
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
          setView('dashboard')
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

  async function encodeFile(file: File) {
    if (file.size > 4_000_000) throw new Error(`${file.name} must be smaller than 4 MB.`)
    const bytes = new Uint8Array(await file.arrayBuffer())
    let binary = ''
    for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768))
    return { filename: file.name, content_base64: btoa(binary) }
  }

  async function postImport<T>(path: string, payload: object, csrf = false): Promise<T> {
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': user.csrf_token } : {}) }, body: JSON.stringify(payload) })
    if (response.status === 401) { onAuthLost(); throw new Error('Session expired. Sign in again to upload.') }
    const body = await response.json()
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Could not process this spreadsheet.')
    return body as T
  }

  function resetImportDraft() {
    setSalesFile(null)
    setMenuFile(null)
    setFileInputVersion(version => version + 1)
    setMenuItems([])
    setUseAgentMapping(false)
    setImportText('')
    setImportPreview(null)
    setImportSource(null)
    setImportMapping(null)
    setImportResult(null)
    setUploadPhase(null)
    setError('')
  }

  function selectImportFile(kind: 'menu' | 'sales', file: File) {
    if (!/\.(csv|xlsx)$/i.test(file.name)) { setError('Choose a CSV or XLSX spreadsheet.'); return }
    if (file.size > 4_000_000) { setError(`${file.name} must be smaller than 4 MB.`); return }
    if (kind === 'menu') setMenuFile(file)
    else setSalesFile(file)
    setFileInputVersion(version => version + 1)
    setMenuItems([])
    setImportText('')
    setImportPreview(null)
    setImportSource(null)
    setImportMapping(null)
    setError('')
  }

  async function importCsv(preview = importPreview, csvText = importText, source = importSource, mapping = importMapping) {
    if (!preview) return
    const menu_costs: Record<string, { ingredient_cost: number; price: number }> = {}
    const unmatched: string[] = []
    for (const dish of preview.dish_costs) {
      const menuItem = menuItems.find(item => item.name.trim().toLocaleLowerCase() === dish.name.trim().toLocaleLowerCase())
      if (menuItem) menu_costs[dish.id] = { ingredient_cost: Number(menuItem.ingredient_cost), price: Number(menuItem.price) }
      else unmatched.push(dish.name)
    }
    if (unmatched.length) { setError(`No menu cost was found for: ${unmatched.join(', ')}.`); return }
    setImportBusy(true)
    setUploadPhase('saving')
    setError('')
    try {
      const body = await postImport<ImportResult>('/api/import/commit', { csv_text: csvText, menu_costs, train: true, source_mapping: mapping, source_signature: source?.signature }, true)
      setImportResult(body)
      setHasData(true)
      setNotice(body.training?.status === 'queued'
        ? `${body.rows} sales records loaded. Model training has been queued.`
        : `${body.rows} sales records loaded. Your prep plan is ready.`)
      setImportPreview(null)
      setImportSource(null)
      setImportMapping(null)
      setImportText('')
      setView('dashboard')
      setShowPlanDetails(false)
      void loadPlan()
      void loadModelStatus()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not import this CSV.')
    } finally {
      setImportBusy(false)
      setUploadPhase(null)
    }
  }

  async function prepareImport() {
    if (!salesFile || !menuFile) { setError('Choose both a sales report and a menu-cost spreadsheet.'); return }
    setImportBusy(true)
    setError('')
    setImportPreview(null)
    setImportSource(null)
    setImportMapping(null)
    setMenuItems([])
    try {
      setUploadPhase('reading')
      const [sales, menu] = await Promise.all([encodeFile(salesFile), encodeFile(menuFile)])
      setUploadPhase('sales')
      const inspectedSales = await postImport<{ signature: string; mapping_source: ImportSource['mapping_source']; sheets: ImportSource['sheets']; mapping: ImportMapping }>('/api/import/inspect', { ...sales, use_agent: useAgentMapping }, true)
      const normalizedSales = await postImport<{ csv_text: string; preview: ImportPreview }>('/api/import/normalize', { ...sales, mapping: inspectedSales.mapping })
      setUploadPhase('menu')
      const inspectedMenu = await postImport<{ mapping: object }>('/api/import/menu/inspect', menu, true)
      const normalizedMenu = await postImport<{ menu: MenuItem[] }>('/api/import/menu/normalize', { ...menu, mapping: inspectedMenu.mapping })
      setUploadPhase('checking')
      const menuNames = new Set(normalizedMenu.menu.map(item => item.name.trim().toLocaleLowerCase()))
      const unmatched = normalizedSales.preview.dish_costs.filter(dish => !menuNames.has(dish.name.trim().toLocaleLowerCase()))
      if (unmatched.length) throw new Error(`No menu cost was found for: ${unmatched.slice(0, 5).map(dish => dish.name).join(', ')}${unmatched.length > 5 ? ` and ${unmatched.length - 5} more` : ''}.`)
      setImportSource({ ...sales, signature: inspectedSales.signature, mapping_source: inspectedSales.mapping_source, sheets: inspectedSales.sheets })
      setImportMapping(inspectedSales.mapping)
      setImportText(normalizedSales.csv_text)
      setImportPreview(normalizedSales.preview)
      setMenuItems(normalizedMenu.menu)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not prepare these spreadsheets.')
    } finally {
      setImportBusy(false)
      setUploadPhase(null)
    }
  }

  const queuedJobId = importResult?.training.job_id
  const visibleJob = importResult && !queuedJobId ? null : queuedJobId && modelStatus?.job?.id !== queuedJobId
    ? { id: queuedJobId, status: 'queued', stage: 'queued' as ModelStage, created_at: Date.now() / 1000, reason: null, metrics: null }
    : modelStatus?.job

  const fullPlanDetails = <div className="product-plan-details" id="full-plan">
    <div className="product-plan-details-head"><div><span className="product-kicker">{plan ? longDate(plan.date) : 'Tomorrow'}</span><h2>Full prep plan</h2></div><button className="product-secondary" type="button" onClick={() => setShowPlanDetails(false)}>HIDE DETAILS</button></div>
    {plan && !showCoverOverride && <div className="product-cover-bar">
      <div><span className="product-kicker">{plan.cover_source === 'forecast' ? `AUTOMATIC FORECAST · ${plan.cover_history_days} SERVICES` : 'MANUAL ESTIMATE'}</span><strong>{plan.covers} covers</strong><p>{plan.cover_source === 'forecast' ? 'Estimated from your service history. It updates as actuals are logged.' : plan.forecast_covers === null ? `${plan.cover_history_days} of 14 services recorded. We’ll estimate covers automatically once there’s enough history.` : `Adjusted from the ${plan.forecast_covers}-cover forecast.`}</p></div>
      <div className="product-cover-actions"><button className="product-secondary" onClick={() => { setCovers(String(plan.covers)); setShowCoverOverride(true) }}>ADJUST COVERS</button>{plan.cover_source === 'manual' && plan.forecast_covers !== null && <button className="product-secondary" disabled={loading} onClick={() => void loadPlan()}>USE FORECAST</button>}<button className="product-secondary" onClick={() => setView('history')}>VIEW HISTORY</button></div>
    </div>}
    {!plan && loading && <div className="product-cover-bar"><span className="product-kicker">CALCULATING TOMORROW’S PLAN…</span></div>}
    {(needsCovers || showCoverOverride || (!plan && !loading && !error)) && <form className="product-controls" onSubmit={event => { event.preventDefault(); setNotice(''); void loadPlan(Number(covers)) }}>
      {needsCovers && <p className="product-cover-help">Add an estimate for tomorrow. After 14 recorded services, YLD will forecast covers automatically. ({coverHistoryDays}/14 recorded)</p>}
      <label>EXPECTED COVERS<input type="number" min="1" max="1000" required value={covers} onChange={event => setCovers(event.target.value)} /></label>
      <button className="product-primary" disabled={loading || !covers || Number(covers) < 1 || Number(covers) > 1000}>{loading ? 'CALCULATING…' : 'UPDATE PLAN'} <span>→</span></button>
      {showCoverOverride && <button type="button" className="product-secondary" onClick={() => setShowCoverOverride(false)}>CANCEL</button>}
    </form>}
    {!!plan?.insights.length && <section className="product-section" aria-labelledby="insights-title">
      <div className="product-section-head"><div><span className="product-kicker">FROM YOUR SERVICE DATA</span><h2 id="insights-title">Prep insights</h2></div></div>
      <div className="product-insights">{plan.insights.map(insight => <article key={insight.title}><h3>{insight.title}</h3><p>{insight.detail}</p></article>)}</div>
    </section>}
    {plan && <section className="product-section" aria-labelledby="dish-plan-title">
      <div className="product-section-head"><div><span className="product-kicker">THE RECOMMENDATION</span><h2 id="dish-plan-title">Dish by dish</h2></div><span>{plan.dishes.length} {plan.dishes.length === 1 ? 'DISH' : 'DISHES'}</span></div>
      <div className="product-dish-list">
        {plan.dishes.map(dish => <article className="product-dish" key={dish.id}>
          <div className="product-dish-name"><h3>{dish.name}</h3><span>{dish.category} · {unitMoney(dish.ingredient_cost)} INGREDIENT COST</span></div>
          <div className="product-dish-quantity"><span>PREP</span><strong>{dish.prep}</strong><small>{dish.delta === null ? 'PREP NOT RECORDED' : `${dish.delta > 0 ? '+' : ''}${dish.delta} VS LAST RECORDED PREP`}</small></div>
          <div className="product-dish-detail"><span>{dish.forecast_source === 'trained' ? 'YLD AGENT FORECAST' : 'STANDARD FORECAST'}</span><strong>{dish.forecast}</strong><small>{dish.confidence_low}–{dish.confidence_high} likely range</small></div>
          <div className="product-dish-detail"><span>EXPECTED LEFTOVER</span><strong>{dish.expected_leftover}</strong><small>{unitMoney(dish.expected_leftover * dish.ingredient_cost)} of ingredients</small></div>
          <button className="product-row-action" onClick={() => openActual(dish)}>LOG ACTUAL <span>→</span></button>
        </article>)}
      </div>
      <p className="product-footnote">Why these numbers? The demand model learns from earlier services. The planner weighs the ingredient cost of leftovers against the margin lost when a dish sells out.</p>
    </section>}
  </div>

  return <div className="product-shell">
    <header className="product-header">
      <button className="product-brand" onClick={() => setView('dashboard')} aria-label="YLD Agent">YLD<span>.</span></button>
      <nav className="product-nav" aria-label="Planner navigation">
        <button className={view === 'dashboard' ? 'active' : ''} aria-current={view === 'dashboard' ? 'page' : undefined} onClick={() => { setView('dashboard'); setError(''); setNotice('') }}>YLD AGENT</button>
      </nav>
      <button className="product-signout" onClick={onSignOut}>SIGN OUT ↗</button>
    </header>

    <main className="product-main">
      {error && !actualDish && !showImportModal && <div className="product-message product-error" role="alert">{error}</div>}
      {notice && <div className="product-message" role="status">{notice}</div>}
      {hasData && visibleJob && visibleJob.status !== 'promoted' && view !== 'dashboard' && !showImportModal && <ModelTrainingProgress job={visibleJob} statusUnavailable={modelStatusUnavailable} />}

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

      {view === 'dashboard' && <>
        {!hasData && <div className="product-page-head"><div><span className="product-kicker">YOUR DATA · YOUR DECISIONS</span><h1>YLD Agent.</h1></div></div>}
        <section className="product-agent-workspace" aria-label="YLD Agent workflow">
          <div className="product-agent-upload">{hasData && visibleJob ? <div className="product-import-body product-import-model-body">
            <ModelTrainingProgress job={visibleJob} statusUnavailable={modelStatusUnavailable} />
            <button className="product-secondary" type="button" onClick={() => { resetImportDraft(); setNotice(''); setShowImportModal(true) }}>UPDATE DATA</button>
          </div> : <><div className="product-section-head"><div><span className="product-kicker">YOUR KITCHEN DATA</span><h2>{hasData ? 'Update your data' : 'Add your kitchen data'}</h2></div></div>
            <div className="product-import-body">
              <p>Upload your menu costs and sales history. YLD builds the prep plan from both.</p>
              <div className="product-import-actions"><button className="product-primary" type="button" onClick={() => { resetImportDraft(); setNotice(''); setShowImportModal(true) }}>{hasData ? 'UPDATE FILES' : 'ADD SPREADSHEETS'} <span>→</span></button></div>
            </div>
          </>}</div>
        </section>
        {hasData && <section className="product-analytics" aria-label="Tomorrow’s prep plan">
          <PrepPlanOverview plan={plan} loading={loading} detailsOpen={showPlanDetails} onOpenPlan={() => setShowPlanDetails(open => !open)} />
        </section>}
        {hasData && showPlanDetails && fullPlanDetails}
      </>}
    </main>

    <LegalFooter />
    {showImportModal && <div className="product-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !importBusy) setShowImportModal(false) }}>
      <section className="product-dialog product-import-modal" role="dialog" aria-modal="true" aria-labelledby="import-modal-title">
        <button type="button" className="product-close" aria-label="Close import" disabled={importBusy} onClick={() => setShowImportModal(false)}>×</button>
        <span className="product-kicker">YLD DATA LOAD</span>
        <h2 id="import-modal-title">{importResult ? <>Data<br/>loaded.</> : <>Add your<br/>spreadsheets.</>}</h2>
        {importResult ? <>
          <p>{importResult.rows} sales rows across {importResult.services} services and {importResult.dishes} dishes are in your prep plan.</p>
          {importResult.training.status === 'queued' && visibleJob && <ModelTrainingProgress job={visibleJob} statusUnavailable={modelStatusUnavailable} />}
          {importResult.training.status === 'queued' && visibleJob && ['queued', 'running'].includes(visibleJob.status) && <p className="product-import-duration">The agent and trainer each have a ten minute limit. You can close this window; live progress remains on the dashboard.</p>}
          {importResult.training.status === 'not_ready' && <p className="product-import-note">The standard forecast is ready. Training needs {importResult.training.required_services} recorded services for at least one dish.</p>}
          {importResult.training.status === 'not_configured' && <p className="product-import-note">The standard forecast is ready. Model training is not enabled on this deployment.</p>}
          <div className="product-import-result-actions"><button className="product-secondary" type="button" onClick={resetImportDraft}>RESET UPLOAD</button><button className="product-primary" type="button" onClick={() => setShowImportModal(false)}>VIEW PREP PLAN <span>→</span></button></div>
          <small>Reset clears this upload form. Your saved data and model run stay in place.</small>
        </> : <>
          <p>Load both files together. YLD maps their columns, matches menu costs to sales, and queues model training when the history qualifies.</p>
          <UploadDropZone title="MENU ITEMS & COSTS" hint="Item, ingredient cost, sale price · 4 MB max" file={menuFile} disabled={importBusy} inputVersion={fileInputVersion} onFile={file => selectImportFile('menu', file)} onError={setError} />
          <UploadDropZone title="SALES REPORT" hint="Date, dish, sold, covers · 4 MB max" file={salesFile} disabled={importBusy} inputVersion={fileInputVersion} onFile={file => selectImportFile('sales', file)} onError={setError} />
          <label className="product-import-agent-choice"><input type="checkbox" checked={useAgentMapping} disabled={importBusy} onChange={event => { setUseAgentMapping(event.target.checked); setImportPreview(null) }} /><span>Let YLD Agent suggest the sales column mapping. Sheet names, headers, and up to three sample rows per sheet are sent to OpenAI. Leave this off to use local header rules.</span></label>
          {uploadPhase && <PipelineProgress title="PREPARING SPREADSHEETS" steps={uploadSteps.map(step => step.label)} active={uploadSteps.findIndex(step => step.phase === uploadPhase)} detail={uploadPhase === 'saving' ? 'Saving your data and queuing eligible model training.' : 'Reading and checking your files. Nothing has been replaced yet.'} />}
          {importPreview && menuItems.length > 0 && <div className="product-import-preview"><span className="product-kicker">READY TO LOAD</span><strong>{importPreview.services} services · {importPreview.dishes} dishes</strong><p>{importPreview.dishes} sales dishes match menu costs. {importPreview.eligible_dishes ? `${importPreview.eligible_dishes} ${importPreview.eligible_dishes === 1 ? 'dish has' : 'dishes have'} enough history for training.` : `Training needs ${modelStatus?.required_services ?? 56} services for at least one dish.`}</p><p>Loading these files replaces your current menu and service history.</p></div>}
          {error && <div className="product-message product-error" role="alert">{error}</div>}
          <div className="product-import-modal-actions"><button className="product-secondary" type="button" disabled={importBusy} onClick={() => setShowImportModal(false)}>CANCEL</button><button className="product-secondary" type="button" disabled={importBusy} onClick={resetImportDraft}>RESET FILES</button>{importPreview && menuItems.length > 0 ? <button className="product-primary" type="button" disabled={importBusy} onClick={() => void importCsv()}>{importPreview.eligible_dishes && modelStatus?.enabled ? 'LOAD & QUEUE TRAINING' : 'LOAD DATA'} <span>→</span></button> : <button className="product-primary" type="button" disabled={importBusy || !salesFile || !menuFile} onClick={() => void prepareImport()}>MAP FILES <span>→</span></button>}</div>
        </>}
      </section>
    </div>}
    {actualDish && <div className="product-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setActualDish(null) }}><form className="product-dialog" role="dialog" aria-modal="true" aria-labelledby="actual-title" onSubmit={event => void saveActual(event)}><button type="button" className="product-close" aria-label="Close" onClick={() => setActualDish(null)}>×</button><span className="product-kicker">AFTER SERVICE</span><h2 id="actual-title">Log {actualDish.name}</h2><p>Record what happened. Leftovers feed tomorrow's forecast.</p><label>SERVICE DATE<input required type="date" max={localDate()} value={actualDay} onChange={event => setActualDay(event.target.value)} /></label><label>ACTUAL COVERS<input required type="number" min="1" max="1000" value={actualCovers} onChange={event => setActualCovers(event.target.value)} /></label><div className="product-dialog-pair"><label>PREPARED<input required type="number" min="0" step="1" value={prepared} onChange={event => setPrepared(event.target.value)} /></label><label>SOLD<input required type="number" min="0" step="1" max={prepared || undefined} value={sold} onChange={event => setSold(event.target.value)} /></label></div><div className="product-leftover"><span>LEFTOVER</span><strong>{prepared !== '' && sold !== '' ? Math.max(0, Number(prepared) - Number(sold)) : '—'}</strong></div>{error && <div className="product-message product-error" role="alert">{error}</div>}<button className="product-primary" disabled={savingId === actualDish.id}>{savingId === actualDish.id ? 'SAVING…' : 'SAVE ACTUALS'} <span>→</span></button></form></div>}
    {serviceSummary && <div className="product-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setServiceSummary(null) }}><section className="product-dialog product-service-summary" role="dialog" aria-modal="true" aria-labelledby="service-summary-title"><button type="button" className="product-close" aria-label="Close summary" onClick={() => setServiceSummary(null)}>×</button><span className="product-kicker">{serviceSummary.complete ? 'SERVICE SUMMARY' : 'SERVICE IN PROGRESS'}</span><h2 id="service-summary-title">{serviceSummary.complete ? <>Service<br/>logged.</> : <>Actuals<br/>saved.</>}</h2><p>{serviceSummary.complete ? `All ${serviceSummary.total_dishes} dishes are recorded for ${longDate(serviceSummary.day)}. Tomorrow’s forecast will use these actuals.` : `${serviceSummary.logged_dishes} of ${serviceSummary.total_dishes} dishes logged. Keep recording actuals to complete this service.`}</p><div className="product-service-summary-metrics"><div><span>PREPARED</span><strong>{serviceSummary.prepared}</strong></div><div><span>SOLD</span><strong>{serviceSummary.sold}</strong></div><div><span>LEFT OVER</span><strong>{serviceSummary.leftovers}</strong></div><div><span>INGREDIENT VALUE</span><strong>{money(serviceSummary.ingredient_waste)}</strong></div></div><div className="product-service-summary-dishes">{serviceSummary.dishes.map(dish => <div key={dish.id}><span>{dish.name}</span><span>{dish.prepared} prepared · {dish.sold} sold · {dish.leftover} left</span></div>)}</div><button className="product-primary" type="button" onClick={() => setServiceSummary(null)}>{serviceSummary.complete ? 'CLOSE SUMMARY' : 'CONTINUE LOGGING'} <span>→</span></button></section></div>}
  </div>
}
