# FRAMES Benchmark — Bielik-11B-v3.0-Instruct

## TL;DR

Przetestowaliśmy polski model **Bielik-11B-v3.0-Instruct** na benchmarku FRAMES (824 pytania multi-hop z Wikipedii). Wyniki:
- **Naive** (bez kontekstu): **12.4%**
- **Oracle** (pełne artykuły Wiki w kontekście): **52.3%**

Gain od kontekstu +39.9pp pokazuje, że model aktywnie korzysta z podanego kontekstu — problem naive'a to głównie brak zaszytej wiedzy o faktach z enwiki (spodziewane dla polskiego modelu 11B), nie brak reasoning-u.

Najmocniejszy obszar: multiple constraints (57.2% oracle). Najsłabszy: numerical reasoning (31.1% oracle).

Kluczowy wzorzec w błędach: "near-miss" — model często dochodzi do poprawnej odpowiedzi i wywala się na ostatnim kroku (błędne pole, błąd arytmetyczny, self-correction w złą stronę). To sugeruje, że potencjał jest, ale brakuje fine-tuningu pod precyzyjne odpowiadanie na multi-hop questions.

**Zastrzeżenie**: oracle mode != pełny test RAG. Bez komponentu retrieval-a (który kwrobel/GregA słusznie podkreślali) nie mierzymy pełnego RAG pipeline. To jest upper bound reading comprehension (model dostaje wszystkie dokumenty na raz), nie wynik pełnego RAG pipeline z komponentem retrieval.

## Wyniki

### Accuracy globalna

| Tryb | Accuracy | n_correct / n_total |
| --- | --- | --- |
| Naive | 12.38% | 102 / 824 |
| Oracle | 52.31% | 431 / 824 |

**Dla porównania (z papera Google, Gemini Pro 1.5):**

| Tryb | Gemini Pro 1.5 | Bielik-11B-v3 | Różnica |
| --- | --- | --- | --- |
| Naive | 40.8% | 12.4% | -28.4pp |
| Oracle | 72.9% | 52.3% | -20.6pp |
| **Gain od oracle** | **+32.1pp** | **+39.9pp** | — |

Większy gain Bielika (+39.9pp vs +32.1pp) wynika z dwóch czynników: (1) niższy baseline naive'a — Bielik nie ma w pre-trainingu wiedzy o niszowych faktach z enwiki (spodziewane dla polskiego modelu 11B), więc ma więcej do zyskania z kontekstu; (2) efektywne wykorzystanie kontekstu — model jest w stanie skompensować brak wiedzy poprzez reading comprehension, co widać w wyniku 52.3% pomimo bardzo niskiego naive'a (12.4%).

Czyli: duża część gain-u to "regresja do średniej" od niskiej bazy, ale nie cała. Bez zdolności czytania ze zrozumieniem oracle nie skoczyłby tak wysoko.

### Breakdown per reasoning type

| Typ | n | Naive | Oracle | Delta |
| --- | --- | --- | --- | --- |
| Multiple constraints | 549 | 11.3% | 57.2% | +45.9pp |
| Temporal reasoning | 278 | 12.6% | 43.2% | +30.6pp |
| Tabular reasoning | 236 | 11.0% | 42.8% | +31.8pp |
| Post processing | 107 | 11.2% | 40.2% | +29.0pp |
| Numerical reasoning | 293 | 8.2% | 31.1% | +22.9pp |

**Insight**: Numerical reasoning to najsłabszy obszar (31.1% oracle vs 57.2% dla multiple constraints). Spójne z literaturą — modele tej wielkości walczą z wieloetapową arytmetyką. Multiple constraints ma najwyższy gain (+45.9pp), co sugeruje, że Bielik radzi sobie dobrze z filtrowaniem informacji z długiego kontekstu.

## 10 najciekawszych błędów

### Error 1: Model trafił prezydenta, ale pomylił imię ze środkowym imieniem

**Typ rozumowania**: Multiple constraints
**Pytanie**: What is the middle name of the U.S. president who died on the same day of the year as Virginia Woolf?
**Gold**: David
**Bielik**: Dwight
**Judge rationale**: The predicted answer is "Dwight," which is the president's first name, not his middle name. The ground truth answer is "David" (referring to Dwight David Eisenhower).
**Analiza**: Klasyczny błędny multi-hop z sukcesu częściowego. Model poprawnie rozwiązał łańcuch: data śmierci Virginii Woolf -> pasujący prezydent USA -> Eisenhower. Ale na ostatnim, trywialnym kroku pomylił imię ("Dwight") ze środkowym imieniem ("David"). Cały reasoning był poprawny — tylko ekstrakcja końcowego atrybutu zawiodła.

### Error 2: Model wybrał zły album z tej samej ery

**Typ rozumowania**: Multiple constraints
**Pytanie**: What was the last album the Grateful Dead released prior to the death of Doors vocalist Jim Morrison?
**Gold**: American Beauty
**Bielik**: The Grateful Dead did not release an album in 1971, the year Jim Morrison died. Their last album before Morrison's death was "Workingman's Dead" in 1970.
**Judge rationale**: "American Beauty" was released after "Workingman's Dead" and before Morrison's death. The predicted answer does not mention "American Beauty" at all.
**Analiza**: Model poprawnie zidentyfikował rok śmierci Morrisona (1971) i poprawnie wskazał "Workingman's Dead" (czerwiec 1970). Ale pominął "American Beauty" (listopad 1970), które wyszło po "Workingman's Dead" a przed śmiercią Morrisona (lipiec 1971). Błąd przeszukiwania dyskografii — model nie sprawdził wszystkich albumów w tym oknie czasowym.

### Error 3: Model ma poprawne daty, ale wyciąga z nich odwrotny wniosek

**Typ rozumowania**: Temporal reasoning
**Pytanie**: Was the person who served as president of the Scottish National Party from 1987 to 2005 alive when the party was founded?
**Gold**: Yes
**Bielik**: No, Winnie Ewing was not alive when the Scottish National Party was founded in 1934. She was born on 10 July 1929.
**Judge rationale**: The Scottish National Party was founded in 1934, and Winnie Ewing was born in 1929. Therefore, she was indeed alive at the time of the party's founding. The Predicted Answer states "No" which is factually incorrect.
**Analiza**: Uderzająca samosprzeczność. Model poprawnie zidentyfikował Winnie Ewing, jej datę urodzenia (1929) i datę założenia partii (1934). Ale odpowiedział "No" mimo że jego własne dane jasno pokazują, że urodziła się 5 lat wcześniej. Model pobrał poprawne fakty, ale zawiódł na trywialnym porównaniu temporalnym (1929 < 1934).

### Error 4: Poprawna data urodzenia, źle przypisany znak zodiaku

**Typ rozumowania**: Temporal reasoning
**Pytanie**: What's the star sign of the author of A Court of Thorns and Roses?
**Gold**: Pisces
**Bielik**: Sarah J. Maas, the author of A Court of Thorns and Roses, was born on March 5, 1986. According to the Western zodiac, individuals born between March 21 and April 19 are considered to be of the zodiac sign Aries. Therefore, Sarah J. Maas's star sign is Aries.
**Judge rationale**: Sarah J. Maas was born on March 5, which falls under Pisces (February 19 - March 20), not Aries (March 21 - April 19).
**Analiza**: Model poprawnie znalazł autorkę i datę urodzenia (5 marca 1986). Sam poprawnie podał zakres dat Barana (21 marca - 19 kwietnia). Ale przypisał Barana osobie urodzonej 5 marca, co ewidentnie nie pasuje do podanego zakresu. Wszystkie informacje były w outputcie — model nie zastosował własnej reguły.

### Error 5: Znalazł poprawną serię finałów, ale wybrał zły mecz

**Typ rozumowania**: Tabular reasoning
**Pytanie**: What team scored the most points in an NBA finals game while Ronald Reagan was president of the United States of America?
**Gold**: Game 1 of the Finals in 1985 the Boston Celtics scored 148 points.
**Bielik**: The Los Angeles Lakers scored the most points in an NBA Finals game while Ronald Reagan was president of the United States of America. This occurred in Game 2 of the 1985 NBA Finals, where the Lakers defeated the Boston Celtics 141-114.
**Judge rationale**: The Ground Truth Answer states that the Boston Celtics scored 148 points in Game 1 of the 1985 NBA Finals. The Predicted Answer claims the Lakers scored the most (141 points in Game 2).
**Analiza**: Model poprawnie zawęził okno czasowe do prezydentury Reagana i nawet trafił w poprawną serię (1985 NBA Finals). Ale wybrał Game 2 (Lakers 141) zamiast Game 1 (Celtics 148). Błąd skanowania tabeli — model znalazł wysoko punktowany mecz, ale nie sprawdził wszystkich meczy w serii.

### Error 6: Poprawne miasta, ale pomylone obiekty ceremonii

**Typ rozumowania**: Tabular reasoning
**Pytanie**: Which cities hosted the Olympics in 1988, and where were the opening ceremonies held in each city?
**Gold**: Calgary- Winter Olympics, opening ceremony held at McMahon Stadium. Seoul- Summer Olympics, opening ceremony held at Seoul Olympic Stadium.
**Bielik**: The 1988 Summer Olympics were held in Seoul, South Korea, with the opening ceremony taking place at the Seoul Olympic Stadium. The 1988 Winter Olympics were held in Calgary, Alberta, Canada, with the opening ceremony held at the Olympic Saddledome.
**Judge rationale**: For Calgary, the Predicted Answer states the Olympic Saddledome, while the Ground Truth correctly states McMahon Stadium.
**Analiza**: Model trafił 3 z 4 faktów (oba miasta + obiekt w Seulu), ale zhalucynował obiekt ceremonii otwarcia w Calgary. Olympic Saddledome był areną hokejową, nie miejscem ceremonii. McMahon Stadium (stadion futbolowy o większej pojemności) był rzeczywistym miejscem. Model prawdopodobnie pomylił obiekty w ramach tego samego kompleksu olimpijskiego.

### Error 7: Używa imienia zamiast drugiego imienia, i zdrobnienia zamiast pełnego imienia

**Typ rozumowania**: Post processing
**Pytanie**: As of July 1, 2024, if I wanted to give my daughter the middle name of the American woman who is the most decorated female in the history of American gymnastics as her first name and the full first name of the American woman who holds the world record in the 800-meter freestyle as her middle name, what would I name my daughter?
**Gold**: Arianne Kathleen
**Bielik**: Simone Katie
**Judge rationale**: The first name should be Biles's middle name (Arianne), not her first name (Simone). The middle name should be Ledecky's full first name (Kathleen), not her nickname (Katie).
**Analiza**: Model poprawnie zidentyfikował obie sportsmenki (Simone Biles i Katie Ledecky), ale dwukrotnie zawiódł na post-processingu. Pytanie jawnie prosiło o *środkowe imię* Biles (Arianne), a model podał *imię* (Simone). Prosiło też o *pełne imię* Ledecky (Kathleen), a model podał *zdrobnienie* (Katie). Wzorzec: model pobiera najpopularniejszą formę imienia zamiast specyficznej warianty, o którą pytano.

### Error 8: Poprawny łańcuch multi-hop, ale błąd w liczeniu słów

**Typ rozumowania**: Post processing
**Pytanie**: Archibald Sinclair had an American mom who was a half-sister. The half-sister had a life partner who had a painting of her by Walter Sickert. How many words is the title of that painting?
**Gold**: 5 (Miss Hudson at Rowlandson House)
**Bielik**: Four
**Judge rationale**: The title of the painting is "Miss Hudson at Rowlandson House," which consists of 5 words. The predicted answer is "Four."
**Analiza**: Model poprawnie przeszedł złożony łańcuch multi-hop (Archibald Sinclair -> matka -> przyrodnia siostra -> partner -> obraz Sickerta) i znalazł właściwy obraz. Ale zawiódł na trywialnym kroku post-processingu: policzeniu słów w tytule "Miss Hudson at Rowlandson House" (5, nie 4). Prawdopodobnie błąd off-by-one lub pominięcie jednego słowa.

### Error 9: Poprawne daty urodzenia, katastrofalny błąd odejmowania

**Typ rozumowania**: Numerical reasoning
**Pytanie**: How many years separate the birth of Alexander Graham Bell and the birth of Charles Dickens?
**Gold**: 35
**Bielik**: 1 year. Alexander Graham Bell was born in 1847 and Charles Dickens was born in 1812.
**Judge rationale**: The ground truth answer is 35 years (1847 - 1812). The predicted answer states "1 year" but provides the correct birth years.
**Analiza**: Niezwykły błąd arytmetyczny. Model poprawnie pobrał obie daty urodzenia (Bell: 1847, Dickens: 1812) i wyświetlił je w odpowiedzi. Odejmowanie 1847 - 1812 = 35 jest trywialne, a mimo to model podał "1 year". Wszystkie fakty poprawne — tylko końcowe obliczenie zawiodło katastrofalnie.

### Error 10: Poprawne obliczenie 50, potem nadpisane bezsensowną "korektą"

**Typ rozumowania**: Numerical reasoning
**Pytanie**: How old was Benjamin Franklin when Wolfgang Amadeus Mozart was born?
**Gold**: 50 years old.
**Bielik**: Benjamin Franklin was 19 years old when Wolfgang Amadeus Mozart was born. Franklin was born on January 17, 1706, and Mozart was born on January 27, 1756. The age difference is calculated as 1756 - 1706 = 50 years, but since Franklin's birthday is in January and Mozart's is in January as well, the exact age difference at the time of Mozart's birth would be 50 - 10 = 40 years. However, considering the exact dates, Franklin was 19 years and 10 months old when Mozart was born.
**Judge rationale**: The Predicted Answer initially calculates the age difference as 50 years (1756 - 1706), which matches the ground truth. However, the Predicted Answer then incorrectly states that Franklin was 19 years old.
**Analiza**: Fascynujący przypadek modelu, który sam siebie pokonuje. Poprawnie obliczył 1756 - 1706 = 50 i jasno to wyraził. Potem zastosował bezsensowną "korektę" (50 - 10 = 40, a następnie doszedł do 19), nadpisując poprawną odpowiedź nonsensem. Krok "50 - 10 = 40" nie ma logicznego uzasadnienia, a finalne "19 lat i 10 miesięcy" jest całkowicie oderwane od jakichkolwiek wcześniejszych obliczeń.

## Metodologia

- **Model pod testem**: `speakleash/Bielik-11B-v3.0-Instruct`, FP16, vLLM 0.19.0
- **Serwer**: 1x NVIDIA H100 NVL (96 GB VRAM) via vast.ai
- **Kontekst modelu**: 32,768 tokenów, GPU memory utilization 90%
- **Temperature**: 0.0 (powtarzalność), max_tokens: 512
- **Oracle context budget**: 80,000 znaków per pytanie (obcinanie równomierne między artykuły)
- **Sędzia**: `gpt-4.1` via OpenAI API, temperature 0.0
- **Dataset**: `google/frames-benchmark` (824 pytania, test split)
- **Prompty**: naive i oracle 1:1 z papera FRAMES, judge prompt z appendixu papera
- **Wiki cache**: 2,457 / 2,463 artykułów pobranych (99.8% coverage)
- **System prompt Bielika**: "Jesteś pomocnym asystentem Bielik."

## Zastrzeżenia (dla uczciwości porównania)

1. **Sędzia** — oryginalny paper używał `Gemini-Pro-1.5-0514` (już nie istnieje). Użyliśmy `gpt-4.1`. Zmiana sędziego potrafi dać 1-3pp różnicy. Planowany cross-check z Claude Opus 4.7.

2. **Context budget** — 80k chars to około 60% średniej pełnej treści artykułów. Mniejszy budget = niższy wynik. Ustawienie trzeba zawsze podawać przy raportowaniu.

3. **Język** — pytania po angielsku, Bielik trenowany głównie po polsku. Oracle w polskim tłumaczeniu datasetu to planowany follow-up, który pozwoli rozdzielić zdolność reasoning od rozumienia angielskiego.

4. **Jeden run** — bez wariancji. Przy temperature 0.0 wyniki są deterministyczne, ale planowany powtórny run na innym seedzie by zmierzyć wrażliwość.

## Co dalej (roadmapa)

- [ ] Cross-check sędzia Claude Opus 4.7 — weryfikacja gpt-4.1 (odchylenia >2pp = ręczna inspekcja)
- [ ] Polski oracle — tłumaczenie datasetu przez gpt-4.1, ponowny run (hipoteza: 50-65% accuracy)
- [ ] Bielik v2.6 vs v3.0 — porównanie starszej wersji w trybie naive
- [ ] BM25 retrieval mode — trzeci, bardziej realistyczny tryb (bez "oraclowych" linków)
- [ ] Analiza długości kontekstu — sweep po context-chars (20k, 40k, 60k, 80k, 100k)

## Reprodukowalność

Wszystkie prompty, kod runnera, skrypt re-fetch Wiki cache i surowe wyniki (raw JSONL) są w repozytorium:

https://github.com/JakubPrejzner/frames-bielik

Pliki wynikowe:
- `results/bielik_v3_naive.scored.jsonl` — 824 pytania, tryb naive, ocenione przez gpt-4.1
- `results/bielik_v3_oracle.scored.jsonl` — 824 pytania, tryb oracle, ocenione przez gpt-4.1
