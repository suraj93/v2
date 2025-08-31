"""
Treasury Dashboard - Phase 1: Core Liquidity KPIs
Streamlit app showing bank balance, AP/AR flows, and deployable cash.
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, date
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import base64
from pathlib import Path

from data_access import (
    get_compute_today, get_data_freshness_info,
    get_investment_totals, load_holdings_df, load_attribution, 
    load_daily_interest_series, load_policy_limits, get_ap_ar_forecast_14d,
    load_perform_data
)
from formatting import fmt_inr_lakh_style, to_ist, format_refresh_time


# Page configuration
st.set_page_config(
    page_title="Treasury Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS to reduce top padding
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        margin-top: 0rem;
    }
</style>
""", unsafe_allow_html=True)

# Auto-refresh every 60 seconds
refresh_count = st_autorefresh(interval=60000, key="auto_refresh")

# Cache data functions
@st.cache_data(ttl=60)  # Treasury data: 60 seconds cache
def get_cached_treasury_data():
    return get_compute_today()

@st.cache_data(ttl=1800)  # Holdings data: 30 minutes cache  
def get_cached_investment_data():
    return get_investment_totals()

@st.cache_data(ttl=1800)
def get_cached_holdings_table():
    return load_holdings_df()

@st.cache_data(ttl=1800)
def get_cached_policy_limits():
    return load_policy_limits()

@st.cache_data(ttl=1800) 
def get_cached_daily_interest_series():
    return load_daily_interest_series(60)

@st.cache_data(ttl=1800)
def get_cached_ap_ar_forecast():
    return get_ap_ar_forecast_14d()

@st.cache_data(ttl=60)  # Treasury data cache (same as summary)
def get_cached_perform_data():
    return load_perform_data()

def get_all_data():
    """Get all data without UI elements."""
    treasury_data = get_cached_treasury_data()
    investment_data = get_cached_investment_data()
    freshness = get_data_freshness_info()
    return treasury_data, investment_data, freshness


def tab_cfo_summary():
    """Tab 1: CFO Summary - Treasury Position + Investment Portfolio + AP/AR Forecast."""
    treasury_data, investment_data, _ = get_all_data()
    
    st.divider()
    
    # ===== ROW 1: TREASURY KPIs =====
    st.subheader("🏦 Treasury Position")
    col1, col2, col3, col4 = st.columns(4)
    
    # KPI 1: Total Bank Balance
    with col1:
        bank_balance = treasury_data.get("bankBalance_rupees", 0)
        st.metric(
            label="💳 **Total Bank Balance**",
            value=fmt_inr_lakh_style(bank_balance),
            help=f"Current bank account balance: ₹{bank_balance:,.2f}"
        )
    
    # KPI 2: Raw AP (Next 7 days)
    with col2:
        raw_ap = treasury_data.get("rawAP_7d_rupees", 0)
        horizon = treasury_data.get("horizon_days", 7)
        st.metric(
            label=f"📤 **Raw AP (Next {horizon}d)**",
            value=fmt_inr_lakh_style(raw_ap),
            help=f"Accounts Payable due in next {horizon} days: ₹{raw_ap:,.2f}"
        )
    
    # KPI 3: Raw AR (Next 7 days)
    with col3:
        raw_ar = treasury_data.get("rawAR_7d_rupees", 0)
        st.metric(
            label=f"📥 **Raw AR (Next {horizon}d)**",
            value=fmt_inr_lakh_style(raw_ar),
            help=f"Accounts Receivable expected in next {horizon} days: ₹{raw_ar:,.2f}"
        )
    
    # KPI 4: Today's Deployable (with amber styling for negative)
    with col4:
        deployable = treasury_data.get("deployable_rupees", 0)
        
        # Apply amber styling for negative deployable
        if deployable < 0:
            st.markdown(
                f"""
                <div style="
                    padding: 1rem;
                    border-radius: 0.5rem;
                    background-color: #FFF8E1;
                    border: 1px solid #FFB300;
                    margin-bottom: 1rem;
                ">
                    <div style="font-size: 0.875rem; color: #666; margin-bottom: 0.25rem;">
                        💰 <strong>Today's Deployable</strong>
                    </div>
                    <div style="font-size: 1.875rem; font-weight: bold; color: #FF8F00;">
                        {fmt_inr_lakh_style(deployable)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.metric(
                label="💰 **Today's Deployable**",
                value=fmt_inr_lakh_style(deployable),
                help=f"Surplus cash available for investment: ₹{deployable:,.2f}"
            )

    st.divider()
    
    # ===== ROW 2: INVESTMENT KPIs =====
    st.subheader("📈 Investment Portfolio")
    col5, col6, col7 = st.columns(3)
    
    # KPI 5: Current Investment Balance  
    with col5:
        investment_balance = investment_data.get("current_investment_rupees", 0)
        st.metric(
            label="🏛️ **Current Investment Balance**",
            value=fmt_inr_lakh_style(investment_balance),
            help=f"Total corpus in liquid funds: ₹{investment_balance:,.2f}"
        )
    
    # KPI 6: Total Interest YTD
    with col6:
        ytd_interest = investment_data.get("ytd_interest_rupees", 0)
        st.metric(
            label="💹 **Total Interest (YTD)**", 
            value=fmt_inr_lakh_style(ytd_interest),
            help=f"Year-to-date interest earned: ₹{ytd_interest:,.2f}"
        )
    
    # KPI 7: Average Investment Balance (30d)
    with col7:
        avg_30d = investment_data.get("avg_30d_investment_rupees", 0)
        st.metric(
            label="📊 **Avg Investment Balance (30d)**",
            value=fmt_inr_lakh_style(avg_30d),
            help=f"30-day average investment balance: ₹{avg_30d:,.2f}"
        )

    st.divider()
    
    # ===== AP/AR FORECAST SECTION =====
    st.subheader("📊 Cash Flow Forecast (14 Days)")
    
    forecast_data = get_cached_ap_ar_forecast()
    
    if forecast_data.get("data_available") and forecast_data.get("forecast"):
        forecast_df = pd.DataFrame(forecast_data["forecast"])
        forecast_df['date'] = pd.to_datetime(forecast_df['date'])
        
        fig_forecast = go.Figure()
        fig_forecast.add_trace(go.Scatter(
            x=forecast_df['date'],
            y=forecast_df['expected_inflows'],
            mode='lines+markers',
            name='Expected Inflows',
            line=dict(color='green', width=2),
            hovertemplate='Inflows: ₹%{y:,.0f}<extra></extra>'
        ))
        fig_forecast.add_trace(go.Scatter(
            x=forecast_df['date'],
            y=forecast_df['expected_outflows'],
            mode='lines+markers', 
            name='Expected Outflows',
            line=dict(color='red', width=2),
            hovertemplate='Outflows: ₹%{y:,.0f}<extra></extra>'
        ))
        
        fig_forecast.update_layout(
            height=400,
            xaxis_title="Date",
            yaxis_title="Amount (₹)",
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig_forecast, use_container_width=True)
        
        # Summary metrics
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            st.metric("Total Inflows (14d)", fmt_inr_lakh_style(forecast_data.get("total_inflows_14d", 0)))
        with col_f2:
            st.metric("Total Outflows (14d)", fmt_inr_lakh_style(forecast_data.get("total_outflows_14d", 0)))
        with col_f3:
            net_flow = forecast_data.get("net_flow_14d", 0)
            st.metric("Net Flow (14d)", fmt_inr_lakh_style(net_flow))
            
    else:
        st.info("14-day forecast data currently unavailable")


def tab_deployment_approvals():
    """Tab 2: Daily Deployment Approvals."""
    st.subheader("📋 Daily Deployment Approvals")
    
    # Load perform.json and summary.json data
    perform_data = get_cached_perform_data()
    treasury_data = get_cached_treasury_data()
    
    if not perform_data.get("data_available"):
        st.error(f"⚠️ Deployment data unavailable: {perform_data.get('error', 'Unknown error')}")
        return
    
    # ===== 1. TABULAR SUMMARY FROM PERFORM.JSON =====
    st.subheader("📊 Investment Deployment Summary")
    
    # Create deployment summary table
    deployment_summary = pd.DataFrame([{
        "Date": perform_data.get("date", "N/A"),
        "Deploy Instrument": perform_data.get("deploy_instrument", "N/A"),
        "Issuer": perform_data.get("deploy_issuer", "N/A"), 
        "Deployable Value": fmt_inr_lakh_style(perform_data.get("deployable_value", 0)),
        "Tenor (Days)": perform_data.get("max_tenor", "N/A"),
        "Approval Needed": "Yes" if perform_data.get("approval_needed") else "No",
        "Status": "Pending Approval" if perform_data.get("approval_needed") else "Ready to Execute"
    }])
    
    st.dataframe(deployment_summary, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # ===== 2. BIG BLUE APPROVAL BUTTON =====
    st.subheader("🔐 Investment Action Approval")
    
    deployable_value = perform_data.get("deployable_value", 0)
    
    if deployable_value > 0 and perform_data.get("approval_needed"):
        # Big blue button for approval
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        with col_btn2:
            if st.button(
                "🔵 Click here to approve investment action",
                type="primary",
                use_container_width=True,
                key="approve_investment_tab2"
            ):
                st.success("✅ Investment action approved! (No action taken - UI demo)")
                st.balloons()
    elif deployable_value <= 0:
        st.info("ℹ️ No deployable surplus available today - no action required")
    else:
        st.info("ℹ️ Investment action does not require approval")
    
    st.divider()
    
    # ===== 3. DEPLOYMENT EXPLANATION (3 LINES) =====
    st.subheader("📝 Deployment Calculation Rationale")
    
    deployable = treasury_data.get("deployable_rupees", 0)
    current_balance = treasury_data.get("bankBalance_rupees", 0)
    raw_ar = treasury_data.get("rawAR_7d_rupees", 0) 
    raw_ap = treasury_data.get("rawAP_7d_rupees", 0)
    
    # Generate explanation based on deployable amount
    if deployable <= 0:
        explanation = f"""
        • **No deployable surplus**: Current balance {fmt_inr_lakh_style(current_balance)} insufficient after safety buffers.

        • **Cash flow requirements**: Expected AP outflows {fmt_inr_lakh_style(raw_ap)} exceed AR inflows {fmt_inr_lakh_style(raw_ar)}.

        • **Conservative approach**: Treasury policy maintains high operational reserves to ensure liquidity.
        """
    else:
        explanation = f"""
        • **Deployable surplus identified**: {fmt_inr_lakh_style(deployable)} available from current balance {fmt_inr_lakh_style(current_balance)}.

        • **Cash flow coverage**: AR inflows {fmt_inr_lakh_style(raw_ar)} and AP outflows {fmt_inr_lakh_style(raw_ap)} factored into calculation.

        • **Investment opportunity**: Surplus can be deployed to {perform_data.get('deploy_instrument', 'liquid instruments')} for overnight returns.
        """
    
    st.markdown(explanation)


def tab_investment_holdings():
    """Tab 3: Investment Holdings - Tables and Interest Chart."""
    # ===== HOLDINGS TABLE =====
    st.subheader("💼 Current Holdings")
    
    holdings_data = get_cached_holdings_table()
    if holdings_data:
        # Convert to DataFrame for display
        holdings_df = pd.DataFrame(holdings_data)
        if not holdings_df.empty:
            # Format for display
            display_df = holdings_df.copy()
            display_df['amount_rupees'] = display_df['amount_rupees'].apply(lambda x: fmt_inr_lakh_style(x))
            display_df['expected_annual_rate_percent'] = display_df['expected_annual_rate_percent'].apply(lambda x: f"{x:.2f}%")
            display_df['daily_interest_rupees'] = display_df['daily_interest_rupees'].apply(lambda x: f"₹{x:.2f}")
            
            # Rename columns for display
            display_df = display_df.rename(columns={
                'instrument_name': 'Instrument',
                'issuer': 'Issuer', 
                'amount_rupees': 'Amount',
                'expected_annual_rate_percent': 'Expected Rate',
                'daily_interest_rupees': 'Daily Interest',
                'updated_at': 'Updated'
            })
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("No holdings data available")
    else:
        st.warning("Holdings data unavailable")
    
    st.divider()
    
    # ===== ATTRIBUTION TABLE =====
    st.subheader("💹 Interest Attribution")
    
    col_date1, col_date2, col_date3 = st.columns([2, 2, 1])
    
    with col_date1:
        start_date = st.date_input("Start Date", value=date(2025, 1, 1), key="attr_start_tab3")
    with col_date2:
        end_date = st.date_input("End Date", value=date.today(), key="attr_end_tab3")
    with col_date3:
        ytd_button = st.button("YTD", help="Set to Year-to-Date range", key="ytd_button_tab3")
        
        if ytd_button:
            st.session_state['attr_start_tab3'] = date(2025, 1, 1)
            st.session_state['attr_end_tab3'] = date.today()
            st.rerun()
    
    # Load attribution data
    attribution_data = load_attribution(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
    
    if attribution_data:
        attr_df = pd.DataFrame(attribution_data)
        if not attr_df.empty:
            # Format for display
            display_attr = attr_df.copy()
            display_attr['interest_earned'] = display_attr['interest_earned'].apply(lambda x: fmt_inr_lakh_style(x))
            display_attr['avg_opening_balance_rupees'] = display_attr['avg_opening_balance_rupees'].apply(lambda x: fmt_inr_lakh_style(x))
            display_attr['avg_rate_percent'] = display_attr['avg_rate_percent'].apply(lambda x: f"{x:.2f}%")
            
            # Rename columns
            display_attr = display_attr.rename(columns={
                'instrument_name': 'Instrument',
                'issuer': 'Issuer',
                'interest_earned': 'Interest Earned', 
                'avg_opening_balance_rupees': 'Avg Balance',
                'avg_rate_percent': 'Avg Rate',
                'days_count': 'Days'
            })
            
            st.dataframe(display_attr, use_container_width=True, hide_index=True)
        else:
            st.info("No attribution data for selected period")
    else:
        st.warning("Attribution data unavailable")
    
    st.divider()
    
    # ===== DAILY INTEREST CHART (LINE GRAPH) =====
    st.subheader("📈 Daily Interest Earned (60 Days)")
    
    daily_series = get_cached_daily_interest_series()
    
    if daily_series:
        series_df = pd.DataFrame(daily_series)
        if not series_df.empty:
            series_df['date'] = pd.to_datetime(series_df['date'])
            
            # Line chart instead of bar chart
            fig_interest = go.Figure()
            fig_interest.add_trace(go.Scatter(
                x=series_df['date'],
                y=series_df['accrued_interest'],
                mode='lines+markers',
                name='Daily Interest',
                line=dict(color='blue', width=2),
                marker=dict(size=4),
                hovertemplate='Date: %{x}<br>Interest: ₹%{y:,.2f}<extra></extra>'
            ))
            
            fig_interest.update_layout(
                height=400,
                xaxis_title="Date",
                yaxis_title="Interest Earned (₹)",
                showlegend=False,
                hovermode='x'
            )
            
            st.plotly_chart(fig_interest, use_container_width=True)
            
            # Summary stats
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                total_interest = series_df['accrued_interest'].sum()
                st.metric("Total (60d)", f"₹{total_interest:,.2f}")
            with col_s2:
                avg_daily = series_df['accrued_interest'].mean()
                st.metric("Daily Average", f"₹{avg_daily:,.2f}")
            with col_s3:
                max_daily = series_df['accrued_interest'].max()
                st.metric("Peak Day", f"₹{max_daily:,.2f}")
            with col_s4:
                days_with_interest = len(series_df[series_df['accrued_interest'] > 0])
                st.metric("Active Days", f"{days_with_interest}/{len(series_df)}")
        else:
            st.info("No interest history available")
    else:
        st.info("Daily interest data unavailable")


def tab_policy_limits():
    """Tab 4: Policy Limits."""
    st.subheader("⚙️ Policy Configuration")
    
    policy_data = get_cached_policy_limits()
    
    col_pol1, col_pol2, col_pol3 = st.columns(3)
    
    with col_pol1:
        st.markdown("**Operational Buffers**")
        st.metric("Min Operating Cash", fmt_inr_lakh_style(policy_data.get("min_operating_cash", 0)))
        st.metric("Payroll Buffer", fmt_inr_lakh_style(policy_data.get("payroll_buffer", 0))) 
        st.metric("Tax Buffer", fmt_inr_lakh_style(policy_data.get("tax_buffer", 0)))
        
        if st.button("✏️ Edit Buffers", disabled=True, key="edit_buffers"):
            pass
        st.caption("Coming soon")
    
    with col_pol2:
        st.markdown("**Vendor Tiers**")
        st.metric("Critical Tier Floor", fmt_inr_lakh_style(policy_data.get("vendor_tier_critical", 0)))
        st.metric("Regular Tier Floor", fmt_inr_lakh_style(policy_data.get("vendor_tier_regular", 0)))
        st.metric("Approval Threshold", fmt_inr_lakh_style(policy_data.get("approval_threshold", 0)))
        
        if st.button("✏️ Edit Tiers", disabled=True, key="edit_tiers"):
            pass
        st.caption("Coming soon")
    
    with col_pol3:
        st.markdown("**Risk Parameters**") 
        st.metric("Recognition Ratio", f"{policy_data.get('recognition_ratio', 0)*100:.0f}%")
        st.metric("Shock Multiplier", f"{policy_data.get('shock_multiplier', 0):.2f}x")
        st.metric("", "")  # Spacer
        
        if st.button("✏️ Edit Parameters", disabled=True, key="edit_params"):
            pass
        st.caption("Coming soon")
    
    st.divider()
    
    # Additional policy details
    st.markdown("**Current Policy Configuration:**")
    if policy_data.get("data_available"):
        st.json({
            "operational_buffers": {
                "min_operating_cash": policy_data.get("min_operating_cash"),
                "payroll_buffer": policy_data.get("payroll_buffer"),
                "tax_buffer": policy_data.get("tax_buffer")
            },
            "vendor_tiers": {
                "critical_floor": policy_data.get("vendor_tier_critical"),
                "regular_floor": policy_data.get("vendor_tier_regular"),
                "approval_threshold": policy_data.get("approval_threshold")
            },
            "risk_parameters": {
                "recognition_ratio": policy_data.get("recognition_ratio"),
                "shock_multiplier": policy_data.get("shock_multiplier")
            }
        })
    else:
        st.warning("Policy data unavailable")

def add_logo(logo_path: str, height_px: int = 42, link: str | None = None, debug: bool = False):
    """
    Pins a logo to the top-left of the app and adds top padding so content doesn't overlap it.
    logo_path: absolute or relative path to the image file
    """
    p = Path(logo_path)
    if not p.exists():
        if debug:
            import streamlit as st
            st.warning(f"Logo not found at: {p.resolve()}")
        return

    b64 = base64.b64encode(p.read_bytes()).decode()
    link_open = f'<a href="{link}" target="_blank">' if link else ""
    link_close = "</a>" if link else ""

    import streamlit as st
    st.markdown(
        f"""
        <style>
            .app-logo {{
                position: fixed;
                top: 12px;
                left: 12px;
                height: {height_px}px;
                z-index: 1000;
            }}
            /* Add enough padding so pinned logo doesn't overlap content */
            .block-container {{
                padding-top: calc({height_px}px + 28px);
            }}
        </style>
        {link_open}
        <img class="app-logo" src="data:image/png;base64,{b64}" alt="Logo">
        {link_close}
        """,
        unsafe_allow_html=True,
    )

def main():
    """Main dashboard application with tabs."""
    base_dir = Path(__file__).parent
    add_logo(base_dir / "logo.png", height_px=80, debug=True)
    st.title("💰 Treasury Dashboard")
    
    # ===== GLOBAL HEADER (outside tabs to avoid duplication) =====
    treasury_data, investment_data, freshness = get_all_data()
    
    # Header info bar
    col_header1, col_header2, col_header3, col_header4 = st.columns([2, 2, 1, 1])
    
    with col_header1:
        as_of_time = to_ist(treasury_data.get("asOf"))
        st.markdown(f"**As of:** {as_of_time}")
    
    with col_header2:
        last_refresh = format_refresh_time()
        st.markdown(f"**Last refreshed:** {last_refresh}")
    
    with col_header3:
        if st.button("🔄 Refresh", help="Refresh all data manually", key="global_refresh"):
            st.cache_data.clear()
            st.rerun()
    
    with col_header4:
        st.markdown("**Timezone:** IST")
    
    # Data freshness indicator
    if freshness.get("is_stale") or treasury_data.get("error"):
        if treasury_data.get("error"):
            st.error(f"⚠️ Treasury Data Error: {treasury_data['error']}")
        elif freshness.get("is_stale"):
            age_hours = freshness.get("file_age_hours", 0)
            st.warning(f"⚠️ Data is {age_hours:.1f} hours old. Consider running CLI to update.")
    
    if not investment_data.get("data_available"):
        st.warning("⚠️ Investment data unavailable - holdings database may be missing")
    
    st.divider()
    
    # Create tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 CFO Summary", 
        "📋 Deployment Approvals", 
        "💼 Investment Holdings",
        "⚙️ Policy Limits"
    ])
    
    with tab1:
        tab_cfo_summary()
        
        # Decision context at bottom of CFO tab  
        reasons = treasury_data.get("reasons", [])
        if reasons:
            st.divider()
            st.subheader("📋 Decision Context")
            
            reason_descriptions = {
                "FIXED_BUFFERS": "Fixed operational buffers applied",
                "OUTFLOW_SHOCK": "Outflow shock buffer active", 
                "CONSERVATIVE_INFLOW": "Conservative inflow recognition",
                "NO_SURPLUS": "No deployable surplus available",
                "VENDOR_BUFFERS": "Vendor-specific buffers required",
                "DATA_UNAVAILABLE": "Treasury data currently unavailable",
                "CUTOFF_PASSED": "Trading cutoff time has passed"
            }
            
            reason_list = []
            for reason in reasons:
                desc = reason_descriptions.get(reason, reason)
                reason_list.append(f"• {desc}")
            
            st.markdown("\n".join(reason_list))
        
        # Footer
        st.divider()
        file_updated = treasury_data.get("file_updated_at")
        if file_updated:
            file_time = to_ist(file_updated)
            st.caption(f"📄 Treasury data last updated: {file_time}")
        else:
            st.caption("📄 Treasury data timestamp unavailable")
    
    with tab2:
        tab_deployment_approvals()
    
    with tab3:
        tab_investment_holdings()
    
    with tab4:
        tab_policy_limits()


if __name__ == "__main__":
    main()