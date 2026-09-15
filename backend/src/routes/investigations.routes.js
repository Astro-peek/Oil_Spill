const express = require('express');
const router = express.Router();
const controller = require('../controllers/investigations.controller');
const validate = require('../middleware/validate');
const schema = require('../schemas/investigation.schema');

router.post('/', validate(schema.createInvestigationSchema), controller.create);
router.get('/:id', controller.getOne);
router.patch('/:id', validate(schema.patchInvestigationSchema), controller.patch);
router.post('/:id/upload', controller.upload);
router.post('/:id/analyze', validate(schema.analyzeInvestigationSchema), controller.analyze);
router.post('/:id/dossier/export', controller.exportDossier);

module.exports = router;
