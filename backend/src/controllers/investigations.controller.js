const supabase = require('../config/supabase');
const { generateAndUploadDossier } = require('../services/dossier');
const path = require('path');
const util = require('util');
const exec = util.promisify(require('child_process').exec);
const fs = require('fs/promises');
const os = require('os');
const crypto = require('crypto');

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

    const { data: inv, error: invError } = await supabase.from('investigations').select().eq('id', id).single();
    if (invError) throw invError;

    const environment = inv.environment || {
      windSpeed: 12,
      windDir: 225,
      currentSpeed: 0.4,
      currentDir: 180
    };

    const outDir = path.join(os.tmpdir(), `oilspill_${crypto.randomUUID()}`);
    await fs.mkdir(outDir, { recursive: true });
    
    // Command to launch python web bridge
    const runDir = path.join(__dirname, '..', '..', '..');
    const pythonExe = 'python';
    
    // On Windows cmd.exe, use double quotes for the argument and escape inner double quotes
    const envJson = JSON.stringify(environment).replace(/"/g, '\\"');
    const cmd = `"${pythonExe}" -m oilspill.web_bridge --out "${outDir}" --lat ${inv.lat} --lon ${inv.lon} --env "${envJson}"`;
    console.log("Running AI process:", cmd);
    
    await exec(cmd, { cwd: runDir });
    
    const resultRaw = await fs.readFile(path.join(outDir, 'web.json'), 'utf8');
    const parsedResult = JSON.parse(resultRaw);
    
    // Clean up temporary out directory
    await fs.rm(outDir, { recursive: true, force: true });

    res.json({
      success: true,
      data: parsedResult
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
