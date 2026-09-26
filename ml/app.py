from pathlib import Path
from html import escape
import pandas as pd
import streamlit as st
from src.backtest import run_backtest
from src.load_data import load_data, restaurant_labels

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='YLD / Inventory modeller', page_icon=str(ROOT / 'assets/favicon.svg'), layout='wide')
st.markdown(f'<style>{(ROOT / "assets/yld.css").read_text(encoding="utf-8")}</style>', unsafe_allow_html=True)
st.markdown('''<header class="yld-nav"><div class="yld-logo" aria-label="YLD">YLD<span>.</span></div>
<div class="yld-nav-label">INVENTORY MODELLER <span class="yld-dot"></span> HISTORICAL ANALYSIS</div></header>
<section class="yld-hero"><div class="yld-eyebrow"><span>YLD / REDUCE YOUR WASTE</span><span>BUILT FROM EVERY SERVICE</span></div>
<h1>LESS WASTE.<br>BETTER PREP.</h1><p>See what a better prep plan could have saved your kitchen.
Choose a restaurant, set your costs, and replay your service history.</p></section>''', unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="yld-logo">YLD<span>.</span></div><div class="yld-sidebar-title">01 / SET UP YOUR ANALYSIS</div>', unsafe_allow_html=True)
    upload = st.file_uploader('Your restaurant history', type='csv', help='Upload a CSV, or explore the included sample data.')
    source = upload if upload is not None else ROOT / 'data/raw/restaurant_data.csv'
    try:
        data, audit = load_data(source)
    except (ValueError, FileNotFoundError) as exc:
        st.error(str(exc))
        st.stop()
    labels = restaurant_labels(data)
    selected_label = st.selectbox('Restaurant', list(labels))
    restaurant = labels[selected_label]
    st.caption('Sample locations use IDs. Include restaurant_name in your CSV to show venue names.')
    st.markdown('<div class="yld-section">02 / COST ASSUMPTIONS</div>', unsafe_allow_html=True)
    cost = st.number_input('Ingredient cost per kg', min_value=0.01, value=8.5)
    margin = st.number_input('Contribution margin per kg', min_value=0.01, value=14.0, help='The contribution lost when you miss a sale, rather than the selling price.')
    currency = st.text_input('Currency label', value='NZD', help='Labels the amounts; does not convert currencies.')
    st.caption('Adjust these assumptions to explore the balance between food waste and missed sales.')

selected_data = data[data.restaurant_id == restaurant]
signature = (restaurant, cost, margin, str(pd.util.hash_pandas_object(data, index=True).sum()))
start, end = selected_data.date.min().date(), selected_data.date.max().date()
st.markdown(f'<div class="yld-status"><span class="yld-dot"></span> {escape(selected_label)}<br>{start} — {end} · {len(selected_data):,} RECORDED DAYS · {"UPLOADED HISTORY" if upload is not None else "SAMPLE DATA"}</div>', unsafe_allow_html=True)
st.caption('Scenario estimates using observed sales as demand. Historical stockouts may hide unmet demand; costs and margins are assumptions.')
if st.button('Run historical analysis', type='primary'):
    with st.spinner('Replaying your restaurant history…'):
        try:
            st.session_state['analysis'] = (signature, run_backtest(selected_data, cost, margin))
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

if 'analysis' in st.session_state and st.session_state['analysis'][0] == signature:
    results, summary, metadata = st.session_state['analysis'][1]
    ml = summary[summary.policy == 'random_forest'].iloc[0]
    st.markdown('<div class="yld-section">03 / YOUR ESTIMATED IMPACT</div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.metric(f'Estimated net savings ({currency})', f'{ml.net_savings:,.2f}')
    b.metric('Simulated waste avoided (kg)', f'{ml.waste_kg_avoided:,.1f}')
    c.metric('Potential shortage (kg)', f'{ml.potential_shortage_kg:,.1f}')
    st.caption(f'Evaluation: {ml.start} to {ml.end}. Savings include a penalty for shortages. Negative savings are retained.')
    st.markdown('<div class="yld-section">04 / DEMAND & PREPARATION</div>', unsafe_allow_html=True)
    chart = results[results.policy == 'random_forest'].set_index('date')
    st.line_chart(chart[['food_sold_kg', 'forecast_kg', 'recommended_prep_kg']].rename(columns={
        'food_sold_kg': 'Actual sales (kg)', 'forecast_kg': 'Demand forecast (kg)',
        'recommended_prep_kg': 'Recommended prep (kg)'}), color=['#111111', '#91918a', '#ff6538'])
    st.markdown('<div class="yld-section">05 / COMPARE THE APPROACHES</div>', unsafe_allow_html=True)
    comparison = summary[['policy', 'mae_kg', 'rmse_kg', 'net_savings', 'potential_lost_margin', 'waste_reduction_pct']].copy()
    comparison['policy'] = comparison.policy.map({'random_forest': 'YLD · Random Forest', 'rolling_mean': 'Rolling-average baseline'})
    st.dataframe(comparison, hide_index=True, column_config={
        'policy': 'Approach', 'mae_kg': st.column_config.NumberColumn('Average error (kg)', format='%.2f'),
        'rmse_kg': st.column_config.NumberColumn('RMSE (kg)', format='%.2f'),
        'net_savings': st.column_config.NumberColumn(f'Net savings ({currency})', format='%.2f'),
        'potential_lost_margin': st.column_config.NumberColumn('Potential lost margin', format='%.2f'),
        'waste_reduction_pct': st.column_config.NumberColumn('Waste reduction (%)', format='%.1f')})
    st.caption('Compare the model with the rolling-average baseline before adopting its recommendations.')
    left, right = st.columns(2)
    left.download_button('Download detailed backtest ↓', results.to_csv(index=False), 'backtest_results.csv', 'text/csv')
    right.download_button('Download savings summary ↓', summary.to_csv(index=False), 'savings_summary.csv', 'text/csv')
    with st.expander('How this analysis was calculated'):
        st.json(metadata)
else:
    st.markdown('''<section class="yld-empty"><h2>MAKE THE BETTER CALL.</h2>
<p>Your history becomes a way to compare preparation decisions. Run an analysis to see the estimated impact.</p>
<div class="yld-steps"><div class="yld-step"><b>01 / HISTORY</b><h3>LEARN YOUR DEMAND</h3><p>Forecast sales from earlier service patterns.</p></div>
<div class="yld-step"><b>02 / PREPARATION</b><h3>BALANCE THE COSTS</h3><p>Weigh leftover food against missed sales.</p></div>
<div class="yld-step"><b>03 / IMPACT</b><h3>SEE THE DIFFERENCE</h3><p>Compare estimated waste, shortages and net savings.</p></div></div></section>''', unsafe_allow_html=True)
with st.expander('Inspect the source data'):
    st.json(audit)
st.markdown('<footer class="yld-footer"><span>YLD / REDUCE YOUR WASTE</span><span>BUILT FROM EVERY SERVICE. BETTER WITH EVERY ACTUAL.</span></footer>', unsafe_allow_html=True)
