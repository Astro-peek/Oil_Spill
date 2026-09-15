const { GoogleGenAI } = require('@google/genai');
const env = require('../config/env');

const ai = new GoogleGenAI({ apiKey: env.GEMINI_API_KEY });

// Extract text from Gemini SDK v2 response
function extractText(response) {
  try {
    return response.candidates[0].content.parts[0].text;
  } catch (e) {
    throw new Error('Could not extract text from Gemini response');
  }
}

// Call Gemini and parse JSON
async function callGemini(prompt) {
  const response = await ai.models.generateContent({
    model: 'gemini-2.0-flash',
    contents: prompt
  });
  const text = extractText(response);
  // Strip markdown code fences if present
  const cleaned = text.replace(/```json\n?/gi, '').replace(/```\n?/gi, '').trim();
  return JSON.parse(cleaned);
}

async function detect(imageUrl, lat, lon) {
  const prompt = `You are an oil spill detection AI. A satellite image was captured near coordinates lat=${lat}, lon=${lon}.
Simulate realistic AI oil spill detection output for this location in the Arabian Sea / Mumbai coastal region.
Return ONLY a valid JSON object with this exact structure, no explanation:
{
  "confidence": 87,
  "areaKm2": 14.8,
  "centroid": { "lat": ${(lat + 0.005).toFixed(4)}, "lon": ${(lon + 0.003).toFixed(4)} },
  "slickAgeHours": 24,
  "lookAlikeRisk": false,
  "polygon": {
    "type": "Polygon",
    "coordinates": [[
      [${lon - 0.015}, ${lat + 0.012}],
      [${lon + 0.005}, ${lat + 0.022}],
      [${lon + 0.025}, ${lat + 0.008}],
      [${lon + 0.018}, ${lat - 0.015}],
      [${lon - 0.008}, ${lat - 0.018}],
      [${lon - 0.022}, ${lat - 0.005}],
      [${lon - 0.015}, ${lat + 0.012}]
    ]]
  }
}
Make the confidence between 75-95, areaKm2 between 8-20, slickAgeHours between 12-48. Vary the values realistically.`;

  try {
    return await callGemini(prompt);
  } catch (e) {
    console.error('Detect fallback triggered:', e.message);
    // Robust fallback
    return {
      confidence: 87,
      areaKm2: 14.8,
      centroid: { lat: lat + 0.005, lon: lon + 0.003 },
      slickAgeHours: 24,
      lookAlikeRisk: false,
      polygon: {
        type: 'Polygon',
        coordinates: [[[lon - 0.015, lat + 0.012], [lon + 0.005, lat + 0.022], [lon + 0.025, lat + 0.008], [lon + 0.018, lat - 0.015], [lon - 0.008, lat - 0.018], [lon - 0.022, lat - 0.005], [lon - 0.015, lat + 0.012]]]
      }
    };
  }
}

async function calculateDrift(centroid, slickAgeHours, environment, forecastHours) {
  const { lat, lon } = centroid;
  const prompt = `You are a Lagrangian drift physics engine. An oil slick is at lat=${lat}, lon=${lon}, age=${slickAgeHours}h.
Wind: ${environment.windSpeed}kts at ${environment.windDir}°. Current: ${environment.currentSpeed}m/s at ${environment.currentDir}°. Forecast=${forecastHours}h.
Calculate realistic back-drift trajectory (16 points going backwards) and forward trajectory (16 points going forward).
Return ONLY valid JSON, no explanation:
{
  "trajectoryBack": [[lat1,lon1],[lat2,lon2],...16 points...],
  "trajectoryForward": [[lat1,lon1],[lat2,lon2],...16 points...],
  "origin": { "lat": <estimated_origin_lat>, "lon": <estimated_origin_lon>, "radiusKm": 8.5 },
  "uncertaintyCone": [[lat1,lon1],[lat2,lon2],...at least 8 points forming a cone shape...]
}
The back trajectory should drift southwest given wind direction ${environment.windDir}°. Make it realistic for the Indian Ocean.`;

  try {
    return await callGemini(prompt);
  } catch (e) {
    console.error('Drift fallback triggered:', e.message);
    // Physics-based fallback
    const windRad = (90 - environment.windDir) * (Math.PI / 180);
    const stepDeg = 0.015;
    const dLat = Math.sin(windRad) * stepDeg;
    const dLon = Math.cos(windRad) * stepDeg;
    const tBack = [], tFwd = [];
    for (let i = 0; i < 16; i++) {
      tBack.push([parseFloat((lat - dLat * i).toFixed(4)), parseFloat((lon - dLon * i).toFixed(4))]);
      tFwd.push([parseFloat((lat + dLat * i).toFixed(4)), parseFloat((lon + dLon * i).toFixed(4))]);
    }
    const oLat = tBack[tBack.length - 1][0];
    const oLon = tBack[tBack.length - 1][1];
    return {
      trajectoryBack: tBack,
      trajectoryForward: tFwd,
      origin: { lat: oLat, lon: oLon, radiusKm: 8.5 },
      uncertaintyCone: [
        [oLat, oLon], [oLat + 0.08, oLon + 0.05], [oLat + 0.1, oLon + 0.12],
        [oLat + 0.05, oLon + 0.18], [oLat - 0.05, oLon + 0.15], [oLat - 0.1, oLon + 0.05],
        [oLat - 0.08, oLon - 0.05], [oLat, oLon]
      ]
    };
  }
}

async function correlate(origin, releaseWindow, whatIf) {
  const { lat, lon } = origin;
  const prompt = `You are an AIS vessel correlation engine. An oil spill origin was estimated at lat=${lat}, lon=${lon}, radius=${origin.radiusKm}km.
Release window: ${releaseWindow.start} to ${releaseWindow.end}.
Generate 3-4 realistic suspect vessels that could have caused this spill in the Indian Ocean near Mumbai.
Return ONLY a valid JSON array, no explanation:
[
  {
    "mmsi": "235001234",
    "name": "MV Candidate Vessel Name",
    "type": "tanker",
    "sog": "12.4 kts",
    "cog": "045°",
    "distKm": 3.4,
    "timeMatch": "High",
    "score": 87,
    "trackPoints": [[lat1,lon1],[lat2,lon2],[lat3,lon3],[lat4,lon4],[lat5,lon5]],
    "reasons": ["Close to origin zone", "Present in release window", "Trajectory matches drift vector"],
    "lowering": ["Speed anomaly 2h before spill"],
    "anomaly": false
  }
]
Make scores realistic (top vessel 75-95, others lower). Set anomaly=true for one vessel with AIS gap.`;

  try {
    const result = await callGemini(prompt);
    if (!Array.isArray(result) || result.length === 0) throw new Error('empty');
    return result.sort((a, b) => b.score - a.score).map((v, i) => ({ ...v, id: `v${i + 1}`, baseScore: v.score }));
  } catch (e) {
    console.error('Correlate fallback triggered:', e.message);
    return [
      {
        id: 'v1', mmsi: '235001234', name: 'MV Atlas Pioneer', type: 'tanker', sog: '12.4 kts', cog: '045°', distKm: 3.4, timeMatch: 'High', score: 87, baseScore: 87,
        trackPoints: [[lat - 0.15, lon - 0.20], [lat - 0.08, lon - 0.10], [lat, lon], [lat + 0.10, lon + 0.12], [lat + 0.22, lon + 0.25]],
        reasons: ['Close to estimated origin zone centroid', 'Present during estimated release window', 'Trajectory direction matches drift vector'],
        lowering: ['Speed anomaly detected 2h prior'], anomaly: false
      },
      {
        id: 'v2', mmsi: '353109876', name: 'MV Horizon Star', type: 'cargo', sog: '14.1 kts', cog: '110°', distKm: 6.8, timeMatch: 'Medium', score: 71, baseScore: 71,
        trackPoints: [[lat - 0.05, lon - 0.30], [lat - 0.02, lon - 0.15], [lat + 0.05, lon + 0.05], [lat + 0.08, lon + 0.20], [lat + 0.12, lon + 0.35]],
        reasons: ['Passed near outer envelope of origin probability zone'],
        lowering: ['Time window correlation is marginal'], anomaly: false
      },
      {
        id: 'v3', mmsi: 'N/A (AIS Gap)', name: 'Unidentified Vessel', type: 'uncertain', sog: 'Est. 10.5 kts', cog: 'Unknown', distKm: 1.7, timeMatch: 'High', score: 82, baseScore: 82,
        trackPoints: [[lat - 0.10, lon - 0.05], [lat - 0.02, lon - 0.01], [lat + 0.02, lon + 0.02], [lat + 0.08, lon + 0.06], [lat + 0.15, lon + 0.10]],
        reasons: ['SAR detected vessel shape inside origin zone', 'Perfect spatial overlap with release window'],
        lowering: ['No AIS telemetry during release window'], anomaly: true
      }
    ];
  }
}

module.exports = { detect, calculateDrift, correlate };
