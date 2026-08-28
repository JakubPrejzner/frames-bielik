# FRAMES Benchmark — Bielik-11B-v3.0-Instruct

## TL;DR

We tested the Polish model **Bielik-11B-v3.0-Instruct** on the FRAMES benchmark (824 multi-hop questions grounded in Wikipedia). Results:
- **Naive** (no context): **12.4%**
- **Oracle** (full Wiki articles in context): **52.3%**

The +39.9pp gain from context shows the model actively uses the context it's given — the naive-mode weakness is mainly missing parametric knowledge of enwiki facts (expected for a Polish 11B model), not a lack of reasoning ability.

Strongest area: multiple constraints (57.2% oracle). Weakest: numerical reasoning (31.1% oracle).

Key error pattern: "near-miss" — the model often arrives at the correct answer and then trips on the last step (wrong field, arithmetic error, self-correction in the wrong direction). This suggests the underlying capability is there, but the model lacks fine-tuning for precise answers on multi-hop questions.

**Caveat**: oracle mode != a full RAG test. Without a retrieval component (as kwrobel/GregA rightly pointed out) we're not measuring a full RAG pipeline. This is an upper bound for reading comprehension (the model gets all documents at once), not the result of a full RAG pipeline with a retrieval component.

## Results

### Overall accuracy

| Mode | Accuracy | n_correct / n_total |
| --- | --- | --- |
| Naive | 12.38% | 102 / 824 |
| Oracle | 52.31% | 431 / 824 |

**For comparison (from Google's paper, Gemini Pro 1.5):**

| Mode | Gemini Pro 1.5 | Bielik-11B-v3 | Difference |
| --- | --- | --- | --- |
| Naive | 40.8% | 12.4% | -28.4pp |
| Oracle | 72.9% | 52.3% | -20.6pp |
| **Gain from oracle** | **+32.1pp** | **+39.9pp** | — |

Bielik's larger gain (+39.9pp vs +32.1pp) comes from two factors: (1) a lower naive baseline — Bielik's pre-training doesn't carry much knowledge of niche enwiki facts (expected for an 11B Polish model), so it has more to gain from context; (2) effective use of context — the model is able to compensate for missing knowledge through reading comprehension, visible in the 52.3% oracle score despite the very low naive score (12.4%).

In other words: a large part of the gain is "regression to the mean" from a low baseline, but not all of it. Without genuine reading-comprehension ability, oracle mode wouldn't have jumped this high.

### Breakdown by reasoning type

| Type | n | Naive | Oracle | Delta |
| --- | --- | --- | --- | --- |
| Multiple constraints | 549 | 11.3% | 57.2% | +45.9pp |
| Temporal reasoning | 278 | 12.6% | 43.2% | +30.6pp |
| Tabular reasoning | 236 | 11.0% | 42.8% | +31.8pp |
| Post processing | 107 | 11.2% | 40.2% | +29.0pp |
| Numerical reasoning | 293 | 8.2% | 31.1% | +22.9pp |

**Insight**: Numerical reasoning is the weakest area (31.1% oracle vs 57.2% for multiple constraints). Consistent with the literature — models of this size struggle with multi-step arithmetic. Multiple constraints has the highest gain (+45.9pp), suggesting Bielik is good at filtering information out of a long context.

## 10 most interesting errors

### Error 1: Model found the right president, but confused first name with middle name

**Reasoning type**: Multiple constraints
**Question**: What is the middle name of the U.S. president who died on the same day of the year as Virginia Woolf?
**Gold**: David
**Bielik**: Dwight
**Judge rationale**: The predicted answer is "Dwight," which is the president's first name, not his middle name. The ground truth answer is "David" (referring to Dwight David Eisenhower).
**Analysis**: A classic case of a wrong answer from a mostly-successful multi-hop chain. The model correctly worked through the chain: Virginia Woolf's death date -> matching U.S. president -> Eisenhower. But on the last, trivial step it confused his first name ("Dwight") with his middle name ("David"). The whole reasoning chain was correct — only the final attribute extraction failed.

### Error 2: Model picked the wrong album from the same era

**Reasoning type**: Multiple constraints
**Question**: What was the last album the Grateful Dead released prior to the death of Doors vocalist Jim Morrison?
**Gold**: American Beauty
**Bielik**: The Grateful Dead did not release an album in 1971, the year Jim Morrison died. Their last album before Morrison's death was "Workingman's Dead" in 1970.
**Judge rationale**: "American Beauty" was released after "Workingman's Dead" and before Morrison's death. The predicted answer does not mention "American Beauty" at all.
**Analysis**: The model correctly identified Morrison's death year (1971) and correctly named "Workingman's Dead" (June 1970). But it missed "American Beauty" (November 1970), which came out after "Workingman's Dead" and before Morrison's death (July 1971). A discography-scanning error — the model found a plausible album but didn't check every album in that time window.

### Error 3: Model has the correct dates, but draws the opposite conclusion

**Reasoning type**: Temporal reasoning
**Question**: Was the person who served as president of the Scottish National Party from 1987 to 2005 alive when the party was founded?
**Gold**: Yes
**Bielik**: No, Winnie Ewing was not alive when the Scottish National Party was founded in 1934. She was born on 10 July 1929.
**Judge rationale**: The Scottish National Party was founded in 1934, and Winnie Ewing was born in 1929. Therefore, she was indeed alive at the time of the party's founding. The Predicted Answer states "No" which is factually incorrect.
**Analysis**: A striking self-contradiction. The model correctly identified Winnie Ewing, her birth date (1929), and the party's founding date (1934). But it answered "No" even though its own stated facts clearly show she was born 5 years earlier. The model retrieved the correct facts but failed a trivial temporal comparison (1929 < 1934).

### Error 4: Correct birth date, wrong zodiac sign assigned

**Reasoning type**: Temporal reasoning
**Question**: What's the star sign of the author of A Court of Thorns and Roses?
**Gold**: Pisces
**Bielik**: Sarah J. Maas, the author of A Court of Thorns and Roses, was born on March 5, 1986. According to the Western zodiac, individuals born between March 21 and April 19 are considered to be of the zodiac sign Aries. Therefore, Sarah J. Maas's star sign is Aries.
**Judge rationale**: Sarah J. Maas was born on March 5, which falls under Pisces (February 19 - March 20), not Aries (March 21 - April 19).
**Analysis**: The model correctly found the author and her birth date (March 5, 1986). It even correctly stated the Aries date range (March 21 - April 19). But it then assigned Aries to someone born March 5, which obviously falls outside that range. All the information was in the output — the model just didn't apply its own stated rule.

### Error 5: Found the right finals series, but picked the wrong game

**Reasoning type**: Tabular reasoning
**Question**: What team scored the most points in an NBA finals game while Ronald Reagan was president of the United States of America?
**Gold**: Game 1 of the Finals in 1985 the Boston Celtics scored 148 points.
**Bielik**: The Los Angeles Lakers scored the most points in an NBA Finals game while Ronald Reagan was president of the United States of America. This occurred in Game 2 of the 1985 NBA Finals, where the Lakers defeated the Boston Celtics 141-114.
**Judge rationale**: The Ground Truth Answer states that the Boston Celtics scored 148 points in Game 1 of the 1985 NBA Finals. The Predicted Answer claims the Lakers scored the most (141 points in Game 2).
**Analysis**: The model correctly narrowed the time window to Reagan's presidency and even landed on the correct series (1985 NBA Finals). But it picked Game 2 (Lakers, 141) instead of Game 1 (Celtics, 148). A table-scanning error — the model found a high-scoring game but didn't check every game in the series.

### Error 6: Correct cities, but mixed up the ceremony venues

**Reasoning type**: Tabular reasoning
**Question**: Which cities hosted the Olympics in 1988, and where were the opening ceremonies held in each city?
**Gold**: Calgary- Winter Olympics, opening ceremony held at McMahon Stadium. Seoul- Summer Olympics, opening ceremony held at Seoul Olympic Stadium.
**Bielik**: The 1988 Summer Olympics were held in Seoul, South Korea, with the opening ceremony taking place at the Seoul Olympic Stadium. The 1988 Winter Olympics were held in Calgary, Alberta, Canada, with the opening ceremony held at the Olympic Saddledome.
**Judge rationale**: For Calgary, the Predicted Answer states the Olympic Saddledome, while the Ground Truth correctly states McMahon Stadium.
**Analysis**: The model got 3 out of 4 facts right (both cities plus the Seoul venue), but hallucinated the opening-ceremony venue in Calgary. The Olympic Saddledome was a hockey arena, not the ceremony venue — McMahon Stadium (a larger-capacity football stadium) was the actual site. The model likely confused venues within the same Olympic complex.

### Error 7: Uses first name instead of middle name, and a nickname instead of the full first name

**Reasoning type**: Post processing
**Question**: As of July 1, 2024, if I wanted to give my daughter the middle name of the American woman who is the most decorated female in the history of American gymnastics as her first name and the full first name of the American woman who holds the world record in the 800-meter freestyle as her middle name, what would I name my daughter?
**Gold**: Arianne Kathleen
**Bielik**: Simone Katie
**Judge rationale**: The first name should be Biles's middle name (Arianne), not her first name (Simone). The middle name should be Ledecky's full first name (Kathleen), not her nickname (Katie).
**Analysis**: The model correctly identified both athletes (Simone Biles and Katie Ledecky), but failed twice on the post-processing step. The question explicitly asked for Biles's *middle* name (Arianne), and the model gave her *first* name (Simone). It also asked for Ledecky's *full* first name (Kathleen), and the model gave the *nickname* (Katie). Pattern: the model retrieves the most common form of a name instead of the specific variant asked for.

### Error 8: Correct multi-hop chain, but a word-counting error

**Reasoning type**: Post processing
**Question**: Archibald Sinclair had an American mom who was a half-sister. The half-sister had a life partner who had a painting of her by Walter Sickert. How many words is the title of that painting?
**Gold**: 5 (Miss Hudson at Rowlandson House)
**Bielik**: Four
**Judge rationale**: The title of the painting is "Miss Hudson at Rowlandson House," which consists of 5 words. The predicted answer is "Four."
**Analysis**: The model correctly walked through a complex multi-hop chain (Archibald Sinclair -> mother -> half-sister -> partner -> Sickert painting) and found the right painting. But it failed on the trivial post-processing step: counting the words in "Miss Hudson at Rowlandson House" (5, not 4). Likely an off-by-one error or a dropped word.

### Error 9: Correct birth dates, catastrophic subtraction error

**Reasoning type**: Numerical reasoning
**Question**: How many years separate the birth of Alexander Graham Bell and the birth of Charles Dickens?
**Gold**: 35
**Bielik**: 1 year. Alexander Graham Bell was born in 1847 and Charles Dickens was born in 1812.
**Judge rationale**: The ground truth answer is 35 years (1847 - 1812). The predicted answer states "1 year" but provides the correct birth years.
**Analysis**: An unusual arithmetic error. The model correctly retrieved both birth years (Bell: 1847, Dickens: 1812) and stated them in its answer. Subtracting 1847 - 1812 = 35 is trivial, yet the model answered "1 year." All the facts were correct — only the final calculation failed catastrophically.

### Error 10: Correctly computes 50, then overwrites it with a nonsensical "correction"

**Reasoning type**: Numerical reasoning
**Question**: How old was Benjamin Franklin when Wolfgang Amadeus Mozart was born?
**Gold**: 50 years old.
**Bielik**: Benjamin Franklin was 19 years old when Wolfgang Amadeus Mozart was born. Franklin was born on January 17, 1706, and Mozart was born on January 27, 1756. The age difference is calculated as 1756 - 1706 = 50 years, but since Franklin's birthday is in January and Mozart's is in January as well, the exact age difference at the time of Mozart's birth would be 50 - 10 = 40 years. However, considering the exact dates, Franklin was 19 years and 10 months old when Mozart was born.
**Judge rationale**: The Predicted Answer initially calculates the age difference as 50 years (1756 - 1706), which matches the ground truth. However, the Predicted Answer then incorrectly states that Franklin was 19 years old.
**Analysis**: A fascinating case of the model defeating itself. It correctly computed 1756 - 1706 = 50 and stated it clearly. Then it applied a nonsensical "correction" (50 - 10 = 40, eventually landing on 19), overwriting the correct answer with nonsense. The step "50 - 10 = 40" has no logical basis, and the final "19 years and 10 months" is completely disconnected from any of the preceding calculations.

## Methodology

- **Model under test**: `speakleash/Bielik-11B-v3.0-Instruct`, FP16, vLLM 0.19.0
- **Server**: 1x NVIDIA H100 NVL (96 GB VRAM) via vast.ai
- **Model context**: 32,768 tokens, GPU memory utilization 90%
- **Temperature**: 0.0 (for reproducibility), max_tokens: 512
- **Oracle context budget**: 80,000 characters per question (truncated evenly across articles)
- **Judge**: `gpt-4.1` via OpenAI API, temperature 0.0
- **Dataset**: `google/frames-benchmark` (824 questions, test split)
- **Prompts**: naive and oracle prompts taken 1:1 from the FRAMES paper, judge prompt from the paper appendix
- **Wiki cache**: 2,457 / 2,463 articles fetched (99.8% coverage)
- **Bielik system prompt**: "You are Bielik, a helpful assistant." (sent in Polish, matching the model's primary training language)

## Caveats (for a fair comparison)

1. **Judge** — the original paper used `Gemini-Pro-1.5-0514` (no longer available). We used `gpt-4.1` instead. Swapping the judge can shift results by 1-3pp. A cross-check with Claude Opus 4.7 is planned.

2. **Context budget** — 80k chars is roughly 60% of the average full article content. A smaller budget means a lower score. This setting should always be reported alongside any accuracy number.

3. **Language** — questions are in English, while Bielik is trained primarily on Polish. An oracle run on a Polish translation of the dataset is a planned follow-up, which would let us separate reasoning ability from English-comprehension ability.

4. **Single run** — no variance measurement. At temperature 0.0 the results are deterministic, but a repeat run with a different seed is planned to measure sensitivity.

## Roadmap

- [ ] Cross-check judge with Claude Opus 4.7 — verification against gpt-4.1 (deviations >2pp trigger manual inspection)
- [ ] Polish oracle — dataset translated via gpt-4.1, re-run (hypothesis: 50-65% accuracy)
- [ ] Bielik v2.6 vs v3.0 — compare the older version in naive mode
- [ ] BM25 retrieval mode — a third, more realistic mode (without "oracle" links)
- [ ] Context-length analysis — sweep over context-chars (20k, 40k, 60k, 80k, 100k)

## Reproducibility

All prompts, the runner code, the Wiki cache re-fetch script, and the raw results (raw JSONL) are in the repository:

https://github.com/JakubPrejzner/frames-bielik

Result files:
- `results/bielik_v3_naive.scored.jsonl` — 824 questions, naive mode, scored by gpt-4.1
- `results/bielik_v3_oracle.scored.jsonl` — 824 questions, oracle mode, scored by gpt-4.1
