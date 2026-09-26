from pathlib import Path
import pandas as pd
import streamlit as st
from src.backtest import run_backtest
from src.load_data import load_data, restaurant_labels

st.set_page_config(page_title='Restaurant inventory analysis', layout='wide')
st.title('Restaurant inventory analysis')
st.caption('Demand forecasting → preparation recommendation → historical savings estimate')
st.warning('Scenario estimates, not proven savings. Observed sales stand in for demand; historical stockouts may hide unmet demand. Cost and margin inputs are assumptions.')
upload = st.sidebar.file_uploader('Restaurant history CSV', type='csv')
st.sidebar.caption('Included sample locations have IDs and descriptors, not real venue names. Add an optional restaurant_name column to your CSV to select your own venues by name.')
cost = st.sidebar.number_input('Assumed ingredient cost per kg', min_value=0.01, value=8.5)
margin = st.sidebar.number_input('Assumed contribution margin per kg', min_value=0.01, value=14.0)
currency = st.sidebar.text_input('Currency label (no conversion)', value='NZD')
source = upload if upload is not None else Path('data/raw/restaurant_data.csv')
try:
    data, audit = load_data(source)
except (ValueError, FileNotFoundError) as exc:
    st.error(str(exc))
    st.stop()
labels = restaurant_labels(data)
selected_label = st.sidebar.selectbox('Restaurant', list(labels))
restaurant = labels[selected_label]
signature = (restaurant, cost, margin, str(pd.util.hash_pandas_object(data, index=True).sum()))
st.write(f'Available history: {audit["start"]} to {audit["end"]}')
with st.expander('Data inspection'):
    st.json(audit)
if st.button('Run historical analysis', type='primary'):
    with st.spinner('Replaying historical forecasts…'):
        try:
            st.session_state['analysis'] = (signature, run_backtest(data[data.restaurant_id == restaurant], cost, margin))
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
if 'analysis' in st.session_state and st.session_state['analysis'][0] == signature:
    results, summary, metadata = st.session_state['analysis'][1]
    st.subheader('Policy comparison')
    st.dataframe(summary[['policy', 'mae_kg', 'rmse_kg', 'net_savings', 'potential_lost_margin', 'waste_reduction_pct']], hide_index=True)
    ml = summary[summary.policy == 'random_forest'].iloc[0]
    a, b, c = st.columns(3)
    a.metric(f'Estimated net savings ({currency})', f'{ml.net_savings:,.2f}')
    b.metric('Simulated waste avoided (kg)', f'{ml.waste_kg_avoided:,.1f}')
    c.metric('Potential shortage (kg)', f'{ml.potential_shortage_kg:,.1f}')
    st.caption(f'Evaluation: {ml.start} to {ml.end}. Negative savings are retained. Compare ML against the rolling-average policy before adopting it.')
    chart = results[results.policy == 'random_forest'].set_index('date')
    st.line_chart(chart[['food_sold_kg', 'forecast_kg', 'recommended_prep_kg']])
    st.download_button('Download detailed backtest', results.to_csv(index=False), 'backtest_results.csv', 'text/csv')
    st.download_button('Download savings summary', summary.to_csv(index=False), 'savings_summary.csv', 'text/csv')
    st.json(metadata)
