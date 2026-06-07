from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
import requests

# 1. Connect to the existing local database
embeddings = OllamaEmbeddings(model="nomic-embed-text")
db = Chroma(persist_directory="./suncoast_db", embedding_function=embeddings)

# 2. The question targeting the memory architecture
question = "What vector databases do you use for LLM memory and RAG pipelines?"
print(f"❓ Question: {question}")

# 3. Search the ChromaDB for MORE relevant context (Increased k to 4)
results = db.similarity_search(question, k=4)
context = "\n".join([doc.page_content for doc in results])
print("\n🔍 Found Context in Database:")
print(f"--- \n{context}\n---")

# 4. Feed the context and the question to local Hermes
print("\n🤖 Hermes is thinking...")
url = "http://127.0.0.1:11434/api/chat"
prompt = f"Use the following internal documentation to answer the question.\n\nContext:\n{context}\n\nQuestion: {question}"

payload = {
    "model": "hermes3:8b",
    "messages": [
        {"role": "system", "content": "You are the Suncoast Agent Factory AI. Answer precisely based ONLY on the provided context."},
        {"role": "user", "content": prompt}
    ],
    "stream": False
}

response = requests.post(url, json=payload).json()
print(f"\n✅ Hermes Response:\n{response['message']['content']}")
