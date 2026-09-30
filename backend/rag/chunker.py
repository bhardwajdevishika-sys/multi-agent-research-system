from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.utils.config import Config
from backend.utils.logger import logger

class TextChunker:
    def __init__(self, chunk_size=None, chunk_overlap=None):
        self.chunk_size = chunk_size or Config.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or Config.CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    def split_documents(self, documents):
        logger.info(f"Splitting {len(documents)} documents into chunks")
        chunks = self.splitter.split_documents(documents)
        logger.info(f"Created {len(chunks)} chunks")
        return chunks

    def split_text(self, text):
        return self.splitter.split_text(text)
