const { createClient } = require('@supabase/supabase-js');
const env = require('./env');

if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
  console.warn('Supabase credentials missing. Client may not be fully functional.');
}

const supabase = createClient(
  env.SUPABASE_URL || 'http://localhost:54321',
  env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY || 'placeholder-key',
  {
    auth: {
      autoRefreshToken: false,
      persistSession: false
    }
  }
);

module.exports = supabase;
