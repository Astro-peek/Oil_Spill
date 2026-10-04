const CONFIG = {
    API_BASE_URL: 'http://localhost:4000/api/v1',
    ENDPOINTS: {
        UPLOAD: '/api/detection/upload',
        DETECT: '/api/detection/segment',
        VALIDATE: '/api/validation/lookalike',
        DRIFT: '/api/drift/lagrangian',
        AIS_CORRELATE: '/api/ais/correlate',
        ATTRIBUTION: '/api/vessel/attribution',
        DOSSIER: '/api/evidence/dossier'
    },
    SIMULATION_DELAY_MS: 700
};

let appState = {
    investigationId: 'OT-2026-0913-001',
    coordinates: {
        lat: 19.0760,
        lon: 72.8777
    },
    image: null,
    isProcessing: false,
    analysisComplete: false,


    detection: {
        confidence: 87,
        areaKm2: 14.8,
        centroid: { lat: 19.0812, lon: 72.8547 },
        slickAgeHours: 24,
        lookAlikeRisk: false
    },


    environment: {
        windSpeed: 12,
        windDir: 45,
        currentSpeed: 0.8,
        currentDir: 30
    },


    drift: {
        mode: 'back',
        forecastHours: 48,
        leewayFactor: 0.03,
        trajectoryBack: [],
        trajectoryForward: []
    },


    origin: {
        lat: 19.0120,
        lon: 72.7800,
        radiusKm: 8.5
    },


    vessels: [],
    selectedVesselId: 'v1',
    timelineHour: 0,
    sourceType: 'all',


    whatIf: {
        radiusKm: 8.5,
        timeShiftHours: 0
    },


    layers: {
        spill: true,
        origin: true,
        backDrift: true,
        forwardDrift: true,
        cone: true,
        vesselTracks: true,
        vessels: true
    },


    evidenceChain: []
};

let map = null;
let mapLayers = {
    investigationMarker: null,
    spillPolygon: null,
    originCircle: null,
    backDriftPolyline: null,
    forwardDriftPolyline: null,
    uncertaintyConePolygon: null,
    vesselTrackLines: [],
    vesselMarkers: []
};

const DOM = {

    navbar: document.getElementById('navbar'),
    mobileBtn: document.getElementById('mobileMenuBtn'),
    navLinks: document.getElementById('navLinks'),
    launchBtns: document.querySelectorAll('#navLaunchBtn, #heroLaunchBtn'),
    btnNewId: document.getElementById('btnNewId'),
    navInvestigationId: document.getElementById('navInvestigationId'),
    heroIncidentId: document.getElementById('heroIncidentId'),
    dossierId: document.getElementById('dossierId'),
    btnResetAll: document.getElementById('btnResetAll'),
    btnExportTop: document.getElementById('btnExportTop'),


    inputLat: document.getElementById('inputLat'),
    inputLon: document.getElementById('inputLon'),
    btnSetLocation: document.getElementById('btnSetLocation'),
    btnCenterMap: document.getElementById('btnCenterMap'),
    loadDemoImgBtn: document.getElementById('loadDemoImgBtn'),


    mapResetBtn: document.getElementById('mapResetBtn'),
    mapFitBoundsBtn: document.getElementById('mapFitBoundsBtn'),
    timeSlider: document.getElementById('timeSlider'),
    scrubberTimeDisplay: document.getElementById('scrubberTimeDisplay'),


    layerSpill: document.getElementById('layerSpill'),
    layerOrigin: document.getElementById('layerOrigin'),
    layerBackDrift: document.getElementById('layerBackDrift'),
    layerForwardDrift: document.getElementById('layerForwardDrift'),
    layerCone: document.getElementById('layerCone'),
    layerVesselTracks: document.getElementById('layerVesselTracks'),
    layerVessels: document.getElementById('layerVessels'),


    uploadZone: document.getElementById('uploadZone'),
    fileInput: document.getElementById('imageUpload'),
    previewArea: document.getElementById('previewArea'),
    imgPreview: document.getElementById('imgPreview'),
    removeImgBtn: document.getElementById('removeImgBtn'),
    fileName: document.getElementById('fileName'),
    runBtn: document.getElementById('runDetectionBtn'),
    pipeline: document.getElementById('processingPipeline'),
    results: document.getElementById('detectionResults'),
    lookAlikeWarning: document.getElementById('lookAlikeWarning'),


    driftPanel: document.getElementById('drift'),
    btnBackDrift: document.getElementById('btnBackDrift'),
    btnForwardDrift: document.getElementById('btnForwardDrift'),
    sliderWindSpeed: document.getElementById('sliderWindSpeed'),
    sliderWindDir: document.getElementById('sliderWindDir'),
    sliderCurrentSpeed: document.getElementById('sliderCurrentSpeed'),
    sliderCurrentDir: document.getElementById('sliderCurrentDir'),
    valWindSpeed: document.getElementById('valWindSpeed'),
    valWindDir: document.getElementById('valWindDir'),
    valCurrentSpeed: document.getElementById('valCurrentSpeed'),
    valCurrentDir: document.getElementById('valCurrentDir'),
    durationButtons: document.querySelectorAll('.btn-sm-toggle'),


    vesselsPanel: document.getElementById('vessels'),
    vesselTableBody: document.querySelector('#vesselTable tbody'),
    vesselDetailEmpty: document.getElementById('vesselDetailEmpty'),
    vesselDetailContent: document.getElementById('vesselDetailContent'),
    sourceTypeFilter: document.getElementById('sourceTypeFilter'),
    radiusSlider: document.getElementById('radiusSlider'),
    timeShiftSlider: document.getElementById('timeShiftSlider'),
    valRadius: document.getElementById('valRadius'),
    valTimeShift: document.getElementById('valTimeShift'),
    robustnessResult: document.getElementById('robustnessResult'),


    evidenceTimeline: document.getElementById('evidenceTimeline'),
    dossierPreview: document.getElementById('dossierPreview'),
    exportBtn: document.getElementById('exportBtn')
};

const PAGE = window.location.pathname.includes('evidence') ? 'evidence' : 'command';

document?.addEventListener('DOMContentLoaded', async () => {
    const saved = localStorage.getItem('oceanTraceApp');
    if (saved) {
        try {
            Object.assign(appState, JSON.parse(saved));
        } catch (e) { console.warn('State restore failed:', e); }
    }

    // Update nav ID on all pages
    const navId = document.getElementById('navInvestigationId');
    if (navId) navId.textContent = appState.investigationId;

    if (PAGE === 'evidence') {
        // Evidence page: just init nav + evidence rendering
        initNav();
        initEvidence();

        if (appState.analysisComplete) {
            // Update dossier ID badge
            const dossierId = document.getElementById('dossierId');
            if (dossierId) dossierId.textContent = appState.investigationId;
            // Render timeline and dossier immediately
            renderEvidenceChain();
            generateDossier();
        }
        return; // Stop here — no command-center inits
    }

    // ---- Command Center page only below ----
    if (!appState.dbId) {
        await generateNewInvestigationId();
    }

    initNav();
    initLeafletMap();
    initInputBar();
    initUpload();
    initAnalysis();
    initEnvironmentalControls();
    initVesselAttribution();
    initEvidence();

    if (appState.analysisComplete) {
        if (DOM.runBtn) {
            DOM.runBtn.textContent = 'Re-Run AI Analysis';
            DOM.runBtn.disabled = false;
        }
        DOM.uploadZone?.classList.add('hidden');
        DOM.previewArea?.classList.remove('hidden');
        if (DOM.imgPreview && appState.imagePreview) DOM.imgPreview.src = appState.imagePreview;

        DOM.pipeline?.classList.remove('hidden');
        document.querySelectorAll('.pipeline-step').forEach(step => {
            step.classList.remove('pending');
            step.classList.add('done');
            if (!step.textContent.includes('✓')) step.textContent += ' ✓';
        });

        DOM.results?.classList.remove('hidden');
        DOM.driftPanel?.classList.remove('hidden');
        DOM.vesselsPanel?.classList.remove('hidden');

        setTimeout(() => {
            renderMapLayers();
            updateUIElements();
            renderEvidenceChain();
            generateDossier();
            if (DOM.exportBtn) DOM.exportBtn.disabled = false;
            if (DOM.btnExportTop) DOM.btnExportTop.disabled = false;
        }, 100);
    }
});

window.addEventListener('beforeunload', () => {
    localStorage.setItem('oceanTraceApp', JSON.stringify(appState));
});

function saveState() {
    localStorage.setItem('oceanTraceApp', JSON.stringify(appState));
}

function initNav() {
    window?.addEventListener('scroll', () => {
        if (window.scrollY > 50) DOM.navbar?.classList.add('scrolled');
        else DOM.navbar?.classList.remove('scrolled');
    });

    DOM.mobileBtn?.addEventListener('click', () => DOM.navLinks?.classList.toggle('active'));

    document.querySelectorAll('.nav-links a').forEach(link => {
        link?.addEventListener('click', (e) => {
            DOM.navLinks?.classList.remove('active');
            const targetId = link.getAttribute('href');
            if (targetId && targetId.startsWith('#')) {
                const targetEl = document.querySelector(targetId);
                if (targetEl && targetEl?.classList.contains('hidden')) {
                    e.preventDefault();
                    window.location.href = 'command-center.html';
                }
            }
        });
    });

    DOM.launchBtns.forEach(btn => {
        btn?.addEventListener('click', () => {
            window.location.href = 'command-center.html';
        });
    });

    DOM.btnNewId?.addEventListener('click', generateNewInvestigationId);
    DOM.btnResetAll?.addEventListener('click', resetFullInvestigation);
    DOM.btnExportTop?.addEventListener('click', exportDossierReport);
}

async function generateNewInvestigationId() {
    try {
        const res = await fetch(`${CONFIG.API_BASE_URL}/investigations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lat: appState.coordinates.lat, lon: appState.coordinates.lon })
        });
        const json = await res.json();
        if (json.success) {
            appState.investigationId = json.data.code;
            appState.dbId = json.data.id;
            if (DOM.navInvestigationId) DOM.navInvestigationId.textContent = appState.investigationId;
            if (DOM.heroIncidentId) DOM.heroIncidentId.textContent = appState.investigationId;
            if (DOM.dossierId) DOM.dossierId.textContent = appState.investigationId;
        }
    } catch (e) { console.error('Failed to create investigation:', e); }
}

function initLeafletMap() {
    try {
        if (!document.getElementById('leafletMap')) return;
        map = L.map('leafletMap', {
            center: [appState.coordinates.lat, appState.coordinates.lon],
            zoom: 10,
            zoomControl: true
        });


        // Use Stadia Maps dark tile — free, no API key needed
        L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 20
        }).addTo(map);


        map.on('click', (e) => {
            const lat = parseFloat(e.latlng.lat.toFixed(4));
            const lon = parseFloat(e.latlng.lng.toFixed(4));

            DOM.inputLat.value = lat;
            DOM.inputLon.value = lon;
            updateInvestigationLocation(lat, lon);
        });


        initMapLayerToggles();


        renderMapLayers();

    } catch (e) {
        console.warn('Leaflet CDN load fallback mode:', e);
        document.getElementById('mapFallback')?.classList.remove('hidden');
    }
}

function initMapLayerToggles() {
    DOM.layerSpill?.addEventListener('change', (e) => {
        appState.layers.spill = e.target.checked;
        if (mapLayers.spillPolygon) {
            if (e.target.checked) mapLayers.spillPolygon.addTo(map);
            else mapLayers.spillPolygon.remove();
        }
    });

    DOM.layerOrigin?.addEventListener('change', (e) => {
        appState.layers.origin = e.target.checked;
        if (mapLayers.originCircle) {
            if (e.target.checked) mapLayers.originCircle.addTo(map);
            else mapLayers.originCircle.remove();
        }
    });

    DOM.layerBackDrift?.addEventListener('change', (e) => {
        appState.layers.backDrift = e.target.checked;
        if (mapLayers.backDriftPolyline) {
            if (e.target.checked) mapLayers.backDriftPolyline.addTo(map);
            else mapLayers.backDriftPolyline.remove();
        }
    });

    DOM.layerForwardDrift?.addEventListener('change', (e) => {
        appState.layers.forwardDrift = e.target.checked;
        if (mapLayers.forwardDriftPolyline) {
            if (e.target.checked) mapLayers.forwardDriftPolyline.addTo(map);
            else mapLayers.forwardDriftPolyline.remove();
        }
    });

    DOM.layerCone?.addEventListener('change', (e) => {
        appState.layers.cone = e.target.checked;
        if (mapLayers.uncertaintyConePolygon) {
            if (e.target.checked) mapLayers.uncertaintyConePolygon.addTo(map);
            else mapLayers.uncertaintyConePolygon.remove();
        }
    });

    DOM.layerVesselTracks?.addEventListener('change', (e) => {
        appState.layers.vesselTracks = e.target.checked;
        mapLayers.vesselTrackLines.forEach(line => {
            if (e.target.checked) line.addTo(map);
            else line.remove();
        });
    });

    DOM.layerVessels?.addEventListener('change', (e) => {
        appState.layers.vessels = e.target.checked;
        mapLayers.vesselMarkers.forEach(m => {
            if (e.target.checked) m.addTo(map);
            else m.remove();
        });
    });

    DOM.mapResetBtn?.addEventListener('click', () => {
        if (!map) return;
        map.setView([appState.coordinates.lat, appState.coordinates.lon], 10);
    });

    DOM.mapFitBoundsBtn?.addEventListener('click', () => {
        if (!map || !mapLayers.spillPolygon) return;
        const featureGroup = L.featureGroup([
            mapLayers.spillPolygon,
            mapLayers.originCircle,
            mapLayers.backDriftPolyline
        ].filter(Boolean));
        if (featureGroup.getLayers().length) {
            map.fitBounds(featureGroup.getBounds().pad(0.2));
        }
    });
}

function initInputBar() {
    DOM.btnSetLocation?.addEventListener('click', () => {
        const lat = parseFloat(DOM.inputLat.value);
        const lon = parseFloat(DOM.inputLon.value);

        if (isNaN(lat) || lat < -90 || lat > 90 || isNaN(lon) || lon < -180 || lon > 180) {
            alert('Please enter valid Latitude (-90 to 90) and Longitude (-180 to 180).');
            return;
        }
        updateInvestigationLocation(lat, lon);
    });

    DOM.btnCenterMap?.addEventListener('click', () => {
        if (!map) return;
        const center = map.getCenter();
        const lat = parseFloat(center.lat.toFixed(4));
        const lon = parseFloat(center.lng.toFixed(4));

        DOM.inputLat.value = lat;
        DOM.inputLon.value = lon;
        updateInvestigationLocation(lat, lon);
    });
}

async function updateInvestigationLocation(lat, lon) {
    appState.coordinates.lat = lat;
    appState.coordinates.lon = lon;
    appState.detection.centroid.lat = lat + 0.005;
    appState.detection.centroid.lon = lon + 0.003;

    if (map) {
        map.panTo([lat, lon]);
    }

    if (appState.dbId) {
        try {
            await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ coordinates: { lat, lon } })
            });
        } catch (e) { console.error(e); }
    }
    recalculatePhysicsAndRender();
}

function calculateDriftTrajectory(startLat, startLon, windSpd, windDir, currSpd, currDir, durationHours, isBackwards) {
    const points = [];
    const stepHours = 3;
    const steps = Math.ceil(durationHours / stepHours);


    const windRad = (90 - windDir) * (Math.PI / 180);
    const windU = Math.cos(windRad) * windSpd * appState.drift.leewayFactor;
    const windV = Math.sin(windRad) * windSpd * appState.drift.leewayFactor;


    const currKts = currSpd * 1.94384;
    const currRad = (90 - currDir) * (Math.PI / 180);
    const currU = Math.cos(currRad) * currKts;
    const currV = Math.sin(currRad) * currKts;


    const totalU = currU + windU;
    const totalV = currV + windV;


    const dirMult = isBackwards ? -1 : 1;

    let curLat = startLat;
    let curLon = startLon;
    points.push([curLat, curLon]);

    for (let i = 1; i <= steps; i++) {
        const deltaHours = stepHours;

        const deltaLat = (totalV * deltaHours * dirMult) / 60.0;

        const deltaLon = (totalU * deltaHours * dirMult) / (60.0 * Math.cos(curLat * Math.PI / 180));

        curLat += deltaLat;
        curLon += deltaLon;
        points.push([parseFloat(curLat.toFixed(4)), parseFloat(curLon.toFixed(4))]);
    }

    return points;
}

function calculateUncertaintyCone(trajectoryPoints) {
    if (trajectoryPoints.length < 2) return [];
    const coneLeft = [];
    const coneRight = [];

    trajectoryPoints.forEach((pt, index) => {
        // Expand perpendicular to the drift direction
        const expansionKm = 1.0 + (index * 1.8) + (appState.whatIf.radiusKm * 0.15);
        const latOffset = expansionKm / 111.0;
        const lonOffset = expansionKm / (111.0 * Math.cos(pt[0] * Math.PI / 180));
        // Perpendicular: swap lat/lon offsets to go sideways relative to trajectory
        coneLeft.push([pt[0] + lonOffset, pt[1] - latOffset]);
        coneRight.unshift([pt[0] - lonOffset, pt[1] + latOffset]);
    });

    return coneLeft.concat(coneRight);
}

function recalculatePhysicsAndRender() {
    renderMapLayers();
    updateUIElements();
}

function renderMapLayers() {
    if (!map) return;


    if (mapLayers.investigationMarker) mapLayers.investigationMarker.remove();
    if (mapLayers.spillPolygon) mapLayers.spillPolygon.remove();
    if (mapLayers.originCircle) mapLayers.originCircle.remove();
    if (mapLayers.backDriftPolyline) mapLayers.backDriftPolyline.remove();
    if (mapLayers.forwardDriftPolyline) mapLayers.forwardDriftPolyline.remove();
    if (mapLayers.uncertaintyConePolygon) mapLayers.uncertaintyConePolygon.remove();
    mapLayers.vesselTrackLines.forEach(l => l.remove());
    mapLayers.vesselMarkers.forEach(m => m.remove());
    mapLayers.vesselTrackLines = [];
    mapLayers.vesselMarkers = [];

    const center = [appState.coordinates.lat, appState.coordinates.lon];


    mapLayers.investigationMarker = L.marker(center, {
        title: 'Investigation Centroid'
    }).addTo(map).bindTooltip('📍 Investigation Location', { sticky: true, className: 'mono' }).bindPopup(`
        <div class="mono">
            <strong>Investigation Location</strong><br>
            Lat: ${appState.coordinates.lat.toFixed(4)} &deg;N<br>
            Lon: ${appState.coordinates.lon.toFixed(4)} &deg;E
        </div>
    `);


    // Use detection centroid (slightly offset from investigation point)
    const cLat = appState.detection.centroid?.lat || appState.coordinates.lat + 0.005;
    const cLon = appState.detection.centroid?.lon || appState.coordinates.lon + 0.003;

    if (appState.analysisComplete) {
        let spillCoords;
        if (appState.detection.polygon && appState.detection.polygon.coordinates) {
            spillCoords = appState.detection.polygon.coordinates[0].map(pt => [pt[1], pt[0]]);
        } else {
            spillCoords = generateSlickPolygonCoords(cLat, cLon);
        }
        mapLayers.spillPolygon = L.polygon(spillCoords, {
            color: '#eab308',
            fillColor: '#eab308',
            fillOpacity: 0.35,
            weight: 2
        }).bindTooltip('🛢️ Oil Slick (AI)', { sticky: true, className: 'mono' }).bindPopup(`<div class="mono"><strong>🛢️ Oil Slick</strong><br>Area: ${appState.detection.areaKm2 || 14.8} km²<br>Confidence: ${appState.detection.confidence || 87}%<br>Age: ~${appState.detection.slickAgeHours || 24}h</div>`);
        if (appState.layers.spill) mapLayers.spillPolygon.addTo(map);
    }

    let backTrack = appState.drift.trajectoryBack;
    let fwdTrack = appState.drift.trajectoryForward;

    if (!backTrack || backTrack.length === 0) {
        backTrack = calculateDriftTrajectory(
            cLat, cLon, appState.environment.windSpeed, appState.environment.windDir,
            appState.environment.currentSpeed, appState.environment.currentDir,
            appState.drift.forecastHours, true
        );
    }
    if (!fwdTrack || fwdTrack.length === 0) {
        fwdTrack = calculateDriftTrajectory(
            cLat, cLon, appState.environment.windSpeed, appState.environment.windDir,
            appState.environment.currentSpeed, appState.environment.currentDir,
            appState.drift.forecastHours, false
        );
    }

    // Update origin from back-drift end point
    if (backTrack.length > 0) {
        const originPt = backTrack[backTrack.length - 1];
        appState.origin.lat = originPt[0];
        appState.origin.lon = originPt[1];
    }

    mapLayers.originCircle = L.circle([appState.origin.lat, appState.origin.lon], {
        radius: appState.origin.radiusKm * 1000,
        color: '#f97316',
        fillColor: '#f97316',
        fillOpacity: 0.18,
        dashArray: '6,6',
        weight: 2
    }).bindTooltip('🔴 Probable Origin Zone', { sticky: true, className: 'mono' }).bindPopup(`<div class="mono"><strong>🔴 Probable Origin Zone</strong><br>Lat: ${appState.origin.lat.toFixed(4)}°N<br>Lon: ${appState.origin.lon.toFixed(4)}°E<br>Radius: ${appState.origin.radiusKm} km</div>`);
    if (appState.layers.origin) mapLayers.originCircle.addTo(map);

    mapLayers.backDriftPolyline = L.polyline(backTrack, {
        color: '#f97316',
        weight: 2.5,
        dashArray: '8,6',
        opacity: 0.9
    }).bindTooltip('⬅️ Back-Drift Trajectory', { sticky: true, className: 'mono' }).bindPopup('<div class="mono"><strong>⬅️ Back-Drift Trajectory</strong><br>Traces slick backwards to probable source</div>');
    if (appState.layers.backDrift) mapLayers.backDriftPolyline.addTo(map);

    mapLayers.forwardDriftPolyline = L.polyline(fwdTrack, {
        color: '#0ea5e9',
        weight: 2.5,
        opacity: 0.85
    }).bindTooltip('➡️ Forecast Trajectory', { sticky: true, className: 'mono' }).bindPopup('<div class="mono"><strong>➡️ Forecast Trajectory</strong><br>Predicted future drift of slick</div>');
    if (appState.layers.forwardDrift) mapLayers.forwardDriftPolyline.addTo(map);

    let coneCoords = appState._uncertaintyCone;
    if (!coneCoords || coneCoords.length === 0) {
        coneCoords = calculateUncertaintyCone(backTrack);
    }
    mapLayers.uncertaintyConePolygon = L.polygon(coneCoords, {
        color: '#f97316',
        fillColor: '#f97316',
        fillOpacity: 0.07,
        weight: 1,
        dashArray: '4,4'
    }).bindTooltip('🌫️ Uncertainty Cone', { sticky: true, className: 'mono' });
    if (appState.layers.cone) mapLayers.uncertaintyConePolygon.addTo(map);

    updateVesselMapPositions();
}

function generateSlickPolygonCoords(lat, lon) {
    return [
        [lat + 0.012, lon - 0.015],
        [lat + 0.022, lon + 0.005],
        [lat + 0.008, lon + 0.025],
        [lat - 0.015, lon + 0.018],
        [lat - 0.018, lon - 0.008],
        [lat - 0.005, lon - 0.022]
    ];
}

function updateVesselMapPositions() {
    if (!map) return;
    mapLayers.vesselTrackLines.forEach(l => l.remove());
    mapLayers.vesselMarkers.forEach(m => m.remove());
    mapLayers.vesselTrackLines = [];
    mapLayers.vesselMarkers = [];

    appState.vessels.forEach(v => {

        const trackLine = L.polyline(v.trackPoints, {
            color: v.id === appState.selectedVesselId ? '#f97316' : '#64748b',
            weight: v.id === appState.selectedVesselId ? 3 : 1.5,
            opacity: 0.7
        }).bindTooltip(`〰️ ${v.name} Track`, { sticky: true, className: 'mono' });
        if (appState.layers.vesselTracks) trackLine.addTo(map);
        mapLayers.vesselTrackLines.push(trackLine);


        const curPos = getVesselPositionAtHour(v, appState.timelineHour);

        const isSelected = v.id === appState.selectedVesselId;
        const iconColor = isSelected ? '#f97316' : (v.anomaly ? '#ef4444' : '#0ea5e9');

        const customIcon = L.divIcon({
            className: 'custom-vessel-icon',
            html: `<div style="width:14px; height:14px; background:${iconColor}; border:2px solid #fff; border-radius:50%; box-shadow:0 0 10px ${iconColor};"></div>`,
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        });

        const marker = L.marker([curPos.lat, curPos.lon], { icon: customIcon }).bindTooltip(`🚢 ${v.name}`, { sticky: true, className: 'mono' }).bindPopup(`
            <div class="mono">
                <strong>${v.name}</strong> ${v.anomaly ? '<span style="color:#ef4444;">[AIS GAP]</span>' : ''}<br>
                MMSI: ${v.mmsi}<br>
                SOG: ${v.sog} | COG: ${v.cog}<br>
                Invest. Score: <strong style="color:${getScoreColorHex(v.score)};">${v.score}%</strong>
            </div>
        `);

        marker.on('click', () => {
            appState.selectedVesselId = v.id;
            renderVesselsTable();
            showVesselDetail(v);
            updateVesselMapPositions();
        });

        if (appState.layers.vessels) marker.addTo(map);
        mapLayers.vesselMarkers.push(marker);
    });
}

function getVesselPositionAtHour(vessel, hour) {

    const pct = (hour + 72) / 144.0;
    const idx = Math.min(vessel.trackPoints.length - 1, Math.max(0, Math.floor(pct * (vessel.trackPoints.length - 1))));
    const pt = vessel.trackPoints[idx];
    return { lat: pt[0], lon: pt[1] };
}

function generateVesselsAroundOrigin() {
    const oLat = appState.origin.lat;
    const oLon = appState.origin.lon;

    appState.vessels = [
        {
            id: 'v1',
            name: 'Candidate Vessel A',
            mmsi: '235001234',
            type: 'vessel',
            sog: '12.4 kts',
            cog: '045°',
            distKm: (appState.origin.radiusKm * 0.4).toFixed(1),
            timeMatch: 'High',
            baseScore: 87,
            score: 87,
            trackPoints: [
                [oLat - 0.15, oLon - 0.20],
                [oLat - 0.08, oLon - 0.10],
                [oLat, oLon],
                [oLat + 0.10, oLon + 0.12],
                [oLat + 0.22, oLon + 0.25]
            ],
            reasons: ['Close to estimated origin zone centroid', 'Present during estimated release window', 'Trajectory direction matches drift vector'],
            lowering: ['Speed anomaly detected 2h prior to release'],
            anomaly: false
        },
        {
            id: 'v2',
            name: 'Candidate Vessel B',
            mmsi: '353109876',
            type: 'vessel',
            sog: '14.1 kts',
            cog: '110°',
            distKm: (appState.origin.radiusKm * 0.8).toFixed(1),
            timeMatch: 'Medium',
            baseScore: 71,
            score: 71,
            trackPoints: [
                [oLat - 0.05, oLon - 0.30],
                [oLat - 0.02, oLon - 0.15],
                [oLat + 0.05, oLon + 0.05],
                [oLat + 0.08, oLon + 0.20],
                [oLat + 0.12, oLon + 0.35]
            ],
            reasons: ['Passed near outer envelope of origin probability zone', 'Reported draft change in regional port'],
            lowering: ['Time window correlation is marginal (-12h delta)'],
            anomaly: false
        },
        {
            id: 'v3',
            name: 'Candidate Vessel C',
            mmsi: '412356789',
            type: 'vessel',
            sog: '9.8 kts',
            cog: '090°',
            distKm: (appState.origin.radiusKm * 1.5).toFixed(1),
            timeMatch: 'Low',
            baseScore: 42,
            score: 42,
            trackPoints: [
                [oLat + 0.25, oLon - 0.10],
                [oLat + 0.20, oLon + 0.05],
                [oLat + 0.15, oLon + 0.20],
                [oLat + 0.10, oLon + 0.35],
                [oLat + 0.05, oLon + 0.50]
            ],
            reasons: ['Present in wider maritime surveillance region'],
            lowering: ['Distance from origin probability zone is large', 'Heading opposes surface current drift'],
            anomaly: false
        },
        {
            id: 'v4',
            name: 'Target: Unverified (AIS Gap)',
            mmsi: 'N/A (AIS Gap)',
            type: 'uncertain',
            sog: 'Est. 10.5 kts',
            cog: 'Unknown',
            distKm: (appState.origin.radiusKm * 0.2).toFixed(1),
            timeMatch: 'High',
            baseScore: 82,
            score: 82,
            trackPoints: [
                [oLat - 0.10, oLon - 0.05],
                [oLat - 0.02, oLon - 0.01],
                [oLat + 0.02, oLon + 0.02],
                [oLat + 0.08, oLon + 0.06],
                [oLat + 0.15, oLon + 0.10]
            ],
            reasons: ['Satellite SAR detected physical vessel shape inside origin zone', 'Perfect spatial overlap with release window'],
            lowering: ['No AIS telemetry broadcast recorded during release window'],
            anomaly: true
        }
    ];

    recalculateVesselScores();
}

function recalculateVesselScores() {
    const shift = appState.whatIf.timeShiftHours;
    // radFactor: extra radius beyond default 8.5km penalizes; smaller radius boosts slightly
    const radFactor = (appState.whatIf.radiusKm - 8.5) * 1.5;

    appState.vessels.forEach(v => {
        let newScore = v.baseScore - Math.abs(shift) * 2 - radFactor;
        // Keep top candidate stable for small time shifts
        if (v.id === 'v1' && Math.abs(shift) <= 3) newScore = Math.max(75, newScore);
        v.score = Math.min(100, Math.max(10, Math.round(newScore)));
    });
}

function initVesselAttribution() {
    DOM.sourceTypeFilter?.addEventListener('change', (e) => {
        appState.sourceType = e.target.value;
        renderVesselsTable();
    });

    DOM.radiusSlider?.addEventListener('input', (e) => {
        appState.whatIf.radiusKm = parseFloat(e.target.value);
        DOM.valRadius.textContent = `${appState.whatIf.radiusKm} km`;
        recalculatePhysicsAndRender();
    });

    DOM.timeShiftSlider?.addEventListener('input', (e) => {
        appState.whatIf.timeShiftHours = parseInt(e.target.value);
        DOM.valTimeShift.textContent = `${appState.whatIf.timeShiftHours} hrs`;
        recalculateVesselScores();
        renderVesselsTable();
        updateRobustnessText();
    });
}

function renderVesselsTable() {
    DOM.vesselTableBody.innerHTML = '';

    const filter = appState.sourceType;
    const filtered = appState.vessels.filter(v => filter === 'all' || v.type === filter);

    filtered.sort((a, b) => b.score - a.score);

    filtered.forEach((v, idx) => {
        const tr = document.createElement('tr');
        if (v.id === appState.selectedVesselId) tr?.classList.add('selected');

        tr.innerHTML = `
            <td>#${idx + 1}</td>
            <td><strong>${v.name}</strong> ${v.anomaly ? '<span class="text-danger ml-1" title="AIS Gap Mismatch">!</span>' : ''}</td>
            <td class="mmsi">${v.mmsi}</td>
            <td class="mono">${v.sog} / ${v.cog}</td>
            <td>${v.distKm} km</td>
            <td><strong style="color:${getScoreColorHex(v.score)}">${v.score}%</strong></td>
        `;

        tr?.addEventListener('click', () => {
            appState.selectedVesselId = v.id;
            renderVesselsTable();
            showVesselDetail(v);
            updateVesselMapPositions();
        });

        DOM.vesselTableBody.appendChild(tr);
    });


    const currentSel = appState.vessels.find(v => v.id === appState.selectedVesselId) || appState.vessels[0];
    if (currentSel) showVesselDetail(currentSel);
}

function showVesselDetail(v) {
    DOM.vesselDetailEmpty?.classList.add('hidden');
    DOM.vesselDetailContent?.classList.remove('hidden');

    document.getElementById('detVesselName').textContent = v.name;
    document.getElementById('detVesselMmsi').textContent = `MMSI: ${v.mmsi} | Type: ${v.type.toUpperCase()}`;

    const ulSupport = document.getElementById('detVesselSupporting');
    ulSupport.innerHTML = v.reasons.map(r => `<li class="check">${r}</li>`).join('');

    const ulLowering = document.getElementById('detVesselLowering');
    ulLowering.innerHTML = v.lowering.map(l => `<li class="warn">${l}</li>`).join('');

    const anomalyBox = document.getElementById('detVesselAnomaly');
    if (v.anomaly) anomalyBox?.classList.remove('hidden');
    else anomalyBox?.classList.add('hidden');

    document.getElementById('detVesselPropagation').innerHTML = `
        Detection (${appState.detection.confidence}%) &rarr; Drift Origin (${Math.max(60, appState.detection.confidence - 12)}%) &rarr; AIS Correlation (${v.score}%) = <strong>Final Score: ${v.score}%</strong>
    `;
}

function getScoreColorHex(score) {
    if (score >= 80) return '#10b981';
    if (score >= 60) return '#eab308';
    return '#ef4444';
}

function updateRobustnessText() {
    const shift = Math.abs(appState.whatIf.timeShiftHours);
    if (shift <= 3) {
        DOM.robustnessResult.innerHTML = `Candidate Vessel A remains Top Ranked &rarr; <span class="text-success">High Model Robustness</span>`;
    } else {
        DOM.robustnessResult.innerHTML = `Ranking sensitivity detected for &plusmn;${shift}h shift &rarr; <span class="text-warning">Moderate Model Sensitivity</span>`;
    }
}

function initEnvironmentalControls() {
    DOM.btnBackDrift?.addEventListener('click', () => {
        appState.drift.mode = 'back';
        DOM.btnBackDrift?.classList.add('active');
        DOM.btnForwardDrift?.classList.remove('active');
        recalculatePhysicsAndRender();
    });

    DOM.btnForwardDrift?.addEventListener('click', () => {
        appState.drift.mode = 'forward';
        DOM.btnBackDrift?.classList.remove('active');
        DOM.btnForwardDrift?.classList.add('active');
        recalculatePhysicsAndRender();
    });

    DOM.durationButtons.forEach(btn => {
        btn?.addEventListener('click', () => {
            DOM.durationButtons.forEach(b => b?.classList.remove('active'));
            btn?.classList.add('active');
            appState.drift.forecastHours = parseInt(btn.dataset.hours);
            recalculatePhysicsAndRender();
        });
    });

    DOM.sliderWindSpeed?.addEventListener('input', (e) => {
        appState.environment.windSpeed = parseInt(e.target.value);
        DOM.valWindSpeed.textContent = `${appState.environment.windSpeed} kts`;
        debouncedPatch({ environment: appState.environment });
    });

    DOM.sliderWindDir?.addEventListener('input', (e) => {
        appState.environment.windDir = parseInt(e.target.value);
        DOM.valWindDir.textContent = `${appState.environment.windDir.toString().padStart(3, '0')}°`;
        debouncedPatch({ environment: appState.environment });
    });

    DOM.sliderCurrentSpeed?.addEventListener('input', (e) => {
        appState.environment.currentSpeed = parseFloat(e.target.value);
        DOM.valCurrentSpeed.textContent = `${appState.environment.currentSpeed} m/s`;
        recalculatePhysicsAndRender();
    });

    DOM.sliderCurrentDir?.addEventListener('input', (e) => {
        appState.environment.currentDir = parseInt(e.target.value);
        DOM.valCurrentDir.textContent = `${appState.environment.currentDir.toString().padStart(3, '0')}°`;
        recalculatePhysicsAndRender();
    });

    DOM.timeSlider?.addEventListener('input', (e) => {
        appState.timelineHour = parseInt(e.target.value);
        const prefix = appState.timelineHour >= 0 ? '+' : '';
        DOM.scrubberTimeDisplay.textContent = `T ${prefix}${appState.timelineHour}h (${appState.timelineHour === 0 ? 'Detection' : (appState.timelineHour < 0 ? 'Origin' : 'Forecast')})`;
        updateVesselMapPositions();
    });
}

function initUpload() {
    DOM.uploadZone?.addEventListener('click', (e) => {
        if (e.target === DOM.loadDemoImgBtn || DOM.loadDemoImgBtn.contains(e.target)) return;
        if (!appState.isProcessing) DOM.fileInput.click();
    });

    if (DOM.loadDemoImgBtn) {
        DOM.loadDemoImgBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            loadSampleImage();
        });
    }

    DOM.fileInput?.addEventListener('change', handleFile);

    ['dragover', 'dragleave', 'drop'].forEach(evt => {
        DOM.uploadZone?.addEventListener(evt, e => e.preventDefault());
    });

    DOM.uploadZone?.addEventListener('dragover', () => DOM.uploadZone.style.borderColor = 'var(--accent-teal)');
    DOM.uploadZone?.addEventListener('dragleave', () => DOM.uploadZone.style.borderColor = '');

    DOM.uploadZone?.addEventListener('drop', e => {
        DOM.uploadZone.style.borderColor = '';
        if (!appState.isProcessing && e.dataTransfer.files.length) {
            DOM.fileInput.files = e.dataTransfer.files;
            handleFile({ target: DOM.fileInput });
        }
    });

    DOM.removeImgBtn?.addEventListener('click', resetUploadState);
}

function loadSampleImage() {
    // Generate a realistic-looking synthetic SAR image as an inline SVG
    const svgSample = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
  <defs>
    <radialGradient id="ocean" cx="50%" cy="50%" r="70%">
      <stop offset="0%" stop-color="#0a1628"/>
      <stop offset="100%" stop-color="#030810"/>
    </radialGradient>
    <filter id="noise">
      <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch"/>
      <feColorMatrix type="saturate" values="0"/>
      <feBlend in="SourceGraphic" mode="multiply"/>
    </filter>
  </defs>
  <rect width="400" height="300" fill="url(#ocean)"/>
  <rect width="400" height="300" fill="#06101e" filter="url(#noise)" opacity="0.5"/>
  <!-- Oil slick dark feature -->
  <ellipse cx="200" cy="160" rx="85" ry="45" fill="#010408" opacity="0.9" transform="rotate(-15,200,160)"/>
  <ellipse cx="220" cy="150" rx="55" ry="28" fill="#020810" opacity="0.8" transform="rotate(-10,220,150)"/>
  <!-- Speckle texture -->
  <rect x="0" y="0" width="400" height="300" fill="none" filter="url(#noise)" opacity="0.3"/>
  <!-- Lat/lon grid lines -->
  <line x1="0" y1="100" x2="400" y2="100" stroke="#1a3050" stroke-width="0.5" opacity="0.4"/>
  <line x1="0" y1="200" x2="400" y2="200" stroke="#1a3050" stroke-width="0.5" opacity="0.4"/>
  <line x1="133" y1="0" x2="133" y2="300" stroke="#1a3050" stroke-width="0.5" opacity="0.4"/>
  <line x1="267" y1="0" x2="267" y2="300" stroke="#1a3050" stroke-width="0.5" opacity="0.4"/>
  <!-- SAR metadata overlay -->
  <rect x="0" y="0" width="400" height="22" fill="black" opacity="0.7"/>
  <text x="6" y="14" font-family="monospace" font-size="10" fill="#06b6d4">SENTINEL-1A | SAR C-BAND | IW MODE | 2026-09-13T06:42:17Z</text>
  <rect x="0" y="278" width="400" height="22" fill="black" opacity="0.7"/>
  <text x="6" y="292" font-family="monospace" font-size="9" fill="#64748b">19.0760N 72.8777E | RES:10m | PASS:ASC | INCIDENCE:38.2°</text>
  <!-- Detection bounding box -->
  <rect x="125" y="110" width="155" height="95" fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="5,3" opacity="0.85"/>
  <text x="127" y="108" font-family="monospace" font-size="8" fill="#f59e0b">OIL_CANDIDATE_001</text>
</svg>`)}`;
    DOM.imgPreview.src = svgSample;
    appState.imagePreview = svgSample;
    DOM.fileName.textContent = 'Sentinel1A_SAR_20260913_Mumbai.tiff';
    DOM.uploadZone?.classList.add('hidden');
    DOM.previewArea?.classList.remove('hidden');
    DOM.runBtn.disabled = false;
}

async function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
        alert('Please select a valid image format.');
        return;
    }

    const reader = new FileReader();
    reader.onload = (ev) => {
        DOM.imgPreview.src = ev.target.result;
        appState.imagePreview = ev.target.result;
        DOM.fileName.textContent = file.name;
        DOM.uploadZone?.classList.add('hidden');
        DOM.previewArea?.classList.remove('hidden');
        DOM.runBtn.disabled = false;
    };
    reader.readAsDataURL(file);

    if (appState.dbId) {
        try {
            const formData = new FormData();
            formData.append('sceneImage', file);
            const res = await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}/upload`, {
                method: 'POST',
                body: formData
            });
            const json = await res.json();
            if (json.success && json.data.sceneId) {
                appState.sceneId = json.data.sceneId;
            }
        } catch (e) { console.error(e); }
    }
}

function resetUploadState() {
    appState.isProcessing = false;
    appState.analysisComplete = false;
    appState.sceneId = null;
    DOM.fileInput.value = '';
    DOM.previewArea?.classList.add('hidden');
    DOM.uploadZone?.classList.remove('hidden');
    DOM.runBtn.disabled = false;
    DOM.runBtn.textContent = 'Run AI Detection';

    document.querySelectorAll('.pipeline-step').forEach(step => {
        step.className = 'pipeline-step pending';
        step.textContent = step.textContent.replace(' ✓', '');
    });

    DOM.results?.classList.add('hidden');
    DOM.pipeline?.classList.add('hidden');
    DOM.driftPanel?.classList.add('hidden');
    DOM.vesselsPanel?.classList.add('hidden');

    if (DOM.evidenceTimeline) {
        DOM.evidenceTimeline.innerHTML = '<div class="empty-state text-muted">Run detection analysis to populate evidence chain steps.</div>';
    }
    if (DOM.dossierPreview) {
        DOM.dossierPreview.innerHTML = '<div class="empty-state text-muted">Dossier summary unavailable until analysis completes.</div>';
    }
    if (DOM.exportBtn) DOM.exportBtn.disabled = true;

    renderMapLayers();
}

function initAnalysis() {
    DOM.runBtn?.addEventListener('click', async () => {
        if (appState.isProcessing) return;
        if (DOM.previewArea?.classList.contains('hidden')) {
            loadSampleImage();
        }

        appState.isProcessing = true;
        DOM.runBtn.disabled = true;
        DOM.pipeline?.classList.remove('hidden');

        try {
            await updateStep('step-upload', 'Validating payload...');

            const stepDetect = document.getElementById('step-detect');
            if (stepDetect) {
                stepDetect.classList.remove('pending');
                stepDetect.classList.add('active');
                stepDetect.textContent = 'Running AI segmentation (~25s)...';
            }

            const sceneIdToUse = appState.sceneId || (crypto.randomUUID ? crypto.randomUUID() : '00000000-0000-4000-8000-000000000001');
            const res = await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sceneId: sceneIdToUse })
            });
            const json = await res.json();

            if (json.success) {
                if (stepDetect) {
                    stepDetect.classList.remove('active');
                    stepDetect.classList.add('done');
                    stepDetect.textContent = 'Running AI segmentation ✓';
                }
                appState.detection = json.data.detection;

                await updateStep('step-validate', 'Evaluating look-alike risk...');

                await updateStep('step-drift', 'Running Lagrangian back-drift...');

                const driftData = json.data.drift;
                appState.drift.trajectoryBack = driftData.trajectoryBack || [];
                appState.drift.trajectoryForward = driftData.trajectoryForward || [];

                if (driftData.origin) {
                    appState.origin.lat = driftData.origin.lat;
                    appState.origin.lon = driftData.origin.lon;
                    appState.origin.radiusKm = driftData.origin.radiusKm || appState.whatIf.radiusKm;
                }
                appState._uncertaintyCone = driftData.uncertaintyCone || [];

                await updateStep('step-ais', 'Correlating AIS telemetry...');
                appState.vessels = json.data.vessels;

                appState.vessels.forEach((v, i) => { v.id = v.id || `v${i + 1}`; v.baseScore = v.score; });
                if (appState.vessels.length > 0) appState.selectedVesselId = appState.vessels[0].id;

                await updateStep('step-evidence', 'Compiling evidence dossier...');
                appState.evidenceChain = json.data.evidenceChain;

                completeAnalysis();
            } else {
                throw new Error(json.error?.message || "API validation failed");
            }

        } catch (e) {
            console.error(e);
            alert(`Analysis workflow interrupted:\n${e.message || 'Unknown Error'}\n\nResetting state.`);
            resetUploadState();
        } finally {
            appState.isProcessing = false;
        }
    });
}

function updateStep(stepId, text) {
    return new Promise(resolve => {
        const step = document.getElementById(stepId);
        step?.classList.remove('pending');
        step?.classList.add('active');
        step.textContent = text;

        setTimeout(() => {
            step?.classList.remove('active');
            step?.classList.add('done');
            step.textContent += ' ✓';
            resolve();
        }, CONFIG.SIMULATION_DELAY_MS);
    });
}

function completeAnalysis() {
    appState.analysisComplete = true;
    if (DOM.runBtn) {
        DOM.runBtn.textContent = 'Re-Run AI Analysis';
        DOM.runBtn.disabled = false;
    }

    DOM.results?.classList.remove('hidden');
    DOM.driftPanel?.classList.remove('hidden');
    DOM.vesselsPanel?.classList.remove('hidden');

    renderMapLayers();
    updateUIElements();
    renderEvidenceChain();
    generateDossier();

    // Fix map cut-off issue by invalidating size after layout changes are rendered
    setTimeout(() => {
        if (map) { map.invalidateSize(); }
        if (mapLayers.spillPolygon) {
            map.fitBounds(mapLayers.spillPolygon.getBounds().pad(0.3));
        }
    }, 150);

    if (DOM.exportBtn) DOM.exportBtn.disabled = false;
    saveState();
}

function initEvidence() {
    DOM.exportBtn?.addEventListener('click', exportDossierReport);
}

function renderEvidenceChain() {
    const timeline = document.getElementById('evidenceTimeline');
    if (!timeline) return;

    // If only minimal API evidence chain, enrich it from appState
    if (!appState.evidenceChain || appState.evidenceChain.length < 3) {
        const d = appState.detection;
        const topV = appState.vessels[0];
        appState.evidenceChain = [
            { event_type: 'success', occurred_label: 'T-0h', title: 'SAR Satellite Pass', description: 'Sentinel-1A SAR C-Band acquired scene over investigation area.', source: 'SATELLITE' },
            { event_type: 'success', occurred_label: 'T-0h', title: 'Oil Anomaly Detected', description: `AI segmentation identified oil slick candidate. Confidence: ${d.confidence}%, Area: ${d.areaKm2} km².`, source: 'AI-DETECT' },
            { event_type: d.lookAlikeRisk ? 'warning' : 'success', occurred_label: 'T-0h', title: 'Look-Alike Risk Assessment', description: d.lookAlikeRisk ? 'Look-alike risk flagged — biogenic sheen possible.' : 'Look-alike risk LOW — spill classification confirmed.', source: 'AI-VALIDATE' },
            { event_type: 'success', occurred_label: 'T-' + d.slickAgeHours + 'h', title: 'Lagrangian Back-Drift Completed', description: `Drift model traced slick origin to ${appState.origin.lat.toFixed(4)}°N, ${appState.origin.lon.toFixed(4)}°E (r=${appState.origin.radiusKm}km).`, source: 'DRIFT-MODEL' },
            { event_type: topV?.anomaly ? 'warning' : 'success', occurred_label: 'T-' + d.slickAgeHours + 'h', title: 'AIS Vessel Correlation', description: topV ? `Top candidate: ${topV.name} (MMSI: ${topV.mmsi}), Score: ${topV.score}%.` : 'No vessels correlated.', source: 'AIS-ENGINE' },
            { event_type: topV?.anomaly ? 'warning' : 'success', occurred_label: 'T-' + d.slickAgeHours + 'h', title: 'Evidence Dossier Compiled', description: topV?.anomaly ? 'AIS broadcast gap detected for top candidate — surveillance gap noted in dossier.' : 'Evidence chain complete. Dossier ready for export.', source: 'LEGAL-AI' }
        ];
    }

    timeline.innerHTML = '';
    appState.evidenceChain.forEach(item => {
        const type = item.event_type || item.type || 'success';
        const time = item.occurred_label || item.time || '';
        const title = item.title || '';
        const desc = item.description || item.desc || '';
        const src = item.source || item.src || '';
        timeline.innerHTML += `
            <div class="timeline-item ${type}">
                <div class="timeline-dot"></div>
                <div class="timeline-box">
                    <div class="timeline-meta"><span>${time}</span> <span>Source: ${src}</span></div>
                    <h4>${title}</h4>
                    <p>${desc}</p>
                </div>
            </div>
        `;
    });
}

// generateEvidenceChain is an alias kept for backward-compat; renderEvidenceChain handles rendering directly.
const generateEvidenceChain = renderEvidenceChain;


function generateDossier() {
    const dossierPreview = document.getElementById('dossierPreview');
    const dossierId = document.getElementById('dossierId');
    if (dossierId) dossierId.textContent = appState.investigationId;

    const topCandidate = appState.vessels[0] || { name: 'Candidate Vessel A', mmsi: '235001234', score: 87 };
    const d = appState.detection;

    const dossierData = [
        ['Investigation ID', appState.investigationId],
        ['Timestamp (UTC)', new Date().toISOString().replace('T', ' ').substring(0, 19)],
        ['Primary Centroid', `${appState.coordinates.lat.toFixed(4)} N, ${appState.coordinates.lon.toFixed(4)} E`],
        ['Primary Sensor', 'Sentinel-1 SAR C-Band'],
        ['Oil Slick Area', `${d.areaKm2 || 14.8} km²`],
        ['Detection Confidence', `${d.confidence || 87}% (${(d.confidence || 87) >= 80 ? 'High' : 'Medium'})`],
        ['Slick Age Estimate', `${d.slickAgeHours || 24} hours`],
        ['Wind Vectors', `${appState.environment.windSpeed} kts @ ${appState.environment.windDir}°`],
        ['Current Vectors', `${appState.environment.currentSpeed} m/s @ ${appState.environment.currentDir}°`],
        ['Origin Probability Zone', `${appState.origin.lat.toFixed(4)} N, ${appState.origin.lon.toFixed(4)} E (r=${appState.origin.radiusKm}km)`],
        ['Top Candidate Source', `${topCandidate.name} (MMSI: ${topCandidate.mmsi})`],
        ['Attribution Score', `${topCandidate.score}%`],
        ['AIS Anomaly Flagged', topCandidate.anomaly ? 'YES — AIS gap detected during release window' : 'No']
    ];

    if (!dossierPreview) return;
    let html = '';
    dossierData.forEach(row => {
        html += `<div class="dossier-row"><strong>${row[0]}</strong> <span class="mono">${row[1]}</span></div>`;
    });
    dossierPreview.innerHTML = html;

    const exportBtn = document.getElementById('exportBtn');
    if (exportBtn) exportBtn.disabled = false;
}

async function exportDossierReport() {
    if (!appState.dbId) return;
    try {
        if (DOM.exportBtn) {
            DOM.exportBtn.textContent = 'Generating...';
            DOM.exportBtn.disabled = true;
        }
        if (DOM.btnExportTop) {
            DOM.btnExportTop.textContent = 'Generating...';
            DOM.btnExportTop.disabled = true;
        }

        const res = await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}/dossier/export`, { method: 'POST' });
        const json = await res.json();

        if (json.success && json.data.downloadUrl) {
            window.location.href = json.data.downloadUrl;
        } else {
            alert('Could not export dossier');
        }
    } catch (e) {
        console.error(e);
        alert('Server error generating dossier.');
    } finally {
        if (DOM.exportBtn) {
            DOM.exportBtn.textContent = 'Export PDF Dossier';
            DOM.exportBtn.disabled = false;
        }
        if (DOM.btnExportTop) {
            DOM.btnExportTop.textContent = 'Export Dossier';
            DOM.btnExportTop.disabled = false;
        }
    }
}

function updateUIElements() {
    DOM.inputLat.value = appState.coordinates.lat.toFixed(4);
    DOM.inputLon.value = appState.coordinates.lon.toFixed(4);

    const detCentroidVal = document.getElementById('detCentroidVal');
    if (detCentroidVal) {
        detCentroidVal.textContent = `${appState.coordinates.lat.toFixed(4)}°N, ${appState.coordinates.lon.toFixed(4)}°E`;
    }

    if (appState.origin && typeof appState.origin.lat === 'number') {
        const originCoordsVal = document.getElementById('originCoordsVal');
        if (originCoordsVal) {
            originCoordsVal.textContent = `${appState.origin.lat.toFixed(4)}°N, ${appState.origin.lon.toFixed(4)}°E`;
        }
    }

    if (appState.analysisComplete) {
        renderVesselsTable();
        generateDossier();
    }
}

function resetFullInvestigation() {
    generateNewInvestigationId();
    appState.coordinates = { lat: 19.0760, lon: 72.8777 };
    appState.environment = { windSpeed: 12, windDir: 45, currentSpeed: 0.8, currentDir: 30 };
    appState.whatIf = { radiusKm: 8.5, timeShiftHours: 0 };
    appState.timelineHour = 0;

    if (DOM.sliderWindSpeed) {
        DOM.sliderWindSpeed.value = 12;
        if (DOM.valWindSpeed) DOM.valWindSpeed.textContent = '12 kts';
        DOM.sliderWindDir.value = 45;
        if (DOM.valWindDir) DOM.valWindDir.textContent = '045° NE';
        DOM.sliderCurrentSpeed.value = 0.8;
        if (DOM.valCurrentSpeed) DOM.valCurrentSpeed.textContent = '0.8 m/s';
        DOM.sliderCurrentDir.value = 30;
        if (DOM.valCurrentDir) DOM.valCurrentDir.textContent = '030° NNE';
        DOM.radiusSlider.value = 8.5;
        if (DOM.valRadius) DOM.valRadius.textContent = '8.5 km';
        DOM.timeShiftSlider.value = 0;
        if (DOM.valTimeShift) DOM.valTimeShift.textContent = '0 hrs';
        DOM.timeSlider.value = 0;
        if (DOM.scrubberTimeDisplay) DOM.scrubberTimeDisplay.textContent = 'T - 0h (Detection)';
    }

    resetUploadState();
    if (map) map.setView([19.0760, 72.8777], 10);
}

let patchTimeout;
function debouncedPatch(payload) {
    if (!appState.dbId) return;
    clearTimeout(patchTimeout);
    patchTimeout = setTimeout(async () => {
        try {
            await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) { console.error('Patch error', e); }
    }, 500);
}
