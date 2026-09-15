const express = require('express');
const cors = require('cors');
const env = require('./config/env');
const errorHandler = require('./middleware/errorHandler');
const rateLimit = require('express-rate-limit');
const investigationsRoutes = require('./routes/investigations.routes');

const app = express();

app.use(cors({ origin: env.CORS_ORIGIN }));
app.use(express.json());

const apiLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 100 });
app.use('/api/', apiLimiter);

app.use('/api/v1/investigations', investigationsRoutes);

app.use(errorHandler);

module.exports = app;
