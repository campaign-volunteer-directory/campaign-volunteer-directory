"""Deterministic issue vocabulary, derived from the stances people actually wrote.

The site's topic chips are terms candidates actually used — nothing invented,
nothing censored. This module:

  1. extracts candidate keyphrases from the stance texts (yake),
  2. strips only structural junk (stopwords, punctuation fragments,
     verb-end n-gram artifacts) — never editorial choices,
  3. canonicalizes near-duplicates to the most frequent variant,
  4. assigns each candidate the vocabulary terms present in their stances.

Every label in the vocabulary is a phrase that appears in the spreadsheet.
"""

import re

import nltk
import yake

# Stopword-ish tokens that carry no meaning on their own.
NOISE_TOKENS = {
    "a", "an", "the", "and", "or", "for", "not", "to", "of", "in", "on", "at",
    "our", "we", "you", "it", "is", "are", "be", "as", "by", "with", "from",
    "n't", "every", "main", "top", "fully", "public",
}

# yake fragments that end in a verb are broken n-grams ("expanding
# healthcare" from "expanding healthcare access"), not spreadsheet terms.
PHRASE_END_VERBS = {
    "expanding", "improving", "improve", "declaring", "funding", "protecting",
    "banning", "enforcing", "connecting", "repealing", "repeal", "raising",
    "building", "lowering", "cutting", "ending", "stopping", "supporting",
    "reforming", "getting", "keeping", "holding", "fighting", "fixing",
    "saving", "starting", "working", "bringing", "taking", "removing",
    "ensuring", "providing", "helping", "making", "investing",
    "strengthening", "increasing", "overturning", "overturn", "expand",
    "increase", "strengthen", "protect", "ensure", "provide", "invest",
    "pay", "enforce", "declare", "ban", "cap", "cut", "raise", "lower",
    "fix", "stop", "end", "start", "keep", "hold", "fight", "build", "work",
    "bring", "take", "remove", "help", "make", "get", "support", "fund",
    "reform", "connect", "save", "approving", "declaring",
}

# Verb-led phrases that ARE meaningful chips (their noun is the issue).
ALLOWED_VERB_LED = {"abolish ice", "impeach trump", "free palestine"}

# Nouns that are never issue labels ("people", "state", "system").
GENERIC_NOUNS = {
    "people", "state", "city", "system", "systems", "funding", "programs",
    "services", "community", "communities", "growth", "policy", "power",
    "families", "jobs", "job", "workers", "class", "quality", "safety",
    "energy", "utility", "solutions", "development", "access", "support",
    "reform", "increase", "make", "pay", "fight", "fund", "end", "invest",
    "tie", "impeach", "protect", "work", "workers", "money", "school",
    "schools", "education", "tax", "taxes", "rights", "costs", "cost",
    "local", "national", "federal", "government", "statewide", "main",
    "data", "corporations", "corporate", "strong", "free", "day", "focused",
    "economic", "level", "living", "congressional", "leadership", "reuse",
    "response", "capacity", "luxury", "spending", "planning", "figures",
    "subsidies", "dollars", "policies", "incentives", "resources",
    "investment", "finance", "transparency", "build", "expand", "ban",
    "cap", "legalize", "increase", "improve", "protect", "support",
    "environments", "neighborhoods", "wealth", "spending", "programs",
}

TERM_PATTERN = re.compile(r"^[a-z0-9][a-z0-9'&.,\- ]*[a-z0-9]$")


def extract_vocabulary(stance_texts, top=40):
    """Return a cleaned, frequency-ordered list of canonical issue terms.

    Multi-word phrases are the primary chips — the faithful units of meaning
    people wrote ("abolish ice", "universal healthcare"). Strong single
    tokens (nouns only, POS-tagged — never verbs like "protect") round out
    the vocabulary ("corruption", "affordability", "infrastructure").
    """
    corpus = " ".join(stance_texts)
    extractor = yake.KeywordExtractor(
        lan="en", n=2, top=300, dedupLim=0.7, dedupFunc="seqm",
        windowsSize=2, max_ngram_size=2,
    )
    raw_terms = [term for term, _ in extractor.extract_keywords(corpus)]

    cleaned = [normalize_term(t) for t in raw_terms]
    cleaned = [t for t in cleaned if t]

    phrases = [t for t in cleaned if " " in t]
    phrase_counts = count_terms(phrases, stance_texts)
    deduped_phrases = canonicalize(phrases, phrase_counts)

    singles = noun_singles(cleaned, stance_texts)
    singles = [t for t in singles if not any(t in phrase for phrase in deduped_phrases)]

    combined = deduped_phrases + singles
    counts = count_terms(combined, stance_texts)
    return sorted(combined, key=lambda t: -counts.get(t, 0))[:top]


def noun_singles(cleaned_terms, stance_texts):
    """Single-token chips that are used as nouns in the actual stances
    (contextual POS tagging, not isolated-word guesses) and frequent enough
    to mean something."""
    singles = {t for t in cleaned_terms if " " not in t}
    if not singles:
        return []
    counts = count_terms(singles, stance_texts)
    frequent = [t for t in singles if counts.get(t, 0) >= 5]
    if not frequent:
        return []
    noun_ratio = contextual_noun_ratios(frequent, stance_texts)
    nouns = [t for t in frequent
             if noun_ratio.get(t, 0) >= 0.8 and t not in GENERIC_NOUNS]
    return dedupe_plurals(nouns, counts)


def _ensure_nltk_resources():
    """Download nltk tagger + tokenizer data once (no-op when present)."""
    for resource, name in [
        ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
        ("tokenizers/punkt_tab/english", "punkt_tab"),
    ]:
        try:
            nltk.data.find(resource)
        except LookupError:
            nltk.download(name, quiet=True)


def contextual_noun_ratios(tokens, stance_texts):
    """Share of each token's occurrences tagged as a noun across the corpus."""
    _ensure_nltk_resources()
    counts = {}
    noun_counts = {}
    for text in stance_texts:
        for sentence in nltk.sent_tokenize(text):
            for word, tag in nltk.pos_tag(nltk.word_tokenize(sentence)):
                key = word.lower()
                counts[key] = counts.get(key, 0) + 1
                if tag.startswith("NN"):
                    noun_counts[key] = noun_counts.get(key, 0) + 1
    return {t: noun_counts.get(t, 0) / counts.get(t, 1) for t in tokens}


def normalize_term(term):
    """Lowercase, strip stopwords and structural junk."""
    lowered = term.lower().strip()
    if not TERM_PATTERN.match(lowered):
        return ""
    tokens = [t for t in lowered.split() if t not in NOISE_TOKENS]
    if not tokens:
        return ""
    if len(tokens) > 1 and tokens[-1] in PHRASE_END_VERBS:
        return ""
    joined = " ".join(tokens)
    if len(tokens) > 1 and tokens[0] in PHRASE_END_VERBS and joined not in ALLOWED_VERB_LED:
        return ""
    if not TERM_PATTERN.match(joined):
        return ""
    return joined


def count_terms(terms, stance_texts):
    """How many candidates' stance texts contain each term."""
    texts = [t.lower() for t in stance_texts]
    counts = {}
    for term in terms:
        counts[term] = sum(1 for text in texts if term in text)
    return counts


def canonicalize(terms, counts):
    """Dedupe near-duplicates, keeping the most frequent variant."""
    order = []
    for term in sorted(terms, key=lambda t: (-counts.get(t, 0), len(t))):
        if any(term in accepted for accepted in order):
            continue
        if any(overlaps(term, accepted) for accepted in order):
            continue
        order.append(term)
    return order


def dedupe_plurals(nouns, counts):
    """Keep the more frequent form of a singular/plural pair (wage/wages)."""
    by_stem = {}
    for noun in nouns:
        stem = singular(noun)
        prev = by_stem.get(stem)
        if prev is None or counts.get(noun, 0) > counts.get(prev, 0):
            by_stem[stem] = noun
    return sorted(by_stem.values(), key=lambda t: -counts.get(t, 0))


def overlaps(a, b):
    """True when two multi-word phrases share most of their tokens.
    Single tokens never absorb phrases ("ice" does not absorb "abolish ice")."""
    tokens_a = a.split()
    tokens_b = b.split()
    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return False
    shared = len(set(tokens_a) & set(tokens_b))
    return shared / min(len(tokens_a), len(tokens_b)) >= 0.5


def assign_topics(records, vocabulary):
    """Set record['topics'] from the vocabulary terms present in stances.

    A phrase tag applies when the phrase appears verbatim OR when any of its
    significant tokens appears — so "rent freeze" earns the "rent control"
    tag, since that phrase is what the spreadsheet actually says. All
    matching is derived from the phrase itself; nothing is invented.
    """
    match_terms = {}
    for phrase in vocabulary:
        if " " in phrase:
            tokens = [singular(t) for t in phrase.split()
                      if len(t) >= 4 and t not in GENERIC_NOUNS]
            match_terms[phrase] = [phrase] + tokens
        else:
            match_terms[phrase] = [phrase, singular(phrase)]
    for record in records:
        text = record["stances"].lower()
        tags = []
        for phrase, terms in match_terms.items():
            if any(term in text for term in terms):
                tags.append(phrase)
        record["topics"] = tags


def singular(token):
    """Naive English singularization, good enough for matching purposes."""
    if len(token) <= 3 or token.endswith("ss") or token.endswith("us"):
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("es") and token.endswith(("ses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token
