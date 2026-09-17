const { createClient } = require('@supabase/supabase-js');
const env = require('./env');

if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
  console.warn('Supabase credentials missing. Client won\'t be fully functional.');
}

const supabase = createClient(env.SUPABASE_URL || 'http:
  auth: {
    autoRefreshToken: false,
    persistSession: false
  }
});

module.exports = supabase;
