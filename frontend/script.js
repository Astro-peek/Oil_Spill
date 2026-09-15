/**
 * OCEANTRACE - DYNAMIC MARINE INTELLIGENCE ENGINE
 * Government-Grade Marine Oil Spill Detection & Vessel Attribution Platform
 * Team OceanSentinel (SIH 2026 - Problem Statement 26143)
 */

// ==========================================
// 1. CONFIGURATION & BACKEND API READY STUBS
// ==========================================
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

// ==========================================
// 2. CENTRALIZED APPLICATION STATE
// ==========================================
let appState = {
    investigationId: 'OT-2026-0913-001',
    coordinates: {
        lat: 19.0760,
        lon: 72.8777
    },
    image: null,
    isProcessing: false,
    analysisComplete: false,
    
    // Detection Model Outputs
    detection: {
        confidence: 87,
        areaKm2: 14.8,
        centroid: { lat: 19.0812, lon: 72.8547 },
        slickAgeHours: 24,
        lookAlikeRisk: false
    },
    
    // Environmental Vectors
    environment: {
        windSpeed: 12,      // kts
        windDir: 45,        // degrees
        currentSpeed: 0.8,  // m/s
        currentDir: 30      // degrees
    },
    
    // Drift Physics Parameters
    drift: {
        mode: 'back',       // 'back' or 'forward'
        forecastHours: 48,
        leewayFactor: 0.03, // 3% wind leeway
        trajectoryBack: [],
        trajectoryForward: []
    },
    
    // Origin Zone
    origin: {
        lat: 19.0120,
        lon: 72.7800,
        radiusKm: 8.5
    },
    
    // Telemetry & Candidates
    vessels: [],
    selectedVesselId: 'v1',
    timelineHour: 0, // -72 to +72
    sourceType: 'all',
    
    // What-If Parameters
    whatIf: {
        radiusKm: 8.5,
        timeShiftHours: 0
    },
    
    // Layer Visibilities
    layers: {
        spill: true,
        origin: true,
        backDrift: true,
        forwardDrift: true,
        cone: true,
        vesselTracks: true,
        vessels: true
    },
    
    // Evidence Log
    evidenceChain: []
};

// ==========================================
// 3. LEAFLET MAP INSTANCE & LAYER GROUPS
// ==========================================
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

// ==========================================
// 4. DOM REFERENCES
// ==========================================
const DOM = {
    // Nav & Controls
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

    // Input Bar
    inputLat: document.getElementById('inputLat'),
    inputLon: document.getElementById('inputLon'),
    btnSetLocation: document.getElementById('btnSetLocation'),
    btnCenterMap: document.getElementById('btnCenterMap'),
    loadDemoImgBtn: document.getElementById('loadDemoImgBtn'),

    // Map Controls & Scrubber
    mapResetBtn: document.getElementById('mapResetBtn'),
    mapFitBoundsBtn: document.getElementById('mapFitBoundsBtn'),
    timeSlider: document.getElementById('timeSlider'),
    scrubberTimeDisplay: document.getElementById('scrubberTimeDisplay'),

    // Checkboxes
    layerSpill: document.getElementById('layerSpill'),
    layerOrigin: document.getElementById('layerOrigin'),
    layerBackDrift: document.getElementById('layerBackDrift'),
    layerForwardDrift: document.getElementById('layerForwardDrift'),
    layerCone: document.getElementById('layerCone'),
    layerVesselTracks: document.getElementById('layerVesselTracks'),
    layerVessels: document.getElementById('layerVessels'),

    // Upload & Detection
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

    // Environmental Sliders & Drift
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

    // Vessel & Attribution
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

    // Evidence & Dossier
    evidenceTimeline: document.getElementById('evidenceTimeline'),
    dossierPreview: document.getElementById('dossierPreview'),
    exportBtn: document.getElementById('exportBtn')
};

// ==========================================
// 5. INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
    await generateNewInvestigationId();
    initNav();
    initLeafletMap();
    initInputBar();
    initUpload();
    initAnalysis();
    initEnvironmentalControls();
    initVesselAttribution();
    initEvidence();
});

// ==========================================
// 6. NAVIGATION & TOP LEVEL CONTROLS
// ==========================================
function initNav() {
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) DOM.navbar.classList.add('scrolled');
        else DOM.navbar.classList.remove('scrolled');
    });

    DOM.mobileBtn.addEventListener('click', () => DOM.navLinks.classList.toggle('active'));
    
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', (e) => {
            DOM.navLinks.classList.remove('active');
            const targetId = link.getAttribute('href');
            if (targetId && targetId.startsWith('#')) {
                const targetEl = document.querySelector(targetId);
                if (targetEl && targetEl.classList.contains('hidden')) {
                    e.preventDefault();
                    document.getElementById('command-center').scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    });

    DOM.launchBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('command-center').scrollIntoView({ behavior: 'smooth' });
        });
    });

    DOM.btnNewId.addEventListener('click', generateNewInvestigationId);
    DOM.btnResetAll.addEventListener('click', resetFullInvestigation);
    DOM.btnExportTop.addEventListener('click', () => DOM.exportBtn.click());
}

async function generateNewInvestigationId() {
    try {
        const res = await fetch(`${CONFIG.API_BASE_URL}/investigations`, {
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
}

// ==========================================
// 7. LEAFLET MAP SYSTEM
// ==========================================
function initLeafletMap() {
    try {
        map = L.map('leafletMap', {
            center: [appState.coordinates.lat, appState.coordinates.lon],
            zoom: 10,
            zoomControl: true
        });

        // Dark nautical CartoDB Tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(map);

        // Map Click Listener to Set Coordinates
        map.on('click', (e) => {
            const lat = parseFloat(e.latlng.lat.toFixed(4));
            const lon = parseFloat(e.latlng.lng.toFixed(4));
            
            DOM.inputLat.value = lat;
            DOM.inputLon.value = lon;
            updateInvestigationLocation(lat, lon);
        });

        // Layer Controls
        initMapLayerToggles();

        // Initial Map Setup
        renderMapLayers();

    } catch (e) {
        console.warn('Leaflet CDN load fallback mode:', e);
        document.getElementById('mapFallback').classList.remove('hidden');
    }
}

function initMapLayerToggles() {
    DOM.layerSpill.addEventListener('change', (e) => {
        appState.layers.spill = e.target.checked;
        if (mapLayers.spillPolygon) {
            if (e.target.checked) mapLayers.spillPolygon.addTo(map);
            else mapLayers.spillPolygon.remove();
        }
    });

    DOM.layerOrigin.addEventListener('change', (e) => {
        appState.layers.origin = e.target.checked;
        if (mapLayers.originCircle) {
            if (e.target.checked) mapLayers.originCircle.addTo(map);
            else mapLayers.originCircle.remove();
        }
    });

    DOM.layerBackDrift.addEventListener('change', (e) => {
        appState.layers.backDrift = e.target.checked;
        if (mapLayers.backDriftPolyline) {
            if (e.target.checked) mapLayers.backDriftPolyline.addTo(map);
            else mapLayers.backDriftPolyline.remove();
        }
    });

    DOM.layerForwardDrift.addEventListener('change', (e) => {
        appState.layers.forwardDrift = e.target.checked;
        if (mapLayers.forwardDriftPolyline) {
            if (e.target.checked) mapLayers.forwardDriftPolyline.addTo(map);
            else mapLayers.forwardDriftPolyline.remove();
        }
    });

    DOM.layerCone.addEventListener('change', (e) => {
        appState.layers.cone = e.target.checked;
        if (mapLayers.uncertaintyConePolygon) {
            if (e.target.checked) mapLayers.uncertaintyConePolygon.addTo(map);
            else mapLayers.uncertaintyConePolygon.remove();
        }
    });

    DOM.layerVesselTracks.addEventListener('change', (e) => {
        appState.layers.vesselTracks = e.target.checked;
        mapLayers.vesselTrackLines.forEach(line => {
            if (e.target.checked) line.addTo(map);
            else line.remove();
        });
    });

    DOM.layerVessels.addEventListener('change', (e) => {
        appState.layers.vessels = e.target.checked;
        mapLayers.vesselMarkers.forEach(m => {
            if (e.target.checked) m.addTo(map);
            else m.remove();
        });
    });

    DOM.mapResetBtn.addEventListener('click', () => {
        if (!map) return;
        map.setView([appState.coordinates.lat, appState.coordinates.lon], 10);
    });

    DOM.mapFitBoundsBtn.addEventListener('click', () => {
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

// ==========================================
// 8. INPUT BAR & LOCATION LOGIC
// ==========================================
function initInputBar() {
    DOM.btnSetLocation.addEventListener('click', () => {
        const lat = parseFloat(DOM.inputLat.value);
        const lon = parseFloat(DOM.inputLon.value);
        
        if (isNaN(lat) || lat < -90 || lat > 90 || isNaN(lon) || lon < -180 || lon > 180) {
            alert('Please enter valid Latitude (-90 to 90) and Longitude (-180 to 180).');
            return;
        }
        updateInvestigationLocation(lat, lon);
    });

    DOM.btnCenterMap.addEventListener('click', () => {
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
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ coordinates: { lat, lon } })
            });
        } catch(e) { console.error(e); }
    }
    recalculatePhysicsAndRender();
}

// ==========================================
// 9. DRIFT PHYSICS & VECTOR ENGINE
// ==========================================
function calculateDriftTrajectory(startLat, startLon, windSpd, windDir, currSpd, currDir, durationHours, isBackwards) {
    const points = [];
    const stepHours = 3;
    const steps = Math.ceil(durationHours / stepHours);
    
    // Wind vector components (converting direction to math angle rad)
    const windRad = (90 - windDir) * (Math.PI / 180);
    const windU = Math.cos(windRad) * windSpd * appState.drift.leewayFactor; // 3% leeway
    const windV = Math.sin(windRad) * windSpd * appState.drift.leewayFactor;
    
    // Current vector components (converting m/s to kts: 1 m/s = 1.94384 kts)
    const currKts = currSpd * 1.94384;
    const currRad = (90 - currDir) * (Math.PI / 180);
    const currU = Math.cos(currRad) * currKts;
    const currV = Math.sin(currRad) * currKts;
    
    // Total velocity vector (kts)
    const totalU = currU + windU;
    const totalV = currV + windV;
    
    // Direction multiplier
    const dirMult = isBackwards ? -1 : 1;
    
    let curLat = startLat;
    let curLon = startLon;
    points.push([curLat, curLon]);
    
    for (let i = 1; i <= steps; i++) {
        const deltaHours = stepHours;
        // 1 degree latitude ~ 60 nautical miles
        const deltaLat = (totalV * deltaHours * dirMult) / 60.0;
        // 1 degree longitude ~ 60 * cos(lat) nautical miles
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
        // Expand radius as time increases
        const expansionKm = 1.5 + (index * 2.5) + (appState.whatIf.radiusKm * 0.3);
        const latOffset = (expansionKm / 111.0);
        const lonOffset = (expansionKm / (111.0 * Math.cos(pt[0] * Math.PI / 180)));
        
        coneLeft.push([pt[0] + latOffset, pt[1] - lonOffset]);
        coneRight.unshift([pt[0] - latOffset, pt[1] + lonOffset]);
    });
    
    return coneLeft.concat(coneRight);
}

function recalculatePhysicsAndRender() {
    renderMapLayers();
    updateUIElements();
}

// ==========================================
// 10. MAP RENDERING FUNCTIONS
// ==========================================
function renderMapLayers() {
    if (!map) return;

    // Clear existing layers
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

    // 1. Investigation Center Marker
    mapLayers.investigationMarker = L.marker(center, {
        title: 'Investigation Centroid'
    }).addTo(map).bindPopup(`
        <div class="mono">
            <strong>Investigation Location</strong><br>
            Lat: ${appState.coordinates.lat.toFixed(4)} &deg;N<br>
            Lon: ${appState.coordinates.lon.toFixed(4)} &deg;E
        </div>
    `);

    // 2. Oil Slick Polygon Layer
    if (appState.analysisComplete) {
        const spillCoords = generateSlickPolygonCoords(appState.coordinates.lat, appState.coordinates.lon);
        mapLayers.spillPolygon = L.polygon(spillCoords, {
            color: '#eab308',
            fillColor: '#eab308',
            fillOpacity: 0.35,
            weight: 2
        });
        if (appState.layers.spill) mapLayers.spillPolygon.addTo(map);
    }

    // 3. Origin Zone Circle Layer
    mapLayers.originCircle = L.circle([appState.origin.lat, appState.origin.lon], {
        radius: appState.origin.radiusKm * 1000,
        color: '#f97316',
        fillColor: '#f97316',
        fillOpacity: 0.15,
        dashArray: '6,6',
        weight: 2
    });
    if (appState.layers.origin) mapLayers.originCircle.addTo(map);

    // 4. Back Drift Trajectory
    mapLayers.backDriftPolyline = L.polyline(appState.drift.trajectoryBack, {
        color: '#f97316',
        weight: 3,
        dashArray: '8,8'
    });
    if (appState.layers.backDrift) mapLayers.backDriftPolyline.addTo(map);

    // 5. Forward Forecast Trajectory
    mapLayers.forwardDriftPolyline = L.polyline(appState.drift.trajectoryForward, {
        color: '#0ea5e9',
        weight: 3
    });
    if (appState.layers.forwardDrift) mapLayers.forwardDriftPolyline.addTo(map);

    // 6. Uncertainty Cone
    const coneCoords = calculateUncertaintyCone(
        appState.drift.mode === 'back' ? appState.drift.trajectoryBack : appState.drift.trajectoryForward
    );
    mapLayers.uncertaintyConePolygon = L.polygon(coneCoords, {
        color: '#0ea5e9',
        fillColor: '#0ea5e9',
        fillOpacity: 0.08,
        stroke: false
    });
    if (appState.layers.cone) mapLayers.uncertaintyConePolygon.addTo(map);

    // 7. Vessels & Tracks
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
        // Render Track Polyline
        const trackLine = L.polyline(v.trackPoints, {
            color: v.id === appState.selectedVesselId ? '#f97316' : '#64748b',
            weight: v.id === appState.selectedVesselId ? 3 : 1.5,
            opacity: 0.7
        });
        if (appState.layers.vesselTracks) trackLine.addTo(map);
        mapLayers.vesselTrackLines.push(trackLine);

        // Interpolate position based on timeline slider (-72 to +72)
        const curPos = getVesselPositionAtHour(v, appState.timelineHour);
        
        const isSelected = v.id === appState.selectedVesselId;
        const iconColor = isSelected ? '#f97316' : (v.anomaly ? '#ef4444' : '#0ea5e9');
        
        const customIcon = L.divIcon({
            className: 'custom-vessel-icon',
            html: `<div style="width:14px; height:14px; background:${iconColor}; border:2px solid #fff; border-radius:50%; box-shadow:0 0 10px ${iconColor};"></div>`,
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        });

        const marker = L.marker([curPos.lat, curPos.lon], { icon: customIcon }).bindPopup(`
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
    // Kinematic position interpolation along vessel's track
    const pct = (hour + 72) / 144.0; // 0 to 1
    const idx = Math.min(vessel.trackPoints.length - 1, Math.max(0, Math.floor(pct * (vessel.trackPoints.length - 1))));
    const pt = vessel.trackPoints[idx];
    return { lat: pt[0], lon: pt[1] };
}

// ==========================================
// 11. AIS VESSEL TELEMETRY & ATTRIBUTION
// ==========================================
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
            name: 'Target Target-Unverified',
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
            anomaly: true // AIS Mismatch
        }
    ];

    recalculateVesselScores();
}

function recalculateVesselScores() {
    const shift = appState.whatIf.timeShiftHours;
    const radFactor = (appState.whatIf.radiusKm - 8.5) * 1.5;

    appState.vessels.forEach(v => {
        let newScore = v.baseScore - Math.abs(shift) * 2 - radFactor;
        if (v.id === 'v1' && Math.abs(shift) <= 3) newScore = Math.max(75, newScore);
        v.score = Math.min(100, Math.max(10, Math.round(newScore)));
    });
}

function initVesselAttribution() {
    DOM.sourceTypeFilter.addEventListener('change', (e) => {
        appState.sourceType = e.target.value;
        renderVesselsTable();
    });

    DOM.radiusSlider.addEventListener('input', (e) => {
        appState.whatIf.radiusKm = parseFloat(e.target.value);
        DOM.valRadius.textContent = `${appState.whatIf.radiusKm} km`;
        recalculatePhysicsAndRender();
    });

    DOM.timeShiftSlider.addEventListener('input', (e) => {
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
    
    filtered.sort((a,b) => b.score - a.score);

    filtered.forEach((v, idx) => {
        const tr = document.createElement('tr');
        if (v.id === appState.selectedVesselId) tr.classList.add('selected');
        
        tr.innerHTML = `
            <td>#${idx + 1}</td>
            <td><strong>${v.name}</strong> ${v.anomaly ? '<span class="text-danger ml-1" title="AIS Gap Mismatch">!</span>' : ''}</td>
            <td class="mmsi">${v.mmsi}</td>
            <td class="mono">${v.sog} / ${v.cog}</td>
            <td>${v.distKm} km</td>
            <td><strong style="color:${getScoreColorHex(v.score)}">${v.score}%</strong></td>
        `;

        tr.addEventListener('click', () => {
            appState.selectedVesselId = v.id;
            renderVesselsTable();
            showVesselDetail(v);
            updateVesselMapPositions();
        });

        DOM.vesselTableBody.appendChild(tr);
    });

    // Auto update detail view for top selected vessel
    const currentSel = appState.vessels.find(v => v.id === appState.selectedVesselId) || appState.vessels[0];
    if (currentSel) showVesselDetail(currentSel);
}

function showVesselDetail(v) {
    DOM.vesselDetailEmpty.classList.add('hidden');
    DOM.vesselDetailContent.classList.remove('hidden');
    
    document.getElementById('detVesselName').textContent = v.name;
    document.getElementById('detVesselMmsi').textContent = `MMSI: ${v.mmsi} | Type: ${v.type.toUpperCase()}`;
    
    const ulSupport = document.getElementById('detVesselSupporting');
    ulSupport.innerHTML = v.reasons.map(r => `<li class="check">${r}</li>`).join('');
    
    const ulLowering = document.getElementById('detVesselLowering');
    ulLowering.innerHTML = v.lowering.map(l => `<li class="warn">${l}</li>`).join('');
    
    const anomalyBox = document.getElementById('detVesselAnomaly');
    if (v.anomaly) anomalyBox.classList.remove('hidden');
    else anomalyBox.classList.add('hidden');
    
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

// ==========================================
// 12. ENVIRONMENTAL CONTROLS & DRIFT SLIDERS
// ==========================================
function initEnvironmentalControls() {
    DOM.btnBackDrift.addEventListener('click', () => {
        appState.drift.mode = 'back';
        DOM.btnBackDrift.classList.add('active');
        DOM.btnForwardDrift.classList.remove('active');
        recalculatePhysicsAndRender();
    });

    DOM.btnForwardDrift.addEventListener('click', () => {
        appState.drift.mode = 'forward';
        DOM.btnBackDrift.classList.remove('active');
        DOM.btnForwardDrift.classList.add('active');
        recalculatePhysicsAndRender();
    });

    DOM.durationButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            DOM.durationButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            appState.drift.forecastHours = parseInt(btn.dataset.hours);
            recalculatePhysicsAndRender();
        });
    });

    DOM.sliderWindSpeed.addEventListener('input', (e) => {
        appState.environment.windSpeed = parseInt(e.target.value);
        DOM.valWindSpeed.textContent = `${appState.environment.windSpeed} kts`;
        debouncedPatch({ environment: appState.environment });
    });

    DOM.sliderWindDir.addEventListener('input', (e) => {
        appState.environment.windDir = parseInt(e.target.value);
        DOM.valWindDir.textContent = `${appState.environment.windDir.toString().padStart(3,'0')}°`;
        debouncedPatch({ environment: appState.environment });
    });

    DOM.sliderCurrentSpeed.addEventListener('input', (e) => {
        appState.environment.currentSpeed = parseFloat(e.target.value);
        DOM.valCurrentSpeed.textContent = `${appState.environment.currentSpeed} m/s`;
        recalculatePhysicsAndRender();
    });

    DOM.sliderCurrentDir.addEventListener('input', (e) => {
        appState.environment.currentDir = parseInt(e.target.value);
        DOM.valCurrentDir.textContent = `${appState.environment.currentDir.toString().padStart(3,'0')}°`;
        recalculatePhysicsAndRender();
    });

    DOM.timeSlider.addEventListener('input', (e) => {
        appState.timelineHour = parseInt(e.target.value);
        const prefix = appState.timelineHour >= 0 ? '+' : '';
        DOM.scrubberTimeDisplay.textContent = `T ${prefix}${appState.timelineHour}h (${appState.timelineHour === 0 ? 'Detection' : (appState.timelineHour < 0 ? 'Origin' : 'Forecast')})`;
        updateVesselMapPositions();
    });
}

// ==========================================
// 13. UPLOAD HANDLING & DEMO PRESETS
// ==========================================
function initUpload() {
    DOM.uploadZone.addEventListener('click', (e) => {
        if (e.target === DOM.loadDemoImgBtn || DOM.loadDemoImgBtn.contains(e.target)) return;
        if (!appState.isProcessing) DOM.fileInput.click();
    });

    if (DOM.loadDemoImgBtn) {
        DOM.loadDemoImgBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            loadSampleImage();
        });
    }

    DOM.fileInput.addEventListener('change', handleFile);

    ['dragover', 'dragleave', 'drop'].forEach(evt => {
        DOM.uploadZone.addEventListener(evt, e => e.preventDefault());
    });

    DOM.uploadZone.addEventListener('dragover', () => DOM.uploadZone.style.borderColor = 'var(--accent-teal)');
    DOM.uploadZone.addEventListener('dragleave', () => DOM.uploadZone.style.borderColor = '');

    DOM.uploadZone.addEventListener('drop', e => {
        DOM.uploadZone.style.borderColor = '';
        if (!appState.isProcessing && e.dataTransfer.files.length) {
            DOM.fileInput.files = e.dataTransfer.files;
            handleFile({ target: DOM.fileInput });
        }
    });

    DOM.removeImgBtn.addEventListener('click', resetUploadState);
}

function loadSampleImage() {
    const svgSample = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="250" viewBox="0 0 400 250"><rect width="400" height="250" fill="%23060d1a"/><path d="M 50 180 Q 120 140 220 160 T 350 90 Q 280 40 180 60 Z" fill="%23000000" opacity="0.85" stroke="%230ea5e9" stroke-width="1.5"/><circle cx="200" cy="120" r="4" fill="%23f97316"/><text x="15" y="25" fill="%230ea5e9" font-family="monospace" font-size="12">SENTINEL-1A SAR C-BAND | VV POLARIZATION</text><text x="15" y="235" fill="%2364748b" font-family="monospace" font-size="10">LAT: ${appState.coordinates.lat}&deg; N  LON: ${appState.coordinates.lon}&deg; E</text></svg>`;
    DOM.imgPreview.src = svgSample;
    DOM.fileName.textContent = 'Sentinel1A_SAR_20260913_NorthSea.tiff';
    DOM.uploadZone.classList.add('hidden');
    DOM.previewArea.classList.remove('hidden');
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
        DOM.fileName.textContent = file.name;
        DOM.uploadZone.classList.add('hidden');
        DOM.previewArea.classList.remove('hidden');
        DOM.runBtn.disabled = false;
    };
    reader.readAsDataURL(file);

    if (appState.dbId) {
        try {
            await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}/upload`, {
                method: 'POST'
            });
        } catch(e) { console.error(e); }
    }
}

function resetUploadState() {
    appState.isProcessing = false;
    appState.analysisComplete = false;
    DOM.fileInput.value = '';
    DOM.previewArea.classList.add('hidden');
    DOM.uploadZone.classList.remove('hidden');
    DOM.runBtn.disabled = false;
    DOM.runBtn.textContent = 'Run AI Detection';

    document.querySelectorAll('.pipeline-step').forEach(step => {
        step.className = 'pipeline-step pending';
        step.textContent = step.textContent.replace(' ✓', '');
    });

    DOM.results.classList.add('hidden');
    DOM.pipeline.classList.add('hidden');
    DOM.driftPanel.classList.add('hidden');
    DOM.vesselsPanel.classList.add('hidden');

    DOM.evidenceTimeline.innerHTML = '<div class="empty-state text-muted">Run detection analysis to populate evidence chain steps.</div>';
    DOM.dossierPreview.innerHTML = '<div class="empty-state text-muted">Dossier summary unavailable until analysis completes.</div>';
    DOM.exportBtn.disabled = true;
    
    renderMapLayers();
}

// ==========================================
// 14. ANALYSIS PIPELINE (MOCK API CHANNELS)
// ==========================================
function initAnalysis() {
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
            // Use a real UUID for sceneId (backend validation requires it)
            const fakeSceneId = crypto.randomUUID ? crypto.randomUUID() : '00000000-0000-4000-8000-000000000001';
            const res = await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}/analyze`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ sceneId: fakeSceneId })
            });
            const json = await res.json();
            
            if (json.success) {
                await updateStep('step-detect', 'Running AI segmentation...');
                appState.detection = json.data.detection;
                
                await updateStep('step-validate', 'Evaluating look-alike risk...');
                
                await updateStep('step-drift', 'Running Lagrangian back-drift...');
                // Merge API drift result into appState (keep mode/forecastHours from local state)
                const driftData = json.data.drift;
                appState.drift.trajectoryBack = driftData.trajectoryBack || [];
                appState.drift.trajectoryForward = driftData.trajectoryForward || [];
                // Update origin from drift result
                if (driftData.origin) {
                    appState.origin.lat = driftData.origin.lat;
                    appState.origin.lon = driftData.origin.lon;
                    appState.origin.radiusKm = driftData.origin.radiusKm || appState.whatIf.radiusKm;
                }
                appState._uncertaintyCone = driftData.uncertaintyCone || [];

                await updateStep('step-ais', 'Correlating AIS telemetry...');
                appState.vessels = json.data.vessels;
                // Add id field for vessel selection compatibility
                appState.vessels.forEach((v, i) => { v.id = v.id || `v${i+1}`; v.baseScore = v.score; });
                if (appState.vessels.length > 0) appState.selectedVesselId = appState.vessels[0].id;

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
}

function updateStep(stepId, text) {
    return new Promise(resolve => {
        const step = document.getElementById(stepId);
        step.classList.remove('pending');
        step.classList.add('active');
        step.textContent = text;

        setTimeout(() => {
            step.classList.remove('active');
            step.classList.add('done');
            step.textContent += ' ✓';
            resolve();
        }, CONFIG.SIMULATION_DELAY_MS);
    });
}

function completeAnalysis() {
    appState.analysisComplete = true;
    DOM.runBtn.textContent = 'Re-Run AI Analysis';
    DOM.runBtn.disabled = false;

    DOM.results.classList.remove('hidden');
    DOM.driftPanel.classList.remove('hidden');
    DOM.vesselsPanel.classList.remove('hidden');

    renderMapLayers();
    updateUIElements();
    renderEvidenceChain();  // Use API data — not the mock generator
    generateDossier();      // Render dossier preview panel from appState
    DOM.exportBtn.disabled = false;
}

// ==========================================
// 15. EVIDENCE DOSSIER & EXPORT SYSTEM
// ==========================================
function initEvidence() {
    DOM.exportBtn.addEventListener('click', exportDossierReport);
}

// Renders evidence chain from API data (supports both old mock fields and new API fields)
function renderEvidenceChain() {
    DOM.evidenceTimeline.innerHTML = '';
    if (!appState.evidenceChain || appState.evidenceChain.length === 0) {
        DOM.evidenceTimeline.innerHTML = '<div class="empty-state text-muted">No evidence chain data returned.</div>';
        return;
    }
    appState.evidenceChain.forEach(item => {
        // Support both API format (event_type, occurred_label, description, source)
        // and old mock format (type, time, title, desc, src)
        const type = item.event_type || item.type || 'success';
        const time = item.occurred_label || item.time || '';
        const title = item.title || '';
        const desc = item.description || item.desc || '';
        const src = item.source || item.src || '';
        DOM.evidenceTimeline.innerHTML += `
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

// Legacy function kept for backward compat (not used when API data is present)
function generateEvidenceChain() {
    renderEvidenceChain();
}

function generateDossier() {
    const topCandidate = appState.vessels[0] || { name: 'Candidate Vessel A', mmsi: '235001234', score: 87 };
    
    const dossierData = [
        ['Investigation ID', appState.investigationId],
        ['Timestamp (UTC)', new Date().toISOString().replace('T',' ').substring(0, 19)],
        ['Primary Centroid', `${appState.coordinates.lat.toFixed(4)} N, ${appState.coordinates.lon.toFixed(4)} E`],
        ['Primary Sensor', 'Sentinel-1 SAR C-Band'],
        ['Oil Slick Area', '14.8 km²'],
        ['Confidence Score', '87% (High)'],
        ['Wind Vectors', `${appState.environment.windSpeed} kts @ ${appState.environment.windDir}°`],
        ['Current Vectors', `${appState.environment.currentSpeed} m/s @ ${appState.environment.currentDir}°`],
        ['Origin Probability', `${appState.origin.lat.toFixed(4)} N, ${appState.origin.lon.toFixed(4)} E (r=${appState.origin.radiusKm}km)`],
        ['Top Candidate Source', `${topCandidate.name} (MMSI: ${topCandidate.mmsi})`],
        ['Attribution Score', `${topCandidate.score}%`],
        ['Surveillance Anomaly', 'Candidate Target-Unverified missing AIS broadcast']
    ];

    let html = '';
    dossierData.forEach(row => {
        html += `<div class="dossier-row"><strong>${row[0]}</strong> <span class="mono">${row[1]}</span></div>`;
    });
    DOM.dossierPreview.innerHTML = html;
}

async function exportDossierReport() {
    if (!appState.dbId) return;
    try {
        DOM.exportBtn.textContent = 'Generating...';
        DOM.exportBtn.disabled = true;
        
        const res = await fetch(`${CONFIG.API_BASE_URL}/investigations/${appState.dbId}/dossier/export`, { method: 'POST' });
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
}

function updateUIElements() {
    DOM.inputLat.value = appState.coordinates.lat.toFixed(4);
    DOM.inputLon.value = appState.coordinates.lon.toFixed(4);
    
    document.getElementById('detCentroidVal').textContent = `${appState.coordinates.lat.toFixed(4)}°N, ${appState.coordinates.lon.toFixed(4)}°E`;
    // Guard against origin being unset before analysis
    if (appState.origin && typeof appState.origin.lat === 'number') {
        document.getElementById('originCoordsVal').textContent = `${appState.origin.lat.toFixed(4)}°N, ${appState.origin.lon.toFixed(4)}°E`;
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
    
    DOM.sliderWindSpeed.value = 12; DOM.valWindSpeed.textContent = '12 kts';
    DOM.sliderWindDir.value = 45; DOM.valWindDir.textContent = '045° NE';
    DOM.sliderCurrentSpeed.value = 0.8; DOM.valCurrentSpeed.textContent = '0.8 m/s';
    DOM.sliderCurrentDir.value = 30; DOM.valCurrentDir.textContent = '030° NNE';
    DOM.radiusSlider.value = 8.5; DOM.valRadius.textContent = '8.5 km';
    DOM.timeShiftSlider.value = 0; DOM.valTimeShift.textContent = '0 hrs';
    DOM.timeSlider.value = 0; DOM.scrubberTimeDisplay.textContent = 'T - 0h (Detection)';

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
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
        } catch(e) { console.error('Patch error', e); }
    }, 500);
}
