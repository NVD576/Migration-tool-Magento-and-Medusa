document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    const logContainer = document.getElementById('log-container');
    let isRunning = false;

    // UI Elements
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const statusIndicator = document.getElementById('status-indicator');

    // Forms
    const magentoForm = document.getElementById('magento-form');
    const medusaForm = document.getElementById('medusa-form');

    // Socket Events
    socket.on('connect', () => {
        logSystem("Connected to server via WebSocket.");
    });

    socket.on('log', (msg) => {
        appendLog(msg.data);
    });

    socket.on('status_update', (data) => {
        isRunning = data.running;
        updateUIState(isRunning);
        if (data.message) logSystem(data.message, 'success');
        if (data.error) logSystem(data.error, 'error');
    });

    // Logging helpers
    function appendLog(text) {
        if (!text) return;
        const div = document.createElement('div');
        div.className = 'log-line';

        // Simple heuristic for coloring
        if (text.includes('❌') || text.includes('[FAIL]') || text.includes('Error')) div.classList.add('log-error');
        else if (text.includes('⚠️') || text.includes('[WARNING]')) div.classList.add('log-warning');
        else if (text.includes('✅') || text.includes('[SUCCESS]')) div.classList.add('log-success');
        else if (text.includes('➡') || text.includes('🚀')) div.classList.add('log-info');

        // Strip emojis
        // Strip emojis and symbols (Broad range: U+2000 to U+2BFF, plus high surrogates)
        text = text.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2000}-\u{2BFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{2300}-\u{23FF}]/gu, '');

        div.textContent = text;
        logContainer.appendChild(div);

        // Auto scroll
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function logSystem(msg, type = 'dim') {
        const div = document.createElement('div');
        div.className = `log-line log-${type} fst-italic`;
        div.textContent = `[SYSTEM] ${msg}`;
        logContainer.appendChild(div);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    document.getElementById('btn-clear-log').addEventListener('click', () => {
        logContainer.innerHTML = '';
    });

    // Toggle Password Visibility
    document.querySelectorAll('.toggle-pass').forEach(btn => {
        btn.addEventListener('click', function () {
            const input = this.previousElementSibling;
            if (input.type === 'password') {
                input.type = 'text';
                this.innerHTML = '<i class="bi bi-eye-slash"></i>';
            } else {
                input.type = 'password';
                this.innerHTML = '<i class="bi bi-eye"></i>';
            }
        });
    });

    // Form Submissions

    async function handleAuth(url, fd, btn) {
        const originalText = btn.innerHTML;
        const spinner = btn.querySelector('.spinner-border');

        btn.disabled = true;
        spinner.classList.remove('d-none');

        const data = Object.fromEntries(fd.entries());
        // Checkbox handling
        if (url.includes('magento')) {
            data.verify_ssl = fd.get('verify_ssl') === 'on';
        }

        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await res.json();

            if (result.success) {
                const sysName = url.includes('magento') ? 'Magento' : 'Medusa';
                logSystem(`${sysName} Authentication successful! Token: ${result.token.substring(0, 10)}...`, 'success');
                btn.classList.add('btn-success');
                setTimeout(() => btn.classList.remove('btn-success'), 2000);
            } else {
                logSystem(`Authentication failed: ${result.error}`, 'error');
                alert(`Error: ${result.error}`);
            }
        } catch (e) {
            logSystem(`Network error: ${e.message}`, 'error');
        } finally {
            btn.disabled = false;
            spinner.classList.add('d-none');
        }
    }

    magentoForm.addEventListener('submit', (e) => {
        e.preventDefault();
        handleAuth('/api/test-magento', new FormData(magentoForm), document.getElementById('btn-test-magento'));
    });

    medusaForm.addEventListener('submit', (e) => {
        e.preventDefault();
        handleAuth('/api/test-medusa', new FormData(medusaForm), document.getElementById('btn-test-medusa'));
    });

    // Control Buttons
    btnStart.addEventListener('click', async () => {
        if (!validateReady()) return;

        const config = gatherConfig();

        btnStart.disabled = true;

        try {
            const res = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const result = await res.json();
            if (result.success) {
                updateUIState(true);
            } else {
                alert(result.error);
                btnStart.disabled = false;
                logSystem(result.error, 'error');
            }
        } catch (e) {
            btnStart.disabled = false;
            alert(e.message);
        }
    });

    btnStop.addEventListener('click', async () => {
        await fetch('/api/stop', { method: 'POST' });
        logSystem("Stop command sent...", 'warning');
    });

    function updateUIState(running) {
        isRunning = running;
        if (running) {
            statusIndicator.textContent = 'Running';
            statusIndicator.className = 'badge bg-success animate-pulse';
            btnStart.classList.add('d-none');
            btnStop.classList.remove('d-none');
            // Disable inputs? Maybe later
        } else {
            statusIndicator.textContent = 'Idle';
            statusIndicator.className = 'badge bg-secondary';
            btnStart.classList.remove('d-none');
            btnStop.classList.add('d-none');
            btnStart.disabled = false;
        }
    }

    function gatherConfig() {
        const entities = [];
        document.querySelectorAll('.entity-check:checked').forEach(c => entities.push(c.value));

        // Helper to get form data
        const getFormData = (form) => {
            const fd = new FormData(form);
            const d = Object.fromEntries(fd.entries());
            if (form === magentoForm) d.verify_ssl = fd.get('verify_ssl') === 'on';
            return d;
        };

        return {
            magento: getFormData(magentoForm),
            medusa: getFormData(medusaForm),
            entities: entities,
            limit: document.getElementById('opt_limit').value,
            product_ids: document.getElementById('ids_products').value,
            category_ids: document.getElementById('ids_categories').value,
            customer_ids: document.getElementById('ids_customers').value,
            order_ids: document.getElementById('ids_orders').value,
            dry_run: document.getElementById('opt_dry_run').checked,
            finalize_orders: document.getElementById('opt_finalize').checked,
            migrate_invoices: document.getElementById('opt_migrate_invoices').checked,
            migrate_payments: document.getElementById('opt_migrate_payments').checked,
            rollback_on_finalize_fail: document.getElementById('opt_rollback_finalize').checked,
            delta_migration: document.getElementById('opt_delta_migration').checked,
            delta_from_date: document.getElementById('opt_delta_from_date').value || null,
            max_workers: 10
        };
    }

    function validateReady() {
        const magentoData = new FormData(magentoForm);
        const medusaData = new FormData(medusaForm);

        if (!magentoData.get('base_url') || !magentoData.get('username')) {
            alert('Please configure Magento Connection first.');
            return false;
        }
        if (!medusaData.get('base_url') || !medusaData.get('email')) {
            alert('Please configure Medusa Connection first.');
            return false;
        }
        return true;
    }

    // Modal Selection Logic
    const selectionModal = new bootstrap.Modal(document.getElementById('selectionModal'));
    let currentSelectType = null;
    let currentTargetInput = null;

    document.querySelectorAll('.btn-select').forEach(btn => {
        btn.addEventListener('click', async () => {
            const type = btn.dataset.type;
            const inputId = `ids_${type}`;
            currentTargetInput = document.getElementById(inputId);
            currentSelectType = type;

            // Check auth implicitly by asking for data
            const magentoData = new FormData(magentoForm);
            if (!magentoData.get('base_url')) {
                alert('Please enter Magento Base URL first');
                return;
            }

            const listContainer = document.getElementById('modal-list');
            listContainer.innerHTML = '<div class="text-center py-4"><span class="spinner-border"></span> Fetching data...</div>';

            selectionModal.show();

            // Fetch items
            const config = {
                type: type,
                magento_config: {
                    base_url: magentoData.get('base_url'),
                    username: magentoData.get('username'),
                    password: magentoData.get('password'),
                    verify_ssl: magentoData.get('verify_ssl') === 'on'
                }
            };

            try {
                const res = await fetch('/api/fetch-entities', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                const result = await res.json();

                if (result.success) {
                    renderModalItems(result.items, currentTargetInput.value);
                } else {
                    listContainer.innerHTML = `<div class="text-danger p-3">${result.error}</div>`;
                }
            } catch (e) {
                listContainer.innerHTML = `<div class="text-danger p-3">${e.message}</div>`;
            }
        });
    });

    function renderModalItems(items, currentValues) {
        const listContainer = document.getElementById('modal-list');
        listContainer.innerHTML = '';
        const searchInput = document.getElementById('modal-search');

        const selectedIds = new Set(currentValues.split(',').map(s => s.trim()).filter(s => s));

        window.currentModalItems = items; // Store for filtering

        function renderList(filteredItems) {
            listContainer.innerHTML = '';
            filteredItems.forEach(item => {
                const lbl = document.createElement('label');
                lbl.className = 'list-group-item d-flex gap-2';
                lbl.innerHTML = `
                    <input class="form-check-input flex-shrink-0" type="checkbox" value="${item.id}" ${selectedIds.has(String(item.id)) ? 'checked' : ''}>
                    <span>${item.label}</span>
                `;
                listContainer.appendChild(lbl);
            });
            if (filteredItems.length === 0) listContainer.innerHTML = '<div class="p-3 text-muted">No items found</div>';
        }

        renderList(items);

        searchInput.oninput = (e) => {
            const term = e.target.value.toLowerCase();
            const filtered = items.filter(i => i.label.toLowerCase().includes(term));
            renderList(filtered);
        };
    }

    document.getElementById('modal-confirm').addEventListener('click', () => {
        const checked = document.querySelectorAll('#modal-list input:checked');
        const ids = Array.from(checked).map(cb => cb.value);
        if (currentTargetInput) {
            currentTargetInput.value = ids.join(', ');
        }
        selectionModal.hide();
    });

    document.getElementById('modal-select-all').addEventListener('click', () => {
        document.querySelectorAll('#modal-list input').forEach(cb => cb.checked = true);
    });

    document.getElementById('modal-deselect-all').addEventListener('click', () => {
        document.querySelectorAll('#modal-list input').forEach(cb => cb.checked = false);
    });
});
