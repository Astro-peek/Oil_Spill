const express = require('express');
const router = express.Router();
const controller = require('../controllers/investigations.controller');
const validate = require('../middleware/validate');
const schema = require('../schemas/investigation.schema');
const multer = require('multer');
const path = require('path');
const fs = require('fs');

const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    const uploadDir = path.join(__dirname, '../../uploads');
    if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });
    cb(null, uploadDir);
  },
  filename: function (req, file, cb) {
    cb(null, req.params.id + '-' + file.originalname);
  }
});
const upload = multer({ storage: storage });

router.post('/', validate(schema.createInvestigationSchema), controller.create);
router.get('/:id', controller.getOne);
router.patch('/:id', validate(schema.patchInvestigationSchema), controller.patch);
router.post('/:id/upload', upload.single('sceneImage'), controller.upload);
router.post('/:id/analyze', validate(schema.analyzeInvestigationSchema), controller.analyze);
router.post('/:id/dossier/export', controller.exportDossier);

module.exports = router;
