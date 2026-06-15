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
  :root{
    --ink:#0a0c11; --panel:rgba(13,16,22,.82); --line:rgba(178,198,234,.12);
    --line2:rgba(178,198,234,.22); --text:#e7ebf3; --muted:#8a93a6; --label:#7b859b;
    --accent:#5fd0e0; --esc:#ff5468; --rev:#f7b733; --clr:#34d6a4;
    --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  }
  html, body { margin:0; background:var(--ink); overflow:hidden; font-family:var(--sans); color:var(--text); }
  #wrap { position:relative; width:100%; height:__HEIGHT__px; }
  #graph { width:100%; height:100%; }
  /* atmosphere: blueprint grid + vignette + grain over the WebGL canvas */
  #atmos{ position:absolute; inset:0; pointer-events:none; z-index:2;
    background:
      radial-gradient(120% 90% at 50% 0%, transparent 55%, rgba(0,0,0,.55) 100%),
      linear-gradient(transparent 0 calc(100% - 1px), rgba(178,198,234,.05) 0) 0 0/100% 44px,
      linear-gradient(90deg, transparent 0 calc(100% - 1px), rgba(178,198,234,.05) 0) 0 0/44px 100%; }
  .panel {
    position:absolute; padding:11px 13px; border-radius:5px;
    background:var(--panel); backdrop-filter:blur(10px) saturate(1.1);
    border:1px solid var(--line); color:var(--text); font-size:12px;
    box-shadow:0 18px 50px -22px rgba(0,0,0,.9), inset 0 1px 0 rgba(255,255,255,.03); z-index:5;
  }
  /* corner masthead */
  #brand{ left:14px; top:14px; padding:9px 14px; display:flex; align-items:baseline; gap:10px; }
  #brand .wm{ font-family:Georgia,"Times New Roman",serif; font-size:19px; font-weight:600; letter-spacing:-.01em; }
  #brand .wm b{ color:var(--accent); font-weight:600; }
  #brand .ey{ font-family:var(--mono); font-size:8.5px; letter-spacing:.26em; text-transform:uppercase; color:var(--label); }
  #controls { left:14px; top:60px; max-width:64%; }
  #controls button {
    cursor:pointer; border:1px solid var(--line2); border-radius:4px; padding:7px 12px; margin:0 5px 6px 0;
    font-family:var(--mono); font-weight:600; font-size:11px; letter-spacing:.05em; text-transform:uppercase;
    color:var(--text); background:rgba(255,255,255,.02); transition:.14s;
  }
  #controls button:hover { border-color:var(--accent); color:var(--accent); }
  #controls button.on { border-color:var(--accent); color:#06141a; background:var(--accent); }
  .btn-ring.on{ border-color:var(--esc); background:var(--esc); color:#180408; }
  #search { background:rgba(0,0,0,.3); border:1px solid var(--line2); color:var(--text);
            border-radius:4px; padding:7px 10px; font-family:var(--mono); font-size:11px; width:150px; }
  #search::placeholder{ color:var(--label); }
  #search:focus{ outline:none; border-color:var(--accent); }
  #legend { right:14px; top:14px; line-height:1.7; min-width:208px; }
  #legend .lh{ font-family:var(--mono); font-size:8.5px; letter-spacing:.2em; text-transform:uppercase;
    color:var(--label); margin:0 0 5px; } #legend .lh+.lh{ margin-top:8px; }
  #legend > div{ font-size:11.5px; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:9px; vertical-align:middle; }
  .ln { display:inline-block; width:16px; height:0; border-top:3px solid; margin-right:8px; vertical-align:middle; }
  #stat { left:14px; bottom:14px; font-size:11px; font-family:var(--mono); letter-spacing:.03em;
    color:var(--muted); max-width:48%; } #stat b{ color:var(--text); }
  /* "following the money" caption — appears on node click */
  #trace { left:50%; bottom:16px; transform:translateX(-50%); display:none; font-family:var(--mono);
    font-size:12px; letter-spacing:.02em; color:var(--text); border-color:var(--line2);
    background:rgba(13,16,22,.92); padding:10px 16px; box-shadow:0 0 0 1px rgba(255,209,102,.25),
    0 18px 50px -20px rgba(0,0,0,.9); animation:traceIn .3s cubic-bezier(.2,.8,.2,1) both; }
  #trace b{ color:#ffd166; }
  #trace .x{ cursor:pointer; color:var(--label); margin-left:12px; padding-left:12px;
    border-left:1px solid var(--line2); font-size:10px; letter-spacing:.1em; text-transform:uppercase; }
  #trace .x:hover{ color:var(--text); }
  @keyframes traceIn{ from{ opacity:0; transform:translate(-50%,8px) } to{ opacity:1; transform:translate(-50%,0) } }
  /* persistent "what the flow means" note while Flow is on */
  #flownote { left:50%; bottom:16px; transform:translateX(-50%); display:none; font-family:var(--mono);
    font-size:10.5px; letter-spacing:.02em; color:var(--muted); padding:8px 15px; }
  #flownote b{ color:var(--text); }
  #flownote .d{ display:inline-block; width:7px; height:7px; border-radius:50%; background:#ffd166;
    margin-right:9px; vertical-align:middle; box-shadow:0 0 8px #ffd166; }
  #help { right:14px; bottom:14px; width:262px; font-size:11.5px; line-height:1.6; display:none; color:var(--muted); }
  #help b{ color:var(--text); }
  #helpBtn { right:14px; bottom:14px; cursor:pointer; padding:7px 12px; font-family:var(--mono);
    font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }
  #helpBtn:hover{ color:var(--accent); }
  #inspector { right:14px; top:150px; width:298px; display:none; max-height:64%; overflow:auto; padding:0; }
  #inspector .ihead{ padding:14px 16px 11px; border-bottom:1px solid var(--line);
    background:linear-gradient(180deg,rgba(255,255,255,.025),transparent); }
  #inspector .ibody{ padding:12px 16px 15px; }
  #inspector h3 { margin:0; font-family:Georgia,serif; font-size:20px; font-weight:600; display:flex;
    align-items:center; justify-content:space-between; }
  #inspector .row { display:flex; justify-content:space-between; margin:6px 0; gap:10px; font-size:11.5px;
    border-bottom:1px solid rgba(178,198,234,.06); padding-bottom:6px; }
  #inspector .k { color:var(--label); font-family:var(--mono); font-size:10px; letter-spacing:.04em; text-transform:uppercase; }
  #inspector .v { font-weight:600; text-align:right; font-family:var(--mono); }
  #inspector .reason { margin-top:10px; color:var(--muted); font-size:11px; line-height:1.55;
    font-family:var(--mono); background:rgba(0,0,0,.25); border:1px solid var(--line); border-radius:4px; padding:10px 11px; }
  #inspector .close { cursor:pointer; color:var(--label); font-size:14px; } #inspector .close:hover{ color:var(--text); }
  #inspector .hint { margin-top:11px; padding-top:10px; border-top:1px solid var(--line); color:var(--label);
    font-family:var(--mono); font-size:9.5px; line-height:1.5; letter-spacing:.02em; }
  .pill { padding:3px 9px; border-radius:4px; font-family:var(--mono); font-size:10px; font-weight:700;
    letter-spacing:.08em; color:#0a0c11; }
  .tag { display:inline-block; background:rgba(95,208,224,.1); color:var(--accent); border:1px solid var(--line2);
         border-radius:4px; padding:2px 7px; margin:3px 4px 0 0; font-family:var(--mono); font-size:9.5px; letter-spacing:.03em; }
  #fallback { color:var(--muted); padding:24px; font-size:13px; font-family:var(--mono);
    position:absolute; top:42%; left:0; right:0; text-align:center; }
  /* hover tooltip — dark panel so text never camouflages against white nodes/lines */
  .scene-tooltip, .graph-tooltip {
    font-family:var(--mono)!important; font-size:11.5px!important; line-height:1.5!important;
    color:var(--text)!important; background:rgba(11,13,18,.96)!important;
    border:1px solid var(--line2)!important; border-radius:5px!important;
    padding:8px 11px!important; max-width:250px!important; letter-spacing:.02em!important;
    box-shadow:0 16px 44px -18px rgba(0,0,0,.95)!important; backdrop-filter:blur(6px); }
  /* no node under the cursor → no empty box */
  .scene-tooltip:empty, .graph-tooltip:empty { display:none!important; }
</style>
</head>
<body>
<div id="wrap">
  <div id="graph"></div>
  <div id="atmos"></div>
  <div id="fallback">Loading 3D graph engine…</div>

  <div id="brand" class="panel">
    <span class="wm">QU<b>O</b>RUM</span>
    <span class="ey">Money-Laundering Constellation</span>
  </div>

  <div id="controls" class="panel">
    <button class="btn-ring" id="bRing" onclick="revealRing()">The ring</button>
    <button class="btn-all on" id="bAll" onclick="showAll()">Show all __N_ACCOUNTS__</button>
    <button class="btn-flow on" id="bFlow" onclick="toggleFlow()">Flow ▶</button>
    <button class="btn-spin on" id="bSpin" onclick="toggleSpin()">Auto-spin ⟳</button>
    <button class="btn-fit" onclick="fit()">Fit ⤢</button>
    <button class="btn-lbl on" id="bLbl" onclick="toggleLabels()">Labels</button>
    <input id="search" placeholder="find AC-0001…" onkeydown="if(event.key==='Enter')doSearch()"/>
  </div>

  <div id="legend" class="panel">
    <div class="lh">Nodes — size = $ moved</div>
    <div><span class="dot" style="background:#ff5468"></span>Escalate — confirmed mule</div>
    <div><span class="dot" style="background:#f7b733"></span>Review — uncertain → human</div>
    <div><span class="dot" style="background:#8a93a6"></span>Decoy — cleared</div>
    <div><span class="dot" style="background:#2b3550"></span>Cleared account (noise)</div>
    <div><span class="dot" style="background:#46527a"></span>Merchant category</div>
    <div class="lh">Edges</div>
    <div><span class="ln" style="border-color:#ff5468"></span>AC→AC transfer (money)</div>
    <div><span class="ln" style="border-color:#f7b733;border-top-style:dashed"></span>Shared device</div>
    <div><span class="ln" style="border-color:#46527a"></span>Merchant spend</div>
  </div>

  <div id="stat" class="panel"></div>
  <div id="trace" class="panel"></div>
  <div id="flownote" class="panel">
    <span class="d"></span>Particles = <b>real transfers</b> · money moves only through the ring
  </div>
  <div id="helpBtn" class="panel" onclick="toggleHelp()">? How to read this</div>
  <div id="help" class="panel">
    <b>Follow the money.</b> Each glowing node is an account the pipeline surfaced;
    the lines are the transfers between them.<br><br>
    <b>Click any account</b> to light up the chain the money flows <i>through</i> it —
    everything else dims so you can read one path at a time.<br><br>
    <b>Show all __N_ACCOUNTS__</b> drops the whole bank back in (the ring hides in the noise).
    <b>Flow</b> animates the transfers · <b>drag</b> to rotate · <b>scroll</b> to zoom.<br><br>
    Red = escalated mule · amber = sent to a human · gray = the planted decoy.
  </div>
  <div id="inspector" class="panel"></div>
</div>

__LIBS__
<script>
const DATA   = __DATA__;
const COLORS = __COLORS__;
let Graph, flowOn=true, view="all", labelsOn=true, hoverNode=null;
let traceActive=false, traceNodes=new Set(), traceLinks=new Set();
let spinOn=true, lastAct=Date.now();

// A tiny d3-style force: nudge every node toward the origin proportional to its
// distance, so disconnected ring-chains cluster together instead of drifting apart.
function centerPull(strength, onlyCandidates){
  let nodes = [];
  function force(alpha){
    for(const n of nodes){
      if(onlyCandidates && !n.candidate) continue;
      n.vx -= (n.x||0) * strength * alpha;
      n.vy -= (n.y||0) * strength * alpha;
      n.vz -= (n.z||0) * strength * alpha;
    }
  }
  force.initialize = ns => { nodes = ns; };
  return force;
}

// Force tuning differs by view: the full account graph wants to spread into a
// noise cloud; the ring view wants the disconnected chains pulled tightly together.
function applyForces(){
  if(!Graph) return;
  const charge = Graph.d3Force("charge");
  const link = Graph.d3Force("link");
  if(view==="ring"){
    if(charge) charge.strength(-70).distanceMax(130);
    if(link) link.distance(32);
    Graph.d3Force("pull", centerPull(0.11));
  } else {
    // Cap how far the repulsion reaches so the cloud can't fling the disconnected
    // ring-chains across the scene, and pull only the surfaced (ring) nodes inward
    // (they have no merchant links). Balanced, they settle just outside the cloud.
    if(charge) charge.strength(-95).distanceMax(165);
    if(link) link.distance(30);
    Graph.d3Force("pull", centerPull(0.30, true));
  }
}

function fail(msg){ const f=document.getElementById("fallback"); if(f){f.style.display="block"; f.innerText=msg;} }
window.addEventListener("error", e => fail("Graph error: " + (e.message||e)));
const sid = l => (l.source&&l.source.id!==undefined)? l.source.id : l.source;
const tid = l => (l.target&&l.target.id!==undefined)? l.target.id : l.target;
// accounts that actually originate a transfer — only these have money to "follow"
const SENDERS = new Set(DATA.links.filter(l => l.type==="ring").map(sid));

// Seed the surfaced (ring) nodes near the centre so the disconnected chains don't
// spawn far out and never get reeled back in before the simulation cools.
function seedRingPositions(){
  DATA.nodes.forEach(n => {
    if(n.candidate){
      n.x = (Math.random()-0.5)*50;
      n.y = (Math.random()-0.5)*50;
      n.z = (Math.random()-0.5)*50;
    }
  });
}

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
  if(traceActive){
    return traceNodes.has(n.id) ? n.color : "#11151d";
  }
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
    seedRingPositions();
    Graph = ForceGraph3D()(document.getElementById("graph"))
      .backgroundColor("#0a0c11")
      .graphData(view==="ring" ? filtered() : DATA)
      .nodeColor(nodeColor)
      .nodeVal(n => n.val)
      .nodeOpacity(0.95)
      .nodeResolution(12)
      .nodeLabel(tooltip)
      .nodeThreeObjectExtend(true)
      .nodeThreeObject(n => labelsOn ? makeLabel(n) : false)
      .linkColor(l => {
          if(traceActive) return traceLinks.has(l) ? "#ffd166" : "rgba(120,140,170,0.04)";
          if(hoverNode && (sid(l)===hoverNode.id || tid(l)===hoverNode.id)) return "#ffffff";
          return l.type==="ring" ? "#ff5468" : l.type==="device" ? "#f7b733" : "rgba(120,140,170,0.09)";
      })
      .linkWidth(l => {
          if(traceActive) return traceLinks.has(l) ? (l.width||2)+1.6 : 0.2;
          const base = l.type==="ring" ? (l.width||2) : 0.4;
          return (hoverNode && (sid(l)===hoverNode.id || tid(l)===hoverNode.id)) ? base+2 : base;
      })
      .linkOpacity(0.6)
      .linkCurvature(l => l.type==="device" ? 0.4 : 0)
      .linkDirectionalArrowLength(l => l.type==="ring" ? 3.5 : 0)
      .linkDirectionalArrowRelPos(1)
      .onNodeHover(n => { if(!traceActive){ hoverNode=n||null; computeNeighbors(n); refresh(); } })
      .onNodeClick(onNodeClick)
      .onBackgroundClick(clearTrace)
      .onNodeDragEnd(n => { n.fx=n.x; n.fy=n.y; n.fz=n.z; });

    applyForces();
    // allow zooming WAY out (and back in close)
    const c = Graph.controls();
    if(c){ c.maxDistance = 60000; c.minDistance = 8; }
    // any interaction pauses the idle auto-spin
    ["pointerdown","wheel","touchstart"].forEach(ev =>
      document.getElementById("graph").addEventListener(ev, ()=>{ lastAct=Date.now(); }, {passive:true}));
    setInterval(idleSpin, 33);
    setStat(); setFlow();
    setTimeout(fit, 600);
  }catch(err){ fail("Graph init error: " + err.message); }
}

// Gently orbit the camera around the scene centre when the user is idle.
function idleSpin(){
  if(!Graph || !spinOn) return;
  if(Date.now() - lastAct < 4000) return;
  const p = Graph.cameraPosition();
  const a = 0.0018, cos = Math.cos(a), sin = Math.sin(a);
  Graph.cameraPosition({ x: p.x*cos - p.z*sin, y: p.y, z: p.x*sin + p.z*cos }, undefined, 0);
}
function toggleSpin(){ spinOn=!spinOn; document.getElementById("bSpin").classList.toggle("on",spinOn); lastAct=Date.now(); }

// "Follow the money": light up the chain the money flows through this account.
function onNodeClick(n){
  lastAct = Date.now();
  focusNode(n);
  // only nodes that originate a transfer have money to follow; others just open the inspector
  if(n && n.candidate && SENDERS.has(n.id)) traceFrom(n); else clearTrace();
}
function traceFrom(n){
  traceNodes = new Set([n.id]); traceLinks = new Set();
  const ringLinks = Graph.graphData().links.filter(l => l.type==="ring");
  let frontier = [n.id], guard = 0, sum = 0;
  while(frontier.length && guard++ < 40){
    const next = [];
    ringLinks.forEach(l => {
      if(frontier.includes(sid(l)) && !traceLinks.has(l)){
        traceLinks.add(l); sum += (l.usd || 0);
        if(!traceNodes.has(tid(l))){ traceNodes.add(tid(l)); next.push(tid(l)); }
      }
    });
    frontier = next;
  }
  traceActive = true; hoverNode = null;
  const cap = document.getElementById("trace");
  const hops = traceNodes.size - 1;
  if(traceLinks.size === 0){
    cap.innerHTML = `<b>${n.label}</b> originates no transfers — it's a sink`
      + `<span class="x" onclick="clearTrace()">✕ clear</span>`;
  } else {
    cap.innerHTML = `Following <b>${n.label}</b> → ${hops} downstream account${hops===1?'':'s'} · `
      + `$${Math.round(sum).toLocaleString()} routed`
      + `<span class="x" onclick="clearTrace()">✕ clear</span>`;
  }
  cap.style.display = "block";
  setFlow(); refresh();
}
function clearTrace(){
  if(!traceActive) return;
  traceActive = false; traceNodes = new Set(); traceLinks = new Set();
  const cap = document.getElementById("trace"); if(cap) cap.style.display = "none";
  setFlow(); refresh();
}

function refresh(){ if(Graph) Graph.nodeColor(nodeColor).linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth()); }

function tooltip(n){
  if(!n.candidate) return (n.kind==="category")
    ? `<span style="color:#8a93a6">merchant · ${n.label}</span>` : n.label;
  const p = (n.p_mule!=null)? (n.p_mule*100).toFixed(1)+"%" : "—";
  const col = n.color || "#5fd0e0";
  const hint = SENDERS.has(n.id) ? "click to follow the money" : "click to inspect";
  return `<span style="color:${col};font-weight:700">${n.label}</span>`
    + `<span style="color:#8a93a6"> · ${(n.role||"").toUpperCase()}</span><br>`
    + `<span style="color:#e7ebf3">P(mule) ${p} · ${n.action||""}</span><br>`
    + `<span style="color:#7b859b;font-size:10px">${hint}</span>`;
}

function setFlow(){
  if(!Graph) return;
  Graph.linkDirectionalParticles(l => {
        if(traceActive) return traceLinks.has(l) ? Math.max(3, Math.round((l.count||0)/8)) : 0;
        return (flowOn && l.type==="ring") ? Math.max(2, Math.round((l.count||0)/12)) : 0;
      })
       .linkDirectionalParticleWidth(traceActive ? 3.4 : 2.6)
       .linkDirectionalParticleSpeed(()=>0.006)
       .linkDirectionalParticleColor(()=>"#ffd166");
  const fn = document.getElementById("flownote");
  if(fn) fn.style.display = (flowOn && !traceActive) ? "block" : "none";
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
  clearTrace(); view="ring"; flowOn=true; lastAct=Date.now();
  document.getElementById("bAll").classList.remove("on");
  document.getElementById("bRing").classList.add("on");
  document.getElementById("bFlow").classList.add("on");
  Graph.graphData(filtered()); applyForces(); setFlow(); setStat(); setTimeout(fit,400);
}
function showAll(){
  clearTrace(); view="all"; flowOn=false; lastAct=Date.now();
  document.getElementById("bAll").classList.add("on");
  document.getElementById("bRing").classList.remove("on");
  document.getElementById("bFlow").classList.remove("on");
  DATA.nodes.forEach(n=>{ n.fx=n.fy=n.fz=undefined; });
  Graph.graphData(DATA); applyForces(); setFlow(); setStat(); setTimeout(fit,400);
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
    <div class="ihead">
      <h3>${n.label}
        <span style="display:flex;gap:8px;align-items:center">
          <span class="pill" style="background:${n.color}">${n.action||""}</span>
          <span class="close" onclick="document.getElementById('inspector').style.display='none'">✕</span>
        </span>
      </h3>
    </div>
    <div class="ibody">
    <div class="row"><span class="k">Role</span><span class="v">${(n.role||"").toUpperCase()}</span></div>
    <div class="row"><span class="k">P(mule)</span><span class="v" style="color:${n.color}">${p}%</span></div>
    <div class="row"><span class="k">$ moved</span><span class="v">${el(n.usd)}</span></div>
    <div class="row"><span class="k">Transfers</span><span class="v">${n.n_transfers??"—"}</span></div>
    <div style="margin-top:10px"><span class="k" style="font-family:var(--mono);font-size:10px;letter-spacing:.04em;text-transform:uppercase;color:var(--label)">Signals fired</span><br>${tags||"—"}</div>
    <div class="hint">Open the Case detail tab for the full posterior &amp; loss math.</div>
    </div>`;
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
    n_accounts = sum(1 for n in graph.get("nodes", []) if n.get("kind") == "account")
    return (_TEMPLATE
            .replace("__LIBS__", _libs())
            .replace("__DATA__", json.dumps(graph))
            .replace("__COLORS__", json.dumps(COLORS))
            .replace("__HEIGHT__", str(height))
            .replace("__N_ACCOUNTS__", str(n_accounts)))


def render(graph: dict, height: int = 600) -> None:
    components.html(build_html(graph, height), height=height + 4, scrolling=False)


def write_html(graph: dict, path, height: int = 860):
    """Write a standalone, double-click-openable HTML file of the graph."""
    from pathlib import Path as _P
    p = _P(path)
    p.write_text(build_html(graph, height), encoding="utf-8")
    return p
