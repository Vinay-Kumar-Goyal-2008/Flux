import os

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

try:
    import pypdf
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# Default Sample documents for initialization if directory is empty
SAMPLE_NDMA = """
NATIONAL DISASTER MANAGEMENT AUTHORITY (NDMA)
SITUATION REPORT - FLOOD SITUATION IN BIHAR
1. General Situation: Due to heavy precipitation in Nepal catchment areas, the Kosi and Gandak rivers are flowing above warning marks.
2. Response Action: SDRF and NDRF teams are deploying rafts and lifejackets to facilitate rescue operations. Safe shelter locations have been opened.
3. Guidelines: Citizens should stay away from low-lying areas and follow local evacuation alerts.
"""

SAMPLE_UNOCHA = """
UN OFFICE FOR THE COORDINATION OF HUMANITARIAN AFFAIRS (UN-OCHA)
FLOOD DISASTER BRIEFING - SOUTH ASIA MONSOON
1. Inundation Levels: Rising river channels have damaged bridges and key arterial roads. Primary clinics require immediate aid.
2. Strategic Interventions: Distribute clean drinking water, sanitation tablets, tarpaulins, and mobile medical tents.
3. Medical warning: High humidity raises risk of mosquito vector breeding; distribute medication protocols.
"""

class FloodVectorDB:
    def __init__(self, db_path="./chroma_data", corpus_path="./corpus"):
        self.db_path = db_path
        self.corpus_path = corpus_path
        self.has_chroma = HAS_CHROMA
        
        os.makedirs(db_path, exist_ok=True)
        os.makedirs(corpus_path, exist_ok=True)
        
        if self.has_chroma:
            try:
                self.client = chromadb.PersistentClient(path=db_path)
                self.collection = self.client.get_or_create_collection(
                    name="flood_situation_reports"
                )
                
                # If corpus folder is completely empty, initialize it with sample files
                if len(os.listdir(corpus_path)) == 0:
                    self._write_default_samples()
                    
                # Dynamically ingest corpus files
                self.ingest_corpus_files()
            except Exception as e:
                print(f"[RAG Database] Client initialization failed: {e}. Running in sandbox mode.")
                self.has_chroma = False
        else:
            print("[RAG Database Sandbox] ChromaDB not installed. Ingestions and queries will use mock templates.")

    def _write_default_samples(self):
        print("[RAG Database] Writing default sample documents into ./corpus directory...")
        with open(os.path.join(self.corpus_path, "ndma_bihar.txt"), "w", encoding="utf-8") as f:
            f.write(SAMPLE_NDMA)
        with open(os.path.join(self.corpus_path, "un_ocha_southasia.txt"), "w", encoding="utf-8") as f:
            f.write(SAMPLE_UNOCHA)

    def extract_text_from_pdf(self, pdf_path):
        text = ""
        if not HAS_PDF:
            print("[RAG PDF Loader] pypdf is not installed. Skipping PDF parse.")
            return text
        try:
            reader = pypdf.PdfReader(pdf_path)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except Exception as e:
            print(f"[RAG Database] Error parsing PDF {pdf_path}: {e}")
        return text

    def chunk_text(self, text, chunk_size=500, overlap=100):
        chunks = []
        words = text.split()
        
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += (chunk_size - overlap)
            
        return [c for c in chunks if len(c.strip()) > 30]

    def ingest_corpus_files(self):
        if not self.has_chroma:
            return
            
        try:
            count = self.collection.count()
            if count > 0:
                print(f"[RAG Database] Collection ready with {count} indexed chunks.")
                return
                
            print("[RAG Database] Scanning ./corpus directory for dynamic ingestion...")
            files = os.listdir(self.corpus_path)
            
            doc_id_counter = 1
            for filename in files:
                filepath = os.path.join(self.corpus_path, filename)
                ext = os.path.splitext(filename)[1].lower()
                
                raw_text = ""
                if ext in [".txt", ".md"]:
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            raw_text = f.read()
                    except Exception as e:
                        print(f"Error reading file {filename}: {e}")
                elif ext == ".pdf":
                    raw_text = self.extract_text_from_pdf(filepath)
                    
                if not raw_text.strip():
                    continue
                    
                chunks = self.chunk_text(raw_text)
                print(f"[RAG Database] Ingesting {filename} ({len(chunks)} chunks)...")
                
                documents = []
                metadatas = []
                ids = []
                
                for index, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadatas.append({"source": filename, "chunk_index": index})
                    ids.append(f"doc_{doc_id_counter}_{index}")
                    
                if documents:
                    self.collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )
                doc_id_counter += 1
                
            print(f"[RAG Database] Ingestion finished. Total indexed documents count: {self.collection.count()}")
        except Exception as e:
            print(f"[RAG Database] Ingestion failed: {e}")

    def query_similar_reports(self, query_text, n_results=2):
        if not self.has_chroma:
            return [
                {"content": SAMPLE_NDMA, "metadata": {"source": "ndma_bihar.txt", "chunk_index": 0}},
                {"content": SAMPLE_UNOCHA, "metadata": {"source": "un_ocha_southasia.txt", "chunk_index": 0}}
            ][:n_results]
            
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            similar_docs = []
            if results and 'documents' in results and len(results['documents']) > 0:
                for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                    similar_docs.append({
                        "content": doc,
                        "metadata": meta
                    })
            return similar_docs
        except Exception as e:
            print(f"[RAG Database] Query failed: {e}. Returning sandbox templates.")
            return [
                {"content": SAMPLE_NDMA, "metadata": {"source": "ndma_bihar.txt", "chunk_index": 0}},
                {"content": SAMPLE_UNOCHA, "metadata": {"source": "un_ocha_southasia.txt", "chunk_index": 0}}
            ][:n_results]
