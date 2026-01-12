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
    const remoteForm = document.getElementById('remoteForm');
    const remoteDynamicForm = document.getElementById('remote-dynamicForm');
    const tabs = document.querySelectorAll('.tab-btn');
    
    tabs.forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    
    // Hide all forms
    staticForm.style.display = 'none';
    dynamicForm.style.display = 'none';
    remoteForm.style.display = 'none';
    remoteDynamicForm.style.display = 'none';
    
    // Show selected form
    if (tab === 'static') {
        staticForm.style.display = 'block';
    } else if (tab === 'dynamic') {
        dynamicForm.style.display = 'block';
    } else if (tab === 'remote') {
        remoteForm.style.display = 'block';
    } else if (tab === 'remote-dynamic') {
        remoteDynamicForm.style.display = 'block';
    }
}

// Start nmap scan
async function startScan() {
    const target = document.getElementById('scanTarget').value.trim();
    const scanType = document.getElementById('scanType').value;
    
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
                loadScanHistory(); // Refresh scan history
            } else if (data.status === 'failed') {
                clearInterval(scanInterval);
                document.getElementById('scanProgress').style.display = 'none';
                showStatus('error', `Scan failed: ${data.error || 'Unknown error'}`);
                loadScanHistory(); // Refresh scan history
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

// Create remote tunnel
async function createRemoteTunnel() {
    const sshUser = document.getElementById('remoteSshUser').value.trim();
    const sshHost = document.getElementById('remoteSshHost').value.trim();
    const remoteBindPort = parseInt(document.getElementById('remoteBindPort').value);
    const bindAddress = document.getElementById('remoteBindAddress').value.trim() || '127.0.0.1';
    const targetHost = document.getElementById('remoteTargetHost').value.trim();
    const targetPort = parseInt(document.getElementById('remoteTargetPort').value);
    const execute = document.getElementById('remoteExecute').checked;
    
    if (!sshUser || !sshHost || !remoteBindPort || !targetHost || !targetPort) {
        showToast('Please fill all required fields', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/tunnels/remote', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ssh_user: sshUser,
                ssh_host: sshHost,
                remote_bind_port: remoteBindPort,
                target_host: targetHost,
                target_port: targetPort,
                bind_address: bindAddress,
                execute: execute
            })
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast('Remote tunnel created successfully!', 'success');
            if (!execute) {
                showToast(`Command: ${data.command}`, 'info');
            }
            refreshTunnels();
            document.getElementById('remoteForm').reset();
        } else {
            showToast(data.detail || 'Failed to create tunnel', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Create remote dynamic tunnel
async function createRemoteDynamicTunnel() {
    const sshUser = document.getElementById('remoteDynamicSshUser').value.trim();
    const sshHost = document.getElementById('remoteDynamicSshHost').value.trim();
    const remoteSocksPort = parseInt(document.getElementById('remoteDynamicSocksPort').value);
    const bindAddress = document.getElementById('remoteDynamicBindAddress').value.trim() || '127.0.0.1';
    const execute = document.getElementById('remoteDynamicExecute').checked;
    
    if (!sshUser || !sshHost || !remoteSocksPort) {
        showToast('Please fill all required fields', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/tunnels/remote-dynamic', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ssh_user: sshUser,
                ssh_host: sshHost,
                remote_socks_port: remoteSocksPort,
                bind_address: bindAddress,
                execute: execute
            })
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast('Remote dynamic tunnel created successfully!', 'success');
            if (!execute) {
                showToast(`Command: ${data.command}`, 'info');
            }
            refreshTunnels();
            document.getElementById('remote-dynamicForm').reset();
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
        const badgeClass = tunnel.type === 'static' ? 'badge-static' : 
                          tunnel.type === 'dynamic' ? 'badge-dynamic' :
                          tunnel.type === 'remote' ? 'badge-remote' : 'badge-remote-dynamic';
        const statusBadgeClass = tunnel.status === 'active' ? 'badge-active' : 'badge-stopped';
        
        let remoteInfo = '';
        if (tunnel.type === 'static') {
            remoteInfo = `${tunnel.remote_host}:${tunnel.remote_port}`;
        } else if (tunnel.type === 'dynamic') {
            remoteInfo = 'SOCKS Proxy';
        } else if (tunnel.type === 'remote') {
            remoteInfo = `${tunnel.bind_address}:${tunnel.remote_bind_port} -> ${tunnel.target_host}:${tunnel.target_port}`;
        } else if (tunnel.type === 'remote_dynamic') {
            remoteInfo = `Remote SOCKS Proxy (${tunnel.bind_address}:${tunnel.remote_socks_port})`;
        }
        
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
                    ${tunnel.type === 'static' || tunnel.type === 'dynamic' ? `
                        <div class="tunnel-detail-item">
                            <strong>Local Port:</strong> ${tunnel.local_port}
                        </div>
                    ` : ''}
                    ${tunnel.type === 'remote' ? `
                        <div class="tunnel-detail-item">
                            <strong>Remote Bind:</strong> ${tunnel.bind_address}:${tunnel.remote_bind_port}
                        </div>
                        <div class="tunnel-detail-item">
                            <strong>Target:</strong> ${tunnel.target_host}:${tunnel.target_port}
                        </div>
                    ` : ''}
                    ${tunnel.type === 'remote_dynamic' ? `
                        <div class="tunnel-detail-item">
                            <strong>Remote SOCKS Port:</strong> ${tunnel.bind_address}:${tunnel.remote_socks_port}
                        </div>
                    ` : ''}
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
        let detailsHtml = `
            <div class="tunnel-details">
                <div><strong>Type:</strong> ${tunnel.type}</div>
                <div><strong>Status:</strong> ${tunnel.status}</div>
        `;
        
        if (tunnel.type === 'static' || tunnel.type === 'dynamic') {
            detailsHtml += `<div><strong>Local Port:</strong> ${tunnel.local_port}</div>`;
            if (tunnel.type === 'static') {
                detailsHtml += `
                    <div><strong>Remote Host:</strong> ${tunnel.remote_host}</div>
                    <div><strong>Remote Port:</strong> ${tunnel.remote_port}</div>
                `;
            }
        } else if (tunnel.type === 'remote') {
            detailsHtml += `
                <div><strong>Remote Bind:</strong> ${tunnel.bind_address}:${tunnel.remote_bind_port}</div>
                <div><strong>Target Host:</strong> ${tunnel.target_host}</div>
                <div><strong>Target Port:</strong> ${tunnel.target_port}</div>
            `;
        } else if (tunnel.type === 'remote_dynamic') {
            detailsHtml += `
                <div><strong>Remote SOCKS Port:</strong> ${tunnel.bind_address}:${tunnel.remote_socks_port}</div>
            `;
        }
        
        detailsHtml += `
                <div><strong>SSH User:</strong> ${tunnel.ssh_user}</div>
                <div><strong>SSH Host:</strong> ${tunnel.ssh_host}</div>
                <div><strong>PID:</strong> ${tunnel.pid || 'N/A'}</div>
                <div><strong>Created:</strong> ${new Date(tunnel.created_at).toLocaleString()}</div>
            </div>
            <div style="margin-top: 20px;">
                <strong>Command:</strong>
                <pre style="background: #0a0000; color: var(--hacker-red); padding: 10px; border-radius: 4px; overflow-x: auto; border: 1px solid var(--hacker-red);">${tunnel.command}</pre>
            </div>
        `;
        
        modalBody.innerHTML = detailsHtml;
        
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

// Load scan history
async function loadScanHistory() {
    try {
        const response = await fetch('/api/scans');
        const data = await response.json();
        displayScanHistory(data.scans);
    } catch (error) {
        console.error('Error loading scan history:', error);
    }
}

// Display scan history
function displayScanHistory(scans) {
    const historyList = document.getElementById('scanHistoryList');
    if (!historyList) return;
    
    if (scans.length === 0) {
        historyList.innerHTML = '<p style="color: #666;">No scans yet. Start a scan to see history.</p>';
        return;
    }
    
    historyList.innerHTML = scans.map(scan => {
        const statusClass = scan.status === 'completed' ? 'success' : 
                           scan.status === 'running' ? 'info' : 
                           scan.status === 'failed' ? 'error' : 'pending';
        const statusIcon = scan.status === 'completed' ? '✓' : 
                          scan.status === 'running' ? '⟳' : 
                          scan.status === 'failed' ? '✗' : '○';
        
        return `
            <div class="scan-history-item" style="padding: 15px; margin: 10px 0; background: #1a0000; border-left: 4px solid var(--hacker-${statusClass === 'success' ? 'red' : statusClass === 'error' ? 'red' : 'orange'}); border-radius: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="color: var(--hacker-red);">${statusIcon} ${scan.target}</strong>
                        <span style="color: var(--hacker-orange); margin-left: 10px;">[${scan.scan_type}]</span>
                        <div style="color: #888; font-size: 0.9em; margin-top: 5px;">
                            Status: <span style="color: var(--hacker-${statusClass === 'success' ? 'red' : statusClass === 'error' ? 'red' : 'orange'});">${scan.status}</span>
                            ${scan.service_count > 0 ? `| Services: ${scan.service_count}` : ''}
                        </div>
                    </div>
                    <div style="color: #666; font-size: 0.85em;">
                        ${new Date(scan.created_at).toLocaleString()}
                    </div>
                </div>
                ${scan.progress ? `<div style="color: #888; margin-top: 5px; font-size: 0.9em;">${scan.progress}</div>` : ''}
            </div>
        `;
    }).join('');
}

// Generate Proxychains configuration
async function generateProxychainsConfig() {
    const proxyType = document.getElementById('proxyType').value;
    const proxyHost = document.getElementById('proxyHost').value.trim();
    const proxyPort = parseInt(document.getElementById('proxyPort').value);
    const chainType = document.getElementById('chainType').value;
    
    if (!proxyHost || !proxyPort) {
        showToast('Please enter proxy host and port', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/proxychains/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                proxy_type: proxyType,
                proxy_host: proxyHost,
                proxy_port: proxyPort,
                chain_type: chainType
            })
        });
        
        const data = await response.json();
        if (response.ok) {
            document.getElementById('proxychainsConfig').textContent = data.config;
            const instructions = data.instructions;
            document.getElementById('proxychainsInstructions').innerHTML = `
                <strong style="color: var(--hacker-orange);">Instructions:</strong><br>
                <strong>Linux:</strong> ${instructions.linux}<br>
                <strong>Usage:</strong> <code style="color: var(--hacker-red);">${instructions.usage}</code><br>
                <strong>Note:</strong> ${instructions.note}
            `;
            document.getElementById('proxychainsOutput').style.display = 'block';
            showToast('Proxychains configuration generated!', 'success');
        } else {
            showToast(data.detail || 'Failed to generate config', 'error');
        }
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Copy proxychains config to clipboard
function copyProxychainsConfig() {
    const configText = document.getElementById('proxychainsConfig').textContent;
    navigator.clipboard.writeText(configText).then(() => {
        showToast('Configuration copied to clipboard!', 'success');
    }).catch(() => {
        showToast('Failed to copy to clipboard', 'error');
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    refreshTunnels();
    loadScanHistory();
    setInterval(refreshTunnels, 5000);
    setInterval(loadScanHistory, 3000); // Refresh scan history every 3 seconds
});
