# MiroFish Token Saving Approach

> A deep-dive into where MiroFish burns tokens unnecessarily, and **8 concrete strategies** to cut costs by 60-90%.

---

## Current Token Waste: The Audit

Before solutions, here's exactly where the money goes — file by file:

### 🔴 Phase 4: Agent Simulation — **~80% of all tokens**

**File:** [`run_parallel_simulation.py`](file:///c:/Users/shriv/MiroFish/backend/scripts/run_parallel_simulation.py)

Every round, every active agent makes **1 full LLM call** via OASIS `LLMAction()`. The agent receives:
- Its full persona (~2000 chars of system prompt)
- The social feed (recent posts, recommendations)
- Available actions list

And outputs: a single action choice (often just `DO_NOTHING`).

**The problem:** There is zero optimization here. Even a `DO_NOTHING` decision costs the same as a `CREATE_POST` with a 500-word essay. With 30 agents × 72 rounds × 2 platforms, that's potentially **4,320 LLM calls** for the simulation phase alone.

```
Per-call cost:
  Input:  ~1,500-3,000 tokens (persona + feed)
  Output: ~100-500 tokens (action decision)
  
  Total for default sim: ~6M-13M input tokens, ~400K-2M output tokens
```

---

### 🟠 Phase 3: Profile Generation — **~10% of all tokens**

**File:** [`oasis_profile_generator.py`](file:///c:/Users/shriv/MiroFish/backend/app/services/oasis_profile_generator.py)

Each agent gets **1 LLM call** to generate a 2000-character persona. The prompt includes:
- Entity attributes from the knowledge graph
- Full Zep search results (facts + related nodes)
- A massive prompt template (700+ chars of instructions)

**The problem:** Every agent gets independently generated — no shared context, no batching, no caching of similar persona types.

```
Per-call cost:
  Input:  ~2,000-4,000 tokens (context + prompt template)
  Output: ~500-2,000 tokens (persona JSON)
  
  Total for 30 agents: ~75K-120K input, ~15K-60K output
```

---

### 🟡 Phase 5: Report Generation — **~8% of all tokens**

**File:** [`report_agent.py`](file:///c:/Users/shriv/MiroFish/backend/app/services/report_agent.py)

Uses a **ReACT loop** per chapter: the system prompt alone is ~2,500 chars. Each chapter does 3-5 tool calls, and each iteration re-sends the **entire conversation history** (including all previous tool results) as context.

**The problem:** 
- Massive prompt templates are repeated every iteration
- Previous chapter content is re-sent for every new chapter
- Tool results are included in full — no summarization
- No streaming or progressive context management

```
Per-chapter cost:
  Input:  ~3,000-8,000 tokens per iteration × 3-5 iterations
  Output: ~1,000-4,000 tokens (section content)
  
  Total for 5 chapters: ~45K-200K input, ~5K-20K output
```

---

### 🟢 Phases 1-2: Config Generation — **~2% of all tokens**

**Files:** [`ontology_generator.py`](file:///c:/Users/shriv/MiroFish/backend/app/services/ontology_generator.py), [`simulation_config_generator.py`](file:///c:/Users/shriv/MiroFish/backend/app/services/simulation_config_generator.py)

Small number of calls (1 for ontology, ~5 for config). Already somewhat optimized with context truncation and batched agent configs (15 per batch).

**Not a priority for optimization.**

---

## Strategy 1: Tiered Model Architecture (Impact: 🔥🔥🔥🔥🔥)

**Estimated savings: 70-85%**

The single biggest waste: MiroFish uses the **same expensive model for everything**. Agent action decisions are simple classification tasks — they don't need GPT-4o.

### Implementation

```python
# config.py — Add tiered model configuration
class Config:
    # Tier 1: Heavy (ontology, report generation)
    LLM_HEAVY_MODEL = os.environ.get('LLM_HEAVY_MODEL', 'gpt-4o')
    LLM_HEAVY_BASE_URL = os.environ.get('LLM_HEAVY_BASE_URL', 'https://api.openai.com/v1')
    
    # Tier 2: Medium (profile generation, config generation)
    LLM_MEDIUM_MODEL = os.environ.get('LLM_MEDIUM_MODEL', 'gpt-4o-mini')
    LLM_MEDIUM_BASE_URL = os.environ.get('LLM_MEDIUM_BASE_URL', 'https://api.openai.com/v1')
    
    # Tier 3: Cheap/Local (agent action decisions during simulation)
    LLM_AGENT_MODEL = os.environ.get('LLM_AGENT_MODEL', 'llama3.1:8b')
    LLM_AGENT_BASE_URL = os.environ.get('LLM_AGENT_BASE_URL', 'http://localhost:11434/v1')
```

### Where to apply each tier

| Phase | Current Model | Recommended Tier | Why |
|-------|--------------|-----------------|-----|
| Ontology design | Same for all | **Tier 1 (Heavy)** | Creative, complex structuring task |
| Sim config generation | Same for all | **Tier 2 (Medium)** | Structured JSON output, medium complexity |
| Profile generation | Same for all | **Tier 2 (Medium)** | Creative but templated — mini models handle this well |
| Agent action decisions | Same for all | **Tier 3 (Local/Cheap)** | Pick 1 of 10 actions — trivial classification |
| Report generation | Same for all | **Tier 1 (Heavy)** | Long-form analysis, needs best reasoning |
| Agent interviews | Same for all | **Tier 2 (Medium)** | In-character responses, moderate complexity |

### Cost comparison

For a default simulation (30 agents, 72 rounds, dual-platform):

| Approach | ~LLM Calls | Estimated Cost |
|----------|-----------|---------------|
| Current (all GPT-4o) | ~2,200 | **$5-25** |
| Current (all GPT-4o-mini) | ~2,200 | **$0.25-1.50** |
| Tiered (Tier 3 = Ollama local) | ~2,200 | **$0.10-0.50** |
| Tiered (Tier 3 = Ollama) + Strategy 2 | ~1,200 | **$0.05-0.25** |

> Running Ollama locally with Llama 3.1 8B makes the simulation phase **completely free**.

---

## Strategy 2: Pre-LLM DO_NOTHING Classifier (Impact: 🔥🔥🔥🔥)

**Estimated savings: 30-50% fewer LLM calls**

Currently, even when an agent decides to do nothing, it costs a full LLM call. We can use a **lightweight rule-based filter** before calling the LLM.

### Implementation

Add this to [`run_parallel_simulation.py`](file:///c:/Users/shriv/MiroFish/backend/scripts/run_parallel_simulation.py) before the `LLMAction()` call:

```python
def should_agent_act(agent_config, current_feed, current_round, last_action_round):
    """
    Lightweight pre-filter: skip the LLM call entirely if the agent
    is unlikely to do anything meaningful this round.
    
    Returns: True = call LLM, False = auto-assign DO_NOTHING
    """
    # 1. Skip if agent is in cooldown (acted in the last round)
    if last_action_round is not None and current_round - last_action_round < 2:
        return False
    
    # 2. Skip if the feed has no new content since the agent last saw it
    if not current_feed or len(current_feed) == 0:
        return False
    
    # 3. Skip if agent's activity_level roll fails (double-check beyond time filter)
    import random
    if random.random() > agent_config.get('activity_level', 0.5) * 1.2:
        return False
    
    # 4. Skip if no relevant topics in feed
    agent_topics = set(t.lower() for t in agent_config.get('interested_topics', []))
    if agent_topics:
        feed_text = ' '.join(str(item) for item in current_feed).lower()
        if not any(topic in feed_text for topic in agent_topics):
            return False
    
    return True  # → Call LLM
```

**Impact:** For a 30-agent simulation, this typically filters out 30-50% of agents per round. That's ~600-1,000 fewer LLM calls.

---

## Strategy 3: Prompt Compression (Impact: 🔥🔥🔥)

**Estimated savings: 20-40% on input tokens**

### 3a. Persona Compression

The 2000-char persona is sent with **every single agent action call**. Most of it is backstory that doesn't change the action decision.

```python
def compress_persona_for_action(full_persona: str, max_chars: int = 600) -> str:
    """
    Create an action-focused persona summary.
    Keep: personality traits, current stance, speaking style
    Drop: backstory details, educational history, personal memories
    """
    # Option 1: Rule-based compression
    # Extract key behavioral directives from the full persona
    key_sections = []
    for line in full_persona.split('。'):
        lower = line.lower()
        if any(kw in lower for kw in ['性格', '态度', '风格', '立场', '倾向', 
                                         'mbti', '发帖', '互动', '活跃']):
            key_sections.append(line.strip())
    
    compressed = '。'.join(key_sections[:8])
    return compressed[:max_chars]
```

**Before:** ~2,000 chars persona per call × 4,320 calls = **8.6M chars of persona text**
**After:** ~600 chars persona per call × 4,320 calls = **2.6M chars of persona text** (70% reduction on persona tokens)

### 3b. Report Prompt Compression

The report agent's system prompt ([`report_agent.py`](file:///c:/Users/shriv/MiroFish/backend/app/services/report_agent.py) lines 551-791) is **~6,000 chars** and is resent with every ReACT iteration. Most of it is formatting instructions and examples.

**Fix:** Move formatting rules to the initial system prompt only. On subsequent iterations, send only the delta (tool result + continuation instruction):

```python
# Instead of re-sending the full system prompt each iteration:
followup_message = {
    "role": "user",
    "content": f"Tool result: {result}\n\nContinue with your analysis."
}
# NOT: re-sending the full 6000-char system prompt
```

---

## Strategy 4: Response Caching (Impact: 🔥🔥🔥)

**Estimated savings: 10-25% fewer LLM calls**

Agents in similar situations often make similar decisions. Cache responses by context hash:

```python
import hashlib
from functools import lru_cache

class ActionCache:
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    def _make_key(self, persona_hash: str, feed_summary: str, action_types: list) -> str:
        """Create a cache key from the agent's decision context."""
        content = f"{persona_hash}|{feed_summary[:200]}|{','.join(action_types)}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, persona_hash, feed_summary, action_types):
        key = self._make_key(persona_hash, feed_summary, action_types)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None
    
    def set(self, persona_hash, feed_summary, action_types, response):
        key = self._make_key(persona_hash, feed_summary, action_types)
        if len(self.cache) >= self.max_size:
            # Evict oldest entry
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        self.cache[key] = response
```

**Best for:** Agents with repetitive feeds (e.g., an "observer" agent who sees the same trending posts as others).

---

## Strategy 5: Batch Profile Generation (Impact: 🔥🔥)

**Estimated savings: 40-60% on profile generation tokens**

Currently in [`oasis_profile_generator.py`](file:///c:/Users/shriv/MiroFish/backend/app/services/oasis_profile_generator.py), each agent gets its own LLM call. Instead, batch similar entity types together:

```python
def batch_generate_profiles(entities: list, batch_size: int = 5) -> list:
    """
    Generate multiple profiles in a single LLM call.
    Group by entity type for better quality.
    """
    # Group entities by type
    by_type = {}
    for entity in entities:
        etype = entity.get_entity_type()
        by_type.setdefault(etype, []).append(entity)
    
    all_profiles = []
    for etype, type_entities in by_type.items():
        for batch in chunk_list(type_entities, batch_size):
            # Single LLM call for 5 profiles at once
            prompt = build_batch_persona_prompt(batch, etype)
            result = llm_client.chat_json(messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
            all_profiles.extend(result.get("profiles", []))
    
    return all_profiles
```

**Before:** 30 agents = 30 LLM calls
**After:** 30 agents ÷ 5 per batch = **6 LLM calls** (80% fewer calls, with slightly larger payloads)

---

## Strategy 6: Token Budget Manager (Impact: 🔥🔥)

**Estimated savings: Prevents runaway costs**

There's currently **zero cost tracking** anywhere in MiroFish. Add a budget-aware wrapper:

```python
class TokenBudgetManager:
    def __init__(self, max_budget_usd: float, model_pricing: dict):
        self.max_budget = max_budget_usd
        self.spent = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.pricing = model_pricing  # e.g. {"input": 0.15/1e6, "output": 0.60/1e6}
        self.call_count = 0
    
    def can_afford(self, est_input_tokens: int, est_output_tokens: int) -> bool:
        est_cost = (est_input_tokens * self.pricing["input"] + 
                    est_output_tokens * self.pricing["output"])
        return (self.spent + est_cost) <= self.max_budget
    
    def record_usage(self, response):
        """Call after each LLM response to track spending."""
        usage = response.usage
        input_cost = usage.prompt_tokens * self.pricing["input"]
        output_cost = usage.completion_tokens * self.pricing["output"]
        self.spent += input_cost + output_cost
        self.total_input_tokens += usage.prompt_tokens
        self.total_output_tokens += usage.completion_tokens
        self.call_count += 1
    
    def get_report(self) -> dict:
        return {
            "total_spent_usd": round(self.spent, 4),
            "remaining_budget_usd": round(self.max_budget - self.spent, 4),
            "total_calls": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }
```

### Integration points

Wrap the LLM client in [`llm_client.py`](file:///c:/Users/shriv/MiroFish/backend/app/utils/llm_client.py):

```python
# In LLMClient.chat() — track every call
response = self.client.chat.completions.create(**kwargs)
if self.budget_manager:
    self.budget_manager.record_usage(response)
```

### Auto-degradation

When budget runs low, automatically switch behaviors:
- **75% spent** → Switch agent decisions to cheaper model
- **90% spent** → Reduce active agents per round by 50%
- **95% spent** → Skip remaining rounds, jump to report generation

---

## Strategy 7: Smarter Report Context Management (Impact: 🔥🔥)

**Estimated savings: 30-50% on report generation tokens**

The report agent re-sends ALL previous chapter content with every new chapter. For a 5-chapter report, Chapter 5 includes Chapters 1-4 in its prompt.

### Fix: Summarize Previous Chapters

```python
def get_previous_context(completed_sections: list, max_summary_chars: int = 1000) -> str:
    """
    Instead of sending full content of all previous chapters,
    send only a compressed summary.
    """
    if not completed_sections:
        return "（尚无已完成章节）"
    
    summaries = []
    for section in completed_sections:
        # Take first 200 chars of each completed section as summary
        summary = section.content[:200] + "..." if len(section.content) > 200 else section.content
        summaries.append(f"**{section.title}**: {summary}")
    
    result = "\n".join(summaries)
    return result[:max_summary_chars]
```

### Fix: Summarize Tool Results

Tool results from Zep searches can be very large. Summarize before adding to context:

```python
def truncate_tool_result(result: str, max_chars: int = 2000) -> str:
    """Keep only the most relevant parts of tool results."""
    if len(result) <= max_chars:
        return result
    # Keep beginning and end (most relevant content is often at top)
    half = max_chars // 2
    return result[:half] + "\n\n...[内容已精简]...\n\n" + result[-half:]
```

---

## Strategy 8: OpenAI Prompt Caching (Impact: 🔥)

**Estimated savings: 10-25% on input token costs (API-level)**

OpenAI and compatible APIs support **prompt caching** for identical prompt prefixes. Since all agents share the same system prompt structure, this can be leveraged automatically.

### How to enable

For OpenAI models, prompt caching is automatic when:
1. The prompt is ≥1024 tokens
2. The prefix (system prompt) is identical across calls

MiroFish already qualifies — the OASIS system prompt (persona + action list) uses the same structure for all agents. The per-agent persona changes, but the instruction prefix is shared.

**For self-hosted models (vLLM, Ollama):** Enable prefix caching:
```bash
# vLLM
python -m vllm.entrypoints.openai.api_server \
  --model llama-3.1-8b \
  --enable-prefix-caching

# Ollama uses prefix caching by default for identical prefixes
```

---

## Priority Matrix

| # | Strategy | Implementation Effort | Token Savings | Cost Savings |
|---|----------|----------------------|---------------|-------------|
| 1 | **Tiered Models** | Medium (config changes + model routing) | N/A (same tokens, cheaper per token) | **70-85%** |
| 2 | **DO_NOTHING Classifier** | Easy (add pre-filter function) | **30-50% fewer calls** | **30-50%** |
| 3 | **Prompt Compression** | Easy-Medium (persona trimming + prompt refactor) | **20-40% input tokens** | **15-30%** |
| 4 | **Response Caching** | Medium (cache layer + hash logic) | **10-25% fewer calls** | **10-25%** |
| 5 | **Batch Profiles** | Medium (refactor profile generator) | **80% fewer profile calls** | **~5%** overall |
| 6 | **Token Budget** | Easy-Medium (wrapper class) | Prevents waste | **Prevents waste** |
| 7 | **Report Context Mgmt** | Easy (summarize previous chapters) | **30-50% report tokens** | **~3%** overall |
| 8 | **Prompt Caching (API)** | Easy (config flag) | **Auto by provider** | **10-25%** input |

### Recommended implementation order

```
Week 1: Strategy 1 (Tiered Models) + Strategy 6 (Budget Manager)
         → Immediate 70%+ cost reduction
         
Week 2: Strategy 2 (DO_NOTHING Classifier) + Strategy 3 (Prompt Compression)
         → Additional 30-50% reduction on remaining costs
         
Week 3: Strategy 4 (Response Caching) + Strategy 5 (Batch Profiles)
         → Further 10-25% reduction
         
Week 4: Strategy 7 (Report Context) + Strategy 8 (API Caching)
         → Polish and optimization
```

---

## Combined Impact Estimate

For a **default simulation** (30 agents, 72 rounds, dual-platform) using **GPT-4o**:

| Optimization Level | Est. Cost | vs. Baseline |
|-------------------|-----------|-------------|
| **No optimization** (current) | $5–25 | — |
| After Strategy 1 (local Llama for agents) | $0.50–2.00 | **-90%** |
| After Strategies 1+2 (+ DO_NOTHING filter) | $0.25–1.00 | **-95%** |
| After Strategies 1+2+3 (+ prompt compression) | $0.15–0.60 | **-97%** |
| All strategies combined | **$0.05–0.30** | **-98%** |

> [!TIP]
> The single most impactful change is **Strategy 1** — using a local model (Ollama + Llama 3.1 8B) for agent action decisions. This alone makes the simulation phase free, and it's just a config change since MiroFish already uses OpenAI-compatible APIs.
