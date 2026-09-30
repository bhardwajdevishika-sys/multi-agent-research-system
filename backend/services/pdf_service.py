import os
from backend.rag.document_loader import DocumentLoader
from backend.utils.config import Config
from backend.utils.logger import logger

class PDFService:
    @staticmethod
    def process_pdf(file_path):
        if not os.path.exists(file_path):
            logger.error(f"PDF file not found: {file_path}")
            return None
        
        try:
            docs = DocumentLoader.load_pdf(file_path)
            # Add metadata about source
            for doc in docs:
                doc.metadata["source_type"] = "pdf"
                doc.metadata["file_name"] = os.path.basename(file_path)
            return docs
        except Exception as e:
            logger.error(f"Error processing PDF: {str(e)}")
            return None

    @staticmethod
    def save_uploaded_file(file):
        filename = file.filename
        upload_path = os.path.join(Config.UPLOAD_DIR, filename)
        file.save(upload_path)
        return upload_path
