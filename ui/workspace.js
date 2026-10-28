/**
 * Life_mean Workspace - Programmable Tool Interface
 * 
 * Provides a unified API for both human users and AI agents.
 * All actions return structured responses: { ok, action, data, error, timestamp }
 */

(function() {
    'use strict';

    // ============================================================================
    // Core State Management
    // ============================================================================

    const WorkspaceState = {
        currentFile: null,
        files: {},
        history: [],
        params: new Map(),
        isRunning: false,
        currentRunId: null,
        model: '',
        workflow: '',
        settings: {
            apiKey: '',
            baseUrl: 'http://localhost:1234/v1',
            defaultModel: 'kwaipilot_kat-coder-v2.5-dev'
        }
    };

    // ============================================================================
    // Response Factory
    // ============================================================================

    function createResponse(action, data = null, error = null) {
        return {
            ok: error === null,
            action,
            data,
            error,
            timestamp: new Date().toISOString()
        };
    }

    // ============================================================================
    // Console / Logging
    // ============================================================================

    function logToConsole(message, type = 'info') {
        const consoleEl = document.getElementById('consoleOutput');
        if (!consoleEl) return;

        const timestamp = new Date().toLocaleTimeString();
        const prefix = {
            info: '[INFO]',
            success: '[OK]',
            error: '[ERR]',
            warning: '[WARN]',
            system: '[SYS]'
        }[type] || '[INFO]';

        const line = document.createElement('div');
        line.textContent = `[${timestamp}] ${prefix} ${message}`;
        line.dataset.type = type;
        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    // ============================================================================
    // History Management
    // ============================================================================

    function addToHistory(action, data) {
        const entry = {
            timestamp: new Date().toISOString(),
            action,
            data
        };
        WorkspaceState.history.unshift(entry);
        if (WorkspaceState.history.length > 100) {
            WorkspaceState.history.pop();
        }
        renderHistory();
    }

    function renderHistory() {
        const list = document.getElementById('actionHistory');
        if (!list) return;

        list.innerHTML = WorkspaceState.history.slice(0, 50).map(entry => `
            <li data-action="${entry.action}">${entry.timestamp.split('T')[1].split('.')[0]} - ${entry.action}</li>
        `).join('');
    }

    // ============================================================================
    // API Client (communicates with dashboard server)
    // ============================================================================

    const ApiClient = {
        async request(endpoint, method = 'GET', body = null) {
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };
            if (body) {
                options.body = JSON.stringify(body);
            }

            try {
                const response = await fetch(`/api${endpoint}`, options);
                const data = await response.json();
                return createResponse(endpoint, data);
            } catch (error) {
                return createResponse(endpoint, null, error.message);
            }
        },

        async getExperiments() {
            return this.request('/experiments');
        },

        async getCodeLabRuns() {
            return this.request('/code-lab/runs');
        },

        async startCodeLabRun(config) {
            return this.request('/code-lab/runs', 'POST', config);
        },

        async stopCodeLabRun(runId) {
            return this.request(`/code-lab/runs/${runId}/stop`);
        },

        async getCodeLabEvents(runId) {
            return this.request(`/code-lab/runs/${runId}/events`);
        },

        async getCodeLabFiles(runId) {
            return this.request(`/code-lab/runs/${runId}/files`);
        },

        async readCodeLabFile(runId, filePath) {
            return this.request(`/code-lab/runs/${runId}/file/${encodeURIComponent(filePath)}`);
        },

        async getConfig() {
            return this.request('/config');
        },

        async getSettings() {
            return this.request('/settings');
        }
    };

    // ============================================================================
    // Public Workspace API (for humans and agents)
    // ============================================================================

    const workspace = {
        // File operations
        async readFile(path) {
            if (!WorkspaceState.currentRunId) {
                return createResponse('readFile', null, 'No active run');
            }
            const result = await ApiClient.readCodeLabFile(WorkspaceState.currentRunId, path);
            if (result.ok) {
                WorkspaceState.files[path] = result.data;
                WorkspaceState.currentFile = path;
                this.updateEditor(path, result.data);
            }
            return result;
        },

        async writeFile(path, content) {
            if (!WorkspaceState.currentRunId) {
                return createResponse('writeFile', null, 'No active run');
            }
            // Simulate file write (in real implementation, would POST to API)
            WorkspaceState.files[path] = content;
            WorkspaceState.currentFile = path;
            this.updateEditor(path, content);
            addToHistory('writeFile', { path, size: content.length });
            logToConsole(`Fichier écrit: ${path}`, 'success');
            return createResponse('writeFile', { path, size: content.length });
        },

        async listFiles() {
            if (!WorkspaceState.currentRunId) {
                return createResponse('listFiles', [], 'No active run');
            }
            const result = await ApiClient.getCodeLabFiles(WorkspaceState.currentRunId);
            return result;
        },

        // Code execution
        async runCode(code, model = null) {
            const config = {
                prompt: code || 'def hello():\n    print("Hello")',
                model: model || WorkspaceState.model || WorkspaceState.settings.defaultModel
            };
            const result = await ApiClient.startCodeLabRun(config);
            if (result.ok) {
                WorkspaceState.currentRunId = result.data.run_id;
                WorkspaceState.isRunning = true;
                this.updateButtons(true);
                logToConsole(`Run démarré: ${result.data.run_id}`, 'success');
                addToHistory('runCode', { runId: result.data.run_id });
            } else {
                logToConsole(`Erreur run: ${result.error}`, 'error');
            }
            return result;
        },

        async stopRun() {
            if (!WorkspaceState.currentRunId) {
                return createResponse('stopRun', null, 'No active run');
            }
            const result = await ApiClient.stopCodeLabRun(WorkspaceState.currentRunId);
            if (result.ok) {
                WorkspaceState.isRunning = false;
                this.updateButtons(false);
                logToConsole(`Run arrêté: ${WorkspaceState.currentRunId}`, 'warning');
                addToHistory('stopRun', { runId: WorkspaceState.currentRunId });
            }
            return result;
        },

        // Prompt execution
        async runPrompt(prompt, model = null) {
            const config = {
                prompt: prompt,
                model: model || WorkspaceState.model || WorkspaceState.settings.defaultModel
            };
            const result = await ApiClient.startCodeLabRun(config);
            if (result.ok) {
                WorkspaceState.currentRunId = result.data.run_id;
                WorkspaceState.isRunning = true;
                this.updateButtons(true);
                logToConsole(`Prompt exécuté: ${prompt.substring(0, 50)}...`, 'success');
                addToHistory('runPrompt', { runId: result.data.run_id, prompt: prompt.substring(0, 50) });
            }
            return result;
        },

        // Workflow operations
        async runWorkflow(name, input = null) {
            const config = {
                workflow_name: name,
                input: input || {}
            };
            const result = await ApiClient.startCodeLabRun(config);
            if (result.ok) {
                WorkspaceState.currentRunId = result.data.run_id;
                addToHistory('runWorkflow', { name, runId: result.data.run_id });
                logToConsole(`Workflow "${name}" démarré`, 'success');
            }
            return result;
        },

        // State management
        getState() {
            return createResponse('getState', {
                currentFile: WorkspaceState.currentFile,
                files: Object.keys(WorkspaceState.files),
                isRunning: WorkspaceState.isRunning,
                currentRunId: WorkspaceState.currentRunId,
                model: WorkspaceState.model,
                workflow: WorkspaceState.workflow,
                settings: WorkspaceState.settings,
                historyLength: WorkspaceState.history.length
            });
        },

        async setValue(key, value) {
            WorkspaceState.params.set(key, value);
            renderParams();
            addToHistory('setValue', { key, value });
            return createResponse('setValue', { key, value });
        },

        async getValue(key) {
            const value = WorkspaceState.params.get(key);
            return createResponse('getValue', { key, value });
        },

        // Settings
        async saveSettings(settings) {
            WorkspaceState.settings = { ...WorkspaceState.settings, ...settings };
            addToHistory('saveSettings', settings);
            logToConsole('Paramètres sauvegardés', 'success');
            return createResponse('saveSettings', WorkspaceState.settings);
        },

        // Internal helpers
        updateEditor(path, content) {
            const editor = document.getElementById('codeEditor');
            if (editor && content !== undefined) {
                editor.value = content;
            }
            const pathDisplay = document.querySelector('[data-tool="current-file"]');
            if (pathDisplay) {
                pathDisplay.textContent = path || 'Aucun fichier ouvert';
                pathDisplay.dataset.state = path || '';
            }
        },

        updateButtons(isRunning) {
            const runBtn = document.getElementById('runBtn');
            const stopBtn = document.getElementById('stopBtn');
            if (runBtn) runBtn.disabled = isRunning;
            if (stopBtn) stopBtn.disabled = !isRunning;
        }
    };

    // ============================================================================
    // UI Event Handlers
    // ============================================================================

    function initEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const view = btn.dataset.view;
                switchView(view);
            });
        });

        // Tool items
        document.querySelectorAll('.tool-item').forEach(item => {
            item.addEventListener('click', () => {
                const toolId = item.dataset.toolId;
                openTool(toolId);
            });
        });

        // Toolbar buttons
        document.querySelector('[data-action="new_file"]')?.addEventListener('click', createNewFile);
        document.querySelector('[data-action="save_file"]')?.addEventListener('click', saveFile);
        document.querySelector('[data-action="run_code"]')?.addEventListener('click', runCodeFromEditor);

        // Run/Stop buttons
        document.getElementById('runBtn')?.addEventListener('click', () => workspace.runCode(document.getElementById('codeEditor').value));
        document.getElementById('stopBtn')?.addEventListener('click', () => workspace.stopRun());

        // Model/Workflow selectors
        document.getElementById('modelSelect')?.addEventListener('change', (e) => {
            WorkspaceState.model = e.target.value;
            logToConsole(`Modèle sélectionné: ${e.target.value}`, 'info');
        });

        document.getElementById('workflowSelect')?.addEventListener('change', (e) => {
            WorkspaceState.workflow = e.target.value;
            logToConsole(`Workflow sélectionné: ${e.target.value}`, 'info');
        });

        // Console input
        const consoleInput = document.getElementById('consoleInput');
        consoleInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                executeConsoleCommand(consoleInput.value);
                consoleInput.value = '';
            }
        });

        // Clear console
        document.querySelector('[data-action="clear_console"]')?.addEventListener('click', () => {
            const consoleEl = document.getElementById('consoleOutput');
            if (consoleEl) consoleEl.innerHTML = '';
        });

        // Panel collapse
        document.querySelectorAll('.collapse-btn').forEach(btn => {
            btn.addEventListener('click', togglePanel);
        });

        // Add param button
        document.querySelector('[data-action="add_param"]')?.addEventListener('click', addParamRow);

        // Apply workflow
        document.querySelector('[data-action="apply_workflow"]')?.addEventListener('click', applyWorkflowConfig);

        // Save settings
        document.querySelector('[data-action="save_settings"]')?.addEventListener('click', saveSettingsFromUI);
    }

    function switchView(viewId) {
        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.remove('active');
        });

        const targetPanel = document.getElementById(`${viewId}View`) || 
                           document.querySelector(`[data-view-id="${viewId}"]`);
        if (targetPanel) {
            targetPanel.classList.add('active');
        }

        document.querySelector(`.nav-btn[data-view="${viewId}"]`)?.classList.add('active');
    }

    function openTool(toolId) {
        logToConsole(`Outil ouvert: ${toolId}`, 'info');
        // Map tool IDs to views
        const toolToView = {
            'file-explorer': 'editor',
            'code-editor': 'editor',
            'prompt-zone': 'editor',
            'json-viewer': 'history',
            'params-editor': 'settings'
        };
        const view = toolToView[toolId];
        if (view) switchView(view);
    }

    function togglePanel() {
        const panel = event.target.closest('.left-panel, .right-panel');
        if (panel) {
            const currentState = panel.dataset.state;
            panel.dataset.state = currentState === 'collapsed' ? 'expanded' : 'collapsed';
        }
    }

    async function createNewFile() {
        const name = prompt('Nom du fichier:', 'new_file.py');
        if (name) {
            await workspace.writeFile(name, '# New file\n');
        }
    }

    function saveFile() {
        const content = document.getElementById('codeEditor').value;
        if (WorkspaceState.currentFile) {
            workspace.writeFile(WorkspaceState.currentFile, content);
        } else {
            logToConsole('Aucun fichier ouvert', 'warning');
        }
    }

    function runCodeFromEditor() {
        const code = document.getElementById('codeEditor').value;
        workspace.runCode(code);
    }

    function addParamRow() {
        const tbody = document.getElementById('paramsBody');
        if (!tbody) return;

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><input type="text" placeholder="clé" data-param-key></td>
            <td><input type="text" placeholder="valeur" data-param-value></td>
            <td><button class="btn btn-small" data-action="remove_param">×</button></td>
        `;
        tbody.appendChild(row);

        row.querySelector('[data-action="remove_param"]').addEventListener('click', () => {
            row.remove();
        });
    }

    function renderParams() {
        const tbody = document.getElementById('paramsBody');
        if (!tbody) return;

        tbody.innerHTML = Array.from(WorkspaceState.params.entries()).map(([key, value]) => `
            <tr>
                <td>${key}</td>
                <td>${value}</td>
                <td><button class="btn btn-small" data-action="remove_param">×</button></td>
            </tr>
        `).join('');

        tbody.querySelectorAll('[data-action="remove_param"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const row = e.target.closest('tr');
                const key = row.querySelector('td').textContent;
                WorkspaceState.params.delete(key);
                renderParams();
            });
        });
    }

    function applyWorkflowConfig() {
        const name = document.getElementById('workflowName')?.value;
        const domain = document.getElementById('domain')?.value;
        const numTasks = parseInt(document.getElementById('numTasks')?.value) || 10;
        const seed = parseInt(document.getElementById('seed')?.value) || 42;

        logToConsole(`Workflow configuré: ${name} (${domain}, ${numTasks} tâches, seed=${seed})`, 'success');
        addToHistory('applyWorkflow', { name, domain, numTasks, seed });
    }

    function saveSettingsFromUI() {
        const settings = {
            apiKey: document.getElementById('settingApiKey')?.value,
            baseUrl: document.getElementById('settingBaseUrl')?.value,
            defaultModel: document.getElementById('settingModel')?.value
        };
        workspace.saveSettings(settings);
    }

    async function executeConsoleCommand(cmd) {
        logToConsole(`❯ ${cmd}`, 'system');

        // Parse command
        const parts = cmd.trim().split(/\s+/);
        const command = parts[0];
        const args = parts.slice(1);

        switch (command) {
            case 'help':
                logToConsole('Commandes: help, state, run <code>, stop, param <key> <value>, clear', 'info');
                break;
            case 'state':
                const state = workspace.getState();
                logToConsole(JSON.stringify(state.data, null, 2), 'info');
                break;
            case 'run':
                await workspace.runCode(args.join(' '));
                break;
            case 'stop':
                await workspace.stopRun();
                break;
            case 'param':
                if (args.length >= 2) {
                    await workspace.setValue(args[0], args.slice(1).join(' '));
                }
                break;
            case 'clear':
                document.getElementById('consoleOutput').innerHTML = '';
                break;
            default:
                logToConsole(`Commande inconnue: ${command}`, 'error');
        }
    }

    // ============================================================================
    // Initialization
    // ============================================================================

    async function init() {
        logToConsole('Life_mean Workspace initialisé', 'system');
        logToConsole('Interface programmable: workspace.readFile(), workspace.runCode(), etc.', 'info');

        initEventListeners();
        renderParams();

        // Load initial data
        try {
            const config = await ApiClient.getConfig();
            if (config.ok) {
                logToConsole('Config chargé', 'success');
            }
        } catch (e) {
            logToConsole(`Erreur chargement config: ${e.message}`, 'warning');
        }

        // Make workspace available globally for agent access
        window.workspace = workspace;
        window.WorkspaceState = WorkspaceState;
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
