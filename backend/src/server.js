const app = require('./app');
const env = require('./config/env');

const PORT = env.PORT || 4000;

app.listen(PORT, () => {
  console.log(`OceanTrace Backend running on port ${PORT} in ${env.NODE_ENV} mode`);
});
