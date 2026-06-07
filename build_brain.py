import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

print("⚙️ Flushing and rebuilding Suncoast Knowledge Base...")

# Load the architecture document
loader = TextLoader("suncoast_architecture.md")
doc = loader.load()

# Split with a larger size to keep sections intact
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
chunks = text_splitter.split_documents(doc)
print(f"🔪 Sliced document into {len(chunks)} comprehensive chunks.")

# Initialize embedding model
embeddings = OllamaEmbeddings(model="nomic-embed-text")

# Build clean vector vault
db = Chroma.from_documents(
    documents=chunks, 
    embedding=embeddings, 
    persist_directory="./suncoast_db"
)

print("✅ SUCCESS: Database rebuilt clean.")
