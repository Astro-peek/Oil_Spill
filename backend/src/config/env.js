require('dotenv').config();

module.exports = {
  PORT: process.env.PORT || 4000,
  NODE_ENV: process.env.NODE_ENV || 'development',
  SUPABASE_URL: process.env.SUPABASE_URL,
  SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY,
  SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY,
  SUPABASE_STORAGE_BUCKET_SCENES: process.env.SUPABASE_STORAGE_BUCKET_SCENES || 'satellite-scenes',
  SUPABASE_STORAGE_BUCKET_DOSSIERS: process.env.SUPABASE_STORAGE_BUCKET_DOSSIERS || 'dossiers',
  CORS_ORIGIN: process.env.CORS_ORIGIN || 'http://localhost:5500',
  GEMINI_API_KEY: process.env.GEMINI_API_KEY
};
