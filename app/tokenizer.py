import regex as re
from typing import List, Dict, Any, Tuple
from app.nlp import normalize_text

TOKEN_PATTERN = re.compile(r"[\p{L}\p{N}]+|[^\p{L}\p{N}\s]+|\s+", re.UNICODE)

class ArticleTokenizer:
    @staticmethod
    def tokenize_text(text: str, paragraph_idx: int, is_title: bool, start_id: int) -> Tuple[List[Dict[str, Any]], int]:
        tokens = []
        current_id = start_id

        # Split using regex
        raw_chunks = TOKEN_PATTERN.findall(text)

        for chunk in raw_chunks:
            if not chunk:
                continue

            # Determine token type
            if chunk.isspace():
                token_type = "space"
                is_word = False
            elif any(c.isalnum() for c in chunk):
                token_type = "word"
                is_word = True
            else:
                token_type = "punct"
                is_word = False

            token = {
                "id": current_id,
                "text": chunk,
                "type": token_type,
                "is_word": is_word,
                "length": len(chunk) if is_word else 0,
                "is_title": is_title,
                "paragraph_idx": paragraph_idx,
                "revealed": not is_word, # Punctuation and spaces are revealed by default
                "normalized": normalize_text(chunk) if is_word else ""
            }
            tokens.append(token)
            current_id += 1

        return tokens, current_id

    @classmethod
    def process_article(cls, title: str, paragraphs: List[str]) -> Dict[str, Any]:
        """
        Tokenizes the title and paragraphs of an article, preparing the masked game structure.
        """
        all_tokens = []
        token_id = 0

        # Process title
        title_tokens, token_id = cls.tokenize_text(title, paragraph_idx=-1, is_title=True, start_id=token_id)
        all_tokens.extend(title_tokens)

        # Process paragraphs
        for p_idx, paragraph in enumerate(paragraphs):
            p_tokens, token_id = cls.tokenize_text(paragraph, paragraph_idx=p_idx, is_title=False, start_id=token_id)
            all_tokens.extend(p_tokens)

        # Gather metadata
        title_word_ids = [t["id"] for t in all_tokens if t["is_title"] and t["is_word"]]
        # Identify significant title words (e.g. length > 2 or non-stop clitics)
        stopwords = {"le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "a", "au", "aux", "en", "et", "ou"}
        significant_title_ids = [
            t["id"] for t in all_tokens
            if t["is_title"] and t["is_word"] and t["normalized"] not in stopwords
        ]
        if not significant_title_ids:
            significant_title_ids = title_word_ids

        body_word_ids = [t["id"] for t in all_tokens if not t["is_title"] and t["is_word"]]
        total_word_count = len(title_word_ids) + len(body_word_ids)

        return {
            "tokens": all_tokens,
            "title_tokens": title_tokens,
            "title_word_ids": title_word_ids,
            "significant_title_ids": significant_title_ids,
            "body_word_ids": body_word_ids,
            "total_words": total_word_count
        }
