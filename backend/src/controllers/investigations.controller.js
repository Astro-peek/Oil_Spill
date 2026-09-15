const supabase = require('../config/supabase');
const ai = require('../services/aiClient');
const { generateAndUploadDossier } = require('../services/dossier');

exports.create = async (req, res, next) => {
  try {
    const { lat, lon } = req.body;
    const code = `OT-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${Math.floor(Math.random()*1000).toString().padStart(3,'0')}`;
    const payload = { lat, lon, code };
    
    // We intentionally don't insert location geometry directly to let postgis handle st_makepoint via triggered or just not passed if it's generated
    // wait, schema says: location geometry(Point, 4326) generated always as ... stored
    
    const { data, error } = await supabase
      .from('investigations')
      .insert({ lat, lon, code })
      .select()
      .single();
      
    if (error) throw error;
    
    res.json({
      success: true,
      data: {
        id: data.id,
        code: data.code,
        coordinates: { lat: data.lat, lon: data.lon },
        environment: data.environment,
        whatIf: data.what_if,
        status: data.status,
        createdAt: data.created_at
      }
    });
  } catch (err) { next(err); }
};

exports.getOne = async (req, res, next) => {
  try {
    const { data, error } = await supabase
      .from('investigations')
      .select(`
        *,
        detections (*),
        drift_results (*),
        investigation_suspects (*),
        evidence_events (*),
        dossiers (*)
      `)
      .eq('id', req.params.id)
      .single();
      
    if (error) throw error;
    
    res.json({ success: true, data });
  } catch (err) { next(err); }
};

exports.patch = async (req, res, next) => {
  try {
    const updates = {};
    if (req.body.coordinates) {
      updates.lat = req.body.coordinates.lat;
      updates.lon = req.body.coordinates.lon;
    }
    if (req.body.environment) updates.environment = req.body.environment;
    if (req.body.whatIf) updates.what_if = req.body.whatIf;
    
    const { data, error } = await supabase
      .from('investigations')
      .update(updates)
      .eq('id', req.params.id)
      .select()
      .single();
      
    if (error) throw error;
    res.json({ success: true, data });
  } catch (err) { next(err); }
};

exports.upload = async (req, res, next) => {
  try {
    res.json({
      success: true,
      data: {
        sceneId: "fake-uuid-not-used-much",
        storagePath: "satellite-scenes/fake-path.tiff",
        publicUrl: "n/a"
      }
    });
  } catch (err) { next(err); }
};

exports.analyze = async (req, res, next) => {
  try {
    const { id } = req.params;
    
    // fetch investigation
    const { data: inv, error: invError } = await supabase.from('investigations').select().eq('id', id).single();
    if (invError) throw invError;
    
    // 1. Detect
    const detection = await ai.detect("mock-url", inv.lat, inv.lon);

    // 2. Drift — use saved environment or sensible defaults if not yet patched
    const environment = inv.environment || {
      windSpeed: 12,
      windDir: 225,
      currentSpeed: 0.4,
      currentDir: 180
    };
    const drift = await ai.calculateDrift(detection.centroid, detection.slickAgeHours, environment, 48);
    
    // 3. Correlate & Attribute
    const releaseWindow = { start: "2026-09-12T00:00:00Z", end: "2026-09-12T18:00:00Z" };
    const candidates = await ai.correlate(drift.origin, releaseWindow, inv.what_if);
    
    // 4. Evidence Chain
    const evidenceChain = [
      { event_type: "success", occurred_label: "T-0h", title: "Anomaly Detected", description: "Spill detected near location.", source: "AI" },
      { event_type: "warning", occurred_label: "T-2h", title: "Correlation", description: candidates[0]?.name + " in origin radius.", source: "AIS" }
    ];

    res.json({
      success: true,
      data: {
        detection,
        drift,
        vessels: candidates,
        evidenceChain
      }
    });
  } catch (err) { next(err); }
};

exports.exportDossier = async (req, res, next) => {
  try {
     const { id } = req.params;
     const { data: inv } = await supabase.from('investigations').select().eq('id', id).single();
     // In a real app we'd fetch actual suspects.
     const suspects = [{ name_snapshot: "Candidate A", mmsi: 123, score: 90 }];
     
     const docResult = await generateAndUploadDossier(inv, { suspects });
     res.json({ success: true, data: docResult });
  } catch(err) { next(err); }
};
