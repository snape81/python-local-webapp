const ipInput = document.getElementById('rtu-ip');
const attestButton = document.getElementById('attest-button');
const verifyButton = document.getElementById('verify-button');
const connectionStatus = document.getElementById('connection-status');
let backendReady = false;
let busy = false;

function updateControls() {
    attestButton.disabled = !backendReady || busy;
    verifyButton.disabled = !backendReady || busy;
    ipInput.disabled = busy;
}

function renderReport(container, report) {
    container.replaceChildren();
    const title = document.createElement('h3');
    title.textContent = `Esito finale: ${report.status}`;
    title.className = `result-${report.status.toLowerCase()}`;
    container.append(title);
    const message = document.createElement('p');
    message.textContent = `${report.ip ? `RTU ${report.ip}: ` : ''}${report.message}`;
    container.append(message);
    const list = document.createElement('ol');
    for (const [index, test] of (report.tests || []).entries()) {
        const item = document.createElement('li');
        const result = document.createElement('strong');
        result.textContent = `Test ${index + 1}: ${test.name} - ${test.status}`;
        result.className = `result-${test.status.toLowerCase()}`;
        const detail = document.createElement('p');
        detail.textContent = test.detail;
        item.append(result, detail);
        list.append(item);
    }
    container.append(list);
}

async function executeOperation(method, target) {
    if (busy || !backendReady) return;
    const container = document.getElementById(target);
    const ip = ipInput.value.trim();
    if (!ip) {
        container.textContent = 'Inserire l\'indirizzo IP della RTU.';
        ipInput.focus();
        return;
    }
    busy = true;
    updateControls();
    container.textContent = `Operazione in corso sulla RTU ${ip}. Attendere...`;
    try {
        const report = await window.pywebview.api[method](ip);
        renderReport(container, report);
    } catch (error) {
        container.textContent = 'Errore del backend locale. Consultare i log prima di riprovare.';
        console.error('Operazione RTU fallita', error);
    } finally {
        busy = false;
        updateControls();
    }
}

attestButton.addEventListener('click', () => executeOperation('attest_rtu', 'attest-report'));
verifyButton.addEventListener('click', () => executeOperation('verify_attestation', 'verify-report'));

function initializeBackend() {
    if (!window.pywebview || !window.pywebview.api) return;
    backendReady = true;
    connectionStatus.textContent = 'Backend locale pronto.';
    updateControls();
}

window.addEventListener('pywebviewready', initializeBackend);
initializeBackend();
