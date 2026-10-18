import React, { useEffect, useRef, useState } from 'react';
import { bitmap, normalize, PATH_NAMES, recognizeWheel, RINGS, templateUrl, wheelWord } from './codewheel.js';

function capture(screen) {
  const image = screen?.querySelector('img');
  if (!image?.naturalWidth || !image.naturalHeight) throw new Error('Wait for the live game picture.');
  if (Math.abs(image.naturalWidth / image.naturalHeight - 1.6) > .02) throw new Error('The game picture has an unsupported size. Use the manual picker.');
  const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 400;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.imageSmoothingEnabled = false;
  context.drawImage(image, 0, 0, 640, 400);
  return context.getImageData(0, 0, 640, 400);
}

async function loadTemplates(signal) {
  const result = [], names = RINGS.flatMap(ring => Array.from({ length: 36 }, (_, i) => ({ ring, number: i + 1 })));
  for (let i = 0; i < names.length; i += 6) {
    result.push(...await Promise.all(names.slice(i, i + 6).map(async item => {
      const response = await fetch(templateUrl(item.ring, item.number), { credentials: 'same-origin', signal });
      if (!response.ok) throw new Error('Rune images are unavailable. Use the numbered lookup or known-word entry.');
      const image = await createImageBitmap(await response.blob());
      try {
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const context = canvas.getContext('2d', { willReadFrequently: true }); context.drawImage(image, 0, 0);
        return { ...item, normalized: normalize(bitmap(context.getImageData(0, 0, image.width, image.height), 'template')) };
      } finally { image.close(); }
    })));
  }
  return result;
}

function RuneChoice({ ring, number, selected, onSelect }) {
  const [missing, setMissing] = useState(false);
  const name = ring === 'esp' ? 'Espruar' : 'Dethek';
  return <button type="button" className="rune-choice" aria-label={`${name} rune ${number}`} aria-pressed={selected} onClick={onSelect}>
    {missing ? <span className="rune-missing">No image</span> : <img src={templateUrl(ring, number)} alt="" loading="lazy" onError={() => setMissing(true)} />}
    <span>{number}</span>
  </button>;
}

export function CodewheelPicker({ screenRef, inputRevision, running, runKey, busy, onSend }) {
  const [a, setA] = useState(null), [b, setB] = useState(null), [path, setPath] = useState(null);
  const [open, setOpen] = useState(false), [analyzing, setAnalyzing] = useState(false), [message, setMessage] = useState('');
  const templates = useRef(null), generation = useRef(0), controller = useRef(null), inFlight = useRef(false), sent = useRef(null);
  const word = wheelWord(a, b, path), locked = busy || analyzing;
  useEffect(() => {
    generation.current++; sent.current = null; controller.current?.abort();
    return () => { generation.current++; controller.current?.abort(); };
  }, [runKey, running]);

  async function auto() {
    if (inFlight.current || busy || !running) return;
    inFlight.current = true; setAnalyzing(true); setMessage('Reading the two runes and path…');
    const ticket = ++generation.current, revision = inputRevision.current;
    controller.current = new AbortController();
    try {
      capture(screenRef.current); // Fail early if the stream has no decoded frame.
      if (!templates.current) templates.current = await loadTemplates(controller.current.signal);
      if (ticket !== generation.current) return;
      const first = recognizeWheel(capture(screenRef.current), templates.current);
      if (!first.confident) {
        setOpen(true);
        setMessage(`No typing: ${first.reason}${first.path !== null ? ` Visible path: ${PATH_NAMES[first.path]}.` : ''} Choose both runes and the path manually, or enter a known word above.`);
        return;
      }
      // Check again after assets have loaded and a second video frame can arrive.
      await new Promise(resolve => setTimeout(resolve, 180));
      if (ticket !== generation.current || revision !== inputRevision.current) {
        if (ticket === generation.current) setMessage('No typing: game input changed during recognition.');
        return;
      }
      const current = recognizeWheel(capture(screenRef.current), templates.current);
      if (!current.confident || current.signature !== first.signature) { setMessage('No typing: the rune prompt changed. Try again or use the picker.'); setOpen(true); return; }
      if (sent.current === current.signature) { setMessage('No typing: this code word was already sent for this prompt.'); return; }
      setA(current.a); setB(current.b); setPath(current.path);
      // Set before dispatch: uncertain delivery must not cause automatic retries.
      sent.current = current.signature;
      const ok = await onSend(current.word);
      if (ticket === generation.current) setMessage(ok ? `Typed ${current.word} + Enter.` : 'Delivery was not confirmed. Inspect the game before sending again.');
    } catch (error) {
      if (ticket === generation.current) { setMessage(`No typing: ${error.message}`); setOpen(true); }
    } finally { inFlight.current = false; setAnalyzing(false); }
  }

  async function manual() {
    if (!word || !running || busy || inFlight.current) return;
    inFlight.current = true;
    try { const ok = await onSend(word); setMessage(ok ? `Typed ${word} + Enter.` : 'Delivery was not confirmed. Inspect the game before sending again.'); }
    finally { inFlight.current = false; }
  }
  const numberValue = value => value === '' ? null : Number(value);
  return <section className="codewheel-panel" aria-label="Code word helper">
    <div className="game-wheel">
      <strong>Code wheel</strong>
      <button onClick={auto} disabled={locked || !running}>{analyzing ? 'Reading runes…' : 'Auto code word'}</button>
      <label>Espruar <input type="number" min="1" max="36" value={a ?? ''} onChange={e => setA(numberValue(e.target.value))} aria-label="Espruar rune number" disabled={locked} /></label>
      <label>Dethek <input type="number" min="1" max="36" value={b ?? ''} onChange={e => setB(numberValue(e.target.value))} aria-label="Dethek rune number" disabled={locked} /></label>
      <select value={path ?? ''} onChange={e => setPath(numberValue(e.target.value))} aria-label="Wheel path" disabled={locked}>
        <option value="">Choose path…</option>{PATH_NAMES.map((name, i) => <option key={i} value={i}>{name}</option>)}
      </select>
      <output className="game-wheel-word" aria-label="Computed code word">{word || '—'}</output>
      <button onClick={manual} disabled={locked || !running || !word}>Type code word</button>
    </div>
    <p className="wheel-help">For the DOS Decimer screen, use the manual wheel or known-word entry above. Auto only types when both wheel runes and the path match clearly.</p>
    {message && <p className="wheel-result" role="status">{message}</p>}
    <details className="wheel-picker" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
      <summary>Visual rune picker</summary>
      <div className="wheel-rings">{RINGS.map(ring => <fieldset key={ring} disabled={locked}>
        <legend>{ring === 'esp' ? 'Espruar · outer ring' : 'Dethek · inner ring'}</legend>
        <div className="rune-grid">{Array.from({ length: 36 }, (_, i) => <RuneChoice key={i} ring={ring} number={i + 1} selected={(ring === 'esp' ? a : b) === i + 1} onSelect={() => (ring === 'esp' ? setA : setB)(i + 1)} />)}</div>
      </fieldset>)}</div>
    </details>
  </section>;
}
