"""
Quorum — Streamlit UI (3 screens)

  1. Queue        — the ~10 surfaced accounts: probability + uncertainty band,
                    top reason, money touched, action chip (Escalate / Review / Clear).
  2. Case detail  — posterior plot, signals, expected-loss arithmetic, typology,
                    ring subgraph, and a downloadable SAR memo.
  3. Pipeline view — the shared Cognee Case object after each agent: fields
                    accreting from signals → probability → action → memo (criterion 2).
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geodo_market
import geodo_research
import gtm
from ui import charts, ring_graph, snapshot
from ui.feed_parse import parse_research_feed
from ui.graph_data import build_graph, funnel_counts
from ui.snapshot import compute_chart_data

GEODO_DOC = Path(__file__).resolve().parents[1] / "docs" / "GEODO_RESEARCH.md"


def _geodo(result: dict) -> dict:
    """The Geodo research payload — from the snapshot, falling back to the live
    registry so the panel still renders against an older snapshot."""
    return (result or {}).get("geodo") or geodo_research.summary()


def _geo_market(result: dict) -> dict:
    """The Geo (geodo.ai) market-intelligence payload — snapshot, else live registry."""
    return (result or {}).get("geo_market") or geodo_market.summary()


def _roi(result: dict) -> dict:
    """The run-specific ROI (Geo labor rate × this run's actuals), from the Domain Expert's
    MarketContext captured in the snapshot."""
    mc = (result or {}).get("market_context") or {}
    return mc.get("roi") or {}


def _gtm(result: dict) -> dict | None:
    """The Tier 2 Ring → Real Buyers packet — snapshot, falling back to the committable cache."""
    return (result or {}).get("gtm") or gtm.load_packet()


def _geo_connection(result: dict) -> dict | None:
    """The Geo live-MCP connection proof captured in the snapshot (None when offline-only)."""
    return (result or {}).get("geo_connection")

load_dotenv()

st.set_page_config(page_title="Quorum — AML Triage", page_icon="🔭",
                   layout="wide", initial_sidebar_state="collapsed")

for key, default in [("result", None), ("selected", None), ("force_upload", False)]:
    if key not in st.session_state:
        st.session_state[key] = default

# Pre-built demo: open straight into the visuals — no upload, no run required.
if st.session_state.result is None and not st.session_state.force_upload:
    st.session_state.result = snapshot.load()

ACTION_COLOR = {"ESCALATE": "#ff4d6d", "REVIEW": "#ffb020", "CLEAR": "#2ee6a6"}
ACTION_EMOJI = {"ESCALATE": "🔴", "REVIEW": "🟡", "CLEAR": "🟢"}
ROLE_COLOR = {"source": "#5fd0e0", "relay": "#8ab4ff", "sink": "#ff5468", "none": "#5a6273"}


def inject_theme() -> None:
    st.markdown(textwrap.dedent("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
      :root{
        --void:#070809; --ink:#0a0c11; --panel:#0f131b; --panel2:#141923;
        --line:rgba(178,198,234,.10); --line2:rgba(178,198,234,.20);
        --text:#e7ebf3; --muted:#8a93a6; --faint:#59617350;
        --label:#7b859b;
        --accent:#5fd0e0;                /* ice-cyan chrome — focus/active only */
        --esc:#ff5468; --rev:#f7b733; --clr:#34d6a4; --noise:#46527a;
        --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
        --sans:'IBM Plex Sans',system-ui,-apple-system,sans-serif;
        --serif:'Fraunces',Georgia,serif;
      }
      /* ── canvas: ink + blueprint grid + grain + vignette ───────────────── */
      .stApp{
        background:
          radial-gradient(1100px 620px at 50% -10%, rgba(95,208,224,.06), transparent 60%),
          radial-gradient(900px 700px at 100% 110%, rgba(255,84,104,.04), transparent 55%),
          linear-gradient(transparent 0 calc(100% - 1px), var(--line) 0) 0 0/100% 38px,
          linear-gradient(90deg, transparent 0 calc(100% - 1px), var(--line) 0) 0 0/38px 100%,
          var(--ink);
        color:var(--text); font-family:var(--sans);
      }
      .stApp::before{ /* film grain */
        content:""; position:fixed; inset:0; z-index:0; pointer-events:none; opacity:.5;
        background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
        mix-blend-mode:overlay;
      }
      .block-container{ padding-top:1.1rem; max-width:1320px; position:relative; z-index:1; }
      header[data-testid="stHeader"]{ background:transparent; }
      #MainMenu, footer{ visibility:hidden; }
      html, body, [class*="css"]{ font-family:var(--sans); }

      /* ── masthead (replaces the gradient hero) ─────────────────────────── */
      .qmast{ border:1px solid var(--line2); border-radius:4px; background:
          linear-gradient(180deg, rgba(255,255,255,.02), transparent),
          var(--panel);
        padding:18px 22px 16px; position:relative; overflow:hidden;
        box-shadow:0 22px 60px -30px rgba(0,0,0,.9), inset 0 1px 0 rgba(255,255,255,.03);
        animation:rise .6s cubic-bezier(.2,.7,.2,1) both; }
      .qmast::after{ /* top scanline accent */
        content:""; position:absolute; left:0; right:0; top:0; height:2px;
        background:linear-gradient(90deg, var(--esc) 0 28%, var(--rev) 28% 36%, var(--clr) 36% 46%, transparent 46%);
        opacity:.85; }
      .qmast-top{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
      .qmark{ font-family:var(--serif); font-weight:600; font-size:34px; letter-spacing:-.02em;
        color:var(--text); line-height:1; }
      .qmark b{ color:var(--accent); font-weight:600; }
      .qeyebrow{ font-family:var(--mono); font-size:10.5px; letter-spacing:.34em; text-transform:uppercase;
        color:var(--label); }
      .qmast-meta{ margin-left:auto; display:flex; gap:22px; font-family:var(--mono); font-size:10.5px;
        letter-spacing:.16em; text-transform:uppercase; color:var(--muted); }
      .qmast-meta b{ color:var(--text); font-weight:600; display:block; letter-spacing:.06em; margin-top:2px; }
      .qmast-sub{ margin-top:11px; color:var(--muted); font-size:13.5px; max-width:60ch; line-height:1.55; }
      .qmast-sub i{ color:var(--text); font-style:normal; border-bottom:1px solid var(--line2); }
      .qlive{ display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--clr);
        margin-right:7px; box-shadow:0 0 0 0 var(--clr); animation:pulse 2.4s infinite; vertical-align:middle; }

      /* ── KPI instrument tiles ──────────────────────────────────────────── */
      .qkpis{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin:12px 0 2px; }
      .qkpi{ border:1px solid var(--line); border-radius:4px; background:var(--panel);
        padding:13px 15px 12px; position:relative; overflow:hidden;
        animation:rise .6s cubic-bezier(.2,.7,.2,1) both; }
      .qkpi::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:var(--c,var(--line2)); }
      .qkpi:nth-child(1){animation-delay:.04s} .qkpi:nth-child(2){animation-delay:.10s}
      .qkpi:nth-child(3){animation-delay:.16s} .qkpi:nth-child(4){animation-delay:.22s}
      .qkpi:nth-child(5){animation-delay:.28s}
      .qkpi:hover{ border-color:var(--line2); background:var(--panel2); }
      .qkpi .lab{ font-family:var(--mono); font-size:9.5px; letter-spacing:.2em; text-transform:uppercase;
        color:var(--label); display:flex; align-items:center; gap:6px; }
      .qkpi .val{ font-family:var(--mono); font-size:27px; font-weight:600; color:var(--text); line-height:1.1;
        margin-top:7px; letter-spacing:-.01em; }
      .qkpi .val.c{ color:var(--c); }
      .qkpi .sub{ font-family:var(--mono); font-size:10px; color:var(--muted); margin-top:5px; letter-spacing:.02em; }
      .qkpi .sub b{ color:var(--clr); font-weight:600; }

      /* ── tabs as a dossier index ───────────────────────────────────────── */
      .stTabs [data-baseweb="tab-list"]{ gap:2px; border-bottom:1px solid var(--line);
        background:transparent; padding-bottom:0; }
      .stTabs [data-baseweb="tab"]{ background:transparent; border:none; border-radius:0;
        padding:9px 16px 11px; color:var(--muted); font-family:var(--mono); font-size:11.5px;
        letter-spacing:.1em; text-transform:uppercase; position:relative; }
      .stTabs [data-baseweb="tab"]:hover{ color:var(--text); }
      .stTabs [aria-selected="true"]{ color:var(--text) !important; }
      .stTabs [aria-selected="true"]::after{ content:""; position:absolute; left:10px; right:10px; bottom:-1px;
        height:2px; background:var(--accent); }
      .stTabs [data-baseweb="tab-highlight"]{ display:none; }

      /* ── controls ──────────────────────────────────────────────────────── */
      .stButton>button, .stDownloadButton>button{ border-radius:3px; font-family:var(--mono);
        font-size:12px; letter-spacing:.06em; font-weight:600; border:1px solid var(--line2);
        background:var(--panel); color:var(--text); transition:.15s; }
      .stButton>button:hover, .stDownloadButton>button:hover{ border-color:var(--accent);
        color:var(--accent); background:var(--panel2); }
      .stButton>button[kind="primary"], .stDownloadButton>button{
        background:var(--accent); border-color:var(--accent); color:#06141a; }
      .stButton>button[kind="primary"]:hover, .stDownloadButton>button:hover{
        background:#7fe0ee; color:#06141a; filter:none; }
      div[data-baseweb="select"]>div{ background:var(--panel); border-color:var(--line2);
        border-radius:3px; font-family:var(--mono); }
      .stTextInput input{ background:var(--panel); border-radius:3px; font-family:var(--mono); }

      /* ── dataframe ─────────────────────────────────────────────────────── */
      [data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:4px; }
      [data-testid="stDataFrame"] thead th{ background:var(--panel)!important;
        font-family:var(--mono)!important; font-size:10px!important; letter-spacing:.1em;
        text-transform:uppercase; color:var(--label)!important; }

      /* ── caption / divider polish ──────────────────────────────────────── */
      [data-testid="stCaptionContainer"], .stCaption{ color:var(--muted)!important; }
      hr{ border-color:var(--line); }
      .stAlert{ border-radius:4px; border:1px solid var(--line2); }

      /* eyebrow label helper */
      .qsec{ font-family:var(--mono); font-size:10px; letter-spacing:.26em; text-transform:uppercase;
        color:var(--label); margin:2px 0 8px; }
      .qsec .num{ color:var(--accent); }

      /* ══ CASE FILE DOSSIER ════════════════════════════════════════════════ */
      .dossier{ border:1px solid var(--line2); border-radius:5px; background:var(--panel);
        overflow:hidden; position:relative; animation:rise .5s cubic-bezier(.2,.7,.2,1) both;
        box-shadow:0 26px 70px -36px rgba(0,0,0,.95); }
      .dh{ display:flex; align-items:center; gap:20px; padding:18px 24px; border-bottom:1px solid var(--line);
        background:linear-gradient(180deg, rgba(255,255,255,.025), transparent); }
      .dh-id{ font-family:var(--serif); font-size:42px; font-weight:600; letter-spacing:-.02em; line-height:.95; }
      .dh-meta{ display:flex; flex-direction:column; gap:4px; font-family:var(--mono); font-size:10.5px;
        letter-spacing:.05em; color:var(--muted); }
      .dh-meta .ln{ display:flex; gap:7px; } .dh-meta b{ color:var(--text); font-weight:600; }
      .stamp{ margin-left:auto; font-family:var(--mono); font-weight:700; font-size:19px; letter-spacing:.16em;
        padding:9px 17px; border:2.5px solid currentColor; border-radius:6px; transform:rotate(-5deg);
        text-transform:uppercase; box-shadow:inset 0 0 0 1.5px currentColor; opacity:.92;
        text-align:center; line-height:1.05; }
      .stamp small{ display:block; font-size:8px; letter-spacing:.25em; opacity:.85; margin-top:2px; }
      .stamp.esc{ color:var(--esc); } .stamp.rev{ color:var(--rev); } .stamp.clr{ color:var(--clr); }

      .callout{ display:flex; gap:13px; align-items:flex-start; margin:14px 0; padding:13px 16px;
        border:1px solid var(--line2); border-left:2px solid var(--rev); border-radius:4px;
        background:var(--panel); font-size:13px; color:var(--muted); line-height:1.55; }
      .callout .mk{ font-family:var(--mono); color:var(--rev); font-size:18px; line-height:1; }
      .callout b{ color:var(--text); }

      .dgrid{ display:grid; grid-template-columns:1.18fr 1fr; }
      .dcol{ padding:20px 24px; min-width:0; }
      .dcol+.dcol{ border-left:1px solid var(--line); }
      .dblk{ margin-bottom:24px; } .dblk:last-child{ margin-bottom:0; }
      .dblk>.h{ font-family:var(--mono); font-size:9.5px; letter-spacing:.2em; text-transform:uppercase;
        color:var(--label); margin-bottom:13px; }

      /* probability rail */
      .rail{ position:relative; height:30px; margin:26px 6px 26px; }
      .rail .track{ position:absolute; top:12px; left:0; right:0; height:6px; border-radius:3px;
        background:linear-gradient(90deg, rgba(52,214,164,.3), rgba(247,183,51,.28) 50%, rgba(255,84,104,.36)); }
      .rail .ci{ position:absolute; top:8px; height:14px; background:rgba(231,235,243,.16);
        border-left:1px solid var(--line2); border-right:1px solid var(--line2); border-radius:2px; }
      .rail .tau{ position:absolute; top:-2px; bottom:8px; width:0; border-left:1.5px dashed var(--accent); }
      .rail .tau span{ position:absolute; top:-15px; left:50%; transform:translateX(-50%);
        font-family:var(--mono); font-size:9px; color:var(--accent); white-space:nowrap; }
      .rail .pt{ position:absolute; top:4px; width:3px; height:22px; background:var(--c); border-radius:2px;
        box-shadow:0 0 12px var(--c); }
      .rail .pv{ position:absolute; top:-23px; transform:translateX(-50%); font-family:var(--mono);
        font-size:14px; font-weight:700; color:var(--c); white-space:nowrap; }
      .rail .scale{ position:absolute; top:24px; left:0; right:0; display:flex; justify-content:space-between;
        font-family:var(--mono); font-size:8.5px; color:var(--label); opacity:.7; }

      /* ledger */
      .ledger .lr{ display:flex; align-items:center; gap:13px; padding:11px 0; border-bottom:1px solid var(--line); }
      .ledger .lr:last-child{ border-bottom:none; }
      .ledger .lk{ font-family:var(--mono); font-size:11px; color:var(--muted); width:120px; flex-shrink:0; }
      .ledger .lr.win .lk{ color:var(--text); }
      .ledger .lbar{ flex:1; height:9px; background:rgba(255,255,255,.05); border-radius:2px; overflow:hidden; }
      .ledger .lbar i{ display:block; height:100%; background:var(--c); opacity:.85; border-radius:2px; }
      .ledger .lv{ font-family:var(--mono); font-size:12.5px; font-weight:600; color:var(--text);
        width:104px; text-align:right; flex-shrink:0; }
      .ledger .pick{ font-family:var(--mono); font-size:8px; letter-spacing:.12em; padding:2px 6px;
        border:1px solid var(--c); color:var(--c); border-radius:3px; }
      .ledger .foot{ display:flex; gap:20px; margin-top:13px; font-family:var(--mono); font-size:10.5px;
        color:var(--muted); } .ledger .foot b{ color:var(--text); }

      /* signal diverging bars */
      .sig .sr{ display:grid; grid-template-columns:120px 1fr 50px; align-items:center; gap:9px; margin:9px 0; }
      .sig .sk{ font-family:var(--mono); font-size:10.5px; color:var(--text); white-space:nowrap;
        overflow:hidden; text-overflow:ellipsis; }
      .sig .sb{ position:relative; height:14px; }
      .sig .sb .mid{ position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--line2); }
      .sig .sb i{ position:absolute; top:2px; height:10px; border-radius:2px; }
      .sig .sb i.toward{ background:var(--esc); left:50%; }
      .sig .sb i.away{ background:var(--clr); right:50%; }
      .sig .sv{ font-family:var(--mono); font-size:10px; text-align:right; }
      .sig .sv.toward{ color:var(--esc); } .sig .sv.away{ color:var(--clr); }
      .sig .axis{ display:flex; justify-content:space-between; font-family:var(--mono); font-size:8px;
        letter-spacing:.08em; color:var(--label); opacity:.7; margin:4px 0 0 129px; }

      .chips{ display:flex; flex-wrap:wrap; gap:7px; }
      .chip{ font-family:var(--mono); font-size:10px; letter-spacing:.03em; padding:5px 10px;
        border:1px solid var(--line2); border-radius:3px; color:var(--text); background:var(--panel2); }
      .chip.off{ color:var(--label); border-style:dashed; opacity:.5; }

      .dlog{ font-family:var(--mono); font-size:11.5px; line-height:1.75; color:var(--muted);
        background:var(--void); border:1px solid var(--line); border-radius:4px; padding:15px 17px;
        white-space:pre-wrap; word-break:break-word; } .dlog b{ color:var(--text); font-weight:600; }
      .dlog .em{ color:var(--accent); }

      /* ══ AGENT RELAY — the Case node accreting through Cognee ═════════════ */
      .accum{ border:1px solid var(--line2); border-radius:5px; background:var(--panel);
        padding:16px 20px; margin-bottom:4px; animation:rise .5s both; }
      .accum-h{ font-family:var(--mono); font-size:10px; letter-spacing:.18em; text-transform:uppercase;
        color:var(--label); } .accum-h b{ color:var(--text); }
      .accbar{ display:flex; gap:3px; margin:13px 0 10px; height:32px; }
      .accbar span{ display:flex; flex-direction:column; align-items:center; justify-content:center;
        border:1px solid var(--c); color:var(--c); border-radius:3px; font-family:var(--mono);
        font-size:10px; font-weight:600; letter-spacing:.02em; white-space:nowrap; overflow:hidden;
        min-width:0; line-height:1.25; animation:grow .55s cubic-bezier(.2,.8,.2,1) both; transform-origin:left; }
      .accbar span small{ font-size:8px; opacity:.7; letter-spacing:.05em; }
      .accbar span:nth-child(1){animation-delay:.02s} .accbar span:nth-child(2){animation-delay:.14s}
      .accbar span:nth-child(3){animation-delay:.26s} .accbar span:nth-child(4){animation-delay:.38s}
      .accum-f{ font-family:var(--mono); font-size:11px; color:var(--muted); } .accum-f b{ color:var(--text); }

      .stages{ margin-top:12px; }
      .stage{ display:grid; grid-template-columns:52px 1fr; }
      .spine{ position:relative; display:flex; justify-content:center; }
      .spine::before{ content:""; position:absolute; top:0; bottom:0; width:2px;
        background:linear-gradient(var(--a), var(--line2)); opacity:.5; }
      .stage:first-child .spine::before{ top:30px; }
      .stage:last-child .spine::before{ bottom:auto; height:30px; }
      .snode{ position:relative; z-index:2; width:34px; height:34px; border-radius:50%; background:var(--ink);
        border:2px solid var(--a); color:var(--a); display:flex; align-items:center; justify-content:center;
        font-family:var(--mono); font-size:12px; font-weight:700; margin-top:14px;
        box-shadow:0 0 0 5px var(--ink), 0 0 18px -3px var(--a); }
      .scard{ border:1px solid var(--line); border-left:2px solid var(--a); border-radius:4px;
        background:var(--panel); margin:8px 0 14px 10px; padding:15px 17px; animation:rise .5s both; }
      .shead{ display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin-bottom:12px;
        border-bottom:1px solid var(--line); padding-bottom:10px; flex-wrap:wrap; }
      .sname{ font-family:var(--serif); font-size:22px; font-weight:600; color:var(--text); line-height:1; }
      .srole{ font-family:var(--mono); font-size:8.5px; letter-spacing:.22em; color:var(--a);
        border:1px solid var(--a); border-radius:3px; padding:2px 7px; margin-left:10px; vertical-align:middle; }
      .sio{ font-family:var(--mono); font-size:10px; color:var(--muted); display:flex; gap:14px; }
      .sio .w{ color:var(--a); font-weight:600; }
      .fields{ display:grid; grid-template-columns:1fr 1fr; gap:0 26px; }
      .frow{ display:flex; justify-content:space-between; gap:12px; font-family:var(--mono); font-size:11px;
        border-bottom:1px solid rgba(178,198,234,.05); padding:5px 0; min-width:0; }
      .frow .fk{ color:var(--label); white-space:nowrap; }
      .frow .fk::before{ content:"+ "; color:var(--a); font-weight:700; }
      .frow .fv{ color:var(--text); font-weight:600; text-align:right; white-space:nowrap; overflow:hidden;
        text-overflow:ellipsis; }
      .handoff{ font-family:var(--mono); font-size:9px; letter-spacing:.12em; color:var(--muted); margin-top:12px;
        text-transform:uppercase; display:flex; align-items:center; gap:8px; }
      .handoff::before{ content:"↳"; color:var(--a); font-size:12px; }
      .handoff b{ color:var(--a); }

      /* ══ LAUNCH CARD — opens the standalone constellation in a new tab ═════ */
      a.launch{ display:flex; align-items:center; gap:24px; text-decoration:none!important;
        color:var(--text)!important; border:1px solid var(--line2); border-radius:7px;
        padding:20px 24px; position:relative; overflow:hidden; transition:.22s cubic-bezier(.2,.7,.2,1);
        background:radial-gradient(640px 220px at 8% -20%, rgba(95,208,224,.08), transparent 60%), var(--panel);
        box-shadow:0 24px 64px -36px rgba(0,0,0,.95); animation:rise .5s both; }
      a.launch:hover{ border-color:var(--accent); transform:translateY(-2px);
        box-shadow:0 30px 76px -32px rgba(0,0,0,.98), 0 0 0 1px rgba(95,208,224,.22); }
      a.launch::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:2px;
        background:linear-gradient(var(--esc), var(--accent)); opacity:.8; }
      .launch-viz{ flex:0 0 auto; width:104px; height:74px; opacity:.95; }
      .launch-viz .ln{ stroke:rgba(178,198,234,.28); stroke-width:1; }
      .launch-viz .ln.r{ stroke:var(--esc); stroke-width:1.4; }
      .launch-viz circle{ transition:.22s; }
      .launch-viz .n{ fill:#8ab4ff; } .launch-viz .e{ fill:var(--esc); }
      .launch-viz .e.p{ animation:vizpulse 2.2s ease-in-out infinite; }
      .launch-viz .e.p2{ animation:vizpulse 2.2s ease-in-out .7s infinite; }
      a.launch:hover .launch-viz{ opacity:1; }
      .launch-body{ display:block; flex:1 1 auto; min-width:0; }
      .launch-k{ font-family:var(--mono); font-size:9.5px; letter-spacing:.22em; text-transform:uppercase;
        color:var(--label); display:flex; align-items:center; gap:9px; }
      .launch-k .dot{ width:6px; height:6px; border-radius:50%; background:var(--clr);
        box-shadow:0 0 7px var(--clr); }
      .launch-t{ display:block; font-family:var(--serif); font-size:24px; font-weight:600; color:var(--text);
        margin:6px 0 7px; line-height:1.05; letter-spacing:-.01em; }
      .launch-d{ display:block; font-size:13px; color:var(--muted); line-height:1.55; max-width:60ch; }
      .launch-d b{ color:var(--text); font-weight:600; }
      .launch-cta{ flex:0 0 auto; font-family:var(--mono); font-size:12px; letter-spacing:.05em;
        color:var(--accent); border:1px solid var(--accent); border-radius:5px; padding:11px 17px;
        white-space:nowrap; display:flex; align-items:center; gap:9px; transition:.2s; }
      a.launch:hover .launch-cta{ background:var(--accent); color:#06141a; }
      .launch-cta .arr{ display:inline-block; transition:transform .2s; font-size:14px; }
      a.launch:hover .arr{ transform:translate(2px,-2px); }
      @keyframes vizpulse{ 0%,100%{ opacity:.55; r:3 } 50%{ opacity:1; r:4.4 } }

      /* ══ GEO / MARKET INTELLIGENCE ══════════════════════════════════════════════ */
      /* geo section divider */
      .geo-sec{ font-family:var(--mono); font-size:9.5px; letter-spacing:.24em; text-transform:uppercase;
        color:var(--label); margin:20px 0 10px; display:flex; align-items:center; gap:10px; }
      .geo-sec::after{ content:""; flex:1; height:1px; background:var(--line); }
      .geo-sec b{ color:var(--accent); }
      /* geodo.ai brand attribution — italic + accent underline so judges notice the brand */
      .geodo-brand{
        color:var(--accent); font-style:italic;
        text-decoration:underline;
        text-decoration-color:rgba(95,208,224,.45);
        text-underline-offset:3px;
      }
      /* geo connection badge */
      .geo-conn{ display:flex; align-items:center; gap:12px; border:1px solid var(--line); border-radius:5px;
        background:var(--panel); padding:11px 17px; font-family:var(--mono); font-size:10.5px;
        color:var(--muted); flex-wrap:wrap; margin-bottom:14px; }
      .geo-conn b{ color:var(--text); }
      .cdot{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }
      .cdot.on{ background:var(--clr); box-shadow:0 0 0 0 var(--clr); animation:pulse 2.4s infinite; }
      .cdot.off{ background:var(--label); }
      /* research quote */
      .geo-quote{ border-left:2px solid var(--accent); margin:12px 0; padding:13px 18px;
        background:var(--panel); border-radius:0 5px 5px 0; font-size:12.5px; color:var(--muted);
        line-height:1.72; }
      .geo-quote .geo-src{ font-family:var(--mono); font-size:8.5px; color:var(--label); margin-top:8px;
        letter-spacing:.1em; display:block; }
      /* enforcement timeline */
      .enf-wrap{ margin:10px 0; }
      .enf-track{ position:relative; padding:0 0 0 26px; }
      .enf-track::before{ content:""; position:absolute; left:7px; top:14px; bottom:14px; width:2px;
        background:linear-gradient(var(--esc), var(--rev), var(--accent)); opacity:.4; }
      .enf-card{ position:relative; border:1px solid var(--line); border-radius:5px; background:var(--panel);
        padding:13px 16px; margin-bottom:9px; animation:rise .5s both; }
      .enf-card::before{ content:""; position:absolute; left:-21px; top:16px; width:9px; height:9px;
        border-radius:50%; background:var(--ec,var(--accent)); border:2px solid var(--ink); box-shadow:0 0 8px var(--ec,var(--accent)); }
      .enf-card::after{ content:""; position:absolute; left:-15px; top:21px; width:15px; height:1px;
        background:var(--ec,var(--accent)); opacity:.35; }
      .enf-top{ display:flex; align-items:baseline; gap:9px; margin-bottom:7px; flex-wrap:wrap; }
      .enf-badge{ font-family:var(--mono); font-size:8px; letter-spacing:.14em; font-weight:700;
        text-transform:uppercase; padding:2px 7px; border-radius:3px; flex-shrink:0; }
      .enf-inst{ font-family:var(--serif); font-size:15px; font-weight:600; color:var(--text); }
      .enf-date{ font-family:var(--mono); font-size:9px; color:var(--label); margin-left:auto; white-space:nowrap; }
      .enf-action{ font-size:12px; color:var(--muted); line-height:1.55; margin-bottom:7px; }
      .enf-signals{ display:flex; gap:4px; flex-wrap:wrap; }
      .enf-sig{ font-family:var(--mono); font-size:8.5px; padding:2px 6px; border-radius:2px;
        border:1px solid rgba(255,84,104,.35); color:var(--esc); background:rgba(255,84,104,.05); }
      /* persona cards */
      .persona-grid{ display:grid; grid-template-columns:1fr 1fr; gap:9px; margin:10px 0; }
      .persona-card{ border:1px solid var(--line); border-radius:5px; background:var(--panel);
        padding:14px 15px; position:relative; overflow:hidden; animation:rise .5s both; }
      .persona-card::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:var(--pc,var(--accent)); }
      .persona-card:hover{ border-color:var(--line2); background:var(--panel2); }
      .persona-title{ font-family:var(--serif); font-size:15px; font-weight:600; color:var(--text); margin-bottom:8px; }
      .persona-pains{ display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px; }
      .persona-pain{ font-family:var(--mono); font-size:8.5px; padding:2px 7px; border:1px solid var(--line2);
        border-radius:2px; color:var(--muted); background:var(--void); }
      .persona-trigger{ font-family:var(--mono); font-size:9px; color:var(--label); }
      .persona-trigger b{ color:var(--rev); }
      /* messaging angle cards */
      .angle-grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:9px; margin:10px 0; }
      .angle-card{ border:1px solid var(--line); border-radius:5px; background:var(--panel);
        padding:15px 16px; animation:rise .5s both; position:relative; overflow:hidden; }
      .angle-card::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:var(--ac,var(--accent)); }
      .angle-persona{ font-family:var(--mono); font-size:8px; letter-spacing:.18em; text-transform:uppercase;
        color:var(--ac,var(--accent)); margin-bottom:8px; }
      .angle-text{ font-size:12px; color:var(--text); line-height:1.65; }
      .angle-text b{ color:var(--ac,var(--accent)); }
      /* digital twin */
      .twin-wrap{ border:1px solid var(--line2); border-radius:6px; overflow:hidden; margin:10px 0;
        animation:rise .5s both; box-shadow:0 20px 60px -36px rgba(0,0,0,.9); }
      .twin-head{ padding:14px 20px; background:linear-gradient(180deg,rgba(178,148,255,.05),transparent);
        border-bottom:1px solid var(--line); display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
      .twin-title{ font-family:var(--serif); font-size:20px; font-weight:600; color:var(--text); }
      .twin-badge{ font-family:var(--mono); font-size:9px; letter-spacing:.14em; text-transform:uppercase;
        padding:3px 9px; border-radius:3px; }
      .twin-badge.learned{ background:rgba(52,214,164,.1); border:1px solid var(--clr); color:var(--clr); }
      .twin-badge.nochg{ background:rgba(255,255,255,.04); border:1px solid var(--line2); color:var(--label); }
      .twin-probe{ font-family:var(--mono); font-size:10px; color:var(--muted); font-style:italic;
        line-height:1.65; padding:10px 20px; border-bottom:1px solid var(--line); background:var(--void); }
      .twin-probe b{ color:var(--accent); font-style:normal; }
      .twin-cols{ display:grid; grid-template-columns:1fr 1fr; background:var(--panel); }
      .twin-col{ padding:15px 19px; min-width:0; max-height:340px; overflow-y:auto; }
      .twin-col+.twin-col{ border-left:1px solid var(--line); }
      .twin-lab{ font-family:var(--mono); font-size:8.5px; letter-spacing:.18em; text-transform:uppercase;
        margin-bottom:8px; display:flex; align-items:center; gap:6px; }
      .twin-dot{ width:5px; height:5px; border-radius:50%; display:inline-block; }
      .twin-text{ font-size:12px; line-height:1.75; white-space:pre-wrap; word-break:break-word; }
      .twin-text.bef{ color:var(--muted); }
      .twin-text.aft{ color:var(--text); }
      .twin-foot{ display:flex; align-items:center; gap:14px; font-family:var(--mono); font-size:10px;
        color:var(--muted); padding:9px 20px; border-top:1px solid var(--line); background:var(--void); flex-wrap:wrap; }
      .twin-foot b{ color:var(--text); }
      .twin-foot .tarrow{ color:var(--clr); font-size:13px; }
      .twin-foot .tdelta{ color:var(--clr); font-weight:700; }
      /* geodo.ai intelligence feed */
      .gfeed-wrap{ border:1px solid var(--line2); border-radius:6px; overflow:hidden; margin:12px 0;
        box-shadow:0 8px 32px -12px rgba(0,0,0,.7); animation:rise .5s both; }
      .gfeed-header{ display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap;
        gap:10px; padding:13px 18px;
        background:linear-gradient(90deg,rgba(95,208,224,.07) 0%,rgba(95,208,224,.02) 60%,transparent 100%);
        border-bottom:1px solid var(--line); }
      .gfeed-brand{ display:flex; align-items:center; gap:10px; }
      .gfeed-title{ font-family:var(--serif); font-size:17px; font-weight:700; color:var(--text);
        letter-spacing:-.01em; }
      .gfeed-sublabel{ font-family:var(--mono); font-size:8px; letter-spacing:.18em;
        text-transform:uppercase; color:var(--muted); margin-top:1px; }
      .gfeed-capbadge{ font-family:var(--mono); font-size:8.5px; letter-spacing:.1em;
        text-transform:uppercase; color:var(--clr);
        border:1px solid rgba(52,214,164,.3); border-radius:3px; padding:3px 9px;
        background:rgba(52,214,164,.06); white-space:nowrap; }
      .gfeed-stream{ background:var(--panel); }
      .gfeed-item{ display:flex; gap:0; border-bottom:1px solid rgba(255,255,255,.03);
        animation:rise .45s both; }
      .gfeed-item:last-child{ border-bottom:none; }
      .gfeed-left{ width:96px; flex-shrink:0; display:flex; flex-direction:column; align-items:flex-start;
        padding:13px 10px 13px 16px; border-right:1px solid var(--line);
        background:rgba(0,0,0,.18); gap:5px; }
      .gfeed-cat{ font-family:var(--mono); font-size:7px; letter-spacing:.14em; text-transform:uppercase;
        padding:2px 6px; border-radius:2px; white-space:nowrap; font-weight:600;
        border:1px solid color-mix(in srgb, var(--gc,#8ab4ff) 40%, transparent);
        background:color-mix(in srgb, var(--gc,#8ab4ff) 8%, transparent);
        color:var(--gc,#8ab4ff); }
      .gfeed-time{ font-family:var(--mono); font-size:8px; color:var(--label); letter-spacing:.04em; }
      .gfeed-body{ flex:1; min-width:0; padding:13px 18px; }
      .gfeed-text{ font-size:12.5px; line-height:1.72; color:var(--text); }
      .gfeed-footer{ display:flex; align-items:center; gap:10px; padding:9px 18px;
        border-top:1px solid var(--line); background:var(--void);
        font-family:var(--mono); font-size:8.5px; color:var(--label); letter-spacing:.06em; }
      /* MCP pipeline flow */
      .mcp-wrap{ border:1px solid var(--line2); border-radius:6px; overflow:hidden; margin:10px 0; }
      .mcp-header{ padding:9px 16px; display:flex; align-items:center; gap:8px;
        background:rgba(95,208,224,.04); border-bottom:1px solid var(--line);
        font-family:var(--mono); font-size:8.5px; letter-spacing:.14em; color:var(--muted); }
      .mcp-header-title{ text-transform:uppercase; letter-spacing:.18em; }
      .mcp-header-count{ margin-left:auto; color:var(--label); }
      .mcp-flow{ display:flex; align-items:center; padding:16px 20px; background:var(--panel);
        overflow-x:auto; gap:0; }
      .mcp-node{ display:flex; flex-direction:column; align-items:center; gap:4px; flex-shrink:0; }
      .mcp-step{ font-family:var(--mono); font-size:7px; letter-spacing:.16em; color:var(--label);
        text-transform:uppercase; }
      .mcp-pill{ font-family:var(--mono); font-size:9px; padding:6px 11px; border-radius:4px;
        border:1px solid var(--line2); background:rgba(255,255,255,.04); color:var(--muted);
        white-space:nowrap; }
      .mcp-pill.active{ border-color:var(--accent); background:rgba(95,208,224,.1);
        color:var(--accent); box-shadow:0 0 14px -4px rgba(95,208,224,.45); }
      .mcp-desc{ font-family:var(--mono); font-size:7.5px; color:var(--label);
        text-align:center; letter-spacing:.04em; }
      .mcp-desc.active{ color:var(--accent); opacity:.75; }
      .mcp-arrow{ font-size:11px; color:var(--line2); padding:0 10px; flex-shrink:0;
        padding-bottom:16px; }
      /* enforcement signal heatmap */
      .hmap-wrap{ margin:10px 0; overflow-x:auto; border:1px solid var(--line2);
        border-radius:6px; overflow:hidden; }
      .hmap-table{ border-collapse:collapse; width:100%; }
      .hmap-th{ font-family:var(--mono); font-size:8px; letter-spacing:.1em; text-transform:uppercase;
        padding:8px 14px; text-align:center; color:var(--label); border-bottom:1px solid var(--line);
        background:var(--void); vertical-align:bottom; white-space:nowrap; }
      .hmap-th-label{ text-align:left; min-width:110px; }
      .hmap-th-ring{ color:var(--accent); }
      .hmap-col-badge{ font-family:var(--mono); font-size:7px; letter-spacing:.1em;
        border-radius:2px; padding:1px 5px; display:inline-block; margin-bottom:4px; }
      .hmap-col-badge.occ{ color:var(--esc); border:1px solid rgba(255,84,104,.3); }
      .hmap-col-badge.fincen{ color:var(--rev); border:1px solid rgba(247,183,51,.3); }
      .hmap-td-label{ font-family:var(--mono); font-size:9.5px; color:var(--muted);
        padding:8px 14px; white-space:nowrap; border-right:1px solid var(--line);
        border-bottom:1px solid rgba(255,255,255,.03); background:var(--void); }
      .hmap-td{ text-align:center; padding:8px 14px;
        border-bottom:1px solid rgba(255,255,255,.03); background:var(--panel); }
      .hmap-cell{ width:14px; height:14px; border-radius:3px; display:inline-block; }
      .hmap-cell.enf{ background:rgba(255,84,104,.28); border:1px solid rgba(255,84,104,.55); }
      .hmap-cell.ring{ background:rgba(95,208,224,.28); border:1px solid rgba(95,208,224,.55); }
      .hmap-cell.empty{ background:rgba(255,255,255,.02); border:1px solid var(--line); }
      .hmap-legend{ display:flex; gap:20px; padding:8px 14px; border-top:1px solid var(--line);
        background:var(--void); font-family:var(--mono); font-size:8.5px; color:var(--label);
        align-items:center; flex-wrap:wrap; }
      .hmap-leg-item{ display:flex; align-items:center; gap:7px; }
      /* buyer contact cards */
      .buyer-row{ display:flex; gap:9px; margin:10px 0; flex-wrap:wrap; }
      .buyer-card{ border:1px solid var(--line); border-radius:5px; background:var(--panel);
        padding:13px 15px; flex:1 1 150px; animation:rise .5s both; position:relative; overflow:hidden; }
      .buyer-card::before{ content:""; position:absolute; top:0; left:0; right:0; height:2px; background:var(--bc,var(--accent)); }
      .buyer-name{ font-family:var(--serif); font-size:18px; font-weight:600; color:var(--text); margin-bottom:3px; }
      .buyer-role{ font-family:var(--mono); font-size:9px; color:var(--muted); letter-spacing:.03em; }
      .buyer-co{ font-family:var(--mono); font-size:10px; color:var(--bc,var(--accent)); margin-top:5px; }
      .buyer-em{ font-family:var(--mono); font-size:8.5px; color:var(--label); margin-top:3px; }
      /* opener cards */
      .opener-card{ border:1px solid var(--line); border-radius:5px; background:var(--panel);
        padding:13px 16px; margin-bottom:9px; animation:rise .5s both; position:relative; overflow:hidden; }
      .opener-card::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:2px; background:var(--oc,var(--accent)); }
      .opener-meta{ display:flex; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap; }
      .opener-angle{ font-family:var(--mono); font-size:8px; letter-spacing:.12em; text-transform:uppercase;
        padding:2px 7px; border-radius:2px; border:1px solid var(--oc,var(--accent)); color:var(--oc,var(--accent)); }
      .opener-to{ font-family:var(--mono); font-size:10px; color:var(--text); font-weight:600; }
      .opener-text{ font-size:12px; color:var(--muted); line-height:1.62; font-style:italic; }

      @keyframes grow{ from{transform:scaleX(0); opacity:0} to{transform:scaleX(1); opacity:1} }
      @keyframes rise{ from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none} }
      @keyframes pulse{ 0%{box-shadow:0 0 0 0 rgba(52,214,164,.5)} 70%{box-shadow:0 0 0 7px rgba(52,214,164,0)} 100%{box-shadow:0 0 0 0 rgba(52,214,164,0)} }
    </style>
    """).strip(), unsafe_allow_html=True)


def _tile(label: str, value: str, sub: str = "", color: str | None = None,
          dot: str | None = None) -> str:
    cvar = f"--c:{color};" if color else ""
    dotspan = (f"<span style='width:6px;height:6px;border-radius:50%;"
               f"background:{dot};display:inline-block'></span>") if dot else ""
    valcls = "val c" if color else "val"
    subhtml = f"<div class='sub'>{sub}</div>" if sub else ""
    return (f"<div class='qkpi' style='{cvar}'>"
            f"<div class='lab'>{dotspan}{label}</div>"
            f"<div class='{valcls}'>{value}</div>{subhtml}</div>")


def kpi_row(r: dict) -> None:
    cn = r["counts"]
    rep = r["reporter"]
    exposure = r["detector"]["total_ring_exposure"]
    volume = r.get("total_volume") or 0
    ratio = (exposure / volume * 100) if volume else 0
    recon = ("<b>reconciled ✓</b>" if rep.get("reconciliation_ok") else "⚠ check")
    tiles = "".join([
        _tile("Accounts scanned", f"{cn['total']:,}", f"{cn['auto_cleared']:,} auto-cleared"),
        _tile("Ring escalated", f"{cn['escalate']:02d}", "confirmed mules",
              color="var(--esc)", dot="#ff5468"),
        _tile("Ring exposure", f"${exposure:,.0f}",
              f"{ratio:.1f}% of ${volume/1000:,.0f}k &middot; {recon}", color="var(--accent)"),
        _tile("Sent to human", f"{cn['review']:02d}", "calibrated abstention",
              color="var(--rev)", dot="#f7b733"),
        _tile("Decoys ignored", f"{cn['clear']:02d}", "device-trap cleared",
              color="var(--clr)", dot="#34d6a4"),
    ])
    st.markdown(f"<div class='qkpis'>{tiles}</div>", unsafe_allow_html=True)


# ── Bespoke "Case File" dossier (pure HTML/CSS, theme-native) ─────────────────
_DEC_CLS = {"ESCALATE": "esc", "REVIEW": "rev", "CLEAR": "clr"}
_DEC_VAR = {"ESCALATE": "var(--esc)", "REVIEW": "var(--rev)", "CLEAR": "var(--clr)"}
_DEC_SUB = {"ESCALATE": "CONFIRMED MULE", "REVIEW": "TO HUMAN REVIEW", "CLEAR": "CLEARED"}
_SIG_FEATS = ["under_threshold", "fresh_cohort", "zero_merchant", "pure_sink",
              "automation", "relay_depth", "device_shared"]


def _pct(x: float) -> float:
    return max(0.0, min(100.0, float(x) * 100.0))


def _dossier_header(c: dict) -> str:
    act = c.get("action", "")
    sig = c.get("signals") or {}
    usd = sig.get("_transfer_usd", 0.0) or 0.0
    ntr = sig.get("_n_transfers", 0) or 0
    return (
        "<div class='dh'>"
        f"<div class='dh-id'>{c['account']}</div>"
        "<div class='dh-meta'>"
        f"<span class='ln'>ROLE <b>{(c.get('role') or '—').upper()}</b></span>"
        f"<span class='ln'>TYPOLOGY <b>{c.get('typology') or '—'}</b></span>"
        f"<span class='ln'>$ MOVED <b>${usd:,.0f}</b> &nbsp;·&nbsp; {ntr} transfers</span>"
        "</div>"
        f"<div class='stamp {_DEC_CLS.get(act,'clr')}'>{act}"
        f"<small>{_DEC_SUB.get(act,'')}</small></div>"
        "</div>")


def _rail_html(c: dict, tau: float) -> str:
    p = float(c.get("p_mule") or 0.0)
    lo, hi = (c.get("credible_interval") or [p, p])
    cvar = _DEC_VAR.get(c.get("action", ""), "var(--accent)")
    lp, hp, pp, tp = _pct(lo), _pct(hi), _pct(p), _pct(tau)
    plabel = max(6.0, min(94.0, pp))
    return (
        f"<div class='rail' style='--c:{cvar}'>"
        "<div class='track'></div>"
        f"<div class='ci' style='left:{lp:.2f}%; width:{max(hp-lp,0.5):.2f}%'></div>"
        f"<div class='tau' style='left:{tp:.2f}%'><span>τ {tau:.2f}</span></div>"
        f"<div class='pt' style='left:{pp:.2f}%'></div>"
        f"<div class='pv' style='left:{plabel:.2f}%'>{p:.3f}</div>"
        "<div class='scale'><span>0</span><span>.25</span><span>.50</span>"
        "<span>.75</span><span>1.0</span></div>"
        "</div>")


def _ledger_html(c: dict) -> str:
    esc = float(c.get("E_loss_escalate") or 0.0)
    clr = float(c.get("E_loss_clear") or 0.0)
    evpi = float(c.get("EVPI") or 0.0)
    action = c.get("action", "")
    mx = max(esc, clr, 1e-9)
    out = ""
    for label, val, act, cv in [("E[loss | escalate]", esc, "ESCALATE", "var(--esc)"),
                                 ("E[loss | clear]", clr, "CLEAR", "var(--clr)")]:
        win = act == action
        pick = "<span class='pick'>ARGMIN</span>" if win else ""
        out += (f"<div class='lr{' win' if win else ''}' style='--c:{cv}'>"
                f"<span class='lk'>{label}</span>"
                f"<span class='lbar'><i style='width:{val/mx*100:.1f}%'></i></span>"
                f"<span class='lv'>${val:,.2f} {pick}</span></div>")
    out += (f"<div class='foot'><span>EVPI&nbsp; <b>${evpi:,.2f}</b></span>"
            f"<span>Decision&nbsp; <b>{action}</b></span></div>")
    return f"<div class='ledger'>{out}</div>"


def _sigbars_html(c: dict) -> str:
    contrib = dict(c.get("signal_contributions") or {})
    bias = contrib.pop("bias", None)
    items = sorted(contrib.items(), key=lambda kv: -abs(kv[1]))
    if bias is not None:
        items = [("prior (bias)", bias)] + items
    mx = (max([abs(v) for _, v in items]) if items else 1.0) or 1.0
    rows = ""
    for name, v in items:
        cls = "toward" if v >= 0 else "away"
        w = abs(v) / mx * 50.0
        rows += (f"<div class='sr'><span class='sk'>{name.replace('_',' ')}</span>"
                 f"<span class='sb'><span class='mid'></span>"
                 f"<i class='{cls}' style='width:{w:.1f}%'></i></span>"
                 f"<span class='sv {cls}'>{v:+.2f}</span></div>")
    axis = "<div class='axis'><span>&larr; clears</span><span>flags &rarr;</span></div>"
    return f"<div class='sig'>{rows}{axis}</div>"


def _chips_html(c: dict) -> str:
    sig = c.get("signals") or {}
    out = ""
    for f in _SIG_FEATS:
        on = bool(sig.get(f))
        out += (f"<span class='chip{'' if on else ' off'}'>"
                f"{'●' if on else '○'}&nbsp;{f.replace('_',' ')}</span>")
    return f"<div class='chips'>{out}</div>"


def dossier_html(c: dict, tau: float) -> str:
    reason = (c.get("action_reason") or "").replace("→", "<span class='em'>→</span>")
    return (
        "<div class='dossier'>"
        + _dossier_header(c)
        + "<div class='dgrid'>"
          "<div class='dcol'>"
          "<div class='dblk'><div class='h'>Posterior &mdash; P(mule) · 94% credible interval</div>"
          + _rail_html(c, tau) + "</div>"
          "<div class='dblk'><div class='h'>Expected-loss ledger &mdash; argmin decides</div>"
          + _ledger_html(c) + "</div>"
          "</div>"
          "<div class='dcol'>"
          "<div class='dblk'><div class='h'>Why &mdash; signed signal contributions (logit)</div>"
          + _sigbars_html(c) + "</div>"
          "<div class='dblk'><div class='h'>Signals fired</div>"
          + _chips_html(c) + "</div>"
          "</div>"
          "</div>"
        + "<div class='dcol' style='border-top:1px solid var(--line)'>"
          "<div class='dblk'><div class='h'>Decision log &mdash; the reason, in full</div>"
          f"<div class='dlog'>{reason}</div></div></div>"
        + "</div>")


# ── Bespoke "Agent Relay" — the Case node accreting through Cognee (criterion 2) ─
_AGENTS = [
    ("01", "Detector", "FIND", "#5fd0e0",
     ["role", "signals", "is_candidate", "decoy_suspect", "dist_stats", "detect_reason"]),
    ("02", "Estimator", "RANK", "#8ab4ff",
     ["p_mule", "credible_interval", "signal_contributions"]),
    ("03", "Adjudicator", "ACT", "#f7b733",
     ["action", "E_loss_escalate", "E_loss_clear", "EVPI", "quorum", "decisive_signals"]),
    ("04", "Domain Expert", "GROUND", "#b48aff", None),  # writes MarketContext (separate Cognee entity)
    ("05", "Reporter", "EXPLAIN", "#34d6a4",
     ["memo_ref", "typology", "dollar_contribution", "closing_rule"]),
]
_N_MC_FIELDS = 5  # MarketContext fields surfaced in the relay view


def _fmt_val(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:,.3f}" if abs(v) < 100 else f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, str):
        return (v[:46] + "…") if len(v) > 47 else v
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, (int, float)) for x in v) and len(v) <= 3:
            return "[" + ", ".join(f"{x:.3f}" if isinstance(x, float) else str(x) for x in v) + "]"
        return f"[{len(v)} items]"
    if isinstance(v, dict):
        fired = sum(1 for k, val in v.items() if not str(k).startswith("_") and val)
        keys = [k for k in v if not str(k).startswith("_")]
        if len(keys) <= 3:
            return "{" + " · ".join(keys) + "}"
        extra = f" · {fired} set" if fired else ""
        return f"{{{len(keys)} fields{extra}}}"
    return str(v)[:46]


def relay_html(c: dict, mc: dict | None = None) -> str:
    mc = mc or {}
    counts = [(len(fields) if fields is not None else _N_MC_FIELDS)
              for *_, fields in _AGENTS]
    total = sum(counts) or 1
    cum = 0  # tracks Case fields accumulated so far
    # accumulator bar
    segs = ""
    for (num, name, role, color, fields), n in zip(_AGENTS, counts):
        w = n / total * 100
        if fields is None:  # Domain Expert → MarketContext branch
            segs += (f"<span style='--c:{color}; background:{_rgba(color,0.08)}; "
                     f"width:{w:.1f}%; border-style:dashed; opacity:.75'>"
                     f"+{n}<small>MktCtx</small></span>")
        else:
            segs += (f"<span style='--c:{color}; background:{_rgba(color,0.16)}; width:{w:.1f}%'>"
                     f"+{n}<small>{name}</small></span>")
    case_fields = sum(len(f) for _, _, _, _, f in _AGENTS if f is not None)
    accum = (
        "<div class='accum'>"
        f"<div class='accum-h'>Five-agent relay · <b>Case::{c['account']}</b> · "
        f"Case + MarketContext entities in Cognee</div>"
        f"<div class='accbar'>{segs}</div>"
        f"<div class='accum-f'>Detector opens the Case; Domain Expert queries the "
        f"<span class='geodo-brand'>geodo.ai MCP</span>, then <b>branches</b> to write "
        f"<b>MarketContext</b> (a separate Cognee entity — geodo.ai-grounded); Reporter reads "
        f"both — Case accretes <b>{case_fields} fields</b>, MarketContext adds "
        f"<b>{_N_MC_FIELDS} more</b> from <span class='geodo-brand'>geodo.ai</span>.</div>"
        "</div>")
    # vertical relay of stages
    stages = ""
    for (num, name, role, color, fields) in _AGENTS:
        reads_case = cum
        if fields is None:
            # Domain Expert — reads decisive_signals from Case, writes MarketContext
            _de = {
                "segment": (mc.get("segment") or "")[:58] or "—",
                "buyer_thesis": (mc.get("buyer_thesis") or "")[:58] or "—",
                "top_intent": (((mc.get("intent_signals") or [{}])[0]).get("institution", "—")),
                "sar_penalty_averted": (
                    f"${mc['roi']['sar_penalty_floor_averted_usd']:,.0f}"
                    if (mc.get("roi") or {}).get("sar_penalty_floor_averted_usd") else "—"),
                "research_grounded": "✓" if mc.get("research_grounded") else "—",
            }
            rows = "".join(
                f"<div class='frow'><span class='fk'>{fname}</span>"
                f"<span class='fv'>{_fmt_val(fval)}</span></div>"
                for fname, fval in _de.items())
            n_written = len(_de)
            stages += (
                f"<div class='stage' style='--a:{color}'>"
                f"<div class='spine'><div class='snode'>{num}</div></div>"
                "<div class='scard' style='border-style:dashed'>"
                "<div class='shead'>"
                f"<div><span class='sname'>{name}</span><span class='srole'>{role}</span></div>"
                f"<div class='sio'><span>reads {reads_case} [Case]</span>"
                f"<span class='w'>writes +{n_written} [MarketCtx]</span></div>"
                "</div>"
                f"<div style='font-family:var(--mono);font-size:8.5px;letter-spacing:.12em;"
                f"color:{color};margin-bottom:10px;text-transform:uppercase;padding:3px 8px;"
                f"border:1px dashed {color}40;border-radius:3px;display:inline-block'>"
                f"Cognee entity: MarketContext (<span class='geodo-brand'>geodo.ai</span>-grounded · separate from Case)</div>"
                f"<div class='fields'>{rows}</div>"
                f"<div class='handoff'>Writes <b>MarketContext</b> to Cognee &mdash; "
                f"Reporter reads Case + this <span class='geodo-brand'>geodo.ai</span>-grounded entity</div>"
                "</div></div>")
        else:
            rows = "".join(
                f"<div class='frow'><span class='fk'>{f}</span>"
                f"<span class='fv'>{_fmt_val(c.get(f))}</span></div>"
                for f in fields)
            cum += len(fields)
            extra_reads = (f" + {_N_MC_FIELDS} [MarketCtx]"
                           if name == "Reporter" else "")
            stages += (
                f"<div class='stage' style='--a:{color}'>"
                f"<div class='spine'><div class='snode'>{num}</div></div>"
                "<div class='scard'>"
                "<div class='shead'>"
                f"<div><span class='sname'>{name}</span><span class='srole'>{role}</span></div>"
                f"<div class='sio'><span>reads {reads_case}{extra_reads}</span>"
                f"<span class='w'>writes +{len(fields)}</span></div>"
                "</div>"
                f"<div class='fields'>{rows}</div>"
                f"<div class='handoff'>Handoff via Cognee &mdash; Case now carries "
                f"<b>{cum} fields</b></div>"
                "</div></div>")
    return f"<div class='relay'>{accum}<div class='stages'>{stages}</div></div>"


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Geo / Market rendering helpers ────────────────────────────────────────────

def _conn_badge_html(conn: dict | None) -> str:
    if conn and conn.get("connected"):
        bits = []
        if conn.get("unlimited"):
            bits.append("credits: unlimited")
        if conn.get("source"):
            bits.append(f"plan: {conn['source']}")
        if conn.get("user_id"):
            bits.append(f"acct …{str(conn['user_id'])[-6:]}")
        details = " · ".join(bits)
        return (f"<div class='geo-conn'><span class='cdot on'></span>"
                f"<b><span class='geodo-brand'>geodo.ai</span> MCP connected</b>&nbsp;—&nbsp;live "
                f"<code style='background:rgba(255,255,255,.06);padding:1px 5px;border-radius:3px'>"
                f"geo_get_account_state</code>"
                f"<span style='margin-left:auto;color:var(--label)'>{details}</span></div>")
    return ("<div class='geo-conn'><span class='cdot off'></span>"
            "<span><span class='geodo-brand'>geodo.ai</span>: offline"
            " &nbsp;·&nbsp; rendering from committed cache snapshot</span></div>")


def enforcement_timeline_html(signals: list) -> str:
    if not signals:
        return "<p style='color:var(--muted);font-family:var(--mono);font-size:11px'>No matched enforcement actions.</p>"
    cards = ""
    for s in signals:
        sid = s.get("id", "")
        if "occ" in sid:
            badge, ec = "OCC", "#5fd0e0"
        elif "fincen" in sid:
            badge, ec = "FinCEN", "#f7b733"
        else:
            badge, ec = "REG", "#8ab4ff"
        sigs = "".join(f"<span class='enf-sig'>{t.replace('_',' ')}</span>"
                       for t in s.get("signal_tags", []))
        action = s.get("action", "")
        url = s.get("url", "")
        inst_html = (f"<a href='{url}' target='_blank' style='color:var(--text);text-decoration:none'>"
                     f"{s.get('institution','')}</a>" if url else s.get("institution", ""))
        cards += (
            f"<div class='enf-card' style='--ec:{ec}'>"
            f"<div class='enf-top'>"
            f"<span class='enf-badge' style='color:{ec};border:1px solid {ec}30;background:{ec}12'>{badge}</span>"
            f"<span class='enf-inst'>{inst_html}</span>"
            f"<span class='enf-date'>{s.get('date','')}</span>"
            f"</div>"
            f"<div class='enf-action'>{action[:240]}</div>"
            f"<div class='enf-signals'>{sigs}</div>"
            f"</div>")
    return f"<div class='enf-wrap'><div class='enf-track'>{cards}</div></div>"


def persona_grid_html(personas: list) -> str:
    COLORS = ["#5fd0e0", "#8ab4ff", "#f7b733", "#b48aff"]
    cards = ""
    for i, p in enumerate(personas or []):
        color = COLORS[i % len(COLORS)]
        pains = "".join(f"<span class='persona-pain'>{pain}</span>"
                        for pain in (p.get("pains") or []))
        cards += (
            f"<div class='persona-card' style='--pc:{color}'>"
            f"<div class='persona-title'>{p.get('title','')}</div>"
            f"<div class='persona-pains'>{pains}</div>"
            f"<div class='persona-trigger'>Trigger: <b>{p.get('trigger','')}</b></div>"
            "</div>")
    return f"<div class='persona-grid'>{cards}</div>"


def messaging_angles_html(angles: dict) -> str:
    COLORS = {"bsa_officer": "var(--esc)", "aml_analyst": "var(--accent)", "executive": "var(--rev)"}
    LABELS = {"bsa_officer": "BSA Officer", "aml_analyst": "AML Analyst", "executive": "Executive / CCO"}
    cards = ""
    for key, data in (angles or {}).items():
        color = COLORS.get(key, "var(--line2)")
        label = LABELS.get(key, key)
        angle = data.get("angle", "")
        if "—" in angle:
            head, rest = angle.split("—", 1)
            angle_html = f"<b>{head.strip()} —</b>{rest}"
        else:
            angle_html = angle
        cards += (
            f"<div class='angle-card' style='--ac:{color}'>"
            f"<div class='angle-persona'>{label}</div>"
            f"<div class='angle-text'>{angle_html}</div>"
            "</div>")
    return f"<div class='angle-grid'>{cards}</div>"


def research_feed_html(excerpt: str, src_line: str, captured_on: str = "") -> str:
    """Render the geodo.ai Intelligence Feed from a markdown research excerpt."""
    items = parse_research_feed(excerpt or "")
    if not items:
        return ""
    cap_label = f"✓ CAPTURED {captured_on}" if captured_on else "✓ CAPTURED RECENTLY"
    rows = ""
    for i, item in enumerate(items):
        # T+0:00, T+0:09, T+0:18 … gives a "live capture" timestamp feel
        secs = i * 9
        ts = f"T+0:{secs:02d}"
        cat = item["category"]
        color = item["color"]
        text = item["text"]
        delay = item["delay"]
        rows += (
            f"<div class='gfeed-item' style='animation-delay:{delay}s'>"
            f"<div class='gfeed-left'>"
            f"<span class='gfeed-cat' style='--gc:{color}'>{cat}</span>"
            f"<span class='gfeed-time'>{ts}</span>"
            f"</div>"
            f"<div class='gfeed-body'><div class='gfeed-text'>{text}</div></div>"
            f"</div>"
        )
    return (
        "<div class='gfeed-wrap'>"
        "<div class='gfeed-header'>"
        "<div class='gfeed-brand'>"
        "<span class='cdot on'></span>"
        f"<div><div class='gfeed-title'>"
        f"<span class='geodo-brand'>geodo.ai</span> Intelligence Feed</div>"
        f"<div class='gfeed-sublabel'>GTM Advisor · This Segment</div></div>"
        "</div>"
        f"<span class='gfeed-capbadge'>{cap_label}</span>"
        "</div>"
        f"<div class='gfeed-stream'>{rows}</div>"
        f"<div class='gfeed-footer'><span class='geodo-brand'>geodo.ai</span>"
        f"&nbsp;GTM Researcher&nbsp;·&nbsp;{src_line}</div>"
        "</div>"
    )


_MCP_META: dict[str, tuple[str, str, bool]] = {
    "geo_list_documents":   ("geo_list_documents",   "document inventory", False),
    "geo_add_document":     ("geo_add_document",     "brief ingested",     False),
    "geo_search_contacts":  ("geo_search_contacts",  "buyers sourced",     True),
    "geo_propose_campaign": ("geo_propose_campaign", "outreach designed",  False),
    "geo_compile_flow_spec":("geo_compile_flow_spec","flow compiled",      False),
}


def mcp_flow_html(tools: list) -> str:
    if not tools:
        return ""
    nodes = ""
    for i, tool in enumerate(tools):
        _, desc, active = _MCP_META.get(tool, (tool, "", False))
        pill_cls = "mcp-pill active" if active else "mcp-pill"
        desc_cls = "mcp-desc active" if active else "mcp-desc"
        nodes += (
            f"<div class='mcp-node'>"
            f"<div class='mcp-step'>step {i + 1}</div>"
            f"<div class='{pill_cls}'>{tool}</div>"
            f"<div class='{desc_cls}'>{desc}</div>"
            f"</div>"
        )
        if i < len(tools) - 1:
            nodes += "<div class='mcp-arrow'>→</div>"
    n = len(tools)
    return (
        "<div class='mcp-wrap'>"
        "<div class='mcp-header'>"
        f"<span class='geodo-brand'>geodo.ai</span>"
        f"<span class='mcp-header-title'>MCP calls · this run</span>"
        f"<span class='mcp-header-count'>{n} tool{'s' if n != 1 else ''} invoked</span>"
        "</div>"
        f"<div class='mcp-flow'>{nodes}</div>"
        "</div>"
    )


_TAG_LABELS: dict[str, str] = {
    "under_threshold": "Sub-threshold",
    "zero_merchant":   "No Merchant",
    "pure_sink":       "Pure Sink",
    "fresh_cohort":    "Fresh Account",
    "relay_depth":     "Relay Depth",
    "automation":      "Automation",
    "device_shared":   "Shared Device",
}



def twin_html(packet: dict) -> str:
    ll = packet.get("learn_loop") or {}
    changed = ll.get("research_changed", False)
    badge_cls = "learned" if changed else "nochg"
    badge_text = "Research updated ✓" if changed else "No change detected"
    before = (ll.get("research_before_excerpt") or "").strip()
    after = (ll.get("research_after_excerpt") or "").strip()
    docs_b = ll.get("docs_before", "?")
    docs_a = ll.get("docs_after", "?")
    added = ll.get("docs_added", 0)
    brief_ok = ll.get("brief_present", False)
    doc_name = (packet.get("document") or {}).get("file_name", "—")
    probe = ("For a US community-bank BSA/AML team, what coordinated money-laundering pattern "
             "is hardest for rules-based monitoring to catch, and what recent peer enforcement "
             "makes fixing it urgent?")
    brief_badge = ("<b style='color:var(--clr)'>✓ present</b>"
                   if brief_ok else "<span style='color:var(--label)'>—</span>")
    return (
        "<div class='twin-wrap'>"
        "<div class='twin-head'>"
        f"<span class='twin-title'><span class='geodo-brand'>geodo.ai</span> Digital Twin</span>"
        f"<span class='twin-badge {badge_cls}'>{badge_text}</span>"
        f"<span style='font-family:var(--mono);font-size:10px;color:var(--muted);margin-left:auto'>"
        f"Taught: <b style='color:var(--text)'>{doc_name}</b></span>"
        "</div>"
        f"<div class='twin-probe'><b>Probe →</b> {probe}</div>"
        "<div class='twin-cols'>"
        "<div class='twin-col'>"
        "<div class='twin-lab' style='color:var(--label)'>"
        "<span class='twin-dot' style='background:var(--label)'></span>Before teaching</div>"
        f"<div class='twin-text bef'>{before}</div>"
        "</div>"
        "<div class='twin-col'>"
        "<div class='twin-lab' style='color:var(--clr)'>"
        "<span class='twin-dot' style='background:var(--clr)'></span>After teaching</div>"
        f"<div class='twin-text aft'>{after}</div>"
        "</div>"
        "</div>"
        "<div class='twin-foot'>"
        f"<span>Documents</span><b>{docs_b}</b>"
        f"<span class='tarrow'>→</span><b>{docs_a}</b>"
        f"<span class='tdelta'>+{added} added</span>"
        f"<span style='margin-left:auto'>Brief present: {brief_badge}</span>"
        "</div>"
        "</div>")


def buyer_contact_cards_html(contacts: list) -> str:
    def _color(title: str) -> str:
        t = title.lower()
        if "bsa" in t:
            return "var(--esc)"
        if "analyst" in t or "aml" in t:
            return "var(--accent)"
        return "var(--rev)"

    cards = ""
    for contact in (contacts or []):
        color = _color(contact.get("title", ""))
        email_html = ("<span style='color:var(--clr)'>✓ email on file</span>"
                      if contact.get("has_email")
                      else "<span style='color:var(--label)'>no email</span>")
        cards += (
            f"<div class='buyer-card' style='--bc:{color}'>"
            f"<div class='buyer-name'>{contact.get('first_name','')}</div>"
            f"<div class='buyer-role'>{contact.get('title','')}</div>"
            f"<div class='buyer-co'>{contact.get('company','')}</div>"
            f"<div class='buyer-em'>{email_html}</div>"
            "</div>")
    return f"<div class='buyer-row'>{cards}</div>"


def opener_cards_html(openers: list) -> str:
    COLORS = {"bsa_officer": "var(--esc)", "aml_analyst": "var(--accent)", "executive": "var(--rev)"}
    cards = ""
    for o in (openers or []):
        color = COLORS.get(o.get("persona_angle", ""), "var(--line2)")
        angle_label = (o.get("persona_angle") or "").replace("_", " ").upper()
        to = o.get("to", "")
        text = (o.get("opener") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cards += (
            f"<div class='opener-card' style='--oc:{color}'>"
            f"<div class='opener-meta'>"
            f"<span class='opener-angle'>{angle_label}</span>"
            f"<span class='opener-to'>{to}</span>"
            f"</div>"
            f"<div class='opener-text'>&ldquo;{text}&rdquo;</div>"
            "</div>")
    return cards


def roi_html(roi: dict) -> str:
    sar = roi.get("sar_penalty_floor_averted_usd", 0)
    exp = roi.get("ring_exposure_usd", 0)
    hrs = roi.get("analyst_hours_reclaimed", 0)
    cap = roi.get("capacity_reclaimed_usd", [0, 0])
    rate = roi.get("analyst_rate_usd_per_hr", [50, 80])
    basis = roi.get("basis", "")
    tiles = "".join([
        _tile("Penalty floor averted", f"${sar:,.0f}", "31 CFR §1020.320 floor \xb7 9 SARs",
              "var(--esc)"),
        _tile("Ring flow flagged", f"${exp:,.0f}", "Detector-reconstructed ring", "var(--accent)"),
        _tile("Analyst hours reclaimed", f"{hrs:.0f} hrs",
              f"${cap[0]:,.0f}–${cap[1]:,.0f} @ geodo.ai rate ${rate[0]}–${rate[1]}/hr",
              "var(--clr)"),
    ])
    basis_html = (f"<div style='font-family:var(--mono);font-size:9px;color:var(--label);"
                  f"margin-top:6px;line-height:1.6'>{basis}</div>") if basis else ""
    return (f"<div class='qkpis' style='grid-template-columns:repeat(3,1fr)'>{tiles}</div>"
            f"{basis_html}")


def _run_pipeline(csv_path: str) -> dict:
    import duckdb
    import cognee_client as cognee
    import geo_client
    import geodo_market
    import geodo_research
    import gtm
    from agents import domain_expert, investigator, narrator, ranker, scout
    from db import queries

    con = duckdb.connect()
    queries.load_csv(con, csv_path)
    detector = scout.run(con)
    ranker.run()
    adjudicator = investigator.run(con, detector_result=detector)
    domain_expert.run(detector_result=detector)
    market_context = cognee.read_market_context(domain_expert.RING_REF)
    reporter = narrator.run(detector_result=detector)
    try:
        gtm_packet = gtm.run(live=False)
    except Exception:  # noqa: BLE001 — GTM is an add-on, never blocks the pipeline
        gtm_packet = None
    geo_connection = geo_client.connection_proof()
    cases = cognee.read_cases(candidates_only=True)
    n_total = detector["dist_stats"].get("n_accounts_total", 0)
    ring_accounts = {c["account"] for c in cases if c.get("action") == "ESCALATE"}
    return {
        "detector": detector,
        "adjudicator": adjudicator,
        "reporter": reporter,
        "geodo": geodo_research.summary(),
        "geo_market": geodo_market.summary(),
        "market_context": market_context,
        "gtm": gtm_packet,
        "geo_connection": geo_connection,
        "cases": cases,
        "dist_stats": detector["dist_stats"],
        "total_volume": float((con.execute("SELECT SUM(amount) FROM transactions").fetchone() or (0,))[0] or 0),
        "total_txns": int((con.execute("SELECT COUNT(*) FROM transactions").fetchone() or (0,))[0] or 0),
        # kept open for the interactive visuals (graph + signature charts)
        "con": con,
        "graph": build_graph(con, detector, cases),
        "counts": funnel_counts(cases, n_total),
        "ring_accounts": sorted(ring_accounts),
        "chart_data": compute_chart_data(con, ring_accounts),
        # The real Cognee graph is built on demand (Pipeline view) — cognify()
        "cognee": st.session_state.get("cognee_status", {"used": False, "reason": "not built yet"}),
    }


def _posterior_plot(case: dict, tau: float):
    p = case.get("p_mule", 0.0)
    lo, hi = case.get("credible_interval", [0.0, 0.0])
    fig, ax = plt.subplots(figsize=(6, 1.5))
    ax.hlines(0, 0, 1, color="#ddd", lw=1)
    ax.fill_betweenx([-0.4, 0.4], lo, hi, color="#90caf9", alpha=0.6,
                     label="94% credible interval")
    ax.vlines(p, -0.4, 0.4, color="#1565C0", lw=2, label=f"p_mule = {p:.3f}")
    ax.vlines(tau, -0.6, 0.6, color="#d32f2f", lw=1.5, ls="--", label=f"τ = {tau:.2f}")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.8, 0.8)
    ax.set_yticks([])
    ax.set_xlabel("P(account is a mule)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.5), ncol=3, fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def _subgraph(edges, cases_by_acct):
    import math
    nodes = sorted({e["sender"] for e in edges} | {e["receiver"] for e in edges})
    ang = 2 * math.pi / max(len(nodes), 1)
    pos = {n: (math.cos(i * ang), math.sin(i * ang)) for i, n in enumerate(nodes)}
    ex, ey = [], []
    for e in edges:
        if e["sender"] in pos and e["receiver"] in pos:
            x0, y0 = pos[e["sender"]]
            x1, y1 = pos[e["receiver"]]
            ex += [x0, x1, None]
            ey += [y0, y1, None]
    edge_tr = go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=1.5, color="#888"),
                         hoverinfo="none")
    colors = [ROLE_COLOR.get(str(cases_by_acct.get(n, {}).get("role", "none")), "#546e7a")
              for n in nodes]
    node_tr = go.Scatter(
        x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
        mode="markers+text", text=nodes, textposition="top center",
        marker=dict(size=26, color=colors, line=dict(width=1, color="white")),
        hovertext=[f"{n} — {cases_by_acct.get(n, {}).get('role','')}" for n in nodes],
        hoverinfo="text")
    fig = go.Figure([edge_tr, node_tr], layout=go.Layout(
        showlegend=False, hovermode="closest", height=460,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="#0a0c11", paper_bgcolor="#0a0c11",
        font=dict(color="#e7ebf3", family="IBM Plex Mono, monospace")))
    return fig


# ── Header ────────────────────────────────────────────────────────────────────
inject_theme()
_recon_ok = (st.session_state.result or {}).get("reporter", {}).get("reconciliation_ok")
_status = "RECONCILED" if _recon_ok else "STANDBY"
st.markdown(
    "<div class='qmast'>"
    "  <div class='qmast-top'>"
    "    <span class='qmark'>QU<b>O</b>RUM</span>"
    "    <span class='qeyebrow'>Calibrated&nbsp;AML&nbsp;Triage</span>"
    "    <div class='qmast-meta'>"
    "      <div>Case File<b>QRM-2026-RING-001</b></div>"
    "      <div>Dataset<b>Crestline · 90d</b></div>"
    f"      <div>Status<b><span class='qlive'></span>{_status}</b></div>"
    "    </div>"
    "  </div>"
    "  <div class='qmast-sub'>Surfaces the layering ring hiding below every alert "
    "threshold, <i>refuses to guess</i> on the one genuinely ambiguous account, "
    "<i>ignores the planted decoy</i>, and shows the math behind every call.</div>"
    "</div>",
    unsafe_allow_html=True)

if st.session_state.result is not None:
    kpi_row(st.session_state.result)

tabs = st.tabs(["📋 Queue", "🌐 Constellation", "🔎 Case detail",
                "🧬 Signatures", "📄 Memo", "🎯 Market", "🧠 Pipeline"])

# ══════════════════════════════════════════════════════════════════════════════
# Screen 1 — Queue
# ══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    if st.session_state.result is None:
        st.markdown("#### Load the Crestline transaction file")

        default_csv = Path(__file__).resolve().parents[1] / "data" / "track02_fraud_watch.csv"

        def _run_on(path: str) -> None:
            prog = st.progress(0, text="Detector → Estimator → Adjudicator → Reporter")
            t0 = time.time()
            for pct, label in [(25, "Detector: roles + signals"),
                               (50, "Estimator: calibrated probabilities"),
                               (75, "Adjudicator: expected-loss decisions"),
                               (95, "Reporter: SAR memo")]:
                prog.progress(pct, text=label)
                time.sleep(0.05)
            st.session_state.result = _run_pipeline(path)
            prog.progress(100, text=f"Done in {time.time()-t0:.1f}s")
            st.rerun()

        if default_csv.exists():
            if st.button(f"▶ Run on competition file — {default_csv.name}",
                         type="primary"):
                _run_on(str(default_csv))
            st.caption("…or upload your own:")

        uploaded = st.file_uploader("Drop the 5,000-transaction CSV", type=["csv"],
                                    label_visibility="collapsed")
        if uploaded is not None:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name
            _run_on(tmp_path)
    else:
        r = st.session_state.result
        adj = r["adjudicator"]
        ds = r["dist_stats"]
        n_total = ds.get("n_accounts_total", 0)
        tcol1, tcol2 = st.columns([3, 1])
        tcol1.markdown("#### Review queue &nbsp;·&nbsp; "
                       "the accounts the pipeline surfaced, ranked by mule probability")
        if r.get("prebuilt"):
            tcol1.caption(f"🔭 Pre-built demo · {r.get('built_at','')}")
        with tcol2:
            if st.button("↻ Run a different file", use_container_width=True):
                st.session_state.result = None
                st.session_state.force_upload = True
                st.rerun()

        st.plotly_chart(charts.posterior_strip(r["cases"], adj["tau"]),
                        use_container_width=True)

        show_cleared = st.toggle("Show cleared accounts (decoys)", value=True)
        cases = sorted(r["cases"], key=lambda c: c.get("p_mule", 0), reverse=True)
        rows = []
        for c in cases:
            act = c.get("action", "")
            if act == "CLEAR" and not show_cleared:
                continue
            lo, hi = c.get("credible_interval", [0, 0])
            rows.append({
                "Account": c["account"],
                "Decision": f"{ACTION_EMOJI.get(act,'')} {act}",
                "Role": (c.get("role") or "").upper(),
                "P(mule)": round(c.get("p_mule", 0), 3),
                "Uncertainty": f"[{lo:.3f} – {hi:.3f}]",
                "$ moved": round((c.get("signals") or {}).get("_transfer_usd", 0.0), 0),
                "Why (decisive signals)": ", ".join(c.get("decisive_signals") or [])
                    or (c.get("detect_reason", "")[:60]),
            })
        df = pd.DataFrame(rows)
        event = st.dataframe(
            df, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "P(mule)": st.column_config.ProgressColumn(
                    "P(mule)", min_value=0.0, max_value=1.0, format="%.3f"),
                "$ moved": st.column_config.NumberColumn("$ moved", format="$%d"),
                "Decision": st.column_config.TextColumn("Decision", width="small"),
            })
        selection = event.get("selection") if event else None
        sel_rows = selection.get("rows", []) if selection else []
        if sel_rows:
            st.session_state.selected = df.iloc[sel_rows[0]]["Account"]
            st.info(f"Selected **{st.session_state.selected}** → open the "
                    f"**🔎 Case detail** tab for the full breakdown.")
        st.caption(f"The {n_total - len(cases)} accounts with no firing signal were "
                   f"auto-cleared by the Detector and never surfaced. "
                   f"Click a row to inspect it.")

# ══════════════════════════════════════════════════════════════════════════════
# Screen 1b — Constellation (the interactive 3D drag-and-drop ring graph)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cn = r["counts"]
        st.markdown("<div class='qsec'>The money-laundering constellation · "
                    "<span class='num'>opens full-screen in its own tab</span></div>",
                    unsafe_allow_html=True)

        # Write the standalone graph into the served static dir (once per session),
        # from the live graph so it always matches the current design.
        static_path = Path(__file__).resolve().parent / "static" / "quorum_constellation.html"
        if not st.session_state.get("_constellation_written"):
            static_path.parent.mkdir(exist_ok=True)
            html = ring_graph.build_html(r["graph"], height=860)
            # Only swap in a *complete* file. If the vendored 3D libs failed to read
            # (e.g. OneDrive evicted them to cloud-only), keep the last good served
            # copy instead of clobbering it with a broken one. Atomic swap via temp.
            if "ForceGraph3D" in html and len(html) > 1_000_000:
                tmp = static_path.with_name("quorum_constellation.html.tmp")
                tmp.write_text(html, encoding="utf-8")
                tmp.replace(static_path)
            st.session_state["_constellation_written"] = True

        st.markdown(
            "<a class='launch' href='app/static/quorum_constellation.html' "
            "target='_blank' rel='noopener'>"
            "<svg class='launch-viz' viewBox='0 0 104 74' fill='none'>"
            "<line class='ln r' x1='30' y1='24' x2='54' y2='16'/>"
            "<line class='ln r' x1='54' y1='16' x2='74' y2='30'/>"
            "<line class='ln r' x1='54' y1='16' x2='50' y2='44'/>"
            "<line class='ln' x1='30' y1='24' x2='20' y2='50'/>"
            "<line class='ln' x1='74' y1='30' x2='84' y2='54'/>"
            "<line class='ln' x1='50' y1='44' x2='40' y2='62'/>"
            "<circle class='e p' cx='54' cy='16' r='4'/>"
            "<circle class='e p2' cx='30' cy='24' r='3.4'/>"
            "<circle class='e' cx='74' cy='30' r='3.2'/>"
            "<circle class='e' cx='50' cy='44' r='3'/>"
            "<circle class='n' cx='20' cy='50' r='2.6'/>"
            "<circle class='n' cx='84' cy='54' r='2.6'/>"
            "<circle class='n' cx='40' cy='62' r='2.4'/>"
            "</svg>"
            "<span class='launch-body'>"
            "<span class='launch-k'><span class='dot'></span>Interactive · WebGL · self-contained</span>"
            "<span class='launch-t'>Launch the Constellation</span>"
            "<span class='launch-d'><b>Click an account to follow its money</b> through the ring · "
            "<b>Show all 294</b> drops the whole bank back in · drag to orbit · it auto-spins when idle.</span>"
            "</span>"
            "<span class='launch-cta'>Open full-screen <span class='arr'>↗</span></span>"
            "</a>",
            unsafe_allow_html=True)
        st.caption("Opens in a new browser tab · fully offline · or double-click "
                   "`ui/quorum_constellation.html`.")

        st.markdown("<div class='qsec'>Triage funnel · "
                    "<span class='num'>294 accounts → the 9-account ring</span></div>",
                    unsafe_allow_html=True)
        st.plotly_chart(charts.funnel(cn), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Screen 2 — Case detail
# ══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cases_by_acct = {c["account"]: c for c in r["cases"]}
        accts = sorted(cases_by_acct, key=lambda a: cases_by_acct[a].get("p_mule", 0), reverse=True)
        sel = st.selectbox("Account", accts,
                           index=accts.index(st.session_state.selected)
                           if st.session_state.selected in accts else 0)
        c = cases_by_acct[sel]
        tau = r["adjudicator"]["tau"]

        # The bespoke Case File — one cohesive dossier (stamp · rail · ledger · signals).
        st.markdown(dossier_html(c, tau), unsafe_allow_html=True)

        if c.get("decoy_suspect"):
            st.markdown(
                "<div class='callout'><span class='mk'>⚠</span><div>"
                "<b>Planted decoy.</b> Shares a device with three accounts — the obvious "
                "flag — but is isolated in the transfer graph. The skeptical prior holds its "
                "probability near zero, so it is <b>cleared, not flagged</b>.</div></div>",
                unsafe_allow_html=True)

        _cfn = _geodo(r)["cost_basis"]["C_FN"]
        st.caption(f"Cost basis · regulatory (BSA penalty) · C_FN = ${_cfn['value']:,.0f} — {_cfn['source']}")

        cites = c.get("citations") or []
        if cites:
            st.markdown("<div class='qsec'>Precedents · <span class='num'>regulatory</span> "
                        "— how this maps to known typologies</div>", unsafe_allow_html=True)
            for ct in cites:
                st.markdown(f"- [{ct['title']}]({ct['url']}) · _{ct['citation']}_"
                            if ct.get("url") else f"- {ct['title']} · _{ct['citation']}_")

        if c.get("closing_rule"):
            st.markdown("<div class='qsec'>Learned closing rule · "
                        "<span class='num'>deploy to catch the next ring</span></div>",
                        unsafe_allow_html=True)
            st.code(c["closing_rule"], language="sql")

        st.markdown("<div class='qsec'>Ring subgraph · "
                    "<span class='num'>node colour = topological role</span></div>",
                    unsafe_allow_html=True)
        st.plotly_chart(_subgraph(r["detector"]["edges"], cases_by_acct),
                        use_container_width=True)

        st.download_button("⬇  DOWNLOAD SAR MEMO", r["reporter"]["memo_text"],
                           "QRM-2026-RING-001-memo.txt", "text/plain", type="primary")

# ══════════════════════════════════════════════════════════════════════════════
# Screen 3 — Signatures (the mechanical fingerprints, learned from the data)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cd = r["chart_data"]
        st.caption("Three independent fingerprints isolate the same ring — none was "
                   "hardcoded; the pipeline learned each boundary from the data.")
        c1, c2 = st.columns(2)
        c1.plotly_chart(charts.second_clock(cd["second_clock"]), use_container_width=True)
        c2.plotly_chart(charts.opening_burst(cd["opening_burst"]["ring"],
                                             cd["opening_burst"]["other"]),
                        use_container_width=True)
        st.plotly_chart(charts.amount_hist(cd["amount_hist"]["ac"],
                                           cd["amount_hist"]["mr"]),
                        use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Screen 4 — Memo (money-flow Sankey + SAR memo + learned closing rule)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        rep = r["reporter"]
        st.plotly_chart(charts.money_sankey(r["detector"]["edges"]),
                        use_container_width=True)
        ok = "✅" if rep.get("reconciliation_ok") else "⚠️"
        cM = st.columns([1, 2])
        cM[0].metric("Reconciled total", f"${rep.get('reconciled_total', 0):,.2f}",
                     f"{ok} target $161,750.90")
        cM[1].markdown(f"**Typology:** {rep.get('typology', '')}")
        cM[1].markdown("**Learned closing rule** — deploy to catch the next ring:")
        cM[1].code(rep.get("closing_rule", ""), language="sql")
        st.download_button("⬇ Download SAR memo (TXT)", rep.get("memo_text", ""),
                           "QRM-2026-RING-001-memo.txt", "text/plain", type="primary")
        with st.expander("Preview SAR memo"):
            st.text(rep.get("memo_text", ""))

        geo = _geodo(r)
        with st.expander("📚 Sources (regulatory precedent) — every claim traces to a verified primary source"):
            st.caption("Domain-Expert REGULATORY research grounding the memo's precedents and the "
                       "cost matrix behind τ. Each citation was verified against its source.")
            rv = geo.get("review")
            if rv:
                st.markdown(f"🧑‍⚖️ **Domain review** — {rv['name']}, _{rv['role']}_ "
                            f"({rv['date']}): {rv['scope']}")
                st.divider()
            for p in geo["precedents"]:
                st.markdown(
                    f"**[{p['title']}]({p['url']})** &nbsp;·&nbsp; _{p['citation']}_  \n"
                    f"{p['relevance']}  \n"
                    f"<span style='color:#8b93b5;font-size:12px'>signals: "
                    f"{', '.join(p['signal_tags'])}</span>",
                    unsafe_allow_html=True)
            st.markdown("**Cost matrix provenance** (the figures behind τ):")
            for name, cb in geo["cost_basis"].items():
                src = f"[{cb['source']}]({cb['url']})" if cb.get("url") else cb["source"]
                st.markdown(f"- `{name} = ${cb['value']:,.0f}` — {cb['rationale']}  \n"
                            f"  <span style='color:#8b93b5;font-size:12px'>source: {src}</span>",
                            unsafe_allow_html=True)
            if GEODO_DOC.exists():
                st.download_button("⬇ Download Geodo research brief (MD)",
                                   GEODO_DOC.read_text(), "GEODO_RESEARCH.md", "text/markdown")

        st.caption("→ Full market intelligence, buyer personas, digital twin learning, "
                   "and go-to-market outreach are on the **🎯 Market** tab.")

# ══════════════════════════════════════════════════════════════════════════════
# Screen 5 — Market (Geo intelligence, digital twin, buyers, outreach)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        mc = (r.get("market_context") or {})
        gm = _geo_market(r)
        packet = _gtm(r)
        conn = _geo_connection(r)

        # ── Geo connection ─────────────────────────────────────────────────
        st.markdown(_conn_badge_html(conn), unsafe_allow_html=True)

        # ── geodo.ai Intelligence Feed ─────────────────────────────────────
        excerpt = mc.get("research_excerpt") or ""
        captured_on = mc.get("captured_on") or ""
        feed_html = research_feed_html(excerpt, captured_on, captured_on)
        if feed_html:
            st.markdown(feed_html, unsafe_allow_html=True)

        # ── Two-column: Enforcement timeline + Persona grid ────────────────
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(
                "<div class='geo-sec'>Matched Enforcement Actions · <b>the &#8216;why now&#8217;</b></div>",
                unsafe_allow_html=True)
            signals = mc.get("intent_signals") or gm.get("intent_signals") or []
            st.markdown(enforcement_timeline_html(signals), unsafe_allow_html=True)
        with col2:
            st.markdown(
                "<div class='geo-sec'>ICP Personas · <b>who Quorum protects</b></div>",
                unsafe_allow_html=True)
            personas = gm.get("icp", {}).get("personas", [])
            st.markdown(persona_grid_html(personas), unsafe_allow_html=True)


        # ── Messaging angles ───────────────────────────────────────────────
        st.markdown(
            "<div class='geo-sec'>Messaging Intelligence · "
            "<b><span class='geodo-brand'>geodo.ai</span>-sourced value props per buyer persona</b></div>",
            unsafe_allow_html=True)
        angles = gm.get("messaging_angles") or mc.get("messaging_angles") or {}
        st.markdown(messaging_angles_html(angles), unsafe_allow_html=True)

        # ── ROI ────────────────────────────────────────────────────────────
        roi = _roi(r)
        if roi:
            st.markdown(
                "<div class='geo-sec'>Business Case · "
                "<b><span class='geodo-brand'>geodo.ai</span> labor rate × this run&#8217;s actuals</b></div>",
                unsafe_allow_html=True)
            st.markdown(roi_html(roi), unsafe_allow_html=True)

        # ── Digital twin learning ──────────────────────────────────────────
        if packet:
            st.markdown(
                "<div class='geo-sec'>Digital Twin Learning · "
                "<b>before vs after teaching <span class='geodo-brand'>geodo.ai</span> the ring</b></div>",
                unsafe_allow_html=True)
            st.markdown(twin_html(packet), unsafe_allow_html=True)
            tools = packet.get("tools_called", [])
            if tools:
                st.markdown(
                    "<div class='geo-sec'>"
                    "<span class='geodo-brand'>geodo.ai</span> MCP Calls · "
                    "<b>tool invocations that powered this packet</b></div>",
                    unsafe_allow_html=True)
                st.markdown(mcp_flow_html(tools), unsafe_allow_html=True)

            # ── Real buyers ────────────────────────────────────────────────
            st.markdown(
                "<div class='geo-sec'>Real Buyers · "
                "<b>sourced via <span class='geodo-brand'>geodo.ai MCP</span> · names masked until enrich</b></div>",
                unsafe_allow_html=True)
            contacts = packet.get("contacts") or []
            st.markdown(buyer_contact_cards_html(contacts), unsafe_allow_html=True)
            b = gm.get("buyers", {})
            if b.get("institutions"):
                st.markdown(
                    f"<span style='font-size:11px;color:var(--label);font-family:var(--mono)'>"
                    f"Institution pool ({b.get('sample_count','')}) via "
                    f"<span class='geodo-brand'>geodo.ai</span>: "
                    + ", ".join(b["institutions"]) + "</span>",
                    unsafe_allow_html=True)

            # ── Persona-tuned openers ──────────────────────────────────────
            if packet.get("openers"):
                st.markdown(
                    "<div class='geo-sec'>Persona-Tuned Openers · "
                    "<b>shared enforcement fact + <span class='geodo-brand'>geodo.ai</span> angle</b></div>",
                    unsafe_allow_html=True)
                st.markdown(opener_cards_html(packet["openers"]),
                            unsafe_allow_html=True)
                if packet.get("schedule"):
                    st.markdown(
                        f"<span style='font-size:12px;color:var(--muted)'>Proposed cadence "
                        f"(<span class='geodo-brand'>geodo.ai</span> · not launched): "
                        f"{packet['schedule']}</span>",
                        unsafe_allow_html=True)

            st.download_button(
                "⬇ Download Go-to-Market packet (MD)",
                gtm.packet_markdown(packet),
                "QRM-2026-RING-001-gtm-packet.md", "text/markdown")

# ══════════════════════════════════════════════════════════════════════════════
# Screen 6 — Pipeline view (criterion 2: fields accreting across 5 agents)
# ══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    if st.session_state.result is None:
        st.info("Load the file on the Queue screen first.")
    else:
        r = st.session_state.result
        cases_by_acct = {c["account"]: c for c in r["cases"]}
        accts = sorted(cases_by_acct)
        st.markdown("<div class='qsec'>Criterion 2 · <span class='num'>provable agent "
                    "collaboration</span> — five agents, <span class='geodo-brand'>geodo.ai</span> "
                    "MCP + Cognee, two entities</div>",
                    unsafe_allow_html=True)
        sel = st.selectbox("Trace this account's Case node through the pipeline", accts,
                           key="pipeline_sel")
        c = cases_by_acct[sel]
        st.markdown(relay_html(c, r.get("market_context")), unsafe_allow_html=True)

        st.markdown("<div class='qsec'>Cognee semantic graph · "
                    "<span class='num'>natural-language layer (Gemini)</span></div>",
                    unsafe_allow_html=True)
        import cognee_client as cognee
        graph = cognee.load_cognee_graph()

        if graph and graph.get("used"):
            st.success(f"✅ Pre-built Cognee graph — each of the 5 agents wrote a layer "
                       f"(`add`), unified with one `cognify`. Built {graph.get('built_at','')}.")
            st.caption("Agents that wrote to Cognee: " + ", ".join(graph.get("agents", [])))
            for agent, text in (graph.get("layers") or {}).items():
                with st.expander(f"Cognee layer written by agent: {agent}"):
                    st.text(text[:4000])
            st.markdown("**Questions answered from the Cognee graph** (`cognee.search`):")
            for item in graph.get("qa", []):
                st.markdown(f"**Q — {item['q']}**")
                st.write(item["a"])
            # Optional live query against the persisted graph (this process).
            q = st.text_input("Ask the graph something else", value="",
                              placeholder="e.g. which account is the hub source?")
            if q and st.button("Search Cognee live"):
                with st.spinner("Searching the Cognee graph…"):
                    res = cognee.cognee_search(q)
                st.write(res if res is not None else "No result / Cognee unavailable.")
        elif not cognee.USE_REAL_COGNEE:
            st.info("Cognee SDK inactive — set `GEMINI_API_KEY` in `.env`, then pre-build the "
                    "graph:  `uv run python main.py data/track02_fraud_watch.csv --cognee`")
        else:
            st.warning("No pre-built Cognee graph found. Build it once (writes "
                       "`cognee_graph.json`): `uv run python main.py "
                       "data/track02_fraud_watch.csv --cognee`  —  or build live below "
                       "(re-runs the agents in Cognee build mode; slow on the free tier).")
            if r.get("con") and st.button("🔭 Build Cognee graph now"):
                from agents import investigator, narrator, ranker, scout
                with st.spinner("Each agent writing its layer → cognify (Gemini)…"):
                    cognee.begin_build()
                    scout.run(r["con"]); ranker.run()
                    investigator.run(r["con"], detector_result=r["detector"])
                    narrator.run(detector_result=r["detector"])
                    cognee.finish_build()
                st.rerun()
            elif not r.get("con"):
                st.caption("Pre-built demo mode — rebuild the Cognee graph from the CLI: "
                           "`uv run python main.py data/track02_fraud_watch.csv --cognee`")
