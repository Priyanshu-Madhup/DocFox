"""
Flashcard System for DocFox
Generates flashcards from document content using RAG and LLM
"""

import json
import random
from typing import List, Dict, Any
import numpy as np

class FlashcardSystem:
    def __init__(self, groq_client):
        """Initialize flashcard system with Groq client."""
        self.client = groq_client
        self.generated_flashcards = []
    
    def _search_relevant_chunks(
        self,
        query: str,
        notebook_id: int,
        document_store: List[Dict],
        embedding_model,
        faiss_index,
        top_k: int = 5
    ) -> List[Dict]:
        """Search for relevant chunks using FAISS."""
        # Generate query embedding
        query_embedding = embedding_model.encode([query])[0]
        query_embedding = query_embedding.astype('float32')
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        
        # Search FAISS
        distances, indices = faiss_index.search(
            np.array([query_embedding]), 
            min(top_k, faiss_index.ntotal)
        )
        
        # Get chunks and filter by notebook
        results = []
        for idx in indices[0]:
            if idx < len(document_store):
                chunk = document_store[idx]
                if chunk.get("notebook_id") == notebook_id:
                    results.append(chunk)
        
        return results[:top_k]
    
    def generate_flashcards(
        self,
        notebook_id: int,
        document_store: List[Dict],
        embedding_model,
        faiss_index,
        num_flashcards: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Generate flashcards from document content.
        
        Args:
            notebook_id: The notebook ID to generate flashcards for
            document_store: List of document chunks
            faiss_index: FAISS index for retrieving chunks
            num_flashcards: Number of flashcards to generate (default: 50)
            
        Returns:
            List of flashcard dictionaries
        """
        print(f"Generating {num_flashcards} flashcards for notebook {notebook_id}")
        
        # Filter chunks for this notebook
        notebook_chunks = [
            doc for doc in document_store
            if doc.get("notebook_id") == notebook_id
        ]
        
        if not notebook_chunks:
            print(f"No chunks found for notebook {notebook_id}")
            return []
        
        print(f"Found {len(notebook_chunks)} chunks for notebook {notebook_id}")
        
        # Use RAG to find key topics and questions
        search_queries = [
            "important concepts definitions",
            "key processes procedures methods",
            "main ideas principles theories",
            "critical facts information",
            "essential skills techniques"
        ]
        
        # Gather relevant chunks using RAG
        all_relevant_chunks = []
        for query in search_queries:
            relevant = self._search_relevant_chunks(
                query=query,
                notebook_id=notebook_id,
                document_store=document_store,
                embedding_model=embedding_model,
                faiss_index=faiss_index,
                top_k=5
            )
            all_relevant_chunks.extend(relevant)
        
        # Remove duplicates and sample
        unique_chunks = []
        seen_content = set()
        for chunk in all_relevant_chunks:
            content = chunk.get("chunk", chunk.get("content", ""))
            if content not in seen_content:
                unique_chunks.append(chunk)
                seen_content.add(content)
        
        # Sample diverse chunks for flashcard generation
        num_samples = min(20, len(unique_chunks)) if unique_chunks else min(20, len(notebook_chunks))
        sampled_chunks = random.sample(unique_chunks if unique_chunks else notebook_chunks, num_samples)
        
        # Create context from sampled chunks
        context = "\n\n".join([
            chunk.get("chunk", chunk.get("content", ""))
            for chunk in sampled_chunks
        ])
        
        # Limit context length
        if len(context) > 5000:
            context = context[:5000] + "..."
        
        # Generate flashcards using LLM with improved prompt
        prompt = f"""Based on the following document content, create {num_flashcards} educational flashcards for studying.

Document Content:
{context}

IMPORTANT INSTRUCTIONS FOR FLASHCARD FORMAT:
- The FRONT must be a clear QUESTION starting with question words
- Question starters: "What is", "How does", "Why is", "When should", "Where can", "Who", "Which", "Define", "Explain", "Describe", "Compare", "List", "Name"
- The BACK should be a concise ANSWER (2-4 sentences maximum)
- Keep answers SHORT and FOCUSED - avoid long paragraphs
- Use bullet points or numbered lists for multiple items

Examples of CORRECT flashcards:
Front: "What is the primary purpose of X?"
Back: "X is designed to achieve Y by doing Z. It helps solve problem A."

Front: "How does process X work?"
Back: "Process X works in 3 steps: 1) First step 2) Second step 3) Final step"

Front: "Why is concept X important?"
Back: "Concept X is important because it enables Y and prevents Z. It's fundamental to achieving W."

Front: "List three key features of X"
Back: "1. Feature one 2. Feature two 3. Feature three"

Examples of WRONG flashcards (DO NOT CREATE):
❌ Front: "The concept of X is important" (Statement, not a question)
❌ Front: "X" (Too vague)
❌ Back: "Long paragraph with multiple concepts and extensive details that goes on and on..." (Too long)

Create {num_flashcards} flashcards with:
1. QUESTIONS on front (must start with question words or command verbs)
2. SHORT, FOCUSED answers on back (2-4 sentences max)
3. Categories: "Definitions", "Concepts", "Procedures", "Facts", "Skills", "Comparisons"
4. Varied difficulty and question types

IMPORTANT: Respond with ONLY a valid JSON array, no additional text.

Format:
[
  {{
    "card_id": 1,
    "front": "What is the main purpose of [concept]?",
    "back": "[Concept] serves to achieve X. It helps solve Y problem.",
    "category": "Concepts"
  }},
  {{
    "card_id": 2,
    "front": "How does [process] work?",
    "back": "It works in 3 steps: 1) Step A 2) Step B 3) Step C",
    "category": "Procedures"
  }},
  {{
    "card_id": 3,
    "front": "List three key benefits of [topic]",
    "back": "1. Benefit one 2. Benefit two 3. Benefit three",
    "category": "Facts"
  }}
]

CRITICAL: Keep answers SHORT (2-4 sentences). Create {num_flashcards} flashcards. Return ONLY the JSON array."""

        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.1-70b-versatile",
                temperature=0.5,
                max_tokens=4000
            )
            
            response_text = completion.choices[0].message.content.strip()
            print(f"LLM response (first 200 chars): {response_text[:200]}")
            
            # Parse JSON response
            try:
                flashcards = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
                if json_match:
                    flashcards = json.loads(json_match.group(0))
                else:
                    # Fallback: create basic flashcards from chunks
                    print("Failed to parse LLM response, creating basic flashcards")
                    flashcards = self._create_basic_flashcards(sampled_chunks, num_flashcards)
            
            # Validate and clean flashcards
            valid_flashcards = []
            for i, card in enumerate(flashcards):
                if isinstance(card, dict) and "front" in card and "back" in card:
                    valid_flashcards.append({
                        "card_id": i + 1,
                        "front": card.get("front", ""),
                        "back": card.get("back", ""),
                        "category": card.get("category", "General")
                    })
            
            self.generated_flashcards = valid_flashcards
            print(f"Successfully generated {len(valid_flashcards)} flashcards")
            return valid_flashcards
            
        except Exception as e:
            print(f"Error generating flashcards: {e}")
            # Fallback: create basic flashcards
            return self._create_basic_flashcards(sampled_chunks, num_flashcards)
    
    def _create_basic_flashcards(self, chunks: List[Dict], num_cards: int) -> List[Dict]:
        """Create basic flashcards from chunks as fallback."""
        flashcards = []
        for i, chunk in enumerate(chunks[:num_cards]):
            content = chunk.get("chunk", chunk.get("content", ""))
            # Split into front (first sentence) and back (rest)
            sentences = content.split('. ')
            front = sentences[0] + "?" if sentences else "What is this about?"
            back = '. '.join(sentences[1:]) if len(sentences) > 1 else content
            
            flashcards.append({
                "card_id": i + 1,
                "front": front[:200],  # Limit length
                "back": back[:500],
                "category": "General"
            })
        
        return flashcards
    
    def get_flashcard_status(self) -> Dict[str, Any]:
        """Get current flashcard generation status."""
        return {
            "flashcards_generated": len(self.generated_flashcards),
            "has_flashcards": len(self.generated_flashcards) > 0
        }
    
    def clear_flashcards(self):
        """Clear generated flashcards."""
        self.generated_flashcards = []
