// src/components/Lab.jsx
// Place in: frontend/src/components/Lab.jsx — REPLACE existing file entirely.
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

// ── Styles ────────────────────────────────────────────────────────────────────
const s = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '1.5rem',
    gap: '1.25rem',
  },
  topBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    maxWidth: '960px',
  },
  backBtn: {
    background: 'none',
    border: '1px solid var(--border)',
    color: 'var(--text-muted)',
    padding: '0.45rem 1.1rem',
    borderRadius: '3px',
    fontSize: '0.72rem',
    fontFamily: 'var(--mono)',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    cursor: 'pointer',
    transition: 'color 0.2s, border-color 0.2s',
  },
  statusDot: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: '0.7rem',
    fontFamily: 'var(--mono)',
    color: 'var(--accent-green)',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
  },
  liveDot: {
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    background: 'var(--accent-green)',
    animation: 'pulse 1.5s ease-in-out infinite',
  },
  layout: {
    display: 'flex',
    gap: '1.25rem',
    width: '100%',
    maxWidth: '960px',
    alignItems: 'flex-start',
  },
  streamCard: {
    flex: '1 1 auto',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    overflow: 'hidden',
    boxShadow: 'var(--glow-blue)',
  },
  windowBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.4rem',
    padding: '0.55rem 1rem',
    borderBottom: '1px solid var(--border)',
  },
  wDot: (c) => ({
    width: '10px', height: '10px', borderRadius: '50%',
    background: c, opacity: 0.7,
  }),
  wTitle: {
    marginLeft: 'auto',
    fontSize: '0.62rem',
    fontFamily: 'var(--mono)',
    color: 'var(--text-muted)',
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
  },
  stream: {
    display: 'block',
    width: '100%',
    minHeight: '300px',
    background: '#000',
  },
  // ── Chemical selector panel ───────────────────────────────────────────────
  selectorPanel: {
    width: '220px',
    flexShrink: 0,
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: '6px',
    overflow: 'hidden',
  },
  panelHeader: {
    padding: '0.75rem 1rem',
    borderBottom: '1px solid var(--border)',
    fontSize: '0.62rem',
    fontFamily: 'var(--mono)',
    color: 'var(--accent-blue)',
    letterSpacing: '0.15em',
    textTransform: 'uppercase',
  },
  panelBody: {
    padding: '0.75rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.4rem',
  },
  groupLabel: {
    fontSize: '0.6rem',
    fontFamily: 'var(--mono)',
    color: 'var(--text-muted)',
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    padding: '0.35rem 0 0.15rem',
  },
  chemBtn: (active, type) => {
    const accent =
      type === 'acid'    ? '#f87171' :
      type === 'base'    ? '#38bdf8' :
                           '#a3a3a3';
    return {
      width: '100%',
      padding: '0.5rem 0.75rem',
      background: active ? `${accent}18` : 'transparent',
      border: `1px solid ${active ? accent : 'var(--border)'}`,
      borderRadius: '4px',
      color: active ? accent : 'var(--text-muted)',
      fontSize: '0.78rem',
      fontFamily: 'var(--mono)',
      textAlign: 'left',
      cursor: 'pointer',
      transition: 'all 0.15s',
      letterSpacing: '0.04em',
    };
  },
  chemType: (type) => ({
    fontSize: '0.6rem',
    fontFamily: 'var(--mono)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: type === 'acid' ? '#f87171' : type === 'base' ? '#38bdf8' : '#a3a3a3',
    float: 'right',
    marginTop: '1px',
  }),
  noChemHint: {
    fontSize: '0.68rem',
    fontFamily: 'var(--mono)',
    color: 'var(--text-muted)',
    padding: '0.5rem 0',
    textAlign: 'center',
    fontStyle: 'italic',
  },
  hint: {
    fontSize: '0.7rem',
    fontFamily: 'var(--mono)',
    color: 'var(--text-muted)',
    letterSpacing: '0.06em',
  },
};

// Inject pulse keyframe once
if (!document.getElementById('lab-pulse-style')) {
  const tag = document.createElement('style');
  tag.id = 'lab-pulse-style';
  tag.textContent = `@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`;
  document.head.appendChild(tag);
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function Lab() {
  const navigate = useNavigate();
  const stopCalled = useRef(false);

  const [chemicals, setChemicals]           = useState([]);
  const [activeChemical, setActiveChemical] = useState(null);
  const [loadingChem, setLoadingChem]       = useState(null);

  // Fetch chemical list on mount
  useEffect(() => {
    api.get('/reactions/chemicals/')
      .then((res) => setChemicals(res.data.chemicals))
      .catch(() => {});  // silent fail — stream still works
  }, []);

  const handleSelectChemical = async (chem) => {
    if (loadingChem) return;
    setLoadingChem(chem.id);
    try {
      await api.post('/reactions/set-chemical/', { chemical_id: chem.id });
      setActiveChemical(chem.id);
    } catch {
      // Keep previous selection if the call fails
    } finally {
      setLoadingChem(null);
    }
  };

  const handleBack = async () => {
    if (stopCalled.current) return;
    stopCalled.current = true;
    try { await api.post('/reactions/stop/'); } finally { navigate('/dashboard'); }
  };

  // Stop on tab close / refresh
  useEffect(() => {
    const onUnload = () =>
      navigator.sendBeacon(
        'http://localhost:8000/api/reactions/stop/',
        new Blob([JSON.stringify({})], { type: 'application/json' }),
      );
    window.addEventListener('beforeunload', onUnload);
    return () => {
      window.removeEventListener('beforeunload', onUnload);
      if (!stopCalled.current) {
        stopCalled.current = true;
        api.post('/reactions/stop/').catch(() => {});
      }
    };
  }, []);

  // Group chemicals for display
  const acids    = chemicals.filter((c) => c.type === 'acid');
  const bases    = chemicals.filter((c) => c.type === 'base');
  const neutrals = chemicals.filter((c) => c.type === 'neutral');

  return (
    <div style={s.page}>
      {/* Top bar */}
      <div style={s.topBar}>
        <button style={s.backBtn} onClick={handleBack}>← Back</button>
        <div style={s.statusDot}>
          <span style={s.liveDot} />
          Live Stream
        </div>
      </div>

      {/* Main layout: stream + selector side-by-side */}
      <div style={s.layout}>

        {/* Video stream */}
        <div style={s.streamCard}>
          <div style={s.windowBar}>
            <span style={s.wDot('#f87171')} />
            <span style={s.wDot('#fbbf24')} />
            <span style={s.wDot('#4ade80')} />
            <span style={s.wTitle}>// webcam feed</span>
          </div>
          {/*
            crossOrigin="use-credentials" is REQUIRED.
            Without it the browser strips the session cookie on cross-origin
            image requests (port 5173 → 8000) and Django returns 401.
          */}
          <img
            src="http://localhost:8000/api/reactions/video-feed/"
            crossOrigin="use-credentials"
            alt="Virtual Lab Stream"
            style={s.stream}
          />
        </div>

        {/* Chemical selector panel */}
        <div style={s.selectorPanel}>
          <div style={s.panelHeader}>// Chemical Select</div>
          <div style={s.panelBody}>
            {chemicals.length === 0 && (
              <p style={s.noChemHint}>Loading chemicals…</p>
            )}

            {acids.length > 0 && (
              <>
                <span style={s.groupLabel}>Acids</span>
                {acids.map((c) => (
                  <button
                    key={c.id}
                    style={s.chemBtn(activeChemical === c.id, c.type)}
                    onClick={() => handleSelectChemical(c)}
                    disabled={loadingChem === c.id}
                  >
                    {loadingChem === c.id ? '…' : c.id}
                    <span style={s.chemType(c.type)}>acid</span>
                  </button>
                ))}
              </>
            )}

            {bases.length > 0 && (
              <>
                <span style={s.groupLabel}>Bases</span>
                {bases.map((c) => (
                  <button
                    key={c.id}
                    style={s.chemBtn(activeChemical === c.id, c.type)}
                    onClick={() => handleSelectChemical(c)}
                    disabled={loadingChem === c.id}
                  >
                    {loadingChem === c.id ? '…' : c.id}
                    <span style={s.chemType(c.type)}>base</span>
                  </button>
                ))}
              </>
            )}

            {neutrals.length > 0 && (
              <>
                <span style={s.groupLabel}>Neutral</span>
                {neutrals.map((c) => (
                  <button
                    key={c.id}
                    style={s.chemBtn(activeChemical === c.id, c.type)}
                    onClick={() => handleSelectChemical(c)}
                    disabled={loadingChem === c.id}
                  >
                    {loadingChem === c.id ? '…' : c.id}
                    <span style={s.chemType(c.type)}>neutral</span>
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      </div>

      <p style={s.hint}>Select a chemical, then tilt your hand to pour.</p>
    </div>
  );
}