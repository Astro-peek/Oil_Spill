const supabase = require('../config/supabase');
const ai = require('../services/aiClient');
const { generateAndUploadDossier } = require('../services/dossier');

exports.create = async (req, res, next) => {
  try {
    const { lat, lon } = req.body;
    const code = `OT-${new Date().toISOString().slice(0,10).replace(/-/g,'')}-${Math.floor(Math.random()*1000).toString().padStart(3,'0')}`;
    const payload = { lat, lon, code };




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
    if (!req.file) {
      throw new Error("No file uploaded");
    }
    res.json({
      success: true,
      data: {
        sceneId: req.file.path,
        storagePath: req.file.path,
        publicUrl: "n/a"
      }
    });
  } catch (err) { next(err); }
};

exports.analyze = async (req, res, next) => {
  try {
    const { id } = req.params;

    const { data: inv, error: invError } = await supabase.from('investigations').select().eq('id', id).single();
    if (invError) throw invError;

    const environment = inv.environment || {
      windSpeed: 12,
      windDir: 225,
      currentSpeed: 0.4,
      currentDir: 180
    };

    const result = await ai.runFullPipeline(inv.lat, inv.lon, environment, req.body.sceneId);

    res.json({
      success: true,
      data: {
        detection: result.detection,
        drift: result.drift,
        vessels: result.vessels,
        evidenceChain: result.evidenceChain
      }
    });
  } catch (err) { next(err); }
};

exports.exportDossier = async (req, res, next) => {
  try {
     const { id } = req.params;
     const { data: inv } = await supabase.from('investigations').select().eq('id', id).single();

     const suspects = [{ name_snapshot: "Candidate A", mmsi: 123, score: 90 }];

     const docResult = await generateAndUploadDossier(inv, { suspects });
     res.json({ success: true, data: docResult });
  } catch(err) { next(err); }
};
