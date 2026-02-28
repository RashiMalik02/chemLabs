// frontend/src/components/Lab.jsx

import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

if (!document.getElementById('lab-styles')) {
  const tag = document.createElement('style');
  tag.id = 'lab-styles';
  tag.textContent = `
    @keyframes pulse        { 0%,100%{opacity:1}  50%{opacity:.3} }
    @keyframes fadeSlideUp  { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:translateY(0)} }
    @keyframes revealGlow   { 0%{box-shadow:0 0 0 rgba(74,222,128,0)} 60%{box-shadow:0 0 32px rgba(74,222,128,.35)} 100%{box-shadow:0 0 12px rgba(74,222,128,.15)} }
    @keyframes hintFade     { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
  `;
  document.head.appendChild(tag);
}

// ── Reaction hint matrix ──────────────────────────────────────────────────────
// Shown below the camera frame as soon as a chemical is selected.
// Covers every (litmus × chemical_type) combination so students always
// know what to expect before they pour.
function getReactionHint(chemType, reactionType) {
  if (!chemType || !reactionType) return null;

  const paper    = reactionType === 'red_litmus' ? 'Red' : 'Blue';
  const willReact = (
    (reactionType === 'blue_litmus' && chemType === 'acid') ||
    (reactionType === 'red_litmus'  && chemType === 'base')
  );

  if (willReact) {
    const turnsTo = reactionType === 'blue_litmus' ? 'RED' : 'BLUE';
    const reason  = chemType === 'acid'
      ? 'Acids donate H⁺ ions, causing blue litmus to turn red.'
      : 'Bases donate OH⁻ ions, causing red litmus to turn blue.';
    return {
      reacts:  true,
      icon:    '⚗️',
      title:   `${paper} litmus paper WILL change colour`,
      detail:  `Tilt your hand to pour. The paper will turn ${turnsTo}. ${reason}`,
      color:   chemType === 'acid' ? '#f87171' : '#38bdf8',
    };
  }

  // No reaction — explain why
  let detail;
  if (chemType === 'neutral') {
    detail = `${paper} litmus paper does NOT change colour with a neutral substance. Neutral substances have no free H⁺ or OH⁻ ions to trigger a reaction.`;
  } else if (chemType === 'acid') {
    // acid + red litmus
    detail = `${paper} litmus paper does NOT change colour in the presence of an acid. Red litmus only changes colour with a base (alkali). Try Blue litmus to test acids.`;
  } else {
    // base + blue litmus
    detail = `${paper} litmus paper does NOT change colour in the presence of a base. Blue litmus only changes colour with an acid. Try Red litmus to test bases.`;
  }
  return {
    reacts: false,
    icon:   '🔬',
    title:  `${paper} litmus paper will NOT change colour`,
    detail,
    color:  '#a3a3a3',
  };
}

// ── Reaction reveal message (shown after reaction fires) ──────────────────────
function buildRevealMessage(chemical, reactionType) {
  if (!chemical) return null;
  const { label, formula, type } = chemical;
  const paperColor = reactionType === 'red_litmus' ? 'Red' : 'Blue';
  if (type === 'neutral') {
    return {
      headline: 'No Reaction Observed',
      body: `The ${paperColor} Litmus paper did not change colour because ${label} (${formula}) is a neutral substance — it has no acidic or basic properties to trigger a reaction.`,
      verdict: 'NEUTRAL',
      color: '#a3a3a3',
    };
  }
  if (type === 'acid' && reactionType === 'blue_litmus') {
    return {
      headline: 'Acid Detected!',
      body: `The Blue Litmus paper turned Red because ${label} (${formula}) is an acid. Acids donate protons (H⁺), which causes blue litmus to change colour.`,
      verdict: 'ACID CONFIRMED',
      color: '#f87171',
    };
  }
  if (type === 'base' && reactionType === 'red_litmus') {
    return {
      headline: 'Base Detected!',
      body: `The Red Litmus paper turned Blue because ${label} (${formula}) is a base. Bases accept protons (OH⁻), which causes red litmus to change colour.`,
      verdict: 'BASE CONFIRMED',
      color: '#38bdf8',
    };
  }
  const typeLabel = type === 'acid' ? 'an acid' : 'a base';
  return {
    headline: 'No Change — Wrong Litmus',
    body: `${label} (${formula}) is ${typeLabel}, but this test used ${paperColor} Litmus. To observe a colour change, use ${type === 'acid' ? 'Blue' : 'Red'} Litmus with this substance.`,
    verdict: 'NO CHANGE',
    color: '#fbbf24',
  };
}

function getWsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host  = import.meta.env.VITE_WS_HOST || window.location.host;
  return `${proto}://${host}/ws/lab/`;
}

const FRAME_W = 640;
const FRAME_H = 480;

// ── Styles ────────────────────────────────────────────────────────────────────
const s = {
  page:          { minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-start', padding: '1.5rem', gap: '1rem', paddingTop: '2rem' },
  topBar:        { display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', maxWidth: '820px' },
  backBtn:       { background: 'none', border: '1px solid var(--border)', color: 'var(--text-muted)', padding: '0.45rem 1.1rem', borderRadius: '3px', fontSize: '0.72rem', fontFamily: 'var(--mono)', letterSpacing: '0.1em', textTransform: 'uppercase', cursor: 'pointer' },
  statusRow:     { display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.7rem', fontFamily: 'var(--mono)', letterSpacing: '0.1em', textTransform: 'uppercase' },
  liveDot:       { width: '7px', height: '7px', borderRadius: '50%', animation: 'pulse 1.5s ease-in-out infinite' },
  bubbleSection: { width: '100%', maxWidth: '820px' },
  bubbleLabel:   { fontSize: '0.62rem', fontFamily: 'var(--mono)', color: 'var(--text-muted)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: '0.6rem', display: 'block' },
  bubbleRow:     { display: 'flex', flexWrap: 'wrap', gap: '0.5rem' },
  bubble:        (active, loading) => ({
    padding: '0.38rem 0.9rem', borderRadius: '999px',
    border: `1px solid ${active ? 'var(--accent-blue)' : 'rgba(255,255,255,0.12)'}`,
    background: active ? 'rgba(56,189,248,0.12)' : 'transparent',
    color: active ? 'var(--accent-blue)' : 'var(--text-muted)',
    fontSize: '0.78rem', fontFamily: 'var(--mono)',
    cursor: loading ? 'wait' : 'pointer', transition: 'all 0.15s ease',
    letterSpacing: '0.04em', opacity: loading ? 0.5 : 1, whiteSpace: 'nowrap',
  }),
  streamCard:    { width: '100%', maxWidth: '820px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden', boxShadow: 'var(--glow-blue)' },
  windowBar:     { display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.55rem 1rem', borderBottom: '1px solid var(--border)' },
  wDot:          (c) => ({ width: '10px', height: '10px', borderRadius: '50%', background: c, opacity: 0.7 }),
  wTitle:        { marginLeft: 'auto', fontSize: '0.62rem', fontFamily: 'var(--mono)', color: 'var(--text-muted)', letterSpacing: '0.12em', textTransform: 'uppercase' },
  canvas:        { display: 'block', width: '100%', minHeight: '280px', background: '#000' },

  // Reaction hint panel — shown as soon as a chemical is selected
  hintPanel:     (color) => ({
    width: '100%', maxWidth: '820px',
    border: `1px solid ${color}44`,
    borderRadius: '6px',
    background: `${color}09`,
    overflow: 'hidden',
    animation: 'hintFade 0.3s ease',
  }),
  hintHeader:    (color, reacts) => ({
    display: 'flex', alignItems: 'center', gap: '0.6rem',
    padding: '0.6rem 1rem',
    background: `${color}${reacts ? '18' : '0d'}`,
    borderBottom: `1px solid ${color}33`,
  }),
  hintIcon:      { fontSize: '1rem', lineHeight: 1 },
  hintTitle:     (color) => ({
    fontSize: '0.8rem', fontWeight: 700, color,
    fontFamily: 'var(--sans)', letterSpacing: '0.01em', flexGrow: 1,
  }),
  hintBadge:     (color, reacts) => ({
    fontSize: '0.58rem', fontFamily: 'var(--mono)', color,
    letterSpacing: '0.18em', textTransform: 'uppercase',
    padding: '0.15rem 0.55rem',
    border: `1px solid ${color}55`, borderRadius: '999px',
    background: reacts ? `${color}22` : 'transparent',
  }),
  hintDetail:    { padding: '0.7rem 1rem', fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.65, fontFamily: 'var(--sans)' },

  // Reveal banner — shown after reaction fires
  revealBanner:  (c) => ({ width: '100%', maxWidth: '820px', background: 'var(--surface)', border: `1px solid ${c}55`, borderRadius: '6px', overflow: 'hidden', animation: 'fadeSlideUp 0.5s ease, revealGlow 1.2s ease' }),
  revealHeader:  (c) => ({ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.7rem 1.2rem', background: `${c}12`, borderBottom: `1px solid ${c}33` }),
  revealHeadline:(c) => ({ fontSize: '0.85rem', fontWeight: 700, color: c, fontFamily: 'var(--sans)', letterSpacing: '0.01em' }),
  revealVerdict: (c) => ({ fontSize: '0.62rem', fontFamily: 'var(--mono)', color: c, letterSpacing: '0.18em', textTransform: 'uppercase', padding: '0.2rem 0.6rem', border: `1px solid ${c}55`, borderRadius: '999px' }),
  revealBody:    { padding: '0.9rem 1.2rem', fontSize: '0.85rem', color: 'var(--text-primary)', lineHeight: 1.65, fontFamily: 'var(--sans)' },
  hint:          { fontSize: '0.68rem', fontFamily: 'var(--mono)', color: 'var(--text-muted)', letterSpacing: '0.06em' },
};

// ── Component ─────────────────────────────────────────────────────────────────
export default function Lab() {
  const navigate   = useNavigate();
  const stopCalled = useRef(false);
  const pollRef    = useRef(null);

  const wsRef         = useRef(null);
  const streamRef     = useRef(null);
  const videoRef      = useRef(null);
  const canvasRef     = useRef(null);
  const offCanvasRef  = useRef(null);
  const wsReady       = useRef(false);
  const frameTimerRef = useRef(null);
  const sendingRef    = useRef(false);

  // Refs so WS callbacks always read the latest value without stale closures.
  const reactionTypeRef = useRef(null);
  const activeChemRef   = useRef(null);

  const [chemicals,    setChemicals]    = useState([]);
  const [activeId,     setActiveId]     = useState(null);
  const [activeChem,   setActiveChem]   = useState(null);   // full object incl. type/formula
  const [loadingChem,  setLoadingChem]  = useState(null);
  const [revealData,   setRevealData]   = useState(null);
  const [reactionType, setReactionType] = useState(null);
  const [wsStatus,     setWsStatus]     = useState('connecting');

  // Keep refs in sync with state.
  useEffect(() => { reactionTypeRef.current = reactionType; }, [reactionType]);
  useEffect(() => { activeChemRef.current   = activeChem;   }, [activeChem]);

  // Derived: hint panel data (recomputed whenever chemical or reaction type changes)
  const reactionHint = (!revealData && activeChem && reactionType)
    ? getReactionHint(activeChem.type, reactionType)
    : null;

  // ── WebSocket helper ────────────────────────────────────────────────────────
  const wsSend = useCallback((payload) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  // ── Camera + WebSocket pipeline ─────────────────────────────────────────────
  const startPipeline = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: FRAME_W, height: FRAME_H },
        audio: false,
      });
      streamRef.current = stream;

      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();

      const off  = document.createElement('canvas');
      off.width  = FRAME_W;
      off.height = FRAME_H;
      offCanvasRef.current = off;

      const ws      = new WebSocket(getWsUrl());
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      function sendFrame() {
        if (!wsReady.current || ws.readyState !== WebSocket.OPEN || sendingRef.current) return;
        sendingRef.current = true;
        const ctx = off.getContext('2d');
        ctx.drawImage(video, 0, 0, FRAME_W, FRAME_H);
        off.toBlob((blob) => {
          if (!blob) { sendingRef.current = false; return; }
          blob.arrayBuffer().then((buf) => {
            if (ws.readyState === WebSocket.OPEN) ws.send(buf);
            sendingRef.current = false;
          });
        }, 'image/jpeg', 0.5);
      }

      ws.onopen = () => {
        wsReady.current = true;
        setWsStatus('live');

        // Push current reaction type and chemical into the consumer immediately.
        const rt = reactionTypeRef.current;
        if (rt) ws.send(JSON.stringify({ type: 'set_reaction', reaction_type: rt }));
        const ac = activeChemRef.current;
        if (ac) ws.send(JSON.stringify({ type: 'set_chemical', chemical_id: ac.id }));

        frameTimerRef.current = setInterval(sendFrame, 66);
      };

      ws.onmessage = (evt) => {
        // ── Text: JSON event from consumer ──────────────────────────────────
        if (typeof evt.data === 'string') {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.type === 'reaction_complete') {
              clearInterval(pollRef.current);
              const chemical = msg.chemical || activeChemRef.current;
              const rt       = msg.reaction_type || reactionTypeRef.current;
              setRevealData(buildRevealMessage(chemical, rt));
            }
          } catch { /* not JSON */ }
          return;
        }
        // ── Binary: processed video frame ───────────────────────────────────
        createImageBitmap(new Blob([evt.data], { type: 'image/jpeg' })).then((bitmap) => {
          const canvas = canvasRef.current;
          if (canvas) {
            canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            bitmap.close();
          }
        });
      };

      ws.onerror = () => setWsStatus('error');
      ws.onclose = () => { wsReady.current = false; setWsStatus('error'); };

    } catch (err) {
      console.error('Camera / WebSocket error:', err);
      setWsStatus('error');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const stopPipeline = useCallback(() => {
    wsReady.current = false;
    if (frameTimerRef.current) { clearInterval(frameTimerRef.current); frameTimerRef.current = null; }
    if (wsRef.current)         { wsRef.current.close(); wsRef.current = null; }
    if (streamRef.current)     { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
  }, []);

  // ── Mount ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    api.get('/reactions/chemicals/')
      .then((r) => setChemicals(r.data.chemicals))
      .catch(() => {});

    api.get('/reactions/current/')
      .then((r) => setReactionType(r.data.active_reaction))
      .catch(() => {});

    startPipeline();
    return () => stopPipeline();
  }, [startPipeline, stopPipeline]);

  // When reactionType resolves (async GET), sync to consumer — covers the
  // race where WS connects before the GET response arrives.
  useEffect(() => {
    if (!reactionType) return;
    wsSend({ type: 'set_reaction', reaction_type: reactionType });
  }, [reactionType, wsSend]);

  // ── Polling fallback (safety net if WS push message is lost) ────────────────
  useEffect(() => {
    pollRef.current = setInterval(async () => {
      if (revealData) { clearInterval(pollRef.current); return; }
      try {
        const { data } = await api.get('/reactions/status/');
        if (data.complete) {
          clearInterval(pollRef.current);
          setRevealData(buildRevealMessage(
            data.chemical || activeChemRef.current,
            data.reaction_type || reactionTypeRef.current,
          ));
        }
      } catch { /* ignore */ }
    }, 1000);
    return () => clearInterval(pollRef.current);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Chemical bubble click ───────────────────────────────────────────────────
  const handleSelectChemical = async (chem) => {
    if (loadingChem || revealData) return;
    setLoadingChem(chem.id);
    setRevealData(null);
    try {
      await api.post('/reactions/set-chemical/', { chemical_id: chem.id });
      setActiveId(chem.id);
      setActiveChem(chem);   // store full object (type + formula from /chemicals/)
      // Layer 1 fix: push state directly into consumer over the open WS.
      wsSend({ type: 'set_chemical', chemical_id: chem.id });
    } catch (err) {
      console.error('set-chemical failed:', err);
    } finally {
      setLoadingChem(null);
    }
  };

  // ── Back ────────────────────────────────────────────────────────────────────
  const handleBack = async () => {
    if (stopCalled.current) return;
    stopCalled.current = true;
    clearInterval(pollRef.current);
    stopPipeline();
    try { await api.post('/reactions/stop/'); } finally { navigate('/dashboard'); }
  };

  useEffect(() => {
    const onUnload = () =>
      navigator.sendBeacon(
        '/api/reactions/stop/',
        new Blob([JSON.stringify({})], { type: 'application/json' }),
      );
    window.addEventListener('beforeunload', onUnload);
    return () => {
      window.removeEventListener('beforeunload', onUnload);
      if (!stopCalled.current) {
        stopCalled.current = true;
        clearInterval(pollRef.current);
        stopPipeline();
        api.post('/reactions/stop/').catch(() => {});
      }
    };
  }, [stopPipeline]);

  // ── Render ──────────────────────────────────────────────────────────────────
  const statusColor = wsStatus === 'live'  ? 'var(--accent-green)'
                    : wsStatus === 'error' ? '#f87171'
                    : '#fbbf24';
  const statusLabel = wsStatus === 'live'  ? 'Live Stream'
                    : wsStatus === 'error' ? 'Connection Error'
                    : 'Connecting…';

  return (
    <div style={s.page}>
      <video ref={videoRef} style={{ display: 'none' }} playsInline muted />

      {/* Top bar */}
      <div style={s.topBar}>
        <button style={s.backBtn} onClick={handleBack}>← Back</button>
        <div style={{ ...s.statusRow, color: statusColor }}>
          <span style={{ ...s.liveDot, background: statusColor }} />
          {statusLabel}
        </div>
      </div>

      {/* Chemical bubbles */}
      <div style={s.bubbleSection}>
        <span style={s.bubbleLabel}>// Select substance for the test tube</span>
        <div style={s.bubbleRow}>
          {chemicals.length === 0 && (
            <span style={{ ...s.bubble(false, false), cursor: 'default' }}>Loading…</span>
          )}
          {chemicals.map((c) => (
            <button
              key={c.id}
              style={s.bubble(activeId === c.id, loadingChem === c.id)}
              onClick={() => handleSelectChemical(c)}
              disabled={!!loadingChem || !!revealData}
              title={c.label}
            >
              {c.id}
            </button>
          ))}
        </div>
      </div>

      {/* Video stream */}
      <div style={s.streamCard}>
        <div style={s.windowBar}>
          <span style={s.wDot('#f87171')} />
          <span style={s.wDot('#fbbf24')} />
          <span style={s.wDot('#4ade80')} />
          <span style={s.wTitle}>
            {activeId ? `// loaded: ${activeId}` : '// webcam feed — select a substance'}
          </span>
        </div>
        <canvas ref={canvasRef} width={FRAME_W} height={FRAME_H} style={s.canvas} />
      </div>

      {/* ── Reaction hint panel ──────────────────────────────────────────────
           Shown as soon as a chemical is selected, hidden once reveal fires.
           Covers all 6 combinations: 2 litmus × 3 chemical types.        */}
      {reactionHint && !revealData && (
        <div style={s.hintPanel(reactionHint.color)}>
          <div style={s.hintHeader(reactionHint.color, reactionHint.reacts)}>
            <span style={s.hintIcon}>{reactionHint.icon}</span>
            <span style={s.hintTitle(reactionHint.color)}>{reactionHint.title}</span>
            <span style={s.hintBadge(reactionHint.color, reactionHint.reacts)}>
              {reactionHint.reacts ? 'WILL REACT' : 'NO REACTION'}
            </span>
          </div>
          <p style={s.hintDetail}>{reactionHint.detail}</p>
        </div>
      )}

      {/* ── Reveal banner ────────────────────────────────────────────────────
           Replaces the hint panel once the reaction actually triggers.     */}
      {revealData && (
        <div style={s.revealBanner(revealData.color)}>
          <div style={s.revealHeader(revealData.color)}>
            <span style={s.revealHeadline(revealData.color)}>{revealData.headline}</span>
            <span style={s.revealVerdict(revealData.color)}>{revealData.verdict}</span>
          </div>
          <p style={s.revealBody}>{revealData.body}</p>
        </div>
      )}

      <p style={s.hint}>
        {revealData
          ? 'Click ← Back to run another experiment.'
          : activeChem
          ? 'Tilt your hand to pour the substance onto the litmus paper.'
          : 'Select a substance above · tilt hand to pour · watch the litmus paper.'}
      </p>
    </div>
  );
}