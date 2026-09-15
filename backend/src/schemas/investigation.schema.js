const { z } = require('zod');

const createInvestigationSchema = z.object({
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180)
});

const patchInvestigationSchema = z.object({
  coordinates: z.object({
    lat: z.number().min(-90).max(90),
    lon: z.number().min(-180).max(180)
  }).optional(),
  environment: z.object({
    windSpeed: z.number().min(0).max(100),
    windDir: z.number().min(0).max(360),
    currentSpeed: z.number().min(0).max(100),
    currentDir: z.number().min(0).max(360)
  }).optional(),
  whatIf: z.object({
    radiusKm: z.number().min(0).max(100),
    timeShiftHours: z.number().min(-72).max(72)
  }).optional()
});

const analyzeInvestigationSchema = z.object({
  sceneId: z.string().min(1).optional(),   // optional — may come from upload step
  analysisType: z.string().optional()
});

module.exports = {
  createInvestigationSchema,
  patchInvestigationSchema,
  analyzeInvestigationSchema
};
