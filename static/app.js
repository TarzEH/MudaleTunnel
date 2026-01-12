// WebSocket connection for real-time updates
let ws = null;
let scanInterval = null;

// Initialize WebSocket connection
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/tunnels`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        setTimeout(initWebSocket, 3000);
    };
    
    // Keepalive ping
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
        }
    }, 30000);
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'initial_state':
            refreshTunnels();
            break;
        case 'tunnel_created':
        case 'tunnel_stopped':
        case 'all_tunnels_stopped':
            refreshTunnels();
            showToast('Tunnel updated', 'success');
            break;
    }
}

// Tab switching
function switchTab(tab) {
    const staticForm = document.getElementById('staticForm');
    const dynamicForm = document.getElementById('dynamicForm');
    const tabs = document.querySelectorAll('.tab-btn');
    
    tabs.forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    
    if (tab === 'static') {
        staticForm.style.display = 'block';
        dynamicForm.style.display = 'none';
    } else {
        staticForm.style.display = 'none';
        dynamicForm.style.display = 'block';
    }
}

// Start nmap scan
async function startScan() {
    const target = document.getElementById('scanTarget').value.trim();
    if (!target) {
        showStatus('error', 'Please enter a target');
        return;
    }
    
    const scanBtn = document.getElementById('scanBtn');
    scanBtn.disabled = true;
    showStatus('info', 'Initiating scan...');
    document.getElementById('scanProgress').style.display = 'block';
    
    try {
        const response = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target })
        });
        
        const data = await response.json();
        if (response.ok) {
            showStatus('info', `Scan started. ID: ${data.scan_id}`);
            pollScanStatus(data.scan_id);
        } else {
            showStatus('error', 'Failed to start scan');
        }
    } catch (error) {
        showStatus('error', `Error: ${error.message}`);
    } finally {
        scanBtn.disabled = false;
    }
}

// Poll scan status
function pollScanStatus(scanId) {
    if (scanInterval) {
        clearInterval(scanInterval);
    }
    
    scanInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/scan/status/${scanId}`);
            const data = await response.json();
            
            if (data.status === 'completed') {
                clearInterval(scanInterval);
                document.getElementById('scanProgress').style.display = 'none';
                showStatus('success', 'Scan completed!');
                displayServices(data.services || []);
            } else if (data.status === 'failed') {
                clearInterval(scanInterval);
                document.getElementById('scanProgress').style.display = 'none';
                showStatus('error', `Scan failed: ${data.error || 'Unknown error'}`);
            } else {
                showStatus('info', data.progress || 'Scanning...');
            }
        } catch (error) {
            console.error('Error polling scan status:', error);
        }
    }, 2000);
}

// Display discovered services
function displayServices(services) {
    const servicesSection = document.getElementById('servicesSection');
    const servicesList = document.getElementById('servicesList');
    
    if (!services || services.length === 0) {
        servicesList.innerHTML = '<p>No services found.</p>';
        servicesSection.style.display = 'block';
        return;
    }
    
    servicesList.innerHTML = services.map(service => `
        <div class="service-item">
            <div class="service-info">
                <strong>Port:</strong> ${service.port} | 
                <strong>Service:</strong> ${service.service} | 
                <strong>State:</strong> ${service.state}
            </div>
            <button onclick="useServiceForTunnel('${service.port}', '${service.service}')" class="btn-secondary">
                Use for Tunnel
            </button>
        </div>
    `).join('');
    
    servicesSection.style.display = 'block';
}

// Use service for tunnel creation
function useServiceForTunnel(port, service) {
    // Switch to static tab
    document.querySelectorAll('.tab-btn')[0].click();
    
    // Parse port number
    const portNum = parseInt(port.split('/')[0]);
    
    // Fill form
    document.getElementById('staticRemotePort').value = portNum;
    document.getElementById('staticLocalPort').value = portNum;
    
    // Scroll to form
    document.getElementById('staticForm').scrollIntoView({ behavior: 'smooth' });
}

// Create static tunnel
async function createStaticTunnel() {
    const sshUser = document.getElementById('staticSshUser').value.trim();
    const sshHost = document.getElementById('staticSshHost').value.trim();
    const targetHost = document.getElementById('staticTargetHost').value.trim();
    const remotePort = parseInt(document.getElementById('staticRemotePort').value);
    const localPortInput = document.getElementById('staticLocalPort').value.trim();
    const localPort = localPortInput ? parseInt(localPortInput) : null;
    const execute = document.getElementById('staticExecute').checked;
    
    if (!sshUser || !sshHost || !targetHost || !remotePort) {
        showToast('Please fill all required fields', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/tunnels/static', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ssh_user: sshUser,
                ssh_host: sshHost,
                target_host: targetHost,
                remote_port: remotePort,
                local_port: localPort,
                execute: execute
            })
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast('Static tunnel created successfully!', 'success');
            if (!execute) {
                showToast(`Command: ${data.command}`, 'info');
            }
            refreshTunnels();
            // Clear form
            document.getElementById('staticForm').reset();
        } else {
            showToast(data.detail || 'Failed to create tunnel', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Create dynamic tunnel
async function createDynamicTunnel() {
    const sshUser = document.getElementById('dynamicSshUser').value.trim();
    const sshHost = document.getElementById('dynamicSshHost').value.trim();
    const localPortInput = document.getElementById('dynamicLocalPort').value.trim();
    const localPort = localPortInput ? parseInt(localPortInput) : null;
    const execute = document.getElementById('dynamicExecute').checked;
    
    if (!sshUser || !sshHost) {
        showToast('Please fill all required fields', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/tunnels/dynamic', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ssh_user: sshUser,
                ssh_host: sshHost,
                local_port: localPort,
                execute: execute
            })
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast('Dynamic tunnel created successfully!', 'success');
            if (!execute) {
                showToast(`Command: ${data.command}`, 'info');
            }
            refreshTunnels();
            // Clear form
            document.getElementById('dynamicForm').reset();
        } else {
            showToast(data.detail || 'Failed to create tunnel', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Refresh tunnels list
async function refreshTunnels() {
    try {
        const response = await fetch('/api/tunnels');
        const data = await response.json();
        displayTunnels(data.tunnels || []);
    } catch (error) {
        console.error('Error fetching tunnels:', error);
    }
}

// Display tunnels
function displayTunnels(tunnels) {
    const tunnelsList = document.getElementById('tunnelsList');
    
    if (!tunnels || tunnels.length === 0) {
        tunnelsList.innerHTML = '<p>No active tunnels.</p>';
        return;
    }
    
    tunnelsList.innerHTML = tunnels.map(tunnel => {
        const statusClass = tunnel.status === 'active' ? 'active' : 'stopped';
        const badgeClass = tunnel.type === 'static' ? 'badge-static' : 'badge-dynamic';
        const statusBadgeClass = tunnel.status === 'active' ? 'badge-active' : 'badge-stopped';
        
        const remoteInfo = tunnel.type === 'static' 
            ? `${tunnel.remote_host}:${tunnel.remote_port}`
            : 'SOCKS Proxy';
        
        return `
            <div class="tunnel-item ${statusClass}">
                <div class="tunnel-header">
                    <h3>
                        <span class="tunnel-badge ${badgeClass}">${tunnel.type.toUpperCase()}</span>
                        <span class="tunnel-badge ${statusBadgeClass}">${tunnel.status}</span>
                    </h3>
                    <span style="font-size: 0.9em; color: #64748b;">ID: ${tunnel.id.substring(0, 8)}</span>
                </div>
                <div class="tunnel-details">
                    <div class="tunnel-detail-item">
                        <strong>Local Port:</strong> ${tunnel.local_port}
                    </div>
                    <div class="tunnel-detail-item">
                        <strong>Remote:</strong> ${remoteInfo}
                    </div>
                    <div class="tunnel-detail-item">
                        <strong>SSH:</strong> ${tunnel.ssh_user}@${tunnel.ssh_host}
                    </div>
                    <div class="tunnel-detail-item">
                        <strong>PID:</strong> ${tunnel.pid || 'N/A'}
                    </div>
                </div>
                <div class="tunnel-actions-item">
                    <button onclick="viewTunnelDetails('${tunnel.id}')" class="btn-secondary">Details</button>
                    <button onclick="viewTunnelLogs('${tunnel.id}')" class="btn-secondary">Logs</button>
                    <button onclick="viewTunnelMetrics('${tunnel.id}')" class="btn-secondary">Metrics</button>
                    ${tunnel.status === 'active' ? `<button onclick="stopTunnel('${tunnel.id}')" class="btn-danger">Stop</button>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

// Stop tunnel
async function stopTunnel(tunnelId) {
    if (!confirm('Are you sure you want to stop this tunnel?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/tunnels/${tunnelId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('Tunnel stopped', 'success');
            refreshTunnels();
        } else {
            showToast('Failed to stop tunnel', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Stop all tunnels
async function stopAllTunnels() {
    if (!confirm('Are you sure you want to stop ALL tunnels?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/tunnels', {
            method: 'DELETE'
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast(`Stopped ${data.count} tunnel(s)`, 'success');
            refreshTunnels();
        } else {
            showToast('Failed to stop tunnels', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// View tunnel details
async function viewTunnelDetails(tunnelId) {
    try {
        const response = await fetch(`/api/tunnels/${tunnelId}`);
        const tunnel = await response.json();
        
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <div class="tunnel-details">
                <div><strong>Type:</strong> ${tunnel.type}</div>
                <div><strong>Status:</strong> ${tunnel.status}</div>
                <div><strong>Local Port:</strong> ${tunnel.local_port}</div>
                ${tunnel.type === 'static' ? `
                    <div><strong>Remote Host:</strong> ${tunnel.remote_host}</div>
                    <div><strong>Remote Port:</strong> ${tunnel.remote_port}</div>
                ` : ''}
                <div><strong>SSH User:</strong> ${tunnel.ssh_user}</div>
                <div><strong>SSH Host:</strong> ${tunnel.ssh_host}</div>
                <div><strong>PID:</strong> ${tunnel.pid || 'N/A'}</div>
                <div><strong>Created:</strong> ${new Date(tunnel.created_at).toLocaleString()}</div>
            </div>
            <div style="margin-top: 20px;">
                <strong>Command:</strong>
                <pre style="background: #f1f5f9; padding: 10px; border-radius: 4px; overflow-x: auto;">${tunnel.command}</pre>
            </div>
        `;
        
        document.getElementById('modalTitle').textContent = 'Tunnel Details';
        document.getElementById('tunnelModal').style.display = 'block';
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// View tunnel logs
async function viewTunnelLogs(tunnelId) {
    try {
        const response = await fetch(`/api/tunnels/${tunnelId}/logs`);
        const data = await response.json();
        
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <div class="log-viewer">
                ${data.logs.length > 0 
                    ? data.logs.map(log => `<div class="log-entry">${escapeHtml(log)}</div>`).join('')
                    : '<div>No logs available</div>'
                }
            </div>
        `;
        
        document.getElementById('modalTitle').textContent = 'Tunnel Logs';
        document.getElementById('tunnelModal').style.display = 'block';
        
        // Auto-scroll to bottom
        const logViewer = modalBody.querySelector('.log-viewer');
        if (logViewer) {
            logViewer.scrollTop = logViewer.scrollHeight;
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// View tunnel metrics
async function viewTunnelMetrics(tunnelId) {
    try {
        const response = await fetch(`/api/tunnels/${tunnelId}/metrics`);
        const metrics = await response.json();
        
        const uptimeHours = Math.floor(metrics.uptime_seconds / 3600);
        const uptimeMinutes = Math.floor((metrics.uptime_seconds % 3600) / 60);
        const uptimeSeconds = Math.floor(metrics.uptime_seconds % 60);
        const uptimeStr = `${uptimeHours}h ${uptimeMinutes}m ${uptimeSeconds}s`;
        
        const modalBody = document.getElementById('modalBody');
        modalBody.innerHTML = `
            <div class="metrics-grid">
                <div class="metric-item">
                    <div class="metric-value">${uptimeStr}</div>
                    <div class="metric-label">Uptime</div>
                </div>
                <div class="metric-item">
                    <div class="metric-value">${metrics.status_checks || 0}</div>
                    <div class="metric-label">Status Checks</div>
                </div>
                <div class="metric-item">
                    <div class="metric-value">${new Date(metrics.created_at).toLocaleDateString()}</div>
                    <div class="metric-label">Created</div>
                </div>
            </div>
        `;
        
        document.getElementById('modalTitle').textContent = 'Tunnel Metrics';
        document.getElementById('tunnelModal').style.display = 'block';
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Close modal
function closeModal() {
    document.getElementById('tunnelModal').style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('tunnelModal');
    if (event.target === modal) {
        closeModal();
    }
}

// Show status message
function showStatus(type, message) {
    const statusEl = document.getElementById('scanStatus');
    statusEl.textContent = message;
    statusEl.className = `status-message ${type}`;
}

// Show toast notification
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    refreshTunnels();
    
    // Auto-refresh tunnels every 5 seconds
    setInterval(refreshTunnels, 5000);
});
