const fs = require('fs');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'frontend', 'script.js');
let content = fs.readFileSync(scriptPath, 'utf8');

// 1. App Boot load: add await to generateNewInvestigationId inside DOMContentLoaded
content = content.replace(
    "document.addEventListener('DOMContentLoaded', () => {",
    "document.addEventListener('DOMContentLoaded', async () => {"
);
content = content.replace(
    "initNav();\n    initLeafletMap();",
    "await generateNewInvestigationId();\n    initNav();\n    initLeafletMap();"
);

// 2. generateNewInvestigationId -> POST /investigations
content = content.replace(
    /function generateNewInvestigationId\(\) \{[\s\S]*?DOM\.dossierId\.textContent = appState\.investigationId;\n\}/g,
    `async function generateNewInvestigationId() {
    try {
        const res = await fetch(\`\${CONFIG.API_BASE_URL}/investigations\`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ lat: appState.coordinates.lat, lon: appState.coordinates.lon })
        });
        const json = await res.json();
        if (json.success) {
            appState.investigationId = json.data.code;
            appState.dbId = json.data.id;
            DOM.navInvestigationId.textContent = appState.investigationId;
            DOM.heroIncidentId.textContent = appState.investigationId;
            DOM.dossierId.textContent = appState.investigationId;
        }
    } catch(e) { console.error('Failed to create investigation:', e); }
}`
);

// 3. updateInvestigationLocation -> PATCH /investigations/:id
content = content.replace(
    /function updateInvestigationLocation\(lat, lon\) \{[\s\S]*?recalculatePhysicsAndRender\(\);\n\}/g,
    `async function updateInvestigationLocation(lat, lon) {
    appState.coordinates.lat = lat;
    appState.coordinates.lon = lon;
    appState.detection.centroid.lat = lat + 0.005;
    appState.detection.centroid.lon = lon + 0.003;

    if (map) {
        map.panTo([lat, lon]);
    }

    if (appState.dbId) {
        try {
            await fetch(\`\${CONFIG.API_BASE_URL}/investigations/\${appState.dbId}\`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ coordinates: { lat, lon } })
            });
        } catch(e) { console.error(e); }
    }
    recalculatePhysicsAndRender();
}`
);

// 4. handleFile -> POST /upload
content = content.replace(
    /function handleFile\(e\) \{[\s\S]*?reader\.readAsDataURL\(file\);\n\}/g,
    `async function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
        alert('Please select a valid image format.');
        return;
    }

    const reader = new FileReader();
    reader.onload = (ev) => {
        DOM.imgPreview.src = ev.target.result;
        DOM.fileName.textContent = file.name;
        DOM.uploadZone.classList.add('hidden');
        DOM.previewArea.classList.remove('hidden');
        DOM.runBtn.disabled = false;
    };
    reader.readAsDataURL(file);

    if (appState.dbId) {
        try {
            await fetch(\`\${CONFIG.API_BASE_URL}/investigations/\${appState.dbId}/upload\`, {
                method: 'POST'
            });
        } catch(e) { console.error(e); }
    }
}`
);

// 5. initAnalysis -> POST /analyze
content = content.replace(
    /function initAnalysis\(\) \{\n\s+DOM\.runBtn\.addEventListener\('click', async \(\) => \{\n\s+if \(appState\.isProcessing\) return;[\s\S]*?DOM\.pipeline\.classList\.remove\('hidden'\);\n\n\s+try \{[\s\S]*?completeAnalysis\(\);\n\n\s+\} catch \(e\) \{[\s\S]*?\} finally \{[\s\S]*?\}\n\s+\}\);\n\}/g,
    `function initAnalysis() {
    DOM.runBtn.addEventListener('click', async () => {
        if (appState.isProcessing) return;
        if (DOM.previewArea.classList.contains('hidden')) {
            loadSampleImage();
        }
        
        appState.isProcessing = true;
        DOM.runBtn.disabled = true;
        DOM.pipeline.classList.remove('hidden');

        try {
            await updateStep('step-upload', 'Validating payload...');
            
            // Call API
            const res = await fetch(\`\${CONFIG.API_BASE_URL}/investigations/\${appState.dbId}/analyze\`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ sceneId: 'scene-id' })
            });
            const json = await res.json();
            
            if (json.success) {
                await updateStep('step-detect', 'Running AI segmentation...');
                appState.detection = json.data.detection;
                
                await updateStep('step-validate', 'Evaluating look-alike risk...');
                
                await updateStep('step-drift', 'Running Lagrangian back-drift...');
                appState.drift = json.data.drift;
                
                await updateStep('step-ais', 'Correlating AIS telemetry...');
                appState.vessels = json.data.vessels;
                
                await updateStep('step-evidence', 'Compiling evidence dossier...');
                appState.evidenceChain = json.data.evidenceChain;
                
                completeAnalysis();
            } else {
                throw new Error("API validation failed");
            }

        } catch (e) {
            console.error(e);
            alert('Analysis workflow interrupted. Resetting state.');
            resetUploadState();
        } finally {
            appState.isProcessing = false;
        }
    });
}`
);

// 6. delete manual recalculatePhysicsAndRender overrides that will destroy API response
content = content.replace(
    /function recalculatePhysicsAndRender\(\) \{[\s\S]*?renderMapLayers\(\);\n\s+updateUIElements\(\);\n\}/g,
    `function recalculatePhysicsAndRender() {
    renderMapLayers();
    updateUIElements();
}`
);

// 7. delete manual generateEvidenceChain overrides
content = content.replace(
    /function generateEvidenceChain\(\) \{[\s\S]*?\}\n\s+div>\n\s+`;\n\s+\}\);\n\}/g,
    `function generateEvidenceChain() {
    DOM.evidenceTimeline.innerHTML = '';
    appState.evidenceChain.forEach(item => {
        DOM.evidenceTimeline.innerHTML += \`
            <div class="timeline-item \${item.event_type}">
                <div class="timeline-dot"></div>
                <div class="timeline-box">
                    <div class="timeline-meta"><span>\${item.occurred_label}</span> <span>Source: \${item.source}</span></div>
                    <h4>\${item.title}</h4>
                    <p>\${item.description}</p>
                </div>
            </div>
        \`;
    });
}`
);

// 8. exportDossierReport -> POST /dossier/export
content = content.replace(
    /function exportDossierReport\(\) \{[\s\S]*?URL\.revokeObjectURL\(url\);\n\}/g,
    `async function exportDossierReport() {
    if (!appState.dbId) return;
    try {
        DOM.exportBtn.textContent = 'Generating...';
        DOM.exportBtn.disabled = true;
        
        const res = await fetch(\`\${CONFIG.API_BASE_URL}/investigations/\${appState.dbId}/dossier/export\`, { method: 'POST' });
        const json = await res.json();
        
        if (json.success && json.data.downloadUrl) {
            window.location.href = json.data.downloadUrl;
        } else {
            alert('Could not export dossier');
        }
    } catch(e) {
        console.error(e);
        alert('Server error generating dossier.');
    } finally {
        DOM.exportBtn.textContent = 'Export PDF Dossier';
        DOM.exportBtn.disabled = false;
    }
}`
);

// Also tie in the environment sliders patching
content = content.replace(
    /appState\.environment\.windSpeed = parseInt\(e\.target\.value\);\n\s+DOM\.valWindSpeed\.textContent = \`\$\{appState\.environment\.windSpeed\} kts\`;\n\s+recalculatePhysicsAndRender\(\);/g,
    `appState.environment.windSpeed = parseInt(e.target.value);
        DOM.valWindSpeed.textContent = \`\${appState.environment.windSpeed} kts\`;
        debouncedPatch({ environment: appState.environment });`
);

content = content.replace(
    /appState\.environment\.windDir = parseInt\(e\.target\.value\);\n\s+DOM\.valWindDir\.textContent = \`\$\{appState\.environment\.windDir\.toString\(\)\.padStart\(3,'0'\)\}\°\`;\n\s+recalculatePhysicsAndRender\(\);/g,
    `appState.environment.windDir = parseInt(e.target.value);
        DOM.valWindDir.textContent = \`\${appState.environment.windDir.toString().padStart(3,'0')}°\`;
        debouncedPatch({ environment: appState.environment });`
);

// We need to inject debouncedPatch globally
content += `\n
let patchTimeout;
function debouncedPatch(payload) {
    if (!appState.dbId) return;
    clearTimeout(patchTimeout);
    patchTimeout = setTimeout(async () => {
        try {
            await fetch(\`\${CONFIG.API_BASE_URL}/investigations/\${appState.dbId}\`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
        } catch(e) { console.error('Patch error', e); }
    }, 500);
}
`;


fs.writeFileSync(scriptPath, content, 'utf8');
console.log('Successfully patched script.js!');
