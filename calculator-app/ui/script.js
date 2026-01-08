let currentExpression = '';

function updateDisplay() {
    const display = document.getElementById('display');
    display.textContent = currentExpression || '0';
}

function appendNumber(num) {
    if (num === '.' && currentExpression.includes('.') && !isLastCharOperator()) return;
    currentExpression += num;
    updateDisplay();
}

function appendOperator(op) {
    if (currentExpression === '') return;
    if (isLastCharOperator()) {
        currentExpression = currentExpression.slice(0, -1);
    }
    currentExpression += op;
    updateDisplay();
}

function isLastCharOperator() {
    const operators = ['+', '-', '*', '/'];
    return operators.includes(currentExpression.slice(-1));
}

function clearDisplay() {
    currentExpression = '';
    updateDisplay();
}

function deleteChar() {
    currentExpression = currentExpression.slice(0, -1);
    updateDisplay();
}

async function calculate() {
    if (currentExpression === '') return;

    try {
        const response = await fetch('/api/calculate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ expression: currentExpression })
        });

        const data = await response.json();

        if (response.ok) {
            currentExpression = data.result.toString();
            updateDisplay();
            fetchHistory(); // Update history immediately
        } else {
            alert('Error: ' + data.detail);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to calculate');
    }
}

async function fetchHistory() {
    try {
        const response = await fetch('/api/history');
        const history = await response.json();

        const list = document.getElementById('history-list');
        list.innerHTML = '';

        history.forEach(item => {
            const li = document.createElement('li');
            li.className = 'history-item';
            li.innerHTML = `
                <span class="history-expr">${item.expression}</span>
                <span class="history-result">= ${item.result}</span>
            `;
            list.appendChild(li);
        });
    } catch (error) {
        console.error('Failed to fetch history:', error);
    }
}

// Load history on start
fetchHistory();
