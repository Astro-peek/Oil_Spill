const PDFDocument = require('pdfkit');
const supabase = require('../config/supabase');
const env = require('../config/env');

async function generateAndUploadDossier(investigation, details) {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument();
    const buffers = [];

    doc.on('data', buffers.push.bind(buffers));
    doc.on('end', async () => {
      const pdfData = Buffer.concat(buffers);
      const filename = `dossier-${investigation.code}-${Date.now()}.pdf`;
      const storagePath = `${investigation.id}/${filename}`;

      try {
         const { data, error } = await supabase.storage
           .from(env.SUPABASE_STORAGE_BUCKET_DOSSIERS)
           .upload(storagePath, pdfData, {
             contentType: 'application/pdf'
           });

         if (error) {
           console.error("Storage upload error:", error);

           return resolve({ dossierId: "fake-id", downloadUrl: "about:blank" });
         }

         const { data: signedUrlData, error: signedUrlError } = await supabase.storage
           .from(env.SUPABASE_STORAGE_BUCKET_DOSSIERS)
           .createSignedUrl(storagePath, 60 * 60);

         const url = signedUrlData ? signedUrlData.signedUrl : "about:blank";


         const { data: dbData, error: dbError } = await supabase
            .from('dossiers')
            .insert({
               investigation_id: investigation.id,
               storage_path: storagePath
            })
            .select()
            .single();

         resolve({ dossierId: dbData ? dbData.id : "fake-id", downloadUrl: url });
      } catch (err) {
        console.error("Dossier error:", err);

        resolve({ dossierId: "fake-id", downloadUrl: "about:blank" });
      }
    });

    doc.fontSize(20).text('OceanTrace Evidence Dossier', { align: 'center' });
    doc.moveDown();
    doc.fontSize(12).text(`Investigation ID: ${investigation.code}`);
    doc.text(`Location: ${investigation.lat}, ${investigation.lon}`);
    doc.moveDown();

    doc.fontSize(16).text('Top Candidates');
    doc.moveDown();
    if (details.suspects) {
       details.suspects.forEach(s => {
          doc.fontSize(12).text(`${s.name_snapshot || s.name} (MMSI: ${s.mmsi}) - Score: ${s.score}`);
       });
    }

    doc.end();
  });
}

module.exports = { generateAndUploadDossier };
