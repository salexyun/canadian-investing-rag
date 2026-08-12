"""Interactive CLI for manually testing the RAG flow.

Not part of the eval pipeline, not the Streamlit interface (not built
yet) — just a REPL wrapper around rag.RAG so the system can be tried by
hand with real, freely-chosen questions.

Usage:
    python rag/chat.py
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from rag import RAG  # noqa: E402
from retriever import Retriever  # noqa: E402


def main() -> None:
    print("Building retriever (embedding model + BM25 index + reranker)...")
    print("(First run downloads the embedding/reranker models — a minute or so; cached after.)\n")
    retriever = Retriever.build()
    rag = RAG(retriever=retriever)
    print("Ready. Ask a question about investing in Canada (or 'quit' to exit).\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in ("quit", "exit"):
            break
        print("\n...\n")
        result = rag.rag(question)
        print(f"Assistant: {result.answer}\n")


if __name__ == "__main__":
    main()
