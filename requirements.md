# PHANTOM — Complete Project Blueprint

---

## Tech Stack (Final Decisions)

```
Language        →  Python 3.11+
AI              →  Google Gemini 1.5 Flash (free)
Database        →  PostgreSQL on Railway
CLI Framework   →  Typer + Rich (beautiful terminal output)
PDF Extraction  →  PyMuPDF (fitz)
Web Scraping    →  Requests + BeautifulSoup4
YouTube         →  youtube-transcript-api
OOP/DSA         →  Built from scratch (core of the project)
Config          →  python-dotenv (.env file)
OS              →  Ubuntu (your primary)
```

---

## Full Project Structure

```
phantom/
│
├── .env                        # API keys, DATABASE_URL
├── .gitignore                  # ignore .env, __pycache__, venv
├── requirements.txt
├── README.md
├── main.py                     # CLI entry point (Typer app)
│
├── config/
│   └── settings.py             # loads .env, exposes constants
│
├── db/
│   ├── __init__.py
│   ├── connection.py           # psycopg2 connection pool
│   ├── schema.py               # CREATE TABLE statements, run once
│   └── queries.py              # all raw SQL queries (no ORM)
│
├── core/                       # OOP layer — your data models
│   ├── __init__.py
│   ├── memory.py               # Memory class (a stored file/note)
│   ├── topic.py                # Topic, StudySession classes
│   ├── quiz.py                 # Quiz, Question, Attempt classes
│   └── conversation.py        # Conversation, Message classes
│
├── dsa/                        # Data structures built from scratch
│   ├── __init__.py
│   ├── trie.py                 # Autocomplete for search
│   ├── inverted_index.py       # Word → [memory_ids] mapping
│   ├── min_heap.py             # Study scheduler (next due topic)
│   ├── lru_cache.py            # Cache recent AI responses
│   └── graph.py               # Topic prerequisite graph
│
├── ingest/                     # File type handlers
│   ├── __init__.py
│   ├── detector.py             # Detects file type from path/url
│   ├── pdf_reader.py           # PyMuPDF text extraction
│   ├── note_reader.py          # .txt .md .py .cpp reader
│   ├── url_scraper.py          # requests + bs4
│   └── youtube_reader.py       # transcript extraction
│
├── ai/
│   ├── __init__.py
│   ├── client.py               # Gemini API wrapper class
│   ├── rag.py                  # RAG pipeline (search + inject + ask)
│   └── prompts.py              # all system prompts as constants
│
└── utils/
    ├── __init__.py
    ├── display.py              # Rich tables, panels, colors
    └── helpers.py              # string cleaning, date formatting
```

---

## Database Schema (Final)

```sql
-- Every file/note/url you store
CREATE TABLE memories (
    id           SERIAL PRIMARY KEY,
    type         VARCHAR(20) NOT NULL,     -- pdf, note, url, code, video
    title        VARCHAR(255),
    filename     VARCHAR(255),
    raw_text     TEXT,
    summary      TEXT,                     -- AI generated
    subject      VARCHAR(100),             -- OS, DSA, SE etc.
    source_url   VARCHAR(500),
    file_size    INTEGER,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Tag index (inverted index lives in memory, this is persistent)
CREATE TABLE tags (
    id        SERIAL PRIMARY KEY,
    tag       VARCHAR(100),
    memory_id INTEGER REFERENCES memories(id) ON DELETE CASCADE
);

-- Topics for study/revision mode
CREATE TABLE topics (
    id                   SERIAL PRIMARY KEY,
    name                 VARCHAR(150) UNIQUE NOT NULL,
    subject              VARCHAR(100),
    confidence           INTEGER DEFAULT 0,     -- 0 to 100
    review_interval_days INTEGER DEFAULT 1,
    last_reviewed        TIMESTAMP,
    next_review          TIMESTAMP,
    memory_id            INTEGER REFERENCES memories(id)
);

-- Quiz history
CREATE TABLE quiz_attempts (
    id         SERIAL PRIMARY KEY,
    topic_id   INTEGER REFERENCES topics(id),
    score      INTEGER,
    total      INTEGER,
    taken_at   TIMESTAMP DEFAULT NOW()
);

-- Topic dependency graph (persistent edges)
CREATE TABLE topic_edges (
    id       SERIAL PRIMARY KEY,
    prereq   VARCHAR(150),
    topic    VARCHAR(150)
);

-- Full conversation history per session
CREATE TABLE conversations (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(50),
    role        VARCHAR(10),       -- user / assistant
    content     TEXT,
    memory_refs TEXT,              -- comma-separated memory IDs cited
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Daily study streak tracker
CREATE TABLE study_log (
    id         SERIAL PRIMARY KEY,
    date       DATE UNIQUE,
    topics_studied INTEGER DEFAULT 0,
    files_added    INTEGER DEFAULT 0
);
```

---

## CLI Commands (Final List)

```bash
# Memory commands
phantom add <file/url>              # ingest anything
phantom list                        # show all stored memories
phantom search <keyword>            # trie-powered search
phantom show <id>                   # show full summary of a memory
phantom delete <id>                 # remove a memory
phantom tag <id> <tag>             # manually add a tag

# AI commands
phantom ask "<question>"            # RAG search your brain
phantom chat                        # persistent conversation mode
phantom summarize <subject>         # summarize all notes in subject
phantom explain <topic>             # explain using your notes first

# Study commands
phantom study add <topic> <subject> # add a topic to track
phantom study review                # pop next due topic from heap
phantom study quiz <topic>          # AI quiz from your notes
phantom study flashcards <topic>    # generate flashcards
phantom study path <topic>          # BFS learning path from graph

# Utility
phantom stats                       # dashboard: files, streaks, progress
phantom export <subject>            # export revision sheet as markdown
```

---

## How Each Major Feature Works Internally

### `phantom add os.pdf`
```
1. detector.py identifies → type = "pdf"
2. pdf_reader.py extracts raw text (PyMuPDF)
3. ai/client.py sends text to Gemini →
       returns: summary, tags[], subject guess
4. Memory object created (OOP)
5. Saved to memories + tags tables (Railway PG)
6. Trie.insert(title) — search index updated
7. InvertedIndex.add(raw_text, memory_id) — keyword index updated
8. Rich panel printed: ✓ Stored | Summary | Tags
```

### `phantom ask "explain deadlock from my notes"`
```
1. Query cleaned + tokenized
2. InvertedIndex.search("deadlock") → [memory_id: 3, 7, 12]
3. Trie.search("deadlock") → ["Deadlock notes", "Deadlock avoidance"]
4. Top 3 memories fetched from DB (ranked by tag match score)
5. Their summaries injected into Gemini prompt as context
6. Gemini answers ONLY from injected context (RAG)
7. Response printed with citation: "Source: os.pdf (id: 3)"
8. Conversation saved to conversations table
```

### `phantom study review`
```
1. MinHeap.pop() → topic with earliest next_review date
2. Show topic name + subject + current confidence
3. phantom ask "explain <topic>" triggered automatically
4. You rate yourself 0-5
5. SM-2 algorithm recalculates review_interval_days
6. Topic pushed back to heap with new next_review date
7. study_log updated for streak tracking
```

---

## Two Week Schedule

---

### WEEK 1 — The Brain (Backend + Core)

---

#### Day 1 — Setup + Database
**Goal:** Project skeleton running, Railway DB connected

```
Tasks:
  □ Create Railway account, spin up PostgreSQL instance
  □ Copy DATABASE_URL into .env
  □ Create virtual environment, install all libraries
  □ Write config/settings.py (loads .env)
  □ Write db/connection.py (psycopg2 pool)
  □ Write db/schema.py and run it (creates all tables)
  □ Test: connect to Railway DB from terminal, insert a row manually

Files created today:
  .env, requirements.txt, config/settings.py,
  db/connection.py, db/schema.py
```

**requirements.txt you'll need:**
```
psycopg2-binary
google-generativeai
pymupdf
requests
beautifulsoup4
youtube-transcript-api
typer[all]
rich
python-dotenv
```

---

#### Day 2 — OOP Core Models
**Goal:** All Python classes defined and working

```
Tasks:
  □ core/memory.py
      class Memory:
          id, type, title, filename, raw_text,
          summary, subject, tags[], created_at
          methods: to_dict(), from_dict(), short_display()

  □ core/topic.py
      class Topic:
          name, subject, confidence, review_interval_days,
          last_reviewed, next_review
          methods: update_after_review(score), is_due()

      class StudySession:
          topic_name, score, duration_minutes, timestamp

  □ core/quiz.py
      class Question:
          text, options[], correct_index, explanation
      class Quiz:
          topic, questions[], attempts
          methods: run(), score()

  □ core/conversation.py
      class Message:
          role, content, timestamp, memory_refs[]
      class Conversation:
          session_id, messages[]
          methods: add_message(), get_context_window(n=10)

  □ db/queries.py
      write functions:
          save_memory(), get_memory_by_id(), get_all_memories()
          save_tag(), get_tags_for_memory()
          save_topic(), get_all_topics(), update_topic()
          save_conversation(), get_conversation_history()

Test: instantiate each class, save to DB, read back
```

---

#### Day 3 — DSA Structures
**Goal:** All 5 data structures implemented and tested

```
Tasks:
  □ dsa/trie.py
      TrieNode, Trie
      methods: insert(word), search(prefix) → [results]
      Test: insert 10 topic names, search "dead" → ["deadlock", ...]

  □ dsa/inverted_index.py
      class InvertedIndex:
          _index: dict[str, set[int]]   # word → {memory_ids}
          methods:
              add(text, memory_id)       # tokenizes + indexes
              search(query) → ranked list of memory_ids
              remove(memory_id)
      Test: add 3 memories, search "scheduling" → correct IDs

  □ dsa/min_heap.py
      class MinHeap:
          built from scratch (array-based)
          push(date, topic_name)
          pop() → (date, topic_name)
          peek()
      Test: push 5 topics with random dates, pop should be sorted

  □ dsa/lru_cache.py
      class LRUCache:
          doubly linked list + hash map (from scratch)
          get(key), put(key, value), capacity
      Test: capacity 3 cache, verify eviction works

  □ dsa/graph.py
      class TopicGraph:
          adjacency list
          add_prerequisite(prereq, topic)
          bfs_path(start) → ordered list
          get_prerequisites(topic)
      Test: build a small graph, verify BFS order
```

---

#### Day 4 — Ingest Layer
**Goal:** `phantom add` works for all file types

```
Tasks:
  □ ingest/detector.py
      detect_type(path_or_url) → "pdf" | "note" | "url" | "code" | "video"
      Logic:
          ends with .pdf → pdf
          ends with .md .txt → note
          ends with .py .cpp .js .c → code
          starts with https://youtube → video
          starts with https:// → url

  □ ingest/pdf_reader.py
      extract_text(filepath) → str
      uses: import fitz (PyMuPDF)
      handle: multi-page, clean whitespace

  □ ingest/note_reader.py
      extract_text(filepath) → str
      simple open() + read()

  □ ingest/url_scraper.py
      extract_text(url) → str
      uses: requests.get() + BeautifulSoup
      extract: title + all <p> tags

  □ ingest/youtube_reader.py
      extract_text(url) → str
      uses: YouTubeTranscriptApi
      parse video ID from URL first

Test each reader individually with a real file
```

---

#### Day 5 — AI Layer
**Goal:** Gemini integration fully working

```
Tasks:
  □ ai/prompts.py
      SUMMARIZE_PROMPT = """..."""
      QUIZ_PROMPT = """..."""
      FLASHCARD_PROMPT = """..."""
      RAG_PROMPT = """..."""
      EXPLAIN_PROMPT = """..."""
      TAGS_PROMPT = """..."""
      
      Each prompt should specify:
          - Return format (JSON where needed)
          - Tone (concise, CS student level)
          - Constraints (only use provided context for RAG)

  □ ai/client.py
      class GhostAI:
          model = gemini-1.5-flash
          methods:
              summarize(text) → {summary, tags[], subject}
              generate_quiz(topic, context) → [Question objects]
              generate_flashcards(topic, context) → [{front, back}]
              explain(topic, context) → str
              chat(messages[], context) → str

      JSON parsing: strip ```json fences, handle errors gracefully

  □ ai/rag.py
      class RAGPipeline:
          def __init__(self, inverted_index, db)
          def retrieve(query, top_k=3) → [Memory objects]
          def answer(query, session_id) → {answer, sources[]}
              1. retrieve relevant memories
              2. build context string from their summaries
              3. call GhostAI.chat() with context injected
              4. save to conversations table
              5. return answer + source citations

Test: add 2 PDFs, ask a question, verify it cites the right one
```

---

#### Day 6 — CLI Wiring (`main.py`)
**Goal:** All commands actually callable from terminal

```
Tasks:
  □ main.py skeleton with Typer
  □ Wire: phantom add → detector → reader → AI → DB → display
  □ Wire: phantom ask → RAGPipeline → display answer + sources
  □ Wire: phantom list → DB query → Rich table
  □ Wire: phantom search → Trie.search() → display results
  □ Wire: phantom show <id> → fetch memory → display full summary
  □ Wire: phantom delete <id> → DB delete + index cleanup
  □ Wire: phantom chat → loop, Conversation object, RAG on each message
  □ utils/display.py
      print_memory_card(memory)    # Rich Panel
      print_table(memories)        # Rich Table
      print_answer(text, sources)  # formatted AI response

Test full flow end to end:
  phantom add os.pdf → phantom ask "what is deadlock" → sees answer
```

---

#### Day 7 — Study Mode
**Goal:** Full spaced repetition + quiz working

```
Tasks:
  □ phantom study add <topic> <subject>
      creates Topic, saves to DB, pushes to MinHeap

  □ phantom study review
      MinHeap.pop() → show topic
      trigger RAG explain
      prompt score 0-5
      SM-2 update → save back to DB
      push back to heap with new date
      update study_log for streak

  □ phantom study quiz <topic>
      fetch memory linked to topic (or search by name)
      GhostAI.generate_quiz(topic, context)
      interactive Q&A loop in terminal
      save QuizAttempt to DB
      update topic confidence

  □ phantom study flashcards <topic>
      GhostAI.generate_flashcards()
      flip-card style CLI interaction
      press enter to reveal answer

  □ phantom study path <topic>
      load edges from DB into TopicGraph
      TopicGraph.bfs_path(topic) → ordered list
      display as numbered learning path

Test: add 3 topics, review them, verify heap order is correct
```

---

### WEEK 2 — Polish + Power Features

---

#### Day 8 — Stats Dashboard + Export
```
Tasks:
  □ phantom stats
      query: total memories, by type breakdown
      query: total topics, mastered count
      query: study_log → current streak
      query: weakest topics (confidence < 40)
      display: Rich layout with multiple panels

  □ phantom export <subject>
      fetch all memories WHERE subject = ?
      concatenate summaries
      Gemini: generate a structured revision sheet
      save as <subject>_revision.md
      display file path
```

---

#### Day 9 — Graph Features + Smart Tagging
```
Tasks:
  □ phantom study connect <topic_a> <topic_b>
      adds edge to topic_edges table
      loads into TopicGraph in memory

  □ phantom tag <id> <tag>
      adds to tags table
      updates InvertedIndex

  □ Improve auto-tagging on add:
      Gemini returns tags → save each to tags table
      on startup: load all tags into InvertedIndex

  □ phantom summarize <subject>
      fetch all memories for subject
      chunk + summarize with Gemini
      display as structured output
```

---

#### Day 10 — LRU Cache Integration + Error Handling
```
Tasks:
  □ Integrate LRUCache into GhostAI
      cache key = hash(prompt)
      if cache hit → skip API call, return cached
      capacity = 50 responses

  □ Add proper error handling everywhere:
      DB connection failures → clear error message
      Gemini API errors → retry once, then fail gracefully
      File not found → helpful message
      Rate limit hit → "Gemini limit reached, try in a minute"

  □ Add --verbose flag to CLI
      shows which memories were retrieved in RAG
      shows token count used
```

---

#### Day 11 — Startup Optimization + Index Bootstrap
```
Tasks:
  □ On every phantom startup:
      load all memory titles into Trie
      load all tags + words into InvertedIndex
      load all topics into MinHeap
      load all edges into TopicGraph
      (all from DB, happens in < 1 second for small data)

  □ Write db/bootstrap.py
      single function: load_all_into_memory(trie, index, heap, graph)
      called once at start of main.py

  □ Measure and optimize startup time
      should be under 2 seconds even with 500 memories
```

---

#### Day 12 — Testing
```
Tasks:
  □ Write tests for every DSA structure:
      trie_test.py
      heap_test.py
      lru_test.py
      graph_test.py
      inverted_index_test.py

  □ Write integration tests:
      test_add_pdf.py   → add real PDF, check DB row exists
      test_rag.py       → add note, ask question, verify answer cites it
      test_quiz.py      → generate quiz, verify JSON structure

  □ Use Python's built-in unittest (no extra libs)
```

---

#### Day 13 — README + GitHub Polish
```
Tasks:
  □ README.md:
      project description
      full install guide
      every command with example output
      architecture diagram (ASCII)
      tech stack table
      screenshot of phantom stats dashboard

  □ .gitignore:
      .env, __pycache__, venv/, *.pyc, data/

  □ requirements.txt finalized

  □ Make a clean demo:
      record a terminal session showing:
      add → list → ask → quiz → stats
      (use 'script' command on Ubuntu to record)

  □ Push to GitHub with a good commit history
      (one commit per day minimum)
```

---

#### Day 14 — Buffer / Stretch Features
```
Pick what you want:
  □ Voice input with speech_recognition library
  □ phantom diff <file1> <file2> → AI compares two notes
  □ phantom teach <topic> → Socratic mode (AI asks YOU)
  □ phantom remind → prints today's due topics on terminal open
        (add to .bashrc: phantom remind)
  □ Start FastAPI backend planning
```

---

## The Full Data Flow (One Diagram)

```
USER INPUT
    │
    ▼
main.py (Typer CLI)
    │
    ├── ADD flow
    │     │
    │     ├── ingest/ (extract raw text)
    │     ├── ai/client.py (summarize + tag)
    │     ├── core/memory.py (create object)
    │     ├── db/queries.py (save to Railway PG)
    │     ├── dsa/trie.py (insert title)
    │     └── dsa/inverted_index.py (index words)
    │
    ├── ASK flow
    │     │
    │     ├── dsa/inverted_index.py (find candidate IDs)
    │     ├── db/queries.py (fetch top memories)
    │     ├── ai/rag.py (inject context → Gemini)
    │     ├── db/queries.py (save conversation)
    │     └── utils/display.py (print answer + sources)
    │
    └── REVIEW flow
          │
          ├── dsa/min_heap.py (pop next due topic)
          ├── ai/rag.py (explain from notes)
          ├── core/topic.py (SM-2 update)
          ├── dsa/min_heap.py (push back with new date)
          └── db/queries.py (save updated topic)
```

---

## Environment Setup (Day 1 Commands)

```bash
# Clone and setup
mkdir phantom && cd phantom
python3 -m venv venv
source venv/bin/activate
pip install psycopg2-binary google-generativeai pymupdf \
            requests beautifulsoup4 youtube-transcript-api \
            typer rich python-dotenv

# .env file
DATABASE_URL=postgresql://user:pass@host:port/dbname  # from Railway
GEMINI_API_KEY=your_key_here                          # from aistudio.google.com

# Create folder structure
mkdir config db core dsa ingest ai utils
touch main.py config/settings.py db/connection.py db/schema.py \
      db/queries.py core/memory.py core/topic.py core/quiz.py \
      core/conversation.py dsa/trie.py dsa/inverted_index.py \
      dsa/min_heap.py dsa/lru_cache.py dsa/graph.py \
      ingest/detector.py ingest/pdf_reader.py ingest/note_reader.py \
      ingest/url_scraper.py ingest/youtube_reader.py \
      ai/client.py ai/rag.py ai/prompts.py \
      utils/display.py utils/helpers.py
```

---

Start Day 1 today — Railway setup takes 10 minutes and you'll have a real cloud database running before dinner. Message me when you're done with each day and I'll help you with whatever you get stuck on.