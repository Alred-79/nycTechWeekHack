"""
The hero visual: an interactive 3D force-directed knowledge graph.

Renders the live transaction graph with vasturiano/3d-force-graph (Three.js/WebGL),
embedded in Streamlit via components.html. Fully interactive and explainable:

  • DRAG-AND-DROP any node · scroll to zoom (zooms out far) · "Fit" recenters
  • "Reveal the ring" collapses the 5,000-txn hairball to the ~14 surfaced Cases
  • "Money flow" animates particles source→sink along the AC→AC transfers
  • persistent labels (toggle) · hover highlights a node's connections
  • search an account by id · click any node → inspector with posterior + decision math

All data is the live pipeline output (see ui/graph_data.py) — nothing is mocked.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit.components.v1 as components

from ui.graph_data import COLORS

_VENDOR = Path(__file__).resolve().parent / "vendor"
_VENDOR_FILES = ["three.min.js", "three-spritetext.min.js", "3d-force-graph.min.js"]


@lru_cache(maxsize=1)
def _libs() -> str:
    """Inline the vendored JS libraries — fully local, no CDN, no network."""
    blocks = []
    for name in _VENDOR_FILES:
        code = (_VENDOR / name).read_text(encoding="utf-8")
        # defensive: never let a library's source close our <script> early
        code = code.replace("</script>", "<\\/script>")
        blocks.append(f"<!-- vendored: {name} -->\n<script>\n{code}\n</script>")
    return "\n".join(blocks)

_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body { margin:0; background:#0a1030; overflow:hidden; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  #wrap { position:relative; width:100%; height:__HEIGHT__px; }
  #graph { width:100%; height:100%; }
  .panel {
    position:absolute; padding:10px 12px; border-radius:12px;
    background:rgba(10,14,22,.86); backdrop-filter:blur(8px);
    border:1px solid rgba(255,255,255,.08); color:#e8edf4; font-size:12px;
    box-shadow:0 8px 30px rgba(0,0,0,.45); z-index:5;
  }
  #controls { left:14px; top:14px; max-width:62%; }
  #controls button {
    cursor:pointer; border:none; border-radius:8px; padding:7px 11px; margin:0 6px 6px 0;
    font-weight:600; font-size:12px; color:#fff; transition:transform .1s, filter .15s;
  }
  #controls button:hover { transform:translateY(-1px); filter:brightness(1.15); }
  #controls button.on { outline:2px solid #ffd166; }
  .btn-all{background:#2a3340} .btn-ring{background:linear-gradient(135deg,#ff3b3b,#ff7a3b)}
  .btn-flow{background:#1f6feb} .btn-fit{background:#2a3340} .btn-lbl{background:#2a3340}
  #search { background:#0c1118; border:1px solid rgba(255,255,255,.12); color:#e8edf4;
            border-radius:8px; padding:7px 10px; font-size:12px; width:140px; }
  #legend { right:14px; top:14px; line-height:1.65; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; vertical-align:middle; }
  .ln { display:inline-block; width:16px; height:0; border-top:3px solid; margin-right:6px; vertical-align:middle; }
  #stat { left:14px; bottom:14px; font-size:11px; opacity:.9; max-width:60%; }
  #help { right:14px; bottom:14px; width:250px; font-size:11px; line-height:1.5; display:none; }
  #helpBtn { right:14px; bottom:14px; cursor:pointer; padding:6px 11px; }
  #inspector { right:14px; top:150px; width:286px; display:none; max-height:62%; overflow:auto; }
  #inspector h3 { margin:0 0 6px; font-size:14px; }
  #inspector .row { display:flex; justify-content:space-between; margin:3px 0; gap:10px; }
  #inspector .k { opacity:.6; } #inspector .v { font-weight:600; text-align:right; }
  #inspector .reason { margin-top:8px; opacity:.85; font-size:11px; line-height:1.45; }
  #inspector .close { float:right; cursor:pointer; opacity:.6; }
  .pill { padding:2px 8px; border-radius:99px; font-size:10px; font-weight:700; color:#0a1030; }
  .tag { display:inline-block; background:#243; color:#9fe; border-radius:6px; padding:1px 6px;
         margin:2px 4px 0 0; font-size:10px; }
  #fallback { color:#9aa4b2; padding:24px; font-size:13px; position:absolute; top:42%; left:0; right:0; text-align:center; }
</style>
</head>
<body>
<div id="wrap">
  <div id="graph"></div>
  <div id="fallback">Loading 3D graph engine…</div>

  <div id="controls" class="panel">
    <button class="btn-all on" id="bAll" onclick="showAll()">All accounts</button>
    <button class="btn-ring" id="bRing" onclick="revealRing()">Reveal the ring</button>
    <button class="btn-flow" id="bFlow" onclick="toggleFlow()">Money flow ▶</button>
    <button class="btn-fit" onclick="fit()">Fit ⤢</button>
    <button class="btn-lbl on" id="bLbl" onclick="toggleLabels()">Labels</button>
    <input id="search" placeholder="find AC-0001…" onkeydown="if(event.key==='Enter')doSearch()"/>
  </div>

  <div id="legend" class="panel">
    <div style="opacity:.5;margin-bottom:3px">NODES — size = $ moved</div>
    <div><span class="dot" style="background:#ff3b3b"></span>Escalate (confirmed mule)</div>
    <div><span class="dot" style="background:#ffb020"></span>Review (uncertain → human)</div>
    <div><span class="dot" style="background:#8a8f98"></span>Decoy — cleared</div>
    <div><span class="dot" style="background:#2a3340"></span>Cleared account (noise)</div>
    <div><span class="dot" style="background:#3a4a63"></span>Merchant category</div>
    <div style="opacity:.5;margin:5px 0 3px">EDGES</div>
    <div><span class="ln" style="border-color:#ff5a5a"></span>AC→AC transfer (money)</div>
    <div><span class="ln" style="border-color:#ffb020;border-top-style:dashed"></span>Shared device</div>
    <div><span class="ln" style="border-color:#5a6b85"></span>Merchant spend</div>
  </div>

  <div id="stat" class="panel"></div>
  <div id="helpBtn" class="panel" onclick="toggleHelp()">? How to read this</div>
  <div id="help" class="panel">
    <b>What you're looking at</b><br>
    Every account at Crestline is a node. Lines are transactions. Most accounts only
    pay <b>merchant categories</b> — that's the noise cloud.<br><br>
    Hit <b>Reveal the ring</b> to drop the noise and keep only the ~14 accounts the
    pipeline surfaced. Hit <b>Money flow</b> to watch funds move through the
    layering chains. <b>Click</b> a node for its probability and the expected-loss
    math behind its decision.<br><br>
    Red = escalated mule · amber = sent to a human · gray = the planted decoy
    (shares a device but no money flows across it).
  </div>
  <div id="inspector" class="panel"></div>
</div>

__LIBS__
<script>
const DATA   = __DATA__;
const COLORS = __COLORS__;
let Graph, flowOn=false, view="all", labelsOn=true, hoverNode=null;

function fail(msg){ const f=document.getElementById("fallback"); if(f){f.style.display="block"; f.innerText=msg;} }
window.addEventListener("error", e => fail("Graph error: " + (e.message||e)));
const sid = l => (l.source&&l.source.id!==undefined)? l.source.id : l.source;
const tid = l => (l.target&&l.target.id!==undefined)? l.target.id : l.target;

function makeLabel(n){
  try{
    if(typeof SpriteText==="undefined") return false;
    if(!(n.candidate || n.kind==="category")) return false;   // label only the meaningful nodes
    const s = new SpriteText(n.label);
    s.color = n.candidate ? "#ffffff" : "#9fb0c8";
    s.textHeight = n.candidate ? 4 : 3;
    s.fontWeight = n.candidate ? "700" : "400";
    s.material.depthWrite = false;
    s.position.y = (Math.cbrt(n.val||3)*4) + 5;
    return s;
  }catch(e){ return false; }
}

function nodeColor(n){
  if(hoverNode){
    if(n===hoverNode) return "#ffffff";
    return (neighbors.has(n.id)) ? n.color : "#1a2230";
  }
  return n.color;
}
let neighbors = new Set();
function computeNeighbors(node){
  neighbors = new Set();
  if(!node) return;
  Graph.graphData().links.forEach(l=>{
    if(sid(l)===node.id) neighbors.add(tid(l));
    if(tid(l)===node.id) neighbors.add(sid(l));
  });
}

function start(){
  try{
    if(typeof ForceGraph3D==="undefined"){ fail("3D engine failed to load (offline?)."); return; }
    document.getElementById("fallback").style.display="none";
    Graph = ForceGraph3D()(document.getElementById("graph"))
      .backgroundColor("#0a1030")
      .graphData(DATA)
      .nodeColor(nodeColor)
      .nodeVal(n => n.val)
      .nodeOpacity(0.95)
      .nodeResolution(10)
      .nodeLabel(tooltip)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject(n => labelsOn ? makeLabel(n) : false)
      .linkColor(l => {
          if(hoverNode && (sid(l)===hoverNode.id || tid(l)===hoverNode.id)) return "#ffffff";
          return l.type==="ring" ? "#ff5a5a" : l.type==="device" ? "#ffb020" : "rgba(120,140,170,0.10)";
      })
      .linkWidth(l => {
          const base = l.type==="ring" ? (l.width||2) : 0.4;
          return (hoverNode && (sid(l)===hoverNode.id || tid(l)===hoverNode.id)) ? base+2 : base;
      })
      .linkOpacity(0.55)
      .linkCurvature(l => l.type==="device" ? 0.4 : 0)
      .linkDirectionalArrowLength(l => l.type==="ring" ? 3.5 : 0)
      .linkDirectionalArrowRelPos(1)
      .onNodeHover(n => { hoverNode=n||null; computeNeighbors(n); refresh(); })
      .onNodeClick(focusNode)
      .onNodeDragEnd(n => { n.fx=n.x; n.fy=n.y; n.fz=n.z; });

    Graph.d3Force("charge").strength(-95);
    // allow zooming WAY out (and back in close)
    const c = Graph.controls();
    if(c){ c.maxDistance = 60000; c.minDistance = 8; }
    setStat(); setFlow();
    setTimeout(fit, 600);
  }catch(err){ fail("Graph init error: " + err.message); }
}

function refresh(){ if(Graph) Graph.nodeColor(nodeColor).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth()); }

function tooltip(n){
  if(!n.candidate) return (n.kind==="category") ? ("merchant: "+n.label) : n.label;
  const p = (n.p_mule!=null)? (n.p_mule*100).toFixed(1)+"%" : "—";
  return `<b>${n.label}</b> · ${(n.role||"").toUpperCase()}<br>P(mule)=${p} · ${n.action||""}<br><span style="opacity:.7">click for detail</span>`;
}

function setFlow(){
  if(!Graph) return;
  Graph.linkDirectionalParticles(l => (flowOn && l.type==="ring") ? Math.max(2, Math.round((l.count||0)/12)) : 0)
       .linkDirectionalParticleWidth(2.6)
       .linkDirectionalParticleSpeed(()=>0.006)
       .linkDirectionalParticleColor(()=>"#ffd166");
}
function toggleFlow(){ flowOn=!flowOn; document.getElementById("bFlow").classList.toggle("on",flowOn); setFlow(); }
function toggleLabels(){ labelsOn=!labelsOn; document.getElementById("bLbl").classList.toggle("on",labelsOn);
  Graph.nodeThreeObject(n => labelsOn ? makeLabel(n) : false); }
function toggleHelp(){ const h=document.getElementById("help"); h.style.display = h.style.display==="block"?"none":"block"; }
function fit(){ if(Graph) Graph.zoomToFit(800, view==="ring"?100:80); }

function filtered(){
  const nodes = DATA.nodes.filter(n => n.candidate);
  const ids = new Set(nodes.map(n=>n.id));
  const links = DATA.links.filter(l => l.type!=="noise" && ids.has(sid(l)) && ids.has(tid(l)));
  return {nodes, links};
}
function revealRing(){
  view="ring"; flowOn=true;
  document.getElementById("bAll").classList.remove("on");
  document.getElementById("bRing").classList.add("on");
  document.getElementById("bFlow").classList.add("on");
  Graph.graphData(filtered()); setFlow(); setStat(); setTimeout(fit,400);
}
function showAll(){
  view="all"; flowOn=false;
  document.getElementById("bAll").classList.add("on");
  document.getElementById("bRing").classList.remove("on");
  document.getElementById("bFlow").classList.remove("on");
  DATA.nodes.forEach(n=>{ n.fx=n.fy=n.fz=undefined; });
  Graph.graphData(DATA); setFlow(); setStat(); setTimeout(fit,400);
}

function setStat(){
  const tot=DATA.nodes.filter(n=>n.kind==="account").length;
  const cand=DATA.nodes.filter(n=>n.candidate).length;
  const esc=DATA.nodes.filter(n=>n.group==="ring").length;
  const txt = view==="ring"
    ? `Ring view · <b>${cand}</b> surfaced · <b>${esc}</b> escalate · ${tot-cand} auto-cleared`
    : `Full graph · <b>${tot}</b> accounts + merchant hubs · the ring is hidden in the noise`;
  const s=document.getElementById("stat"); if(s) s.innerHTML=txt;
}

function doSearch(){
  const q=document.getElementById("search").value.trim().toUpperCase();
  if(!q) return;
  const n=Graph.graphData().nodes.find(x=>(x.id||"").toUpperCase()===q
        || (x.label||"").toUpperCase()===q);
  if(n){ focusNode(n); } else { document.getElementById("search").value=""; document.getElementById("search").placeholder="not in view — Reveal ring?"; }
}

function focusNode(n){
  const dist=90, r=1+dist/Math.hypot(n.x||1,n.y||1,n.z||1);
  Graph.cameraPosition({x:(n.x||0)*r,y:(n.y||0)*r,z:(n.z||1)*r}, n, 900);
  hoverNode=n; computeNeighbors(n); refresh();
  const ins=document.getElementById("inspector");
  if(!n.candidate){ ins.style.display="none"; return; }
  const p=(n.p_mule*100).toFixed(1);
  const ci=n.ci?`[${(n.ci[0]*100).toFixed(1)}%, ${(n.ci[1]*100).toFixed(1)}%]`:"—";
  const tags=(n.fired||[]).map(s=>`<span class="tag">${s.replace(/_/g,' ')}</span>`).join("");
  const el=(v)=> v!=null ? ("$"+Number(v).toLocaleString(undefined,{maximumFractionDigits:2})) : "—";
  ins.innerHTML = `
    <span class="close" onclick="document.getElementById('inspector').style.display='none'">✕</span>
    <h3>${n.label} <span class="pill" style="background:${n.color}">${n.action||""}</span></h3>
    <div class="row"><span class="k">Role</span><span class="v">${(n.role||"").toUpperCase()}</span></div>
    <div class="row"><span class="k">P(mule)</span><span class="v">${p}%</span></div>
    <div class="row"><span class="k">94% credible interval</span><span class="v">${ci}</span></div>
    <div class="row"><span class="k">$ moved</span><span class="v">${el(n.usd)}</span></div>
    <div class="row"><span class="k">Transfers</span><span class="v">${n.n_transfers??"—"}</span></div>
    <div class="row"><span class="k">Typology</span><span class="v">${n.typology||"—"}</span></div>
    <div class="row"><span class="k">E[loss] escalate</span><span class="v">${el(n.e_loss_escalate)}</span></div>
    <div class="row"><span class="k">E[loss] clear</span><span class="v">${el(n.e_loss_clear)}</span></div>
    <div style="margin-top:6px"><span class="k">Signals fired</span><br>${tags||"—"}</div>
    <div class="reason">${n.action_reason||n.reason||""}</div>`;
  ins.style.display="block";
}

if(document.readyState!=="loading") start();
else document.addEventListener("DOMContentLoaded", start);
</script>
</body>
</html>
"""


def build_html(graph: dict, height: int = 600) -> str:
    """The complete, self-contained HTML (vendored JS inlined) for `graph`."""
    return (_TEMPLATE
            .replace("__LIBS__", _libs())
            .replace("__DATA__", json.dumps(graph))
            .replace("__COLORS__", json.dumps(COLORS))
            .replace("__HEIGHT__", str(height)))


def render(graph: dict, height: int = 600) -> None:
    components.html(build_html(graph, height), height=height + 4, scrolling=False)


def write_html(graph: dict, path, height: int = 860):
    """Write a standalone, double-click-openable HTML file of the graph."""
    from pathlib import Path as _P
    p = _P(path)
    p.write_text(build_html(graph, height), encoding="utf-8")
    return p
