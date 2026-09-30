import os
from langchain_community.document_loaders import PyMuPDFLoader, TextLoader, UnstructuredURLLoader
from backend.utils.logger import logger

class DocumentLoader:
    @staticmethod
    def load_pdf(file_path):
        logger.info(f"Loading PDF: {file_path}")
        try:
            loader = PyMuPDFLoader(file_path)
            return loader.load()
        except Exception as e:
            logger.error(f"Error loading PDF {file_path}: {str(e)}")
            return []

    @staticmethod
    def load_txt(file_path):
        logger.info(f"Loading TXT: {file_path}")
        try:
            loader = TextLoader(file_path)
            return loader.load()
        except Exception as e:
            logger.error(f"Error loading TXT {file_path}: {str(e)}")
            return []

    @staticmethod
    def load_url(urls):
        if isinstance(urls, str):
            urls = [urls]
        logger.info(f"Loading URLs: {urls}")
        try:
            loader = UnstructuredURLLoader(urls=urls)
            return loader.load()
        except Exception as e:
            logger.error(f"Error loading URLs {urls}: {str(e)}")
            return []
