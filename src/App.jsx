import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import {
  AppBar, Toolbar, Typography, Box, Paper, Button, Chip,
  CircularProgress, Divider, Stack, LinearProgress,
  TextField, Avatar, Dialog, DialogTitle, DialogContent, DialogActions,
  Collapse, IconButton,
} from '@mui/material';
import { createTheme, ThemeProvider } from '@mui/material/styles';

const API_BASE = 'http://localhost:8000';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#00e5ff' },
    secondary: { main: '#69ff47' },
    success: { main: '#69ff47' },
    warning: { main: '#ffb300' },
    error: { main: '#ff1744' },
    background: { default: '#0a0e1a', paper: '#111827' },
  },
  typography: { fontFamily: '"Roboto Mono", "Consolas", monospace', fontSize: 13 },
  components: {
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiDivider: { styleOverrides: { root: { borderColor: '#1e2d4a' } } },
  },
});

const FLOW_COLOR = {
  idle: 'default', requested: 'warning', accepted: 'info',
  completed: 'success', rejected: 'error',
};
const FLOW_STEPS = ['idle', 'requested', 'accepted', 'completed'];

function PowerBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
        <Typography variant="caption" sx={{ color: '#888' }}>{label}</Typography>
        <Typography variant="caption" sx={{ fontWeight: 700 }}>{(value / 1000).toFixed(2)} kW</Typography>
      </Box>
      <LinearProgress variant="determinate" value={pct} color={color || 'primary'}
        sx={{ height: 7, borderRadius: 4, bgcolor: 'rgba(255,255,255,0.07)' }} />
    </Box>
  );
}

function ChatBubble({ msg }) {
  const clr = { bap: '#00e5ff', bpp: '#69ff47', system: '#ffb300' };
  return (
    <Box sx={{ mb: 1, display: 'flex', gap: 1, alignItems: 'flex-start' }}>
      <Avatar sx={{ width: 22, height: 22, fontSize: 9, bgcolor: clr[msg.sender] || '#555', color: '#000' }}>
        {msg.sender.slice(0, 3).toUpperCase()}
      </Avatar>
      <Box>
        <Typography variant="caption" sx={{ color: clr[msg.sender] || '#888', fontWeight: 700 }}>
          {msg.sender.toUpperCase()} · {msg.timestamp}
        </Typography>
        <Typography variant="body2" sx={{ fontSize: 11, lineHeight: 1.4 }}>{msg.text}</Typography>
      </Box>
    </Box>
  );
}

function SectionTitle({ children, color }) {
  return (
    <Typography variant="overline"
      sx={{ color: color || '#00e5ff', letterSpacing: 2, fontSize: 10, fontWeight: 700 }}>
      {children}
    </Typography>
  );
}

function CycleCard({ c }) {
  const [open, setOpen] = useState(false);
  const hasTrades = (c.trades?.length || 0) > 0;
  return (
    <Box sx={{
      mb: 1, bgcolor: '#0d1528', borderRadius: 1,
      borderLeft: '3px solid ' + (hasTrades ? '#69ff47' : '#2e3a50'),
      overflow: 'hidden',
    }}>
      <Box
        onClick={() => setOpen(o => !o)}
        sx={{
          p: 1.5, cursor: 'pointer',
          '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' },
        }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="caption" sx={{ fontWeight: 700, color: '#69ff47', minWidth: 60 }}>
            Cycle #{c.cycle}
          </Typography>
          <Typography variant="caption" sx={{ color: '#888' }}>
            {c.time_block?.label || ''}
          </Typography>
          <Chip label={(c.trades?.length || 0) + ' trades'} size="small" sx={{ fontSize: 10 }}
            color={hasTrades ? 'success' : 'default'} />
          <Typography variant="caption"
            sx={{ color: '#00e5ff', fontWeight: 700, minWidth: 90, textAlign: 'right' }}>
            {(c.cycle_trade_volume_kwh || 0).toFixed(5)} kWh
          </Typography>
          <Typography variant="caption" sx={{ color: '#444', ml: 0.5 }}>
            {open ? '▲' : '▼'}
          </Typography>
        </Stack>
        {c.telemetry && (
          <Typography variant="caption" sx={{ color: '#444', mt: 0.3, display: 'block' }}>
            {'Gen: ' + (c.telemetry.total_generation_w / 1000).toFixed(2) + 'kW · ' +
             'Demand: ' + (c.telemetry.demand_w / 1000).toFixed(2) + 'kW · ' +
             'Excess: ' + (c.telemetry.excess_power_w / 1000).toFixed(2) + 'kW · ' +
             'Avail: ' + (c.telemetry.available_for_trading_w / 1000).toFixed(2) + 'kW'}
          </Typography>
        )}
      </Box>
      <Collapse in={open}>
        <Divider sx={{ borderColor: '#1e2d4a' }} />
        <Box sx={{ p: 1.5, pt: 1 }}>
          {hasTrades ? c.trades.map((t, i) => (
            <Box key={i} sx={{
              mb: 0.8, p: 1, bgcolor: '#0a0e1a', borderRadius: 1,
              borderLeft: '2px solid #69ff47',
            }}>
              <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 0.5 }}>
                {t.trade_id && (
                  <Typography variant="caption" sx={{ color: '#a78bfa', fontWeight: 700 }}>
                    {t.trade_id}
                  </Typography>
                )}
                {t.seller && (
                  <Typography variant="caption">
                    <span style={{ color: '#555' }}>Seller: </span>
                    <span style={{ color: '#69ff47' }}>{t.seller}</span>
                  </Typography>
                )}
                {t.buyer && (
                  <Typography variant="caption">
                    <span style={{ color: '#555' }}>Buyer: </span>
                    <span style={{ color: '#00e5ff' }}>{t.buyer}</span>
                  </Typography>
                )}
                {t.energy_kwh != null && (
                  <Typography variant="caption">
                    <span style={{ color: '#555' }}>Energy: </span>
                    <span style={{ color: '#fff', fontWeight: 700 }}>{Number(t.energy_kwh).toFixed(5)} kWh</span>
                  </Typography>
                )}
                {t.price_usd != null && (
                  <Typography variant="caption">
                    <span style={{ color: '#555' }}>Price: </span>
                    <span style={{ color: '#ffb300', fontWeight: 700 }}>${Number(t.price_usd).toFixed(4)}</span>
                  </Typography>
                )}
                {t.status && (
                  <Chip label={t.status} size="small"
                    color={t.status === 'completed' ? 'success' : t.status === 'rejected' ? 'error' : 'default'}
                    sx={{ fontSize: 9, height: 16 }} />
                )}
              </Stack>
              {t.time_block?.label && (
                <Typography variant="caption" sx={{ color: '#555', display: 'block' }}>
                  Block: {t.time_block.label}
                </Typography>
              )}
              {t.explainability && Object.keys(t.explainability).length > 0 && (
                <Typography variant="caption" sx={{ color: '#444', display: 'block', mt: 0.3 }}>
                  {JSON.stringify(t.explainability)}
                </Typography>
              )}
            </Box>
          )) : (
            <Typography variant="caption" sx={{ color: '#444' }}>No trades in this cycle</Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

export default function App() {
  const [simStatus, setSimStatus] = useState({ running: false, cycles: 0 });
  const [simData, setSimData] = useState([]);
  const [trading, setTrading] = useState({
    trade_flow: 'idle', payment_status: 'not-started',
    current_offer: null, activity_log: [], chat_messages: [],
  });
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState({});
  const [chatInput, setChatInput] = useState('');
  const [chatSender, setChatSender] = useState('bap');
  const [reqDialog, setReqDialog] = useState(false);
  const [reqForm, setReqForm] = useState({
    seller: 'DER_1', buyer: 'BAP_1',
    energy_kwh: '0.75', price_usd: '0.045', time_block: '14:00-14:15',
  });
  const chatEndRef = useRef(null);

  const set = (k, v) => setBusy(b => ({ ...b, [k]: v }));

  const refreshTrading = () =>
    axios.get(`${API_BASE}/trading/state`).then(r => setTrading(r.data)).catch(() => {});

  // SSE real-time updates
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/events`);
    es.onmessage = e => {
      try {
        const d = JSON.parse(e.data);
        if (d.simulation_status) setSimStatus(d.simulation_status);
        if (d.latest_cycle) {
          setSimData(prev => {
            const exists = prev.find(c => c.cycle === d.latest_cycle.cycle);
            return exists
              ? prev.map(c => c.cycle === d.latest_cycle.cycle ? d.latest_cycle : c)
              : [...prev, d.latest_cycle];
          });
        }
      } catch {}
    };
    return () => es.close();
  }, []);

  // Poll trading state
  useEffect(() => {
    refreshTrading();
    const id = setInterval(refreshTrading, 1500);
    return () => clearInterval(id);
  }, []);

  // Health check
  useEffect(() => {
    const check = () =>
      axios.get(`${API_BASE}/health`)
        .then(() => setHealth('ok'))
        .catch(() => setHealth('error'));
    check();
    const id = setInterval(check, 10000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [trading.chat_messages]);

  const startSim = async () => {
    set('start', true);
    setSimData([]);
    await axios.post(`${API_BASE}/start_simulation`, null, { params: { num_cycles: 10 } }).catch(() => {});
    set('start', false);
  };

  const stopSim = async () => {
    set('stop', true);
    await axios.post(`${API_BASE}/stop_simulation`).catch(() => {});
    set('stop', false);
  };

  const tradeAction = async key => {
    set(key, true);
    await axios.post(`${API_BASE}/trading/${key}`).catch(() => {});
    await refreshTrading();
    set(key, false);
  };

  const submitRequest = async () => {
    set('req', true);
    await axios.post(`${API_BASE}/trading/request`, {
      seller: reqForm.seller,
      buyer: reqForm.buyer,
      energy_kwh: parseFloat(reqForm.energy_kwh),
      price_usd: parseFloat(reqForm.price_usd),
      time_block: reqForm.time_block,
    }).catch(() => {});
    await refreshTrading();
    set('req', false);
    setReqDialog(false);
  };

  const sendChat = async () => {
    if (!chatInput.trim()) return;
    await axios.post(`${API_BASE}/trading/chat`, { sender: chatSender, text: chatInput }).catch(() => {});
    setChatInput('');
  };

  const resetTrading = async () => {
    await axios.post(`${API_BASE}/trading/reset`).catch(() => {});
    refreshTrading();
  };

  const latestCycle = simData[simData.length - 1];
  const tel = latestCycle?.telemetry;
  const maxPow = tel ? Math.max(tel.total_generation_w, 1) : 1;
  const flow = trading.trade_flow;
  const offer = trading.current_offer;

  return (
    <ThemeProvider theme={darkTheme}>
      <Box sx={{ minHeight: '100vh', bgcolor: '#0a0e1a', color: 'text.primary' }}>

        {/* ── Top Bar ── */}
        <AppBar position="static" elevation={0}
          sx={{ bgcolor: '#0d1528', borderBottom: '1px solid #1e2d4a' }}>
          <Toolbar variant="dense" sx={{ gap: 1.5 }}>
            <Typography variant="h6"
              sx={{ fontWeight: 700, color: '#00e5ff', letterSpacing: 3, mr: 1 }}>
              ⚡ DCOMET
            </Typography>
            <Typography variant="caption" sx={{ color: '#555', flexGrow: 1 }}>
              Beckn P2P Energy Trading · Decentralised DER Network
            </Typography>
            <Chip size="small" variant="outlined"
              label={health === 'ok' ? '● LIVE' : health === 'error' ? '○ OFFLINE' : '● …'}
              color={health === 'ok' ? 'success' : 'error'} />
            <Chip size="small"
              label={simStatus.running ? `▶ SIM · ${simStatus.cycles} cycles` : '■ SIM STOPPED'}
              color={simStatus.running ? 'primary' : 'default'} />
            <Chip size="small"
              label={'TRADE: ' + flow.toUpperCase()}
              color={FLOW_COLOR[flow] || 'default'} />
          </Toolbar>
        </AppBar>

        {/* ── 4-col grid ── */}
        <Box sx={{ p: 2, display: 'grid', gap: 2, gridTemplateColumns: 'repeat(4, 1fr)' }}>

          {/* ── Simulation Control ── */}
          <Paper sx={{ p: 2 }}>
            <SectionTitle color="#00e5ff">Simulation</SectionTitle>
            <Divider sx={{ my: 1 }} />
            <Stack spacing={0.8} sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#888' }}>Status</Typography>
                {simStatus.running
                  ? <Chip label="Running" color="success" size="small" />
                  : <Chip label="Stopped" size="small" />}
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#888' }}>Cycles</Typography>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>{simStatus.cycles}</Typography>
              </Box>
              {tel && <>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="caption" sx={{ color: '#888' }}>Total Gen</Typography>
                  <Typography variant="body2" sx={{ color: '#69ff47', fontWeight: 700 }}>
                    {(tel.total_generation_w / 1000).toFixed(2)} kW
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="caption" sx={{ color: '#888' }}>Demand</Typography>
                  <Typography variant="body2" sx={{ color: '#ffb300', fontWeight: 700 }}>
                    {(tel.demand_w / 1000).toFixed(2)} kW
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="caption" sx={{ color: '#888' }}>Excess</Typography>
                  <Typography variant="body2" sx={{ color: '#00e5ff', fontWeight: 700 }}>
                    {(tel.excess_power_w / 1000).toFixed(2)} kW
                  </Typography>
                </Box>
              </>}
            </Stack>
            <Stack spacing={1}>
              <Button fullWidth size="small" variant="contained" color="success"
                onClick={startSim} disabled={simStatus.running || busy.start}
                startIcon={busy.start ? <CircularProgress size={12} /> : null}>
                Start (10 cycles)
              </Button>
              <Button fullWidth size="small" variant="outlined" color="error"
                onClick={stopSim} disabled={!simStatus.running || busy.stop}>
                Stop
              </Button>
            </Stack>
          </Paper>

          {/* ── DER Telemetry ── */}
          <Paper sx={{ p: 2 }}>
            <SectionTitle color="#69ff47">DER Telemetry</SectionTitle>
            <Divider sx={{ my: 1 }} />
            {tel ? <>
              <PowerBar label="DER 1 — Solar" value={tel.der_power_w?.der_1 || 0} max={maxPow} color="success" />
              <PowerBar label="DER 2 — Solar+" value={tel.der_power_w?.der_2 || 0} max={maxPow} color="success" />
              <PowerBar label="DER 3 — Steady" value={tel.der_power_w?.der_3 || 0} max={maxPow} color="info" />
              <Divider sx={{ my: 1 }} />
              <PowerBar label="Total Generation" value={tel.total_generation_w} max={maxPow} color="primary" />
              <PowerBar label="Demand" value={tel.demand_w} max={maxPow} color="warning" />
              <PowerBar label="Available for Trade" value={tel.available_for_trading_w} max={maxPow} color="secondary" />
              <PowerBar label="Excess" value={tel.excess_power_w} max={maxPow} color="primary" />
            </> : (
              <Typography variant="caption" sx={{ color: '#444' }}>
                Start simulation to see live DER telemetry
              </Typography>
            )}
          </Paper>

          {/* ── Beckn Trading ── */}
          <Paper sx={{ p: 2 }}>
            <SectionTitle color="#ffb300">Beckn Trading Protocol</SectionTitle>
            <Divider sx={{ my: 1 }} />
            <Stack direction="row" flexWrap="wrap" gap={0.5} sx={{ mb: 1.5 }}>
              {FLOW_STEPS.map(s => (
                <Chip key={s} label={s} size="small" sx={{ fontSize: 9 }}
                  color={flow === s ? (FLOW_COLOR[s] || 'primary') : 'default'}
                  variant={flow === s ? 'filled' : 'outlined'} />
              ))}
              {flow === 'rejected' && (
                <Chip label="rejected" size="small" color="error" sx={{ fontSize: 9 }} />
              )}
            </Stack>
            {offer ? (
              <Box sx={{ p: 1.5, mb: 1.5, bgcolor: '#0d1528', borderRadius: 1, border: '1px solid #1e2d4a' }}>
                <Typography variant="caption" sx={{ color: '#555', display: 'block', mb: 0.5 }}>
                  Current Offer
                </Typography>
                {[
                  ['Seller', offer.seller, '#69ff47'],
                  ['Buyer', offer.buyer, '#00e5ff'],
                  ['Energy', offer.energy_kwh + ' kWh', '#fff'],
                  ['Price', '$' + offer.price_usd, '#ffb300'],
                  ['Block', offer.time_block, '#888'],
                ].map(([k, v, c]) => (
                  <Box key={k} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="caption" sx={{ color: '#555' }}>{k}</Typography>
                    <Typography variant="caption" sx={{ color: c, fontWeight: 700 }}>{v}</Typography>
                  </Box>
                ))}
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                  <Typography variant="caption" sx={{ color: '#555' }}>Payment</Typography>
                  <Chip label={trading.payment_status} size="small" sx={{ fontSize: 9, height: 16 }}
                    color={trading.payment_status === 'paid' ? 'success' : 'default'} />
                </Box>
              </Box>
            ) : (
              <Typography variant="caption" sx={{ color: '#444', display: 'block', mb: 1.5 }}>
                No active offer
              </Typography>
            )}
            <Stack spacing={0.8}>
              <Button size="small" variant="contained" color="primary" fullWidth
                onClick={() => setReqDialog(true)}
                disabled={flow !== 'idle' && flow !== 'rejected' && flow !== 'completed'}>
                Request Trade
              </Button>
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="outlined" color="success" fullWidth
                  onClick={() => tradeAction('accept')}
                  disabled={flow !== 'requested' || busy.accept}>
                  Accept
                </Button>
                <Button size="small" variant="outlined" color="error" fullWidth
                  onClick={() => tradeAction('reject')}
                  disabled={flow !== 'requested' || busy.reject}>
                  Reject
                </Button>
              </Stack>
              <Button size="small" variant="outlined" color="info" fullWidth
                onClick={() => tradeAction('complete')}
                disabled={flow !== 'accepted' || busy.complete}>
                Complete Dispatch
              </Button>
              <Button size="small" variant="outlined" color="warning" fullWidth
                onClick={() => tradeAction('payment/confirm')}
                disabled={trading.payment_status !== 'pending' || busy['payment/confirm']}>
                Confirm Payment
              </Button>
              <Button size="small" variant="text" sx={{ color: '#444', fontSize: 10 }}
                onClick={resetTrading}>
                Reset Trading State
              </Button>
            </Stack>
          </Paper>

          {/* ── Activity Log ── */}
          <Paper sx={{ p: 2 }}>
            <SectionTitle color="#a78bfa">Activity Log</SectionTitle>
            <Divider sx={{ my: 1 }} />
            <Box sx={{ maxHeight: 380, overflow: 'auto' }}>
              {trading.activity_log.length === 0
                ? <Typography variant="caption" sx={{ color: '#444' }}>No activity yet</Typography>
                : trading.activity_log.map(a => (
                  <Box key={a.id} sx={{
                    mb: 0.8, p: 0.8, bgcolor: '#0d1528', borderRadius: 1,
                    borderLeft: '2px solid #a78bfa',
                  }}>
                    <Typography variant="caption" sx={{ color: '#a78bfa', display: 'block' }}>
                      {a.timestamp}
                    </Typography>
                    <Typography variant="caption">{a.message}</Typography>
                  </Box>
                ))
              }
            </Box>
          </Paper>

          {/* ── Chat (spans 2 cols) ── */}
          <Paper sx={{ p: 2, gridColumn: 'span 2' }}>
            <SectionTitle color="#00e5ff">Beckn Protocol Chat — BAP / BPP</SectionTitle>
            <Divider sx={{ my: 1 }} />
            <Box sx={{ maxHeight: 220, overflow: 'auto', mb: 1.5 }}>
              {trading.chat_messages.map(m => <ChatBubble key={m.id} msg={m} />)}
              <div ref={chatEndRef} />
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Stack direction="row" spacing={0.5}>
                {['bap', 'bpp'].map(s => (
                  <Chip key={s} label={s.toUpperCase()} size="small" clickable
                    onClick={() => setChatSender(s)}
                    color={chatSender === s ? 'primary' : 'default'} sx={{ fontSize: 10 }} />
                ))}
              </Stack>
              <TextField size="small" placeholder="Type message…" value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendChat()}
                sx={{ flexGrow: 1, '& .MuiInputBase-input': { fontSize: 12 } }} />
              <Button size="small" variant="contained" onClick={sendChat}>Send</Button>
            </Stack>
          </Paper>

          {/* ── Cycles History (spans 2 cols) ── */}
          <Paper sx={{ p: 2, gridColumn: 'span 2' }}>
            <SectionTitle color="#69ff47">Trading Cycles — {simData.length} total</SectionTitle>
            <Divider sx={{ my: 1 }} />
            <Box sx={{ maxHeight: 280, overflow: 'auto' }}>
              {simData.length === 0
                ? <Typography variant="caption" sx={{ color: '#444' }}>
                    No cycles yet — start simulation
                  </Typography>
                : [...simData].reverse().map(c => (
                  <CycleCard key={c.cycle} c={c} />
                ))
              }
            </Box>
          </Paper>

        </Box>

        {/* ── Request Trade Dialog ── */}
        <Dialog open={reqDialog} onClose={() => setReqDialog(false)} maxWidth="xs" fullWidth
          PaperProps={{ sx: { bgcolor: '#111827', border: '1px solid #1e2d4a' } }}>
          <DialogTitle sx={{ color: '#00e5ff', fontSize: 14 }}>Request Energy Trade</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {[['seller', 'Seller'], ['buyer', 'Buyer'], ['time_block', 'Time Block']].map(([k, lbl]) => (
                <TextField key={k} label={lbl} size="small" fullWidth value={reqForm[k]}
                  onChange={e => setReqForm(f => ({ ...f, [k]: e.target.value }))} />
              ))}
              <TextField label="Energy (kWh)" type="number" size="small" fullWidth
                value={reqForm.energy_kwh}
                onChange={e => setReqForm(f => ({ ...f, energy_kwh: e.target.value }))} />
              <TextField label="Price (USD)" type="number" size="small" fullWidth
                value={reqForm.price_usd}
                onChange={e => setReqForm(f => ({ ...f, price_usd: e.target.value }))} />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button size="small" onClick={() => setReqDialog(false)}>Cancel</Button>
            <Button size="small" variant="contained" onClick={submitRequest} disabled={busy.req}>
              {busy.req ? <CircularProgress size={14} /> : 'Submit'}
            </Button>
          </DialogActions>
        </Dialog>

      </Box>
    </ThemeProvider>
  );
}
