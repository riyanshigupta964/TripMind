import React, { useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { motion } from 'framer-motion';
import { Plane, MapPin, CalendarDays, Users, Wallet, Sparkles, Compass, CloudSun, Hotel, Route, LoaderCircle, AlertCircle } from 'lucide-react';
import './styles.css';

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const choices = ['Nature', 'Food', 'Adventure', 'Culture', 'Beaches', 'Shopping', 'Relaxation'];
function App() {
  const [form, setForm] = useState({origin:'Bhopal, India', destination:'Goa, India', start_date:'2026-11-15', end_date:'2026-11-18', travelers:2, budget_inr:100000, vibe:'balanced', preferences:['Beaches','Food']});
  const [loading, setLoading] = useState(false), [error, setError] = useState(''), [plan, setPlan] = useState(null), [health, setHealth] = useState('checking');
  useEffect(() => { fetch(`${API}/api/health`).then(r=>r.ok?r.json():Promise.reject()).then(()=>setHealth('online')).catch(()=>setHealth('offline')); }, []);
  const update = (k,v) => setForm(p=>({...p,[k]:v}));
  const toggle = x => update('preferences', form.preferences.includes(x) ? form.preferences.filter(v=>v!==x) : [...form.preferences,x]);
  async function submit(e) { e.preventDefault(); setLoading(true); setError(''); setPlan(null); try { const r=await fetch(`${API}/api/plan`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...form, travelers:Number(form.travelers), budget_inr:Number(form.budget_inr)})}); const data=await r.json(); if(!r.ok) throw new Error(data.detail || 'Unable to generate the trip.'); setPlan(data.plan); } catch(err) { setError(err.message==='Failed to fetch'?'Cannot connect to FastAPI. Start the backend on port 8000.':err.message); } finally {setLoading(false);} }
  const pretty = (v) => typeof v==='string'?v:JSON.stringify(v,null,2);
  return <div className="app-shell"><nav className="nav"><a className="brand" href="#top"><span className="brand-icon"><Compass size={22}/></span>TripMind<span className="ai-tag">AI</span></a><span className={`status ${health}`}><i/>API {health}</span></nav>
    <main id="top"><section className="hero"><motion.div initial={{opacity:0,y:14}} animate={{opacity:1,y:0}} transition={{duration:.45}}><div className="eyebrow"><Sparkles size={15}/> YOUR NEXT ADVENTURE, PERSONALIZED</div><h1>Travel smarter.<br/><em>Feel every moment.</em></h1><p>Build a thoughtful itinerary around your budget, your dates, and your kind of adventure.</p><div className="hero-points"><span><Plane size={16}/> Flight research</span><span><Hotel size={16}/> Stay options</span><span><CloudSun size={16}/> Weather-aware plans</span></div></motion.div><div className="hero-art" aria-hidden="true"><div className="sun"/><div className="hill hill-back"/><div className="hill hill-front"/><div className="art-label"><MapPin size={15}/> YOUR STORY STARTS HERE</div></div></section>
    <section className="planner"><div className="section-title"><div><span className="step">01 / PLAN YOUR TRIP</span><h2>Where are we going?</h2><p>Tell us a little about your trip. We'll handle the planning.</p></div><span className="round-icon"><Route/></span></div>
    <form onSubmit={submit}><div className="fields two"><label><span><MapPin size={15}/> From</span><input required minLength="2" value={form.origin} onChange={e=>update('origin',e.target.value)} placeholder="City or airport"/></label><label><span><MapPin size={15}/> To</span><input required minLength="2" value={form.destination} onChange={e=>update('destination',e.target.value)} placeholder="Destination"/></label></div>
    <div className="fields two"><label><span><CalendarDays size={15}/> Departure</span><input type="date" required value={form.start_date} min={new Date().toISOString().slice(0,10)} onChange={e=>update('start_date',e.target.value)}/></label><label><span><CalendarDays size={15}/> Return</span><input type="date" required value={form.end_date} min={form.start_date} onChange={e=>update('end_date',e.target.value)}/></label></div>
    <div className="fields two"><label><span><Users size={15}/> Travellers</span><input type="number" min="1" max="20" required value={form.travelers} onChange={e=>update('travelers',e.target.value)}/></label><label><span><Wallet size={15}/> Total budget (₹)</span><input type="number" min="1" required value={form.budget_inr} onChange={e=>update('budget_inr',e.target.value)}/></label></div>
    <div className="choice-block"><label className="field-heading">What's your travel vibe?</label><div className="vibes">{['balanced','slow & relaxing','adventure','luxury','budget-friendly'].map(v=><button type="button" key={v} className={form.vibe===v?'vibe selected':'vibe'} onClick={()=>update('vibe',v)}>{v}</button>)}</div></div>
    <div className="choice-block"><label className="field-heading">What are you into? <small>Choose any</small></label><div className="chips">{choices.map(c=><button type="button" key={c} className={form.preferences.includes(c)?'chip active':'chip'} onClick={()=>toggle(c)}>{c}</button>)}</div></div>
    {error && <div className="error"><AlertCircle size={18}/><span>{error}</span></div>}<button className="submit" disabled={loading}>{loading?<><LoaderCircle className="spin" size={18}/> Creating your trip...</>:<><Sparkles size={18}/> Create my itinerary <span>→</span></>}</button><p className="privacy">Your plan is generated by the TripMind backend. Live provider limits may affect availability.</p></form></section>
    {plan && <section className="result"><div className="result-head"><span className="step">02 / YOUR TRIP PLAN</span><h2>Your adventure, taking shape.</h2></div><pre>{pretty(plan)}</pre></section>}
    <footer><span className="brand small"><Compass size={17}/> TripMind</span><span>Thoughtful travel, powered by AI.</span></footer></main></div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
