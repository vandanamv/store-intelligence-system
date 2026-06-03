import React, { useState, useEffect, useRef } from 'react';

// Zero-dependency SVG Icon Pack
const Icons = {
  Refresh: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H18" /></svg>,
  Users: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg>,
  Cart: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" /></svg>,
  TrendingDown: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" /></svg>,
  AlertTriangle: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>,
  Activity: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>,
  Check: () => <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
};

export default function App() {
  const [storeId, setStoreId] = useState('STORE_BLR_002');
  const [metrics, setMetrics] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [health, setHealth] = useState(null);
  const [eventsFeed, setEventsFeed] = useState([]);
  const [wsStatus, setWsStatus] = useState('CONNECTING');
  const [apiError, setApiError] = useState(false);

  const canvasRef = useRef(null);
  const socketRef = useRef(null);

  const API_HOST = window.location.hostname === 'localhost' ? 'localhost:8000' : `${window.location.hostname}:8000`;
  const httpProtocol = window.location.protocol;
  const wsProtocol = httpProtocol === 'https:' ? 'wss:' : 'ws:';

  // 1. Fetch initial statistics
  const fetchAllData = async () => {
    try {
      setApiError(false);
      const [resMetrics, resFunnel, resHeatmap, resAnomalies, resHealth] = await Promise.all([
        fetch(`${httpProtocol}//${API_HOST}/stores/${storeId}/metrics`),
        fetch(`${httpProtocol}//${API_HOST}/stores/${storeId}/funnel`),
        fetch(`${httpProtocol}//${API_HOST}/stores/${storeId}/heatmap`),
        fetch(`${httpProtocol}//${API_HOST}/stores/${storeId}/anomalies`),
        fetch(`${httpProtocol}//${API_HOST}/health`)
      ]);

      if (resMetrics.ok) setMetrics(await resMetrics.json());
      if (resFunnel.ok) setFunnel(await resFunnel.json());
      if (resHeatmap.ok) setHeatmap(await resHeatmap.json());
      if (resAnomalies.ok) {
        const data = await resAnomalies.json();
        setAnomalies(data.anomalies || []);
      }
      if (resHealth.ok) setHealth(await resHealth.json());
    } catch (e) {
      console.error("API fetching error:", e);
      setApiError(true);
    }
  };

  useEffect(() => {
    fetchAllData();
    const interval = setInterval(fetchAllData, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, [storeId]);

  // 2. Establish WebSocket connection
  useEffect(() => {
    const connectWs = () => {
      setWsStatus('CONNECTING');
      const wsUrl = `${wsProtocol}//${API_HOST}/ws`;
      console.log(`Connecting to WebSocket: ${wsUrl}`);
      
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        setWsStatus('CONNECTED');
        console.log("WebSocket connected.");
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'NEW_EVENTS') {
            // Append new events to feed
            setEventsFeed(prev => {
              const merged = [...data.events, ...prev];
              return merged.slice(0, 30); // cap at 30 items
            });
            // Update metrics instantly on new event arrival
            fetchAllData();
          }
        } catch (err) {
          console.error("WebSocket message parsing failed:", err);
        }
      };

      socket.onclose = () => {
        setWsStatus('DISCONNECTED');
        console.log("WebSocket disconnected. Reconnecting in 3s...");
        setTimeout(connectWs, 3000);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connectWs();
    return () => {
      if (socketRef.current) socketRef.current.close();
    };
  }, [storeId]);

  // 3. Canvas CCTV Feed Simulator
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationId;

    // Track state inside the CCTV view
    // Simulate coordinates of people walking around the store
    const participants = [
      { id: 'VIS_5b2d8c', x: 200, y: 150, targetX: 200, targetY: 150, label: 'Customer', color: '#6366f1', speed: 1.5, group: null, isStaff: false },
      { id: 'VIS_a3c8e4', x: 120, y: 100, targetX: 150, targetY: 200, label: 'Customer', color: '#6366f1', speed: 2, group: 'GROUP_f38a', isStaff: false },
      { id: 'VIS_f19d22', x: 140, y: 120, targetX: 170, targetY: 210, label: 'Customer', color: '#6366f1', speed: 2, group: 'GROUP_f38a', isStaff: false },
      { id: 'VIS_staff_01', x: 450, y: 300, targetX: 450, targetY: 300, label: 'Staff (Uniform)', color: '#f59e0b', speed: 1, group: null, isStaff: true },
      { id: 'VIS_vendor_1', x: 800, y: 400, targetX: 850, targetY: 420, label: 'Re-entry matched', color: '#06b6d4', speed: 1.2, group: null, isStaff: false }
    ];

    const storeZones = [
      { name: 'ENTRY AREA', x: 50, y: 50, w: 200, h: 250, color: 'rgba(99, 102, 241, 0.05)' },
      { name: 'SKINCARE SECTION', x: 300, y: 50, w: 300, h: 180, color: 'rgba(6, 182, 212, 0.05)' },
      { name: 'MAKEUP ZONE', x: 650, y: 50, w: 250, h: 250, color: 'rgba(168, 85, 247, 0.05)' },
      { name: 'BILLING COUNTER', x: 300, y: 280, w: 500, h: 150, color: 'rgba(16, 185, 129, 0.05)' }
    ];

    const render = () => {
      // Clear
      ctx.fillStyle = '#0a101e';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw grid
      ctx.strokeStyle = 'rgba(255,255,255,0.02)';
      ctx.lineWidth = 1;
      for (let i = 0; i < canvas.width; i += 30) {
        ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
      }
      for (let j = 0; j < canvas.height; j += 30) {
        ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(canvas.width, j); ctx.stroke();
      }

      // Draw Store Layout Zones
      storeZones.forEach(zone => {
        ctx.fillStyle = zone.color;
        ctx.fillRect(zone.x, zone.y, zone.w, zone.h);
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        ctx.strokeRect(zone.x, zone.y, zone.w, zone.h);
        
        ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
        ctx.font = "bold 9px 'Outfit', sans-serif";
        ctx.fillText(zone.name, zone.x + 10, zone.y + 20);
      });

      // Update and Draw Participants (Customers / Staff)
      participants.forEach(p => {
        // Move towards target coordinates
        if (Math.abs(p.x - p.targetX) < 5 && Math.abs(p.y - p.targetY) < 5) {
          // Select new random target within store boundaries
          p.targetX = Math.random() * (canvas.width - 100) + 50;
          p.targetY = Math.random() * (canvas.height - 100) + 50;
        }

        const angle = Math.atan2(p.targetY - p.y, p.targetX - p.x);
        p.x += Math.cos(angle) * p.speed;
        p.y += Math.sin(angle) * p.speed;

        // Draw Bounding Box (YOLOv8 representation)
        const boxWidth = 40;
        const boxHeight = 70;
        ctx.lineWidth = 2;
        ctx.strokeStyle = p.color;
        ctx.strokeRect(p.x - boxWidth/2, p.y - boxHeight/2, boxWidth, boxHeight);

        // Drawing label tag
        ctx.fillStyle = p.color;
        ctx.fillRect(p.x - boxWidth/2 - 1, p.y - boxHeight/2 - 18, boxWidth + 2, 18);

        ctx.fillStyle = '#ffffff';
        ctx.font = "bold 8px 'Inter', sans-serif";
        ctx.fillText(p.id, p.x - boxWidth/2 + 4, p.y - boxHeight/2 - 7);

        // Connect group members with fluorescent threads (Edge Case 1: Group handling)
        if (p.group) {
          participants.forEach(other => {
            if (other.id !== p.id && other.group === p.group) {
              ctx.beginPath();
              ctx.strokeStyle = 'rgba(168, 85, 247, 0.3)';
              ctx.lineWidth = 1;
              ctx.setLineDash([4, 4]);
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(other.x, other.y);
              ctx.stroke();
              ctx.setLineDash([]);
            }
          });
        }
        
        // Indicate is_staff visual tag
        if (p.isStaff) {
          ctx.beginPath();
          ctx.arc(p.x, p.y - boxHeight/2 - 25, 4, 0, 2*Math.PI);
          ctx.fillStyle = '#f59e0b';
          ctx.fill();
        }
      });

      // Overlay lens filter
      ctx.fillStyle = 'rgba(99, 102, 241, 0.02)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Camera Angle title overlay
      ctx.fillStyle = '#ffffff';
      ctx.font = "bold 11px 'Outfit', sans-serif";
      ctx.fillText("🔴 LIVE FEED SIMULATOR // WIDE_ANGLE_OVERLAP_CAM_01", 20, 30);

      animationId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animationId);
  }, []);

  return (
    <div style={{ minHeight: '100vh', padding: '24px' }}>
      {/* Header section */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="live-indicator"></span>
            <h1 className="grad-text" style={{ fontSize: '28px', fontWeight: 800, margin: 0 }}>APEX STORE INTELLIGENCE</h1>
          </div>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', marginTop: '4px' }}>Real-time Edge Video Processing & Session Analytics Engine</p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Status Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px', borderRadius: '30px', fontSize: '12px', fontWeight: 600, background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-glass)' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: wsStatus === 'CONNECTED' ? 'var(--color-success)' : 'var(--color-danger)' }}></span>
            <span style={{ color: wsStatus === 'CONNECTED' ? 'var(--color-success)' : 'var(--color-text-muted)' }}>WS: {wsStatus}</span>
          </div>

          {/* Store Selector */}
          <select 
            value={storeId} 
            onChange={(e) => setStoreId(e.target.value)}
            style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border-glass)', backgroundColor: 'var(--bg-panel-solid)', color: '#ffffff', outline: 'none', fontWeight: 600, cursor: 'pointer' }}
          >
            <option value="STORE_BLR_002">STORE_BLR_002 (Bengaluru)</option>
            <option value="STORE_MUM_001">STORE_MUM_001 (Mumbai)</option>
            <option value="STORE_DEL_005">STORE_DEL_005 (Delhi)</option>
          </select>

          <button 
            onClick={fetchAllData}
            style={{ padding: '8px', borderRadius: '8px', border: '1px solid var(--border-glass)', backgroundColor: 'var(--bg-panel-solid)', color: '#ffffff', cursor: 'pointer', transition: '0.2s' }}
          >
            <Icons.Refresh />
          </button>
        </div>
      </header>

      {apiError && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--color-danger)', borderRadius: '12px', padding: '16px', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Icons.AlertTriangle />
          <div>
            <h4 style={{ color: 'var(--color-danger)', fontWeight: 700 }}>API Connection Error</h4>
            <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginTop: '2px' }}>Failed to resolve store metrics. Verify that the FastAPI backend server is running on port 8000.</p>
          </div>
        </div>
      )}

      {/* Grid Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', lg: '3fr 1fr', gap: '24px' }}>
        
        {/* Left Column: CCTV feed + charts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Live Feed Simulator Canvas */}
          <div className="glass-panel" style={{ overflow: 'hidden', padding: '12px' }}>
            <canvas 
              ref={canvasRef} 
              width={960} 
              height={500} 
              style={{ width: '100%', height: 'auto', borderRadius: '12px', display: 'block', backgroundColor: '#060913' }}
            />
          </div>

          {/* Stats Metrics Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '20px' }}>
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontWeight: 500 }}>Unique Customers</span>
                <span style={{ color: 'var(--color-primary)' }}><Icons.Users /></span>
              </div>
              <h2 style={{ fontSize: '32px', fontWeight: 800, fontFamily: 'var(--font-display)' }}>
                {metrics ? metrics.unique_visitors : '0'}
              </h2>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Excluding staff members</p>
            </div>

            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontWeight: 500 }}>Conversion Rate</span>
                <span style={{ color: 'var(--color-success)' }}><Icons.Cart /></span>
              </div>
              <h2 style={{ fontSize: '32px', fontWeight: 800, fontFamily: 'var(--font-display)', color: 'var(--color-success)' }}>
                {metrics ? `${(metrics.conversion_rate * 100).toFixed(2)}%` : '0.00%'}
              </h2>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Window purchase ratio</p>
            </div>

            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontWeight: 500 }}>Billing Queue Depth</span>
                <span style={{ color: 'var(--color-warning)' }}><Icons.Activity /></span>
              </div>
              <h2 style={{ fontSize: '32px', fontWeight: 800, fontFamily: 'var(--font-display)' }}>
                {metrics ? metrics.current_queue_depth : '0'}
              </h2>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Active visitors in checkout zone</p>
            </div>

            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontWeight: 500 }}>Queue Abandonment</span>
                <span style={{ color: 'var(--color-danger)' }}><Icons.TrendingDown /></span>
              </div>
              <h2 style={{ fontSize: '32px', fontWeight: 800, fontFamily: 'var(--font-display)', color: 'var(--color-danger)' }}>
                {metrics ? `${(metrics.abandonment_rate * 100).toFixed(1)}%` : '0.0%'}
              </h2>
              <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>Left queue without POS checkout</p>
            </div>
          </div>

          {/* conversion funnel & heatmaps */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '20px' }}>
            {/* Funnel Graph */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'var(--font-display)', marginBottom: '16px' }}>Store Conversion Funnel</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                {funnel && funnel.funnel.map((stage, idx) => (
                  <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ width: '100px', fontSize: '12px', fontWeight: 600, color: 'var(--color-text-muted)' }}>{stage.stage_name}</div>
                    <div style={{ flex: 1, height: '24px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '4px', overflow: 'hidden', border: '1px solid var(--border-glass)', position: 'relative' }}>
                      <div 
                        style={{ 
                          width: funnel.funnel[0].count > 0 ? `${(stage.count / funnel.funnel[0].count) * 100}%` : '0%', 
                          height: '100%', 
                          background: 'linear-gradient(90deg, #6366f1, #06b6d4)', 
                          borderRadius: '3px',
                          transition: 'width 0.8s ease-out'
                        }}
                      />
                      <span style={{ position: 'absolute', right: '8px', top: '3px', fontSize: '11px', fontWeight: 700 }}>{stage.count}</span>
                    </div>
                    <div style={{ width: '80px', fontSize: '11px', fontWeight: 700, color: 'var(--color-danger)', textAlign: 'right' }}>
                      {idx > 0 && stage.drop_off_percentage > 0 ? `-${stage.drop_off_percentage}%` : '0%'}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Heatmap Grid */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'var(--font-display)' }}>Zone Visit Heatmap</h3>
                {heatmap && (
                  <span style={{ fontSize: '10px', padding: '3px 8px', borderRadius: '20px', background: heatmap.data_confidence ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)', color: heatmap.data_confidence ? 'var(--color-success)' : 'var(--color-warning)', fontWeight: 700 }}>
                    {heatmap.data_confidence ? 'High Confidence' : 'Low Sample Window'}
                  </span>
                )}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
                {heatmap && heatmap.heatmap.map((item, idx) => (
                  <div key={idx} style={{ padding: '12px', borderRadius: '8px', border: '1px solid var(--border-glass)', background: `rgba(99, 102, 241, ${item.visit_frequency / 250})` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700 }}>{item.zone_id}</span>
                      <span style={{ fontSize: '11px', fontWeight: 800, color: 'var(--color-secondary)' }}>{item.visit_frequency.toFixed(0)} pts</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--color-text-muted)' }}>
                      <span>Avg Dwell</span>
                      <span style={{ fontWeight: 600 }}>{(item.avg_dwell_ms / 1000).toFixed(1)}s</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: AI Anomalies + Live logs */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* AI Anomaly Logs */}
          <div className="glass-panel glass-panel-glow" style={{ padding: '20px', minHeight: '300px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'var(--font-display)', marginBottom: '16px' }}>AI Anomaly Engine</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {anomalies.length === 0 ? (
                <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '13px' }}>
                  <Icons.Check />
                  <p style={{ marginTop: '8px' }}>No operational anomalies detected in the last 30 minutes.</p>
                </div>
              ) : (
                anomalies.map((anom, idx) => (
                  <div 
                    key={idx} 
                    className="animate-slide-in"
                    style={{ 
                      padding: '12px', 
                      borderRadius: '8px', 
                      background: anom.severity === 'CRITICAL' ? 'rgba(239, 68, 68, 0.05)' : 'rgba(245, 158, 11, 0.05)', 
                      border: `1px solid ${anom.severity === 'CRITICAL' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.2)'}` 
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <span style={{ fontSize: '11px', fontWeight: 800, color: anom.severity === 'CRITICAL' ? 'var(--color-danger)' : 'var(--color-warning)' }}>
                        {anom.type}
                      </span>
                      <span style={{ fontSize: '9px', padding: '2px 5px', borderRadius: '4px', background: 'rgba(255,255,255,0.03)', color: 'var(--color-text-muted)', fontWeight: 600 }}>
                        {anom.severity}
                      </span>
                    </div>
                    <p style={{ fontSize: '12px', lineHeight: '1.4', marginBottom: '8px' }}>{anom.description}</p>
                    <div style={{ fontSize: '11px', padding: '6px 8px', borderRadius: '4px', background: 'rgba(255,255,255,0.02)', borderLeft: '2px solid var(--color-secondary)' }}>
                      <span style={{ color: 'var(--color-secondary)', fontWeight: 700 }}>Action: </span>
                      {anom.suggested_action}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Real-time Ingestion Feed */}
          <div className="glass-panel" style={{ padding: '20px', flex: 1, display: 'flex', flexDirection: 'column' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, fontFamily: 'var(--font-display)', marginBottom: '16px' }}>Raw Event Stream</h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', overflowY: 'auto', maxHeight: '520px', flex: 1 }}>
              {eventsFeed.length === 0 ? (
                <div style={{ margin: 'auto', padding: '24px 0', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '13px' }}>
                  <p>Awaiting events from edge camera feeds...</p>
                  <code style={{ display: 'block', padding: '8px', background: '#05070f', borderRadius: '6px', fontSize: '11px', color: 'var(--color-primary)', marginTop: '12px' }}>
                    run pipeline/run.sh
                  </code>
                </div>
              ) : (
                eventsFeed.map((evt, idx) => (
                  <div 
                    key={idx} 
                    className="animate-slide-in"
                    style={{ 
                      padding: '10px', 
                      borderRadius: '8px', 
                      border: '1px solid var(--border-glass)', 
                      backgroundColor: 'rgba(255,255,255,0.01)',
                      fontSize: '12px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 700, color: evt.is_staff ? 'var(--color-warning)' : 'var(--color-primary)' }}>
                        {evt.visitor_id} {evt.is_staff ? '(STAFF)' : ''}
                      </span>
                      <span style={{ fontSize: '10px', color: 'var(--color-text-muted)' }}>
                        {new Date(evt.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, color: evt.event_type.includes('ABANDON') || evt.event_type.includes('EXIT') ? 'var(--color-danger)' : 'var(--color-success)' }}>
                        {evt.event_type}
                      </span>
                      <span style={{ fontSize: '10px', color: 'var(--color-text-muted)' }}>
                        {evt.zone_id ? evt.zone_id : evt.camera_id}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
