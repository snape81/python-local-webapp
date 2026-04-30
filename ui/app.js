async function loadStatus() {
    const result = await window.pywebview.api.get_status();
    document.getElementById('status').textContent = JSON.stringify(result, null, 2);
}

async function sendConfig() {
    const input = document.getElementById('configInput').value;
    let json;

    try {
        json = JSON.parse(input);
    } catch (e) {
        alert('Invalid JSON');
        return;
    }

    const result = await window.pywebview.api.set_config(json);
    alert(JSON.stringify(result));
}
