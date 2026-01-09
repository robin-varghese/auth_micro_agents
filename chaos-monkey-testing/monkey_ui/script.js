// Configuration
// In production, this should be configurable. Assuming localhost mapping or relative path if proxied.
const API_URL = 'http://localhost:5007';

const container = document.getElementById('scenarios-container');
const logs = document.getElementById('console-logs');
const statusMsg = document.getElementById('status-message');

function log(msg) {
    const timestamp = new Date().toLocaleTimeString();
    logs.innerText = `[${timestamp}] ${msg}\n` + logs.innerText;
}

function showStatus(msg, type = 'normal') {
    statusMsg.innerText = msg;
    statusMsg.className = `status-bar ${type}`;
    setTimeout(() => {
        if (type !== 'loading') statusMsg.classList.add('hidden');
    }, 5000);
}

async function fetchScenarios() {
    try {
        const response = await fetch(`${API_URL}/scenarios`);
        if (!response.ok) throw new Error("Failed to fetch scenarios");
        const scenarios = await response.json();
        renderScenarios(scenarios);
        log("Scenarios loaded successfully.");
    } catch (e) {
        container.innerHTML = `<div class="error">Failed to load scenarios. Ensure Backend is running at ${API_URL}</div>`;
        log(`Error: ${e.message}`);
    }
}

async function executeAction(id, name, action) {
    try {
        showStatus(`Executing ${action.toUpperCase()} on ${name}...`, 'loading');
        log(`>>> REQUEST: ${action.toUpperCase()} - ${name} (ID: ${id})`);

        const response = await fetch(`${API_URL}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: id,
                action: action,
                user_email: "robin@cloudroaster.com"
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            showStatus(`${action.toUpperCase()} Initiated!`, 'success');
            log(`<<< SUCCESS: Orchestrator accepted the request.`);
            log(`Response: ${JSON.stringify(data.orchestrator_response, null, 2)}`);
        } else {
            throw new Error(data.message || "Unknown error");
        }

    } catch (e) {
        showStatus(`Failed: ${e.message}`, 'error');
        log(`<<< ERROR: ${e.message}`);
    }
}

function renderScenarios(list) {
    container.innerHTML = '';
    // Sort by ID
    list.sort((a, b) => parseInt(a.id) - parseInt(b.id));

    list.forEach(item => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <div>
                <h3>#${item.id} ${item.name}</h3>
                <p>${item.description}</p>
            </div>
            <div class="actions">
                <button class="btn-break" onclick="executeAction('${item.id}', '${item.name}', 'break')">🔥 Break</button>
                <button class="btn-restore" onclick="executeAction('${item.id}', '${item.name}', 'restore')">🚑 Restore</button>
            </div>
        `;
        container.appendChild(card);
    });
}

// Initialize
fetchScenarios();
