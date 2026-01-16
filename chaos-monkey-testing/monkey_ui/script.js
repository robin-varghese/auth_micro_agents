const API_BASE = 'http://localhost:5007'; // Ensure this matches monkey_agent port

// State
let scenarios = [];
let activeScenarioId = null;

// DOM Elements
const scenarioListEl = document.getElementById('scenario-list');
const scenarioCountEl = document.getElementById('scenario-count');
const emptyStateEl = document.getElementById('empty-state');
const scenarioDetailsEl = document.getElementById('scenario-details');
const detailTitleEl = document.getElementById('detail-title');
const detailDescEl = document.getElementById('detail-description');
const detailExplanationEl = document.getElementById('detail-explanation');
const detailStepsEl = document.getElementById('detail-steps');
const orchestratorOutputEl = document.getElementById('orchestrator-output');
const toastEl = document.getElementById('toast');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchScenarios();
});

// Fetch Scenarios
async function fetchScenarios() {
    try {
        const response = await fetch(`${API_BASE}/scenarios`);
        if (!response.ok) throw new Error('Failed to fetch scenarios');

        scenarios = await response.json();
        renderScenarioList();
    } catch (error) {
        console.error('Error:', error);
        scenarioListEl.innerHTML = `<div class="error-msg">Failed to load scenarios.<br>${error.message}</div>`;
    }
}

// Render List
function renderScenarioList() {
    scenarioListEl.innerHTML = '';
    scenarioCountEl.textContent = scenarios.length;

    scenarios.forEach(scenario => {
        const card = document.createElement('div');
        card.className = `scenario-card ${activeScenarioId === scenario.id ? 'active' : ''}`;
        card.onclick = () => selectScenario(scenario.id);

        card.innerHTML = `
            <div class="card-title">${scenario.id}. ${scenario.name}</div>
            <div class="card-desc">${scenario.description}</div>
        `;

        scenarioListEl.appendChild(card);
    });
}

// Select Scenario
function selectScenario(id) {
    activeScenarioId = id;
    renderScenarioList(); // Re-render to update active class

    const scenario = scenarios.find(s => s.id === id);
    if (!scenario) return;

    // Show details pane
    emptyStateEl.style.display = 'none';
    scenarioDetailsEl.classList.remove('hidden');

    // Populate Data
    detailTitleEl.textContent = `${scenario.id}. ${scenario.name}`;
    detailDescEl.textContent = scenario.description;

    // Populate Overview
    detailExplanationEl.textContent = scenario.technical_explanation || "No explanation available.";

    // Populate Steps
    detailStepsEl.innerHTML = '';
    if (scenario.steps && scenario.steps.length > 0) {
        scenario.steps.forEach(step => {
            const li = document.createElement('li');
            li.textContent = step;
            detailStepsEl.appendChild(li);
        });
    } else {
        detailStepsEl.innerHTML = '<li>No steps defined.</li>';
    }

    orchestratorOutputEl.textContent = "Ready for execution...";
}

// Execute Action
async function executeAction(action) {
    if (!activeScenarioId) return;

    showToast(`Initiating ${action.toUpperCase()}...`);
    orchestratorOutputEl.textContent = `Sending ${action} request...`;

    try {
        const response = await fetch(`${API_BASE}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: activeScenarioId, action: action })
        });

        const data = await response.json();

        if (response.ok) {
            orchestratorOutputEl.textContent = JSON.stringify(data.orchestrator_response, null, 2);
            showToast(`${action.toUpperCase()} Completed!`);
        } else {
            orchestratorOutputEl.textContent = `Error: ${data.message || 'Unknown error'}`;
            showToast('Execution Failed', true);
        }
    } catch (error) {
        console.error('Execution Error:', error);
        orchestratorOutputEl.textContent = `Network Error: ${error.message}`;
        showToast('Network Error', true);
    }
}

// Toast
function showToast(msg, isError = false) {
    toastEl.textContent = msg;
    toastEl.style.backgroundColor = isError ? '#f85149' : '#58a6ff';
    toastEl.classList.remove('hidden');
    setTimeout(() => {
        toastEl.classList.add('hidden');
    }, 3000);
}
