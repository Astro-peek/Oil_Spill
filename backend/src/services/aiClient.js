const { execFile } = require('node:child_process');
const { readFile, rm } = require('node:fs/promises');
const { promisify } = require('node:util');
const path = require('node:path');

// Target the handoff folder. Adjust based on where this backend is located.
// backend is at \ASTRO\Sih_26143\Oil_Spill\backend
// handoff is at \ASTRO\Sih_26143\AI-model-handoff\handoff
const AI_DIR = path.resolve(__dirname, '../../../../AI-model-handoff/handoff');
const PY = 'python';

async function runFullPipeline(lat, lon, env, imagePath) {
  const out = path.join(process.cwd(), `tmp-oceantrace-${Date.now()}`);
  
  const args = [
    "-m", "oilspill.web_bridge", 
    "--out", out, 
    "--lat", String(lat), 
    "--lon", String(lon)
  ];
  if (env) {
    args.push("--env", JSON.stringify(env));
  }
  if (imagePath && imagePath !== "fake-uuid-not-used-much" && !imagePath.match(/^00000000/)) {
    // If not a fake fallback string, assume it's a real path
    args.push("--image", imagePath);
  }

  try {
    await promisify(execFile)(PY, args, {
      cwd: AI_DIR,
      timeout: 300_000,
      maxBuffer: 10 * 1024 * 1024,
      env: { ...process.env, OILSPILL_DEVICE: "cpu" },
    });

    const webJsonPath = path.join(out, "web.json");
    const data = JSON.parse(await readFile(webJsonPath, "utf8"));
    return data;
  } catch (error) {
    if (error.stderr) {
      const match = error.stderr.match(/(ValueError|Exception|Error|RunTimeError):\s*(.*)/i);
      if (match) {
        throw new Error("AI Model Rejected Image: " + match[2].trim());
      }
    }
    console.error('AI pipeline error:', error);
    throw new Error('AI pipeline failed to run: ' + (error.message || 'Unknown error'));
  } finally {
    try {
      await rm(out, { recursive: true, force: true });
    } catch (cleanupError) {
      console.warn('Failed to cleanup temp directory:', out, cleanupError);
    }
  }
}

module.exports = { runFullPipeline };
