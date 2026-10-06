"""Local semantic embeddings using a small quantized ONNX model."""

from pathlib import Path


DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384
DEFAULT_BATCH_SIZE = 16


class FastEmbedEmbeddingProvider:
    """Create local passage and query vectors with FastEmbed."""

    def __init__(
        self,
        model=None,
        model_name=DEFAULT_MODEL,
        batch_size=DEFAULT_BATCH_SIZE,
        cache_dir=None,
    ):
        if not 1 <= batch_size <= 64:
            raise ValueError("batch_size must be between 1 and 64")
        self.model_name = model_name
        self.batch_size = batch_size
        self.cache_dir = Path(cache_dir) if cache_dir else (
            Path(__file__).resolve().parents[1] / "data" / "models" / "fastembed"
        )

        if model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as error:
                raise RuntimeError(
                    "FastEmbed is not installed. Run "
                    "'.venv/bin/pip install -r requirements.txt'."
                ) from error

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.model = TextEmbedding(
                model_name=model_name,
                cache_dir=str(self.cache_dir),
                threads=2,
            )
        else:
            self.model = model

    def embed_texts(self, texts):
        """Encode a sequence of already formatted text inputs."""

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")
        if not texts:
            return []

        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            vectors.extend(
                [float(value) for value in vector]
                for vector in self.model.embed(batch, batch_size=self.batch_size)
            )
        if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
            raise ValueError("Embedding model returned an unexpected vector dimension")
        return vectors

    def embed_query(self, question):
        """Encode one search question using the model's query instruction."""

        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        return self.embed_texts([f"query: {question}"])[0]

    def embed_chunks(self, chunks):
        """Encode code chunks with passage instructions and source metadata."""

        texts = [f"passage: {format_chunk_for_embedding(chunk)}" for chunk in chunks]
        vectors = self.embed_texts(texts)
        return [
            {"id": chunk["id"], "embedding": vector}
            for chunk, vector in zip(chunks, vectors)
        ]


def format_chunk_for_embedding(chunk):
    """Add source metadata to code so semantic search has useful context."""

    lines = [
        f"File: {chunk['file']}",
        f"Kind: {chunk.get('symbol_kind', chunk.get('kind', 'CODE'))}",
    ]
    if chunk.get("symbol"):
        lines.append(f"Symbol: {chunk['symbol']}")
    if chunk.get("class_name"):
        lines.append(f"Class: {chunk['class_name']}")
    if chunk.get("start_line") is not None and chunk.get("end_line") is not None:
        lines.append(f"Lines: {chunk['start_line']}-{chunk['end_line']}")
    lines.extend(["", chunk["content"]])
    return "\n".join(lines)
